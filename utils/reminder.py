# utils/reminder.py
"""
超时提醒管理模块
负责记录消息发送时间，检查是否超时，并发送提醒
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Set, Tuple
from telegram import Bot

logger = logging.getLogger(__name__)

# 存储待检查的消息
# 格式: (group_id, message_id) -> (发送时间, 原始数据, 发送者信息)
_pending_messages: Dict[Tuple[int, int], dict] = {}

# 存储已处理的消息（避免重复提醒）
# 格式: (group_id, message_id) -> 处理时间
_processed_messages: Set[Tuple[int, int]] = set()

# 存储检查任务
_check_tasks: Dict[Tuple[int, int], asyncio.Task] = {}

# 超时时间（秒）
TIMEOUT_SECONDS = 180  # 3分钟

# 提醒文本模板
REMINDER_TEXT_TEMPLATE = """⚠️ 此信息已超过{minutes}分钟未处理

📋 原始数据：{data}
👤 提交者：{sender}
⏰ 发送时间：{time}"""

def get_reminder_text(data: str, sender: str, send_time: datetime) -> str:
    """生成提醒文本"""
    time_str = send_time.strftime("%H:%M:%S")
    return REMINDER_TEXT_TEMPLATE.format(
        minutes=TIMEOUT_SECONDS // 60,
        data=data[:100] + "..." if len(data) > 100 else data,
        sender=sender,
        time=time_str
    )

def add_pending_message(
    group_id: int,
    message_id: int,
    original_data: str,
    sender_info: str
) -> None:
    """
    添加待检查的消息
    """
    key = (group_id, message_id)
    
    # 如果已有相同消息的待处理任务，先取消
    if key in _check_tasks:
        try:
            _check_tasks[key].cancel()
        except:
            pass
    
    # 记录消息信息
    _pending_messages[key] = {
        'send_time': datetime.now(),
        'original_data': original_data,
        'sender_info': sender_info,
        'reminded': False  # 是否已发送提醒
    }
    
    logger.info(f"📝 添加待检查消息: group={group_id}, message={message_id}, data={original_data[:20]}...")


def mark_as_processed(group_id: int, message_id: int) -> None:
    """
    标记消息为已处理
    """
    key = (group_id, message_id)
    
    # 从待检查列表中移除
    if key in _pending_messages:
        del _pending_messages[key]
        logger.info(f"✅ 标记消息为已处理: group={group_id}, message={message_id}")
    
    # 添加到已处理集合
    _processed_messages.add(key)
    
    # 取消检查任务
    if key in _check_tasks:
        try:
            _check_tasks[key].cancel()
            del _check_tasks[key]
        except:
            pass


def is_processed(group_id: int, message_id: int) -> bool:
    """
    检查消息是否已处理
    """
    return (group_id, message_id) in _processed_messages


def get_pending_count() -> int:
    """
    获取待处理消息数量
    """
    return len(_pending_messages)


async def schedule_check(
    bot: Bot,
    group_id: int,
    message_id: int,
    delay_seconds: int = TIMEOUT_SECONDS
) -> None:
    """
    安排超时检查任务
    """
    key = (group_id, message_id)
    
    if key not in _pending_messages:
        logger.warning(f"❌ 无法安排检查，消息不存在: {key}")
        return
    
    async def check_and_remind():
        try:
            # 等待指定时间
            await asyncio.sleep(delay_seconds)
            
            # 检查消息是否仍然待处理
            if key in _pending_messages:
                message_info = _pending_messages[key]
                
                # 检查是否已发送提醒
                if not message_info.get('reminded', False):
                    # 生成提醒文本
                    reminder_text = get_reminder_text(
                        message_info['original_data'],
                        message_info['sender_info'],
                        message_info['send_time']
                    )
                    
                    # 发送提醒
                    try:
                        await bot.send_message(
                            chat_id=group_id,
                            text=reminder_text,
                            reply_to_message_id=message_id
                        )
                        
                        # 标记为已提醒
                        message_info['reminded'] = True
                        logger.info(f"⏰ 发送超时提醒: group={group_id}, message={message_id}")
                        
                        # 标记为已处理（避免重复提醒）
                        mark_as_processed(group_id, message_id)
                        
                    except Exception as e:
                        logger.error(f"❌ 发送提醒失败: {e}")
            
            # 清理任务
            if key in _check_tasks:
                del _check_tasks[key]
                
        except asyncio.CancelledError:
            # 任务被取消，正常退出
            logger.info(f"⏹️ 取消检查任务: group={group_id}, message={message_id}")
            if key in _check_tasks:
                del _check_tasks[key]
        except Exception as e:
            logger.error(f"❌ 检查任务异常: {e}")
    
    # 创建并存储任务
    task = asyncio.create_task(check_and_remind())
    _check_tasks[key] = task
    
    logger.info(f"⏰ 安排检查任务: group={group_id}, message={message_id}, 延迟={delay_seconds}秒")


async def check_all_pending(bot: Bot) -> None:
    """
    检查所有待处理消息（用于调试或手动触发）
    """
    now = datetime.now()
    pending_count = len(_pending_messages)
    
    if pending_count == 0:
        logger.info("📭 没有待处理消息")
        return
    
    logger.info(f"📊 当前待处理消息: {pending_count} 条")
    
    for key, info in list(_pending_messages.items()):
        group_id, message_id = key
        send_time = info['send_time']
        elapsed = (now - send_time).total_seconds()
        
        if elapsed >= TIMEOUT_SECONDS and not info.get('reminded', False):
            logger.info(f"⏰ 发现超时消息: group={group_id}, message={message_id}, 已过 {elapsed:.1f} 秒")
            # 生成提醒文本
            reminder_text = get_reminder_text(
                info['original_data'],
                info['sender_info'],
                info['send_time']
            )
            
            # 立即发送提醒
            try:
                await bot.send_message(
                    chat_id=group_id,
                    text=reminder_text,
                    reply_to_message_id=message_id
                )
                info['reminded'] = True
                mark_as_processed(group_id, message_id)
            except Exception as e:
                logger.error(f"❌ 发送立即提醒失败: {e}")


def cleanup_old_records(hours: int = 24) -> int:
    """
    清理旧记录（避免内存泄漏）
    返回清理的记录数
    """
    now = datetime.now()
    cutoff_time = now - timedelta(hours=hours)
    
    cleaned = 0
    
    # 清理待处理消息
    for key in list(_pending_messages.keys()):
        info = _pending_messages[key]
        if info['send_time'] < cutoff_time:
            del _pending_messages[key]
            cleaned += 1
    
    # 清理已处理消息（保持最近24小时）
    # 注意：我们无法知道已处理消息的时间，所以清理所有
    if len(_processed_messages) > 1000:  # 如果太多，清理一半
        items_to_remove = len(_processed_messages) // 2
        for _ in range(items_to_remove):
            if _processed_messages:
                _processed_messages.pop()
        cleaned += items_to_remove
    
    logger.info(f"🧹 清理 {cleaned} 条旧记录")
    return cleaned


# 创建全局实例
reminder_manager = {
    'add_pending_message': add_pending_message,
    'mark_as_processed': mark_as_processed,
    'is_processed': is_processed,
    'get_pending_count': get_pending_count,
    'schedule_check': schedule_check,
    'check_all_pending': check_all_pending,
    'cleanup_old_records': cleanup_old_records,
    'TIMEOUT_SECONDS': TIMEOUT_SECONDS,
    'get_reminder_text': get_reminder_text
}