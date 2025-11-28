import googlemaps
import folium
import polyline
from datetime import datetime

API_KEY = 'тут ключ' 
gmaps = googlemaps.Client(key=API_KEY)

def create_smart_route(start_address, delivery_addresses):
    print(f"🌍 Отримано замовлення. Точок доставки: {len(delivery_addresses)}")
    print("⏳ Відправляю запит до Google AI для оптимізації маршруту...")

    now = datetime.now()
    directions_result = gmaps.directions(
        origin=start_address,
        destination=start_address, 
        waypoints=delivery_addresses,
        optimize_waypoints=True, 
        mode="driving",
        departure_time=now
    )

    if not directions_result:
        print("❌ Помилка: не вдалося побудувати маршрут.")
        return

    route = directions_result[0]
    
    total_distance = 0
    total_seconds = 0
    order_of_stops = route['waypoint_order'] 
    
    for leg in route['legs']:
        total_distance += leg['distance']['value']
        total_seconds += leg['duration']['value']
    
    total_km = total_distance / 1000
    total_min = total_seconds / 60
    
    print(f"✅ Маршрут оптимізовано!")
    print(f"📊 Загальна дистанція: {total_km:.1f} км")
    print(f"⏱️ Загальний час: {int(total_min)} хв")

    start_lat = route['legs'][0]['start_location']['lat']
    start_lng = route['legs'][0]['start_location']['lng']
    m = folium.Map(location=[start_lat, start_lng], zoom_start=13)

    decoded_points = polyline.decode(route['overview_polyline']['points'])
    folium.PolyLine(decoded_points, color="blue", weight=5, opacity=0.7).add_to(m)

    folium.Marker(
        [start_lat, start_lng],
        popup=f"🏢 СКЛАД (Старт/Фініш)<br>{start_address}",
        icon=folium.Icon(color='black', icon='home')
    ).add_to(m)
    
    for i, leg in enumerate(route['legs']):
        if i == len(route['legs']) - 1:
            break
            
        stop_lat = leg['end_location']['lat']
        stop_lng = leg['end_location']['lng']
        address = leg['end_address']
        
        folium.Marker(
            [stop_lat, stop_lng],
            popup=f"📦 Зупинка №{i+1}<br>{address}<br>Відстань: {leg['distance']['text']}",
            icon=folium.Icon(color='red', icon='user', prefix='fa'),
            tooltip=f"Stop {i+1}"
        ).add_to(m)

    m.save("smart_logistics.html")
    print("🚀 Карта готова: smart_logistics.html")

my_warehouse = "Kyiv, Maidan Nezalezhnosti" 

my_clients = [
    "Kyiv, Ocean Plaza",          
    "Kyiv, Zoo",                  
    "Kyiv, Dream Town",           
    "Kyiv, Gulliver Mall",        
    "Kyiv, Hydropark"             
]

if __name__ == "__main__":
    try:
        create_smart_route(my_warehouse, my_clients)
    except Exception as e:
        print(f"Error: {e}")