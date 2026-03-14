"""
Избранное (Wishlist) - сохранение понравившихся товаров.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime

from src.database.models import WishlistModel, ItemInfo
from src.utils.helpers import format_price

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "wishlist")
async def wishlist_show(callback: CallbackQuery):
    """Показать избранное."""
    user_id = callback.from_user.id
    items = WishlistModel.get_all(user_id)
    
    if not items:
        await callback.message.edit_text(
            "❤️ *ИЗБРАННОЕ*\n\n"
            "У вас пока нет сохранённых товаров.\n"
            "Загляните в витрину и добавляйте понравившиеся!",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase")],
                [InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")]
            ])
        )
        await callback.answer()
        return
    
    text = "❤️ *ИЗБРАННОЕ*\n\n"
    buttons = []
    
    for item in items:
        price_str = format_price(item['price']) if item['price'] else "Цена уточняется"
        text += f"• *{item['name']}* — {price_str}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📦 {item['name']}",
            callback_data=f"product_{item['item_id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="💎 ВИТРИНА", callback_data="showcase")])
    buttons.append([InlineKeyboardButton(text="← В МЕНЮ", callback_data="menu")])
    
    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("wishlist_add_"))
async def wishlist_add(callback: CallbackQuery):
    """Добавить товар в избранное."""
    product_id = int(callback.data.replace("wishlist_add_", ""))
    user_id = callback.from_user.id
    
    success = WishlistModel.add(user_id, product_id)
    
    if success:
        await callback.answer("❤️ Добавлено в избранное!", show_alert=False)
    else:
        await callback.answer("❌ Ошибка при добавлении", show_alert=True)


@router.callback_query(F.data.startswith("wishlist_remove_"))
async def wishlist_remove(callback: CallbackQuery):
    """Удалить товар из избранного."""
    product_id = int(callback.data.replace("wishlist_remove_", ""))
    user_id = callback.from_user.id
    
    success = WishlistModel.remove(user_id, product_id)
    
    if success:
        await callback.answer("❌ Удалено из избранного", show_alert=False)
        # Обновляем отображение
        await wishlist_show(callback)
    else:
        await callback.answer("❌ Ошибка при удалении", show_alert=True)