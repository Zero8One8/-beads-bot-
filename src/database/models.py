"""
Модели данных (Data Access Objects).
Каждый класс отвечает за работу с одной таблицей.
"""
import json
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from src.database.db import db

class UserModel:
    """Работа с таблицей users."""
    
    TABLE = "users"
    
    @staticmethod
    def get(user_id: int) -> Optional[Dict[str, Any]]:
        with db.cursor() as c:
            c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def create_or_update(user_id: int, username: str, first_name: str, referred_by: Optional[int] = None) -> bool:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO users (user_id, username, first_name, created_at, referred_by) 
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name
            """, (user_id, username, first_name, datetime.now(), referred_by))
            return c.rowcount > 0
    
    @staticmethod
    def is_admin(user_id: int) -> bool:
        from src.config import Config
        if user_id == Config.ADMIN_ID:
            return True
        with db.cursor() as c:
            c.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
            return c.fetchone() is not None
    
    @staticmethod
    def set_birthday(user_id: int, birthday: str) -> bool:
        with db.cursor() as c:
            c.execute("UPDATE users SET birthday = ? WHERE user_id = ?", (birthday, user_id))
            return c.rowcount > 0
    
    @staticmethod
    def get_bonus_balance(user_id: int) -> float:
        with db.cursor() as c:
            c.execute("SELECT balance FROM referral_balance WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return float(row['balance']) if row else 0.0
    
    @staticmethod
    def get_all(limit: int = 1000) -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,))
            return [dict(row) for row in c.fetchall()]


class AdminModel:
    """Работа с таблицей admins."""
    
    @staticmethod
    def add(admin_id: int) -> bool:
        with db.cursor() as c:
            c.execute("INSERT OR IGNORE INTO admins (admin_id) VALUES (?)", (admin_id,))
            return c.rowcount > 0
    
    @staticmethod
    def remove(admin_id: int) -> bool:
        with db.cursor() as c:
            c.execute("DELETE FROM admins WHERE admin_id = ?", (admin_id,))
            return c.rowcount > 0
    
    @staticmethod
    def get_all() -> List[int]:
        with db.cursor() as c:
            c.execute("SELECT admin_id FROM admins")
            return [row['admin_id'] for row in c.fetchall()]


class CategoryModel:
    """Работа с категориями."""
    
    @staticmethod
    def get_all() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM categories ORDER BY id")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_id(category_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM categories WHERE id = ?", (category_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def create(name: str, emoji: str = "📦", description: str = "") -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO categories (name, emoji, description) VALUES (?, ?, ?)
            """, (name, emoji, description))
            return c.lastrowid
    
    @staticmethod
    def update(category_id: int, **kwargs) -> bool:
        allowed = ['name', 'emoji', 'description']
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(category_id)
        with db.cursor() as c:
            c.execute(f"UPDATE categories SET {', '.join(updates)} WHERE id = ?", params)
            return c.rowcount > 0
    
    @staticmethod
    def delete(category_id: int) -> bool:
        # Проверяем, есть ли товары в категории
        with db.cursor() as c:
            c.execute("SELECT COUNT(*) as cnt FROM bracelets WHERE category_id = ?", (category_id,))
            if c.fetchone()['cnt'] > 0:
                return False
            c.execute("DELETE FROM categories WHERE id = ?", (category_id,))
            return c.rowcount > 0
    
    @staticmethod
    def get_products(category_id: int) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT si.*, sc.name as collection_name
                FROM showcase_items si
                JOIN showcase_collections sc ON si.collection_id = sc.id
                WHERE sc.id = ?
                ORDER BY si.sort_order
            """, (category_id,))
            items = [dict(row) for row in c.fetchall()]
            if items:
                return items
            c.execute("""
                SELECT id, name, description, price, image_url as image_file_id
                FROM bracelets
                WHERE category_id = ?
                ORDER BY created_at DESC
            """, (category_id,))
            return [dict(row) for row in c.fetchall()]


class BraceletModel:
    """Работа с браслетами."""
    
    @staticmethod
    def get_by_id(item_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM bracelets WHERE id = ?", (item_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def get_all(category_id: Optional[int] = None) -> List[Dict]:
        with db.cursor() as c:
            if category_id:
                c.execute("SELECT * FROM bracelets WHERE category_id = ? ORDER BY created_at DESC", (category_id,))
            else:
                c.execute("SELECT * FROM bracelets ORDER BY created_at DESC LIMIT 50")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def create(name: str, price: float, category_id: int, description: str = "", image_url: str = "") -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO bracelets (name, description, price, image_url, category_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (name, description, price, image_url, category_id, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def update(bracelet_id: int, **kwargs) -> bool:
        allowed = ['name', 'description', 'price', 'image_url', 'category_id']
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(bracelet_id)
        with db.cursor() as c:
            c.execute(f"UPDATE bracelets SET {', '.join(updates)} WHERE id = ?", params)
            return c.rowcount > 0
    
    @staticmethod
    def delete(bracelet_id: int) -> bool:
        with db.cursor() as c:
            c.execute("SELECT COUNT(*) as cnt FROM order_items WHERE item_id = ?", (bracelet_id,))
            if c.fetchone()['cnt'] > 0:
                c.execute("UPDATE bracelets SET deleted = 1 WHERE id = ?", (bracelet_id,))
                return True
            c.execute("DELETE FROM bracelets WHERE id = ?", (bracelet_id,))
            return c.rowcount > 0


class ShowcaseCollectionModel:
    """Коллекции витрины."""
    
    @staticmethod
    def get_all() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM showcase_collections ORDER BY sort_order, id")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def create(name: str, emoji: str = "💎", description: str = "") -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO showcase_collections (name, emoji, description, created_at)
                VALUES (?, ?, ?, ?)
            """, (name, emoji, description, datetime.now()))
            return c.lastrowid


class ShowcaseItemModel:
    """Товары витрины."""
    
    @staticmethod
    def get_by_id(item_id: int) -> Optional[Dict]:
        real_id = item_id - 100000 if item_id >= 100000 else item_id
        with db.cursor() as c:
            c.execute("SELECT * FROM showcase_items WHERE id = ?", (real_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def get_all(collection_id: Optional[int] = None) -> List[Dict]:
        with db.cursor() as c:
            if collection_id:
                c.execute("SELECT * FROM showcase_items WHERE collection_id = ? ORDER BY sort_order", (collection_id,))
            else:
                c.execute("SELECT * FROM showcase_items ORDER BY created_at DESC LIMIT 50")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def create(collection_id: int, name: str, price: float, description: str = "", image_file_id: str = "", stars_price: int = 0) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO showcase_items (collection_id, name, description, price, stars_price, image_file_id, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (collection_id, name, description, price, stars_price, image_file_id, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def update(item_id: int, **kwargs) -> bool:
        allowed = ['name', 'description', 'price', 'stars_price', 'image_file_id', 'collection_id', 'sort_order']
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(item_id)
        with db.cursor() as c:
            c.execute(f"UPDATE showcase_items SET {', '.join(updates)} WHERE id = ?", params)
            return c.rowcount > 0
    
    @staticmethod
    def delete(item_id: int) -> bool:
        with db.cursor() as c:
            c.execute("DELETE FROM showcase_items WHERE id = ?", (item_id,))
            return c.rowcount > 0


class ItemInfo:
    """Получение информации о товаре по ID."""
    
    @staticmethod
    def get_info(item_id: int) -> Tuple[str, float, str]:
        if item_id >= 100000:
            real_id = item_id - 100000
            with db.cursor() as c:
                c.execute("SELECT name, price FROM showcase_items WHERE id = ?", (real_id,))
                row = c.fetchone()
                if row:
                    return row['name'], float(row['price'] or 0), 'showcase'
        else:
            with db.cursor() as c:
                c.execute("SELECT name, price FROM bracelets WHERE id = ?", (item_id,))
                row = c.fetchone()
                if row:
                    return row['name'], float(row['price'] or 0), 'bracelet'
        return f"Товар #{item_id}", 0.0, 'unknown'
    
    @staticmethod
    def format_price(price: float) -> str:
        return f"{price:.0f}₽" if price else "цена уточняется"
    
    @staticmethod
    def get_name(item_id: int) -> str:
        name, _, _ = ItemInfo.get_info(item_id)
        return name
    
    @staticmethod
    def get_price(item_id: int) -> float:
        _, price, _ = ItemInfo.get_info(item_id)
        return price


class CartModel:
    """Работа с корзиной."""
    
    @staticmethod
    def get_active(user_id: int) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT c.id, c.bracelet_id, c.quantity, 
                       b.name, b.price
                FROM cart c
                JOIN bracelets b ON c.bracelet_id = b.id
                WHERE c.user_id = ? AND c.status = 'active'
            """, (user_id,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def add(user_id: int, bracelet_id: int, quantity: int = 1) -> bool:
        if quantity <= 0:
            return False
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, quantity FROM cart 
                WHERE user_id = ? AND bracelet_id = ? AND status = 'active'
            """, (user_id, bracelet_id))
            existing = c.fetchone()
            if existing:
                new_qty = existing['quantity'] + quantity
                c.execute("UPDATE cart SET quantity = ? WHERE id = ?", (new_qty, existing['id']))
            else:
                c.execute("""
                    INSERT INTO cart (user_id, bracelet_id, quantity, added_at, status) 
                    VALUES (?, ?, ?, ?, 'active')
                """, (user_id, bracelet_id, quantity, datetime.now()))
            return True
    
    @staticmethod
    def remove(cart_id: int) -> bool:
        with db.cursor() as c:
            c.execute("DELETE FROM cart WHERE id = ?", (cart_id,))
            return c.rowcount > 0
    
    @staticmethod
    def clear(user_id: int) -> bool:
        with db.cursor() as c:
            c.execute("DELETE FROM cart WHERE user_id = ? AND status = 'active'", (user_id,))
            return True
    
    @staticmethod
    def get_total(user_id: int) -> Tuple[float, List[Dict]]:
        items = CartModel.get_active(user_id)
        total = sum((item['price'] or 0) * item['quantity'] for item in items)
        return total, items


class OrderModel:
    """Работа с заказами."""
    
    @staticmethod
    def create(user_id: int, total: float, payment_method: str, promo_code: str = None, bonus_used: float = 0) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO orders (user_id, total_price, status, payment_method, promo_code, bonus_used, created_at)
                VALUES (?, ?, 'pending', ?, ?, ?, ?)
            """, (user_id, total, payment_method, promo_code, bonus_used, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def add_item(order_id: int, user_id: int, item_id: int, item_name: str, quantity: int, price: float):
        item_type = 'showcase' if item_id >= 100000 else 'bracelet'
        real_id = item_id - 100000 if item_id >= 100000 else item_id
        with db.cursor() as c:
            c.execute("""
                INSERT INTO order_items (order_id, user_id, item_type, item_id, item_name, quantity, price, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (order_id, user_id, item_type, real_id, item_name, quantity, price, datetime.now()))
    
    @staticmethod
    def get_user_orders(user_id: int, limit: int = 10) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT id, total_price, status, payment_method, created_at
                FROM orders
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT ?
            """, (user_id, limit))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_id(order_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT o.*, u.first_name, u.username
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                WHERE o.id = ?
            """, (order_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def get_items(order_id: int) -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM order_items WHERE order_id = ?", (order_id,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def update_status(order_id: int, status: str) -> bool:
        with db.cursor() as c:
            c.execute("UPDATE orders SET status = ? WHERE id = ?", (status, order_id))
            return c.rowcount > 0
    
    @staticmethod
    def get_all(limit: int = 50, offset: int = 0, status: Optional[str] = None) -> List[Dict]:
        with db.cursor() as c:
            query = """
                SELECT o.*, u.first_name, u.username,
                       (SELECT COUNT(*) FROM order_items WHERE order_id = o.id) as items_count
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
            """
            params = []
            if status:
                query += " WHERE o.status = ?"
                params.append(status)
            query += " ORDER BY o.created_at DESC LIMIT ? OFFSET ?"
            params.extend([limit, offset])
            c.execute(query, params)
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_stats_by_status() -> Dict[str, int]:
        with db.cursor() as c:
            c.execute("SELECT status, COUNT(*) as count FROM orders GROUP BY status")
            return {row['status']: row['count'] for row in c.fetchall()}


class PromoModel:
    """Работа с промокодами."""
    
    @staticmethod
    def check(code: str, user_id: int) -> Dict[str, Any]:
        with db.cursor() as c:
            c.execute("""
                SELECT * FROM promocodes 
                WHERE code = ? AND active = 1 
                AND (max_uses = 0 OR used_count < max_uses)
                AND (expires_at IS NULL OR expires_at > datetime('now'))
            """, (code.upper(),))
            promo = c.fetchone()
            if not promo:
                return {'valid': False, 'reason': 'Промокод не существует или неактивен'}
            c.execute("SELECT 1 FROM promo_uses WHERE user_id = ? AND code = ?", (user_id, code.upper()))
            if c.fetchone():
                return {'valid': False, 'reason': 'Вы уже использовали этот промокод'}
            return {
                'valid': True,
                'discount_pct': promo['discount_pct'],
                'discount_rub': promo['discount_rub']
            }
    
    @staticmethod
    def use(code: str, user_id: int):
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("UPDATE promocodes SET used_count = used_count + 1 WHERE code = ?", (code.upper(),))
            c.execute("INSERT INTO promo_uses (user_id, code, used_at) VALUES (?, ?, ?)", 
                      (user_id, code.upper(), datetime.now()))
    
    @staticmethod
    def get_all() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM promocodes ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_code(code: str) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM promocodes WHERE code = ?", (code.upper(),))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def create(code: str, discount_pct: int = 0, discount_rub: int = 0, max_uses: int = 0, 
               expires_days: int = 0, description: str = "") -> int:
        code = code.upper()
        expires_at = None
        if expires_days > 0:
            expires_at = (datetime.now() + timedelta(days=expires_days)).strftime('%Y-%m-%d %H:%M:%S')
        with db.cursor() as c:
            c.execute("""
                INSERT INTO promocodes (code, discount_pct, discount_rub, max_uses, expires_at, description, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (code, discount_pct, discount_rub, max_uses, expires_at, description, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def update(code: str, **kwargs) -> bool:
        allowed = ['discount_pct', 'discount_rub', 'max_uses', 'active', 'expires_at', 'description']
        updates = []
        params = []
        for k, v in kwargs.items():
            if k in allowed:
                updates.append(f"{k} = ?")
                params.append(v)
        if not updates:
            return False
        params.append(code.upper())
        with db.cursor() as c:
            c.execute(f"UPDATE promocodes SET {', '.join(updates)} WHERE code = ?", params)
            return c.rowcount > 0
    
    @staticmethod
    def delete(code: str) -> bool:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("DELETE FROM promo_uses WHERE code = ?", (code.upper(),))
            c.execute("DELETE FROM promocodes WHERE code = ?", (code.upper(),))
            return True
    
    @staticmethod
    def get_usage_stats(code: str) -> Dict:
        with db.cursor() as c:
            c.execute("""
                SELECT COUNT(*) as total_uses, COUNT(DISTINCT user_id) as unique_users,
                       SUM(o.total_price) as total_revenue
                FROM promo_uses pu
                LEFT JOIN orders o ON pu.user_id = o.user_id AND o.promo_code = pu.code
                WHERE pu.code = ?
            """, (code.upper(),))
            stats = dict(c.fetchone())
            c.execute("""
                SELECT pu.user_id, u.first_name, u.username, pu.used_at, o.total_price
                FROM promo_uses pu
                LEFT JOIN users u ON pu.user_id = u.user_id
                LEFT JOIN orders o ON o.user_id = pu.user_id AND o.promo_code = pu.code
                WHERE pu.code = ?
                ORDER BY pu.used_at DESC
                LIMIT 10
            """, (code.upper(),))
            stats['recent_uses'] = [dict(row) for row in c.fetchall()]
            return stats


class DiagnosticModel:
    """Работа с диагностикой."""
    
    @staticmethod
    def create(user_id: int, notes: str, photo1: str, photo2: Optional[str] = None) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO diagnostics (user_id, photo_count, notes, photo1_file_id, photo2_file_id, created_at, sent)
                VALUES (?, ?, ?, ?, ?, ?, 0)
            """, (user_id, 2 if photo2 else 1, notes, photo1, photo2, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def get_pending() -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT d.*, u.first_name, u.username
                FROM diagnostics d
                JOIN users u ON d.user_id = u.user_id
                WHERE d.sent = 0
                ORDER BY d.created_at ASC
            """)
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_all(limit: int = 50) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT d.*, u.first_name, u.username
                FROM diagnostics d
                JOIN users u ON d.user_id = u.user_id
                ORDER BY d.created_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_id(diag_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM diagnostics WHERE id = ?", (diag_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def set_result(diag_id: int, result: str) -> bool:
        with db.cursor() as c:
            c.execute("UPDATE diagnostics SET admin_result = ?, sent = 1 WHERE id = ?", (result, diag_id))
            return c.rowcount > 0


class CustomOrderModel:
    """Кастомные заказы браслетов."""
    
    @staticmethod
    def create(user_id: int, purpose: str, stones: str, size: str, notes: str = "", photo1: str = None, photo2: str = None) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO custom_orders (user_id, purpose, stones, size, notes, photo1, photo2, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (user_id, purpose, stones, size, notes, photo1, photo2, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def get_pending() -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT co.*, u.first_name, u.username
                FROM custom_orders co
                JOIN users u ON co.user_id = u.user_id
                WHERE co.status = 'pending'
                ORDER BY co.created_at ASC
            """)
            return [dict(row) for row in c.fetchall()]


class MusicModel:
    """Музыкальная библиотека."""
    
    @staticmethod
    def get_all() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM music ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def create(name: str, description: str, audio_url: str, duration: int = 0) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO music (name, description, duration, audio_url, created_at)
                VALUES (?, ?, ?, ?, ?)
            """, (name, description, duration, audio_url, datetime.now()))
            return c.lastrowid


class WorkoutModel:
    """Тренировки."""
    
    @staticmethod
    def get_all() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM workouts ORDER BY created_at DESC")
            return [dict(row) for row in c.fetchall()]


class ServiceModel:
    """Услуги."""
    
    @staticmethod
    def get_all(active_only: bool = True) -> List[Dict]:
        with db.cursor() as c:
            query = "SELECT * FROM services"
            params = []
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY sort_order, price"
            c.execute(query, params)
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_id(service_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM services WHERE id = ?", (service_id,))
            row = c.fetchone()
            return dict(row) if row else None


class ScheduleModel:
    """Расписание слотов."""
    
    @staticmethod
    def get_available(days_ahead: int = 14) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT * FROM schedule_slots
                WHERE slot_date >= date('now')
                  AND slot_date <= date('now', ?)
                  AND available = 1
                ORDER BY slot_date, time_slot
            """, (f'+{days_ahead} days',))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def book(slot_id: int, user_id: int) -> bool:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("""
                UPDATE schedule_slots
                SET available = 0, booked_by = ?, booked_at = ?
                WHERE id = ? AND available = 1
            """, (user_id, datetime.now(), slot_id))
            return c.rowcount > 0
    
    @staticmethod
    def release(slot_id: int):
        with db.cursor() as c:
            c.execute("""
                UPDATE schedule_slots
                SET available = 1, booked_by = NULL, booked_at = NULL
                WHERE id = ?
            """, (slot_id,))
    
    @staticmethod
    def get_by_id(slot_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM schedule_slots WHERE id = ?", (slot_id,))
            row = c.fetchone()
            return dict(row) if row else None


class ConsultationModel:
    """Записи на консультации/услуги."""
    
    @staticmethod
    def create(user_id: int, service_id: int, slot_id: int, comment: str = "") -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO consultations (user_id, service_id, slot_id, comment, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
            """, (user_id, service_id, slot_id, comment, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def get_user_consultations(user_id: int) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT c.*, s.name as service_name, s.price, sl.slot_date, sl.time_slot
                FROM consultations c
                JOIN services s ON c.service_id = s.id
                JOIN schedule_slots sl ON c.slot_id = sl.id
                WHERE c.user_id = ?
                ORDER BY sl.slot_date DESC, sl.time_slot DESC
            """, (user_id,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_id(consult_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM consultations WHERE id = ?", (consult_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def update_status(consult_id: int, status: str) -> bool:
        with db.cursor() as c:
            c.execute("UPDATE consultations SET status = ? WHERE id = ?", (status, consult_id))
            return c.rowcount > 0


class GiftModel:
    """Подарочные сертификаты."""
    
    @staticmethod
    def generate_code() -> str:
        import random
        import string
        prefix = "GIFT"
        timestamp = datetime.now().strftime("%y%m")
        random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"{prefix}-{timestamp}-{random_part}"
    
    @staticmethod
    def create(buyer_id: int, amount: float, recipient_name: str, message: str = "") -> str:
        code = GiftModel.generate_code()
        expires_at = datetime.now() + timedelta(days=365)
        with db.cursor() as c:
            c.execute("""
                INSERT INTO gift_certificates (code, amount, buyer_id, recipient_name, message, created_at, expires_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (code, amount, buyer_id, recipient_name, message, datetime.now(), expires_at))
            return code
    
    @staticmethod
    def apply(code: str, user_id: int) -> Optional[float]:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("""
                SELECT id, amount FROM gift_certificates 
                WHERE code = ? AND status = 'active' AND expires_at > datetime('now')
            """, (code,))
            cert = c.fetchone()
            if not cert:
                return None
            cert_id = cert['id']
            amount = cert['amount']
            c.execute("""
                INSERT INTO referral_balance (user_id, balance, total_earned, referral_count)
                VALUES (?, ?, ?, 0)
                ON CONFLICT(user_id) DO UPDATE SET
                    balance = balance + ?,
                    total_earned = total_earned + ?
            """, (user_id, amount, amount, amount, amount))
            c.execute("UPDATE gift_certificates SET status = 'used', used_by = ?, used_at = ? WHERE id = ?",
                      (user_id, datetime.now(), cert_id))
            c.execute("INSERT INTO bonus_history (user_id, amount, operation, created_at) VALUES (?, ?, 'gift', ?)",
                      (user_id, amount, datetime.now()))
            conn.commit()
            return amount


class WishlistModel:
    """Избранное."""
    
    @staticmethod
    def add(user_id: int, item_id: int) -> bool:
        with db.cursor() as c:
            c.execute("INSERT OR IGNORE INTO wishlist (user_id, item_id, added_at) VALUES (?, ?, ?)",
                      (user_id, item_id, datetime.now()))
            return c.rowcount > 0
    
    @staticmethod
    def remove(user_id: int, item_id: int) -> bool:
        with db.cursor() as c:
            c.execute("DELETE FROM wishlist WHERE user_id = ? AND item_id = ?", (user_id, item_id))
            return c.rowcount > 0
    
    @staticmethod
    def get_all(user_id: int) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT w.item_id, b.name, b.price
                FROM wishlist w
                JOIN bracelets b ON w.item_id = b.id
                WHERE w.user_id = ?
                ORDER BY w.added_at DESC
            """, (user_id,))
            return [dict(row) for row in c.fetchall()]


class FAQModel:
    """Часто задаваемые вопросы."""
    
    @staticmethod
    def get_all(active_only: bool = True) -> List[Dict]:
        with db.cursor() as c:
            query = "SELECT * FROM faq"
            if active_only:
                query += " WHERE active = 1"
            query += " ORDER BY sort_order"
            c.execute(query)
            return [dict(row) for row in c.fetchall()]


class KnowledgeModel:
    """База знаний о камнях."""
    
    @staticmethod
    def get_all() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT id, stone_name, emoji FROM knowledge ORDER BY stone_name")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_by_id(stone_id: str) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM knowledge WHERE stone_id = ? OR LOWER(stone_name) LIKE ?", 
                      (stone_id, f'%{stone_id}%'))
            row = c.fetchone()
            return dict(row) if row else None


class QuizModel:
    """Квиз 'Узнай свой камень'."""
    
    @staticmethod
    def get_questions() -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT id, question, options, weights, sort_order
                FROM quiz_questions
                WHERE active = 1
                ORDER BY sort_order, id
            """)
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def save_result(user_id: int, answers: List[int], recommended_stone: str) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO quiz_results (user_id, answers, recommended_stone, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, json.dumps(answers), recommended_stone, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def get_user_results(user_id: int) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT * FROM quiz_results
                WHERE user_id = ?
                ORDER BY created_at DESC
                LIMIT 5
            """, (user_id,))
            return [dict(row) for row in c.fetchall()]


class TotemModel:
    """Тотемный квиз."""
    
    @staticmethod
    def get_questions() -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT id, question, options, weights, sort_order
                FROM totem_questions
                WHERE active = 1
                ORDER BY sort_order, id
            """)
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def save_result(user_id: int, answers: Dict, top3: List[str]) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO totem_results (user_id, answers, top1, top2, top3, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, json.dumps(answers), top3[0], top3[1], top3[2], datetime.now()))
            return c.lastrowid


class StoryModel:
    """Истории клиентов."""
    
    @staticmethod
    def create(user_id: int, story_text: str, photo_file_id: Optional[str] = None) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO stories (user_id, story_text, photo_file_id, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, story_text, photo_file_id, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def get_pending() -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT s.*, u.first_name, u.username
                FROM stories s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.approved = 0
                ORDER BY s.created_at ASC
            """)
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_approved(limit: int = 10) -> List[Dict]:
        with db.cursor() as c:
            c.execute("""
                SELECT s.*, u.first_name
                FROM stories s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.approved = 1
                ORDER BY s.created_at DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def approve(story_id: int) -> bool:
        with db.cursor() as c:
            c.execute("UPDATE stories SET approved = 1 WHERE id = ?", (story_id,))
            return c.rowcount > 0
    
    @staticmethod
    def reject(story_id: int) -> bool:
        with db.cursor() as c:
            c.execute("DELETE FROM stories WHERE id = ?", (story_id,))
            return c.rowcount > 0


class ReferralModel:
    """Реферальная система."""
    
    @staticmethod
    def add(referrer_id: int, referred_id: int) -> bool:
        with db.connection() as conn:
            c = conn.cursor()
            c.execute("INSERT INTO referrals (referrer_id, referred_id, created_at) VALUES (?, ?, ?)",
                      (referrer_id, referred_id, datetime.now()))
            c.execute("""
                INSERT INTO referral_balance (user_id, balance, total_earned, referral_count)
                VALUES (?, 100, 100, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    balance = balance + 100,
                    total_earned = total_earned + 100,
                    referral_count = referral_count + 1
            """, (referrer_id,))
            conn.commit()
            return True


class ClubModel:
    """Закрытый клуб 'Портал силы'."""
    
    @staticmethod
    def get_user_subscription(user_id: int) -> Optional[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM club_subscriptions WHERE user_id = ?", (user_id,))
            row = c.fetchone()
            return dict(row) if row else None
    
    @staticmethod
    def has_access(user_id: int) -> bool:
        sub = ClubModel.get_user_subscription(user_id)
        if not sub:
            return False
        now = datetime.now()
        if sub['status'] == 'active' and sub['subscription_end'] and sub['subscription_end'] > now:
            return True
        if sub['status'] == 'trial' and sub['trial_end'] and sub['trial_end'] > now:
            return True
        return False
    
    @staticmethod
    def start_trial(user_id: int) -> bool:
        with db.connection() as conn:
            c = conn.cursor()
            now = datetime.now()
            trial_end = now + timedelta(days=1)
            c.execute("""
                INSERT INTO club_subscriptions (user_id, status, trial_start, trial_end, created_at)
                VALUES (?, 'trial', ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = 'trial',
                    trial_start = ?,
                    trial_end = ?,
                    updated_at = ?
                WHERE status NOT IN ('active', 'trial')
            """, (user_id, now, trial_end, now, now, trial_end, now))
            return c.rowcount > 0
    
    @staticmethod
    def activate_paid(user_id: int, payment_id: str, duration_days: int = 30) -> bool:
        with db.connection() as conn:
            c = conn.cursor()
            now = datetime.now()
            end = now + timedelta(days=duration_days)
            c.execute("""
                INSERT INTO club_subscriptions (user_id, status, subscription_start, subscription_end, payment_id, created_at)
                VALUES (?, 'active', ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    status = 'active',
                    subscription_start = ?,
                    subscription_end = ?,
                    payment_id = ?,
                    updated_at = ?
            """, (user_id, now, end, payment_id, now, now, end, payment_id, now))
            return c.rowcount > 0
    
    @staticmethod
    def expire_subscriptions():
        with db.cursor() as c:
            now = datetime.now()
            c.execute("""
                UPDATE club_subscriptions
                SET status = 'expired', updated_at = ?
                WHERE status IN ('active', 'trial')
                  AND (
                      (status = 'active' AND subscription_end < ?)
                      OR
                      (status = 'trial' AND trial_end < ?)
                  )
            """, (now, now, now))


class ScheduledPostModel:
    """Планировщик постов."""
    
    @staticmethod
    def create(post_id: str, scheduled_time: str, channel_id: Optional[str] = None) -> int:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO scheduled_posts (post_id, channel_id, scheduled_time, created_at)
                VALUES (?, ?, ?, ?)
            """, (post_id, channel_id or '', scheduled_time, datetime.now()))
            return c.lastrowid
    
    @staticmethod
    def get_pending() -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM scheduled_posts WHERE status = 'pending' ORDER BY scheduled_time")
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_all(limit: int = 50) -> List[Dict]:
        with db.cursor() as c:
            c.execute("SELECT * FROM scheduled_posts ORDER BY scheduled_time DESC LIMIT ?", (limit,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def mark_published(post_id: int):
        with db.cursor() as c:
            c.execute("UPDATE scheduled_posts SET status = 'published', published_at = ? WHERE id = ?",
                      (datetime.now(), post_id))
    
    @staticmethod
    def mark_failed(post_id: int, error: str):
        with db.cursor() as c:
            c.execute("UPDATE scheduled_posts SET status = 'failed', error = ? WHERE id = ?", (error, post_id))


class FunnelModel:
    """Статистика воронки."""
    
    @staticmethod
    def track(user_id: int, event_type: str, details: str = None):
        with db.cursor() as c:
            c.execute("""
                INSERT INTO funnel_stats (user_id, event_type, details, created_at)
                VALUES (?, ?, ?, ?)
            """, (user_id, event_type, details, datetime.now()))
    
    @staticmethod
    def get_stats(days: int = 30) -> Dict[str, int]:
        events = ['start', 'view_showcase', 'view_product', 'add_to_cart', 'checkout', 'payment_success']
        result = {}
        with db.cursor() as c:
            for event in events:
                c.execute("""
                    SELECT COUNT(DISTINCT user_id) as users
                    FROM funnel_stats
                    WHERE event_type = ? AND created_at > datetime('now', ?)
                """, (event, f'-{days} days'))
                result[event] = c.fetchone()['users'] or 0
        return result


class SettingsModel:
    """Настройки бота."""
    
    DEFAULT = {
        'welcome_text': '🌟 ДОБРО ПОЖАЛОВАТЬ В МИР МАГИИ КАМНЕЙ!\n\nЯ помогу найти браслет или чётки, которые подойдут именно вам.\n\n🎁 СКИДКА 20% на первый заказ!\nПромокод: WELCOME20\n\nВыберите раздел 👇',
        'return_text': '👋 С возвращением! Выбери раздел:',
        'cashback_percent': '5',
        'min_order_for_cashback': '0',
        'contact_master': '@master',
        'delivery_info': '🚚 Доставка по всей России 1-3 дня.'
    }
    
    @staticmethod
    def get_all() -> Dict[str, str]:
        with db.cursor() as c:
            c.execute("SELECT key, value FROM bot_settings")
            settings = {row['key']: row['value'] for row in c.fetchall()}
        for k, v in SettingsModel.DEFAULT.items():
            if k not in settings:
                settings[k] = v
                with db.cursor() as c2:
                    c2.execute("INSERT OR IGNORE INTO bot_settings (key, value) VALUES (?, ?)", (k, v))
        return settings
    
    @staticmethod
    def get(key: str) -> str:
        return SettingsModel.get_all().get(key, '')
    
    @staticmethod
    def set(key: str, value: str) -> bool:
        with db.cursor() as c:
            c.execute("""
                INSERT INTO bot_settings (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, value))
            return True