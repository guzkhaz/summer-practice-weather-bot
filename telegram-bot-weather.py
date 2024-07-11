"""Telegram Bot on Yandex Cloud Function."""

import io
import datetime
import os
import json
import requests


FUNC_RESPONSE = {
    'statusCode': 200,
    'body': ''
}

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
OPEN_WEATHER_MAP_TOKEN = os.environ.get("OPEN_WEATHER_MAP_TOKEN")
SPEECHKIT_API_KEY = os.environ.get("SPEECHKIT_API_KEY")
TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GEOCODING_URL= f"http://api.openweathermap.org/geo/1.0/direct?appid={OPEN_WEATHER_MAP_TOKEN}"
SPEECHKIT_URL = 'https://stt.api.cloud.yandex.net/speech/v1/stt:recognize'
TELEGRAM_FILE_API_URL = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}"

def generate_response_template(weather):
    response_template = ""
    response_template += f'{weather["description"].capitalize()}.\n'
    response_template += f'Температура {weather["temperature"]} ℃, ощущается как {weather["feels_like"]} ℃.\n'
    response_template += f'Атмосферное давление {weather["pressure"]} мм рт. ст.\n'
    response_template += f'Влажность {weather["humidity"]} %.\n'
    response_template += f'Видимость {weather["visibility"]} метров.\n'
    response_template += f'Ветер {weather["wind_speed"]} м/с {weather["wind_direction"]}.\n'
    response_template += f'Восход солнца {weather["sunrise_time"]} МСК. Закат {weather["sunset_time"]} МСК.'

    return response_template

def get_coordinates_by_city_name(name,message_in):
    response = requests.get(url=f'{GEOCODING_URL}&q={name}')

    locations = response.json()

    if len(locations) > 0:
        location = locations[0]
        return {
            "latitude": location["lat"],
            "longitude": location["lon"]
        }

def get_weather_by_coordinates(latitude, longitude):
    try:
        url = f"http://api.openweathermap.org/data/2.5/weather?lat={latitude}&lon={longitude}&appid={OPEN_WEATHER_MAP_TOKEN}&lang=ru"

        response = requests.get(url)
        response.raise_for_status()

        weather_data = response.json()

        weather_description = weather_data["weather"][0]["description"]

        #Переводим из Кельвинов в Цельсия
        temperature = round(weather_data["main"]["temp"] - 273.15, 1) 
        feels_like = round(weather_data["main"]["feels_like"] - 273.15, 1)

        pressure = round(weather_data["main"]["pressure"] * 0.75006375541921)
        humidity = weather_data["main"]["humidity"] 
        visibility = weather_data["visibility"]  

        wind_speed = weather_data["wind"]["speed"]  
        wind_direction_deg = weather_data["wind"]["deg"] 

        # Перевод градусов ветра в текстовое обозначение
        wind_direction = ""
        if wind_direction_deg is not None:
            if 22.5 <= wind_direction_deg < 67.5:
                wind_direction = "СВ"
            elif 67.5 <= wind_direction_deg < 112.5:
                wind_direction = "В"
            elif 112.5 <= wind_direction_deg < 157.5:
                wind_direction = "ЮВ"
            elif 157.5 <= wind_direction_deg < 202.5:
                wind_direction = "Ю"
            elif 202.5 <= wind_direction_deg < 247.5:
                wind_direction = "ЮЗ"
            elif 247.5 <= wind_direction_deg < 292.5:
                wind_direction = "З"
            elif 292.5 <= wind_direction_deg < 337.5:
                wind_direction = "СЗ"
            else:
                wind_direction = "С"

        sunrise_timestamp = weather_data["sys"]["sunrise"]
        sunset_timestamp = weather_data["sys"]["sunset"]

        sunrise_datetime = datetime.datetime.fromtimestamp(sunrise_timestamp)
        sunset_datetime = datetime.datetime.fromtimestamp(sunset_timestamp)
        moscow_timezone = datetime.timezone(datetime.timedelta(hours=3))

        sunrise_time = sunrise_datetime.astimezone(moscow_timezone).strftime("%H:%M")
        sunset_time = sunset_datetime.astimezone(moscow_timezone).strftime("%H:%M")

        weather = {
            "description": weather_description,
            "temperature": temperature,
            "feels_like": feels_like,
            "pressure": pressure,
            "humidity": humidity,
            "visibility": visibility,
            "wind_speed": wind_speed,
            "wind_direction": wind_direction,
            "sunrise_time": sunrise_time,
            "sunset_time": sunset_time
        }

        return weather

    except requests.exceptions.RequestException as ex:
        print(f"Произошла ошибка: {ex}")
        raise

def generate_text_from_speech(audio):
    auth_header = f"Api-Key {SPEECHKIT_API_KEY}"
    response = requests.post(url=SPEECHKIT_URL,data=audio,headers={'Authorization': auth_header})

    return response.json()['result']

def send_message(text, message):

    message_id = message['message_id']
    chat_id = message['chat']['id']
    reply_message = {'chat_id': chat_id,
                     'text': text,
                     'reply_to_message_id': message_id}

    requests.post(url=f'{TELEGRAM_API_URL}/sendMessage', json=reply_message)


def download_file(file_id):
    url = f"{TELEGRAM_API_URL}/getFile?file_id={file_id}"
    result = requests.get(url)
    file_path = result.json()['result']["file_path"]

    url = f"{TELEGRAM_FILE_API_URL}/{file_path}?file_id={file_id}"
    response = requests.get(url)

    return response.content

def handler(event, context):
    try:
        if TELEGRAM_BOT_TOKEN is None:
            return FUNC_RESPONSE

        update = json.loads(event['body'])
        text = None
        if 'message' not in update:
            return FUNC_RESPONSE
        message_in = update['message']

        print(message_in)
        if 'text' not in message_in:
            if 'voice' not in message_in:
                if 'location' not in message_in:
                    send_message("Я не могу ответить на такой тип сообщения.\nНо могу ответить на:\n- Текстовое сообщение с названием населенного пункта.\n- Голосовое сообщение с названием населенного пункта.\n- Сообщение с геопозицией.", message_in)
                    return FUNC_RESPONSE

        if 'voice' in message_in:
            if message_in['voice']['duration'] > 30:
                send_message("Я не могу обработать это голосовое сообщение.", message_in)
                return FUNC_RESPONSE
            audio_bytes = download_file(message_in['voice']['file_id'])
            text = generate_text_from_speech(audio_bytes)

        if 'text' in message_in:
            if message_in['text'] == '/start' or message_in['text'] == '/help':
                message = "Я расскажу о текущей погоде для населенного пункта.\nЯ могу ответить на:\n- Текстовое сообщение с названием населенного пункта.\n- Голосовое сообщение с названием населенного пункта.\n- Сообщение с геопозицией."
                send_message(message, message_in)
                return FUNC_RESPONSE
            else: text = message_in['text']

        if 'location' in message_in:
            weather = get_weather_by_coordinates(message_in['location']['latitude'], message_in['location']['longitude'])
            send_message(generate_response_template(weather), message_in)
            return FUNC_RESPONSE

        print('Распознанный текст: ',text)
        if not text:
            send_message("Я не нашел населенный пункт <Пустой ввод>", message_in)
            return FUNC_RESPONSE

        coordinates = get_coordinates_by_city_name(text, message_in)
        if coordinates:
            weather = get_weather_by_coordinates(coordinates["latitude"], coordinates["longitude"])
        else:
            send_message(f"Я не нашел населенный пункт <{text}>", message_in)
            return FUNC_RESPONSE

        send_message(generate_response_template(weather), message_in)

        return FUNC_RESPONSE
    except (Exception):
        return FUNC_RESPONSE