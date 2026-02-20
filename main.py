"""
═══════════════════════════════════════════════════════════════════════════
TELEGRAM БОТ - ПОЛНЫЙ ФУНКЦИОНАЛ ДЛЯ RENDER.COM

✅ ДОБАВЛЯТЬ КАТЕГОРИИ - через админ-панель
✅ ДОБАВЛЯТЬ КОНТЕНТ - через админ-панель
✅ ДОБАВЛЯТЬ ТРЕНИРОВКИ - через админ-панель
✅ ДОБАВЛЯТЬ МУЗЫКУ - через админ-панель
✅ ДОБАВЛЯТЬ УСЛУГИ - через админ-панель
✅ ДИАГНОСТИКА (загрузка фото) - через бот

ВСЁ БЕЗ КОДА! ТОЛЬКО АДМИН-ПАНЕЛЬ!
═══════════════════════════════════════════════════════════════════════════
"""

import asyncio
import logging
import os
import sqlite3
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime

from aiogram import F, types, Router, Dispatcher, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters import CommandStart, Command
from aiogram.types import FSInputFile

# ═══════════════════════════════════════════════════════════════════════════
# КОНФИГУРАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', '0')) if os.getenv('ADMIN_ID') else 0
PORT = int(os.getenv('PORT', 8000))

if not BOT_TOKEN:
    print("❌ ОШИБКА: BOT_TOKEN не установлен!")
    exit(1)

Path('storage').mkdir(exist_ok=True)
Path('storage/diagnostics').mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# БОТ И ДИСПЕТЧЕР
# ═══════════════════════════════════════════════════════════════════════════

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
main_router = Router()
admin_router = Router()
diag_router = Router()

# ═══════════════════════════════════════════════════════════════════════════
# БД
# ═══════════════════════════════════════════════════════════════════════════

DB = 'storage/beads.db'

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    # Пользователи
    c.execute('''CREATE TABLE IF NOT EXISTS users 
                 (user_id INT PRIMARY KEY, username TEXT, first_name TEXT, created_at TIMESTAMP)''')
    
    # Категории
    c.execute('''CREATE TABLE IF NOT EXISTS categories 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, emoji TEXT, desc TEXT)''')
    
    # Контент (текст в категориях)
    c.execute('''CREATE TABLE IF NOT EXISTS content 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, cat_id INT, title TEXT, desc TEXT, created_at TIMESTAMP)''')
    
    # Тренировки
    c.execute('''CREATE TABLE IF NOT EXISTS workouts 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, duration INT, difficulty TEXT, created_at TIMESTAMP)''')
    
    # Музыка
    c.execute('''CREATE TABLE IF NOT EXISTS music 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, duration INT, created_at TIMESTAMP)''')
    
    # Услуги
    c.execute('''CREATE TABLE IF NOT EXISTS services 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, desc TEXT, price REAL, created_at TIMESTAMP)''')
    
    # Диагностика (фото)
    c.execute('''CREATE TABLE IF NOT EXISTS diagnostics 
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INT, photo_count INT, notes TEXT, created_at TIMESTAMP, admin_result TEXT, sent BOOLEAN DEFAULT FALSE)''')
    
    # Админы
    c.execute('''CREATE TABLE IF NOT EXISTS admins (admin_id INT PRIMARY KEY)''')
    
    conn.commit()
    
    # Стандартные категории
    try:
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🏋️ Практики', '🏋️', 'Физические упражнения'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🎵 Музыка 432Hz', '🎵', 'Исцеляющая музыка'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('💎 Браслеты', '💎', 'Браслеты из камней'))
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", ('🩺 Диагностика', '🩺', 'Загрузка фото'))
        conn.commit()
    except:
        pass
    
    try:
        c.execute("INSERT INTO admins VALUES (?)", (ADMIN_ID,))
        conn.commit()
    except:
        pass
    
    conn.close()

init_db()

# ═══════════════════════════════════════════════════════════════════════════
# СОСТОЯНИЯ (для админ-панели)
# ═══════════════════════════════════════════════════════════════════════════

class AdminStates(StatesGroup):
    add_category = State()
    add_content = State()
    select_content_cat = State()
    add_workout = State()
    add_music = State()
    add_service = State()

class DiagnosticStates(StatesGroup):
    waiting_photo1 = State()
    waiting_photo2 = State()
    waiting_notes = State()

# ═══════════════════════════════════════════════════════════════════════════
# ФУНКЦИИ
# ═══════════════════════════════════════════════════════════════════════════

def is_admin(user_id):
    if user_id == ADMIN_ID:
        return True
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT admin_id FROM admins WHERE admin_id = ?', (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

async def get_categories_keyboard():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"cat_{cat[0]}")] for cat in cats]
    return types.InlineKeyboardMarkup(inline_keyboard=buttons)

async def admin_panel_keyboard():
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="📋 КАТЕГОРИИ", callback_data="admin_categories")],
        [types.InlineKeyboardButton(text="📝 КОНТЕНТ", callback_data="admin_content")],
        [types.InlineKeyboardButton(text="🏋️ ТРЕНИРОВКИ", callback_data="admin_workouts")],
        [types.InlineKeyboardButton(text="🎵 МУЗЫКА", callback_data="admin_music")],
        [types.InlineKeyboardButton(text="💼 УСЛУГИ", callback_data="admin_services")],
        [types.InlineKeyboardButton(text="🩺 ДИАГНОСТИКА", callback_data="admin_diagnostics")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ])

# ═══════════════════════════════════════════════════════════════════════════
# КОМАНДЫ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message(CommandStart())
async def start(msg: types.Message, state: FSMContext):
    await state.clear()
    
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?)', 
              (msg.from_user.id, msg.from_user.username, msg.from_user.first_name, datetime.now()))
    conn.commit()
    conn.close()
    
    if is_admin(msg.from_user.id):
        await msg.answer("👋 АДМИНИСТРАТОР!", reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="⚙️ АДМИН-ПАНЕЛЬ", callback_data="admin_panel")],
            [types.InlineKeyboardButton(text="👥 МЕНЮ", callback_data="menu")],
        ]))
    else:
        kb = await get_categories_keyboard()
        await msg.answer("👋 ДОБРО ПОЖАЛОВАТЬ!\n\nВыбери раздел:", reply_markup=kb)

@main_router.message(Command("admin"))
async def admin_cmd(msg: types.Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("❌ Нет прав!")
        return
    await msg.answer("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())

@main_router.message(Command("diagnostics"))
async def diag_cmd(msg: types.Message, state: FSMContext):
    await msg.answer("📸 Загрузи ПЕРВУЮ фотографию:")
    await state.set_state(DiagnosticStates.waiting_photo1)

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНЫЕ CALLBACK - НАВИГАЦИЯ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.callback_query(F.data == "admin_panel")
async def admin_panel_cb(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("⚙️ АДМИН-ПАНЕЛЬ", reply_markup=await admin_panel_keyboard())
    await cb.answer()

@main_router.callback_query(F.data == "menu")
async def menu_cb(cb: types.CallbackQuery):
    kb = await get_categories_keyboard()
    await cb.message.edit_text("Выбери раздел:", reply_markup=kb)
    await cb.answer()

@main_router.callback_query(F.data.startswith("cat_"))
async def show_category(cb: types.CallbackQuery):
    cat_id = int(cb.data.split("_")[1])
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM categories WHERE id = ?', (cat_id,))
    cat = c.fetchone()
    c.execute('SELECT title, desc FROM content WHERE cat_id = ?', (cat_id,))
    content = c.fetchall()
    conn.close()
    
    text = f"{cat[1]} {cat[0]}\n\n"
    if content:
        for item in content:
            text += f"📝 {item[0]}\n{item[1]}\n\n"
    else:
        text += "Контента нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="menu")],
    ]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - КАТЕГОРИИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_categories")
async def admin_categories(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, emoji FROM categories')
    cats = c.fetchall()
    conn.close()
    
    text = "📋 КАТЕГОРИИ:\n\n"
    for cat in cats:
        text += f"{cat[1]} {cat[0]}\n"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_cat")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_cat")
async def add_cat_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название новой категории:")
    await state.set_state(AdminStates.add_category)
    await cb.answer()

@admin_router.message(AdminStates.add_category)
async def add_cat_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO categories (name, emoji, desc) VALUES (?, ?, ?)", (name, '📌', 'Новая категория'))
        conn.commit()
        await msg.answer(f"✅ Категория '{name}' добавлена!")
        logger.info(f"Категория '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - КОНТЕНТ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_content")
async def admin_content(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT id, emoji, name FROM categories')
    cats = c.fetchall()
    conn.close()
    
    buttons = [[types.InlineKeyboardButton(text=f"{cat[1]} {cat[2]}", callback_data=f"content_cat_{cat[0]}")] for cat in cats]
    buttons.append([types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")])
    
    await cb.message.edit_text("Выбери категорию для добавления контента:", 
                              reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons))
    await cb.answer()

@admin_router.callback_query(F.data.startswith("content_cat_"))
async def select_content_category(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    cat_id = int(cb.data.split("_")[-1])
    await state.update_data(content_cat_id=cat_id)
    await cb.message.edit_text("Напиши название контента (заголовок):")
    await state.set_state(AdminStates.add_content)
    await cb.answer()

@admin_router.message(AdminStates.add_content)
async def add_content_title(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.update_data(content_title=msg.text)
    await msg.answer("Теперь напиши описание/текст для этого контента:")
    # Ждём следующего сообщения как описание

@admin_router.message(AdminStates.add_content)
async def add_content_desc(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    title = data.get('content_title')
    
    if not title:
        await msg.answer("Ошибка. Начни сначала: /admin → Контент")
        await state.clear()
        return
    
    cat_id = data['content_cat_id']
    desc = msg.text
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO content (cat_id, title, desc, created_at) VALUES (?, ?, ?, ?)",
                 (cat_id, title, desc, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Контент '{title}' добавлен!")
        logger.info(f"Контент '{title}' добавлен в категорию {cat_id}")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ТРЕНИРОВКИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_workouts")
async def admin_workouts(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM workouts')
    workouts = c.fetchall()
    conn.close()
    
    text = "🏋️ ТРЕНИРОВКИ:\n\n"
    if workouts:
        for w in workouts:
            text += f"• {w[0]}\n"
    else:
        text += "Тренировок нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_workout")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_workout")
async def add_workout_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название тренировки:")
    await state.set_state(AdminStates.add_workout)
    await cb.answer()

@admin_router.message(AdminStates.add_workout)
async def add_workout_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO workouts (name, desc, duration, difficulty, created_at) VALUES (?, ?, ?, ?, ?)",
                 (name, "Описание", 30, "Средняя", datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Тренировка '{name}' добавлена!")
        logger.info(f"Тренировка '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - МУЗЫКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_music")
async def admin_music(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name FROM music')
    tracks = c.fetchall()
    conn.close()
    
    text = "🎵 МУЗЫКА:\n\n"
    if tracks:
        for t in tracks:
            text += f"• {t[0]}\n"
    else:
        text += "Музыки нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_music")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_music")
async def add_music_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название музыки:")
    await state.set_state(AdminStates.add_music)
    await cb.answer()

@admin_router.message(AdminStates.add_music)
async def add_music_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO music (name, desc, duration, created_at) VALUES (?, ?, ?, ?)",
                 (name, "432 Hz музыка", 60, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Музыка '{name}' добавлена!")
        logger.info(f"Музыка '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - УСЛУГИ
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_services")
async def admin_services(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT name, price FROM services')
    services = c.fetchall()
    conn.close()
    
    text = "💼 УСЛУГИ:\n\n"
    if services:
        for s in services:
            text += f"• {s[0]} - {s[1]} руб\n"
    else:
        text += "Услуг нет"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="➕ ДОБАВИТЬ", callback_data="add_service")],
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

@admin_router.callback_query(F.data == "add_service")
async def add_service_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    await cb.message.edit_text("Напиши название услуги:")
    await state.set_state(AdminStates.add_service)
    await cb.answer()

@admin_router.message(AdminStates.add_service)
async def add_service_process(msg: types.Message, state: FSMContext):
    name = msg.text
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO services (name, desc, price, created_at) VALUES (?, ?, ?, ?)",
                 (name, "Описание услуги", 1000, datetime.now()))
        conn.commit()
        await msg.answer(f"✅ Услуга '{name}' добавлена!")
        logger.info(f"Услуга '{name}' добавлена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
    finally:
        conn.close()
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# АДМИН - ДИАГНОСТИКА
# ═══════════════════════════════════════════════════════════════════════════

@admin_router.callback_query(F.data == "admin_diagnostics")
async def admin_diagnostics(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        await cb.answer("❌ Нет прав!", show_alert=True)
        return
    
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM diagnostics WHERE sent = FALSE')
    count = c.fetchone()[0]
    conn.close()
    
    text = f"🩺 ДИАГНОСТИКА\n\nОжидающих проверки: {count}"
    
    await cb.message.edit_text(text, reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="← НАЗАД", callback_data="admin_panel")],
    ]))
    await cb.answer()

# ═══════════════════════════════════════════════════════════════════════════
# ДИАГНОСТИКА - ЗАГРУЗКА ФОТО
# ═══════════════════════════════════════════════════════════════════════════

@diag_router.message(DiagnosticStates.waiting_photo1)
async def diag_photo1(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo1=photo.file_id)
    await msg.answer("✅ Первая фото получена!\n\nТеперь загрузи ВТОРУЮ:")
    await state.set_state(DiagnosticStates.waiting_photo2)

@diag_router.message(DiagnosticStates.waiting_photo2)
async def diag_photo2(msg: types.Message, state: FSMContext):
    if not msg.photo:
        await msg.answer("❌ Отправь фотографию!")
        return
    
    photo = msg.photo[-1]
    await state.update_data(photo2=photo.file_id)
    await msg.answer("✅ Вторая фото получена!\n\nНапиши заметки (или 'пропустить'):")
    await state.set_state(DiagnosticStates.waiting_notes)

@diag_router.message(DiagnosticStates.waiting_notes)
async def diag_notes(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    user_id = msg.from_user.id
    notes = msg.text if msg.text.lower() != 'пропустить' else "Нет заметок"
    
    conn = get_db()
    c = conn.cursor()
    try:
        c.execute("INSERT INTO diagnostics (user_id, photo_count, notes, created_at) VALUES (?, ?, ?, ?)",
                 (user_id, 2, notes, datetime.now()))
        conn.commit()
        
        if ADMIN_ID and ADMIN_ID != 0:
            try:
                admin_msg = f"🩺 НОВАЯ ДИАГНОСТИКА!\n\nОт: {msg.from_user.first_name}\nЗаметки: {notes}"
                await bot.send_message(ADMIN_ID, admin_msg)
            except:
                pass
        
        await msg.answer("✅ СПАСИБО!\n\nДиагностика отправлена! Результаты в течение 24 часов! 💚")
        logger.info(f"Диагностика от {user_id} сохранена")
    except Exception as e:
        await msg.answer(f"❌ Ошибка: {e}")
        logger.error(f"Ошибка диагностики: {e}")
    finally:
        conn.close()
    
    await state.clear()

# ═══════════════════════════════════════════════════════════════════════════
# ОСТАЛЬНОЕ
# ═══════════════════════════════════════════════════════════════════════════

@main_router.message()
async def handle_any(msg: types.Message):
    await msg.answer("❓ Команды:\n/start - меню\n/admin - админ-панель\n/diagnostics - диагностика")

# ═══════════════════════════════════════════════════════════════════════════
# ВЕБХУК
# ═══════════════════════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════════════════════
# ГЛАВНАЯ
# ═══════════════════════════════════════════════════════════════════════════

async def main():
    print("\n" + "="*60)
    print("🚀 БОТ С ПОЛНЫМ ФУНКЦИОНАЛОМ ЗАПУСКАЕТСЯ")
    print("="*60 + "\n")
    
    dp.include_router(admin_router)
    dp.include_router(diag_router)
    dp.include_router(main_router)
    
    # Railway использует polling (не webhook)
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("✅ Polling активирован")
    
    print(f"✅ БОТ РАБОТАЕТ")
    print(f"📍 ПОЛНЫЙ ФУНКЦИОНАЛ ВКЛЮЧЁН")
    print("\n" + "="*60 + "\n")
    
    # Запуск polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 БОТ ОСТАНОВЛЕН")
    except Exception as e:
        logger.error(f"❌ ОШИБКА: {e}")
