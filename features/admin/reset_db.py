# features/admin/reset_db.py (新建文件)

import logging
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.score_db import drop_and_recreate_tables
from utils.group import get_group_name

logger = logging.getLogger(__name__)

# 内存级二次确认缓存
_PENDING_RESET = set()


async def reset_score_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    第一次确认：重置整个评分数据库
    /reset_score_db
    """
    user = update.effective_user
    chat = update.effective_chat

    # ===== 权限校验 =====
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以执行该操作")
        return

    # ===== 只允许私聊 =====
    if chat.type != "private":
        await update.message.reply_text("❌ 请在私聊中使用该命令")
        return

    key = user.id
    _PENDING_RESET.add(key)

    await update.message.reply_text(
        f"⚠️ ⚠️ ⚠️  危险操作确认 ⚠️ ⚠️ ⚠️\n\n"
        f"你即将重置整个评分数据库！\n\n"
        f"此操作将：\n"
        f"1. 删除所有评分记录表\n"
        f"2. 重新创建空表结构\n"
        f"3. 所有历史数据将永久丢失\n\n"
        f"❗ 此操作非常危险，请谨慎执行！\n\n"
        f"如果确实需要重置，请在 2 分钟内发送：\n"
        f"/confirm_reset_score_db\n\n"
        f"输入其他内容将取消操作"
    )


async def confirm_reset_score_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    第二次确认：重置整个评分数据库
    /confirm_reset_score_db
    """
    user = update.effective_user
    chat = update.effective_chat

    if user.id not in settings.ADMINS:
        return

    if chat.type != "private":
        return

    key = user.id

    if key not in _PENDING_RESET:
        await update.message.reply_text(
            "❌ 未找到待确认的重置请求\n"
            "请先发送 /reset_score_db"
        )
        return

    # 执行重置
    try:
        result = drop_and_recreate_tables()
        _PENDING_RESET.discard(key)

        if result.get("error"):
            await update.message.reply_text(
                f"❌ 重置数据库失败：{result['error'][:100]}"
            )
            return

        # 构建回复消息
        reply_lines = []
        reply_lines.append("✅ 评分数据库已重置")
        reply_lines.append("")
        
        if result.get("score_ledger_dropped"):
            reply_lines.append("✅ score_ledger 表已删除并重建")
        if result.get("daily_score_summary_dropped"):
            reply_lines.append("✅ daily_score_summary 表已删除并重建")
        if result.get("tables_recreated"):
            reply_lines.append("✅ 所有表结构已重新创建")
        
        reply_lines.append("")
        reply_lines.append("💡 说明：")
        reply_lines.append("• 所有历史评分数据已被删除")
        reply_lines.append("• 表结构已重置为初始状态")
        reply_lines.append("• /report 命令将显示空统计")
        reply_lines.append("• 需要重新开始评分才能生成新数据")

        await update.message.reply_text("\n".join(reply_lines))
        
    except Exception as e:
        logger.error(f"重置数据库失败: {e}")
        await update.message.reply_text(
            f"❌ 重置数据库失败：{str(e)[:100]}"
        )