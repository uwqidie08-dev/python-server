# utils/forward.py

import logging
from telegram import Message
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def forward_to_group(
    *,
    context: ContextTypes.DEFAULT_TYPE,
    tg_group_id: int,
    text: str
) -> Message:
    """
    向指定群组发送消息（用于提交数据）
    返回发送的消息对象
    
    消息格式应为：
    用户名
    数据
    数字
    """
    try:
        message = await context.bot.send_message(
            chat_id=tg_group_id,
            text=text
        )
        logger.info(f"消息已发送到群组 {tg_group_id}")
        return message
    except Exception as e:
        logger.error(
            f"发送消息到群组失败 group={tg_group_id}, err={e}",
            exc_info=True
        )
        raise