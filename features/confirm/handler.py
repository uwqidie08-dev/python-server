# features/confirm/handler.py
from telegram import Update
from telegram.ext import ContextTypes

from auth.team import team_only
from features.confirm.state import (
    get_confirm,
    clear_confirm,
    is_expired,
)
from features.submit.forwarder import forward_to_group


@team_only
async def handle_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    处理 1 / 2 确认回复
    """
    message = update.message
    if not message or not message.text:
        return

    user_id = message.from_user.id
    text = message.text.strip()

    if text not in {"1", "2"}:
        return

    state = get_confirm(user_id)
    if not state:
        await message.reply_text("⚠️ 当前没有需要确认的提交")
        return

    if is_expired(state):
        clear_confirm(user_id)
        await message.reply_text("⌛ 确认已超时，提交已取消")
        return

    # ---------- 用户取消 ----------
    if text == "2":
        clear_confirm(user_id)
        await message.reply_text("❌ 提交已取消")
        return

    # ---------- 用户确认 ----------
    await forward_to_group(
        update,
        data=state.data,
        number=state.number,
    )

    clear_confirm(user_id)
    await message.reply_text("✅ 已确认并成功发送")
