# CodeGuessr Backend

FastAPI читает карту и задания из JSON в `app/data/`. Активные раунды хранятся в памяти одного процесса.

Запуск из `Backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Проверки запускаются командой `python -m pytest`. Документация API доступна на [локальном сервере](http://localhost:8000/docs).
