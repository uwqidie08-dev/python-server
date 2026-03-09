# features/query/handler.py

import logging
from telegram import Update
from telegram.ext import ContextTypes

from auth.query import query_only
from db.phone_db import phone_db

logger = logging.getLogger(__name__)


@query_only
async def handle_query_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    私聊数字查询
    支持8-13位数字查询，支持后8位以上模糊匹配
    """
    message = update.message
    if not message or not message.text:
        return

    query_str = message.text.strip()

    # 基础校验
    if not query_str.isdigit():
        await message.reply_text("❌ 查询格式错误，请输入数字")
        return
    
    if len(query_str) < 8:
        await message.reply_text("❌ 查询格式错误，请输入至少8位数字")
        return
    
    if len(query_str) > 13:
        await message.reply_text("❌ 查询格式错误，最多13位数字")
        return

    try:
        # 执行查询
        result_code, data = phone_db.query_number(query_str)

        # =============================
        # 1️⃣ 首次查询
        # =============================
        if result_code == 1:
            if data and 'query_match' in data and data['query_match'] != data['full_number']:
                # 模糊匹配成功
                reply_text = f"1  ✅ 查询成功：首次查询\n"
                reply_text += f"🔍 查询匹配：{data['query_match']}\n"
                reply_text += f"📋 完整号码：{data['full_number']}\n"
                reply_text += f"📤 数据上传时间：{data['upload_time']}"
            else:
                # 精确匹配成功
                reply_text = f"1  ✅ 查询成功：首次查询\n"
                reply_text += f"📤 数据上传时间：{data['upload_time']}"
            
            await message.reply_text(reply_text)
            return

        # =============================
        # 2️⃣ 不存在
        # =============================
        if result_code == 2:
            await message.reply_text("2  ❌ 查询结果：该数字不存在于数据库中")
            return

        # =============================
        # 3️⃣ 已被查询过
        # =============================
        if result_code == 3:
            if data and 'query_match' in data and data['query_match'] != data['full_number']:
                # 模糊匹配成功
                reply_text = f"3  📌 此数字已被查询过\n"
                reply_text += f"🔍 查询匹配：{data['query_match']}\n"
                reply_text += f"📋 完整号码：{data['full_number']}\n"
                reply_text += f"⏰ 上次查询时间：{data['last_query_time']}\n"
                reply_text += f"📤 上传时间：{data['upload_time']}"
            else:
                # 精确匹配成功
                reply_text = f"3  📌 此数字已被查询过\n"
                reply_text += f"⏰ 上次查询时间：{data['last_query_time']}\n"
                reply_text += f"📤 上传时间：{data['upload_time']}"
            
            await message.reply_text(reply_text)
            return

    except Exception as e:
        logger.error(f"查询失败: {e}", exc_info=True)
        await message.reply_text("❌ 查询过程中发生错误，请稍后再试")