import time
import requests
import xml.etree.ElementTree as ET
import threading
import webbrowser
import os
import re
import sys
import smtplib
from email.mime.text import MIMEText
from flask import Flask, render_template, request, jsonify

# Set stdout to utf-8 to avoid charmap errors on Windows
if sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
    
app = Flask(__name__)

# ================= GLOBAL STATE =================
agent_running = False
agent_thread = None
agent_config = {
    'channel_id': '',
    'bot_token': '8887322177:AAEK8fsl3hotiAUqqmPBZ2KdaRsPpkIFVYM',
    'chat_id': '@antitestagent',
    'discord_webhook': '',
    'email_user': '',
    'email_pass': '',
    'email_to': '',
    'openai_api_key': '',
    'openai_prompt': 'Напиши короткий, привлекательный анонс для нового YouTube видео. Название: {title}. Ссылка: {link}',
    'check_interval': 1800 # 30 минут
}
# Файл для хранения ID последнего отправленного видео
LAST_VIDEO_FILE = 'last_video_id.txt'

def get_latest_videos(channel_id, limit=5):
    """Получает последние видео с канала через RSS фид (не требует API ключа)"""
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
        
        videos = []
        for entry in root.findall('atom:entry', ns)[:limit]:
            video_id = entry.find('yt:videoId', ns).text
            title = entry.find('atom:title', ns).text
            link = entry.find('atom:link', ns).attrib['href']
            
            videos.append({
                'id': video_id,
                'title': title,
                'link': link
            })
            
        return videos
    except Exception as e:
        print(f"Ошибка при получении данных с YouTube: {e}")
        return []

def send_telegram_message(text, bot_token, chat_id):
    """Отправляет сообщение в Telegram"""
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print(f"Сообщение успешно отправлено в Telegram!")
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Telegram: {e}")

def send_discord_message(text, webhook_url):
    """Отправляет сообщение в Discord через Webhook"""
    if not webhook_url: return
    try:
        response = requests.post(webhook_url, json={"content": text}, timeout=10)
        response.raise_for_status()
        print(f"Сообщение успешно отправлено в Discord!")
    except Exception as e:
        print(f"Ошибка при отправке сообщения в Discord: {e}")

def send_email_message(subject, text, user, password, to_email):
    """Отправляет email через Gmail SMTP"""
    if not all([user, password, to_email]): return
    try:
        msg = MIMEText(text)
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_email
        
        server = smtplib.SMTP_SSL('smtp.gmail.com', 465)
        server.login(user, password)
        server.send_message(msg)
        server.quit()
        print(f"Сообщение успешно отправлено на Email!")
    except Exception as e:
        print(f"Ошибка при отправке Email: {e}")

def send_yahoo_email_message(subject, text, user, password, to_email):
    """Отправляет email через Yahoo SMTP"""
    if not all([user, password, to_email]): return
    try:
        msg = MIMEText(text)
        msg['Subject'] = subject
        msg['From'] = user
        msg['To'] = to_email
        
        server = smtplib.SMTP_SSL('smtp.mail.yahoo.com', 465)
        server.login(user, password)
        server.send_message(msg)
        server.quit()
        print(f"Сообщение успешно отправлено через Yahoo Mail!")
    except Exception as e:
        print(f"Ошибка при отправке Yahoo Mail: {e}")

# ================= ROCKSTAR / GTA 6 MODULE =================
ROCKSTAR_CHANNEL_ID = 'UCkfYjCGsoNVyuJEHLOBn0YQ'

def get_rockstar_latest_video():
    """Получает последнее видео с официального канала Rockstar Games через RSS"""
    url = f'https://www.youtube.com/feeds/videos.xml?channel_id={ROCKSTAR_CHANNEL_ID}'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        ns = {'atom': 'http://www.w3.org/2005/Atom', 'yt': 'http://www.youtube.com/xml/schemas/2015'}
        entry = root.find('atom:entry', ns)
        if entry is None:
            return None
        video_id = entry.find('yt:videoId', ns).text
        title = entry.find('atom:title', ns).text
        link = entry.find('atom:link', ns).attrib['href']
        # Thumbnail
        thumbnail = f'https://img.youtube.com/vi/{video_id}/maxresdefault.jpg'
        return {'id': video_id, 'title': title, 'link': link, 'thumbnail': thumbnail}
    except Exception as e:
        print(f"Ошибка при получении видео Rockstar: {e}")
        return None

def generate_chatgpt_message(title, link, api_key, prompt):
    if not api_key:
        return None
    try:
        # pyrefly: ignore [missing-import]
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        
        user_prompt = prompt.replace('{title}', title).replace('{link}', link)
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты креативный ассистент, который пишет привлекательные анонсы для видео."},
                {"role": "user", "content": user_prompt}
            ]
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"Ошибка ChatGPT: {e}")
        return None

def agent_worker():
    """Фоновый процесс агента, который периодически проверяет новые видео."""
    global agent_running, agent_config
    print("Агент запущен в фоновом режиме.")
    
    while agent_running:
        channel_id = agent_config['channel_id']
        bot_token = agent_config['bot_token']
        chat_id = agent_config['chat_id']
        discord_webhook = agent_config['discord_webhook']
        email_user = agent_config['email_user']
        email_pass = agent_config['email_pass']
        email_to = agent_config['email_to']
        
        if channel_id:
            print(f"Проверка канала {channel_id}...")
            videos = get_latest_videos(channel_id, limit=1) # Берем только самое последнее
            
            if videos:
                video = videos[0]
                video_id = video['id']
                
                # Проверяем, не отправляли ли мы это видео уже
                last_sent = ""
                if os.path.exists(LAST_VIDEO_FILE):
                    with open(LAST_VIDEO_FILE, 'r', encoding='utf-8') as f:
                        last_sent = f.read().strip()
                
                if video_id != last_sent:
                    # Новое видео
                    title = video['title'].replace('[', '(').replace(']', ')')
                    
                    openai_api_key = agent_config.get('openai_api_key')
                    openai_prompt = agent_config.get('openai_prompt', '')
                    
                    custom_message = None
                    if openai_api_key:
                        print("Генерация сообщения через ChatGPT...")
                        custom_message = generate_chatgpt_message(title, video['link'], openai_api_key, openai_prompt)

                    tg_message = custom_message if custom_message else f"📺 *Новое видео!*\n\n[{title}]({video['link']})"
                    dc_message = custom_message if custom_message else f"📺 **Новое видео!**\n{title}\n{video['link']}"
                    em_message = custom_message if custom_message else f"Вышло новое видео: {title}\nСсылка: {video['link']}"

                    if bot_token and chat_id:
                        send_telegram_message(tg_message, bot_token, chat_id)
                        
                    if discord_webhook:
                        send_discord_message(dc_message, discord_webhook)
                        
                    if email_user and email_pass and email_to:
                        send_email_message("Новое видео на YouTube!", em_message, email_user, email_pass, email_to)
                    
                    with open(LAST_VIDEO_FILE, 'w', encoding='utf-8') as f:
                        f.write(video_id)
                else:
                    print("Новых видео нет.")
        
        # Ждем перед следующей проверкой, разбивая на мелкие паузы, чтобы быстро реагировать на остановку
        for _ in range(agent_config['check_interval']):
            if not agent_running:
                break
            time.sleep(1)
            
    print("Агент остановлен.")

# ================= FLASK WEB SERVER =================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def status():
    return jsonify({
        'running': agent_running,
        'channel_id': agent_config['channel_id'],
        'bot_token': agent_config['bot_token'],
        'chat_id': agent_config['chat_id'],
        'discord_webhook': agent_config['discord_webhook'],
        'email_user': agent_config['email_user'],
        'email_pass': agent_config['email_pass'],
        'email_to': agent_config['email_to'],
        'openai_api_key': agent_config.get('openai_api_key', ''),
        'openai_prompt': agent_config.get('openai_prompt', '')
    })

@app.route('/api/find_channel', methods=['GET'])
def find_channel():
    handle = request.args.get('handle', '').strip()
    if not handle:
        return jsonify({'error': 'Пустой запрос'})
        
    if not handle.startswith('@'):
        handle = '@' + handle
        
    try:
        r = requests.get(f"https://www.youtube.com/{handle}", timeout=10)
        match = re.search(r'"channelId":"(UC[\w-]+)"', r.text)
        if match:
            return jsonify({'id': match.group(1)})
        else:
            return jsonify({'error': 'ID не найден. Возможно, неверный формат (нужен @username) или канал не существует.'})
    except Exception as e:
        return jsonify({'error': str(e)})

@app.route('/api/start_agent', methods=['POST'])
def start_agent():
    global agent_running, agent_thread, agent_config
    
    if agent_running:
        return jsonify({'success': False, 'error': 'Агент уже запущен'})
        
    data = request.json
    agent_config['channel_id'] = data.get('channel_id', '').strip()
    agent_config['bot_token'] = data.get('bot_token', '').strip()
    agent_config['chat_id'] = data.get('chat_id', '').strip()
    agent_config['discord_webhook'] = data.get('discord_webhook', '').strip()
    agent_config['email_user'] = data.get('email_user', '').strip()
    agent_config['email_pass'] = data.get('email_pass', '').strip()
    agent_config['email_to'] = data.get('email_to', '').strip()
    agent_config['openai_api_key'] = data.get('openai_api_key', '').strip()
    agent_config['openai_prompt'] = data.get('openai_prompt', '').strip()
    
    if not agent_config['channel_id']:
        return jsonify({'success': False, 'error': 'ID канала обязателен'})
        
    agent_running = True
    agent_thread = threading.Thread(target=agent_worker, daemon=True)
    agent_thread.start()
    
    return jsonify({'success': True})

@app.route('/api/stop_agent', methods=['POST'])
def stop_agent():
    global agent_running
    agent_running = False
    return jsonify({'success': True})

@app.route('/api/ai_build_path', methods=['POST'])
def ai_build_path():
    data = request.json
    history = data.get('history', [])
    api_key = data.get('api_key') or agent_config.get('openai_api_key')
    
    if not api_key:
        return jsonify({"success": False, "error": "Пожалуйста, настройте ChatGPT модуль и введите OpenAI API Key для использования AI-ассистента."})
        
    try:
        from openai import OpenAI
        import json
        client = OpenAI(api_key=api_key)
        
        system_prompt = """
        Ты дружелюбный ИИ-ассистент, который помогает пользователю собрать и настроить автоматизацию.
        Система всегда начинается с модуля YouTube (требуется channel_id, можно найти по @username) и может подключать:
        - tg: Telegram (требуется bot_token, chat_id)
        - dc: Discord (требуется webhook_url)
        - em: Email (требуется email_user, email_pass, email_to)
        - cg: ChatGPT (используется для рерайта текста)
        - yh: Yahoo Mail (требуется yahoo_user, yahoo_pass, yahoo_to)
        
        Твоя задача — понять, что хочет пользователь, включить нужные модули и ЗАПРАШИВАТЬ у пользователя недостающие настройки (токены, ID, почты). Если пользователь дает @username ютуба, скажи ему, что ты используешь это, но для точного ID нужно воспользоваться поиском в модуле YouTube или сам попроси точный ID (UC...).
        
        ОБЯЗАТЕЛЬНО отвечай только в формате JSON:
        {
            "reply": "Твой ответ пользователю на русском языке. Спрашивай недостающие данные (токены, ID и т.д.) здесь.",
            "modules": ["список", "кодов", "модулей", "которые", "надо", "включить", "например: tg, dc"],
            "config": {
                "channel_id": "значение если дал пользователь",
                "bot_token": "значение если дал",
                "chat_id": "значение если дал",
                "discord_webhook": "...",
                "email_user": "...",
                "email_pass": "...",
                "email_to": "...",
                "yahoo_user": "...",
                "yahoo_pass": "...",
                "yahoo_to": "..."
            }
        }
        В 'config' передавай только те ключи, которые пользователь явно предоставил. Остальные не пиши.
        Если пользователь дает тебе данные, хвали его и проси следующие.
        """
        
        messages = [{"role": "system", "content": system_prompt}]
        for msg in history:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})
            
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=messages,
            response_format={ "type": "json_object" }
        )
        
        result_text = response.choices[0].message.content.strip()
        result_json = json.loads(result_text)
        
        return jsonify({"success": True, "result": result_json})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route('/api/send_gta_trailer', methods=['POST'])
def send_gta_trailer():
    """Отправляет последний трейлер Rockstar на выбранные платформы"""
    data = request.json
    platforms = data.get('platforms', [])
    
    video = get_rockstar_latest_video()
    if not video:
        return jsonify({'success': False, 'error': 'Не удалось получить видео с канала Rockstar Games. Попробуйте позже.'})
    
    title = video['title'].replace('[', '(').replace(']', ')')
    link = video['link']
    
    results = []
    errors = []
    
    if 'tg' in platforms:
        bot_token = data.get('bot_token', '').strip()
        chat_id = data.get('chat_id', '').strip()
        if bot_token and chat_id:
            msg = f"🎮 *GTA 6 | Rockstar Games*\n\n*{title}*\n\n{link}"
            try:
                send_telegram_message(msg, bot_token, chat_id)
                results.append('Telegram')
            except Exception as e:
                errors.append(f'Telegram: {e}')
        else:
            errors.append('Telegram: не заполнен Bot Token или Chat ID')
    
    if 'dc' in platforms:
        webhook = data.get('discord_webhook', '').strip()
        if webhook:
            msg = f"🎮 **GTA 6 | Rockstar Games**\n**{title}**\n{link}"
            try:
                send_discord_message(msg, webhook)
                results.append('Discord')
            except Exception as e:
                errors.append(f'Discord: {e}')
        else:
            errors.append('Discord: не заполнен Webhook URL')
    
    if 'em' in platforms:
        email_user = data.get('email_user', '').strip()
        email_pass = data.get('email_pass', '').strip()
        email_to = data.get('email_to', '').strip()
        if email_user and email_pass and email_to:
            subject = f'🎮 Rockstar: {title}'
            body = f"Новое видео от Rockstar Games!\n\n{title}\n\nСмотреть: {link}"
            try:
                send_email_message(subject, body, email_user, email_pass, email_to)
                results.append('Gmail')
            except Exception as e:
                errors.append(f'Gmail: {e}')
        else:
            errors.append('Gmail: не заполнены данные почты')
    
    if 'yh' in platforms:
        yahoo_user = data.get('yahoo_user', '').strip()
        yahoo_pass = data.get('yahoo_pass', '').strip()
        yahoo_to = data.get('yahoo_to', '').strip()
        if yahoo_user and yahoo_pass and yahoo_to:
            subject = f'🎮 Rockstar: {title}'
            body = f"Новое видео от Rockstar Games!\n\n{title}\n\nСмотреть: {link}"
            try:
                send_yahoo_email_message(subject, body, yahoo_user, yahoo_pass, yahoo_to)
                results.append('Yahoo Mail')
            except Exception as e:
                errors.append(f'Yahoo Mail: {e}')
        else:
            errors.append('Yahoo Mail: не заполнены данные')
    
    if not results and errors:
        return jsonify({'success': False, 'error': '; '.join(errors)})
    
    return jsonify({
        'success': True,
        'video': video,
        'sent_to': results,
        'errors': errors
    })

def open_browser():
    time.sleep(1.5)
    print("Открытие браузера с дашбордом агента...")
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == '__main__':
    # Запускаем открытие браузера в отдельном потоке
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Запускаем Flask сервер
    print("=== Запуск Web-интерфейса YouTube Telegram Agent ===")
    app.run(host='127.0.0.1', port=5000, threaded=True, debug=False)
