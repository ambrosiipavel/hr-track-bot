"""Координатор: список своих кандидатов, смена статуса, история."""

from datetime import datetime, timedelta

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from database.db import (
    SessionLocal, change_status, get_candidate,
    get_candidates_for_coordinator, get_history, get_user_by_tg,
)
from database.models import (
    FINAL_STATUSES, ROLE_LABELS, STATUS_LABELS, Role, Status, User
)
from filters import HasRole
from keyboards import candidate_card_kb, main_menu, status_kb

router = Router()


class CloseCandidate(StatesGroup):
    reason = State()
    callback_days = State()


def card_text(candidate) -> str:
    lines = [
        f"Кандидат №{candidate.id}",
        "",
        candidate.full_name,
        f"Телефон: {candidate.phone}",
        f"Должность: {candidate.position}",
        f"Статус: {STATUS_LABELS[candidate.status]}",
    ]
    if candidate.next_contact_at:
        lines.append(f"Перезвонить: {candidate.next_contact_at:%d.%m.%Y}")
    if candidate.reject_reason:
        lines.append(f"Причина отказа: {candidate.reject_reason}")
    return "\n".join(lines)


@router.message(F.text == "📋 Мои кандидаты", HasRole(Role.COORDINATOR, Role.ADMIN))
async def my_candidates(message: Message, user: User) -> None:
    async with SessionLocal() as session:
        candidates = await get_candidates_for_coordinator(session, user.id)

    if not candidates:
        await message.answer("Открытых кандидатов нет.")
        return

    await message.answer(f"Открытых кандидатов: {len(candidates)}")
    for candidate in candidates:
        await message.answer(
            card_text(candidate),
            reply_markup=candidate_card_kb(candidate.id),
        )


@router.callback_query(F.data.startswith("card:"))
async def show_card(callback: CallbackQuery) -> None:
    candidate_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        candidate = await get_candidate(session, candidate_id)

    await callback.message.edit_text(
        card_text(candidate),
        reply_markup=candidate_card_kb(candidate_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("status:"))
async def choose_status(callback: CallbackQuery) -> None:
    candidate_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        user = await get_user_by_tg(session, callback.from_user.id)
        candidate = await get_candidate(session, candidate_id)

    # координатор не может трогать чужих кандидатов
    if user.role != Role.ADMIN and candidate.coordinator_id != user.id:
        await callback.answer("Это не ваш кандидат.", show_alert=True)
        return

    await callback.message.edit_text(
        f"{candidate.full_name}\nТекущий статус: {STATUS_LABELS[candidate.status]}\n\n"
        "Выберите новый статус:",
        reply_markup=status_kb(candidate_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("setstatus:"))
async def set_status(callback: CallbackQuery, state: FSMContext) -> None:
    _, raw_id, raw_status = callback.data.split(":")
    candidate_id = int(raw_id)
    new_status = Status(raw_status)

    async with SessionLocal() as session:
        user = await get_user_by_tg(session, callback.from_user.id)
        candidate = await get_candidate(session, candidate_id)

        if user.role != Role.ADMIN and candidate.coordinator_id != user.id:
            await callback.answer("Это не ваш кандидат.", show_alert=True)
            return

        # отказ требует причины — без неё кандидата закрыть нельзя
        if new_status == Status.REJECTED:
            await state.set_state(CloseCandidate.reason)
            await state.update_data(candidate_id=candidate_id)
            await callback.message.edit_text(
                f"{candidate.full_name}\n\nУкажите причину отказа одним сообщением:"
            )
            await callback.answer()
            return

        # для «перезвонить» спрашиваем, через сколько дней
        if new_status == Status.CALLBACK:
            await state.set_state(CloseCandidate.callback_days)
            await state.update_data(candidate_id=candidate_id)
            await callback.message.edit_text(
                f"{candidate.full_name}\n\nЧерез сколько дней перезвонить? Введите число:"
            )
            await callback.answer()
            return

        await change_status(session, candidate, new_status, user.id)
        candidate = await get_candidate(session, candidate_id)

    await callback.message.edit_text(
        card_text(candidate),
        reply_markup=None if candidate.status in FINAL_STATUSES else candidate_card_kb(candidate_id),
    )
    await callback.answer("Статус обновлён")


@router.message(CloseCandidate.reason)
async def save_reject_reason(message: Message, state: FSMContext) -> None:
    reason = (message.text or "").strip()
    if len(reason) < 3:
        await message.answer("Причина слишком короткая. Опишите подробнее:")
        return

    data = await state.get_data()
    async with SessionLocal() as session:
        user = await get_user_by_tg(session, message.from_user.id)
        candidate = await get_candidate(session, data["candidate_id"])
        await change_status(session, candidate, Status.REJECTED, user.id, comment=reason)
        candidate = await get_candidate(session, data["candidate_id"])

    await state.clear()
    await message.answer(
        "Кандидат закрыт.\n\n" + card_text(candidate),
        reply_markup=main_menu(user.role),
    )


@router.message(CloseCandidate.callback_days)
async def save_callback_date(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit() or not 1 <= int(raw) <= 90:
        await message.answer("Введите число от 1 до 90:")
        return

    days = int(raw)
    next_contact = datetime.now() + timedelta(days=days)

    data = await state.get_data()
    async with SessionLocal() as session:
        user = await get_user_by_tg(session, message.from_user.id)
        candidate = await get_candidate(session, data["candidate_id"])
        await change_status(
            session, candidate, Status.CALLBACK, user.id,
            comment=f"Перезвонить через {days} дн.",
            next_contact_at=next_contact,
        )
        candidate = await get_candidate(session, data["candidate_id"])

    await state.clear()
    await message.answer(
        card_text(candidate),
        reply_markup=main_menu(user.role),
    )


@router.callback_query(F.data.startswith("history:"))
async def show_history(callback: CallbackQuery) -> None:
    candidate_id = int(callback.data.split(":")[1])

    async with SessionLocal() as session:
        candidate = await get_candidate(session, candidate_id)
        records = await get_history(session, candidate_id)

    lines = [f"История по кандидату №{candidate_id} — {candidate.full_name}", ""]
    for record in records:
        was = STATUS_LABELS[record.old_status] if record.old_status else "—"
        now = STATUS_LABELS[record.new_status]
        lines.append(f"{record.created_at:%d.%m.%Y %H:%M} · {record.user.full_name}")
        lines.append(f"   {was} → {now}")
        if record.comment:
            lines.append(f"   {record.comment}")
        lines.append("")

    await callback.message.edit_text(
        "\n".join(lines),
        reply_markup=candidate_card_kb(candidate_id),
    )
    await callback.answer()
