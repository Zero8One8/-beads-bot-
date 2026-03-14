"""
Модуль аналитики и статистики.
Сбор и агрегация данных для админ-панели.
"""
from typing import Dict, List, Any, Optional
from datetime import datetime, timedelta
from collections import defaultdict
from src.database.db import db


class Analytics:
    """
    Класс для сбора аналитических данных.
    """
    
    @staticmethod
    def get_user_stats(days: int = 30) -> Dict[str, Any]:
        """
        Статистика по пользователям за последние N дней.
        """
        with db.cursor() as c:
            # Всего пользователей
            c.execute("SELECT COUNT(*) as total FROM users")
            total_users = c.fetchone()['total']
            
            # Новые за период
            c.execute("""
                SELECT COUNT(*) as new 
                FROM users 
                WHERE created_at > datetime('now', ?)
            """, (f'-{days} days',))
            new_users = c.fetchone()['new']
            
            # Активные (заходили в бота)
            c.execute("""
                SELECT COUNT(DISTINCT user_id) as active
                FROM funnel_stats
                WHERE created_at > datetime('now', ?)
            """, (f'-{days} days',))
            active_users = c.fetchone()['active']
            
            # По дням (для графика)
            c.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count
                FROM users
                WHERE created_at > datetime('now', '-30 days')
                GROUP BY DATE(created_at)
                ORDER BY date
            """)
            daily_new = [dict(row) for row in c.fetchall()]
            
            return {
                'total': total_users,
                'new': new_users,
                'active': active_users,
                'daily_new': daily_new
            }
    
    @staticmethod
    def get_order_stats(days: int = 30) -> Dict[str, Any]:
        """
        Статистика по заказам за последние N дней.
        """
        with db.cursor() as c:
            # Всего заказов
            c.execute("SELECT COUNT(*) as total, SUM(total_price) as total_revenue FROM orders WHERE status = 'paid'")
            row = c.fetchone()
            total_orders = row['total'] or 0
            total_revenue = float(row['total_revenue'] or 0)
            
            # За период
            c.execute("""
                SELECT COUNT(*) as count, SUM(total_price) as revenue
                FROM orders
                WHERE status = 'paid' AND created_at > datetime('now', ?)
            """, (f'-{days} days',))
            row = c.fetchone()
            period_orders = row['count'] or 0
            period_revenue = float(row['revenue'] or 0)
            
            # Средний чек
            avg_check = period_revenue / period_orders if period_orders > 0 else 0
            
            # По дням
            c.execute("""
                SELECT DATE(created_at) as date, COUNT(*) as count, SUM(total_price) as revenue
                FROM orders
                WHERE status = 'paid' AND created_at > datetime('now', '-30 days')
                GROUP BY DATE(created_at)
                ORDER BY date
            """)
            daily = [dict(row) for row in c.fetchall()]
            
            return {
                'total_orders': total_orders,
                'total_revenue': total_revenue,
                'period_orders': period_orders,
                'period_revenue': period_revenue,
                'avg_check': avg_check,
                'daily': daily
            }
    
    @staticmethod
    def get_popular_products(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Самые популярные товары по количеству продаж.
        """
        with db.cursor() as c:
            c.execute("""
                SELECT 
                    oi.item_name,
                    oi.item_type,
                    COUNT(*) as sales_count,
                    SUM(oi.quantity) as total_quantity,
                    SUM(oi.price * oi.quantity) as total_revenue
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                WHERE o.status = 'paid'
                GROUP BY oi.item_id, oi.item_name, oi.item_type
                ORDER BY sales_count DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_popular_stones(limit: int = 10) -> List[Dict[str, Any]]:
        """
        Самые популярные камни (из базы знаний) по упоминаниям в заказах.
        """
        with db.cursor() as c:
            c.execute("""
                SELECT 
                    k.stone_name,
                    k.emoji,
                    COUNT(*) as mentions
                FROM order_items oi
                JOIN orders o ON oi.order_id = o.id
                JOIN knowledge k ON LOWER(oi.item_name) LIKE '%' || LOWER(k.stone_name) || '%'
                WHERE o.status = 'paid'
                GROUP BY k.id
                ORDER BY mentions DESC
                LIMIT ?
            """, (limit,))
            return [dict(row) for row in c.fetchall()]
    
    @staticmethod
    def get_funnel_stats(days: int = 30) -> Dict[str, int]:
        """
        Статистика воронки продаж.
        """
        events = ['start', 'view_showcase', 'add_to_cart', 'checkout', 'payment_success']
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
    
    @staticmethod
    def get_cashback_stats() -> Dict[str, Any]:
        """
        Статистика по бонусной системе.
        """
        with db.cursor() as c:
            c.execute("SELECT SUM(balance) as total_balance, SUM(total_earned) as total_earned FROM referral_balance")
            row = c.fetchone()
            
            c.execute("SELECT COUNT(*) as users_with_balance FROM referral_balance WHERE balance > 0")
            users_with_balance = c.fetchone()['users_with_balance']
            
            c.execute("SELECT SUM(amount) as total_used FROM bonus_history WHERE operation = 'used'")
            total_used = c.fetchone()['total_used'] or 0
            
            return {
                'total_balance': float(row['total_balance'] or 0),
                'total_earned': float(row['total_earned'] or 0),
                'users_with_balance': users_with_balance,
                'total_used': float(total_used)
            }