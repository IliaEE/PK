# PuzzleKids — локальный сервер

## Установка

```bash
cd puzzle-server
pip install -r requirements.txt
```

## Запуск

**Терминал 1 — сервер:**
```bash
python server.py
```

**Терминал 2 — фронтенд:**
```bash
# Открой index.html в браузере
open index.html
# Или запусти простой HTTP сервер:
python -m http.server 8080
# Затем открой: http://localhost:8080
```

## Как это работает

1. Фронтенд отправляет base64 фото на `localhost:5001/slice`
2. Python (Pillow) нарезает изображение с точными масками
3. Возвращает массив PNG-деталей как base64
4. Фронтенд строит игровое поле

## Структура

```
puzzle-server/
├── server.py       # Flask API
├── index.html      # Игра
├── requirements.txt
└── README.md
```
