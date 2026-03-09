# features/submit/duplicate.py
from datetime import datetime, timedelta

from config.settings import settings


# 🚧 临时内存重复缓存
# data -> last_submit_time
_DUPLICATE_CACHE: dict[str, datetime] = {}


def is_duplicate(data: str) -> bool:
    """
    判断是否 5 分钟内重复提交
    """
    now = datetime.utcnow()

    last_time = _DUPLICATE_CACHE.get(data)
    if last_time and now - last_time < timedelta(seconds=settings.DUPLICATE_WINDOW_SECONDS):
        return True

    # 记录最新提交时间
    _DUPLICATE_CACHE[data] = now
    return False
