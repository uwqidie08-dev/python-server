# features/admin/clear_today.py
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.score_db import (
    clear_today_summary,
    clear_today_completely,  # 新增
    get_today_total
)
from utils.group import get_group_name

logger = logging.getLogger(__name__)

# 内存级二次确认缓存
_PENDING_CLEAR = set()


async def clear_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    第一次确认：
    /clear_today
    """
    user = update.effective_user
    chat = update.effective_chat

    # ===== 权限校验 =====
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以执行该操作")
        return

    # ===== 只允许群组 =====
    if chat.type not in ("group", "supergroup"):
        await update.message.reply_text("❌ 请在群组中使用该命令")
        return

    tg_group_id = chat.id
    group_name = get_group_name(tg_group_id)
    total = get_today_total(tg_group_id)

    if total == 0:
        await update.message.reply_text("📭 今日暂无可清空的统计数据")
        return

    key = (tg_group_id, user.id)
    _PENDING_CLEAR.add(key)

    await update.message.reply_text(
        f"⚠️ 确认清空今日统计？\n\n"
        f"📍 群组：{group_name}\n"
        f"🏁 当前总分：{total}\n\n"
        f"此操作将：\n"
        f"1. 删除今日所有评分记录\n"
        f"2. 清空今日统计缓存\n"
        f"3. 删除强制统计备份\n\n"
        f"请在 2 分钟内发送：\n"
        f"/confirm_clear_today\n\n"
        f"❗ 此操作不可撤销"
    )


async def confirm_clear_today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    第二次确认：
    /confirm_clear_today
    """
    user = update.effective_user
    chat = update.effective_chat

    if user.id not in settings.ADMINS:
        return

    if chat.type not in ("group", "supergroup"):
        return

    tg_group_id = chat.id
    key = (tg_group_id, user.id)

    if key not in _PENDING_CLEAR:
        await update.message.reply_text(
            "❌ 未找到待确认的清空请求\n"
            "请先发送 /clear_today"
        )
        return

    # 执行彻底清空
    try:
        result = clear_today_completely(tg_group_id)
        _PENDING_CLEAR.discard(key)

        group_name = get_group_name(tg_group_id)

        # 构建回复消息
        reply_lines = []
        reply_lines.append(f"✅ 今日数据已彻底清空")
        reply_lines.append("")
        reply_lines.append(f"📍 群组：{group_name}")
        reply_lines.append(f"🗑 删除评分记录：{result.get('ledger_deleted', 0)} 条")
        reply_lines.append(f"🗑 删除缓存记录：{result.get('summary_deleted', 0)} 条")
        reply_lines.append(f"🗑 删除备份文件：{result.get('backup_deleted', 0)} 个")
        reply_lines.append("")
        reply_lines.append("💡 说明：")
        reply_lines.append("• 所有今日评分记录已被删除")
        reply_lines.append("• 统计缓存已被清空")
        reply_lines.append("• 强制统计备份已被删除")
        reply_lines.append("• /report 命令将显示空统计")

        await update.message.reply_text("\n".join(reply_lines))
        
    except Exception as e:
        logger.error(f"清空今日数据失败: {e}")
        await update.message.reply_text(
            f"❌ 清空今日数据失败：{str(e)[:100]}"
        )