# core/app.py
import logging
from telegram.ext import (
    Application,
    MessageHandler,
    CommandHandler,
    filters,
)

from config.settings import settings
from core.router import route_message

logger = logging.getLogger(__name__)


def create_application() -> Application:
    """
    创建并配置 Telegram Application
    """
    app = Application.builder().token(settings.BOT_TOKEN).build()

    # 所有“普通消息”都先进入 router
    app.add_handler(
        MessageHandler(filters.ALL, route_message)
    )

    logger.info("✅ Application 创建完成，消息路由已绑定")
    return app
