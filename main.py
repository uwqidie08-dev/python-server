# main.py
import logging
import sys
import json
import os
import asyncio
from pathlib import Path

from telegram.ext import Application

from config.settings import settings

# 数据库初始化
from db.score_db import init_score_tables
from db.whitelist_db import init_whitelist_tables
from db.submit_db import init_submit_tables
from db.phone_db import phone_db  # 确保phone_db初始化

# 路由注册
from core.router import register_routes

# 超时提醒管理
from utils.reminder import reminder_manager

# ==========================================================
# 初始化群组记录表 - 使用更安全的方法处理表结构
# ==========================================================

def init_group_records_tables():
    """初始化群组记录表 - 使用更安全的方法处理表结构"""
    from config.settings import settings
    import sqlite3
    
    for db_path in [settings.GROUP_ONE_DB, settings.GROUP_TWO_DB]:
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                
                # 检查表是否存在
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records'")
                table_exists = cur.fetchone()
                
                if not table_exists:
                    # 如果表不存在，创建新表
                    cur.execute("""
                    CREATE TABLE records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        data TEXT NOT NULL,
                        number INTEGER NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT,
                        group_id INTEGER NOT NULL,
                        message_id INTEGER NOT NULL,
                        created_at TEXT NOT NULL
                    )
                    """)
                    logger.info(f"✅ 创建 records 表: {db_path}")
                else:
                    # 如果表已存在，检查是否需要重建表
                    logger.info(f"🔍 检查 records 表结构: {db_path}")
                    
                    # 获取现有列
                    cur.execute("PRAGMA table_info(records)")
                    existing_columns_info = cur.fetchall()
                    existing_columns = [col[1] for col in existing_columns_info]
                    
                    # 需要确保存在的列
                    required_columns = ['data', 'number', 'user_id', 'username', 'group_id', 'message_id', 'created_at']
                    
                    # 检查是否缺少必要列
                    missing_columns = [col for col in required_columns if col not in existing_columns]
                    
                    if missing_columns:
                        logger.warning(f"⚠️ records 表缺少必要列 {missing_columns}，重建表: {db_path}")
                        
                        # 方法1：尝试通过临时表重建
                        try:
                            # 创建临时表备份（如果表有数据的话）
                            cur.execute("SELECT COUNT(*) FROM records")
                            record_count = cur.fetchone()[0]
                            
                            if record_count > 0:
                                logger.warning(f"⚠️ records 表有 {record_count} 条数据，将丢失: {db_path}")
                            
                            # 删除旧表
                            cur.execute("DROP TABLE IF EXISTS records")
                            
                            # 创建新表
                            cur.execute("""
                            CREATE TABLE records (
                                id INTEGER PRIMARY KEY AUTOINCREMENT,
                                data TEXT NOT NULL,
                                number INTEGER NOT NULL,
                                user_id INTEGER NOT NULL,
                                username TEXT,
                                group_id INTEGER NOT NULL,
                                message_id INTEGER NOT NULL,
                                created_at TEXT NOT NULL
                            )
                            """)
                            
                            logger.info(f"✅ 重建 records 表完成: {db_path}")
                            
                        except Exception as e:
                            logger.error(f"❌ 重建表失败: {db_path}, {e}")
                            
                            # 方法2：尝试逐个添加列（允许NULL）
                            try:
                                for column in missing_columns:
                                    if column == 'data':
                                        cur.execute("ALTER TABLE records ADD COLUMN data TEXT")
                                    elif column == 'number':
                                        cur.execute("ALTER TABLE records ADD COLUMN number INTEGER")
                                    elif column == 'user_id':
                                        cur.execute("ALTER TABLE records ADD COLUMN user_id INTEGER")
                                    elif column == 'username':
                                        cur.execute("ALTER TABLE records ADD COLUMN username TEXT")
                                    elif column == 'group_id':
                                        cur.execute("ALTER TABLE records ADD COLUMN group_id INTEGER")
                                    elif column == 'message_id':
                                        cur.execute("ALTER TABLE records ADD COLUMN message_id INTEGER")
                                    elif column == 'created_at':
                                        cur.execute("ALTER TABLE records ADD COLUMN created_at TEXT")
                                
                                logger.info(f"✅ 添加缺失列完成: {db_path}, 列: {missing_columns}")
                                
                            except Exception as e2:
                                logger.error(f"❌ 添加列也失败: {db_path}, {e2}")
                                # 最后一次尝试：删除表重新创建
                                cur.execute("DROP TABLE IF EXISTS records")
                                cur.execute("""
                                CREATE TABLE records (
                                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                                    data TEXT NOT NULL,
                                    number INTEGER NOT NULL,
                                    user_id INTEGER NOT NULL,
                                    username TEXT,
                                    group_id INTEGER NOT NULL,
                                    message_id INTEGER NOT NULL,
                                    created_at TEXT NOT NULL
                                )
                                """)
                                logger.info(f"✅ 强制重建 records 表完成: {db_path}")
                    
                    else:
                        # 所有必要列都存在，检查表结构是否完整
                        logger.info(f"✅ records 表结构完整: {db_path}")
                        
                        # 检查是否有任何记录，如果有的话验证数据结构
                        try:
                            cur.execute("SELECT data, number, user_id FROM records LIMIT 1")
                            test_result = cur.fetchone()
                            if test_result:
                                logger.info(f"📊 records 表已有 {test_result[0]} 等数据: {db_path}")
                        except:
                            # 如果查询失败，说明表结构可能有问题，但至少有列存在
                            pass
                    
                conn.commit()
                logger.info(f"✅ records 表处理完成: {db_path}")
                
        except Exception as e:
            logger.error(f"❌ 处理 records 表失败 {db_path}: {e}")


# ==========================================================
# 强制统计备份清理
# ==========================================================

def cleanup_old_force_stats():
    """
    清理旧的强制统计备份文件
    只保留今天的备份
    """
    from datetime import datetime, timedelta
    import os
    
    backup_file = "data/force_stats_backup.json"
    if os.path.exists(backup_file):
        try:
            with open(backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # 检查是否为今天的数据
            backup_date_str = data.get("date")
            if backup_date_str:
                backup_date = datetime.strptime(backup_date_str, "%Y-%m-%d").date()
                today = datetime.now().date()
                
                if backup_date < today:
                    # 备份是旧数据，删除
                    os.remove(backup_file)
                    logger.info(f"🗑️  删除旧的强制统计备份: {backup_date_str}")
                else:
                    logger.info(f"📁 保留今天的强制统计备份: {backup_date_str}")
                    
        except Exception as e:
            logger.error(f"❌ 清理强制统计备份失败: {e}")


# ==========================================================
# 定时清理任务
# ==========================================================

async def periodic_cleanup(application: Application):
    """
    定期清理旧记录
    """
    while True:
        try:
            # 每6小时清理一次
            await asyncio.sleep(6 * 60 * 60)
            
            # 清理24小时前的记录
            cleaned = reminder_manager['cleanup_old_records'](hours=24)
            
            if cleaned > 0:
                logger.info(f"🧹 定期清理完成: 清理了 {cleaned} 条旧记录")
                
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ 定期清理失败: {e}")


# ==========================================================
# 日志配置
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


# ==========================================================
# 主入口
# ==========================================================

def main() -> None:
    """
    Bot 启动入口
    1. 初始化数据库
    2. 创建 Telegram Application
    3. 注册所有 handlers
    4. 启动轮询
    """

    logger.info("🚀 Bot 正在启动...")

    # ===============================
    # 1️⃣ 初始化数据库表
    # ===============================
    try:
        logger.info("📊 开始初始化数据库表...")
        
        # 确保数据目录存在
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        logger.info(f"📁 数据目录: {data_dir.absolute()}")
        
        # 清理旧的强制统计备份
        cleanup_old_force_stats()
        
        # 初始化评分数据库
        init_score_tables()
        logger.info("✅ score_db 表初始化完成")
        
        # 初始化白名单数据库
        init_whitelist_tables()
        logger.info("✅ whitelist_db 表初始化完成")
        
        # 初始化提交数据库
        init_submit_tables()
        logger.info("✅ submit_db 表初始化完成")
        
        # 初始化群组记录表
        init_group_records_tables()
        logger.info("✅ 群组records表初始化完成")
        
        # 初始化phone_db（会自动检查表结构）
        # phone_db在导入时已自动初始化
        logger.info("✅ phone_db 表初始化完成")
        
        # 创建强制统计备份目录
        logger.info("✅ 强制统计备份目录创建完成")
        
        logger.info("🎉 所有数据库表初始化完成")
        
    except Exception as e:
        logger.exception("❌ 数据库初始化失败")
        sys.exit(1)

    # ===============================
    # 2️⃣ 创建 Application
    # ===============================
    if not settings.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN 未配置")
        sys.exit(1)

    logger.info("🤖 创建 Telegram Application...")
    application = (
        Application.builder()
        .token(settings.BOT_TOKEN)
        .build()
    )

    # ===============================
    # 2.5️⃣ 启动定时清理任务
    # ===============================
    cleanup_task = None
    try:
        # 创建定时清理任务
        loop = asyncio.get_event_loop()
        cleanup_task = loop.create_task(periodic_cleanup(application))
        logger.info("✅ 定时清理任务已启动")
    except Exception as e:
        logger.warning(f"⚠️ 无法启动定时清理任务: {e}")

    # ===============================
    # 3️⃣ 注册路由 / handlers
    # ===============================
    try:
        logger.info("🔄 注册路由处理器...")
        register_routes(application)
        logger.info("✅ 路由注册完成")
    except Exception as e:
        logger.exception("❌ 路由注册失败")
        sys.exit(1)

    # ===============================
    # 4️⃣ 启动 Bot
    # ===============================
    logger.info("🚀 Bot 启动完成，开始 polling...")
    
    # 显示启动信息
    logger.info(f"👑 管理员数量: {len(settings.ADMINS)}")
    logger.info(f"🏢 群组一 ID: {settings.GROUP_ONE_ID}")
    logger.info(f"🏢 群组二 ID: {settings.GROUP_TWO_ID}")
    logger.info(f"🗂️  数据库路径: {settings.DATA_DIR}")
    
    # 显示超时提醒状态
    logger.info(f"⏰ 超时提醒功能已启用")
    logger.info(f"⏰ 超时时间: {reminder_manager['TIMEOUT_SECONDS']}秒 ({reminder_manager['TIMEOUT_SECONDS'] // 60}分钟)")
    
    # 显示强制统计状态
    force_stats_file = Path("data/force_stats_backup.json")
    if force_stats_file.exists():
        logger.info(f"📊 强制统计备份文件存在: {force_stats_file.absolute()}")
    else:
        logger.info("📊 强制统计备份文件不存在，将创建新的备份")
    
    try:
        application.run_polling(
            allowed_updates=[
                "message",
                "edited_message",
                "callback_query",
            ],
            drop_pending_updates=True,  # 启动时丢弃未处理更新
        )
    finally:
        # 停止时取消清理任务
        if cleanup_task and not cleanup_task.done():
            cleanup_task.cancel()
            logger.info("✅ 定时清理任务已停止")


# ==========================================================
# CLI 启动
# ==========================================================

if __name__ == "__main__":
    main()