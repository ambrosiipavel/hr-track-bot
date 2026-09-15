"""Рекрутер: добавление кандидата пошагово."""

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database.db import SessionLocal, create_candidate, get_coordinators, get_user_by_tg
from database.models import Role, User
from filters import HasRole
from keyboards import cancel_kb, coordinators_kb, main_menu

router = Router()

PHONE_RE = re.compile(r"^\+?\d[\d\s\-()]{6,19}$")


class AddCandidate(StatesGroup):
    last_name = State()
    first_name = State()
    phone = State()
    position = State()
    coordinator = State()


@router.message(F.text == "➕ Добавить кандидата", HasRole(Role.RECRUITER, Role.ADMIN))
async def add_start(message: Message, user: User, state: FSMContext) -> None:
    await state.set_state(AddCandidate.last_name)
    await message.answer("Фамилия кандидата:", reply_markup=cancel_kb())


@router.message(AddCandidate.last_name)
async def add_last_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Слишком коротко. Введите фамилию:")
        return

    await state.update_data(last_name=text)
    await state.set_state(AddCandidate.first_name)
    await message.answer("Имя:", reply_markup=cancel_kb())


@router.message(AddCandidate.first_name)
async def add_first_name(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Слишком коротко. Введите имя:")
        return

    await state.update_data(first_name=text)
    await state.set_state(AddCandidate.phone)
    await message.answer("Номер телефона:", reply_markup=cancel_kb())


@router.message(AddCandidate.phone)
async def add_phone(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if not PHONE_RE.match(text):
        await message.answer(
            "Не похоже на номер. Введите в формате +37360000000 или 060000000:"
        )
        return

    await state.update_data(phone=text)
    await state.set_state(AddCandidate.position)
    await message.answer("Должность:", reply_markup=cancel_kb())


@router.message(AddCandidate.position)
async def add_position(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if len(text) < 2:
        await message.answer("Слишком коротко. Введите должность:")
        return

    await state.update_data(position=text)

    async with SessionLocal() as session:
        coordinators = await get_coordinators(session)

    if not coordinators:
        await state.clear()
        await message.answer(
            "В базе нет ни одного координатора. "
            "Попросите администратора добавить сотрудника с этой ролью."
        )
        return

    await state.set_state(AddCandidate.coordinator)
    await message.answer("Кому назначаем кандидата:", reply_markup=coordinators_kb(coordinators))


@router.callback_query(AddCandidate.coordinator, F.data.startswith("assign:"))
async def add_coordinator(callback: CallbackQuery, state: FSMContext) -> None:
    coordinator_id = int(callback.data.split(":")[1])
    data = await state.get_data()

    async with SessionLocal() as session:
        author = await get_user_by_tg(session, callback.from_user.id)

        candidate = await create_candidate(
            session,
            first_name=data["first_name"],
            last_name=data["last_name"],
            phone=data["phone"],
            position=data["position"],
            coordinator_id=coordinator_id,
            created_by_id=author.id,
        )
        coordinator = await session.get(User, coordinator_id)

    await state.clear()
    await callback.message.edit_text(
        f"Кандидат добавлен (№{candidate.id})\n\n"
        f"{candidate.full_name}\n"
        f"Телефон: {candidate.phone}\n"
        f"Должность: {candidate.position}\n"
        f"Координатор: {coordinator.full_name}"
    )
    await callback.answer()
    await callback.message.answer("Что дальше?", reply_markup=main_menu(author.role))

    # уведомляем координатора о новом кандидате
    try:
        await callback.bot.send_message(
            coordinator.telegram_id,
            f"Вам назначен новый кандидат №{candidate.id}\n\n"
            f"{candidate.full_name}\n"
            f"Телефон: {candidate.phone}\n"
            f"Должность: {candidate.position}",
        )
    except Exception:
        # координатор мог не запускать бота — не роняем процесс из-за этого
        pass
