from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

# =========================
# 私聊：提交 / 查询
# =========================
from features.submit.handler import handle_submit_message
from features.query.handler import handle_query_message

# =========================
# 123 定位功能
# =========================
from features.reply123.handler import handle_reply123

# =========================
# TXT 上传（评分白名单 / 管理员）
# =========================
from features.upload.handler import handle_txt_upload_simple

# =========================
# 群组评分 / 失败 / 回复
# =========================
from features.score.handler import handle_score_reply

# =========================
# 管理员：统计 / 清空 / 说明
# =========================
from features.admin.report import report_today  # 使用新的用户统计报告
from features.admin.clear_today import (
    clear_today,
    confirm_clear_today,
)
from features.admin.stats import handle_stats

# =========================
# 管理员：权限管理
# =========================
from features.admin.whitelist import (
    wl_add,          # 普通白名单（同时添加提交和查询权限）
    wl_remove,       # 同时移除提交和查询权限
    wl_list,         # 查看提交权限用户
    debug_db,        # 数据库调试
)
from features.admin.score_whitelist import (
    score_add,       # 评分权限
    score_remove,
    score_list,
)

# =========================
# 管理员：超时管理
# =========================
from features.admin.timeout import (
    check_timeout_status,
    force_check_timeout,
    clear_timeout_cache,
    confirm_clear_timeout_cache,
    list_pending_messages,
)

# =========================
# 管理员：数据库重置
# =========================
from features.admin.reset_db import (
    reset_score_db,
    confirm_reset_score_db,
)


# ==================================================
# 帮助命令（新增，不影响原有业务逻辑）
# ==================================================
async def show_help(update, context):
    """
    /start 和 /help 使用说明
    """
    if not update.message:
        return

    await update.message.reply_text(
        "📌 支持格式：\n"
        "• 单行 8-13 位数字 → 查询\n"
        "• 两行内容 → 数据提交\n"
        "• 123 <数据> → 定位历史记录\n"
        "• 1 → 确认重复提交（仅当有等待确认时）\n\n"
        "🔧 常用命令：\n"
        "• /help → 查看说明\n"
        "• /start → 查看说明\n"
        "• /stats → 使用说明\n\n"
        "👑 管理员命令：\n"
        "• /report → 用户统计报告\n"
        "• /clear_today → 清空今日数据\n"
        "• /reset_score_db → 重置评分数据库\n"
        "• /wl_list → 查看白名单\n"
        "• /score_list → 查看评分白名单\n"
        "• /timeout_status → 查看超时状态\n"
        "• /list_pending → 查看待确认消息"
    )


# ==================================================
# 私聊消息分流
# ==================================================
async def private_message_router(update, context):
    """
    私聊消息智能分流（不处理命令和单独的"1"）：
    - 两行 → 提交
    - 单行 8-13 位数字 → 查询
    - 以"123 "开头 → 123定位（实际上由专门的handler处理）
    """
    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    if not text:
        return

    # 处理超时缓存清理确认
    if context.user_data.get('awaiting_cache_clear', False):
        from features.admin.timeout import confirm_clear_timeout_cache
        await confirm_clear_timeout_cache(update, context)
        return

    # 去掉空行
    lines = [l.strip() for l in text.splitlines() if l.strip()]

    # 两行：提交
    if len(lines) == 2:
        await handle_submit_message(update, context)
        return

    # 单行数字：查询
    if len(lines) == 1 and lines[0].isdigit() and 8 <= len(lines[0]) <= 13:
        await handle_query_message(update, context)
        return

    # 兜底
    await message.reply_text(
        "❌ 无法识别的指令或格式\n\n"
        "📌 支持格式：\n"
        "• 单行 8-13 位数字 → 查询\n"
        "• 两行内容 → 数据提交\n"
        "• 123 <数据> → 定位历史记录\n"
        "• 1 → 确认重复提交（仅当有等待确认时）\n\n"
        "💡 发送 /help 查看完整说明"
    )


# ==================================================
# 路由注册入口
# ==================================================
def register_routes(app: Application):
    """
    注册所有 handlers（路由核心）
    注意：handler注册顺序很重要！
    """

    # ==================================================
    # 一、命令处理器（CommandHandler）
    # ==================================================

    # 帮助命令（新增）
    app.add_handler(CommandHandler("start", show_help))
    app.add_handler(CommandHandler("help", show_help))

    # 管理员命令
    app.add_handler(CommandHandler("report", report_today))  # 用户统计报告
    app.add_handler(CommandHandler("clear_today", clear_today))
    app.add_handler(CommandHandler("confirm_clear_today", confirm_clear_today))

    # 数据库重置命令
    app.add_handler(CommandHandler("reset_score_db", reset_score_db))
    app.add_handler(CommandHandler("confirm_reset_score_db", confirm_reset_score_db))

    # 使用说明命令（所有白名单用户可用）
    app.add_handler(CommandHandler("stats", handle_stats))

    # 数据库调试命令
    app.add_handler(CommandHandler("debug_db", debug_db))

    # 权限管理命令
    app.add_handler(CommandHandler("wl_add", wl_add))
    app.add_handler(CommandHandler("wl_remove", wl_remove))
    app.add_handler(CommandHandler("wl_list", wl_list))
    app.add_handler(CommandHandler("score_add", score_add))
    app.add_handler(CommandHandler("score_remove", score_remove))
    app.add_handler(CommandHandler("score_list", score_list))

    # 超时管理命令
    app.add_handler(CommandHandler("timeout_status", check_timeout_status))
    app.add_handler(CommandHandler("force_check_timeout", force_check_timeout))
    app.add_handler(CommandHandler("clear_timeout_cache", clear_timeout_cache))
    app.add_handler(CommandHandler("list_pending", list_pending_messages))

    # ==================================================
    # 二、消息处理器（MessageHandler）
    # ==================================================

    # TXT 文件上传
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_txt_upload_simple
        )
    )

    # 群组评分（必须是"回复"）
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & filters.REPLY
            & (filters.TEXT | filters.PHOTO),
            handle_score_reply
        )
    )

    # 123 定位命令（普通白名单权限）
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r'^123\s+.+'),
            handle_reply123
        )
    )

    # 单独的"1"确认命令（必须在private_message_router之前注册）
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & filters.Regex(r'^1$'),  # 仅匹配单独的"1"
            handle_submit_message
        )
    )

    # 私聊消息智能分流（不包括命令和单独的"1"）
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND  # 排除命令
            & ~filters.Regex(r'^1$'),  # 排除单独的"1"
            private_message_router
        )
    )