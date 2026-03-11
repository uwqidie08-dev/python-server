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
from features.admin.report import report_today
from features.admin.clear_today import (
    clear_today,
    confirm_clear_today,
)
from features.admin.stats import handle_stats

# =========================
# 管理员：权限管理
# =========================
from features.admin.whitelist import (
    wl_add,
    wl_remove,
    wl_list,
    debug_db,
)

from features.admin.score_whitelist import (
    score_add,
    score_remove,
    score_list,
)

from features.admin.admin_manage import (
    admin_add,
    admin_remove,
    admin_list,
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
# 帮助命令（不影响原有业务逻辑）
# ==================================================
async def show_help(update, context):
    """
    /start 和 /help 使用说明
    """
    if not update.message:
        return

    await update.message.reply_text(
        """
🤖 使用说明：

📱 团队数据提交（普通白名单）：
格式：
第一行：数据（支持：11位数字/13位数字/邮箱/UUID）
第二行：数字

数据格式示例：
• 手机号：13800138000
• 13位数字：8613800138000
• 邮箱：test@example.com
• UUID：c398b651-e7fe-430b-b1f3-d046b06a22e3

规则：
- 第二行 < 14 → 群组一（重复则取消）
- 第二行 ≥ 14 → 群组二（显示重复记录）
- 5分钟内相同数据只能提交一次

🔍 数据查询（普通白名单）：
- 发送 8-13 位数字进行查询
- 查询结果：
  1 - 首次查询（显示上传时间）
  2 - 数字不存在
  3 - 已被查询过（显示上次查询时间）

🔄 回复123：（普通白名单）
格式：123 数据
示例：123 13800138000
      123 test@example.com
      123 c398b651-e7fe-430b-b1f3-d046b06a22e3

📤 TXT文件上传（评分白名单专用）：
- 直接发送TXT文件给机器人
- 自动提取13位数字并上传到查询数据库
- 只有评分白名单和管理员可以使用此功能

📊 管理员命令：
/report - 今日统计
/clear_today - 清空分数

👥 普通白名单管理：
/wl_add
/wl_remove
/wl_list

🔐 评分白名单管理：
/score_add
/score_remove
/score_list

👑 管理员管理：
/admin_add
/admin_remove
/admin_list
""",
        parse_mode=None
    )


# ==================================================
# 私聊消息分流
# ==================================================
async def private_message_router(update, context):
    """
    私聊消息智能分流（不处理命令和单独的"1"）：
    - 两行 → 提交
    - 单行 8-13 位数字 → 查询
    - 以"123 "开头 → 123定位
    """

    message = update.message
    if not message or not message.text:
        return

    text = message.text.strip()
    if not text:
        return

    if context.user_data.get('awaiting_cache_clear', False):
        from features.admin.timeout import confirm_clear_timeout_cache
        await confirm_clear_timeout_cache(update, context)
        return

    lines = [l.strip() for l in text.splitlines() if l.strip()]

    if len(lines) == 2:
        await handle_submit_message(update, context)
        return

    if len(lines) == 1 and lines[0].isdigit() and 8 <= len(lines[0]) <= 13:
        await handle_query_message(update, context)
        return

    await message.reply_text(
        "❌ 无法识别的指令或格式\n\n"
        "📌 支持格式：\n"
        "• 单行 8-13 位数字 → 查询\n"
        "• 两行内容 → 数据提交\n"
        "• 123 <数据> → 定位历史记录\n"
        "• 1 → 确认重复提交\n\n"
        "💡 发送 /help 查看完整说明"
    )


# ==================================================
# 路由注册入口
# ==================================================
def register_routes(app: Application):

    # 帮助命令
    app.add_handler(CommandHandler("start", show_help))
    app.add_handler(CommandHandler("help", show_help))

    # 管理员命令
    app.add_handler(CommandHandler("report", report_today))
    app.add_handler(CommandHandler("clear_today", clear_today))
    app.add_handler(CommandHandler("confirm_clear_today", confirm_clear_today))

    # 数据库重置
    app.add_handler(CommandHandler("reset_score_db", reset_score_db))
    app.add_handler(CommandHandler("confirm_reset_score_db", confirm_reset_score_db))

    # 说明
    app.add_handler(CommandHandler("stats", handle_stats))

    # 调试
    app.add_handler(CommandHandler("debug_db", debug_db))

    # 白名单管理
    app.add_handler(CommandHandler("wl_add", wl_add))
    app.add_handler(CommandHandler("wl_remove", wl_remove))
    app.add_handler(CommandHandler("wl_list", wl_list))

    app.add_handler(CommandHandler("score_add", score_add))
    app.add_handler(CommandHandler("score_remove", score_remove))
    app.add_handler(CommandHandler("score_list", score_list))

    # 管理员管理
    app.add_handler(CommandHandler("admin_add", admin_add))
    app.add_handler(CommandHandler("admin_remove", admin_remove))
    app.add_handler(CommandHandler("admin_list", admin_list))

    # 超时管理
    app.add_handler(CommandHandler("timeout_status", check_timeout_status))
    app.add_handler(CommandHandler("force_check_timeout", force_check_timeout))
    app.add_handler(CommandHandler("clear_timeout_cache", clear_timeout_cache))
    app.add_handler(CommandHandler("list_pending", list_pending_messages))

    # TXT上传
    app.add_handler(
        MessageHandler(
            filters.Document.ALL,
            handle_txt_upload_simple
        )
    )

    # 群组评分
    app.add_handler(
        MessageHandler(
            filters.ChatType.GROUPS
            & filters.REPLY
            & (filters.TEXT | filters.PHOTO),
            handle_score_reply
        )
    )

    # 123定位
    app.add_handler(
        MessageHandler(
            filters.TEXT & filters.Regex(r'^123\s+.+'),
            handle_reply123
        )
    )

    # 单独1确认
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & filters.Regex(r'^1$'),
            handle_submit_message
        )
    )

    # 私聊分流
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE
            & filters.TEXT
            & ~filters.COMMAND
            & ~filters.Regex(r'^1$'),
            private_message_router
        )
    )