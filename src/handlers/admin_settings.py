"""
Админ-панель: общие настройки бота.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database.db import db
from src.database.models import UserModel, SettingsModel
from src.utils.helpers import escape_markdown

logger = logging.getLogger(__name__)
router = Router()


class SettingsStates(StatesGroup):
    waiting_setting_value = State()


@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    """Главное меню настроек."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    settings = SettingsModel.get_all()
    
    text = (
        "⚙️ *ОБЩИЕ НАСТРОЙКИ БОТА*\n\n"
        f"👋 *Приветствие новых:*\n{escape_markdown(settings['welcome_text'][:100])}...\n\n"
        f"🔄 *Приветствие вернувшихся:*\n{escape_markdown(settings['return_text'][:100])}...\n\n"
        f"💰 *Кэшбэк:* {settings['cashback_percent']}% (мин. заказ {settings['min_order_for_cashback']}₽)\n"
        f"📞 *Контакты мастера:* {settings['contact_master']}\n"
        f"🚚 *Информация о доставке:*\n{escape_markdown(settings['delivery_info'][:50])}...\n"
    )
    
    buttons = [
        [InlineKeyboardButton(text="👋 Приветствие новых", callback_data="settings_edit_welcome_text")],
        [InlineKeyboardButton(text="🔄 Приветствие вернувшихся", callback_data="settings_edit_return_text")],
        [InlineKeyboardButton(text="💰 Процент кэшбэка", callback_data="settings_edit_cashback_percent")],
        [InlineKeyboardButton(text="💰 Мин. сумма для кэшбэка", callback_data="settings_edit_min_order_for_cashback")],
        [InlineKeyboardButton(text="📞 Контакт мастера", callback_data="settings_edit_contact_master")],
        [InlineKeyboardButton(text="🚚 Информация о доставке", callback_data="settings_edit_delivery_info")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("settings_edit_"))
async def settings_edit(callback: CallbackQuery, state: FSMContext):
    """Начать редактирование настройки."""
    setting_key = callback.data.replace("settings_edit_", "")
    await state.update_data(setting_key=setting_key)
    await state.set_state(SettingsStates.waiting_setting_value)
    
    prompts = {
        'welcome_text': '✏️ Введите новый текст приветствия для новых пользователей:',
        'return_text': '✏️ Введите новый текст приветствия для вернувшихся пользователей:',
        'cashback_percent': '✏️ Введите процент кэшбэка (только число, например 5):',
        'min_order_for_cashback': '✏️ Введите минимальную сумму заказа для начисления кэшбэка (в рублях):',
        'contact_master': '✏️ Введите контакт мастера (например @username):',
        'delivery_info': '✏️ Введите информацию о доставке:'
    }
    
    await callback.message.edit_text(prompts.get(setting_key, "Введите новое значение:"))
    await callback.answer()


@router.message(SettingsStates.waiting_setting_value)
async def settings_save(message: Message, state: FSMContext):
    """Сохранить новое значение настройки."""
    data = await state.get_data()
    setting_key = data['setting_key']
    new_value = message.text
    
    # Валидация для числовых полей
    if setting_key in ['cashback_percent', 'min_order_for_cashback']:
        try:
            int(new_value)
        except ValueError:
            await message.answer("❌ Введите число!")
            return
    
    success = SettingsModel.set(setting_key, new_value)
    await state.clear()
    
    if success:
        await message.answer(
            f"✅ *Настройка {setting_key} обновлена!*",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К НАСТРОЙКАМ", callback_data="admin_settings")]
            ])
        )
    else:
        await message.answer(
            "❌ Ошибка при сохранении",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К НАСТРОЙКАМ", callback_data="admin_settings")]
            ])
        )