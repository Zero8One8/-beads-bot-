"""
Базовые пользовательские хендлеры.
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext

from src.database.db import db
from src.database.models import UserModel, SettingsModel
from src.keyboards.inline import get_main_keyboard
from src.services.analytics import FunnelTracker
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, bot):
    """Обработчик команды /start."""
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # Парсим реферальный код
    ref_id = None
    if message.text and len(message.text.split()) > 1:
        try:
            ref_arg = message.text.split()[1]
            if ref_arg.startswith('ref'):
                ref_id = int(ref_arg.replace('ref', ''))
                if ref_id == user_id:
                    ref_id = None
        except:
            ref_id = None
    
    # Регистрируем пользователя
    is_new = not UserModel.get(user_id)
    UserModel.create_or_update(user_id, username, first_name, ref_id)
    
    # Начисляем бонусы за реферала
    if is_new and ref_id:
        from src.database.models import ReferralModel
        ReferralModel.add(ref_id, user_id)
        try:
            await bot.send_message(
                ref_id,
                "🎉 *По вашей реферальной ссылке зарегистрировался новый пользователь!*\n"
                "Вам начислено *100 бонусов*!",
                parse_mode="Markdown"
            )
        except:
            pass
    
    # Отслеживаем в воронке
    await FunnelTracker.track(user_id, 'start')
    await state.clear()
    
    # Отправляем приветствие
    settings = SettingsModel.get_all()
    welcome_text = settings.get('welcome_text', '🌟 ДОБРО ПОЖАЛОВАТЬ!')
    
    await message.answer(welcome_text, reply_markup=get_main_keyboard())


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Вход в админ-панель."""
    if not UserModel.is_admin(message.from_user.id):
        await message.answer("❌ У вас нет прав администратора")
        return
    
    from src.keyboards.admin import get_admin_main_keyboard
    await message.answer(
        "⚙️ *АДМИН-ПАНЕЛЬ*",
        parse_mode="Markdown",
        reply_markup=get_admin_main_keyboard()
    )


@router.callback_query(F.data == "menu")
async def menu_cb(callback: CallbackQuery, state: FSMContext):
    """Возврат в главное меню."""
    await state.clear()
    await callback.message.edit_text(
        "👋 *Главное меню*",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    await callback.answer()


@router.callback_query(F.data == "contact_master")
async def contact_master(callback: CallbackQuery, state: FSMContext):
    """Связь с мастером."""
    await state.set_state("waiting_contact_message")
    await callback.message.edit_text(
        "📞 *СВЯЗЬ С МАСТЕРОМ*\n\n"
        "Напишите ваш вопрос или запрос, и я передам его мастеру.\n"
        "Ответ придёт в течение 24 часов.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← ОТМЕНА", callback_data="menu")]
        ])
    )
    await callback.answer()


@router.message(F.text, F.chat.func(lambda chat: True))
async def contact_message_received(message: Message, state: FSMContext, bot):
    """Получение сообщения для мастера."""
    current_state = await state.get_state()
    if current_state != "waiting_contact_message":
        return
    
    user_id = message.from_user.id
    user = UserModel.get(user_id)
    name = user['first_name'] or user['username'] or str(user_id)
    
    await bot.send_message(
        Config.ADMIN_ID,
        f"📞 *СООБЩЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ*\n\n"
        f"👤 {name} (@{user['username']})\n"
        f"🆔 {user_id}\n\n"
        f"{message.text}"
    )
    await state.clear()
    await message.answer(
        "✅ Сообщение отправлено мастеру. Ожидайте ответа.",
        reply_markup=get_main_keyboard()
    )


@router.callback_query(F.data == "referral")
async def referral_info(callback: CallbackQuery):
    """Информация о реферальной программе."""
    user_id = callback.from_user.id
    bot_username = (await callback.bot.get_me()).username
    ref_link = f"https://t.me/{bot_username}?start=ref{user_id}"
    
    with db.cursor() as c:
        c.execute("SELECT balance, total_earned, referral_count FROM referral_balance WHERE user_id = ?", (user_id,))
        row = c.fetchone()
    
    if row:
        balance = row['balance']
        total_earned = row['total_earned']
        referral_count = row['referral_count']
    else:
        balance = total_earned = referral_count = 0
    
    text = (
        "🤝 *РЕФЕРАЛЬНАЯ ПРОГРАММА*\n\n"
        f"💰 *Ваш баланс:* {balance} бонусов\n"
        f"📊 *Всего заработано:* {total_earned} бонусов\n"
        f"👥 *Приглашено друзей:* {referral_count}\n\n"
        f"🔗 *Ваша реферальная ссылка:*\n`{ref_link}`\n\n"
        "За каждого приглашённого друга вы получаете 100 бонусов!"
    )
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="menu")]
        ])
    )
    await callback.answer()
