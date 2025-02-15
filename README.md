# GigaChat Telegram Bot

Многофункциональный Telegram бот с интеграцией GigaChat API. Поддерживает текстовые диалоги с сохранением контекста, анализ изображений и генерацию изображений.

## Возможности

- 💬 Контекстные диалоги с использованием GigaChat API
- 🖼️ Генерация изображений по текстовому описанию
- 📷 Анализ загруженных изображений
- 📄 Анализ текстовых документов (PDF, DOC, DOCX, TXT)
- 🔄 Сохранение контекста диалога
- 🧹 Команда очистки истории чата

## Требования

- Python 3.11+
- Telegram Bot Token
- GigaChat API авторизационный ключ
- Доступ к API GigaChat (https://gigachat.devices.sberbank.ru)

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/your-username/gigachat-bot.git
cd gigachat-bot
```

2. Установите зависимости:
```bash
pip install -r requirements.txt
```

3. Создайте файл конфигурации:
```bash
cp secrets.yaml.example secrets.yaml
```

4. Отредактируйте `secrets.yaml` и добавьте необходимые credentials:
```yaml
telegram_bot_api_key: "YOUR_BOT_TOKEN"
telegram_allowed_chat_ids:
  - CHAT_ID1
  - CHAT_ID2
gigachat_authorization_key: "YOUR_GIGACHAT_AUTH_KEY"
```

## Запуск

### Локальный запуск

```bash
python src/main.py
```

### Запуск на сервере через systemd

1. Создайте systemd service файл:
```bash
sudo nano /etc/systemd/system/gigachat-bot.service
```

2. Добавьте следующее содержимое (измените пути и пользователя):
```ini
[Unit]
Description=GigaChat Telegram Bot
After=network.target

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/gigachat-bot
ExecStart=/usr/bin/python3 src/main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

3. Включите и запустите сервис:
```bash
sudo systemctl enable gigachat-bot
sudo systemctl start gigachat-bot
```

## Использование

После запуска бота доступны следующие команды:

- `/start` - Начало работы с ботом
- `/image <описание>` - Генерация изображения по описанию
- `/clear` - Очистка истории диалога
- Отправка текстовых сообщений для диалога
- Отправка изображений для анализа
- Отправка документов для анализа

## Мониторинг

Логи бота доступны через:
- Файл `bot.log` в директории бота
- systemd журнал: `journalctl -u gigachat-bot.service -f`

## License

MIT
