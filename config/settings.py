# config/settings.py

import os
import sys
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class Settings:
    """
    全局配置中心
    所有配置统一从这里读取
    """

    # ==================================================
    # Telegram Bot
    # ==================================================
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN 未设置，请在 .env 文件中配置")
        sys.exit(1)

    # ==================================================
    # 群组配置
    # ==================================================
    GROUP_ONE_ID: int = int(os.getenv("GROUP_ONE_ID", "0").strip())
    GROUP_TWO_ID: int = int(os.getenv("GROUP_TWO_ID", "0").strip())

    # ==================================================
    # 管理员
    # ==================================================
    ADMINS: list[int] = [
        int(x.strip()) for x in os.getenv("ADMINS", "").split(",") if x.strip()
    ]

    # ✅ 日志：用于确认 Render 是否读取到管理员
    logger.info(f"ADMINS loaded: {ADMINS}")

    # ==================================================
    # 行为控制
    # ==================================================
    DUPLICATE_WINDOW_SECONDS: int = 300   # 5 分钟
    CONFIRM_TIMEOUT_SECONDS: int = 120    # 群组二确认超时（预留）

    # ==================================================
    # 路径配置
    # ==================================================
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ✅ 免费版 Render 用项目目录下的 data
    DATA_DIR = os.path.join(BASE_DIR, "data")
    os.makedirs(DATA_DIR, exist_ok=True)

    # ==================================================
    # 数据库路径（新命名）
    # ==================================================
    GROUP_ONE_DB = os.path.join(DATA_DIR, "group_one.db")
    GROUP_TWO_DB = os.path.join(DATA_DIR, "group_two.db")
    PHONE_DB = os.path.join(DATA_DIR, "phone_bot.db")
    SCORE_DB = os.path.join(DATA_DIR, "score.db")
    WHITELIST_DB = os.path.join(DATA_DIR, "whitelist.db")

    # ==================================================
    # 🔁 向下兼容旧代码命名（非常重要）
    # ==================================================
    PHONE_BOT_DB = PHONE_DB
    GROUP1_DB = GROUP_ONE_DB
    GROUP2_DB = GROUP_TWO_DB


# ==================================================
# 全局唯一配置实例
# ==================================================
settings = Settings()