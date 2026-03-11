# main.py
import asyncio
import json
import logging
import os
import sqlite3
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from telegram.ext import Application

from config.settings import settings

# 数据库初始化
from db.score_db import init_score_tables
from db.whitelist_db import init_whitelist_tables
from db.submit_db import init_submit_tables
from db.phone_db import phone_db  # 确保 phone_db 初始化

# 路由注册
from core.router import register_routes

# 超时提醒管理
from utils.reminder import reminder_manager


# ==========================================================
# 日志配置
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


# ==========================================================
# Render 健康检查 HTTP 服务（不会影响你的群逻辑）
# 目的：让 Render Web Service 检测到端口，避免“No open ports detected”
# ==========================================================

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"OK")
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        # 不输出 http server 的访问日志，避免刷屏
        return


def start_healthcheck_server():
    """
    仅在 Render/云端环境中启动一个超轻量 HTTP 服务
    不影响 Telegram Bot 逻辑，只用于平台健康检查
    """
    port_str = os.environ.get("PORT")
    if not port_str:
        logger.info("ℹ️ 未检测到 PORT 环境变量，跳过健康检查服务（本地运行正常）")
        return None

    try:
        port = int(port_str)
    except ValueError:
        logger.warning(f"⚠️ PORT 环境变量无效: {port_str}")
        return None

    def _run():
        try:
            server = HTTPServer(("0.0.0.0", port), _HealthHandler)
            logger.info(f"🌐 健康检查服务已启动: 0.0.0.0:{port}")
            server.serve_forever()
        except Exception as e:
            logger.exception(f"❌ 健康检查服务启动失败: {e}")

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return thread


# ==========================================================
# 初始化群组 records 表
# ==========================================================

def init_group_records_tables():
    """初始化群组记录表 - 使用更安全的方法处理表结构"""
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
                    logger.info(f"🔍 检查 records 表结构: {db_path}")

                    # 获取现有列
                    cur.execute("PRAGMA table_info(records)")
                    existing_columns_info = cur.fetchall()
                    existing_columns = [col[1] for col in existing_columns_info]

                    # 需要确保存在的列
                    required_columns = [
                        "data", "number", "user_id", "username",
                        "group_id", "message_id", "created_at"
                    ]

                    # 检查是否缺少必要列
                    missing_columns = [col for col in required_columns if col not in existing_columns]

                    if missing_columns:
                        logger.warning(f"⚠️ records 表缺少必要列 {missing_columns}，重建表: {db_path}")

                        try:
                            cur.execute("SELECT COUNT(*) FROM records")
                            record_count = cur.fetchone()[0]

                            if record_count > 0:
                                logger.warning(f"⚠️ records 表有 {record_count} 条数据，将丢失: {db_path}")

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

                            logger.info(f"✅ 重建 records 表完成: {db_path}")

                        except Exception as e:
                            logger.error(f"❌ 重建表失败: {db_path}, {e}")

                            try:
                                for column in missing_columns:
                                    if column == "data":
                                        cur.execute("ALTER TABLE records ADD COLUMN data TEXT")
                                    elif column == "number":
                                        cur.execute("ALTER TABLE records ADD COLUMN number INTEGER")
                                    elif column == "user_id":
                                        cur.execute("ALTER TABLE records ADD COLUMN user_id INTEGER")
                                    elif column == "username":
                                        cur.execute("ALTER TABLE records ADD COLUMN username TEXT")
                                    elif column == "group_id":
                                        cur.execute("ALTER TABLE records ADD COLUMN group_id INTEGER")
                                    elif column == "message_id":
                                        cur.execute("ALTER TABLE records ADD COLUMN message_id INTEGER")
                                    elif column == "created_at":
                                        cur.execute("ALTER TABLE records ADD COLUMN created_at TEXT")

                                logger.info(f"✅ 添加缺失列完成: {db_path}, 列: {missing_columns}")

                            except Exception as e2:
                                logger.error(f"❌ 添加列也失败: {db_path}, {e2}")
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
                        logger.info(f"✅ records 表结构完整: {db_path}")

                        try:
                            cur.execute("SELECT data, number, user_id FROM records LIMIT 1")
                            test_result = cur.fetchone()
                            if test_result:
                                logger.info(f"📊 records 表已有 {test_result[0]} 等数据: {db_path}")
                        except Exception:
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
    backup_file = "data/force_stats_backup.json"
    if os.path.exists(backup_file):
        try:
            with open(backup_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            backup_date_str = data.get("date")
            if backup_date_str:
                from datetime import datetime

                backup_date = datetime.strptime(backup_date_str, "%Y-%m-%d").date()
                today = datetime.now().date()

                if backup_date < today:
                    os.remove(backup_file)
                    logger.info(f"🗑️ 删除旧的强制统计备份: {backup_date_str}")
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
            cleaned = reminder_manager["cleanup_old_records"](hours=24)

            if cleaned > 0:
                logger.info(f"🧹 定期清理完成: 清理了 {cleaned} 条旧记录")

        except asyncio.CancelledError:
            logger.info("🛑 定时清理任务已取消")
            break
        except Exception as e:
            logger.error(f"❌ 定时清理失败: {e}")


async def on_startup(application: Application):
    """
    Application 启动后的钩子
    在这里创建后台任务，避免 event loop 生命周期问题
    """
    try:
        cleanup_task = asyncio.create_task(periodic_cleanup(application))
        application.bot_data["_cleanup_task"] = cleanup_task
        logger.info("✅ 定时清理任务已启动")
    except Exception as e:
        logger.warning(f"⚠️ 无法启动定时清理任务: {e}")


async def on_shutdown(application: Application):
    """
    Application 停止前的钩子
    """
    cleanup_task = application.bot_data.get("_cleanup_task")
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        logger.info("✅ 定时清理任务已停止")


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
    # 0️⃣ 启动健康检查服务（仅 Render 用）
    # ===============================
    start_healthcheck_server()

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

        # 初始化 phone_db（导入时已自动初始化）
        _ = phone_db
        logger.info("✅ phone_db 表初始化完成")

        logger.info("🎉 所有数据库表初始化完成")

    except Exception:
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
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    # ===============================
    # 3️⃣ 注册路由 / handlers
    # ===============================
    try:
        logger.info("🔄 注册路由处理器...")
        register_routes(application)
        logger.info("✅ 路由注册完成")
    except Exception:
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
    logger.info(f"🗂️ 数据库路径: {settings.DATA_DIR}")

    # 显示超时提醒状态
    logger.info("⏰ 超时提醒功能已启用")
    logger.info(
        f"⏰ 超时时间: {reminder_manager['TIMEOUT_SECONDS']}秒 "
        f"({reminder_manager['TIMEOUT_SECONDS'] // 60}分钟)"
    )

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
            drop_pending_updates=True,
        )
    except Exception:
        logger.exception("❌ Bot 运行失败")
        sys.exit(1)


# ==========================================================
# CLI 启动
# ==========================================================

if __name__ == "__main__":
    main()