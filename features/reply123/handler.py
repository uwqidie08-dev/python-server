# features/reply123/handler.py

import logging
from telegram import Update
from telegram.ext import ContextTypes

from auth.team import team_only
from config.settings import settings
from db.group_db import group_one_db, group_two_db
from db.submit_db import get_submission_history_by_data
from utils.group import get_group_name

logger = logging.getLogger(__name__)


@team_only
async def handle_reply123(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理：123 数据
    格式：123 <data>
    功能：在群组中定位该数据的历史提交记录并回复
    """
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    
    # 解析命令
    if not text.startswith("123 "):
        return
    
    # 提取数据
    data = text[4:].strip()
    if not data:
        await update.message.reply_text("❌ 请提供要定位的数据，格式：123 <数据>")
        return
    
    user = update.effective_user
    
    # 检查是否是私聊
    if message.chat.type == "private":
        await _handle_private_reply123(update, context, data, user)
    else:
        await _handle_group_reply123(update, context, data, user)


async def _handle_private_reply123(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user):
    """
    私聊中处理 123 命令
    """
    # 获取该用户的所有提交历史
    user_records = get_submission_history_by_data(data, user.id)
    
    if not user_records:
        await update.message.reply_text("❌ 未找到您发送的该数据记录")
        return
    
    # 按时间排序，取最新的记录
    user_records.sort(key=lambda x: x.get("time", ""), reverse=True)
    latest_record = user_records[0]
    
    target_group_id = latest_record.get("group_id")
    target_message_id = latest_record.get("group_message_id")
    
    if not target_group_id or not target_message_id:
        await update.message.reply_text("❌ 无法确定目标消息，请联系管理员")
        return
    
    group_name = "群组一" if target_group_id == settings.GROUP_ONE_ID else "群组二"
    
    # 在群组中回复123
    try:
        reply_text = f"🔍 {user.username or user.id} 申请此条数据账单"
        await context.bot.send_message(
            chat_id=target_group_id,
            text=reply_text,
            reply_to_message_id=target_message_id
        )
        
        # 同时发送给用户确认
        user_notification = f"✅ 已成功定位历史记录\n\n"
        user_notification += f"📊 数据：{data}\n"
        user_notification += f"📍 群组：{group_name}\n"
        user_notification += f"📅 提交时间：{latest_record.get('time', '未知时间')}"
        
        await update.message.reply_text(user_notification)
        
    except Exception as e:
        logger.error(f"在群组中回复123失败: {e}")
        await update.message.reply_text(f"❌ 定位失败：{str(e)}")


async def _handle_group_reply123(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str, user):
    """
    群聊中处理 123 命令
    """
    current_group_id = update.effective_chat.id
    
    # 确定使用哪个数据库
    if current_group_id == settings.GROUP_ONE_ID:
        db = group_one_db
    elif current_group_id == settings.GROUP_TWO_ID:
        db = group_two_db
    else:
        # 不在配置的群组中，不处理
        return
    
    result = db.find_latest_by_data(data)
    if not result:
        await update.message.reply_text("❌ 未找到该数据的历史记录")
        return
    
    group_id, message_id = result
    
    try:
        # 回复到找到的消息
        reply_text = f"🔍 {user.username or user.id} 申请此条数据账单"
        await context.bot.send_message(
            chat_id=group_id,
            text=reply_text,
            reply_to_message_id=message_id
        )
        
        await update.message.reply_text("✅ 已成功定位历史记录")
        
    except Exception as e:
        logger.error(f"在群组中回复123失败: {e}")
        await update.message.reply_text(f"❌ 定位失败：{str(e)}")