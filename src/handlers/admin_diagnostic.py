"""
Админ-панель: управление диагностикой.
"""
import logging
from aiogram import Router, F, Bot
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database.db import db
from src.database.models import UserModel, DiagnosticModel, ServiceModel
from src.utils.helpers import format_datetime

logger = logging.getLogger(__name__)
router = Router()


class AdminDiagnosticStates(StatesGroup):
    waiting_result = State()
    waiting_service = State()
    waiting_comment = State()


@router.callback_query(F.data == "admin_diagnostics")
async def admin_diagnostics(callback: CallbackQuery):
    """Главное меню диагностики."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    pending = DiagnosticModel.get_pending()
    
    text = (
        f"🩺 *УПРАВЛЕНИЕ ДИАГНОСТИКОЙ*\n\n"
        f"📋 *Новых заявок:* {len(pending)}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📋 НОВЫЕ ЗАЯВКИ", callback_data="admin_diag_pending")],
        [InlineKeyboardButton(text="📋 ВСЕ ЗАЯВКИ", callback_data="admin_diag_all")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_diag_pending")
async def admin_diag_pending(callback: CallbackQuery):
    """Список новых заявок."""
    pending = DiagnosticModel.get_pending()
    
    if not pending:
        await callback.message.edit_text(
            "📭 Нет новых заявок.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_diagnostics")]
            ])
        )
        await callback.answer()
        return
    
    text = "📋 *НОВЫЕ ЗАЯВКИ НА ДИАГНОСТИКУ*\n\n"
    
    for d in pending:
        text += (
            f"───────────────\n"
            f"🆔 #{d['id']} | {d['first_name']} (@{d['username']})\n"
            f"📅 {format_datetime(d['created_at'])}\n"
            f"📸 Фото: {d['photo_count']} шт.\n"
            f"📝 {d['notes'][:50]}...\n"
            f"[👁️ ПРОСМОТРЕТЬ](дествие:diag_view_{d['id']})\n"
        )
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_diagnostics")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("diag_view_"))
async def admin_diag_view(callback: CallbackQuery, bot: Bot):
    """Просмотр деталей диагностики."""
    diag_id = int(callback.data.replace("diag_view_", ""))
    
    with db.cursor() as c:
        c.execute("""
            SELECT d.*, u.first_name, u.username, u.user_id
            FROM diagnostics d
            JOIN users u ON d.user_id = u.user_id
            WHERE d.id = ?
        """, (diag_id,))
        diag = c.fetchone()
    
    if not diag:
        await callback.answer("❌ Диагностика не найдена")
        return
    
    text = (
        f"🩺 *ДИАГНОСТИКА #{diag_id}*\n\n"
        f"👤 {diag['first_name']} (@{diag['username']})\n"
        f"🆔 {diag['user_id']}\n"
        f"📅 {format_datetime(diag['created_at'])}\n\n"
        f"📝 *ЗАМЕТКИ КЛИЕНТА:*\n{diag['notes']}\n\n"
    )
    
    if diag['admin_result']:
        text += f"📊 *РЕЗУЛЬТАТ:*\n{diag['admin_result']}\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 ВВЕСТИ РЕЗУЛЬТАТ", callback_data=f"diag_result_{diag_id}")],
        [InlineKeyboardButton(text="✨ НАЗНАЧИТЬ УСЛУГУ", callback_data=f"diag_service_{diag_id}")],
        [InlineKeyboardButton(text="✍️ НАПИСАТЬ КЛИЕНТУ", url=f"tg://user?id={diag['user_id']}")],
        [InlineKeyboardButton(text="🔙 К СПИСКУ", callback_data="admin_diag_pending")]
    ])
    
    await callback.message.edit_text(text, reply_markup=kb)
    
    # Отправляем фото отдельно
    if diag['photo1_file_id']:
        await bot.send_photo(callback.from_user.id, diag['photo1_file_id'], caption="📸 Фото 1")
    if diag['photo2_file_id']:
        await bot.send_photo(callback.from_user.id, diag['photo2_file_id'], caption="📸 Фото 2")
    
    await callback.answer()


@router.callback_query(F.data.startswith("diag_result_"))
async def admin_diag_result(callback: CallbackQuery, state: FSMContext):
    """Ввод результата диагностики."""
    diag_id = int(callback.data.replace("diag_result_", ""))
    await state.update_data(diag_id=diag_id)
    await state.set_state(AdminDiagnosticStates.waiting_result)
    
    await callback.message.edit_text(
        f"📝 *ВВЕДИТЕ РЕЗУЛЬТАТ ДИАГНОСТИКИ #{diag_id}*\n\n"
        f"Опишите результаты и рекомендации.\n"
        f"Это сообщение будет отправлено клиенту."
    )
    await callback.answer()


@router.message(AdminDiagnosticStates.waiting_result)
async def admin_diag_result_save(message: Message, state: FSMContext, bot: Bot):
    """Сохранение результата."""
    data = await state.get_data()
    diag_id = data['diag_id']
    result_text = message.text
    
    with db.cursor() as c:
        c.execute("SELECT user_id FROM diagnostics WHERE id = ?", (diag_id,))
        row = c.fetchone()
        if not row:
            await message.answer("❌ Диагностика не найдена")
            await state.clear()
            return
        user_id = row['user_id']
        
        c.execute("UPDATE diagnostics SET admin_result = ?, sent = 1 WHERE id = ?", (result_text, diag_id))
    
    await state.clear()
    
    # Отправляем клиенту
    await bot.send_message(
        user_id,
        f"🔮 *РЕЗУЛЬТАТ ВАШЕЙ ДИАГНОСТИКИ*\n\n{result_text}\n\n"
        f"Мастер готов предложить вам дальнейшие шаги. "
        f"Перейдите в раздел УСЛУГИ для записи.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✨ УСЛУГИ", callback_data="services")]
        ])
    )
    
    await message.answer("✅ Результат отправлен клиенту!")


@router.callback_query(F.data.startswith("diag_service_"))
async def admin_diag_service(callback: CallbackQuery, state: FSMContext):
    """Назначение услуги по результатам диагностики."""
    diag_id = int(callback.data.replace("diag_service_", ""))
    await state.update_data(diag_id=diag_id)
    
    services = ServiceModel.get_all(active_only=True)
    
    buttons = []
    for s in services:
        buttons.append([InlineKeyboardButton(
            text=f"{s['name']} — {s['price']}⭐",
            callback_data=f"diag_service_sel_{diag_id}_{s['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"diag_view_{diag_id}")])
    
    await callback.message.edit_text(
        "✨ *ВЫБЕРИТЕ УСЛУГУ ДЛЯ РЕКОМЕНДАЦИИ*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("diag_service_sel_"))
async def admin_diag_service_sel(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """Отправка рекомендации услуги клиенту."""
    parts = callback.data.split("_")
    diag_id = int(parts[3])
    service_id = int(parts[4])
    
    with db.cursor() as c:
        c.execute("SELECT user_id FROM diagnostics WHERE id = ?", (diag_id,))
        diag = c.fetchone()
        c.execute("SELECT name, price FROM services WHERE id = ?", (service_id,))
        service = c.fetchone()
    
    if not diag or not service:
        await callback.answer("❌ Ошибка")
        return
    
    user_id = diag['user_id']
    
    # Отправляем клиенту
    await bot.send_message(
        user_id,
        f"✨ *РЕКОМЕНДАЦИЯ ПО РЕЗУЛЬТАТАМ ДИАГНОСТИКИ*\n\n"
        f"Мастер рекомендует вам услугу:\n\n"
        f"*{service['name']}*\n"
        f"Стоимость: {service['price']}⭐\n\n"
        f"Хотите записаться?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📅 ЗАПИСАТЬСЯ", callback_data=f"service_{service_id}")],
            [InlineKeyboardButton(text="✍️ НАПИСАТЬ МАСТЕРУ", callback_data="contact_master")]
        ])
    )
    
    await callback.message.edit_text(
        f"✅ Рекомендация услуги отправлена клиенту.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К ДИАГНОСТИКЕ", callback_data=f"diag_view_{diag_id}")]
        ])
    )
    await callback.answer()