"""
Админ-панель: управление контентом (база знаний, посты, истории).
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from src.database.models import UserModel
from src.utils.text_loader import ContentLoader

logger = logging.getLogger(__name__)
router = Router()


@router.callback_query(F.data == "admin_content")
async def admin_content(callback: CallbackQuery):
    """Главное меню управления контентом."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    # Получаем статистику
    stones = ContentLoader.load_all_stones()
    posts = ContentLoader.list_posts()
    
    # Получаем количество историй на модерации
    from src.database.models import StoryModel
    pending_stories = len(StoryModel.get_pending())
    
    text = (
        "📚 *УПРАВЛЕНИЕ КОНТЕНТОМ*\n\n"
        f"📊 *Статистика:*\n"
        f"• Камней в базе: {len(stones)}\n"
        f"• Готовых постов: {len(posts)}\n"
        f"• Историй на модерации: {pending_stories}\n\n"
        f"Выберите раздел:"
    )
    
    buttons = [
        [InlineKeyboardButton(text="📚 База знаний (камни)", callback_data="admin_stones")],
        [InlineKeyboardButton(text="📝 Готовые посты", callback_data="admin_posts")],
        [InlineKeyboardButton(text="📖 Истории клиентов", callback_data="admin_stories")],
        [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_menu")]
    ]
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stones")
async def admin_stones(callback: CallbackQuery):
    """Список камней в базе знаний."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    stones = ContentLoader.load_all_stones()
    
    if not stones:
        await callback.message.edit_text(
            "📚 *БАЗА ЗНАНИЙ*\n\nВ базе пока нет камней.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")]
            ])
        )
        await callback.answer()
        return
    
    text = "📚 *БАЗА ЗНАНИЙ*\n\n"
    buttons = []
    
    for stone_id, stone_data in list(stones.items())[:20]:
        title = stone_data.get('TITLE', stone_id)
        emoji = stone_data.get('EMOJI', '💎')
        text += f"• {emoji} {title}\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {title[:20]}",
            callback_data=f"admin_stone_edit_{stone_id}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")])
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_posts")
async def admin_posts(callback: CallbackQuery):
    """Список готовых постов."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    posts = ContentLoader.list_posts()
    
    if not posts:
        await callback.message.edit_text(
            "📝 *ГОТОВЫЕ ПОСТЫ*\n\nНет готовых постов.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")]
            ])
        )
        await callback.answer()
        return
    
    text = "📝 *ГОТОВЫЕ ПОСТЫ*\n\n"
    buttons = []
    
    for post in posts[:10]:
        text += f"• {post}\n"
        buttons.append([InlineKeyboardButton(
            text=f"✏️ {post}",
            callback_data=f"admin_post_edit_{post}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")])
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data == "admin_stories")
async def admin_stories(callback: CallbackQuery):
    """Список историй на модерацию."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return
    
    from src.database.models import StoryModel
    stories = StoryModel.get_pending()
    
    if not stories:
        await callback.message.edit_text(
            "📖 *ИСТОРИИ КЛИЕНТОВ*\n\nНет историй на модерацию.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")]
            ])
        )
        await callback.answer()
        return
    
    text = "📖 *ИСТОРИИ НА МОДЕРАЦИЮ*\n\n"
    buttons = []
    
    for story in stories[:10]:
        name = story['first_name'] or story['username'] or f"ID{story['user_id']}"
        date = story['created_at'][:10] if story['created_at'] else ""
        text += f"• {name} — {date}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📖 История #{story['id']}",
            callback_data=f"admin_story_view_{story['id']}"
        )])
    
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")])
    
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()