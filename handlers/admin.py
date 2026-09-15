"""Администратор: сотрудники, статистика, поиск, выгрузка."""

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from database.db import (
    SessionLocal, deactivate_user, get_all_users, get_open_candidates,
    get_stats, search_candidates, create_user,
)
from database.models import ROLE_LABELS, STATUS_LABELS, Role, User
from filters import HasRole
from keyboards import main_menu, roles_kb, users_kb
from services.export import build_workbook

router = Router()


class AddUser(StatesGroup):
    telegram_id = State()
    full_name = State()
    role = State()


# ---------- сотрудники ----------

@router.message(F.text == "👥 Сотрудники", HasRole(Role.ADMIN))
async def staff_list(message: Message, user: User) -> None:
    async with SessionLocal() as session:
        users = await get_all_users(session)

    lines = ["Сотрудники:", ""]
    for u in users:
        mark = "" if u.is_active else " (отключён)"
        lines.append(f"{u.full_name} — {ROLE_LABELS[u.role]}{mark}")

    lines.append("")
    lines.append("Добавить сотрудника: /adduser")
    await message.answer("\n".join(lines), reply_markup=users_kb(users))


@router.message(Command("adduser"), HasRole(Role.ADMIN))
async def add_user_start(message: Message, user: User, state: FSMContext) -> None:
    await state.set_state(AddUser.telegram_id)
    await message.answer(
        "Telegram ID сотрудника (число).\n\n"
        "Сотрудник может узнать свой ID у бота @userinfobot "
        "или отправив /start этому боту — бот покажет ID в ответе."
    )


@router.message(AddUser.telegram_id)
async def add_user_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer("Нужно число. Введите Telegram ID:")
        return

    await state.update_data(telegram_id=int(raw))
    await state.set_state(AddUser.full_name)
    await message.answer("Фамилия и имя сотрудника:")


@router.message(AddUser.full_name)
async def add_user_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if len(name) < 3:
        await message.answer("Слишком коротко. Введите фамилию и имя:")
        return

    await state.update_data(full_name=name)
    await state.set_state(AddUser.role)
    await message.answer("Роль:", reply_markup=roles_kb())


@router.callback_query(AddUser.role, F.data.startswith("role:"))
async def add_user_role(callback: CallbackQuery, state: FSMContext) -> None:
    role = Role(callback.data.split(":")[1])
    data = await state.get_data()

    async with SessionLocal() as session:
        created = await create_user(
            session,
            telegram_id=data["telegram_id"],
            full_name=data["full_name"],
            role=role,
        )

    await state.clear()

    if created is None:
        await callback.message.edit_text("Такой Telegram ID уже есть в базе.")
        await callback.answer()
        return

    await callback.message.edit_text(
        f"Добавлен сотрудник:\n{created.full_name} — {ROLE_LABELS[created.role]}"
    )
    await callback.answer()

    try:
        await callback.bot.send_message(
            created.telegram_id,
            f"Вам выдан доступ к боту.\nРоль: {ROLE_LABELS[created.role]}\n"
            "Отправьте /start, чтобы начать работу.",
        )
    except Exception:
        await callback.message.answer(
            "Сотрудник добавлен, но уведомление не доставлено — "
            "он ещё не запускал бота. Попросите его отправить /start."
        )


@router.callback_query(F.data.startswith("deact:"), HasRole(Role.ADMIN))
async def deactivate(callback: CallbackQuery, user: User) -> None:
    user_id = int(callback.data.split(":")[1])

    if user_id == user.id:
        await callback.answer("Нельзя отключить самого себя.", show_alert=True)
        return

    async with SessionLocal() as session:
        target = await deactivate_user(session, user_id)
        users = await get_all_users(session)

    lines = ["Сотрудники:", ""]
    for u in users:
        mark = "" if u.is_active else " (отключён)"
        lines.append(f"{u.full_name} — {ROLE_LABELS[u.role]}{mark}")

    await callback.message.edit_text("\n".join(lines), reply_markup=users_kb(users))
    await callback.answer(f"{target.full_name} отключён")


# ---------- статистика ----------

@router.message(F.text == "📊 Статистика", HasRole(Role.ADMIN))
async def stats(message: Message, user: User) -> None:
    async with SessionLocal() as session:
        data = await get_stats(session)
        open_items = await get_open_candidates(session)

    lines = [
        "Статистика",
        "",
        f"Всего кандидатов: {data['total']}",
        f"В работе: {data['open']}",
        f"Закрыто: {data['closed']}",
        "",
        "По статусам:",
    ]
    for status, count in data["by_status"].items():
        lines.append(f"  {STATUS_LABELS[status]}: {count}")

    if open_items:
        lines.append("")
        lines.append("Незакрытые кандидаты:")
        for c in open_items[:15]:
            days = (c.days_open)
            lines.append(
                f"  №{c.id} {c.full_name} — {STATUS_LABELS[c.status]}, {days} дн."
            )
        if len(open_items) > 15:
            lines.append(f"  … и ещё {len(open_items) - 15}")

    lines.append("")
    lines.append("Выгрузка: /export · Поиск: /find текст")
    await message.answer("\n".join(lines))


# ---------- поиск ----------

@router.message(Command("find"), HasRole(Role.ADMIN, Role.RECRUITER))
async def find(message: Message, user: User) -> None:
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Укажите, что искать. Пример: /find Сидоров")
        return

    query = parts[1].strip()
    async with SessionLocal() as session:
        found = await search_candidates(session, query)

    if not found:
        await message.answer(f"По запросу «{query}» ничего не найдено.")
        return

    lines = [f"Найдено: {len(found)}", ""]
    for c in found[:20]:
        lines.append(
            f"№{c.id} {c.full_name} · {c.phone}\n"
            f"   {c.position} — {STATUS_LABELS[c.status]}"
        )
    if len(found) > 20:
        lines.append(f"… и ещё {len(found) - 20}")

    await message.answer("\n".join(lines))


# ---------- экспорт ----------

@router.message(Command("export"), HasRole(Role.ADMIN))
async def export(message: Message, user: User) -> None:
    await message.answer("Готовлю файл…")

    async with SessionLocal() as session:
        content, filename = await build_workbook(session)

    if content is None:
        await message.answer("В базе пока нет кандидатов.")
        return

    await message.answer_document(
        BufferedInputFile(content, filename=filename),
        caption="Выгрузка кандидатов и истории статусов",
        reply_markup=main_menu(user.role),
    )
