"""
Админ-панель: управление рассылками.
"""
import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel
from src.services.broadcast_manager import BroadcastManager
from src.utils.helpers import split_long_message

logger = logging.getLogger(__name__)
router = Router()


class BroadcastStates(StatesGroup):
    waiting_text = State()
    waiting_buttons = State()
    waiting_button_text = State()
    waiting_button_url = State()
    waiting_audience = State()
    waiting_confirm = State()


@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery):
    """Главное меню рассылок."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    # Получаем историю рассылок
    with db.cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM broadcasts")
        total = c.fetchone()['cnt']
    
    text = (
        f"📢 *УПРАВЛЕНИЕ РАССЫЛКАМИ*\n\n"
        f"📊 *Статистика:*\n"
        f"• Всего рассылок: {total}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📝 СОЗДАТЬ РАССЫЛКУ", callback_data="broadcast_create")],
        [InlineKeyboardButton(text="📊 ИСТОРИЯ РАССЫЛОК", callback_data="broadcast_history")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "broadcast_history")
async def broadcast_history(callback: CallbackQuery):
    """История рассылок."""
    with db.cursor() as c:
        c.execute("SELECT * FROM broadcasts ORDER BY created_at DESC LIMIT 10")
        history = [dict(row) for row in c.fetchall()]
    
    if not history:
        await callback.message.edit_text(
            "📭 История рассылок пуста.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_broadcast")]
            ])
        )
        await callback.answer()
        return
    
    text = "📊 *ИСТОРИЯ РАССЫЛОК*\n\n"
    for b in history:
        date = b['created_at'][:16] if b['created_at'] else ""
        preview = b['broadcast_text'][:50] + "..." if len(b['broadcast_text']) > 50 else b['broadcast_text']
        text += f"• {date}\n  {preview}\n  ✅ {b['sent_count']} | ❌ {b['failed_count']} | 🚫 {b['blocked_count']} | Всего: {b['total_count']}\n\n"
    
    if len(text) > 3500:
        parts = split_long_message(text)
        for part in parts:
            await callback.message.answer(part)
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_broadcast")]
            ])
        )
    else:
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_broadcast")]
            ])
        )
    await callback.answer()


@router.callback_query(F.data == "broadcast_create")
async def broadcast_create(callback: CallbackQuery, state: FSMContext):
    """Начать создание рассылки."""
    await state.set_state(BroadcastStates.waiting_text)
    await callback.message.edit_text(
        "📝 *СОЗДАНИЕ РАССЫЛКИ*\n\n"
        "Введите текст сообщения для рассылки.\n"
        "Можно использовать Markdown (*жирный*, _курсив_ и т.д.)\n\n"
        "Для отмены введите /cancel"
    )
    await callback.answer()


@router.message(BroadcastStates.waiting_text)
async def broadcast_text_received(message: Message, state: FSMContext):
    """Получен текст рассылки."""
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "❌ Создание рассылки отменено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 В РАССЫЛКИ", callback_data="admin_broadcast")]
            ])
        )
        return
    
    await state.update_data(broadcast_text=message.text, parse_mode="Markdown")
    await state.set_state(BroadcastStates.waiting_buttons)
    
    await message.answer(
        "🔘 *ДОБАВЛЕНИЕ КНОПОК*\n\n"
        "Хотите добавить кнопки под сообщением?\n\n"
        "• Если да, отправьте текст кнопки\n"
        "• Если нет, отправьте /skip\n"
        "• Для отмены /cancel"
    )


@router.message(BroadcastStates.waiting_buttons)
async def broadcast_buttons(message: Message, state: FSMContext):
    """Обработка добавления кнопок."""
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "❌ Создание рассылки отменено.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 В РАССЫЛКИ", callback_data="admin_broadcast")]
            ])
        )
        return
    
    if message.text == "/skip":
        await state.update_data(reply_markup=None)
        await state.set_state(BroadcastStates.waiting_audience)
        await show_audience_selection(message, state)
        return
    
    await state.update_data(button_text=message.text)
    await state.set_state(BroadcastStates.waiting_button_url)
    
    await message.answer(
        "🔗 Введите URL для кнопки (или /skip, если не нужна ссылка):"
    )


@router.message(BroadcastStates.waiting_button_url)
async def broadcast_button_url(message: Message, state: FSMContext):
    """Получение URL для кнопки."""
    data = await state.get_data()
    button_text = data.get('button_text')
    
    if message.text == "/skip":
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, callback_data="noop")]]
        )
    else:
        reply_markup = InlineKeyboardMarkup(
            inline_keyboard=[[InlineKeyboardButton(text=button_text, url=message.text)]]
        )
    
    await state.update_data(reply_markup=reply_markup)
    await state.set_state(BroadcastStates.waiting_audience)
    await show_audience_selection(message, state)


async def show_audience_selection(message: Message, state: FSMContext):
    """Показать выбор аудитории."""
    # Получаем статистику по аудитории
    with db.cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM users")
        total_users = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM funnel_stats WHERE created_at > datetime('now', '-30 days')")
        active_users = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(*) as cnt FROM new_item_subscribers")
        subscribers = c.fetchone()['cnt']
        
        c.execute("SELECT COUNT(DISTINCT user_id) as cnt FROM orders WHERE status = 'paid'")
        buyers = c.fetchone()['cnt']
    
    text = (
        f"👥 *ВЫБОР АУДИТОРИИ*\n\n"
        f"📊 *Доступные сегменты:*\n"
        f"• Все пользователи: {total_users}\n"
        f"• Активные за 30 дней: {active_users}\n"
        f"• Подписанные на новинки: {subscribers}\n"
        f"• Купившие хотя бы раз: {buyers}\n\n"
        f"Выберите, кому отправить рассылку:"
    )
    
    buttons = [
        [InlineKeyboardButton(text=f"👥 ВСЕ ({total_users})", callback_data="audience_all")],
        [InlineKeyboardButton(text=f"🔥 АКТИВНЫЕ ({active_users})", callback_data="audience_active")],
        [InlineKeyboardButton(text=f"🔔 ПОДПИСЧИКИ НОВИНОК ({subscribers})", callback_data="audience_subscribers")],
        [InlineKeyboardButton(text=f"💰 КУПИВШИЕ ({buyers})", callback_data="audience_buyers")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_broadcast")]
    ]
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(BroadcastStates.waiting_audience, F.data.startswith("audience_"))
async def broadcast_audience(callback: CallbackQuery, state: FSMContext):
    """Выбор аудитории."""
    audience_type = callback.data.replace("audience_", "")
    
    if audience_type == "all":
        with db.cursor() as c:
            c.execute("SELECT user_id FROM users")
            user_ids = [row['user_id'] for row in c.fetchall()]
    elif audience_type == "active":
        with db.cursor() as c:
            c.execute("SELECT DISTINCT user_id FROM funnel_stats WHERE created_at > datetime('now', '-30 days')")
            user_ids = [row['user_id'] for row in c.fetchall()]
    elif audience_type == "subscribers":
        with db.cursor() as c:
            c.execute("SELECT user_id FROM new_item_subscribers")
            user_ids = [row['user_id'] for row in c.fetchall()]
    elif audience_type == "buyers":
        with db.cursor() as c:
            c.execute("SELECT DISTINCT user_id FROM orders WHERE status = 'paid'")
            user_ids = [row['user_id'] for row in c.fetchall()]
    else:
        await callback.answer("❌ Неизвестный тип аудитории")
        return
    
    if not user_ids:
        await callback.message.edit_text(
            "❌ В выбранной аудитории нет пользователей.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_broadcast")]
            ])
        )
        await callback.answer()
        await state.clear()
        return
    
    await state.update_data(audience=user_ids, audience_type=audience_type, total=len(user_ids))
    await state.set_state(BroadcastStates.waiting_confirm)
    
    # Показываем предпросмотр
    data = await state.get_data()
    text = data['broadcast_text']
    preview = text[:200] + "..." if len(text) > 200 else text
    
    await callback.message.edit_text(
        f"📨 *ПОДТВЕРЖДЕНИЕ РАССЫЛКИ*\n\n"
        f"👥 *Аудитория:* {audience_type}\n"
        f"👤 *Получателей:* {len(user_ids)}\n\n"
        f"📝 *Текст:*\n{preview}\n\n"
        f"✅ Подтвердите отправку.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ОТПРАВИТЬ", callback_data="broadcast_confirm")],
            [InlineKeyboardButton(text="❌ ОТМЕНИТЬ", callback_data="broadcast_cancel")]
        ])
    )
    await callback.answer()


@router.callback_query(BroadcastStates.waiting_confirm, F.data == "broadcast_confirm")
async def broadcast_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Подтверждение и запуск рассылки."""
    data = await state.get_data()
    user_ids = data['audience']
    text = data['broadcast_text']
    parse_mode = data.get('parse_mode', 'Markdown')
    reply_markup = data.get('reply_markup')
    
    await callback.message.edit_text(
        f"📤 *РАССЫЛКА НАЧАТА*\n\n"
        f"Всего получателей: {len(user_ids)}\n"
        f"Отправка может занять некоторое время...\n"
        f"Я буду сообщать о прогрессе."
    )
    await callback.answer()
    
    # Функция для обновления прогресса
    async def progress(current, total):
        if current % 50 == 0:
            await callback.message.edit_text(
                f"📤 *РАССЫЛКА В ПРОЦЕССЕ*\n\n"
                f"Отправлено: {current} из {total}\n"
                f"Прогресс: {current/total*100:.1f}%"
            )
    
    # Запускаем отправку
    sent = 0
    failed = 0
    blocked = 0
    total = len(user_ids)
    
    for i, user_id in enumerate(user_ids):
        try:
            await bot.send_message(user_id, text, parse_mode=parse_mode, reply_markup=reply_markup)
            sent += 1
        except Exception as e:
            error_str = str(e).lower()
            if "blocked" in error_str or "forbidden" in error_str:
                blocked += 1
            else:
                failed += 1
            logger.warning(f"Ошибка отправки пользователю {user_id}: {e}")
        
        if (i + 1) % 10 == 0:
            await progress(i + 1, total)
        
        await asyncio.sleep(0.04)  # задержка между сообщениями
    
    # Сохраняем статистику
    with db.cursor() as c:
        c.execute("""
            INSERT INTO broadcasts (broadcast_text, sent_count, failed_count, blocked_count, total_count, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (text[:500], sent, failed, blocked, total, datetime.now()))
    
    await state.clear()
    
    await callback.message.edit_text(
        f"✅ *РАССЫЛКА ЗАВЕРШЕНА*\n\n"
        f"📊 *Статистика:*\n"
        f"• Всего: {total}\n"
        f"• ✅ Доставлено: {sent}\n"
        f"• ❌ Ошибок: {failed}\n"
        f"• 🚫 Заблокировали бота: {blocked}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В РАССЫЛКИ", callback_data="admin_broadcast")]
        ])
    )


@router.callback_query(BroadcastStates.waiting_confirm, F.data == "broadcast_cancel")
async def broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена рассылки."""
    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В РАССЫЛКИ", callback_data="admin_broadcast")]
        ])
    )
    await callback.answer()