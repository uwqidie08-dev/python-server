# features/confirm/state.py
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict

from config.settings import settings


@dataclass
class ConfirmState:
    user_id: int
    data: str
    number: int
    created_at: datetime


# user_id -> ConfirmState
_PENDING_CONFIRMS: Dict[int, ConfirmState] = {}


def set_confirm(user_id: int, data: str, number: int) -> None:
    _PENDING_CONFIRMS[user_id] = ConfirmState(
        user_id=user_id,
        data=data,
        number=number,
        created_at=datetime.utcnow(),
    )


def get_confirm(user_id: int) -> ConfirmState | None:
    return _PENDING_CONFIRMS.get(user_id)


def clear_confirm(user_id: int) -> None:
    _PENDING_CONFIRMS.pop(user_id, None)


def is_expired(state: ConfirmState) -> bool:
    return datetime.utcnow() - state.created_at > timedelta(
        seconds=settings.CONFIRM_TIMEOUT_SECONDS
    )
