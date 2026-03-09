import re
import logging
from telegram import Update, Message
from telegram.ext import ContextTypes

from auth.team import team_only
from config.settings import settings
from db.submit_db import (
    is_duplicate_recent,
    is_duplicate_data,
    insert_submission,
    save_to_group_records,
    get_duplicate_summary_old_format,
)
from utils.forward import forward_to_group
from utils.reminder import reminder_manager  # 新增导入

logger = logging.getLogger(__name__)

# =============================
# 正则规则
# =============================
RE_11_13_DIGIT = re.compile(r"^(\d{11}|\d{13})$")
RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RE_UUID = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def _valid_data(text: str) -> bool:
    return (
        RE_11_13_DIGIT.fullmatch(text)
        or RE_EMAIL.fullmatch(text)
        or RE_UUID.fullmatch(text)
    )


def _ensure_username(user) -> str:
    """
    确保用户名包含"组"字以满足统计要求
    优先使用个人资料姓名（first_name + last_name），而不是用户名（username）
    """
    # 优先使用完整的个人资料姓名
    if user.first_name:
        # 如果有 last_name，合并显示
        if user.last_name:
            username = f"{user.first_name} {user.last_name}"
        else:
            username = user.first_name
    else:
        username = user.username or f"用户{user.id}"
    
    # 检查是否包含"组"字
    if "组" not in username:
        # 添加默认组名
        username = f"{username}组"
    
    return username


def _format_duplicate_display(duplicate_summary):
    """按照要求格式显示重复数据"""
    if not duplicate_summary or duplicate_summary.get('total_count', 0) == 0:
        return "无"
    
    recent_records = duplicate_summary.get('total_records', [])
    if not recent_records:
        return "无"
    
    display_text = ""
    for i, record in enumerate(recent_records, 1):
        time_str = record.get('full_time', '未知时间')
        record_username = record.get('username', '未知用户')
        quantity = record.get('quantity', 0)  # 注意：这里使用quantity字段
        group_name = record.get('group', '未知群组')
        
        # 格式化时间显示
        if ' ' in time_str:
            date_part, time_part = time_str.split(' ', 1)
            formatted_time = f"{date_part} {time_part}"
        else:
            formatted_time = time_str
        
        display_text += f"{i}. [{formatted_time}] {group_name} | {record_username} | 数量：{quantity}\n"
    
    return display_text.strip()


async def _forward_to_group_with_reminder(
    context: ContextTypes.DEFAULT_TYPE,
    group_id: int,
    text: str,
    original_data: str,
    sender_info: str
) -> Message:
    """
    转发消息到群组并设置超时检查
    """
    try:
        # 发送消息到群组
        sent_message: Message = await forward_to_group(
            context=context,
            tg_group_id=group_id,
            text=text
        )
        
        # 记录待检查消息并安排超时检查
        reminder_manager['add_pending_message'](
            group_id=group_id,
            message_id=sent_message.message_id,
            original_data=original_data,
            sender_info=sender_info
        )
        
        # 安排3分钟后的检查
        await reminder_manager['schedule_check'](
            bot=context.bot,
            group_id=group_id,
            message_id=sent_message.message_id,
            delay_seconds=reminder_manager['TIMEOUT_SECONDS']
        )
        
        logger.info(f"✅ 消息已转发并设置超时检查: group={group_id}, message={sent_message.message_id}")
        
        return sent_message
        
    except Exception as e:
        logger.error(f"❌ 转发消息失败: {e}")
        raise


# ==================================================
# 私聊提交 & 确认 主入口
# ==================================================
@team_only
async def handle_submit_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    私聊消息处理：
    - 两行 → 新提交
    - 单独回复 1 → 群组二重复确认发送
    """
    message = update.message
    user = update.effective_user

    if not message or not message.text:
        return

    text = message.text.strip()

    # ==================================================
    # 一、处理「回复 1」确认发送（群组二）
    # ==================================================
    if text == "1":
        confirm = context.user_data.pop("confirm_submit", None)
        if not confirm:
            await message.reply_text("❌ 没有需要确认的提交")
            return

        data = confirm["data"]
        number = confirm["number"]
        group_id = confirm["group_id"]
        duplicate_info = confirm.get("duplicate_info", {})

        # 确保用户名包含"组"
        username = _ensure_username(user)
        
        # 写入提交数据库
        insert_submission(
            data=data,
            number=number,
            user_id=user.id,
            username=username,
            tg_group_id=group_id,
        )

        # 构建转发消息 - 使用确保包含"组"的用户名
        # 📌 修改：群组2的转发消息与群组1保持一致，只包含三行信息
        forward_text = f"{username}\n{data}\n{number}"
        
        # 📌 修改：删除群组2转发消息中的历史记录提醒
        # 即使有重复记录，转发到群组2的消息也不显示历史记录
        # 保持与群组1一致的格式
        
        try:
            # 转发到群组并设置超时检查
            sent_message = await _forward_to_group_with_reminder(
                context=context,
                group_id=group_id,
                text=forward_text,
                original_data=data,
                sender_info=username
            )
            
            # 保存记录到群组数据库用于123定位
            try:
                save_to_group_records(
                    data=data,
                    number=number,
                    user_id=user.id,
                    username=username,
                    tg_group_id=group_id,
                    message_id=sent_message.message_id
                )
                logger.info(f"✅ 记录保存成功: data={data}, username={username}, message_id={sent_message.message_id}")
            except Exception as save_error:
                logger.error(f"⚠️ 保存记录失败（但转发成功）: {save_error}")
            
            await message.reply_text("✅ 已确认并发送至 群组二")
            
        except Exception as e:
            logger.error(f"❌ 转发消息失败: {e}")
            await message.reply_text("❌ 发送到群组失败")

        return

    # ==================================================
    # 二、普通两行提交
    # ==================================================
    lines = text.splitlines()
    if len(lines) != 2:
        await message.reply_text("❌ 提交格式错误，请使用两行格式")
        return

    data_line = lines[0].strip()
    number_line = lines[1].strip()

    # 第一行校验
    if not _valid_data(data_line):
        await message.reply_text("❌ 第一行数据格式不合法")
        return

    # 第二行校验
    if not number_line.isdigit():
        await message.reply_text("❌ 第二行必须是数字")
        return

    number_value = int(number_line)

    # 5 分钟内重复提交（同用户同数据）
    if is_duplicate_recent(
        data=data_line,
        user_id=user.id,
        window_seconds=settings.DUPLICATE_WINDOW_SECONDS
    ):
        await message.reply_text("⏳ 该数据 5 分钟内已提交，请稍后再试")
        return

    # ==================================================
    # 三、根据数量决定处理逻辑
    # ==================================================
    
    if number_value < 14:
        # ==================================================
        # 群组一（第二行<14）的处理
        # ==================================================
        target_group_id = settings.GROUP_ONE_ID
        target_group_name = "群组一"
        
        # 检查是否重复数据（群组一内）
        if is_duplicate_data(data_line, target_group_id):
            await message.reply_text("🔁 群组一已存在该数据，提交已取消")
            return
        
        # 确保用户名包含"组"
        username = _ensure_username(user)
        
        # 写入提交数据库
        insert_submission(
            data=data_line,
            number=number_value,
            user_id=user.id,
            username=username,
            tg_group_id=target_group_id
        )

        # 构建转发消息
        forward_text = f"{username}\n{data_line}\n{number_value}"
        
        try:
            # 转发群组并设置超时检查
            sent_message = await _forward_to_group_with_reminder(
                context=context,
                group_id=target_group_id,
                text=forward_text,
                original_data=data_line,
                sender_info=username
            )
            
            # 保存记录到群组数据库用于123定位
            try:
                save_to_group_records(
                    data=data_line,
                    number=number_value,
                    user_id=user.id,
                    username=username,
                    tg_group_id=target_group_id,
                    message_id=sent_message.message_id
                )
                logger.info(f"✅ 记录保存成功: data={data_line}, username={username}, message_id={sent_message.message_id}")
            except Exception as save_error:
                logger.error(f"⚠️ 保存记录失败（但转发成功）: {save_error}")
            
            await message.reply_text(f"✅ 提交成功，已发送至 {target_group_name}")
            
        except Exception as e:
            logger.error(f"❌ 转发消息失败: {e}")
            await message.reply_text(f"❌ 发送到{target_group_name}失败")
        
        return  # 群组一处理结束

    else:
        # ==================================================
        # 群组二（第二行>=14）的处理：全部需要确认
        # ==================================================
        target_group_id = settings.GROUP_TWO_ID
        target_group_name = "群组二"
        
        # 检查两个群组的所有历史记录
        duplicate_summary = get_duplicate_summary_old_format(data_line)
        has_duplicates = duplicate_summary.get('total_count', 0) > 0
        
        # 确保用户名包含"组"
        username = _ensure_username(user)
        
        # 构建确认消息 - 按照要求的格式
        # 📌 注意：私信确认时仍然显示重复记录提醒
        confirm_msg = f"📊 数据: {data_line}\n"
        confirm_msg += f"🔢 数量: {number_value}\n"
        confirm_msg += f"👤 提交人: {username}\n\n"
        
        confirm_msg += f"📝 重复数据:\n"
        confirm_msg += _format_duplicate_display(duplicate_summary)
        
        confirm_msg += f"\n\n📤 如需继续发送，请回复：1"
        
        await message.reply_text(confirm_msg)
        context.user_data["confirm_submit"] = {
            "data": data_line,
            "number": number_value,
            "group_id": target_group_id,
            "duplicate_info": duplicate_summary,  # 仍然保留用于后续处理
        }
        return