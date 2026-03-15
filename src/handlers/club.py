"""
Портал силы - закрытый клуб с подпиской.
Пробный период 24 часа, затем оплата 1990⭐/мес.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import ClubModel, UserModel
from src.keyboards.club import (
    get_club_main_keyboard, get_club_content_list_keyboard,
    get_club_content_keyboard, get_club_admin_keyboard
)
from src.utils.text_loader import ContentLoader
from src.utils.helpers import split_long_message
from src.services.stars_payment import StarsPayment
from src.services.analytics import FunnelTracker
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "club")
async def club_enter(callback: CallbackQuery):
    """Вход в раздел Портал силы."""
    user_id = callback.from_user.id
    has_access = ClubModel.has_access(user_id)

    if has_access:
        await show_club_content(callback)
    else:
        await show_club_info(callback)


async def show_club_info(callback: CallbackQuery):
    """Показать информацию о клубе (для неподписанных)."""
    club_info = ContentLoader.load_club_info()

    text = (
        "🔮 *ПОРТАЛ СИЛЫ — ЗАКРЫТЫЙ КЛУБ*\n\n"
        f"{club_info}\n\n"
        "*✨ ЧТО ВНУТРИ:*\n"
        "• Эксклюзивные практики и медитации (аудио/текст)\n"
        "• Закрытые эфиры с мастером\n"
        "• Скидка 20% на все товары и услуги\n"
        "• Ранний доступ к новым камням\n"
        "• Персональный вопрос мастеру раз в неделю\n\n"
        "*💰 ТАРИФЫ:*\n"
        "• Пробный период: 24 часа бесплатно\n"
        "• Месячная подписка: 1990⭐\n"
        "• Годовая подписка: 19900⭐ (скидка 17%)\n\n"
        "Попробуйте бесплатно и оцените все преимущества!"
    )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=get_club_main_keyboard()
    )
    await callback.answer()


async def show_club_content(callback: CallbackQuery):
    """Показать список доступных материалов клуба."""
    items = ContentLoader.list_club_content()

    if not items:
        await callback.message.edit_text(
            "📭 В клубе пока нет контента. Загляните позже.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return

    await callback.message.edit_text(
        "📚 *МАТЕРИАЛЫ КЛУБА:*",
        parse_mode="Markdown",
        reply_markup=get_club_content_list_keyboard(items)
    )
    await callback.answer()


@router.callback_query(F.data == "club_trial")
async def club_trial(callback: CallbackQuery):
    """Активировать пробный период."""
    user_id = callback.from_user.id
    success = ClubModel.start_trial(user_id)

    if success:
        await FunnelTracker.track(user_id, 'club_trial_started')
        await callback.message.edit_text(
            "✅ *ПРОБНЫЙ ПЕРИОД АКТИВИРОВАН!*\n\n"
            "У вас есть 24 часа бесплатного доступа ко всем материалам клуба.\n"
            "Наслаждайтесь!",
            parse_mode="Markdown",
            reply_markup=get_club_main_keyboard()
        )
    else:
        await callback.message.edit_text(
            "❌ Не удалось активировать пробный период.\n"
            "Возможно, у вас уже есть или была подписка.",
            reply_markup=get_club_main_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data.startswith("club_buy_"))
async def club_buy(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Покупка подписки."""
    period = callback.data.replace("club_buy_", "")  # month или year
    amount = 1990 if period == "month" else 19900
    duration = 30 if period == "month" else 365

    user_id = callback.from_user.id
    await state.update_data(club_period=period, club_duration=duration)

    await StarsPayment.create_invoice(
        bot=bot,
        user_id=user_id,
        title=f"Подписка «Портал силы» ({'месяц' if period=='month' else 'год'})",
        description="Доступ к закрытому клубу",
        payload=f"club_{period}_{user_id}",
        amount_rub=amount
    )

    await callback.answer("💳 Счёт создан", show_alert=False)


@router.callback_query(F.data == "club_content")
async def club_content_list(callback: CallbackQuery):
    """Показать список материалов (для подписанных)."""
    user_id = callback.from_user.id
    if not ClubModel.has_access(user_id):
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return

    await show_club_content(callback)


@router.callback_query(F.data.startswith("club_item_"))
async def club_item_view(callback: CallbackQuery):
    """Просмотр конкретного материала."""
    user_id = callback.from_user.id
    if not ClubModel.has_access(user_id):
        await callback.answer("❌ У вас нет доступа", show_alert=True)
        return

    item_id = callback.data.replace("club_item_", "")
    content = ContentLoader.get_club_content(item_id)

    if not content:
        await callback.answer("❌ Материал не найден", show_alert=True)
        return

    if len(content) > 3500:
        parts = split_long_message(content)
        for part in parts:
            await callback.message.answer(part, parse_mode="Markdown")
    else:
        await callback.message.edit_text(
            content,
            parse_mode="Markdown",
            reply_markup=get_club_content_keyboard()
        )
    await callback.answer()


@router.callback_query(F.data == "club_back")
async def club_back(callback: CallbackQuery):
    """Вернуться к списку материалов."""
    await show_club_content(callback)
    await callback.answer()
