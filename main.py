import googlemaps
import folium
import polyline
from datetime import datetime
import logging
import os

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler, # Додали для обробки натискання кнопок
)

# --- НАЛАШТУВАННЯ ---
# Вставте сюди ваші НОВІ ключі
GOOGLE_API_KEY = 'ключ' 
TELEGRAM_TOKEN = 'ключ'

# Ініціалізація клієнта Google
gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

# Словник для зберігання маршрутів: {user_id: ["Адреса 1", "Адреса 2"]}
user_routes = {}

# Словник для зберігання режиму пересування: {user_id: "driving"}
user_modes = {}

# Налаштування логування
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- ЛОГІКА GOOGLE MAPS ---
def create_smart_route_file(user_id, points, travel_mode="driving"):
    """
    travel_mode може бути: 'driving', 'walking', 'bicycling'
    """
    if len(points) < 2:
        return None, "Мало точок для маршруту! Потрібен хоча б Склад і 1 Клієнт."

    start_address = points[0]      # Перша точка - склад
    delivery_addresses = points[1:] # Решта - клієнти

    # Переклад режиму для красивого виводу
    mode_names = {"driving": "🚗 Авто", "walking": "🚶 Пішки", "bicycling": "🚲 Велосипед"}
    mode_ukr = mode_names.get(travel_mode, travel_mode)

    print(f"🌍 Користувач {user_id}: Будуємо маршрут ({mode_ukr})...")

    try:
        now = datetime.now()
        
        # Запит до Google API
        directions_result = gmaps.directions(
            origin=start_address,
            destination=start_address, # Кільцевий маршрут
            waypoints=delivery_addresses,
            optimize_waypoints=True,   # Оптимізація порядку точок
            mode=travel_mode,          # <--- ТУТ МИ ПЕРЕДАЄМО ОБРАНИЙ РЕЖИМ
            departure_time=now
        )
    except Exception as e:
        return None, f"Помилка Google API: {e}"

    if not directions_result:
        return None, "Google не зміг побудувати маршрут. Перевірте адреси або доступність цього транспорту."

    route = directions_result[0]
    
    # Статистика
    total_distance = 0
    total_seconds = 0
    for leg in route['legs']:
        total_distance += leg['distance']['value']
        total_seconds += leg['duration']['value']
    
    total_km = total_distance / 1000
    total_min = total_seconds / 60
    
    stats_text = (
        f"✅ <b>Маршрут оптимізовано!</b>\n"
        f"⚙️ Режим: <b>{mode_ukr}</b>\n"
        f"📊 Дистанція: {total_km:.1f} км\n"
        f"⏱️ Час у дорозі: {int(total_min)} хв"
    )

    # Візуалізація
    start_lat = route['legs'][0]['start_location']['lat']
    start_lng = route['legs'][0]['start_location']['lng']
    
    m = folium.Map(location=[start_lat, start_lng], zoom_start=13)

    # Малювання лінії
    decoded_points = polyline.decode(route['overview_polyline']['points'])
    folium.PolyLine(decoded_points, color="blue", weight=5, opacity=0.7).add_to(m)

    # Маркер Складу
    folium.Marker(
        [start_lat, start_lng],
        popup=f"🏢 СКЛАД<br>{start_address}",
        icon=folium.Icon(color='black', icon='home')
    ).add_to(m)
    
    # Маркери клієнтів
    for i, leg in enumerate(route['legs']):
        if i == len(route['legs']) - 1: break 
            
        stop_lat = leg['end_location']['lat']
        stop_lng = leg['end_location']['lng']
        address = leg['end_address']
        
        folium.Marker(
            [stop_lat, stop_lng],
            popup=f"📦 Зупинка {i+1}<br>{address}",
            icon=folium.Icon(color='red', icon='user', prefix='fa')
        ).add_to(m)

    filename = f"route_{user_id}.html"
    m.save(filename)
    
    return filename, stats_text


# --- TELEGRAM HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_routes[user_id] = []
    user_modes[user_id] = "driving" # За замовчуванням авто
    
    await update.message.reply_text(
        "🚛 <b>Вітаю в Логістичному Боті!</b>\n\n"
        "Я допоможу побудувати оптимальний маршрут.\n"
        "Перша додана точка — це <b>СКЛАД</b>.\n\n"
        "<b>Команди:</b>\n"
        "/add [адреса] - додати точку\n"
        "/mode - змінити тип транспорту (Авто/Пішки/Вело)\n"
        "/list - показати список\n"
        "/del [номер] - видалити точку\n"
        "/new - очистити все\n"
        "/finish - розрахувати маршрут",
        parse_mode=ParseMode.HTML
    )

async def new_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_routes[update.effective_user.id] = []
    user_modes[update.effective_user.id] = "driving"
    await update.message.reply_text("🗑️ Маршрут очищено. Режим скинуто на 🚗 Авто.")

async def add_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_routes: user_routes[user_id] = []
    
    address = " ".join(context.args)
    if not address:
        await update.message.reply_text("⚠️ Вкажіть адресу! Наприклад: <code>/add Kyiv, Khreshchatyk 1</code>", parse_mode=ParseMode.HTML)
        return

    # Захист від дублікатів (простий)
    if user_routes[user_id] and user_routes[user_id][-1] == address:
        return

    user_routes[user_id].append(address)
    count = len(user_routes[user_id])
    role = "🏢 СКЛАД (База)" if count == 1 else f"📦 Клієнт #{count-1}"
    
    await update.message.reply_text(f"Додано: <b>{role}</b>\n📍 {address}", parse_mode=ParseMode.HTML)

# --- НОВА ЛОГІКА ДЛЯ ВИБОРУ РЕЖИМУ ---
async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Створюємо кнопки
    keyboard = [
        [InlineKeyboardButton("Автомобіль", callback_data='mode_driving')],
        [InlineKeyboardButton("Пішки", callback_data='mode_walking')],
        [InlineKeyboardButton("Велосипед", callback_data='mode_bicycling')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    current_mode = user_modes.get(update.effective_user.id, "driving")
    await update.message.reply_text(f"Поточний режим: <b>{current_mode}</b>\nОберіть новий:", reply_markup=reply_markup, parse_mode=ParseMode.HTML)

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer() # Обов'язково відповідаємо серверу, щоб кнопка перестала "крутитися"

    # Отримуємо дані з кнопки (наприклад, "mode_walking")
    data = query.data
    
    if data.startswith("mode_"):
        new_mode = data.replace("mode_", "") # Отримуємо чистий режим ("walking")
        user_modes[query.from_user.id] = new_mode
        
        mode_names = {"driving": "🚗 Автомобіль", "walking": "🚶 Пішки", "bicycling": "🚲 Велосипед"}
        nice_name = mode_names.get(new_mode, new_mode)
        
        # Редагуємо повідомлення, прибираючи кнопки і показуючи результат
        await query.edit_message_text(text=f"✅ Режим змінено на: <b>{nice_name}</b>", parse_mode=ParseMode.HTML)

# -------------------------------------

async def list_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points = user_routes.get(user_id, [])
    current_mode = user_modes.get(user_id, "driving")
    
    if not points:
        await update.message.reply_text("Список порожній.")
        return

    text = f"⚙️ Режим: <b>{current_mode}</b>\n📋 <b>Маршрутний лист:</b>\n\n"
    for i, p in enumerate(points):
        role = "🏢 СКЛАД" if i == 0 else f"📦 Точка {i}"
        text += f"{i}. {role}: {p}\n"
    
    text += "\n/del [номер] - видалити\n/finish - розрахувати"
    await update.message.reply_text(text, parse_mode=ParseMode.HTML)

async def delete_point(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points = user_routes.get(user_id, [])
    try:
        index = int(context.args[0])
        removed = points.pop(index)
        await update.message.reply_text(f"❌ Видалено: {removed}")
    except (IndexError, ValueError):
        await update.message.reply_text("⚠️ Невірний номер.")

async def finish_route(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    points = user_routes.get(user_id, [])
    # Отримуємо режим користувача (або driving, якщо немає)
    mode = user_modes.get(user_id, "driving")
    
    if len(points) < 2:
        await update.message.reply_text("⚠️ Додайте хоча б Склад і 1 Клієнта!")
        return

    await update.message.reply_text(f"⏳ Оптимізую маршрут ({mode})...")

    # Передаємо режим у функцію
    filename, stats = create_smart_route_file(user_id, points, travel_mode=mode)

    if filename:
        await update.message.reply_text(stats, parse_mode=ParseMode.HTML)
        try:
            with open(filename, 'rb') as f:
                 await update.message.reply_document(document=f, filename=f"route_{mode}.html")
        except Exception as e:
            await update.message.reply_text(f"Помилка відправки: {e}")
        try:
            os.remove(filename)
        except OSError:
            pass
    else:
        await update.message.reply_text(stats)

if __name__ == "__main__":
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("new", new_route))
    app.add_handler(CommandHandler("add", add_point))
    app.add_handler(CommandHandler("list", list_points))
    app.add_handler(CommandHandler("del", delete_point))
    app.add_handler(CommandHandler("mode", choose_mode)) # Нова команда
    app.add_handler(CommandHandler("finish", finish_route))
    
    # Обробник натискання кнопок
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Бот запущено...")
    app.run_polling()