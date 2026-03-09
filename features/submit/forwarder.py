# features/submit/forwarder.py
from telegram import Update

from config.settings import settings


async def forward_to_group(
    update: Update,
    data: str,
    number: int,
) -> None:
    """
    根据 number 大小转发到对应群组
    """
    bot = update.get_bot()

    text = f"📤 新提交数据：\n\n{data}\n{number}"

    if number < 14:
        chat_id = settings.GROUP_ONE_ID
    else:
        chat_id = settings.GROUP_TWO_ID

    await bot.send_message(chat_id=chat_id, text=text)
