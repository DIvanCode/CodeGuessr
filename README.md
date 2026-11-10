# CodeGuessr

GeoGuessr для кода: игроку показывают кусок кода из реального репозитория, он угадывает язык, проект и год.

## Запуск бэкенда

Нужны Docker и Docker Compose. Из корня репозитория:

```bash
cp .env.example .env
docker compose up --build -d
```

В Windows можно скопировать `.env.example` в `.env` через проводник.

- API ping: http://localhost:8000/api/ping
- Проверка PostgreSQL: http://localhost:8000/api/health/ready
- Swagger UI: http://localhost:8000/docs
- OpenAPI JSON: http://localhost:8000/openapi.json

Оба контейнера запускаются через `compose.yaml`: PostgreSQL хранит данные в Docker volume,
а FastAPI автоматически применяет миграции Alembic перед запуском сервера.
Команды `docker compose down` и `docker compose down -v` останавливают сервисы;
вторая команда **удаляет данные PostgreSQL**.

Переменные окружения и локальный запуск без контейнера описаны в [Backend/README.md](Backend/README.md).
**Сейчас есть только инфраструктура и служебные endpoints:** доменные модели, таблицы игры и игровая логика не реализованы.

> Значения из `.env.example` предназначены только для локальной разработки. Для внешнего развёртывания замените пароль и настройте сеть/TLS.
