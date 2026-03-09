# features/upload/handler.py
import logging
from datetime import datetime
from telegram import Update, Document
from telegram.ext import ContextTypes

from auth.scorer import scorer_only
from db.phone_db import phone_db

logger = logging.getLogger(__name__)


def scorer_or_admin_only(func):
    """
    组合装饰器：允许评分白名单或管理员
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        if not user:
            return
        
        # 检查是否为管理员
        from config.settings import settings
        if user.id in settings.ADMINS:
            return await func(update, context)
        
        # 检查是否为评分白名单
        from db.whitelist_db import has_role
        if has_role(user.id, "scorer"):
            return await func(update, context)
        
        await update.message.reply_text("❌ 你没有上传权限")
        return
    
    return wrapper


@scorer_or_admin_only
async def handle_txt_upload_simple(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    TXT 文件上传处理：
    - 评分白名单 / 管理员
    - 私聊发送 TXT 即可
    """

    message = update.message
    if not message or not message.document:
        return

    document: Document = message.document

    # ========= 文件校验 =========
    if not document.file_name.lower().endswith(".txt"):
        await message.reply_text("❌ 仅支持 TXT 文件上传")
        return

    # ========= 初始反馈 =========
    status_msg = await message.reply_text(
        "📁 文件上传中...\n\n"
        f"📄 文件名：{document.file_name}\n"
        "⏳ 状态：正在下载并处理文件...\n"
        "⌛️ 请稍候..."
    )

    try:
        # ========= 下载文件 =========
        tg_file = await document.get_file()
        file_bytes = await tg_file.download_as_bytearray()

        text = file_bytes.decode("utf-8", errors="ignore")
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        total_lines = len(lines)

        # ========= 数据写入（自动清理7天前数据） =========
        result = phone_db.insert_numbers(lines, clean_days=7)

        # ========= 统计 =========
        success = result.get("inserted", 0)
        duplicate = result.get("duplicate", 0)
        invalid = result.get("invalid", 0)
        cleaned = result.get("cleaned", 0)
        total_db = result.get("total", 0)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # ========= 构建格式化回复 =========
        reply_lines = []
        reply_lines.append("✅ 文件处理完成！")
        reply_lines.append("")
        reply_lines.append("📊 处理统计：")
        reply_lines.append(f"├─ 📄总行数：{total_lines} 行")
        reply_lines.append(f"├─ ✅成功添加：{success}条")
        reply_lines.append(f"├─ 🔄重复跳过：{duplicate}条")
        reply_lines.append(f"├─ ❌无效格式：{invalid}条")
        reply_lines.append(f"├─ 🗑清理旧数据：{cleaned}条")
        reply_lines.append(f"└─ 💾数据库现有：{total_db}条")
        reply_lines.append("")
        reply_lines.append(f"⏰本次上传时间：{now}")

        reply_text = "\n".join(reply_lines)

        # ========= 成功反馈 =========
        await status_msg.edit_text(reply_text)

        logger.info(
            f"TXT 上传完成 file={document.file_name} "
            f"total={total_lines} success={success} duplicate={duplicate} "
            f"invalid={invalid} cleaned={cleaned} total_db={total_db}"
        )

    except Exception as e:
        logger.exception("TXT 上传处理失败")
        await status_msg.edit_text(
            "❌ 文件处理失败\n\n"
            f"错误信息：{str(e)}"
        )