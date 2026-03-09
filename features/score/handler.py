import re
import logging
import os
import json
from datetime import datetime, date
from telegram import Update
from telegram.ext import ContextTypes

from auth.scorer import scorer_only  # 使用统一的权限装饰器
from db.score_db import (
    record_score,
    record_fail,
    record_reply,
    get_recent_scores,
    get_today_total,
    get_message_score_history,
    get_user_total_scores,  # 从数据库获取用户总分统计
    get_user_score_statistics,  # 用于调试
)
from db.submit_db import get_user_id_by_message
from utils.group import get_group_name
from utils.extract import extract_logical_group
from utils.reminder import reminder_manager

logger = logging.getLogger(__name__)

SCORE_PATTERN = re.compile(r"^[+-]\d+$")
FAIL_KEYWORD = "失败"


def _get_original_user_display(replied_text):
    """
    从被回复的消息中提取原始用户的显示信息
    格式通常是: 用户名\n数据\n数字
    我们需要提取第一行的用户名
    """
    if not replied_text:
        return "未知用户"
    
    lines = replied_text.strip().split('\n')
    if len(lines) >= 1:
        # 第一行是用户名，可能包含表情符号
        original_user = lines[0].strip()
        return original_user if original_user else "未知用户"
    
    return "未知用户"


def _format_time_display(time_str):
    """
    格式化时间显示为 [时:分:秒]
    """
    try:
        if ' ' in time_str:
            # 格式: "2024-01-20 10:57:30"
            time_part = time_str.split(' ')[1]
            return f"[{time_part}]"
        elif 'T' in time_str:
            # 格式: "2024-01-20T10:57:30.123456"
            time_part = time_str.split('T')[1].split('.')[0]
            return f"[{time_part}]"
        else:
            # 已经是时间格式
            return f"[{time_str}]"
    except:
        return f"[{time_str}]"


def _get_user_scores_from_db(tg_group_id):
    """
    直接从数据库获取用户分数统计
    确保数据是最新的
    """
    try:
        # 直接调用数据库函数获取用户总分统计
        user_scores = get_user_total_scores(tg_group_id)
        group_total = sum(user_scores.values())
        
        # 调试信息
        logger.info(f"📊 从数据库获取用户分数统计: {len(user_scores)} 个用户，总分: {group_total}")
        
        # 如果数据库返回为空，尝试使用更详细的统计函数
        if not user_scores:
            logger.warning("用户总分统计为空，尝试使用详细统计函数...")
            detailed_stats = get_user_score_statistics(tg_group_id)
            
            # 从详细统计中提取用户分数
            user_scores = {}
            for group, group_info in detailed_stats.get("user_stats", {}).items():
                for user_info in group_info.get("users", []):
                    user_scores[user_info["username"]] = user_info["score"]
            
            group_total = detailed_stats.get("group_total", 0)
            logger.info(f"📊 从详细统计获取用户分数: {len(user_scores)} 个用户，总分: {group_total}")
        
        return user_scores, group_total
    except Exception as e:
        logger.error(f"获取用户分数统计失败: {e}")
        # 返回空数据
        return {}, 0


# ==========================================================
# 清理强制统计缓存函数（保留用于兼容性）
# ==========================================================

def clear_force_stats_cache(tg_group_id: int = None):
    """
    清理强制统计缓存
    由于现在我们直接从数据库获取数据，这个函数主要用于清理旧备份文件
    """
    try:
        backup_file = "data/force_stats_backup.json"
        
        if tg_group_id:
            # 只清理指定群组的缓存
            if os.path.exists(backup_file):
                with open(backup_file, 'r', encoding='utf-8') as f:
                    backup_data = json.load(f)
                    if backup_data.get("tg_group_id") == tg_group_id:
                        os.remove(backup_file)
                        logger.info(f"🗑 清理群组 {tg_group_id} 的强制统计备份文件")
        else:
            # 清理所有缓存
            if os.path.exists(backup_file):
                os.remove(backup_file)
                logger.info("🗑 清理所有强制统计备份文件")
        
        logger.info("✅ 强制统计备份文件已清理")
        
    except Exception as e:
        logger.error(f"清理强制统计备份文件失败: {e}")


def _get_grouped_scores_from_db(tg_group_id):
    """
    从数据库获取按逻辑分组的分数统计
    返回格式: {逻辑组名: 总分, ...}
    """
    try:
        # 使用 user_score_statistics 获取分组数据
        user_stats = get_user_score_statistics(tg_group_id)
        
        # 提取分组总分
        grouped_scores = {}
        for logical_group, group_info in user_stats.get("user_stats", {}).items():
            grouped_scores[logical_group] = group_info.get("total_score", 0)
        
        group_total = user_stats.get("group_total", 0)
        
        logger.info(f"📊 从数据库获取分组分数统计: {len(grouped_scores)} 个分组，总分: {group_total}")
        
        return grouped_scores, group_total
    except Exception as e:
        logger.error(f"获取分组分数统计失败: {e}")
        # 返回空数据
        return {}, 0


@scorer_only
async def handle_score_reply(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    群组评分 / 失败 / 回复 handler
    直接从数据库获取统计数据，确保数据一致性
    """
    message = update.message
    user = update.effective_user

    if not message or not message.reply_to_message:
        return

    replied = message.reply_to_message
    chat = message.chat

    # 只处理群组
    if chat.type not in ("group", "supergroup"):
        return

    tg_group_id = chat.id
    group_name = get_group_name(tg_group_id)
    target_msg_id = replied.message_id
    
    # ==============================================
    # ⚠️ 重要：首先标记消息为已处理（无论是什么回复）
    # ==============================================
    reminder_manager['mark_as_processed'](
        group_id=tg_group_id,
        message_id=target_msg_id
    )
    logger.info(f"✅ 消息标记为已处理: group={tg_group_id}, message={target_msg_id}")
    
    # ⚠️ 被回复的消息必须是机器人转发的数据消息
    if not replied.from_user or not replied.from_user.is_bot:
        return

    text = message.text.strip() if message.text else ""

    logical_group = extract_logical_group(replied.text or "")
    
    # ==============================================
    # 获取被评分的原始用户信息
    # ==============================================
    original_user_display = _get_original_user_display(replied.text)
    
    # ==============================================
    # 获取原始发送者ID
    # ==============================================
    original_sender_id = None
    if replied.forward_from:
        original_sender_id = replied.forward_from.id
        logger.info(f"从转发信息获取到用户ID: {original_sender_id}")
    else:
        original_sender_id = get_user_id_by_message(tg_group_id, target_msg_id)
        if original_sender_id:
            logger.info(f"从数据库获取到用户ID: {original_sender_id}")
        else:
            logger.warning(f"无法获取消息 {target_msg_id} 的发送者ID")
    
    # 获取管理员的用户名（仅用于记录）
    admin_username = ""
    if user.first_name and user.last_name:
        admin_username = f"{user.first_name} {user.last_name}"
    elif user.first_name:
        admin_username = user.first_name
    elif user.username:
        admin_username = user.username
    else:
        admin_username = str(user.id)

    # ================================
    # 1️⃣ 评分（+8 / -5）
    # ================================
    if SCORE_PATTERN.match(text):
        score_delta = int(text)
        score_sign = "+" if score_delta > 0 else ""
        
        # 记录评分开始
        logger.info(f"🎯 开始处理评分: {original_user_display} -> {logical_group} = {score_delta:+}")

        try:
            # 1. 首先记录评分到数据库
            record_score(
                tg_group_id=tg_group_id,
                logical_group=logical_group,
                operator_id=user.id,
                operator_name=admin_username,
                target_msg_id=target_msg_id,
                original_sender_id=original_sender_id,
                original_sender_name=original_user_display,
                score_delta=score_delta,
                force=False,
            )
            logger.info(f"✅ 数据库评分记录成功: {original_user_display} -> {score_delta:+}")
            
            # 2. 从数据库获取最新的分组统计数据
            grouped_scores, group_total = _get_grouped_scores_from_db(tg_group_id)
            
            # 3. 获取消息的评分历史（用于显示）
            score_history = get_message_score_history(tg_group_id, target_msg_id)
            
            # 4. 获取群组最近5条评分记录
            recent_records = get_recent_scores(tg_group_id, limit=5)
            logger.info(f"📝 获取到 {len(recent_records)} 条群组最近评分记录")

            # 构建回复消息
            reply = f"✅ 评分已更新：{score_sign}{score_delta}\n"
            
            # 如果有评分历史，显示历史记录 - 修复：显示被评分的用户而不是管理员
            if score_history:
                reply += f"\n📝 本消息评分历史（共 {len(score_history)} 次）：\n"
                
                for i, record in enumerate(score_history[:5], 1):
                    time_str = _format_time_display(record['time'])
                    record_score_sign = "+" if record['score'] > 0 else ""
                    # 使用被评分的用户显示名称，而不是管理员
                    reply += f"  - {time_str} {original_user_display} ➜ 分数：{record_score_sign}{record['score']}\n"
                
                # 计算历史总分
                history_total = sum(record['score'] for record in score_history)
                reply += f"  📊 本消息历史总分: {history_total} (本次: {score_delta:+})\n"
            
            reply += "\n🕓 群组最近 5 条评分记录：\n"
            if recent_records:
                for r in recent_records[:5]:
                    time_str = _format_time_display(r['time'])
                    record_score_sign = "+" if r['score'] > 0 else ""
                    user_display = r.get('user', '未知用户')
                    reply += f" - {time_str} {user_display} ➜ 分数：{record_score_sign}{r['score']}\n"
            else:
                reply += " - 暂无最近评分记录\n"

            # 显示按逻辑分组的总分统计
            reply += "\n📊 今日各组总分统计：\n"
            if grouped_scores:
                # 按分数降序排序
                sorted_groups = sorted(grouped_scores.items(), key=lambda x: x[1], reverse=True)
                for group_name_display, total_score in sorted_groups:
                    reply += f"  {group_name_display}今日总分：{total_score} 分\n"
            else:
                reply += "  暂无分组分数记录\n"
            
            reply += f"\n🏁 今日本群总分：{group_total}\n"
            # 修复：显示实际群组名称而不是逻辑分组
            reply += f"📍 当前群组：{group_name}"

            await message.reply_text(reply)

        except Exception as e:
            # 如果普通评分失败，尝试使用强制模式
            logger.error(f"评分失败，尝试强制评分: {e}")
            try:
                # 强制记录评分
                record_score(
                    tg_group_id=tg_group_id,
                    logical_group=logical_group,
                    operator_id=user.id,
                    operator_name=admin_username,
                    target_msg_id=target_msg_id,
                    original_sender_id=original_sender_id,
                    original_sender_name=original_user_display,
                    score_delta=score_delta,
                    force=True,
                )
                logger.info(f"✅ 强制评分记录成功: {original_user_display} -> {score_delta:+}")
                
                # 从数据库获取最新的分组统计数据
                grouped_scores, group_total = _get_grouped_scores_from_db(tg_group_id)

                reply = f"✅ 评分已强制更新：{score_sign}{score_delta}\n\n"
                reply += "📊 今日各组总分统计：\n"
                if grouped_scores:
                    sorted_groups = sorted(grouped_scores.items(), key=lambda x: x[1], reverse=True)
                    for group_name_display, total_score in sorted_groups:
                        reply += f"  {group_name_display}今日总分：{total_score} 分\n"
                else:
                    reply += "  暂无分组分数记录\n"
                reply += f"\n🏁 今日本群总分：{group_total}\n"
                # 修复：显示实际群组名称而不是逻辑分组
                reply += f"📍 当前群组：{group_name}"

                await message.reply_text(reply)
            except Exception as e2:
                logger.error(f"强制评分也失败: {e2}")
                await message.reply_text(
                    f"❌ 评分失败，请稍后重试\n"
                    f"错误信息: {str(e2)[:100]}"
                )

        return

    # ================================
    # 2️⃣ 失败
    # ================================
    if text == FAIL_KEYWORD:
        try:
            # 记录失败操作
            record_fail(
                tg_group_id=tg_group_id,
                logical_group=logical_group,
                operator_id=user.id,
                operator_name=admin_username,
                target_msg_id=target_msg_id,
                original_sender_id=original_sender_id,
                original_sender_name=original_user_display,
            )

            # 尝试通知用户
            user_notified = False
            notification_error = None
            
            if original_sender_id:
                try:
                    await context.bot.send_message(
                        chat_id=original_sender_id,
                        text=(
                            f"{replied.text}\n\n"
                            "❌ 该数据处理失败，请核对后重试。"
                        ),
                    )
                    user_notified = True
                    logger.info(f"✅ 失败通知已发送给用户 {original_sender_id}")
                except Exception as user_error:
                    notification_error = str(user_error)
                    logger.warning(f"⚠️ 无法通知用户 {original_sender_id}: {user_error}")
            else:
                logger.warning(f"⚠️ original_sender_id 为空，无法通知用户")

            if user_notified:
                await message.reply_text("❌ 已标记为失败，并通知原发送者")
            else:
                error_msg = f"❌ 已标记为失败，但无法通知原发送者"
                if notification_error:
                    error_msg += f"\n原因: {notification_error[:50]}"
                await message.reply_text(error_msg)

        except Exception as e:
            logger.error(f"标记失败失败: {e}")
            await message.reply_text(f"❌ 标记失败时出错: {str(e)[:100]}")
        return

    # ================================
    # 3️⃣ 普通文字回复
    # ================================
    if message.text:
        try:
            # 记录回复操作
            record_reply(
                tg_group_id=tg_group_id,
                logical_group=logical_group,
                operator_id=user.id,
                operator_name=admin_username,
                target_msg_id=target_msg_id,
                original_sender_id=original_sender_id,
                original_sender_name=original_user_display,
                reply_type="reply_text",
                content=message.text,
            )

            # 尝试通知用户
            user_notified = False
            notification_error = None
            
            if original_sender_id:
                try:
                    await context.bot.send_message(
                        chat_id=original_sender_id,
                        text=(
                            f"{replied.text}\n\n"
                            f"📩 评分反馈：\n{message.text}"
                        ),
                    )
                    user_notified = True
                    logger.info(f"✅ 文字反馈已发送给用户 {original_sender_id}")
                except Exception as user_error:
                    notification_error = str(user_error)
                    logger.warning(f"⚠️ 无法发送文字反馈给用户 {original_sender_id}: {user_error}")
            else:
                logger.warning(f"⚠️ original_sender_id 为空，无法发送文字反馈")

            if user_notified:
                await message.reply_text("📨 已将回复发送给原发送者")
            else:
                error_msg = f"📨 已将回复记录，但无法发送给原发送者"
                if notification_error:
                    error_msg += f"\n原因: {notification_error[:50]}"
                await message.reply_text(error_msg)
                
        except Exception as e:
            logger.error(f"记录回复失败: {e}")
            await message.reply_text(f"❌ 记录回复时出错: {str(e)[:100]}")
        return

    # ================================
    # 4️⃣ 图片回复
    # ================================
    if message.photo:
        photo = message.photo[-1]

        try:
            # 记录图片回复操作
            record_reply(
                tg_group_id=tg_group_id,
                logical_group=logical_group,
                operator_id=user.id,
                operator_name=admin_username,
                target_msg_id=target_msg_id,
                original_sender_id=original_sender_id,
                original_sender_name=original_user_display,
                reply_type="reply_photo",
                content=photo.file_id,
            )

            # 尝试通知用户
            user_notified = False
            notification_error = None
            
            if original_sender_id:
                try:
                    await context.bot.send_photo(
                        chat_id=original_sender_id,
                        photo=photo.file_id,
                        caption=replied.text or "",
                    )
                    user_notified = True
                    logger.info(f"✅ 图片反馈已发送给用户 {original_sender_id}")
                except Exception as user_error:
                    notification_error = str(user_error)
                    logger.warning(f"⚠️ 无法发送图片反馈给用户 {original_sender_id}: {user_error}")
            else:
                logger.warning(f"⚠️ original_sender_id 为空，无法发送图片反馈")

            if user_notified:
                await message.reply_text("🖼 已将图片发送给原发送者")
            else:
                error_msg = f"🖼 已将图片记录，但无法发送给原发送者"
                if notification_error:
                    error_msg += f"\n原因: {notification_error[:50]}"
                await message.reply_text(error_msg)
            
        except Exception as e:
            logger.error(f"发送图片失败: {e}")
            await message.reply_text(f"❌ 发送图片失败: {str(e)[:100]}")
        return


# ==========================================================
# 程序启动时清理旧的缓存文件，确保使用数据库数据
# ==========================================================
def init_score_handler():
    """初始化评分处理器"""
    try:
        # 清理所有强制统计备份文件，确保从数据库获取数据
        backup_file = "data/force_stats_backup.json"
        if os.path.exists(backup_file):
            os.remove(backup_file)
            logger.info("🗑 清理旧的强制统计备份文件")
        
        logger.info("✅ 评分处理器初始化完成，使用数据库作为唯一数据源")
    except Exception as e:
        logger.error(f"初始化评分处理器失败: {e}")


# 在模块导入时初始化
init_score_handler()