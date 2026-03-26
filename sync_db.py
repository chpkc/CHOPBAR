# -*- coding: utf-8 -*-

import os
import json
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("Ошибка: SUPABASE_URL или SUPABASE_KEY не найдены в .env")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def sync_bookings():
    print("--- Синхронизация бронирований ---")
    
    # Загружаем локальные данные
    try:
        with open('data/bookings.json', 'r', encoding='utf-8') as f:
            bookings = json.load(f)
    except FileNotFoundError:
        print("Файл data/bookings.json не найден.")
        return

    if not bookings:
        print("Нет локальных бронирований для синхронизации.")
        return

    print(f"Найдено {len(bookings)} бронирований. Начинаем загрузку...")

    # Пробуем вставить данные
    # Примечание: id должен быть уникальным. Если записи уже есть, может возникнуть ошибка.
    # Supabase upsert работает по Primary Key.
    
    success_count = 0
    error_count = 0
    
    for booking in bookings:
        try:
            # Подготавливаем данные
            # Убедимся, что формат даты и времени подходит для Postgres (если там типы date/time)
            # В JSON у нас: "date": "Среда, 4 марта" (строка) или "2026-03-10" (ISO)
            # Если в базе типы text, то ок. Если date, то нужно конвертировать.
            # Пока пробуем отправить как есть, предполагая, что таблица создана с text полями или compatible types.
            
            # Очищаем данные от лишних полей, если нужно
            data = {
                "id": booking.get("id"), # Используем ID из JSON как PK
                "master": booking.get("master"),
                "service": booking.get("service"),
                "price": booking.get("price"),
                "date": booking.get("date"),
                "time": booking.get("time"),
                "duration": booking.get("duration"),
                "telegram_id": booking.get("telegram_id"),
                "status": booking.get("status"),
                "created_at": booking.get("created_at")
            }
            
            # Используем upsert чтобы обновить существующие или создать новые
            response = supabase.table("bookings").upsert(data).execute()
            
            # Проверяем ответ (в новых версиях supabase-py execute() возвращает APIResponse)
            # Если нет исключения, считаем успешным
            success_count += 1
            print(f"Бронирование {booking.get('id')} синхронизировано.")
            
        except Exception as e:
            error_count += 1
            print(f"Ошибка при синхронизации бронирования {booking.get('id')}: {e}")

    print(f"\nИтог: Успешно: {success_count}, Ошибок: {error_count}")

if __name__ == "__main__":
    sync_bookings()
