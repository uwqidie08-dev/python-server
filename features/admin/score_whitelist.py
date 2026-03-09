# features/admin/score_whitelist.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.whitelist_db import (
    add_user_role,
    remove_user_role,
    get_users_by_role,
)

logger = logging.getLogger(__name__)


def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user or user.id not in settings.ADMINS:
            await update.message.reply_text("❌ 仅管理员可用")
            return
        return await func(update, context)
    return wrapper


def _parse_user_ids(text: str):
    """
    支持：
    - 空格
    - 换行
    - 逗号
    """
    parts = text.replace(",", " ").split()
    return [int(p) for p in parts if p.isdigit()]


@admin_only
async def score_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /score_add 123 456
    """
    args = update.message.text.split()[1:]  # 去掉命令本身
    if not args:
        await update.message.reply_text("❌ 请提供用户ID，例如：/score_add 123 456")
        return
    
    ids = _parse_user_ids(" ".join(args))
    if not ids:
        await update.message.reply_text("❌ 未检测到任何用户 ID")
        return

    success_count = 0
    for user_id in ids:
        try:
            add_user_role(user_id, "scorer")
            success_count += 1
        except Exception as e:
            logger.error(f"添加用户到scorer白名单失败: {user_id}, {e}")
    
    await update.message.reply_text(
        f"✅ 已添加 {success_count}/{len(ids)} 个用户到【评分白名单】(scorer角色)"
    )


@admin_only
async def score_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /score_remove 123
    """
    args = update.message.text.split()[1:]  # 去掉命令本身
    if not args:
        await update.message.reply_text("❌ 请提供用户ID，例如：/score_remove 123")
        return
    
    ids = _parse_user_ids(" ".join(args))
    if not ids:
        await update.message.reply_text("❌ 未检测到任何用户 ID")
        return

    removed_count = 0
    for user_id in ids:
        try:
            affected = remove_user_role(user_id, "scorer")
            removed_count += affected
        except Exception as e:
            logger.error(f"从scorer白名单移除用户失败: {user_id}, {e}")
    
    await update.message.reply_text(
        f"🗑 已从【评分白名单】移除 {removed_count}/{len(ids)} 个用户"
    )


@admin_only
async def score_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /score_list
    """
    users = get_users_by_role("scorer")
    if not users:
        await update.message.reply_text("📭 评分白名单(scorer)为空")
        return
    
    text = "🎯 评分白名单用户(scorer)：\n"
    text += "\n".join(str(u) for u in users)
    await update.message.reply_text(text)