"""
FAQ - часто задаваемые вопросы.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.database.models import FAQModel

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "faq")
async def faq_list(callback: CallbackQuery):
    """Список вопросов и ответов."""
    faqs = FAQModel.get_all(active_only=True)
    
    if not faqs:
        await callback.message.edit_text(
            "❓ *ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ*\n\n"
            "Раздел находится в наполнении.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "❓ *ЧАСТО ЗАДАВАЕМЫЕ ВОПРОСЫ*\n\n"
    
    for faq in faqs:
        text += f"*Q: {faq['question']}*\n"
        text += f"A: {faq['answer']}\n\n"
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
        ])
    )
    await callback.answer()