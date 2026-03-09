import logging
from datetime import datetime, date
from typing import List

from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.score_db import (
    get_today_total,
    get_user_score_statistics,  # 使用新的用户统计函数
)
from utils.group import get_group_name

logger = logging.getLogger(__name__)


async def report_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    管理员命令：
    /report
    今日详细统计（按逻辑分组 -> 按用户，只显示总分）
    统计被评分的用户的得分情况
    """
    user = update.effective_user
    chat = update.effective_chat

    # ===== 权限校验 =====
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以查看统计")
        return

    # ===== 只允许在群组中使用 =====
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ 请在群组中使用该命令")
        return

    tg_group_id = chat.id
    group_name = get_group_name(tg_group_id)
    today_date = date.today().strftime("%Y-%m-%d")
    current_time = datetime.now().strftime("%H:%M")
    
    # 发送处理中的消息
    processing_msg = await update.message.reply_text("📊 正在生成统计报告，请稍候...")
    
    try:
        # 获取用户评分统计
        user_stats = get_user_score_statistics(tg_group_id)
        
        if not user_stats.get("user_stats"):
            await processing_msg.edit_text(
                f"📊 今日暂无评分记录\n"
                f"📍 当前群组：{group_name}\n"
                f"📅 日期：{today_date}"
            )
            return

        # ===== 构建详细统计报表（按用户分组） =====
        lines = []
        
        # 头部信息（使用示例中的格式）
        lines.append(f"📊 {group_name} - 今日统计（{today_date}）")
        lines.append(f"🎯 今日本群总分：{user_stats['group_total']}")
        lines.append("")
        lines.append("─" * 60)  # 分割线
        
        # 处理每个逻辑分组中的用户
        for logical_group, group_info in user_stats["user_stats"].items():
            group_total_score = group_info["total_score"]
            user_count = group_info["user_count"]
            
            # 添加组标题（使用示例中的格式）
            lines.append("")
            lines.append(f"🏆 {logical_group}（总分：{group_total_score}分，成员：{user_count}人）")
            lines.append("")
            
            # 添加用户列表（最多显示30个）
            for i, user in enumerate(group_info["users"][:30], 1):
                username = ' '.join(str(user["username"]).split())  # 清理空格
                score_display = f"{user['score']:>4}分"
                # 用户名最大显示宽度为25个字符，左对齐
                username_display = username[:25] if len(username) <= 25 else username[:22] + "..."
                username_display = f"{username_display:<25}"
                lines.append(f"{i:>2}. {username_display}：{score_display}")
            
            # 如果还有更多用户，显示统计
            if len(group_info["users"]) > 30:
                remaining_count = len(group_info["users"]) - 30
                remaining_score = sum(user["score"] for user in group_info["users"][30:])
                lines.append(f"   ... 还有 {remaining_count} 位用户，共 {remaining_score}分")
            
            lines.append("")
            lines.append("─" * 60)  # 分割线
        
        # 底部信息（使用示例中的格式）
        lines.append("")
        lines.append(f"💡 统计范围：今日（{today_date}）00:00 - {current_time}")
        
        # 发送统计报告
        report_text = "\n".join(lines)
        
        # 如果报告太长，分割发送
        if len(report_text) > 4000:
            chunks = _split_long_message(lines)
            
            for i, chunk in enumerate(chunks):
                if i == 0:
                    await processing_msg.edit_text(chunk)
                else:
                    await update.message.reply_text(f"（续 {i+1}/{len(chunks)}）\n{chunk}")
        else:
            await processing_msg.edit_text(report_text)
            
    except Exception as e:
        logger.error(f"生成统计报告失败: {e}", exc_info=True)
        await processing_msg.edit_text(f"❌ 生成统计报告失败：{str(e)[:100]}")


def _split_long_message(lines: list, max_length: int = 4000) -> list:
    """分割长消息"""
    chunks = []
    current_chunk = []
    current_length = 0
    
    for line in lines:
        line_length = len(line) + 1  # +1 for newline
        
        if current_length + line_length < max_length:
            current_chunk.append(line)
            current_length += line_length
        else:
            if current_chunk:
                chunks.append("\n".join(current_chunk))
            current_chunk = [line]
            current_length = line_length
    
    if current_chunk:
        chunks.append("\n".join(current_chunk))
    
    return chunks