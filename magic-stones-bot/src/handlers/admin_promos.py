"""
Админ-панель: управление промокодами.
"""
import logging
import random
import string
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta

from src.database.db import db
from src.database.models import UserModel, PromoModel
from src.utils.helpers import format_price

logger = logging.getLogger(__name__)
router = Router()


class AdminPromoStates(StatesGroup):
    # Создание
    promo_create_type = State()
    promo_create_discount = State()
    promo_create_max_uses = State()
    promo_create_expires = State()
    promo_create_description = State()
    promo_create_code = State()
    
    # Редактирование
    promo_edit_select = State()
    promo_edit_field = State()
    promo_edit_value = State()


@router.callback_query(F.data == "admin_promos")
async def admin_promos(callback: CallbackQuery):
    """Главное меню промокодов."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    promos = PromoModel.get_all()
    active = sum(1 for p in promos if p['active'])
    
    text = (
        f"🎟️ *УПРАВЛЕНИЕ ПРОМОКОДАМИ*\n\n"
        f"📊 *Статистика:*\n"
        f"• Всего промокодов: {len(promos)}\n"
        f"• Активных: {active}\n\n"
        f"Выберите действие:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📋 СПИСОК ПРОМОКОДОВ", callback_data="admin_promos_list")],
        [InlineKeyboardButton(text="➕ СОЗДАТЬ ПРОМОКОД", callback_data="admin_promo_create")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_promos_list")
async def admin_promos_list(callback: CallbackQuery):
    """Список промокодов."""
    promos = PromoModel.get_all()
    
    if not promos:
        await callback.message.edit_text(
            "📭 Промокодов пока нет.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ СОЗДАТЬ", callback_data="admin_promo_create")],
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_promos")]
            ])
        )
        await callback.answer()
        return
    
    text = "🎟️ *СПИСОК ПРОМОКОДОВ*\n\n"
    buttons = []
    
    for p in promos:
        status = "✅" if p['active'] else "❌"
        if p['expires_at'] and p['expires_at'] < datetime.now():
            status = "⌛"
        
        discount = f"{p['discount_pct']}%" if p['discount_pct'] else f"{p['discount_rub']}₽"
        uses = f"{p['used_count']}/{p['max_uses'] if p['max_uses'] else '∞'}"
        
        text += f"{status} `{p['code']}` — {discount} ({uses})\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {p['code']}",
            callback_data=f"admin_promo_view_{p['code']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_promos")])
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo_view_"))
async def admin_promo_view(callback: CallbackQuery):
    """Просмотр деталей промокода."""
    code = callback.data.replace("admin_promo_view_", "")
    promo = PromoModel.get_by_code(code)
    
    if not promo:
        await callback.answer("❌ Промокод не найден")
        return
    
    stats = PromoModel.get_usage_stats(code)
    
    status = "✅ Активен" if promo['active'] else "❌ Неактивен"
    if promo['expires_at'] and promo['expires_at'] < datetime.now():
        status = "⌛ Истёк"
    
    discount = f"{promo['discount_pct']}%" if promo['discount_pct'] else f"{promo['discount_rub']}₽"
    uses = f"{promo['used_count']} / {promo['max_uses'] if promo['max_uses'] else '∞'}"
    expires = promo['expires_at'][:10] if promo['expires_at'] else "Бессрочно"
    
    text = (
        f"🎟️ *ПРОМОКОД: {promo['code']}*\n\n"
        f"📊 *Статус:* {status}\n"
        f"💰 *Скидка:* {discount}\n"
        f"📅 *Срок действия:* {expires}\n"
        f"🔄 *Использований:* {uses}\n"
        f"📝 *Описание:* {promo.get('description', 'Нет')}\n\n"
        f"📈 *Статистика использования:*\n"
        f"• Всего использований: {stats['total_uses']}\n"
        f"• Уникальных пользователей: {stats['unique_users']}\n"
        f"• Выручка: {format_price(stats['total_revenue'] or 0)}\n"
    )
    
    if stats['recent_uses']:
        text += "\n*Последние использования:*\n"
        for use in stats['recent_uses'][:5]:
            user = use['first_name'] or use['username'] or f"ID{use['user_id']}"
            date = use['used_at'][:10] if use['used_at'] else ""
            text += f"• {user} — {format_price(use['total_price'])} ({date})\n"
    
    buttons = [
        [InlineKeyboardButton(text="✏️ РЕДАКТИРОВАТЬ", callback_data=f"admin_promo_edit_{code}")],
        [InlineKeyboardButton(text="❌ УДАЛИТЬ", callback_data=f"admin_promo_delete_{code}")],
        [InlineKeyboardButton(text="🔙 К СПИСКУ", callback_data="admin_promos_list")]
    ]
    
    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))
    await callback.answer()


@router.callback_query(F.data == "admin_promo_create")
async def admin_promo_create(callback: CallbackQuery, state: FSMContext):
    """Создание промокода."""
    await state.set_state(AdminPromoStates.promo_create_type)
    await callback.message.edit_text(
        "🎟️ *СОЗДАНИЕ ПРОМОКОДА*\n\n"
        "Выберите тип скидки:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Процент", callback_data="admin_promo_type_pct")],
            [InlineKeyboardButton(text="💰 Фиксированная сумма", callback_data="admin_promo_type_rub")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_promos")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo_type_"))
async def admin_promo_type(callback: CallbackQuery, state: FSMContext):
    promo_type = callback.data.replace("admin_promo_type_", "")
    await state.update_data(promo_type=promo_type)
    await state.set_state(AdminPromoStates.promo_create_discount)
    
    prompt = "Введите размер скидки (только число):" if promo_type == "pct" else "Введите сумму скидки в рублях:"
    await callback.message.edit_text(prompt)
    await callback.answer()


@router.message(AdminPromoStates.promo_create_discount)
async def admin_promo_discount(message: Message, state: FSMContext):
    try:
        discount = int(message.text)
        if discount <= 0:
            raise ValueError
    except:
        await message.answer("❌ Введите положительное число")
        return
    
    await state.update_data(discount=discount)
    await state.set_state(AdminPromoStates.promo_create_max_uses)
    await message.answer("🔄 Введите максимальное количество использований (0 для безлимита):")


@router.message(AdminPromoStates.promo_create_max_uses)
async def admin_promo_max_uses(message: Message, state: FSMContext):
    try:
        max_uses = int(message.text)
        if max_uses < 0:
            raise ValueError
    except:
        await message.answer("❌ Введите неотрицательное число")
        return
    
    await state.update_data(max_uses=max_uses)
    await state.set_state(AdminPromoStates.promo_create_expires)
    await message.answer("📅 Введите срок действия в днях (0 для бессрочного):")


@router.message(AdminPromoStates.promo_create_expires)
async def admin_promo_expires(message: Message, state: FSMContext):
    try:
        expires_days = int(message.text)
        if expires_days < 0:
            raise ValueError
    except:
        await message.answer("❌ Введите неотрицательное число")
        return
    
    await state.update_data(expires_days=expires_days)
    await state.set_state(AdminPromoStates.promo_create_description)
    await message.answer("📝 Введите описание промокода (или /skip):")


@router.message(AdminPromoStates.promo_create_description)
async def admin_promo_description(message: Message, state: FSMContext):
    description = message.text if message.text != "/skip" else ""
    await state.update_data(description=description)
    await state.set_state(AdminPromoStates.promo_create_code)
    
    await message.answer(
        "🔤 Введите код промокода (или /random для генерации):"
    )


@router.message(AdminPromoStates.promo_create_code)
async def admin_promo_code(message: Message, state: FSMContext):
    data = await state.get_data()
    
    if message.text == "/random":
        chars = string.ascii_uppercase + string.digits
        code = ''.join(random.choices(chars, k=8))
    else:
        code = message.text.strip().upper()
        if PromoModel.get_by_code(code):
            await message.answer("❌ Такой код уже существует. Введите другой или /random")
            return
    
    promo_id = PromoModel.create(
        code=code,
        discount_pct=data['discount'] if data['promo_type'] == 'pct' else 0,
        discount_rub=data['discount'] if data['promo_type'] == 'rub' else 0,
        max_uses=data['max_uses'],
        expires_days=data['expires_days'],
        description=data['description']
    )
    
    await state.clear()
    await message.answer(
        f"✅ *ПРОМОКОД СОЗДАН!*\n\nКод: `{code}`",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 К ПРОМОКОДАМ", callback_data="admin_promos_list")]
        ])
    )


@router.callback_query(F.data.startswith("admin_promo_edit_"))
async def admin_promo_edit(callback: CallbackQuery, state: FSMContext):
    """Редактирование промокода."""
    code = callback.data.replace("admin_promo_edit_", "")
    await state.update_data(edit_code=code)
    
    await callback.message.edit_text(
        f"✏️ *РЕДАКТИРОВАНИЕ ПРОМОКОДА {code}*\n\n"
        f"Что хотите изменить?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Статус", callback_data="admin_promo_edit_field_active")],
            [InlineKeyboardButton(text="💰 Скидку", callback_data="admin_promo_edit_field_discount")],
            [InlineKeyboardButton(text="🔄 Лимит", callback_data="admin_promo_edit_field_max_uses")],
            [InlineKeyboardButton(text="📅 Срок", callback_data="admin_promo_edit_field_expires")],
            [InlineKeyboardButton(text="📝 Описание", callback_data="admin_promo_edit_field_desc")],
            [InlineKeyboardButton(text="🔙 НАЗАД", callback_data=f"admin_promo_view_{code}")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo_edit_field_"))
async def admin_promo_edit_field(callback: CallbackQuery, state: FSMContext):
    field = callback.data.replace("admin_promo_edit_field_", "")
    await state.update_data(edit_field=field)
    await state.set_state(AdminPromoStates.promo_edit_value)
    
    prompts = {
        "active": "Введите 1 для активации или 0 для деактивации:",
        "discount": "Введите новый размер скидки (только число):",
        "max_uses": "Введите новый лимит использований (0 для безлимита):",
        "expires": "Введите новый срок действия в днях от сегодня (0 для бессрочного):",
        "desc": "Введите новое описание:"
    }
    
    await callback.message.edit_text(prompts.get(field, "Введите новое значение:"))
    await callback.answer()


@router.message(AdminPromoStates.promo_edit_value)
async def admin_promo_edit_save(message: Message, state: FSMContext, bot):
    data = await state.get_data()
    code = data['edit_code']
    field = data['edit_field']
    
    promo = PromoModel.get_by_code(code)
    if not promo:
        await message.answer("❌ Промокод не найден")
        await state.clear()
        return
    
    updates = {}
    
    try:
        if field == "active":
            val = int(message.text)
            updates['active'] = 1 if val == 1 else 0
        elif field == "discount":
            val = int(message.text)
            if promo['discount_pct']:
                updates['discount_pct'] = val
            else:
                updates['discount_rub'] = val
        elif field == "max_uses":
            val = int(message.text)
            updates['max_uses'] = val
        elif field == "expires":
            days = int(message.text)
            if days <= 0:
                updates['expires_at'] = None
            else:
                updates['expires_at'] = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
        elif field == "desc":
            updates['description'] = message.text
    except ValueError:
        await message.answer("❌ Некорректное значение")
        return
    
    success = PromoModel.update(code, **updates)
    await state.clear()
    
    if success:
        await message.answer(
            "✅ *Промокод обновлен!*",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К ПРОМОКОДУ", callback_data=f"admin_promo_view_{code}")]
            ])
        )
    else:
        await message.answer("❌ Ошибка при обновлении")


@router.callback_query(F.data.startswith("admin_promo_delete_"))
async def admin_promo_delete(callback: CallbackQuery):
    """Удаление промокода."""
    code = callback.data.replace("admin_promo_delete_", "")
    
    await callback.message.edit_text(
        f"⚠️ *ПОДТВЕРДИТЕ УДАЛЕНИЕ*\n\n"
        f"Удалить промокод {code}?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Да", callback_data=f"admin_promo_confirm_delete_{code}"),
                InlineKeyboardButton(text="❌ Нет", callback_data=f"admin_promo_view_{code}")
            ]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_promo_confirm_delete_"))
async def admin_promo_confirm_delete(callback: CallbackQuery):
    code = callback.data.replace("admin_promo_confirm_delete_", "")
    success = PromoModel.delete(code)
    
    if success:
        await callback.message.edit_text(
            "✅ *Промокод удален*",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 К ПРОМОКОДАМ", callback_data="admin_promos_list")]
            ])
        )
    else:
        await callback.message.edit_text(
            "❌ Ошибка при удалении",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_promos")]
            ])
        )
    await callback.answer()