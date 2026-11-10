import json
from functools import cache
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


@cache
def catalog() -> dict:
    return json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))


@cache
def demo_repositories() -> dict:
    return json.loads((DATA / "demo.json").read_text(encoding="utf-8"))
