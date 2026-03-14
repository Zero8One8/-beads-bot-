"""
Админ-панель: управление закрытым клубом 'Портал силы'.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import UserModel, ClubModel
from src.utils.text_loader import ContentLoader
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class AdminClubStates(StatesGroup):
    editing_info = State()
    extending_user = State()
    extending_days = State()


@router.callback_query(F.data == "admin_club")
async def admin_club(callback: CallbackQuery):
    """Главное меню управления клубом."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    with db.cursor() as c:
        c.execute("SELECT COUNT(*) FROM club_subscriptions WHERE status = 'active'")
        active = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM club_subscriptions WHERE status = 'trial'")
        trial = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM club_subscriptions WHERE status = 'expired'")
        expired = c.fetchone()[0]
    
    text = (
        f"🔮 *УПРАВЛЕНИЕ КЛУБОМ 'ПОРТАЛ СИЛЫ'*\n\n"
        f"📊 *Статистика:*\n"
        f"• Активных подписок: {active}\n"
        f"• Пробных: {trial}\n"
        f"• Истекших: {expired}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📋 СПИСОК ПОДПИСЧИКОВ", callback_data="admin_club_list")],
        [InlineKeyboardButton(text="📝 РЕДАКТИРОВАТЬ ОПИСАНИЕ", callback_data="admin_club_edit_info")],
        [InlineKeyboardButton(text="📚 УПРАВЛЕНИЕ КОНТЕНТОМ", callback_data="admin_club_content")],
        [InlineKeyboardButton(text="➕ ПРОДЛИТЬ ПОДПИСКУ", callback_data="admin_club_extend")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_club_list")
async def admin_club_list(callback: CallbackQuery):
    """Список подписчиков."""
    with db.cursor() as c:
        c.execute("""
            SELECT cs.*, u.first_name, u.username
            FROM club_subscriptions cs
            JOIN users u ON cs.user_id = u.user_id
            ORDER BY cs.created_at DESC
            LIMIT 50
        """)
        subs = [dict(row) for row in c.fetchall()]
    
    if not subs:
        await callback.message.edit_text(
            "📭 Нет подписчиков.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_club")]
            ])
        )
        await callback.answer()
        return
    
    text = "📋 *ПОДПИСЧИКИ КЛУБА*\n\n"
    buttons = []
    
    for s in subs:
        status_emoji = {
            'active': '✅',
            'trial': '🆓',
            'expired': '⌛'
        }.get(s['status'], '❓')
        
        name = s['first_name'] or s['username'] or str(s['user_id'])
        text += f"{status_emoji} {name} (ID: {s['user_id']})\n"
        buttons.append([InlineKeyboardButton(
            text=f"👤 {name[:20]}",
            callback_data=f"admin_club_user_{s['user_id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_club")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_club_user_"))
async def admin_club_user(callback: CallbackQuery):
    """Детали подписчика."""
    user_id = int(callback.data.replace("admin_club_user_", ""))
    sub = ClubModel.get_user_subscription(user_id)
    user = UserModel.get(user_id)
    
    if not sub:
        await callback.message.edit_text(
            f"👤 *Пользователь ID {user_id}*\n\nНет подписки.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ АКТИВИРОВАТЬ", callback_data=f"admin_club_activate_{user_id}")],
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_club_list")]
            ])
        )
        await callback.answer()
        return
    
    name = user['first_name'] or user['username'] or str(user_id)
    
    text = (
        f"👤 *Пользователь:* {name}\n"
        f"🆔 ID: {user_id}\n"
        f"📊 *Статус:* {sub['status']}\n"
    )
    
    if sub['trial_start']:
        text += f"📅 *Пробный начат:* {sub['trial_start'][:10]}\n"
    if sub['trial_end']:
        text += f"📅 *Пробный истекает:* {sub['trial_end'][:10]}\n"
    if sub['subscription_start']:
        text += f"📅 *Подписка с:* {sub['subscription_start'][:10]}\n"
    if sub['subscription_end']:
        text += f"📅 *Подписка до:* {sub['subscription_end'][:10]}\n"
    if sub['payment_id']:
        text += f"💳 *Платёж:* {sub['payment_id']}\n"
    
    buttons = [
        [InlineKeyboardButton(text="➕ ПРОДЛИТЬ", callback_data=f"admin_club_extend_{user_id}")],
        [InlineKeyboardButton(text="✍️ НАПИСАТЬ", url=f"tg://user?id={user_id}")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_club_list")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_club_extend_"))
async def admin_club_extend(callback: CallbackQuery, state: FSMContext):
    """Продление подписки (ручное)."""
    user_id = int(callback.data.replace("admin_club_extend_", ""))
    await state.update_data(extend_user_id=user_id)
    await state.set_state(AdminClubStates.extending_days)
    
    await callback.message.edit_text(
        "📅 Введите количество дней для продления:"
    )
    await callback.answer()


@router.message(AdminClubStates.extending_days)
async def admin_club_extend_days(message: Message, state: FSMContext, bot: Bot):
    try:
        days = int(message.text)
        if days <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное число")
        return
    
    data = await state.get_data()
    user_id = data['extend_user_id']
    
    # Получаем текущую подписку
    sub = ClubModel.get_user_subscription(user_id)
    now = datetime.now()
    
    if sub and sub['status'] in ['active', 'trial']:
        # Продлеваем существующую
        if sub['status'] == 'active' and sub['subscription_end']:
            current_end = datetime.fromisoformat(sub['subscription_end'])
            new_end = current_end + timedelta(days=days)
        else:
            new_end = now + timedelta(days=days)
    else:
        # Создаём новую
        new_end = now + timedelta(days=days)
    
    with db.cursor() as c:
        c.execute("""
            INSERT INTO club_subscriptions (user_id, status, subscription_start, subscription_end, created_at)
            VALUES (?, 'active', ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                status = 'active',
                subscription_start = ?,
                subscription_end = ?,
                updated_at = ?
        """, (user_id, now, new_end, now, now, new_end, now))
    
    await state.clear()
    
    # Уведомление пользователю
    await bot.send_message(
        user_id,
        f"🎉 *ВАША ПОДПИСКА ПРОДЛЕНА!*\n\n"
        f"Срок действия до {new_end.strftime('%d.%m.%Y')}\n"
        f"Спасибо, что остаётесь с нами!"
    )
    
    await message.answer(
        f"✅ Подписка пользователя {user_id} продлена до {new_end.strftime('%d.%m.%Y')}",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В КЛУБ", callback_data="admin_club")]
        ])
    )


@router.callback_query(F.data == "admin_club_edit_info")
async def admin_club_edit_info(callback: CallbackQuery, state: FSMContext):
    """Редактирование описания клуба."""
    info_path = Config.CONTENT_PATH / 'club_info.txt'
    if info_path.exists():
        current = info_path.read_text(encoding='utf-8')
    else:
        current = "Описание клуба (можно использовать Markdown)"
    
    await state.set_state(AdminClubStates.editing_info)
    await callback.message.edit_text(
        f"✏️ *РЕДАКТИРОВАНИЕ ОПИСАНИЯ КЛУБА*\n\n"
        f"Текущее описание:\n```\n{current[:500]}```\n\n"
        f"Отправьте новый текст (или /cancel):"
    )
    await callback.answer()


@router.message(AdminClubStates.editing_info)
async def admin_club_edit_info_save(message: Message, state: FSMContext):
    if message.text == "/cancel":
        await state.clear()
        await message.answer(
            "❌ Отменено",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 В КЛУБ", callback_data="admin_club")]
            ])
        )
        return
    
    info_path = Config.CONTENT_PATH / 'club_info.txt'
    info_path.write_text(message.text, encoding='utf-8')
    ContentLoader.clear_cache()
    
    await state.clear()
    await message.answer(
        "✅ Описание клуба обновлено!",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 В КЛУБ", callback_data="admin_club")]
        ])
    )


@router.callback_query(F.data == "admin_club_content")
async def admin_club_content(callback: CallbackQuery):
    """Управление контентом клуба."""
    items = ContentLoader.list_club_content()
    
    text = "📚 *УПРАВЛЕНИЕ КОНТЕНТОМ КЛУБА*\n\n"
    
    if items:
        text += "Существующие материалы:\n"
        for item in items:
            text += f"• {item['title']} (ID: {item['id']})\n"
    else:
        text += "Пока нет материалов.\n"
    
    text += "\nЧтобы добавить материал, загрузите файл в папку content/club/ на сервере.\n"
    text += "Формат: ID_название.txt (латиница, без пробелов)."
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 ОБНОВИТЬ СПИСОК", callback_data="admin_club_content")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_club")]
        ])
    )
    await callback.answer()