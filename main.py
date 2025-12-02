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
    CallbackQueryHandler,
)

GOOGLE_API_KEY = 'ключ' 
TELEGRAM_TOKEN = 'ключ'

gmaps = googlemaps.Client(key=GOOGLE_API_KEY)

user_routes = {}

user_modes = {}

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

def create_smart_route_file(user_id, points, travel_mode="driving"):
    """
    travel_mode може бути: 'driving', 'walking', 'bicycling'
    """
    if len(points) < 2:
        return None, "Мало точок для маршруту! Потрібен хоча б Склад і 1 Клієнт."

    start_address = points[0]      
    delivery_addresses = points[1:]

    mode_names = {"driving": "🚗 Авто", "walking": "🚶 Пішки", "bicycling": "🚲 Велосипед"}
    mode_ukr = mode_names.get(travel_mode, travel_mode)

    print(f"🌍 Користувач {user_id}: Будуємо маршрут ({mode_ukr})...")

    try:
        now = datetime.now()
        
        directions_result = gmaps.directions(
            origin=start_address,
            destination=start_address, 
            waypoints=delivery_addresses,
            optimize_waypoints=True,   
            mode=travel_mode,          
            departure_time=now
        )
    except Exception as e:
        return None, f"Помилка Google API: {e}"

    if not directions_result:
        return None, "Google не зміг побудувати маршрут. Перевірте адреси або доступність цього транспорту."

    route = directions_result[0]
    
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

    start_lat = route['legs'][0]['start_location']['lat']
    start_lng = route['legs'][0]['start_location']['lng']
    
    m = folium.Map(location=[start_lat, start_lng], zoom_start=13)

    decoded_points = polyline.decode(route['overview_polyline']['points'])
    folium.PolyLine(decoded_points, color="blue", weight=5, opacity=0.7).add_to(m)

    folium.Marker(
        [start_lat, start_lng],
        popup=f"🏢 СКЛАД<br>{start_address}",
        icon=folium.Icon(color='black', icon='home')
    ).add_to(m)
    
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



async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_routes[user_id] = []
    user_modes[user_id] = "driving" 
    
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

    if user_routes[user_id] and user_routes[user_id][-1] == address:
        return

    user_routes[user_id].append(address)
    count = len(user_routes[user_id])
    role = "🏢 СКЛАД (База)" if count == 1 else f"📦 Клієнт #{count-1}"
    
    await update.message.reply_text(f"Додано: <b>{role}</b>\n📍 {address}", parse_mode=ParseMode.HTML)

async def choose_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    await query.answer() 
    data = query.data
    
    if data.startswith("mode_"):
        new_mode = data.replace("mode_", "") 
        user_modes[query.from_user.id] = new_mode
        
        mode_names = {"driving": "🚗 Автомобіль", "walking": "🚶 Пішки", "bicycling": "🚲 Велосипед"}
        nice_name = mode_names.get(new_mode, new_mode)
        
        await query.edit_message_text(text=f"✅ Режим змінено на: <b>{nice_name}</b>", parse_mode=ParseMode.HTML)


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
    mode = user_modes.get(user_id, "driving")
    
    if len(points) < 2:
        await update.message.reply_text("⚠️ Додайте хоча б Склад і 1 Клієнта!")
        return

    await update.message.reply_text(f"⏳ Оптимізую маршрут ({mode})...")

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
    app.add_handler(CommandHandler("mode", choose_mode)) 
    app.add_handler(CommandHandler("finish", finish_route))
    
    app.add_handler(CallbackQueryHandler(button_callback))

    print("🤖 Бот запущено...")
    app.run_polling()