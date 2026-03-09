# features/stats/state.py
from datetime import datetime, timedelta

_PENDING_CLEAR = {}
TIMEOUT_SECONDS = 60


def set_pending(user_id: int):
    _PENDING_CLEAR[user_id] = datetime.utcnow()


def is_pending(user_id: int) -> bool:
    ts = _PENDING_CLEAR.get(user_id)
    if not ts:
        return False
    return datetime.utcnow() - ts < timedelta(seconds=TIMEOUT_SECONDS)


def clear_pending(user_id: int):
    _PENDING_CLEAR.pop(user_id, None)
