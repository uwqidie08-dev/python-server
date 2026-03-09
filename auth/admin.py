# auth/admin.py
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings


def is_admin(user_id: int) -> bool:
    """
    判断是否为管理员
    """
    return user_id in settings.ADMINS


def admin_only(func):
    """
    仅管理员可用的装饰器
    """
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return

        if not is_admin(user.id):
            await update.message.reply_text("❌ 该功能仅管理员可用")
            return

        return await func(update, context, *args, **kwargs)

    return wrapper
