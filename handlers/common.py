"""Общие команды: /start, /cancel, отбой посторонним."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove

from database.models import ROLE_LABELS, Role, User
from filters import HasRole
from keyboards import main_menu

router = Router()


@router.message(CommandStart(), HasRole())
async def start_known(message: Message, user: User, state: FSMContext) -> None:
    await state.clear()

    hints = {
        Role.RECRUITER: "Добавляйте кандидатов и назначайте координатора.",
        Role.COORDINATOR: "Здесь только ваши кандидаты. Обновляйте статус после каждого контакта.",
        Role.ADMIN: "Доступны все кандидаты, статистика и управление сотрудниками.",
    }

    await message.answer(
        f"Здравствуйте, {user.full_name}.\n"
        f"Ваша роль: {ROLE_LABELS[user.role]}.\n\n"
        f"{hints[user.role]}",
        reply_markup=main_menu(user.role),
    )


@router.message(CommandStart())
async def start_unknown(message: Message) -> None:
    """Сработает, если пользователя нет в базе."""
    await message.answer(
        "У вас нет доступа к этому боту.\n"
        f"Передайте администратору ваш ID: {message.from_user.id}",
        reply_markup=ReplyKeyboardRemove(),
    )


@router.message(Command("cancel"), HasRole())
async def cancel_command(message: Message, user: User, state: FSMContext) -> None:
    if await state.get_state() is None:
        await message.answer("Сейчас нечего отменять.")
        return

    await state.clear()
    await message.answer("Отменено.", reply_markup=main_menu(user.role))


@router.callback_query(F.data == "cancel")
async def cancel_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await callback.message.edit_text("Отменено.")
    await callback.answer()
