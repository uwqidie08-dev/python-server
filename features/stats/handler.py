# features/stats/handler.py
from telegram import Update
from telegram.ext import ContextTypes

from auth.scorer import scorer_only
from features.stats.db import get_today, clear_today
from features.stats.state import (
    set_pending,
    is_pending,
    clear_pending,
)


@scorer_only
async def handle_report(update: Update, context: ContextTypes.DEFAULT_TYPE):
    stats = get_today()

    if not stats:
        await update.message.reply_text("📊 今日暂无数据")
        return

    text = ["📊 今日统计："]
    for group, count in stats.items():
        text.append(f"• {group}：{count}")

    await update.message.reply_text("\n".join(text))


@scorer_only
async def handle_clear_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if not is_pending(user_id):
        set_pending(user_id)
        await update.message.reply_text(
            "⚠️ 确认清空今日统计？\n\n"
            "请再次发送 /clear_today 进行确认"
        )
        return

    clear_today()
    clear_pending(user_id)
    await update.message.reply_text("🗑 今日统计已清空")
