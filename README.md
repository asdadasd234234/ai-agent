# 📺 YouTube AI Agent

Агент для автоматического отслеживания новых видео на YouTube-канале и рассылки уведомлений через Telegram, Discord или Email. Поддерживает генерацию анонсов через ChatGPT.

## ✨ Возможности

- 🔍 Мониторинг YouTube-канала через RSS (без API ключа)
- 📨 Уведомления в **Telegram**
- 💬 Уведомления в **Discord** (через Webhook)
- 📧 Уведомления на **Email** (Gmail SMTP)
- 🤖 AI-генерация анонсов через **ChatGPT** (GPT-3.5-turbo)
- 🌐 Удобный **веб-интерфейс** (Flask dashboard)
- 🧠 AI-ассистент для настройки автоматизации

## 🚀 Установка

```bash
git clone https://github.com/maksim19145674-coder/ai-agent.git
cd ai-agent
pip install -r requirements.txt
```

## ▶️ Запуск

```bash
python youtube_agent.py
```

Откроется браузер с веб-интерфейсом на `http://127.0.0.1:5000`

## ⚙️ Настройка

В веб-интерфейсе можно настроить:

| Параметр | Описание |
|----------|----------|
| `channel_id` | ID YouTube-канала (например: `UCxxxxxx`) |
| `bot_token` | Telegram Bot Token |
| `chat_id` | Telegram Chat ID или `@username` |
| `discord_webhook` | URL Webhook'а Discord |
| `email_user` | Gmail-адрес отправителя |
| `email_pass` | Пароль приложения Gmail |
| `email_to` | Email получателя |
| `openai_api_key` | OpenAI API ключ (опционально) |

## 📦 Зависимости

```
requests
flask
openai
```

## 📄 Лицензия

MIT
