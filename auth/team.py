# auth/team.py
from telegram import Update
from telegram.ext import ContextTypes

from auth.admin import is_admin
from db.whitelist_db import has_role


def team_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id

        if is_admin(user_id):
            return await func(update, context)

        if not has_role(user_id, "team"):
            await update.message.reply_text("❌ 你不在团队白名单中")
            return

        return await func(update, context)

    return wrapper