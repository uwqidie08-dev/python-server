# utils\group.py
from config.settings import settings  # 确保导入 settings


def get_group_name(chat_id: int) -> str:
    """
    根据 Telegram 群 ID 返回人类可读的群组名
    """
    if chat_id == settings.GROUP_ONE_ID:
        return "群组一"
    elif chat_id == settings.GROUP_TWO_ID:
        return "群组二"
    else:
        return f"未知群组 ({chat_id})"


def is_valid_group(chat_id: int) -> bool:
    """
    是否是机器人允许工作的群组
    """
    return chat_id in (settings.GROUP_ONE_ID, settings.GROUP_TWO_ID)