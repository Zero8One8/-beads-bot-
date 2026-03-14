"""
Сервис экспорта данных в CSV.
"""
import csv
import io
from typing import List, Dict
from datetime import datetime

from src.database.db import db
from src.utils.helpers import format_price

class ExportService:
    @staticmethod
    def export_orders(limit: int = 5000) -> bytes:
        output = io.StringIO()
        writer = csv.writer(output, delimiter=';')
        
        writer.writerow([
            'ID заказа', 'ID пользователя', 'Имя', 'Username',
            'Сумма', 'Статус', 'Метод оплаты', 'Дата создания',
            'Промокод', 'Скидка', 'Бонусы', 'Кэшбэк'
        ])
        
        with db.cursor() as c:
            c.execute("""
                SELECT o.*, u.first_name, u.username
                FROM orders o
                LEFT JOIN users u ON o.user_id = u.user_id
                ORDER BY o.created_at DESC
                LIMIT ?
            """, (limit,))
            
            for row in c.fetchall():
                writer.writerow([
                    row['id'], row['user_id'], row['first_name'] or '', row['username'] or '',
                    row['total_price'], row['status'], row['payment_method'] or '',
                    row['created_at'][:19] if row['created_at'] else '',
                    row['promo_code'] or '', row['discount_rub'] or 0,
                    row['bonus_used'] or 0, row['cashback_amount'] or 0
                ])
        
        output.seek(0)
        return output.getvalue().encode('utf-8-sig')