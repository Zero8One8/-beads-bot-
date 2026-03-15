"""
Админ-панель: управление контентом (база знаний, посты, истории).
"""
import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from src.database.models import UserModel
from src.utils.text_loader import ContentLoader

logger = logging.getLogger(__name__)
router = Router()


class PostStates(StatesGroup):
    waiting_post_title = State()
    waiting_post_content = State()


# ──────────────────────────────────────────────────────────────
# ГЛАВНОЕ МЕНЮ КОНТЕНТА
# ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_content")
async def admin_content(callback: CallbackQuery):
    """Главное меню управления контентом."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    stones = ContentLoader.load_all_stones()
    posts = ContentLoader.list_posts()

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


# ──────────────────────────────────────────────────────────────
# ПОСТЫ
# ──────────────────────────────────────────────────────────────

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
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="➕ ДОБАВИТЬ ПОСТ", callback_data="admin_post_add")],
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")]
            ])
        )
        await callback.answer()
        return

    text = f"📝 *ГОТОВЫЕ ПОСТЫ* — всего {len(posts)}\n\n"
    buttons = []

    for post in posts[:15]:
        buttons.append([InlineKeyboardButton(
            text=f"📄 {post}",
            callback_data=f"admin_post_view_{post}"
        )])

    buttons.append([InlineKeyboardButton(text="➕ ДОБАВИТЬ ПОСТ", callback_data="admin_post_add")])
    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")])

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_post_view_"))
async def admin_post_view(callback: CallbackQuery):
    """Просмотр конкретного поста."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    post_id = callback.data.replace("admin_post_view_", "")
    content = ContentLoader.load_post(post_id)

    if not content:
        await callback.answer("❌ Пост не найден", show_alert=True)
        return

    # Обрезаем если слишком длинный для превью
    preview = content[:800] + ("..." if len(content) > 800 else "")

    text = (
        f"📄 *ПОСТ: {post_id}*\n\n"
        f"{preview}"
    )

    buttons = [
        [InlineKeyboardButton(text="🗑 УДАЛИТЬ ПОСТ", callback_data=f"admin_post_delete_{post_id}")],
        [InlineKeyboardButton(text="🔙 К ПОСТАМ", callback_data="admin_posts")]
    ]

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_post_delete_"))
async def admin_post_delete_confirm(callback: CallbackQuery):
    """Подтверждение удаления поста."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    post_id = callback.data.replace("admin_post_delete_", "")

    await callback.message.edit_text(
        f"⚠️ *УДАЛЕНИЕ ПОСТА*\n\n"
        f"Вы уверены, что хотите удалить пост `{post_id}`?\n"
        f"Это действие нельзя отменить.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ ДА, УДАЛИТЬ", callback_data=f"admin_post_delete_ok_{post_id}")],
            [InlineKeyboardButton(text="❌ ОТМЕНА", callback_data=f"admin_post_view_{post_id}")]
        ])
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_post_delete_ok_"))
async def admin_post_delete_do(callback: CallbackQuery):
    """Удаление поста."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    post_id = callback.data.replace("admin_post_delete_ok_", "")

    from src.config import Config
    file_path = Config.POSTS_PATH / f"{post_id}.txt"

    if file_path.exists():
        file_path.unlink()
        ContentLoader.clear_cache()
        await callback.answer("✅ Пост удалён", show_alert=True)
    else:
        await callback.answer("❌ Файл не найден", show_alert=True)

    # Возвращаемся к списку
    await admin_posts(callback)


@router.callback_query(F.data == "admin_post_add")
async def admin_post_add(callback: CallbackQuery, state: FSMContext):
    """Начало добавления поста."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    await state.set_state(PostStates.waiting_post_title)
    await callback.message.edit_text(
        "➕ *ДОБАВЛЕНИЕ ПОСТА*\n\n"
        "Введите ID (имя файла) поста — латиницей без пробелов:\n"
        "Например: `monday_amethyst` или `week_promo`",
        parse_mode="Markdown"
    )
    await callback.answer()


@router.message(PostStates.waiting_post_title)
async def post_title_received(message: Message, state: FSMContext):
    post_id = message.text.strip().lower()

    if not post_id.replace('_', '').isalnum():
        await message.answer("❌ Только латиница, цифры и нижнее подчеркивание. Попробуйте ещё:")
        return

    from src.config import Config
    if (Config.POSTS_PATH / f"{post_id}.txt").exists():
        await message.answer(f"❌ Пост `{post_id}` уже существует. Введите другой ID:")
        return

    await state.update_data(post_id=post_id)
    await state.set_state(PostStates.waiting_post_content)
    await message.answer(
        f"✅ ID: `{post_id}`\n\n"
        f"Теперь введите текст поста (Markdown поддерживается):",
        parse_mode="Markdown"
    )


@router.message(PostStates.waiting_post_content)
async def post_content_received(message: Message, state: FSMContext):
    data = await state.get_data()
    post_id = data['post_id']

    from src.config import Config
    file_path = Config.POSTS_PATH / f"{post_id}.txt"
    file_path.write_text(message.text, encoding='utf-8')
    ContentLoader.clear_cache()

    await state.clear()
    await message.answer(
        f"✅ *Пост `{post_id}` сохранён!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 К ПОСТАМ", callback_data="admin_posts")]
        ])
    )


# ──────────────────────────────────────────────────────────────
# ИСТОРИИ
# ──────────────────────────────────────────────────────────────

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
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")]
            ])
        )
        await callback.answer()
        return

    text = f"📖 *ИСТОРИИ НА МОДЕРАЦИЮ* — {len(stories)} шт.\n\n"
    buttons = []

    for story in stories[:10]:
        name = story.get('first_name') or story.get('username') or f"ID{story['user_id']}"
        date = str(story.get('created_at', ''))[:10]
        text += f"• {name} — {date}\n"
        buttons.append([InlineKeyboardButton(
            text=f"📖 История #{story['id']} — {name}",
            callback_data=f"admin_story_view_{story['id']}"
        )])

    buttons.append([InlineKeyboardButton(text="🔙 НАЗАД", callback_data="admin_content")])

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_story_view_"))
async def admin_story_view(callback: CallbackQuery):
    """Просмотр конкретной истории."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    story_id = int(callback.data.replace("admin_story_view_", ""))

    from src.database.models import StoryModel
    stories = StoryModel.get_pending()
    story = next((s for s in stories if s['id'] == story_id), None)

    if not story:
        await callback.answer("❌ История не найдена (возможно, уже обработана)", show_alert=True)
        await admin_stories(callback)
        return

    name = story.get('first_name') or story.get('username') or f"ID{story['user_id']}"
    date = str(story.get('created_at', ''))[:16]

    text = (
        f"📖 *ИСТОРИЯ #{story_id}*\n"
        f"👤 Автор: {name}\n"
        f"📅 Дата: {date}\n\n"
        f"{story.get('story_text', '—')}"
    )

    buttons = [
        [
            InlineKeyboardButton(text="✅ ОДОБРИТЬ", callback_data=f"admin_story_approve_{story_id}"),
            InlineKeyboardButton(text="❌ ОТКЛОНИТЬ", callback_data=f"admin_story_reject_{story_id}")
        ],
        [InlineKeyboardButton(text="🔙 К ИСТОРИЯМ", callback_data="admin_stories")]
    ]

    # Если есть фото — отправляем отдельно
    if story.get('photo_file_id'):
        await callback.message.answer_photo(
            photo=story['photo_file_id'],
            caption=f"📸 Фото к истории #{story_id}"
        )

    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_story_approve_"))
async def admin_story_approve(callback: CallbackQuery):
    """Одобрить историю."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    story_id = int(callback.data.replace("admin_story_approve_", ""))

    from src.database.models import StoryModel
    ok = StoryModel.approve(story_id)

    if ok:
        await callback.answer("✅ История одобрена и опубликована!", show_alert=True)
    else:
        await callback.answer("❌ Не удалось одобрить историю", show_alert=True)

    await admin_stories(callback)


@router.callback_query(F.data.startswith("admin_story_reject_"))
async def admin_story_reject(callback: CallbackQuery):
    """Отклонить историю."""
    if not UserModel.is_admin(callback.from_user.id):
        await callback.answer("❌ Нет прав")
        return

    story_id = int(callback.data.replace("admin_story_reject_", ""))

    from src.database.models import StoryModel
    ok = StoryModel.reject(story_id)

    if ok:
        await callback.answer("🗑 История отклонена и удалена", show_alert=True)
    else:
        await callback.answer("❌ Не удалось удалить историю", show_alert=True)

    await admin_stories(callback)
