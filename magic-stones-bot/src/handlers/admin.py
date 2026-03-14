"""
Общая админ-панель - главное меню и навигация.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext

from src.database.models import UserModel
from src.keyboards.admin import get_admin_main_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.text == "/admin")
async def admin_cmd(message: Message):
    """Вход в админ-панель."""
    if not UserModel.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    await message.answer(
        "⚙️ *АДМИН-ПАНЕЛЬ*\n\n"
        "Добро пожаловать в систему управления.\n"
        "Здесь вы можете управлять всем контентом, заказами, пользователями.",
        reply_markup=get_admin_main_keyboard(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "admin_menu")
async def admin_menu(callback: CallbackQuery):
    """Главное меню админки."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    await callback.message.edit_text(
        "⚙️ *АДМИН-ПАНЕЛЬ*\n\nВыберите раздел:",
        reply_markup=get_admin_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    """Возврат в главное меню админки."""
    await admin_menu(callback)