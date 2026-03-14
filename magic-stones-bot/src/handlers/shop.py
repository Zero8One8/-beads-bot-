"""
Хендлеры магазина: витрина, корзина, оформление заказа.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from src.database.models import (
    CategoryModel, ItemInfo, CartModel, OrderModel, 
    PromoModel, UserModel, ClubModel
)
from src.keyboards.shop import (
    get_categories_keyboard, get_products_keyboard, get_product_keyboard,
    get_cart_keyboard, get_payment_keyboard
)
from src.utils.helpers import format_price
from src.services.analytics import FunnelTracker
from src.services.notifications import AdminNotifier
from src.config import Config

logger = logging.getLogger(__name__)
router = Router()


class OrderStates(StatesGroup):
    waiting_promo = State()


@router.callback_query(F.data == "showcase")
async def showcase(callback: CallbackQuery):
    categories = CategoryModel.get_all()
    await callback.message.edit_text(
        "💎 *ВИТРИНА*\n\nВыберите категорию:",
        reply_markup=get_categories_keyboard(categories)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("category_"))
async def category_products(callback: CallbackQuery):
    category_id = int(callback.data.replace("category_", ""))
    products = CategoryModel.get_products(category_id)
    
    if not products:
        await callback.answer("❌ В этой категории пока нет товаров", show_alert=True)
        return
    
    from src.database.db import db
    with db.cursor() as c:
        c.execute("SELECT name, emoji FROM categories WHERE id = ?", (category_id,))
        cat = c.fetchone()
        cat_name = f"{cat['emoji']} {cat['name']}" if cat else "Товары"
    
    await callback.message.edit_text(
        f"📦 *{cat_name}*\n\nНайдено товаров: {len(products)}",
        reply_markup=get_products_keyboard(products)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("product_"))
async def product_detail(callback: CallbackQuery):
    product_id = int(callback.data.replace("product_", ""))
    name, price, _ = ItemInfo.get_info(product_id)
    
    with db.cursor() as c:
        if product_id >= 100000:
            real_id = product_id - 100000
            c.execute("SELECT description, image_file_id FROM showcase_items WHERE id = ?", (real_id,))
        else:
            c.execute("SELECT description, image_url as image_file_id FROM bracelets WHERE id = ?", (product_id,))
        row = c.fetchone()
        description = row['description'] if row else "Описание временно отсутствует"
    
    text = f"*{name}*\n\n💰 *Цена:* {format_price(price)}\n\n📝 *Описание:*\n{description}"
    
    # Проверяем, есть ли уже в корзине
    cart_items = CartModel.get_active(callback.from_user.id)
    in_cart = any(item['bracelet_id'] == product_id for item in cart_items)
    
    await callback.message.edit_text(
        text,
        reply_markup=get_product_keyboard(product_id, price > 0, in_cart),
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data.startswith("add_to_cart_"))
async def add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.replace("add_to_cart_", ""))
    user_id = callback.from_user.id
    
    name, price, _ = ItemInfo.get_info(product_id)
    
    if price <= 0:
        await callback.answer("❌ Этот товар нельзя добавить в корзину", show_alert=True)
        return
    
    success = CartModel.add(user_id, product_id)
    
    if success:
        await FunnelTracker.track(user_id, 'add_to_cart', f"product_{product_id}")
        _, items = CartModel.get_total(user_id)
        cart_count = len(items)
        
        await callback.answer(f"✅ Товар добавлен! В корзине {cart_count} товар(ов)", show_alert=False)
        
        # Обновляем кнопку
        await callback.message.edit_reply_markup(
            reply_markup=get_product_keyboard(product_id, True, in_cart=True)
        )
    else:
        await callback.answer("❌ Ошибка при добавлении", show_alert=True)


@router.callback_query(F.data == "cart")
async def show_cart(callback: CallbackQuery):
    user_id = callback.from_user.id
    total, items = CartModel.get_total(user_id)
    
    if not items:
        await callback.message.edit_text(
            "🛒 *КОРЗИНА ПУСТА*\n\nДобавьте товары из витрины!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase")],
                [InlineKeyboardButton(text="← ГЛАВНОЕ МЕНЮ", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "🛒 *ВАША КОРЗИНА*\n\n"
    for item in items:
        line_total = (item['price'] or 0) * item['quantity']
        text += f"• *{item['name']}*\n"
        text += f"  {item['quantity']} × {format_price(item['price'])} = {format_price(line_total)}\n"
        text += f"  [Удалить](дествие:remove_{item['id']})\n\n"
    
    text += f"*ИТОГО: {format_price(total)}*"
    
    await callback.message.edit_text(
        text,
        reply_markup=get_cart_keyboard(total),
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data.startswith("remove_"))
async def remove_from_cart(callback: CallbackQuery):
    cart_id = int(callback.data.replace("remove_", ""))
    success = CartModel.remove(cart_id)
    
    if success:
        await callback.answer("✅ Товар удален")
        await show_cart(callback)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)


@router.callback_query(F.data == "cart_clear")
async def clear_cart(callback: CallbackQuery):
    CartModel.clear(callback.from_user.id)
    await callback.answer("🗑 Корзина очищена", show_alert=True)
    await show_cart(callback)


@router.callback_query(F.data == "checkout")
async def checkout_start(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    total, items = CartModel.get_total(user_id)
    
    if not items:
        await callback.answer("❌ Корзина пуста", show_alert=True)
        return
    
    await FunnelTracker.track(user_id, 'checkout')
    await state.set_state(OrderStates.waiting_promo)
    
    await callback.message.edit_text(
        f"💳 *ОФОРМЛЕНИЕ ЗАКАЗА*\n\n"
        f"Сумма заказа: *{format_price(total)}*\n\n"
        f"Если у вас есть промокод, введите его сейчас.\n"
        f"Или отправьте /skip, чтобы продолжить без промокода.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← В КОРЗИНУ", callback_data="cart")]
        ])
    )
    await callback.answer()


@router.message(OrderStates.waiting_promo)
async def process_promo(message: Message, state: FSMContext):
    if message.text == "/skip":
        await state.update_data(promo_code=None, discount=0)
        await show_payment_methods(message, state)
        return
    
    promo_code = message.text.strip().upper()
    user_id = message.from_user.id
    
    result = PromoModel.check(promo_code, user_id)
    
    if not result['valid']:
        await message.answer(
            f"❌ {result['reason']}\n\nПопробуйте другой код или /skip для продолжения."
        )
        return
    
    total, _ = CartModel.get_total(user_id)
    discount = result.get('discount_rub', 0)
    if result.get('discount_pct'):
        discount = int(total * result['discount_pct'] / 100)
    
    await state.update_data(promo_code=promo_code, discount=discount)
    await message.answer(f"✅ Промокод принят! Скидка: {format_price(discount)}")
    await show_payment_methods(message, state)


async def show_payment_methods(message: Message, state: FSMContext):
    user_id = message.from_user.id
    data = await state.get_data()
    promo_code = data.get('promo_code')
    discount = data.get('discount', 0)
    
    total, _ = CartModel.get_total(user_id)
    final_total = max(0, total - discount)
    
    # Применяем скидку клуба, если есть подписка
    if ClubModel.has_access(user_id):
        club_discount = int(final_total * 0.2)
        final_total -= club_discount
        discount += club_discount
    
    bonus_balance = UserModel.get_bonus_balance(user_id)
    
    await message.answer(
        f"💳 *ВЫБЕРИТЕ СПОСОБ ОПЛАТЫ*\n\n"
        f"Сумма заказа: {format_price(total)}\n"
        f"Скидка: {format_price(discount)}\n"
        f"*К оплате: {format_price(final_total)}*\n\n"
        f"💰 Ваш бонусный баланс: {format_price(bonus_balance)}",
        reply_markup=get_payment_keyboard(final_total, bonus_balance)
    )
    
    await state.update_data(final_total=final_total, discount_total=discount)
    await state.set_state("waiting_payment")