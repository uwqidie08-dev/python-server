import os
import asyncio
from datetime import datetime
from pathlib import Path

from telegram import Bot


# 管理员 Telegram ID（可以多个）
ADMIN_TELEGRAM_IDS = {
    8284983034,
    6140897469,
}


# 机器人 token
BOT_TOKEN = "你的机器人token"


# 要备份的数据库文件
DB_FILES = [
    "data/group_one.db",
    "data/group_two.db",
    "data/score.db",
    "data/whitelist.db",
    "data/submit.db",
]


async def send_db_backups():

    if not BOT_TOKEN:
        print("❌ BOT_TOKEN 未设置")
        return

    bot = Bot(token=BOT_TOKEN)

    now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    sent_any = False

    for db_path in DB_FILES:

        path = Path(db_path)

        if not path.exists():
            print(f"⚠️ 备份跳过，不存在: {db_path}")
            continue

        caption = f"📦 数据库自动备份\n文件: {path.name}\n时间: {now_str}"

        for admin_id in ADMIN_TELEGRAM_IDS:

            with open(path, "rb") as f:

                await bot.send_document(
                    chat_id=admin_id,
                    document=f,
                    filename=f"{now_str}_{path.name}",
                    caption=caption,
                )

        print(f"✅ 已发送备份: {db_path}")
        sent_any = True

    if not sent_any:
        print("⚠️ 没有数据库文件可备份")


async def backup_loop():

    while True:

        try:
            await send_db_backups()

        except Exception as e:
            print(f"❌ 自动备份失败: {e}")

        # 每24小时备份一次
        await asyncio.sleep(24 * 60 * 60)