# features/admin/timeout.py
import logging
from datetime import datetime
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from utils.reminder import reminder_manager

logger = logging.getLogger(__name__)


async def check_timeout_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    检查超时状态
    /timeout_status
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以查看超时状态")
        return
    
    pending_count = reminder_manager['get_pending_count']()
    
    status_text = f"⏰ 超时提醒系统状态\n\n"
    status_text += f"📊 待处理消息: {pending_count} 条\n"
    status_text += f"⏱️  超时时间: {reminder_manager['TIMEOUT_SECONDS'] // 60} 分钟\n"
    status_text += f"📅 当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
    
    if pending_count > 0:
        status_text += "⚠️ 有消息等待处理，请及时处理。\n\n"
        status_text += "可用命令：\n"
        status_text += "/force_check_timeout - 强制检查所有待处理消息\n"
        status_text += "/clear_timeout_cache - 清理超时缓存"
    else:
        status_text += "✅ 所有消息均已处理。\n\n"
        status_text += "可用命令：\n"
        status_text += "/force_check_timeout - 测试超时检查功能\n"
        status_text += "/clear_timeout_cache - 清理超时缓存"
    
    await update.message.reply_text(status_text)


async def force_check_timeout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    强制检查所有待处理消息
    /force_check_timeout
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以强制检查超时")
        return
    
    await update.message.reply_text("⏰ 正在强制检查所有待处理消息...")
    
    try:
        await reminder_manager['check_all_pending'](context.bot)
        
        # 检查结果
        pending_count = reminder_manager['get_pending_count']()
        
        if pending_count > 0:
            await update.message.reply_text(
                f"⚠️ 强制检查完成，仍有 {pending_count} 条消息待处理\n"
                f"请使用 /timeout_status 查看详情"
            )
        else:
            await update.message.reply_text("✅ 强制检查完成，所有消息均已处理")
            
    except Exception as e:
        logger.error(f"强制检查失败: {e}")
        await update.message.reply_text(f"❌ 强制检查失败: {str(e)[:100]}")


async def clear_timeout_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    清理超时缓存
    /clear_timeout_cache
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以清理缓存")
        return
    
    # 确认操作
    await update.message.reply_text(
        "⚠️ 确认清理超时缓存？\n\n"
        "此操作将清除所有待处理和已处理的记录。\n"
        "如果确实需要清理，请回复：确认清理"
    )
    
    # 设置确认状态
    context.user_data['awaiting_cache_clear'] = True


async def confirm_clear_timeout_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    确认清理超时缓存
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        return
    
    # 检查是否在等待确认状态
    if not context.user_data.get('awaiting_cache_clear', False):
        return
    
    text = update.message.text.strip()
    if text != "确认清理":
        await update.message.reply_text("❌ 清理已取消")
        context.user_data.pop('awaiting_cache_clear', None)
        return
    
    # 执行清理
    try:
        # 清理所有记录
        cleaned = 0
        
        # 清理待处理消息
        pending_count = reminder_manager['get_pending_count']()
        cleaned += pending_count
        
        # 执行清理函数
        cleaned += reminder_manager['cleanup_old_records'](hours=0)  # 清理所有记录
        
        # 清除确认状态
        context.user_data.pop('awaiting_cache_clear', None)
        
        await update.message.reply_text(
            f"✅ 超时缓存已清理\n"
            f"清理记录数: {cleaned}"
        )
        
    except Exception as e:
        logger.error(f"清理超时缓存失败: {e}")
        await update.message.reply_text(f"❌ 清理失败: {str(e)[:100]}")


# 添加一个命令来查看详细的待处理消息
async def list_pending_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    列出所有待处理消息
    /list_pending
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以查看待处理消息")
        return
    
    try:
        # 导入内存中的_pending_messages
        from utils.reminder import _pending_messages
        
        if not _pending_messages:
            await update.message.reply_text("📭 没有待处理消息")
            return
        
        response = "📋 待处理消息列表:\n\n"
        
        now = datetime.now()
        for i, (key, info) in enumerate(_pending_messages.items(), 1):
            group_id, message_id = key
            send_time = info['send_time']
            elapsed = (now - send_time).total_seconds()
            minutes = int(elapsed // 60)
            seconds = int(elapsed % 60)
            
            response += f"{i}. 群组: {group_id}, 消息ID: {message_id}\n"
            response += f"   数据: {info['original_data'][:30]}...\n"
            response += f"   发送者: {info['sender_info']}\n"
            response += f"   已等待: {minutes}分{seconds}秒\n"
            response += f"   发送时间: {send_time.strftime('%H:%M:%S')}\n\n"
        
        # 如果消息太长，分割发送
        if len(response) > 4000:
            chunks = [response[i:i+4000] for i in range(0, len(response), 4000)]
            for i, chunk in enumerate(chunks, 1):
                if i == 1:
                    await update.message.reply_text(chunk)
                else:
                    await update.message.reply_text(f"(续) {chunk}")
        else:
            await update.message.reply_text(response)
            
    except Exception as e:
        logger.error(f"列出待处理消息失败: {e}")
        await update.message.reply_text(f"❌ 列出失败: {str(e)[:100]}")