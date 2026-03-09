# features/whitelist/handler.py
from telegram import Update
from telegram.ext import ContextTypes

from auth.admin import admin_only
from db.whitelist_db import add_users, remove_users, list_users


def _parse_ids(text: str) -> list[int]:
    return [int(x) for x in text.split() if x.isdigit()]


@admin_only
async def handle_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /adduser <role> <id1> <id2> ...
    """
    parts = update.message.text.split()
    if len(parts) < 3:
        await update.message.reply_text("用法：/adduser team|query|scorer 用户ID...")
        return

    role = parts[1]
    user_ids = _parse_ids(" ".join(parts[2:]))

    count = add_users(role, user_ids)
    await update.message.reply_text(f"✅ 成功添加 {count} 人到 {role} 白名单")


@admin_only
async def handle_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /removeuser <role> <id1> <id2> ...
    """
    parts = update.message.text.split()
    if len(parts) < 3:
        await update.message.reply_text("用法：/removeuser team|query|scorer 用户ID...")
        return

    role = parts[1]
    user_ids = _parse_ids(" ".join(parts[2:]))

    count = remove_users(role, user_ids)
    await update.message.reply_text(f"🗑 已从 {role} 白名单移除 {count} 人")


@admin_only
async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /listusers <role>
    """
    parts = update.message.text.split()
    if len(parts) != 2:
        await update.message.reply_text("用法：/listusers team|query|scorer")
        return

    role = parts[1]
    users = list_users(role)

    if not users:
        await update.message.reply_text("（空）")
        return

    await update.message.reply_text(
        f"📋 {role} 白名单：\n" + "\n".join(map(str, users))
    )
