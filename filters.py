"""Фильтр доступа по ролям.

Правило простое: если пользователя нет в таблице users — бот его не обслуживает.
Так посторонние не попадут во внутреннюю базу кандидатов.
"""

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from database.db import SessionLocal, get_user_by_tg
from database.models import Role, User


class HasRole(BaseFilter):
    def __init__(self, *roles: Role):
        self.roles = roles

    async def __call__(self, event: Message | CallbackQuery) -> bool | dict:
        async with SessionLocal() as session:
            user = await get_user_by_tg(session, event.from_user.id)

        if user is None or not user.is_active:
            return False
        if self.roles and user.role not in self.roles:
            return False

        # пробрасываем пользователя в хендлер параметром user
        return {"user": user}


async def fetch_user(telegram_id: int) -> User | None:
    async with SessionLocal() as session:
        return await get_user_by_tg(session, telegram_id)
