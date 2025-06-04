import asyncio
import logging
import json  # Импорт для работы с JSON файлами
import os    # Импорт для работы с операционной системой (проверка существования файла)
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command
from datetime import datetime, time, timedelta # Импорты для работы с датой и временем
import locale # Импорт для работы с локализацией ( для названий дней недели)
from dotenv import load_dotenv # Импорт для загрузки переменных окружения из .env файла

# Загружает переменные окружения (API_TOKEN) из файла .env
load_dotenv()

# Получение токена бота из переменных окружения
API_TOKEN = os.getenv("API_TOKEN")
if not API_TOKEN:
    # Если токен не найден, прерываем выполнение с ошибкой
    raise RuntimeError("API_TOKEN не найден в переменных окружения (.env)")

# Настройка базовой конфигурации логирования
# Уровень логирования INFO означает, что будут записываться информационные сообщения, предупреждения и ошибки
# Формат лога включает время, уровень, имя логгера и сообщение
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s - %(message)s')
# Создание именованного логгера для этого модуля
logger = logging.getLogger(__name__)

# Инициализация объекта бота с указанием токена и настроек по умолчанию (HTML как режим парсинга сообщений)
bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
# Инициализация диспетчера для обработки входящих обновлений
dp = Dispatcher()

# --- Начало секции персистентности ---
# Определение имен файлов для хранения данных
USER_IDS_FILE = 'user_ids.json'             # Файл для хранения ID пользователей
PRACTICE_SLOTS_FILE = 'practice_slots.json' # Файл для хранения информации о записи на практики
SENT_NOTIFICATIONS_FILE = 'sent_notifications.json' # Файл для хранения отправленных уведомлений (для избежания дублей)

def load_persistent_data():
    """
    Загружает данные (user_ids, practice_slots, sent_notifications) из JSON файлов при запуске бота.
    Если файлы не существуют или содержат некорректный JSON, инициализирует соответствующую
    структуру данных пустым значением (set() или dict()).
    """
    loaded_user_ids = set()
    loaded_practice_slots = {}
    loaded_sent_notifications = set()

    # Загрузка user_ids (множество ID пользователей)
    try:
        if os.path.exists(USER_IDS_FILE): # Проверка существования файла
            with open(USER_IDS_FILE, 'r', encoding='utf-8') as f:
                # Загрузка из JSON и преобразование в множество
                loaded_user_ids = set(json.load(f))
            logger.info(f"Загружено {len(loaded_user_ids)} user_ids из {USER_IDS_FILE}")
    except (json.JSONDecodeError, FileNotFoundError) as e:
        # Обработка ошибок: если файл не найден или ошибка парсинга JSON
        logger.warning(f"Не удалось загрузить user_ids из {USER_IDS_FILE} ({e}). Используется пустое множество.")
        loaded_user_ids = set() # Инициализация пустым множеством

    # Загрузка practice_slots (словарь с информацией о практиках)
    try:
        if os.path.exists(PRACTICE_SLOTS_FILE):
            with open(PRACTICE_SLOTS_FILE, 'r', encoding='utf-8') as f:
                temp_practice_slots = json.load(f) # Временный словарь для обработки
                for key, value in temp_practice_slots.items():
                    # Преобразование строки времени открытия практики обратно в datetime объект
                    if isinstance(value, dict) and "open_time" in value and isinstance(value["open_time"], str):
                        try:
                            value["open_time"] = datetime.fromisoformat(value["open_time"])
                        except ValueError:
                            logger.error(
                                f"Ошибка парсинга datetime для open_time в practice_slots для ключа {key}. Значение: {value['open_time']}")
                    # Преобразование ключей слотов (номеров мест) обратно в int,
                    # так как JSON сохраняет все ключи словарей как строки.
                    value_copy = value.copy()  # Копируем словарь для безопасной итерации при изменении ключей
                    for slot_key, user_id_val in value.items():
                        # Пропускаем служебные поля "open_time" и "subject_name"
                        if slot_key not in ["open_time", "subject_name"]:
                            try:
                                int_slot_key = int(slot_key) # Попытка преобразовать ключ в int
                                if str(int_slot_key) == slot_key and int_slot_key != slot_key : # Если ключ был "1", а стал 1
                                     del value_copy[slot_key] # Удаляем старый строковый ключ
                                     value_copy[int_slot_key] = user_id_val # Добавляем новый int ключ
                                elif isinstance(slot_key, str) : # если ключ строка, но должен быть int
                                    del value_copy[slot_key]
                                    value_copy[int_slot_key] = user_id_val

                            except ValueError:
                                # Если ключ слота не может быть преобразован в int, логируем предупреждение
                                logger.warning(f"Ключ слота {slot_key} не является числом в {key} в practice_slots.")
                    loaded_practice_slots[key] = value_copy # Сохраняем обработанное значение
            logger.info(f"Загружено {len(loaded_practice_slots)} записей practice_slots из {PRACTICE_SLOTS_FILE}")
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning(
            f"Не удалось загрузить practice_slots из {PRACTICE_SLOTS_FILE} ({e}). Используется пустой словарь.")
        loaded_practice_slots = {} # Инициализация пустым словарем

    # Загрузка sent_notifications (множество отправленных уведомлений)
    try:
        if os.path.exists(SENT_NOTIFICATIONS_FILE):
            with open(SENT_NOTIFICATIONS_FILE, 'r', encoding='utf-8') as f:
                loaded_sent_notifications = set(json.load(f))
            logger.info(f"Загружено {len(loaded_sent_notifications)} sent_notifications из {SENT_NOTIFICATIONS_FILE}")
    except (json.JSONDecodeError, FileNotFoundError) as e:
        logger.warning(
            f"Не удалось загрузить sent_notifications из {SENT_NOTIFICATIONS_FILE} ({e}). Используется пустое множество.")
        loaded_sent_notifications = set() # Инициализация пустым множеством

    return loaded_user_ids, loaded_practice_slots, loaded_sent_notifications


def save_persistent_data(user_ids_data, practice_slots_data, sent_notifications_data):
    """
    Сохраняет текущее состояние user_ids, practice_slots и sent_notifications в JSON файлы.
    Множества преобразуются в списки, datetime объекты - в строки ISO формата.
    """
    # Сохранение user_ids
    try:
        with open(USER_IDS_FILE, 'w', encoding='utf-8') as f:
            # Преобразование множества в список для JSON-сериализации
            json.dump(list(user_ids_data), f, ensure_ascii=False, indent=4)
        # logger.debug(f"user_ids сохранены в {USER_IDS_FILE}") # Отладочное сообщение (закомментировано)
    except IOError as e: # Обработка ошибок ввода-вывода
        logger.error(f"Ошибка сохранения user_ids в {USER_IDS_FILE}: {e}")

    # Подготовка и сохранение practice_slots
    practice_slots_to_save = {} # Временный словарь для данных, готовых к сохранению
    for key, value in practice_slots_data.items():
        # Если значение является словарем и содержит 'open_time' типа datetime,
        # преобразуем 'open_time' в строку ISO формата.
        if isinstance(value, dict) and "open_time" in value and isinstance(value["open_time"], datetime):
            value_copy = value.copy()  # Копируем, чтобы не изменять оригинальный объект в памяти
            value_copy["open_time"] = value_copy["open_time"].isoformat() # Преобразование datetime в строку
            practice_slots_to_save[key] = value_copy
        else:
            # Если нет 'open_time' или он не datetime, сохраняем значение как есть
            # (или value.copy() если есть другие вложенные изменяемые структуры, требующие копирования)
            practice_slots_to_save[key] = value
    try:
        with open(PRACTICE_SLOTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(practice_slots_to_save, f, ensure_ascii=False, indent=4)
        # logger.debug(f"practice_slots сохранены в {PRACTICE_SLOTS_FILE}")
    except IOError as e:
        logger.error(f"Ошибка сохранения practice_slots в {PRACTICE_SLOTS_FILE}: {e}")

    # Сохранение sent_notifications
    try:
        with open(SENT_NOTIFICATIONS_FILE, 'w', encoding='utf-8') as f:
            # Преобразование множества в список для JSON-сериализации
            json.dump(list(sent_notifications_data), f, ensure_ascii=False, indent=4)
        # logger.debug(f"sent_notifications сохранены в {SENT_NOTIFICATIONS_FILE}")
    except IOError as e:
        logger.error(f"Ошибка сохранения sent_notifications в {SENT_NOTIFICATIONS_FILE}: {e}")
    # Логирование успешного сохранения всех данных
    logger.info("Данные сохранены (user_ids, practice_slots, sent_notifications).")


# Инициализация глобальных переменных данными из файлов (или пустыми значениями по умолчанию, если файлы отсутствуют/повреждены)
# Эта строка выполняется один раз при запуске скрипта.
user_ids, practice_slots, sent_notifications = load_persistent_data()
# --- Конец секции персистентности ---


# Полное расписание занятий: список кортежей (день_недели, время_начала, тип_занятия, название_предмета)
# Это основное расписание, на основе которого бот будет отправлять уведомления.
full_schedule = [
    ("Понедельник", time(9, 0), "лекция", "Теория вероятностей и математическая статистика"),
    ("Понедельник", time(10, 40), "лекция", "Проектирование баз данных"),
    ("Понедельник", time(12, 40), "практика", "Иностранный язык"),
    ("Вторник", time(9, 00), "лекция", "Философия"),
    ("Вторник", time(10, 40), "лекция", "Социальная психология и педагогика"),
    ("Среда", time(14, 35), "лекция", "Лекция Среды (Финансы)"), # Тестовый пример
    ("Среда", time(15, 10), "практика", "Практика Среды (Английский)"), # Тестовый пример 2
    ("Четверг", time(10, 40), "лекция", "Технология разработки программных приложений"),
    ("Четверг", time(12, 40), "практика", "Теория принятия решений"),
    ("Четверг", time(14, 20), "практика", "Технология разработки программных приложений"),
    ("Четверг", time(16, 20), "практика", "Физическая культура и спорт"),
    ("Пятница", time(9, 0), "практика", "Анализ и концептуальное моделирование систем"),
    ("Пятница", time(10, 40), "практика", "Проектирование баз данных"),
    ("Пятница", time(12, 40), "практика", "Многоагентное моделирование"),
    ("Пятница", time(14, 20), "практика", "Иностранный язык"),
    ("Пятница", time(16, 20), "практика", "Иностранный язык"),
    ("Суббота", time(12, 40), "практика", "Теория вероятностей и математическая статистика"),
    ("Суббота", time(14, 20), "практика", "Теория вероятностей и математическая статистика"),
    ("Суббота", time(16, 20), "практика", "Программирование на языке Питон"),
    ("Суббота", time(18, 0), "практика", "Программирование на языке Питон"),
]

# practice_slots = {} # Эта переменная теперь инициализируется функцией load_persistent_data()
MAX_SLOTS = 33 # Максимальное количество мест на практику
RECORDING_DURATION = timedelta(hours=1) # Продолжительность открытия записи на практику (1 час)


def get_confirm_keyboard(practice_session_key: str) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру с кнопками "Да" и "Нет" для подтверждения записи на практику.
    practice_session_key: Уникальный ключ сессии практики (например, "Понедельник_12:40").
    """
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"confirm_yes_{practice_session_key}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"confirm_no_{practice_session_key}")
    ]])


def get_slot_keyboard(practice_session_key: str, user_id: int) -> InlineKeyboardMarkup:
    """
    Создает инлайн-клавиатуру для выбора места на практику.
    practice_session_key: Уникальный ключ сессии практики.
    user_id: ID пользователя, для которого генерируется клавиатура (чтобы отметить его место).
    """
    global practice_slots  # Используем глобальную переменную practice_slots
    # Если сессия практики не найдена (например, запись уже закрыта), возвращаем клавиатуру с сообщением.
    if practice_session_key not in practice_slots:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Запись закрыта", callback_data="closed")]
        ])

    booked_data = practice_slots.get(practice_session_key, {}) # Получаем данные о забронированных местах
    keyboard_rows = [] # Список рядов кнопок
    current_row = []   # Текущий формируемый ряд кнопок

    # Итерация по всем возможным местам (от 1 до MAX_SLOTS)
    for i in range(1, MAX_SLOTS + 1):
        slot_owner_id = booked_data.get(i)  # Получаем ID пользователя, занявшего слот i (ключи слотов должны быть int)
        text = "" # Текст на кнопке
        callback_data_slot = "" # Данные, отправляемые при нажатии кнопки

        if isinstance(slot_owner_id, int): # Если слот занят
            if slot_owner_id == user_id: # Если слот занят текущим пользователем
                text = f"✅{i}" # Отмечаем его место галочкой
                callback_data_slot = f"slot_{practice_session_key}_{i}" # Позволяем отменить запись
            else: # Если слот занят другим пользователем
                text = f"🔒{i}" # Отмечаем место как заблокированное
                callback_data_slot = "busy" # Сообщаем, что место занято
        else: # Если слот свободен
            text = str(i) # Просто номер места
            callback_data_slot = f"slot_{practice_session_key}_{i}" # Позволяем занять место

        current_row.append(InlineKeyboardButton(text=text, callback_data=callback_data_slot))
        # Формируем ряды по 6 кнопок
        if len(current_row) == 6:
            keyboard_rows.append(current_row)
            current_row = []
    # Добавляем последний неполный ряд, если он есть
    if current_row:
        keyboard_rows.append(current_row)
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


@dp.message(Command(commands=["start"]))
async def register_user(message: types.Message):
    """
    Обработчик команды /start. Регистрирует пользователя (добавляет его ID в user_ids)
    и сохраняет обновленный список user_ids.
    """
    # Объявляем использование глобальных переменных, чтобы их можно было изменять
    global user_ids, practice_slots, sent_notifications
    user_ids.add(message.from_user.id) # Добавляем ID нового пользователя
    # Сохраняем все персистентные данные (включая обновленный user_ids)
    save_persistent_data(user_ids, practice_slots, sent_notifications)
    await message.answer("Бот запущен. Ждите уведомлений о занятиях.")


@dp.callback_query(lambda c: c.data == "busy")
async def handle_busy_slot(callback: CallbackQuery):
    """Обработчик нажатия на кнопку занятого места."""
    await callback.answer("Это место уже занято другим пользователем.", show_alert=True)


@dp.callback_query(lambda c: c.data == "closed")
async def handle_closed_practice(callback: CallbackQuery):
    """Обработчик нажатия на кнопку "Запись закрыта"."""
    await callback.answer("Запись на эту практику уже закрыта.", show_alert=True)


@dp.callback_query(lambda c: c.data.startswith("confirm_yes_"))
async def handle_confirm_yes_to_practice(callback: CallbackQuery):
    """
    Обработчик нажатия кнопки "Да" для подтверждения участия в практике.
    Показывает клавиатуру для выбора места.
    """
    global practice_slots # Используем глобальную переменную
    # Извлекаем ключ сессии практики из callback_data
    practice_session_key = callback.data.replace("confirm_yes_", "")
    if practice_session_key in practice_slots: # Если сессия еще активна
        session_data = practice_slots.get(practice_session_key)
        # Формируем отображаемое имя предмета
        subject_name_display = practice_session_key.replace('_', ' ') # По умолчанию, если имя не найдено
        if session_data and "subject_name" in session_data:
            subject_name_display = session_data["subject_name"]

        # Редактируем сообщение, предлагая выбрать место
        await callback.message.edit_text(
            f"Выберите место на практику: <b>{subject_name_display}</b>\n({practice_session_key.replace('_', ' ')}):",
            reply_markup=get_slot_keyboard(practice_session_key, callback.from_user.id)
        )
        await callback.answer() # Отвечаем на callback, чтобы убрать "часики"
    else: # Если сессия уже закрыта
        await callback.message.edit_text("Запись на эту практику уже закрыта.")
        await callback.answer("Запись на эту практику уже закрыта.", show_alert=True)


@dp.callback_query(lambda c: c.data.startswith("confirm_no_"))
async def handle_confirm_no_to_practice(callback: CallbackQuery):
    """Обработчик нажатия кнопки "Нет" (отказ от записи)."""
    await callback.message.edit_text("❌ Вы отказались от записи.")
    await callback.answer()


@dp.callback_query(lambda c: c.data.startswith("slot_"))
async def handle_slot_selection(callback: CallbackQuery):
    """
    Обработчик выбора конкретного места на практику.
    Позволяет занять свободное место или отменить свою бронь.
    """
    global practice_slots, user_ids, sent_notifications # Используем глобальные переменные
    # Парсинг callback_data для получения информации о слоте и сессии
    parts = callback.data.split("_") # Например, "slot_Понедельник_12:40_5"
    slot_num_str = parts[-1]          # Номер слота (строка)
    time_str = parts[-2]              # Время сессии
    practice_day_key_part = parts[1]  # День недели
    practice_session_key = f"{practice_day_key_part}_{time_str}" # Полный ключ сессии

    try:
        slot_num = int(slot_num_str) # Преобразуем номер слота в число
    except ValueError:
        logger.error(f"Ошибка парсинга номера слота из callback_data: {callback.data}")
        await callback.answer("Произошла ошибка. Попробуйте еще раз.", show_alert=True)
        return

    user_id = callback.from_user.id # ID пользователя, выбравшего слот

    # Проверка, активна ли еще сессия практики
    if practice_session_key not in practice_slots:
        await callback.message.edit_text("Запись на эту практику уже закрыта.")
        await callback.answer("Запись на эту практику уже закрыта.", show_alert=True)
        return

    current_practice_session_data = practice_slots[practice_session_key]

    # Проверка, не занял ли кто-то это место только что
    # Слот `slot_num` (int) должен быть ключом в `current_practice_session_data`
    if current_practice_session_data.get(slot_num) is not None and \
            isinstance(current_practice_session_data.get(slot_num), int) and \
            current_practice_session_data.get(slot_num) != user_id:
        await callback.answer("Это место только что заняли. Выберите другое.", show_alert=True)
        # Обновляем клавиатуру, чтобы показать актуальное состояние
        await callback.message.edit_reply_markup(reply_markup=get_slot_keyboard(practice_session_key, user_id))
        return

    # Проверяем, был ли этот слот уже занят текущим пользователем
    user_already_has_this_slot = (current_practice_session_data.get(slot_num) == user_id)

    # Ищем, был ли у пользователя уже другой слот в этой сессии, и если да, удаляем его
    old_slot_of_user = None
    # Создаем копию ключей для безопасной итерации, так как можем изменять словарь
    keys_to_check = list(current_practice_session_data.keys())
    for s_key in keys_to_check:
        # Пропускаем служебные поля
        if s_key in ["open_time", "subject_name"]: continue

        s_num_candidate = -1
        try:
            # Преобразуем ключ слота в int (так как они могут быть строками после загрузки из JSON,
            # хотя load_persistent_data должен это исправлять)
            s_num_candidate = int(s_key)
        except ValueError:
            continue # Пропускаем нечисловые ключи (если такие есть по ошибке)

        booked_uid = current_practice_session_data.get(s_key) # Получаем ID пользователя на этом слоте
        # Если на слоте `s_num_candidate` записан текущий пользователь
        if isinstance(booked_uid, int) and booked_uid == user_id:
            old_slot_of_user = s_num_candidate
            # Удаляем старую бронь пользователя. Важно удалять по правильному типу ключа.
            # Если s_key был строкой, а s_num_candidate - int, убедимся, что удаляем правильно.
            if s_num_candidate in current_practice_session_data:
                 del current_practice_session_data[s_num_candidate]
            elif str(s_num_candidate) in current_practice_session_data: # На случай, если ключ все еще строка
                 del current_practice_session_data[str(s_num_candidate)]
            break # Пользователь может занимать только одно место, выходим из цикла

    if user_already_has_this_slot:
        # Если пользователь нажал на свой уже занятый слот, это означает отмену записи на этот слот.
        # К этому моменту `old_slot_of_user` должен был найти этот слот и удалить его из `current_practice_session_data`.
        await callback.answer(f"Ваша запись на место #{slot_num} отменена.")
    else:
        # Если пользователь выбрал новый слот (не тот, что был у него ранее, или у него не было слотов):
        # 1. Если у него был другой слот, он уже удален (см. цикл выше).
        # 2. Теперь занимаем новый слот.
        current_practice_session_data[slot_num] = user_id  # Записываем пользователя на новый слот (ключ slot_num - int)
        await callback.answer(f"Вы выбрали место #{slot_num}.")

    # Сохраняем изменения в practice_slots
    save_persistent_data(user_ids, practice_slots, sent_notifications)
    # Обновляем клавиатуру с новым состоянием слотов
    await callback.message.edit_reply_markup(reply_markup=get_slot_keyboard(practice_session_key, user_id))


async def schedule_checker():
    """
    Асинхронная задача, которая периодически проверяет расписание и:
    1. Отправляет уведомления о начинающихся лекциях.
    2. Открывает запись на практики и уведомляет пользователей.
    3. Закрывает запись на практики по истечении времени (RECORDING_DURATION) и уведомляет записавшихся.
    4. Очищает старые записи из sent_notifications.
    """
    global sent_notifications, practice_slots, user_ids # Используем глобальные переменные

    # Словари для преобразования дней недели (если locale не сработает)
    weekdays_map_english_to_russian = {
        "Monday": "Понедельник", "Tuesday": "Вторник", "Wednesday": "Среда",
        "Thursday": "Четверг", "Friday": "Пятница", "Saturday": "Суббота", "Sunday": "Воскресенье"
    }
    # Список русских дней недели для использования с datetime.weekday() (Понедельник=0)
    russian_weekdays_by_index = [
        "Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"
    ]

    while True: # Бесконечный цикл проверки
        now = datetime.now() # Текущее время
        today_russian_weekday = "Unknown" # Переменная для хранения текущего дня недели на русском

        # Пытаемся определить день недели через strftime (зависит от установленной локали)
        try:
            day_from_strftime = now.strftime("%A").capitalize() # Например, "Monday" -> "Понедельник"
            if day_from_strftime in weekdays_map_english_to_russian.values(): # Если уже на русском
                today_russian_weekday = day_from_strftime
            elif day_from_strftime in weekdays_map_english_to_russian: # Если на английском, переводим
                today_russian_weekday = weekdays_map_english_to_russian[day_from_strftime]
        except Exception as e:
            logger.warning(f"Ошибка при получении дня недели через strftime('%A'): {e}.")

        # Если strftime не сработал или вернул не то, используем datetime.weekday() (не зависит от локали)
        if today_russian_weekday == "Unknown":
            try:
                day_index = now.weekday()  # Понедельник=0, Вторник=1, ...
                today_russian_weekday = russian_weekdays_by_index[day_index]
                logger.info(
                    f"День недели определен через now.weekday() как: {today_russian_weekday} (индекс {day_index})")
            except IndexError: # На всякий случай, если day_index будет некорректным
                logger.error(f"Ошибка: индекс дня недели {day_index} вне диапазона.")
                today_russian_weekday = "Unknown"
            except Exception as e:
                logger.error(f"Непредвиденная ошибка при определении дня через now.weekday(): {e}")
                today_russian_weekday = "Unknown"

        # Если день недели так и не определен, пропускаем текущую итерацию проверки
        if today_russian_weekday == "Unknown":
            logger.error("Не удалось определить текущий день недели. Пропускаем проверку расписания.")
            await asyncio.sleep(60) # Ждем минуту перед следующей попыткой
            continue

        logger.debug(f"Финальный определенный русский день недели: {today_russian_weekday}")
        now_minutes = now.hour * 60 + now.minute # Текущее время в минутах от начала дня
        data_changed = False  # Флаг, указывающий, были ли изменения в данных, требующие сохранения

        # --- Закрытие старых сессий записи на практики ---
        keys_to_remove_from_practice_slots = [] # Список ключей сессий для удаления
        # Итерируемся по копии элементов словаря, так как можем изменять его в процессе
        for practice_session_key, session_data in list(practice_slots.items()):
            # Проверяем, что 'open_time' существует и является объектом datetime
            if "open_time" in session_data and isinstance(session_data["open_time"], datetime):
                # Если с момента открытия записи прошло больше времени, чем RECORDING_DURATION
                if (now - session_data["open_time"]) > RECORDING_DURATION:
                    keys_to_remove_from_practice_slots.append(practice_session_key)
                    day_from_key, time_str_from_key = practice_session_key.split("_")
                    subject_name_closed = session_data.get("subject_name", f"{day_from_key} {time_str_from_key}")

                    # Собираем ID всех пользователей, записавшихся на эту практику
                    booked_user_ids = {uid for slot, uid in session_data.items() if
                                       slot not in ["open_time", "subject_name"] and isinstance(uid, int)}
                    # Уведомляем каждого записавшегося пользователя о закрытии записи
                    for user_id_booked in booked_user_ids:
                        try:
                            await bot.send_message(user_id_booked,
                                                   f"📢 Запись на практику <b>{subject_name_closed}</b> ({day_from_key} в {time_str_from_key}) закрыта. Ваше место подтверждено.")
                        except Exception as e: # Обработка возможных ошибок при отправке (например, пользователь заблокировал бота)
                            logger.warning(
                                f"Не удалось отправить сообщение о закрытии записи пользователю {user_id_booked}: {e}")
            elif "open_time" in session_data: # Если 'open_time' есть, но не datetime (ошибка в данных)
                logger.error(
                    f"Некорректный тип open_time для {practice_session_key}: {type(session_data['open_time'])}")

        # Удаляем закрытые сессии из practice_slots
        if keys_to_remove_from_practice_slots:
            for key_to_del in keys_to_remove_from_practice_slots:
                if key_to_del in practice_slots:
                    del practice_slots[key_to_del]
                    logger.info(f"Сессия записи на практику {key_to_del} закрыта и удалена.")
                    data_changed = True # Отмечаем, что данные изменились

        # --- Проверка текущих событий по расписанию (лекции, практики) ---
        for day_schedule, t_schedule, type_schedule, subject_name in full_schedule:
            # Пропускаем события, не относящиеся к сегодняшнему дню
            if day_schedule != today_russian_weekday:
                continue

            t_schedule_minutes = t_schedule.hour * 60 + t_schedule.minute # Время начала события в минутах
            # Уникальный ключ для события (включая дату), чтобы не отправлять уведомление повторно в тот же день
            notification_event_key = f"{day_schedule}_{t_schedule.strftime('%H:%M')}_{type_schedule}_{subject_name}_{now.date().isoformat()}"
            # Проверяем, наступило ли время события
            should_notify = (now_minutes == t_schedule_minutes)

            # Если время наступило и уведомление еще не было отправлено
            if should_notify and notification_event_key not in sent_notifications:
                sent_notifications.add(notification_event_key) # Добавляем ключ в отправленные
                data_changed = True # Отмечаем, что данные изменились
                logger.info(f"Отправка уведомления для: {notification_event_key}")

                if type_schedule == "лекция":
                    message_text = f"📘 Сейчас начинается лекция: <b>{subject_name}</b>\n{day_schedule} в {t_schedule.strftime('%H:%M')}"
                    # Отправляем уведомление всем зарегистрированным пользователям
                    for uid in user_ids:
                        try:
                            await bot.send_message(uid, message_text)
                        except Exception as e:
                            logger.warning(f"Не удалось отправить уведомление о лекции пользователю {uid}: {e}")

                elif type_schedule == "практика":
                    current_practice_session_key = f"{day_schedule}_{t_schedule.strftime('%H:%M')}"
                    # Если запись на эту практику еще не открыта
                    if current_practice_session_key not in practice_slots:
                        # Открываем запись: добавляем сессию в practice_slots
                        practice_slots[current_practice_session_key] = {"open_time": now, "subject_name": subject_name}
                        data_changed = True # Отмечаем, что данные изменились
                        message_text = f"📢 Открыта запись на практику: <b>{subject_name}</b>\n{day_schedule} в {t_schedule.strftime('%H:%M')}.\nЗапись будет открыта в течение {int(RECORDING_DURATION.total_seconds() / 3600)} часа."
                        # Уведомляем всех пользователей об открытии записи
                        for uid in user_ids:
                            try:
                                await bot.send_message(
                                    uid,
                                    message_text,
                                    reply_markup=get_confirm_keyboard(current_practice_session_key) # Клавиатура "Да/Нет"
                                )
                            except Exception as e:
                                logger.warning(f"Не удалось отправить уведомление о практике пользователю {uid}: {e}")
                        logger.info(f"Открыта запись на практику: {subject_name} ({current_practice_session_key})")
                    else: # Если сессия уже была открыта (например, после перезапуска бота)
                        logger.info(
                            f"Сессия записи на практику {subject_name} ({current_practice_session_key}) уже была открыта ранее. Уведомление не отправляется повторно.")

        # --- Очистка старых ключей из sent_notifications ---
        # Удаляем ключи уведомлений, относящиеся к вчерашнему дню, чтобы sent_notifications не рос бесконечно
        yesterday_date_str = (now - timedelta(days=1)).date().isoformat()
        keys_to_clear_from_sent = {
            key for key in sent_notifications if yesterday_date_str in key
        }
        if keys_to_clear_from_sent:
            for old_key in keys_to_clear_from_sent:
                sent_notifications.discard(old_key) # Используем discard, чтобы не было ошибки, если ключ уже удален
                logger.info(f"Удален старый ключ из sent_notifications: {old_key}")
            data_changed = True # Отмечаем, что данные изменились

        # Если в течение этой итерации были изменения в данных, сохраняем их
        if data_changed:
            save_persistent_data(user_ids, practice_slots, sent_notifications)

        await asyncio.sleep(30) # Пауза перед следующей проверкой (30 секунд)


async def main():
    """Основная функция запуска бота."""
    # Объявляем использование глобальных переменных (хотя здесь они только читаются,
    # присваивание им происходит на уровне модуля при вызове load_persistent_data)
    global user_ids, practice_slots, sent_notifications

    # Загрузка персистентных данных уже выполнена на уровне модуля при инициализации переменных:
    # user_ids, practice_slots, sent_notifications = load_persistent_data()

    # --- Настройка локали для корректного отображения дней недели ---
    logger.info("Попытка установить русскую локаль...")
    # Список локалей, которые могут соответствовать русской
    locales_to_try = ['ru_RU.UTF-8', 'ru_RU.utf8', 'Russian_Russia.1251', 'rus_rus.1251']
    locale_set_successfully = False
    current_locale_lc_time = "" # Хранение текущей локали перед попытками установки
    try:
        current_locale_lc_time = locale.getlocale(locale.LC_TIME)
    except Exception:
        logger.warning("Не удалось получить текущую LC_TIME локаль перед установкой.")

    for loc in locales_to_try:
        try:
            locale.setlocale(locale.LC_TIME, loc) # Попытка установить локаль
            test_day = datetime(2023, 1, 2).strftime('%A')  # Это понедельник, проверяем его название
            logger.info(
                f"Попытка установить локаль '{loc}'. Тестовый день: '{test_day}'. Установленная локаль: {locale.getlocale(locale.LC_TIME)}")
            # Простая проверка, содержит ли название дня русские буквы
            if any(c in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' for c in test_day.lower()):
                logger.info(f"Локаль '{loc}' успешно установлена и возвращает русские дни.")
                locale_set_successfully = True
                break # Выходим из цикла, если подходящая локаль найдена
            else:
                logger.warning(f"Локаль '{loc}' установлена, но тестовый день '{test_day}' не на русском.")
        except locale.Error: # Ошибка при установке локали
            logger.warning(f"Не удалось установить локаль '{loc}'.")
        # Если попытка была неудачной, возвращаем предыдущую установленную локаль (если она была)
        if current_locale_lc_time and current_locale_lc_time != (None, None):
            try:
                locale.setlocale(locale.LC_TIME, current_locale_lc_time)
            except locale.Error:
                logger.warning(f"Не удалось вернуть локаль к {current_locale_lc_time} после неудачной попытки с {loc}.")

    if not locale_set_successfully:
        logger.error(
            "Не удалось установить подходящую русскую локаль. Определение дня недели будет полагаться на метод weekday().")
    else:
        logger.info(f"Финально установленная локаль для LC_TIME: {locale.getlocale(locale.LC_TIME)}")

    logger.info("Запуск бота...")
    # Запуск фоновой задачи schedule_checker
    asyncio.create_task(schedule_checker())
    # Удаление вебхука и очистка ожидающих обновлений перед запуском поллинга
    await bot.delete_webhook(drop_pending_updates=True)
    # Запуск поллинга для получения обновлений от Telegram
    await dp.start_polling(bot)


if __name__ == "__main__":
    # Точка входа в программу
    asyncio.run(main())