"""Настройки проекта. Всё чувствительное — в .env, не в коде."""

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Файл базы данных лежит рядом с проектом.
# При переходе на PostgreSQL меняется только эта строка:
# DATABASE_URL = "postgresql+asyncpg://user:pass@localhost/hrbot"
DATABASE_URL = "sqlite+aiosqlite:///hrbot.db"

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан. Создай файл .env рядом с bot.py и впиши в него:\n"
        "BOT_TOKEN=токен_от_BotFather\n"
        "ADMIN_ID=твой_telegram_id"
    )

if not ADMIN_ID:
    raise RuntimeError("ADMIN_ID не задан в .env. Узнать свой ID можно у бота @userinfobot")
