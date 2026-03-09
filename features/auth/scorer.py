# auth/scorer.py
from telegram import Update
from telegram.ext import ContextTypes

from auth.admin import is_admin
from config.settings import settings


def scorer_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if is_admin(user_id):
            return await func(update, context)

        if user_id not in settings.SCORER_WHITELIST:
            await update.message.reply_text("❌ 你没有统计权限")
            return

        return await func(update, context)

    return wrapper
