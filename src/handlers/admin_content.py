"""
Админ-панель: управление контентом (база знаний, посты).
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from src.database.models import UserModel
from src.utils.text_loader import ContentLoader

logger = logging.getLogger(__name__)
router = Router()

@router.callback_query(F.data == "admin_content")
async def admin_content(callback: CallbackQuery):
    """Главное меню управления контентом."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    stones_count = len(ContentLoader.list_posts())  # это для примера
    
    text = (
        "📚 *УПРАВЛЕНИЕ КОНТЕНТОМ*\n\n"
        f"• Камней в базе: {stones_count}\n"
        f"• Постов: {len(ContentLoader.list_posts())}\n\n"
        "Выберите раздел:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📚 База знаний", callback_data="admin_stones")],
        [InlineKeyboardButton(text="📝 Посты", callback_data="admin_posts")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()