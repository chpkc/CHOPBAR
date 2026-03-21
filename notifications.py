import logging
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

# Часовой пояс (как у тебя в других файлах)
pavlodar_tz = timezone(timedelta(hours=5))

async def check_reminders(bot, supabase):
    """
    Задача для планировщика: проверяет БД каждые 60 секунд и рассылает 
    уведомления клиентам за 24 и 2 часа до записи.
    """
    if not supabase:
        return

    try:
        # Получаем все подтвержденные записи (в твоей таблице статус может быть 'new' или 'confirmed')
        # Исходя из bot.py, у тебя статус 'new' означает активную запись, но давай проверять оба
        res = supabase.table('bookings').select('*').in_('status', ['new', 'confirmed']).execute()
        appointments = res.data

        if not appointments:
            return

        now = datetime.now(pavlodar_tz)

        for a in appointments:
            # Если оба уведомления уже отправлены, пропускаем
            if a.get('notified_24h') and a.get('notified_2h'):
                continue

            try:
                # Парсим время записи
                dt_naive = datetime.strptime(f"{a['date']} {a['time']}", "%Y-%m-%d %H:%M")
                dt = dt_naive.replace(tzinfo=pavlodar_tz)
                
                delta = dt - now
                hours_left = delta.total_seconds() / 3600

                barber_name = a.get('master', 'Мастер')
                time_str = a['time'][:5] if isinstance(a['time'], str) else str(a['time'])
                client_tg_id = a.get('telegram_id')

                if not client_tg_id:
                    continue

                # 1. Напоминание за 24 часа (+/- 5 минут, то есть от 23.9 до 24.1 часов)
                if 23.9 <= hours_left <= 24.1 and not a.get('notified_24h'):
                    msg = f"Напоминаем, завтра в {time_str} у тебя запись к мастеру {barber_name} — {a['service']}. Ждём!"
                    await bot.send_message(client_tg_id, msg)
                    
                    # Отмечаем, что уведомили
                    supabase.table('bookings').update({'notified_24h': True}).eq('id', a['id']).execute()

                # 2. Напоминание за 2 часа (+/- 5 минут, то есть от 1.9 до 2.1 часов)
                elif 1.9 <= hours_left <= 2.1 and not a.get('notified_2h'):
                    msg = f"Через 2 часа твоя стрижка! {time_str}, мастер {barber_name}. Будем ждать 💈"
                    await bot.send_message(client_tg_id, msg)
                    
                    # Отмечаем, что уведомили
                    supabase.table('bookings').update({'notified_2h': True}).eq('id', a['id']).execute()

            except Exception as e:
                logger.error(f"Ошибка обработки записи {a.get('id')}: {e}")

    except Exception as e:
        logger.error(f"Ошибка при проверке уведомлений: {e}")

async def notify_master_new_appointment(bot, barber_tg_id, client_name, service, date, time):
    """
    Отправляет уведомление мастеру о новой записи.
    """
    msg = f"Новая запись! Клиент: {client_name}, услуга: {service}, дата: {date} в {time}"
    try:
        await bot.send_message(barber_tg_id, msg)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления мастеру о новой записи: {e}")

async def notify_master_cancellation(bot, barber_tg_id, client_name, service, date, time):
    """
    Отправляет уведомление мастеру об отмене записи.
    """
    msg = f"Запись отменена. {client_name}, {service}, {date} {time}"
    try:
        await bot.send_message(barber_tg_id, msg)
    except Exception as e:
        logger.error(f"Ошибка отправки уведомления мастеру об отмене записи: {e}")

def setup_scheduler(bot, supabase) -> AsyncIOScheduler:
    """Инициализация планировщика"""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_reminders,
        trigger='interval',
        seconds=60, # Проверяем каждые 60 секунд
        kwargs={'bot': bot, 'supabase': supabase}
    )
    return scheduler