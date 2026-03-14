ADMIN_IDS = set()


def is_super_admin(user_id: int) -> bool:
    """
    超级管理员判断
    这里先写死，后续你可以改成数据库读取
    """
    SUPER_ADMIN_IDS = {
        123456789,  # 改成你自己的 Telegram 用户ID
    }
    return user_id in SUPER_ADMIN_IDS


async def admin_add(update, context):
    """
    /admin_add <user_id>
    添加管理员
    """
    if not update.message or not update.effective_user:
        return

    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return

    if not context.args:
        await update.message.reply_text("用法：/admin_add <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id 必须是数字")
        return

    if target_id in ADMIN_IDS:
        await update.message.reply_text(f"⚠️ 管理员 {target_id} 已存在")
        return

    ADMIN_IDS.add(target_id)
    await update.message.reply_text(f"✅ 已添加管理员：{target_id}")


async def admin_remove(update, context):
    """
    /admin_remove <user_id>
    删除管理员
    """
    if not update.message or not update.effective_user:
        return

    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return

    if not context.args:
        await update.message.reply_text("用法：/admin_remove <user_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ user_id 必须是数字")
        return

    if target_id not in ADMIN_IDS:
        await update.message.reply_text(f"⚠️ 管理员 {target_id} 不存在")
        return

    ADMIN_IDS.remove(target_id)
    await update.message.reply_text(f"✅ 已移除管理员：{target_id}")


async def admin_list(update, context):
    """
    /admin_list
    查看管理员列表
    """
    if not update.message or not update.effective_user:
        return

    if not is_super_admin(update.effective_user.id):
        await update.message.reply_text("❌ 你没有权限使用此命令")
        return

    if not ADMIN_IDS:
        await update.message.reply_text("📭 当前没有管理员")
        return

    text = "\n".join(str(x) for x in sorted(ADMIN_IDS))
    await update.message.reply_text(f"👑 当前管理员列表：\n{text}")