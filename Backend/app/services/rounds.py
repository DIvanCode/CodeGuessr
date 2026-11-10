import math
from dataclasses import dataclass, field
from urllib.parse import quote
from uuid import UUID

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound

from app.schemas.game import STAR_BANDS, Guess
from app.services.call_graph import entry_node, make_call_graph

POINTS = {"repository": 5000, "year": 2000, "languages": 1000, "stars": 750}
REGION_HINT_COST = 1000
HINT_COSTS = {
    "context": 500, "path": 500, "region": REGION_HINT_COST,
    "stars": POINTS["stars"], "languages": REGION_HINT_COST,
}
MAX_SCORE = sum(POINTS.values())
SNIPPET_LENGTH = 35
CONTEXT_LENGTH = 8


@dataclass
class GameRound:
    id: UUID
    snapshot: dict
    hints: dict = field(default_factory=dict)
    result: dict | None = None


def make_snapshot(repo: dict, country: dict, demo: dict) -> dict:
    files = []
    for path, source in zip(repo["challenges"][0]["paths"], demo["sources"], strict=True):
        lines = source.splitlines()
        start = min(CONTEXT_LENGTH, max(0, len(lines) - 9))
        context_start = max(0, start - CONTEXT_LENGTH)
        try:
            lexer = get_lexer_for_filename(path, stripnl=False)
        except ClassNotFound:
            lexer = TextLexer(stripnl=False)
        code = "\n".join(line[:500] for line in lines[: start + SNIPPET_LENGTH])
        highlighted = highlight(code, lexer, HtmlFormatter(nowrap=True)).split("\n")
        files.append({
            "path": path,
            "ref": repo["branch"],
            "context_start": context_start + 1,
            "start": start + 1,
            "lines": highlighted[context_start:start + SNIPPET_LENGTH],
            "full_lines": highlight(source, lexer, HtmlFormatter(nowrap=True)).splitlines(),
        })
    return {
        "year": demo["year"],
        **{key: repo[key] for key in ("full_name", "region", "stars", "size_mb", "languages")},
        "repository_id": repo["id"],
        "x": country["x"],
        "y": country["y"],
        "files": files,
        "call_graph": make_call_graph(demo),
    }


def public_round(round_: GameRound) -> dict:
    hints = round_.hints
    return {
        "id": str(round_.id),
        "hints": hints,
        "hint_costs": HINT_COSTS,
        "star_bands": STAR_BANDS,
        "hint_values": {
            **({"stars": round_.snapshot["stars"]} if hints.get("stars") else {}),
            **({"languages": list(round_.snapshot["languages"])} if hints.get("languages") else {}),
        },
        "region": round_.snapshot["region"] if hints.get("region") else None,
        "files": [
            {
                "id": index,
                "entry_node_id": entry_node(round_.snapshot, index),
                "name": file["path"] if hints.get("path") or round_.result else f"Файл {index + 1:02d}",
                "start": file["context_start"] if hints.get("context") else file["start"],
                "lines": file["lines"] if hints.get("context") else file["lines"][file["start"] - file["context_start"]:],
                "has_context": file["start"] > file["context_start"],
            }
            for index, file in enumerate(round_.snapshot["files"])
        ],
        "result": round_.result,
    }


def normalized(value: str) -> str:
    return value.strip().casefold().lstrip("@")


def grade(round_: GameRound, guess: Guess, selected_repo: dict | None) -> dict:
    answer = round_.snapshot
    full_name = answer["full_name"]
    repo_guess = normalized(guess.repository)
    exact_repo = repo_guess == full_name.casefold() or (selected_repo is not None and selected_repo["id"] == answer["repository_id"])
    pin = guess.pin.model_dump() if guess.pin else None
    if selected_repo:
        pin = {"x": selected_repo["x"], "y": selected_repo["y"]}
    distance = math.hypot(pin["x"] - answer["x"], pin["y"] - answer["y"]) if pin else None
    if exact_repo:
        repo_points = POINTS["repository"]
    elif distance is not None:
        repo_points = round(4500 * math.exp(-distance / 135))
    else:
        repo_points = 0

    overlap = sum(min(share, guess.languages.get(name.casefold(), 0)) for name, share in answer["languages"].items())
    star_band = max(threshold for threshold in STAR_BANDS if threshold <= answer["stars"])
    breakdown = {
        "repository": repo_points,
        "year": round(POINTS["year"] * math.exp(-abs(guess.year - answer["year"]) / 4)) if guess.year is not None else 0,
        "languages": round(POINTS["languages"] * overlap / 100),
        "stars": POINTS["stars"] if guess.stars == star_band else 0,
    }
    penalty = sum(HINT_COSTS[kind] for kind in round_.hints)
    repo_url = f"https://github.com/{full_name}"
    return {
        "score": max(0, sum(breakdown.values()) - penalty),
        "max_score": MAX_SCORE,
        "breakdown": breakdown,
        "penalty": penalty,
        "pin": pin,
        "selected_repository_id": selected_repo["id"] if selected_repo else None,
        "answer": {
            **{key: answer[key] for key in (
                "repository_id", "full_name", "languages", "year", "stars", "size_mb", "x", "y"
            )},
            "url": repo_url,
            "files": [
                {"path": file["path"], "url": f"{repo_url}/blob/{quote(file['ref'], safe='')}/{quote(file['path'])}"}
                for file in answer["files"]
            ],
        },
    }
