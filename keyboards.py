"""Клавиатуры. Отдельным модулем, чтобы не мешать разметку с логикой."""

from aiogram.types import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup,
)

from database.models import Role, Status, ROLE_LABELS, STATUS_LABELS, User

# Статусы, которые координатор может поставить вручную
SELECTABLE_STATUSES = [
    Status.CONTACTED,
    Status.NO_ANSWER,
    Status.CALLBACK,
    Status.IN_PROGRESS,
    Status.HIRED,
    Status.REJECTED,
]


def main_menu(role: Role) -> ReplyKeyboardMarkup:
    """Нижнее меню зависит от роли: каждый видит только свои действия."""
    rows: list[list[KeyboardButton]] = []

    if role in (Role.RECRUITER, Role.ADMIN):
        rows.append([KeyboardButton(text="➕ Добавить кандидата")])

    if role in (Role.COORDINATOR, Role.ADMIN):
        rows.append([KeyboardButton(text="📋 Мои кандидаты")])

    if role == Role.ADMIN:
        rows.append([
            KeyboardButton(text="📊 Статистика"),
            KeyboardButton(text="👥 Сотрудники"),
        ])

    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True)


def coordinators_kb(coordinators: list[User]) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=c.full_name, callback_data=f"assign:{c.id}")]
        for c in coordinators
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отменить", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def candidate_card_kb(candidate_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Изменить статус", callback_data=f"status:{candidate_id}")],
        [InlineKeyboardButton(text="История", callback_data=f"history:{candidate_id}")],
    ])


def status_kb(candidate_id: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(
            text=STATUS_LABELS[s],
            callback_data=f"setstatus:{candidate_id}:{s.value}",
        )]
        for s in SELECTABLE_STATUSES
    ]
    rows.append([InlineKeyboardButton(text="← Назад", callback_data=f"card:{candidate_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✖️ Отменить", callback_data="cancel")]
    ])


def roles_kb() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=ROLE_LABELS[r], callback_data=f"role:{r.value}")]
        for r in (Role.RECRUITER, Role.COORDINATOR, Role.ADMIN)
    ]
    rows.append([InlineKeyboardButton(text="✖️ Отменить", callback_data="cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def users_kb(users: list[User]) -> InlineKeyboardMarkup:
    """Кнопки отключения доступа для активных сотрудников."""
    rows = [
        [InlineKeyboardButton(
            text=f"Отключить {u.full_name}",
            callback_data=f"deact:{u.id}",
        )]
        for u in users if u.is_active
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)
