# 📦 Media Processing Service

Сервис загрузки и фоновой обработки медиафайлов. Пользователи загружают изображения и видео, сервис обрабатывает их в фоне через Celery и возвращает ссылки на все сгенерированные версии.

**Стек:** Python · FastAPI · Celery · Redis · PostgreSQL · MinIO · Docker Compose

---

## Содержание

- [Возможности](#возможности)
- [Архитектура](#архитектура)
- [Быстрый старт](#быстрый-старт)
- [Переменные окружения](#переменные-окружения)
- [API](#api)
- [Обработка файлов](#обработка-файлов)
- [Модели БД](#модели-бд)
- [Запуск тестов](#запуск-тестов)
- [Структура проекта](#структура-проекта)

---

## Возможности

- Загрузка изображений (jpg, png, gif) и видео (mp4, mov)
- Фоновая обработка через Celery + Redis
- Автоматическая генерация версий файла (thumbnail, medium, preview)
- Хранение файлов в MinIO (self-hosted S3)
- JWT-авторизация через внешний auth-сервис
- Квота хранилища на пользователя
- Контроль доступа к файлам (приватные / публичные / по списку ID)
- Статус обработки в реальном времени через polling

---

## Архитектура

```
Client
  │
  ▼
FastAPI (media_service)
  │         │
  │         └──► MinIO (хранение файлов)
  │
  ├──► PostgreSQL (файлы, версии, задачи)
  │
  └──► Redis ──► Celery Worker
                    │
                    ├──► Pillow (обработка изображений)
                    ├──► ffmpeg (обработка видео)
                    └──► MinIO (сохранение версий)

Auth Service (отдельный микросервис, JWT)
```

**Флоу загрузки:**
1. `POST /upload` — файл сохраняется в MinIO, создаётся запись в БД, задача уходит в Celery
2. Celery-воркер обрабатывает файл и создаёт версии
3. `GET /status/{task_id}` — клиент полит статус (`pending → processing → done / failed`)
4. `GET /files/{file_id}` — возвращает все версии с ссылками на скачивание

---

## Быстрый старт

### Требования

- Docker & Docker Compose
- Запущенный auth-сервис (переменная `USER_SERVICE_URL`)

### Запуск

```bash
git clone https://github.com/your-username/media-service.git
cd media-service

cp .env.example .env
# Заполните переменные окружения в .env

docker compose up --build
```

Сервис поднимется на `http://localhost:8000`.  
Документация API: `http://localhost:8000/docs`

### Применение миграций

```bash
docker compose exec api alembic upgrade head
```

---

## Переменные окружения

Создайте `.env` на основе `.env.example`:

```env
# База данных
DATABASE_URL=postgresql+asyncpg://user:password@db:5432/media_db

# Redis / Celery
REDIS_URL=redis://redis:6379

# MinIO
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET_NAME=media

# Auth-сервис
USER_SERVICE_URL=http://auth-service:8001

# JWT
JWT_SECRET=your-secret-key
JWT_ALGORITHM=HS256
```

---

## API

### Авторизация

Все защищённые эндпоинты требуют заголовок:
```
Authorization: Bearer <access_token>
```

Токен выдаётся auth-сервисом (`POST /login`).

### Эндпоинты

| Метод | Путь | Описание | Auth |
|-------|------|----------|------|
| `POST` | `/upload` | Загрузить файл, получить `task_id` | ✅ |
| `GET` | `/status/{task_id}` | Статус обработки | ✅ |
| `GET` | `/files` | Список файлов пользователя | ✅ |
| `GET` | `/files/{file_id}` | Детали файла + ссылки на все версии | ✅ |
| `DELETE` | `/files/{file_id}` | Удалить файл и все версии из MinIO | ✅ |
| `GET` | `/files/{file_id}/download/{version}` | Скачать конкретную версию | ✅ |
| `GET` | `/health` | Healthcheck | — |

### Примеры запросов

**Загрузка файла:**
```bash
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@photo.jpg"
```

Ответ:
```json
{
  "id": 1,
  "file_id": 42,
  "status": "pending",
  "started_at": "2024-01-15T10:00:00Z",
  "finished_at": null,
  "error_message": null
}
```

**Загрузка с контролем доступа:**
```bash
# Публичный файл (доступен всем)
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@photo.jpg" \
  -F 'ids={"ids": []}'

# Только для пользователей с id 5 и 10
curl -X POST http://localhost:8000/upload \
  -H "Authorization: Bearer <token>" \
  -F "file=@photo.jpg" \
  -F 'ids={"ids": [5, 10]}'
```

**Проверка статуса:**
```bash
curl http://localhost:8000/status/1 \
  -H "Authorization: Bearer <token>"
```

```json
{
  "id": 1,
  "file_id": 42,
  "status": "done",
  "started_at": "2024-01-15T10:00:00Z",
  "finished_at": "2024-01-15T10:00:05Z",
  "error_message": null
}
```

---

## Обработка файлов

### Изображения (jpg · png · gif)

| Версия | Описание |
|--------|----------|
| `original` | Оригинал, сохраняется в MinIO без изменений |
| `medium` | Ресайз до 800px по ширине (Pillow, LANCZOS) |
| `thumbnail` | Уменьшение до 128×128px (Pillow) |

### Видео (mp4 · mov)

| Версия | Описание |
|--------|----------|
| `original` | Оригинал, сохраняется в MinIO без изменений |
| `converted` | Перекодирование в mp4 (H.264 + AAC) через ffmpeg |
| `preview` | Первый кадр на 1-й секунде, 128×128px (ffmpeg) |

### Статусы задачи

```
pending → processing → done
                     ↘ failed (error_message заполнен)
```

---

## Модели БД

```
MediaFile
├── id, user_id, original_filename
├── filetype, filesize
├── user_access_ids  (null = приватный, [] = публичный, [...] = ACL)
└── created_at, updated_at

MediaVersion
├── id, file_id (FK)
├── version_type  (original / medium / thumbnail / converted / preview)
├── minio_key
└── url

ProcessingTask
├── id, file_id (FK)
├── status, error_message
└── started_at, finished_at
```

Миграции управляются через **Alembic**:
```bash
# Создать новую миграцию
alembic revision --autogenerate -m "description"

# Применить
alembic upgrade head

# Откатить
alembic downgrade -1
```

---

## Запуск тестов

```bash
docker compose exec api pytest -v
```

Покрытие: `/upload`, `/status`, `/files`, `/download`.

```bash
# С отчётом о покрытии
docker compose exec api pytest --cov=. --cov-report=term-missing
```

---

## Структура проекта

```
media-service/
├── api/
│   ├── router.py          # FastAPI эндпоинты
│   ├── schemas.py         # Pydantic-схемы
│   └── media.py           # Celery-таски, обработка файлов
├── core/
│   ├── models/
│   │   ├── base.py
│   │   ├── media_file.py
│   │   ├── media_version.py
│   │   └── processing_task.py
│   ├── auth.py            # JWT-утилиты
│   ├── config.py
│   └── db.py              # SQLAlchemy + MinIO клиент
├── migrations/            # Alembic
├── tests/
├── docker-compose.yml
├── Dockerfile
├── .env.example
└── README.md
```

---

## CI/CD

GitHub Actions запускает тесты на каждый push в `main`:

```yaml
# .github/workflows/ci.yml
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - name: Run tests
        run: docker compose run --rm api pytest -v
```

---

## Лицензия

MIT