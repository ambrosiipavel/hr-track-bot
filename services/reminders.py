"""Напоминания координаторам.

Две задачи, обе раз в сутки в 10:00:
  1. кандидаты, у которых наступила дата перезвона;
  2. кандидаты без финального статуса, висящие дольше STALE_DAYS дней.
"""

import logging

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from database.db import SessionLocal, get_due_callbacks, get_stale_candidates
from database.models import STATUS_LABELS

logger = logging.getLogger(__name__)

STALE_DAYS = 3          # сколько дней кандидат может висеть без движения
REMIND_HOUR = 10        # во сколько отправлять напоминания


async def send_callback_reminders(bot: Bot) -> None:
    """Кому сегодня нужно перезвонить."""
    async with SessionLocal() as session:
        candidates = await get_due_callbacks(session)

    by_coordinator: dict[int, list] = {}
    for candidate in candidates:
        by_coordinator.setdefault(candidate.coordinator.telegram_id, []).append(candidate)

    for telegram_id, items in by_coordinator.items():
        lines = ["Сегодня нужно перезвонить:", ""]
        for c in items:
            lines.append(f"№{c.id} {c.full_name} · {c.phone}")
            lines.append(f"   {c.position}")
        try:
            await bot.send_message(telegram_id, "\n".join(lines))
        except Exception as error:
            logger.warning("Не доставлено %s: %s", telegram_id, error)


async def send_stale_reminders(bot: Bot) -> None:
    """Кандидаты, зависшие без финального статуса."""
    async with SessionLocal() as session:
        candidates = await get_stale_candidates(session, STALE_DAYS)

    by_coordinator: dict[int, list] = {}
    for candidate in candidates:
        by_coordinator.setdefault(candidate.coordinator.telegram_id, []).append(candidate)

    for telegram_id, items in by_coordinator.items():
        lines = [
            f"Кандидаты без результата дольше {STALE_DAYS} дней — {len(items)}:",
            "",
        ]
        for c in items:
            lines.append(
                f"№{c.id} {c.full_name} — {STATUS_LABELS[c.status]}, {c.days_open} дн."
            )
        lines.append("")
        lines.append("Каждого нужно закрыть: вышел на работу или отказ с причиной.")
        try:
            await bot.send_message(telegram_id, "\n".join(lines))
        except Exception as error:
            logger.warning("Не доставлено %s: %s", telegram_id, error)


def setup_scheduler(bot: Bot) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="Europe/Chisinau")

    scheduler.add_job(
        send_callback_reminders,
        CronTrigger(hour=REMIND_HOUR, minute=0),
        args=[bot],
        id="callbacks",
        replace_existing=True,
    )
    scheduler.add_job(
        send_stale_reminders,
        CronTrigger(hour=REMIND_HOUR, minute=5),
        args=[bot],
        id="stale",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Напоминания включены: ежедневно в %02d:00", REMIND_HOUR)
    return scheduler
