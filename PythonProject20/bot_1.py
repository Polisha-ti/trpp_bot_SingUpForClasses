import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.enums import ParseMode
from datetime import datetime, time, timedelta
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
import logging

API_TOKEN = "7221891232:AAEG9L2JjVtpaqDfqiO2lHNwenNlQmxSNzY"

logging.basicConfig(level=logging.INFO)

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher()

# --- Данные ---
user_ids = set()  # Тут будут все ID пользователей
practice_schedule = [  # (день, время начала)
    ("Понедельник", time(13, 0)),
    ("Вторник", time(14, 32)),
    ("Среда", time(15, 30)),
]
# Расписание
schedule = {
    "Понедельник": ["9:00 - Математика", "13:00 - Практика"],
    "Вторник": ["9:00 - Математика", "14:05 - Практика"],
    "Среда": ["12:00 - Информатика", "15:00 - Практика"]
}

practice_slots = {}  # key: "Понедельник_13:00", value: {"open_time": datetime, 1: user_id, ...}
MAX_SLOTS = 33
RECORDING_DURATION = timedelta(hours=1)

# --- Кнопки ---
def get_confirm_keyboard(key):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_yes_{key}"),
            InlineKeyboardButton(text="❌ Нет", callback_data=f"confirm_no_{key}")
        ]
    ])

def get_slot_keyboard(key, user_id):
    if key not in practice_slots:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Запись закрыта", callback_data="closed")]])
    booked = practice_slots.get(key, {})
    keyboard = []
    row = []
    for i in range(1, MAX_SLOTS + 1):
        if i in booked and isinstance(booked[i], int):  # Проверяем, что это ID пользователя
            text = f"🔒{i}" if booked[i] != user_id else f"✅{i}"
            callback_data = "busy"
        else:
            text = str(i)
            callback_data = f"slot_{key}_{i}"
        row.append(InlineKeyboardButton(text=text, callback_data=callback_data))
        if len(row) == 6:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Обработчики ---
@dp.message(Command(commands=["start"]))
async def register_user(message: types.Message):
    user_ids.add(message.from_user.id)
    await message.answer("Бот запущен. Ждите открытия записи.")

@dp.callback_query(lambda c: c.data == "busy")
async def handle_busy(callback: CallbackQuery):
    await callback.answer("Это место уже занято.", show_alert=True)

@dp.callback_query(lambda c: c.data == "closed")
async def handle_closed(callback: CallbackQuery):
    await callback.answer("Запись на эту практику уже закрыта.", show_alert=True)

@dp.callback_query(lambda c: c.data.startswith("confirm_yes_"))
async def handle_confirm_yes(callback: CallbackQuery):
    key = callback.data.replace("confirm_yes_", "")
    if key in practice_slots:
        await callback.message.answer(
            f"Выберите место на практику ({key.replace('_', ' ')}):",
            reply_markup=get_slot_keyboard(key, callback.from_user.id)
        )
        await callback.answer()
    else:
        await callback.answer("Запись на эту практику уже закрыта.")

@dp.callback_query(lambda c: c.data.startswith("confirm_no_"))
async def handle_confirm_no(callback: CallbackQuery):
    await callback.message.edit_text("❌ Вы отказались от записи.")
    await callback.answer()

@dp.callback_query(lambda c: c.data.startswith("slot_"))
async def handle_slot_selection(callback: CallbackQuery):
    _, day, time_str, slot_str = callback.data.split("_")
    key = f"{day}_{time_str}"
    slot_num = int(slot_str)
    user_id = callback.from_user.id

    if key not in practice_slots:
        await callback.answer("Запись на эту практику уже закрыта.", show_alert=True)
        return

    booked = practice_slots.get(key)

    if slot_num in booked and isinstance(booked[slot_num], int):
        await callback.answer("Это место уже занято.", show_alert=True)
        return

    # Удаляем старую запись пользователя
    for s, uid in list(booked.items()):
        if isinstance(uid, int) and uid == user_id:
            del booked[s]

    booked[slot_num] = user_id
    await callback.message.edit_reply_markup(reply_markup=get_slot_keyboard(key, user_id))
    await callback.answer(f"Вы выбрали место #{slot_num}")

# --- Фоновая проверка пар ---
async def schedule_checker():
    sent_notifications = set()
    weekdays = {
        "Monday": "Понедельник",
        "Tuesday": "Вторник",
        "Wednesday": "Среда",
        "Thursday": "Четверг",
        "Friday": "Пятница",
        "Saturday": "Суббота",
        "Sunday": "Воскресенье"
    }

    while True:
        now = datetime.now(tz=None)  # Используем локальное время без указания часового пояса
        today = weekdays[now.strftime("%A")]
        current_time = now.strftime("%H:%M")

        keys_to_remove = []
        for key, data in practice_slots.items():
            if "open_time" in data and (now - data["open_time"]) > RECORDING_DURATION:
                keys_to_remove.append(key)
                booked_users = {slot: user_id for slot, user_id in data.items() if isinstance(user_id, int)}
                for user_id in booked_users.values():
                    try:
                        day, time_str = key.split("_")
                        await bot.send_message(user_id, f"📢 Запись на практику {day} в {time_str} закрыта.")
                    except Exception as e:
                        logging.warning(f"Не удалось отправить сообщение о закрытии записи пользователю {user_id}: {e}")

        for key in keys_to_remove:
            del practice_slots[key]
            if key in sent_notifications:
                sent_notifications.remove(key)

        for day, t in practice_schedule:
            time_str = t.strftime("%H:%M")
            key = f"{day}_{time_str}"

            if today == day and current_time == time_str and key not in sent_notifications:
                sent_notifications.add(key)
                practice_slots[key] = {"open_time": now}

                for uid in user_ids:
                    try:
                        await bot.send_message(
                            uid,
                            f"📢 Открыта запись на практику {day} в {time_str}.\nЗапись будет открыта в течение 1 часа.",
                            reply_markup=get_confirm_keyboard(key)
                        )
                    except Exception as e:
                        logging.warning(f"Не удалось отправить уведомление об открытии записи пользователю {uid}: {e}")
        await asyncio.sleep(60)

# --- Старт ---
async def main():
    asyncio.create_task(schedule_checker())
    await dp.start_polling(bot)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())