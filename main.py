# main.py
import asyncio
import json
import logging
import os
import sqlite3
import sys
import threading
import time
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
# Render 健康检查 HTTP 服务
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
        return


def start_healthcheck_server():
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
    for db_path in [settings.GROUP_ONE_DB, settings.GROUP_TWO_DB]:
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()

                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records'")
                table_exists = cur.fetchone()

                if not table_exists:
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

                conn.commit()
                logger.info(f"✅ records 表处理完成: {db_path}")

        except Exception as e:
            logger.error(f"❌ 处理 records 表失败 {db_path}: {e}")


# ==========================================================
# 强制统计备份清理
# ==========================================================

def cleanup_old_force_stats():
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

        except Exception as e:
            logger.error(f"❌ 清理强制统计备份失败: {e}")


# ==========================================================
# 定时清理任务
# ==========================================================

async def periodic_cleanup(application: Application):
    while True:
        try:
            await asyncio.sleep(6 * 60 * 60)

            cleaned = reminder_manager["cleanup_old_records"](hours=24)

            if cleaned > 0:
                logger.info(f"🧹 定期清理完成: 清理了 {cleaned} 条旧记录")

        except asyncio.CancelledError:
            logger.info("🛑 定时清理任务已取消")
            break
        except Exception as e:
            logger.error(f"❌ 定时清理失败: {e}")


async def on_startup(application: Application):
    cleanup_task = asyncio.create_task(periodic_cleanup(application))
    application.bot_data["_cleanup_task"] = cleanup_task
    logger.info("✅ 定时清理任务已启动")


async def on_shutdown(application: Application):
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

    logger.info("🚀 Bot 正在启动...")

    start_healthcheck_server()

    try:
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)

        cleanup_old_force_stats()

        init_score_tables()
        init_whitelist_tables()
        init_submit_tables()
        init_group_records_tables()

        _ = phone_db

    except Exception:
        logger.exception("❌ 数据库初始化失败")
        sys.exit(1)

    if not settings.BOT_TOKEN:
        logger.error("❌ BOT_TOKEN 未配置")
        sys.exit(1)

    application = (
        Application.builder()
        .token(settings.BOT_TOKEN)
        .post_init(on_startup)
        .post_shutdown(on_shutdown)
        .build()
    )

    register_routes(application)

    application.run_polling(
        allowed_updates=[
            "message",
            "edited_message",
            "callback_query",
        ],
        drop_pending_updates=True,
        close_loop=False,
    )


if __name__ == "__main__":
    while True:
        try:
            main()
        except Exception:
            logger.exception("❌ Bot 运行异常，5秒后自动重启...")
            time.sleep(5)