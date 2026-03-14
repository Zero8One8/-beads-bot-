"""
Админ-панель: планировщик постов.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime

from src.database.db import db
from src.database.models import UserModel, ScheduledPostModel
from src.utils.text_loader import ContentLoader
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class SchedulerStates(StatesGroup):
    selecting_post = State()
    entering_datetime = State()
    confirming = State()


@router.callback_query(F.data == "admin_scheduler")
async def admin_scheduler(callback: CallbackQuery):
    """Главное меню планировщика."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    posts = ContentLoader.list_posts()
    
    with db.cursor() as c:
        c.execute("SELECT COUNT(*) as cnt FROM scheduled_posts WHERE status = 'pending'")
        pending = c.fetchone()['cnt']
        c.execute("SELECT COUNT(*) as cnt FROM scheduled_posts WHERE status = 'published'")
        published = c.fetchone()['cnt']
    
    text = (
        f"📅 *ПЛАНИРОВЩИК ПОСТОВ*\n\n"
        f"📁 *Доступно постов:* {len(posts)}\n"
        f"⏳ *Запланировано:* {pending}\n"
        f"✅ *Опубликовано:* {published}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="➕ ДОБАВИТЬ ПОСТ", callback_data="scheduler_add")],
        [InlineKeyboardButton(text="📋 СПИСАК ЗАПЛАНИРОВАННЫХ", callback_data="scheduler_list")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "scheduler_add")
async def scheduler_add(callback: CallbackQuery, state: FSMContext):
    """Добавление поста в расписание."""
    posts = ContentLoader.list_posts()
    
    if not posts:
        await callback.message.edit_text(
            "❌ Нет доступных постов. Сначала добавьте файлы в папку content/posts/",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_scheduler")]
            ])
        )
        await callback.answer()
        return
    
    await state.set_state(SchedulerStates.selecting_post)
    
    buttons = []
    for p in posts[:20]:
        buttons.append([InlineKeyboardButton(text=p, callback_data=f"scheduler_post_{p}")])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_scheduler")])
    
    await callback.message.edit_text(
        "📝 Выберите пост для публикации:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(SchedulerStates.selecting_post, F.data.startswith("scheduler_post_"))
async def scheduler_post_selected(callback: CallbackQuery, state: FSMContext):
    """Пост выбран, запрашиваем дату."""
    post_id = callback.data.replace("scheduler_post_", "")
    await state.update_data(post_id=post_id)
    await state.set_state(SchedulerStates.entering_datetime)
    
    await callback.message.edit_text(
        "📅 Введите дату и время публикации в формате:\n"
        "`2026-03-10 15:30`\n\n"
        "Или отправьте /now для публикации как можно скорее."
    )
    await callback.answer()


@router.message(SchedulerStates.entering_datetime)
async def scheduler_datetime(message: Message, state: FSMContext):
    """Обработка даты."""
    if message.text == "/now":
        dt = datetime.now().strftime('%Y-%m-%d %H:%M:00')
    else:
        try:
            dt = datetime.strptime(message.text, '%Y-%m-%d %H:%M')
            if dt < datetime.now():
                await message.answer("❌ Дата должна быть в будущем")
                return
            dt = dt.strftime('%Y-%m-%d %H:%M:00')
        except ValueError:
            await message.answer("❌ Неверный формат. Используйте ГГГГ-ММ-ДД ЧЧ:ММ")
            return
    
    await state.update_data(scheduled_time=dt)
    await state.set_state(SchedulerStates.confirming)
    
    data = await state.get_data()
    
    await message.answer(
        f"✅ *Подтвердите:*\n"
        f"Пост: `{data['post_id']}`\n"
        f"Время: {dt}\n\n"
        f"Отправить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Да", callback_data="scheduler_confirm"),
             InlineKeyboardButton(text="❌ Нет", callback_data="scheduler_cancel")]
        ])
    )


@router.callback_query(SchedulerStates.confirming, F.data == "scheduler_confirm")
async def scheduler_confirm(callback: CallbackQuery, state: FSMContext):
    """Подтверждение и сохранение."""
    data = await state.get_data()
    post_id = data['post_id']
    scheduled_time = data['scheduled_time']
    
    with db.cursor() as c:
        c.execute("""
            INSERT INTO scheduled_posts (post_id, channel_id, scheduled_time, created_at)
            VALUES (?, ?, ?, ?)
        """, (post_id, Config.CHANNEL_ID, scheduled_time, datetime.now()))
    
    await state.clear()
    await callback.message.edit_text(
        f"✅ Пост `{post_id}` запланирован на {scheduled_time}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В ПЛАНИРОВЩИК", callback_data="admin_scheduler")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data == "scheduler_cancel")
async def scheduler_cancel(callback: CallbackQuery, state: FSMContext):
    """Отмена."""
    await state.clear()
    await admin_scheduler(callback)


@router.callback_query(F.data == "scheduler_list")
async def scheduler_list(callback: CallbackQuery):
    """Список запланированных постов."""
    with db.cursor() as c:
        c.execute("""
            SELECT * FROM scheduled_posts 
            WHERE status = 'pending' 
            ORDER BY scheduled_time
        """)
        pending = [dict(row) for row in c.fetchall()]
        
        c.execute("""
            SELECT * FROM scheduled_posts 
            WHERE status = 'published' 
            ORDER BY scheduled_time DESC
            LIMIT 10
        """)
        published = [dict(row) for row in c.fetchall()]
    
    text = "📅 *ЗАПЛАНИРОВАННЫЕ ПОСТЫ*\n\n"
    
    if pending:
        for p in pending:
            text += f"• {p['post_id']} — {p['scheduled_time'][:16]}\n"
    else:
        text += "Нет запланированных постов.\n\n"
    
    text += "\n✅ *Последние опубликованные:*\n"
    if published:
        for p in published:
            text += f"• {p['post_id']} — {p['published_at'][:16] if p['published_at'] else p['scheduled_time'][:16]}\n"
    else:
        text += "Нет опубликованных постов."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_scheduler")]
        ])
    )
    await callback.answer()