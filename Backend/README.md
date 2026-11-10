# CodeGuessr Backend

Python 3.12, FastAPI, async SQLAlchemy, PostgreSQL and Alembic. No game logic or domain tables yet.

## Structure

- `app/api/` – HTTP routes (request handling only)
- `app/core/` – environment-based configuration
- `app/db/` – database engine, sessions and ORM base
- `app/models/` – future SQLAlchemy models
- `app/repositories/` – future database access
- `app/services/` – future application logic
- `app/schemas/` – future API request/response DTOs
- `alembic/` – database migrations
- `tests/` – API smoke tests

## Local development

From repository root, start PostgreSQL with `docker compose up -d db`.
Then from `Backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

The application reads `DATABASE_URL` and `CORS_ORIGINS` from environment variables
(or from `Backend/.env` when run from `Backend/`). For Windows, activate the
virtual environment with `.venv\Scripts\activate` and copy `.env.example` to `.env`.

## Migrations

After defining a model, import its module from `app/db/base.py` so Alembic sees its metadata.
Then run `alembic revision --autogenerate -m "describe change"` and review the generated migration.
Apply migrations with `alembic upgrade head`. Docker starts the API only after applying migrations.

## Tests

Run `python -m pytest` from `Backend/`. Unit tests replace the DB session dependency;
the Docker Compose readiness check validates the actual PostgreSQL connection.
