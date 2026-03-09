# features/admin/repair.py (新文件)
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.submit_db import retry_pending_records, get_pending_records_count
from db.score_db import fix_incomplete_scores
from utils.group import get_group_name

logger = logging.getLogger(__name__)


async def repair_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /repair - 修复数据不一致问题
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以执行修复操作")
        return

    await update.message.reply_text("🛠️ 开始修复数据...")
    
    results = []
    
    # 1. 重试待处理的提交记录
    pending_count = get_pending_records_count()
    if pending_count > 0:
        retry_results = retry_pending_records()
        results.append(f"📝 提交记录修复: 总数 {pending_count}, 成功 {retry_results['success']}, 失败 {retry_results['failed']}")
    
    # 2. 修复不完整的评分统计
    fix_results = fix_incomplete_scores()
    results.append(f"📊 评分统计修复: 修复了 {fix_results.get('fixed_count', 0)} 条记录")
    
    # 3. 汇总结果
    if results:
        summary = "✅ 数据修复完成:\n\n" + "\n".join(results)
    else:
        summary = "✅ 未发现需要修复的数据"
    
    await update.message.reply_text(summary)


async def check_data_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /check - 检查数据状态
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以检查数据状态")
        return
    
    from db.submit_db import get_pending_records_count
    from db.phone_db import phone_db
    
    status_messages = []
    
    # 1. 待处理记录
    pending_count = get_pending_records_count()
    status_messages.append(f"📝 待处理记录: {pending_count} 条")
    
    # 2. 数据库状态
    try:
        phone_info = phone_db.get_table_info()
        status_messages.append(f"📊 查询数据库: {phone_info.get('total_records', 0)} 条记录")
    except:
        status_messages.append("📊 查询数据库: 状态未知")
    
    # 3. 群组记录状态
    try:
        from db.group_db import group_one_db, group_two_db
        import sqlite3
        
        for db_name, db_instance in [("群组一", group_one_db), ("群组二", group_two_db)]:
            try:
                # 检查连接是否正常
                with sqlite3.connect(db_instance.db_path) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT COUNT(*) FROM records")
                    count = cur.fetchone()[0]
                    status_messages.append(f"🏢 {db_name}记录: {count} 条")
            except:
                status_messages.append(f"🏢 {db_name}记录: 连接失败")
    except:
        status_messages.append("🏢 群组记录: 检查失败")
    
    status_text = "📋 数据状态检查:\n\n" + "\n".join(status_messages)
    await update.message.reply_text(status_text)