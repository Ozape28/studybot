import telebot
from telebot import types
import time
import threading
import random
import json
import os
from datetime import datetime
from dotenv import load_dotenv
import os

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise ValueError("Токен не найден! Проверь файл .env")
bot = telebot.TeleBot(TOKEN)

DATA_FILE = "bot_data.json"  

# ============ ХРАНИЛИЩЕ ДАННЫХ ============
active_timers = {}

# Загружаем сохранённые данные пользователей
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

user_data = load_data()

def get_user(user_id):
    """Получить или создать запись пользователя."""
    uid = str(user_id)
    if uid not in user_data:
        user_data[uid] = {
            "notes": [],
            "schedule": [],
            "stats": {"pomodoros_completed": 0, "pomodoros_cancelled": 0}
        }
        save_data()
    return user_data[uid]


# ============ ГЛАВНОЕ МЕНЮ (КНОПКИ) ============
def main_menu():
    """Inline-клавиатура с основными командами."""
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("⏱ Помодоро", callback_data="menu_pomodoro"),
        types.InlineKeyboardButton("💪 Мотивация", callback_data="menu_motivation"),
        types.InlineKeyboardButton("🔢 Конвертер", callback_data="menu_convert_help"),
        types.InlineKeyboardButton("📝 Заметки", callback_data="menu_notes"),
        types.InlineKeyboardButton("📅 Расписание", callback_data="menu_schedule"),
        types.InlineKeyboardButton("🎲 Выбор", callback_data="menu_choose_help"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="menu_stats"),
        types.InlineKeyboardButton("ℹ️ Помощь", callback_data="menu_help"),
    )
    return kb


# ============ /start ============
@bot.message_handler(commands=['start'])
def start(message):
    get_user(message.from_user.id)
    bot.send_message(
        message.chat.id,
        "👋 *Привет\\! Я StudyBot — твой учебный помощник\\.*\n\n"
        "Выбери действие в меню ниже\\.",
        reply_markup=main_menu(),
        parse_mode="MarkdownV2"
    )


# ============ /help ============
HELP_TEXT = (
    "📚 *Все команды:*\n\n"
    "⏱ /pomodoro \\[мин\\] — таймер \\(по умолчанию 25 мин\\)\n"
    "💪 /motivation — мотивирующая цитата\n"
    "🔢 /convert 5 km m — конвертер единиц\n"
    "📝 /note текст — сохранить заметку\n"
    "📝 /notes — все заметки\n"
    "📅 /schedule — расписание на день\n"
    "🎲 /choose опция1, опция2 — случайный выбор\n"
    "📊 /stats — твоя статистика\n"
    "🏠 /menu — главное меню"
)

@bot.message_handler(commands=['help', 'menu'])
def show_help(message):
    bot.send_message(message.chat.id, HELP_TEXT, reply_markup=main_menu(), parse_mode="MarkdownV2")


# ============ /motivation ============
quotes = [
    "💪 Ты можешь всё, что захочешь!",
    "📖 Знание — сила. Учись каждый день.",
    "🚀 Начни сейчас, совершенствуй потом.",
    "⭐ Каждый эксперт когда-то был новичком.",
    "🎯 Сосредоточься на прогрессе, а не на совершенстве.",
    "🌱 Маленький шаг каждый день меняет всё.",
    "🔥 Дисциплина = свобода.",
    "🧠 Мозг растёт от вызовов. Берись за сложное.",
    "☕ Чашка кофе и 25 минут фокуса — и горы свернёшь.",
    "✨ Делай или не делай. Не существует попытки.",
]

@bot.message_handler(commands=['motivation'])
def motivation(message):
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔄 Ещё цитату", callback_data="menu_motivation"))
    bot.send_message(message.chat.id, random.choice(quotes), reply_markup=kb)


# ============ /pomodoro с живым счётчиком и отменой ============
def format_time(seconds):
    """Преобразует секунды в MM:SS."""
    m, s = divmod(max(0, seconds), 60)
    return f"{m:02d}:{s:02d}"


def pomodoro_progress_bar(elapsed, total):
    """Прогресс-бар вида ▰▰▰▱▱▱▱▱▱▱"""
    filled = int(10 * elapsed / total) if total else 0
    return "▰" * filled + "▱" * (10 - filled)


def run_pomodoro(chat_id, user_id, duration_min, phase="work"):
    """Запуск таймера в отдельном потоке с живым счётчиком."""
    duration_sec = duration_min * 60
    phase_label = "🔥 Работа" if phase == "work" else "🧘 Отдых"

    # Отправляем стартовое сообщение
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("❌ Отменить", callback_data=f"pomo_cancel_{user_id}"))

    msg = bot.send_message(
        chat_id,
        f"{phase_label}\n\n"
        f"⏱ Осталось: *{format_time(duration_sec)}*\n"
        f"`{pomodoro_progress_bar(0, duration_sec)}`",
        reply_markup=kb,
        parse_mode="Markdown"
    )

    active_timers[user_id] = {"cancel": False, "msg_id": msg.message_id, "chat_id": chat_id}

    start_time = time.time()
    last_update = 0

    while True:
        elapsed = int(time.time() - start_time)
        remaining = duration_sec - elapsed

        # Проверка отмены
        if active_timers.get(user_id, {}).get("cancel"):
            try:
                bot.edit_message_text(
                    "❌ Таймер отменён.",
                    chat_id=chat_id,
                    message_id=msg.message_id
                )
            except Exception:
                pass
            user = get_user(user_id)
            user["stats"]["pomodoros_cancelled"] += 1
            save_data()
            active_timers.pop(user_id, None)
            return

        if remaining <= 0:
            break

        # Обновляем экран каждые 30 секунд (чтобы не упереться в лимиты Telegram)
        if elapsed - last_update >= 30 or elapsed == 1:
            try:
                bot.edit_message_text(
                    f"{phase_label}\n\n"
                    f"⏱ Осталось: *{format_time(remaining)}*\n"
                    f"`{pomodoro_progress_bar(elapsed, duration_sec)}`",
                    chat_id=chat_id,
                    message_id=msg.message_id,
                    reply_markup=kb,
                    parse_mode="Markdown"
                )
                last_update = elapsed
            except Exception:
                pass  # Telegram иногда ругается на одинаковое содержимое

        time.sleep(1)

    # Таймер завершился
    active_timers.pop(user_id, None)

    if phase == "work":
        user = get_user(user_id)
        user["stats"]["pomodoros_completed"] += 1
        save_data()

        kb_done = types.InlineKeyboardMarkup()
        kb_done.add(types.InlineKeyboardButton("🧘 Запустить отдых (5 мин)", callback_data=f"pomo_break_{user_id}"))
        kb_done.add(types.InlineKeyboardButton("🔥 Ещё помидор", callback_data="menu_pomodoro"))

        bot.send_message(
            chat_id,
            f"🔔 *{duration_min} минут прошло!*\n\n"
            f"Отличная работа 💪\n"
            f"Всего помидоров завершено: *{user['stats']['pomodoros_completed']}*",
            reply_markup=kb_done,
            parse_mode="Markdown"
        )
    else:
        kb_done = types.InlineKeyboardMarkup()
        kb_done.add(types.InlineKeyboardButton("🔥 Назад к работе", callback_data="menu_pomodoro"))
        bot.send_message(chat_id, "✨ Отдых окончен! Готов к новому раунду?", reply_markup=kb_done)


@bot.message_handler(commands=['pomodoro'])
def pomodoro(message):
    user_id = message.from_user.id

    if user_id in active_timers:
        bot.send_message(message.chat.id, "⚠️ У тебя уже запущен таймер! Сначала отмени его.")
        return

    # Можно указать длительность: /pomodoro 50
    parts = message.text.split()
    duration = 25
    if len(parts) > 1:
        try:
            duration = int(parts[1])
            if not 1 <= duration <= 120:
                bot.send_message(message.chat.id, "⚠️ Длительность должна быть от 1 до 120 минут.")
                return
        except ValueError:
            bot.send_message(message.chat.id, "⚠️ Формат: /pomodoro 25")
            return

    threading.Thread(
        target=run_pomodoro,
        args=(message.chat.id, user_id, duration, "work"),
        daemon=True
    ).start()


# ============ КОНВЕРТЕР (расширенный) ============
# Все коэффициенты к базовой единице
conversions = {
    # Длина → метры
    "длина": {
        "base": "m",
        "units": {"mm": 0.001, "cm": 0.01, "m": 1, "km": 1000,
                  "inch": 0.0254, "ft": 0.3048, "mile": 1609.34}
    },
    # Масса → граммы
    "масса": {
        "base": "g",
        "units": {"mg": 0.001, "g": 1, "kg": 1000, "oz": 28.35, "lb": 453.59}
    },
    # Время → секунды
    "время": {
        "base": "s",
        "units": {"sec": 1, "s": 1, "min": 60, "h": 3600, "day": 86400}
    },
}

# Алиасы для удобства
aliases = {
    "м": "m", "км": "km", "см": "cm", "мм": "mm",
    "кг": "kg", "г": "g", "мг": "mg",
    "ч": "h", "час": "h", "мин": "min", "сек": "s", "день": "day",
    "миля": "mile", "фут": "ft", "дюйм": "inch",
    "фунт": "lb", "унция": "oz",
}


def convert_units(value, from_u, to_u):
    """Универсальная конвертация. Возвращает (result, error)."""
    from_u = aliases.get(from_u, from_u)
    to_u = aliases.get(to_u, to_u)

    # Температура — особый случай
    temp = {"c", "f", "k"}
    if from_u in temp and to_u in temp:
        if from_u == to_u:
            return value, None
        # Сначала в Цельсий
        if from_u == "f":
            c = (value - 32) * 5/9
        elif from_u == "k":
            c = value - 273.15
        else:
            c = value
        # Из Цельсия в нужное
        if to_u == "f":
            return c * 9/5 + 32, None
        elif to_u == "k":
            return c + 273.15, None
        else:
            return c, None

    # Остальные единицы
    for category in conversions.values():
        units = category["units"]
        if from_u in units and to_u in units:
            return value * units[from_u] / units[to_u], None

    return None, "Неподдерживаемые единицы. Поддерживается:\n• Длина: mm, cm, m, km, inch, ft, mile\n• Масса: mg, g, kg, oz, lb\n• Время: s, min, h, day\n• Температура: c, f, k"


@bot.message_handler(commands=['convert'])
def convert(message):
    parts = message.text.split()
    if len(parts) != 4:
        bot.send_message(message.chat.id,
            "⚠️ Формат: `/convert 5 km m`\n\n"
            "Примеры:\n"
            "`/convert 100 c f` — Цельсий в Фаренгейт\n"
            "`/convert 5 km mile`\n"
            "`/convert 2 h min`",
            parse_mode="Markdown")
        return

    try:
        value = float(parts[1].replace(",", "."))
    except ValueError:
        bot.send_message(message.chat.id, "⚠️ Второй аргумент должен быть числом.")
        return

    result, error = convert_units(value, parts[2].lower(), parts[3].lower())
    if error:
        bot.send_message(message.chat.id, f"❌ {error}")
    else:
        bot.send_message(message.chat.id, f"✅ {value} {parts[2]} = *{result:g}* {parts[3]}", parse_mode="Markdown")


# ============ ЗАМЕТКИ ============
@bot.message_handler(commands=['note'])
def add_note(message):
    text = message.text.replace("/note", "", 1).strip()
    if not text:
        bot.send_message(message.chat.id, "⚠️ Формат: /note текст заметки")
        return

    user = get_user(message.from_user.id)
    user["notes"].append({
        "text": text,
        "date": datetime.now().strftime("%d.%m %H:%M")
    })
    save_data()
    bot.send_message(message.chat.id, f"✅ Заметка сохранена! Всего заметок: {len(user['notes'])}")


@bot.message_handler(commands=['notes'])
def list_notes(message):
    user = get_user(message.from_user.id)
    if not user["notes"]:
        bot.send_message(message.chat.id, "📝 У тебя пока нет заметок.\n\nДобавь первую: /note текст")
        return

    text = "📝 *Твои заметки:*\n\n"
    kb = types.InlineKeyboardMarkup(row_width=4)
    buttons = []
    for i, note in enumerate(user["notes"], 1):
        text += f"{i}. _{note['date']}_ — {note['text']}\n\n"
        buttons.append(types.InlineKeyboardButton(f"🗑 {i}", callback_data=f"note_del_{i-1}"))

    if buttons:
        kb.add(*buttons)
        kb.add(types.InlineKeyboardButton("🗑 Удалить все", callback_data="note_del_all"))

    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")


# ============ РАСПИСАНИЕ ============
@bot.message_handler(commands=['schedule'])
def show_schedule(message):
    user = get_user(message.from_user.id)
    text = "📅 *Расписание на день:*\n\n"

    if not user["schedule"]:
        text += "_Расписание пустое._\n\n"
    else:
        for i, item in enumerate(sorted(user["schedule"], key=lambda x: x["time"]), 1):
            text += f"🕐 *{item['time']}* — {item['task']}\n"
        text += "\n"

    text += "Добавить: отправь сообщение в формате `9:00 Физика`"

    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("➕ Добавить", callback_data="sched_add"),
        types.InlineKeyboardButton("🗑 Очистить", callback_data="sched_clear")
    )
    bot.send_message(message.chat.id, text, reply_markup=kb, parse_mode="Markdown")


# Обработчик "9:00 Физика" формата
@bot.message_handler(func=lambda m: m.text and len(m.text.split()) >= 2 and ":" in m.text.split()[0] and m.text.split()[0].replace(":", "").isdigit())
def add_schedule_item(message):
    parts = message.text.split(maxsplit=1)
    time_str = parts[0]
    task = parts[1]

    # Проверка формата времени
    try:
        h, m = map(int, time_str.split(":"))
        if not (0 <= h < 24 and 0 <= m < 60):
            raise ValueError
    except ValueError:
        return

    user = get_user(message.from_user.id)
    user["schedule"].append({"time": f"{h:02d}:{m:02d}", "task": task})
    save_data()
    bot.send_message(message.chat.id, f"✅ Добавлено: {h:02d}:{m:02d} — {task}")


# ============ /choose — случайный выбор ============
@bot.message_handler(commands=['choose'])
def choose(message):
    text = message.text.replace("/choose", "", 1).strip()
    if not text:
        bot.send_message(message.chat.id, "⚠️ Формат: /choose пицца, суши, бургер")
        return

    options = [opt.strip() for opt in text.split(",") if opt.strip()]
    if len(options) < 2:
        bot.send_message(message.chat.id, "⚠️ Нужно минимум 2 варианта через запятую.")
        return

    bot.send_message(message.chat.id, f"🎲 Мой выбор: *{random.choice(options)}*", parse_mode="Markdown")


# ============ /stats ============
@bot.message_handler(commands=['stats'])
def stats(message):
    user = get_user(message.from_user.id)
    s = user["stats"]
    text = (
        f"📊 *Твоя статистика:*\n\n"
        f"🔥 Помидоров завершено: *{s['pomodoros_completed']}*\n"
        f"❌ Помидоров отменено: *{s['pomodoros_cancelled']}*\n"
        f"📝 Заметок: *{len(user['notes'])}*\n"
        f"📅 Дел в расписании: *{len(user['schedule'])}*"
    )
    bot.send_message(message.chat.id, text, parse_mode="Markdown")


# ============ ОБРАБОТЧИК КНОПОК ============
@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    data = call.data
    chat_id = call.message.chat.id
    user_id = call.from_user.id

    # Отмена таймера
    if data.startswith("pomo_cancel_"):
        target_user = int(data.split("_")[2])
        if target_user == user_id and user_id in active_timers:
            active_timers[user_id]["cancel"] = True
            bot.answer_callback_query(call.id, "Таймер отменяется...")
        else:
            bot.answer_callback_query(call.id, "Это не твой таймер 😅")
        return

    # Запуск перерыва после Помодоро
    if data.startswith("pomo_break_"):
        if user_id in active_timers:
            bot.answer_callback_query(call.id, "Сначала заверши текущий таймер")
            return
        threading.Thread(
            target=run_pomodoro,
            args=(chat_id, user_id, 5, "break"),
            daemon=True
        ).start()
        bot.answer_callback_query(call.id, "Отдыхай 🧘")
        return

    # Удаление заметки
    if data.startswith("note_del_"):
        user = get_user(user_id)
        suffix = data[len("note_del_"):]
        if suffix == "all":
            user["notes"] = []
            save_data()
            bot.edit_message_text("✅ Все заметки удалены.", chat_id, call.message.message_id)
        else:
            idx = int(suffix)
            if 0 <= idx < len(user["notes"]):
                user["notes"].pop(idx)
                save_data()
                bot.answer_callback_query(call.id, "Удалено")
                # Перерисовываем список
                list_notes_inline(chat_id, call.message.message_id, user_id)
        return

    # Очистка расписания
    if data == "sched_clear":
        user = get_user(user_id)
        user["schedule"] = []
        save_data()
        bot.edit_message_text("✅ Расписание очищено.", chat_id, call.message.message_id)
        return

    if data == "sched_add":
        bot.answer_callback_query(call.id)
        bot.send_message(chat_id, "📝 Просто отправь сообщение в формате:\n`9:00 Физика`", parse_mode="Markdown")
        return

    # Меню
    bot.answer_callback_query(call.id)
    if data == "menu_pomodoro":
        if user_id in active_timers:
            bot.send_message(chat_id, "⚠️ У тебя уже запущен таймер!")
            return
        threading.Thread(target=run_pomodoro, args=(chat_id, user_id, 25, "work"), daemon=True).start()
    elif data == "menu_motivation":
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("🔄 Ещё", callback_data="menu_motivation"))
        bot.send_message(chat_id, random.choice(quotes), reply_markup=kb)
    elif data == "menu_convert_help":
        bot.send_message(chat_id,
            "🔢 *Конвертер единиц*\n\n"
            "Формат: `/convert число из в`\n\n"
            "Примеры:\n"
            "`/convert 5 km m`\n"
            "`/convert 100 c f`\n"
            "`/convert 2 h min`",
            parse_mode="Markdown")
    elif data == "menu_notes":
        list_notes(call.message)
    elif data == "menu_schedule":
        show_schedule(call.message)
    elif data == "menu_choose_help":
        bot.send_message(chat_id,
            "🎲 *Помощник выбора*\n\n"
            "Формат: `/choose вариант1, вариант2, ...`\n\n"
            "Пример: `/choose пицца, суши, бургер`",
            parse_mode="Markdown")
    elif data == "menu_stats":
        stats(call.message)
    elif data == "menu_help":
        bot.send_message(chat_id, HELP_TEXT, reply_markup=main_menu(), parse_mode="MarkdownV2")


def list_notes_inline(chat_id, msg_id, user_id):
    """Перерисовать список заметок после удаления одной."""
    user = get_user(user_id)
    if not user["notes"]:
        bot.edit_message_text("📝 Заметки кончились.", chat_id, msg_id)
        return

    text = "📝 *Твои заметки:*\n\n"
    kb = types.InlineKeyboardMarkup(row_width=4)
    buttons = []
    for i, note in enumerate(user["notes"], 1):
        text += f"{i}. _{note['date']}_ — {note['text']}\n\n"
        buttons.append(types.InlineKeyboardButton(f"🗑 {i}", callback_data=f"note_del_{i-1}"))

    kb.add(*buttons)
    kb.add(types.InlineKeyboardButton("🗑 Удалить все", callback_data="note_del_all"))

    try:
        bot.edit_message_text(text, chat_id, msg_id, reply_markup=kb, parse_mode="Markdown")
    except Exception:
        pass


# ============ ЗАПУСК ============
print("✅ Бот запущен. Ctrl+C для остановки.")
bot.infinity_polling()