# Backend — локальная разработка

Требуется Python 3.11+. Из корня репозитория:

```bash
cd Backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

В Windows PowerShell вместо `source` используйте `.\.venv\Scripts\Activate.ps1`.

API: http://localhost:8000/docs. Для запросов к GitHub можно задать переменную окружения `GITHUB_TOKEN` (необязательно).

Проверка тестов из `Backend/`:

```bash
python -m pytest
```
