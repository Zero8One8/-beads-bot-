"""
База знаний - просмотр камней из файлов knowledge_base.
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from src.utils.text_loader import ContentLoader

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "knowledge")
async def knowledge_list(callback: CallbackQuery):
    """Список всех камней в базе знаний."""
    stones = ContentLoader.load_all_stones()

    if not stones:
        await callback.message.edit_text(
            "📚 *БАЗА ЗНАНИЙ*\n\nБаза знаний пока пуста.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="← НАЗАД", callback_data="menu")]
            ])
        )
        await callback.answer()
        return

    text = f"📚 *БАЗА ЗНАНИЙ КАМНЕЙ*\n\nВ базе {len(stones)} камней. Выберите камень для подробного описания:\n"

    buttons = []
    for stone_id, data in list(stones.items())[:30]:
        title = data.get('TITLE', stone_id)
        emoji = data.get('EMOJI', '💎')
        buttons.append([InlineKeyboardButton(
            text=f"{emoji} {title}",
            callback_data=f"know_{stone_id}"
        )])

    if len(stones) > 30:
        text += f"\n_(показано 30 из {len(stones)})_"

    buttons.append([InlineKeyboardButton(text="← НАЗАД", callback_data="menu")])

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("know_"))
async def knowledge_stone(callback: CallbackQuery):
    """Подробное описание камня."""
    stone_id = callback.data.replace("know_", "")
    stone = ContentLoader.load_stone(stone_id)

    if not stone:
        await callback.answer("❌ Камень не найден", show_alert=True)
        return

    emoji = stone.get('EMOJI', '💎')
    title = stone.get('TITLE', stone_id)
    short_desc = stone.get('SHORT_DESC', '')
    full_desc = stone.get('FULL_DESC', '')
    properties = stone.get('PROPERTIES', '')
    chakra = stone.get('CHAKRA', '')
    zodiac = stone.get('ZODIAC', '')
    color = stone.get('COLOR', '')
    forms = stone.get('FORMS', '')
    price = stone.get('PRICE_PER_BEAD', '')
    notes = stone.get('NOTES', '')

    text = f"{emoji} *{title}*\n\n"

    if short_desc:
        text += f"_{short_desc}_\n\n"

    if full_desc:
        # Обрезаем если слишком длинное для одного сообщения
        if len(full_desc) > 2500:
            text += full_desc[:2500] + "...\n\n"
        else:
            text += full_desc + "\n\n"

    details = []
    if properties:
        details.append(f"✨ *Свойства:* {properties}")
    if chakra:
        details.append(f"🌀 *Чакры:* {chakra}")
    if zodiac:
        details.append(f"♈ *Зодиак:* {zodiac}")
    if color:
        details.append(f"🎨 *Цвет:* {color}")
    if forms:
        details.append(f"📏 *Размеры бусин:* {forms}")
    if price and str(price) != '0':
        details.append(f"💰 *Цена за бусину:* {price} руб.")
    if notes:
        details.append(f"📝 *Заметки:* {notes}")

    if details:
        text += "\n".join(details)

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="← К СПИСКУ", callback_data="knowledge")],
            [InlineKeyboardButton(text="← ГЛАВНОЕ МЕНЮ", callback_data="menu")]
        ])
    )
    await callback.answer()
