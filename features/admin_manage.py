from telegram import Update
from telegram.ext import ContextTypes, CommandHandler

from config.settings import settings


# =========================
# 权限检查
# =========================
def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMINS


# =========================
# /admin_add
# =========================
async def admin_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # ✅ 调试日志（关键）
    print("===== ADMIN DEBUG =====")
    print("user_id =", user_id)
    print("ADMINS =", settings.ADMINS)
    print("=======================")

    if not is_admin(user_id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法：/admin_add 用户ID")
        return

    try:
        new_admin = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 用户ID必须是数字")
        return

    if new_admin in settings.ADMINS:
        await update.message.reply_text("⚠️ 该用户已经是管理员")
        return

    settings.ADMINS.append(new_admin)

    await update.message.reply_text(f"✅ 已添加管理员：{new_admin}")


# =========================
# /admin_remove
# =========================
async def admin_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # ✅ 调试日志
    print("===== ADMIN DEBUG =====")
    print("user_id =", user_id)
    print("ADMINS =", settings.ADMINS)
    print("=======================")

    if not is_admin(user_id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return

    if not context.args:
        await update.message.reply_text("❌ 用法：/admin_remove 用户ID")
        return

    try:
        remove_admin = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ 用户ID必须是数字")
        return

    if remove_admin not in settings.ADMINS:
        await update.message.reply_text("⚠️ 该用户不是管理员")
        return

    settings.ADMINS.remove(remove_admin)

    await update.message.reply_text(f"✅ 已移除管理员：{remove_admin}")


# =========================
# /admin_list
# =========================
async def admin_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    # ✅ 调试日志
    print("===== ADMIN DEBUG =====")
    print("user_id =", user_id)
    print("ADMINS =", settings.ADMINS)
    print("=======================")

    if not is_admin(user_id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return

    admin_list_str = "\n".join(str(a) for a in settings.ADMINS)

    await update.message.reply_text(f"👑 当前管理员列表：\n{admin_list_str}")