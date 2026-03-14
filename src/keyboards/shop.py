"""
Клавиатуры для магазина (витрина, корзина, оплата).
"""
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict

from src.utils.helpers import format_price


def get_categories_keyboard(categories: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком категорий."""
    buttons = []
    for cat in categories:
        buttons.append([
            InlineKeyboardButton(
                text=f"{cat['emoji']} {cat['name']}",
                callback_data=f"category_{cat['id']}"
            )
        ])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_products_keyboard(products: List[Dict]) -> InlineKeyboardMarkup:
    """Клавиатура со списком товаров."""
    buttons = []
    for p in products:
        price = format_price(p['price']) if p['price'] else "Цена уточняется"
        btn_text = f"{p['name']} — {price}"
        if 'collection_name' in p:
            callback_data = f"product_{p['id'] + 100000}"
        else:
            callback_data = f"product_{p['id']}"
        buttons.append([InlineKeyboardButton(text=btn_text, callback_data=callback_data)])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="showcase")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_product_keyboard(product_id: int, purchasable: bool, in_cart: bool = False) -> InlineKeyboardMarkup:
    """Клавиатура для страницы товара."""
    buttons = []
    
    if purchasable:
        if in_cart:
            buttons.append([
                InlineKeyboardButton(text="✅ УЖЕ В КОРЗИНЕ", callback_data="noop"),
                InlineKeyboardButton(text="🛒 ПЕРЕЙТИ В КОРЗИНУ", callback_data="cart")
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text="➕ ДОБАВИТЬ В КОРЗИНУ", callback_data=f"add_to_cart_{product_id}")
            ])
    
    buttons.append([
        InlineKeyboardButton(text="← НАЗАД", callback_data="showcase"),
        InlineKeyboardButton(text="❤️ В ИЗБРАННОЕ", callback_data=f"wishlist_add_{product_id}")
    ])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_cart_keyboard(total: float) -> InlineKeyboardMarkup:
    """Клавиатура для корзины."""
    buttons = []
    
    if total > 0:
        buttons.append([InlineKeyboardButton(text="✅ ОФОРМИТЬ ЗАКАЗ", callback_data="checkout")])
    
    buttons.append([InlineKeyboardButton(text="🗑 ОЧИСТИТЬ КОРЗИНУ", callback_data="cart_clear")])
    buttons.append([InlineKeyboardButton(text="← ПРОДОЛЖИТЬ ПОКУПКИ", callback_data="showcase")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_payment_keyboard(amount: float, bonus_balance: float = 0) -> InlineKeyboardMarkup:
    """Клавиатура выбора оплаты."""
    buttons = []
    
    if amount > 0:
        stars_amount = max(1, int(amount))
        buttons.append([
            InlineKeyboardButton(text=f"⭐ Оплатить Stars ({stars_amount} ⭐)", callback_data="pay_stars")
        ])
        
        if bonus_balance >= amount:
            buttons.append([
                InlineKeyboardButton(text="💰 Оплатить бонусами", callback_data="pay_bonus")
            ])
        elif bonus_balance > 0:
            buttons.append([
                InlineKeyboardButton(text=f"💰 Частично бонусами ({format_price(bonus_balance)})", 
                                     callback_data="pay_partial_bonus")
            ])
    
    buttons.append([InlineKeyboardButton(text="📞 Связаться с мастером", callback_data="contact_master")])
    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="cart")])
    
    return InlineKeyboardMarkup(inline_keyboard=buttons)