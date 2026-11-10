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
from app.services.difficulty import Difficulty
from app.services.sources import SourceFile
from app.services.worlds import World, locate

POINTS = {"repository": 5000, "year": 2000, "languages": 1000, "stars": 750}
REGION_HINT_COST = 1000
MAX_SCORE = sum(POINTS.values())
DEMO_CONTEXT_LENGTH = 8
DISTANCE_POINTS = 4500


@dataclass
class GameRound:
    id: UUID
    snapshot: dict
    world: World
    hints: dict = field(default_factory=dict)
    result: dict | None = None


def hint_costs(difficulty: Difficulty) -> dict[str, int]:
    return {
        "context": 500, "path": 1500 if difficulty.folders else 500, "region": REGION_HINT_COST,
        "stars": POINTS["stars"], "languages": REGION_HINT_COST,
    }


def demo_sources(repo: dict, demo: dict) -> list[SourceFile]:
    return [
        SourceFile(path=path, text=text, start=min(DEMO_CONTEXT_LENGTH, max(0, len(text.splitlines()) - 9)))
        for path, text in zip(repo["challenges"][0]["paths"], demo["sources"], strict=True)
    ]


def make_snapshot(
    world: World, repo: dict, year: int, sources: list[SourceFile],
    *, folder: dict | None = None, functions: list[list[dict]] | None = None,
) -> dict:
    difficulty = world.difficulty
    country = world.country(repo["id"])
    files = []
    for source in sources:
        lines = source.text.splitlines()
        start = source.start
        context_start = max(0, start - difficulty.context_length)
        try:
            lexer = get_lexer_for_filename(source.path, stripnl=False)
        except ClassNotFound:
            lexer = TextLexer(stripnl=False)
        code = "\n".join(line[:500] for line in lines[: start + difficulty.snippet_length])
        highlighted = highlight(code, lexer, HtmlFormatter(nowrap=True)).split("\n")
        files.append({
            "path": source.path,
            "ref": repo["branch"],
            "context_start": context_start + 1,
            "start": start + 1,
            "lines": highlighted[context_start:start + difficulty.snippet_length],
            "full_lines": highlight(source.text, lexer, HtmlFormatter(nowrap=True)).splitlines(),
        })
        if functions is not None:
            files[-1]["full_lines"] = highlight(
                source.text, lexer, HtmlFormatter(nowrap=True)
            ).split("\n")
    target = folder or country
    return {
        "year": year,
        **{key: repo[key] for key in ("full_name", "region", "stars", "size_mb", "languages")},
        "repository_id": repo["id"],
        "repository": repo["id"],
        "group": country["group"],
        "folder": folder["id"] if folder else None,
        "folder_polygon": folder["polygon"] if folder else None,
        "x": target["x"],
        "y": target["y"],
        "files": files,
        "call_graph": make_call_graph(functions or []),
    }


def public_round(round_: GameRound) -> dict:
    hints = round_.hints
    return {
        "id": str(round_.id),
        "difficulty": round_.world.difficulty.name,
        "hints": hints,
        "hint_costs": hint_costs(round_.world.difficulty),
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


def country_by_name(world: World, text: str) -> dict | None:
    name = normalized(text)
    if not name:
        return None
    countries = world.atlas["repositories"]
    exact = next((repo for repo in countries if repo["name"].casefold() == name), None)
    if exact:
        return exact
    matches = [repo for repo in countries if repo["name"].rsplit("/", 1)[-1].casefold() == name]
    return matches[0] if len(matches) == 1 else None


def location_points(difficulty: Difficulty, location: dict, answer: dict) -> int:
    points = 0
    for level, level_points in zip(difficulty.levels, difficulty.level_points):
        if location[level] is None or location[level] != answer[level]:
            break
        points = level_points
    return points


def grade(round_: GameRound, guess: Guess) -> dict:
    world, answer = round_.world, round_.snapshot
    difficulty = world.difficulty
    full_name = answer["full_name"]
    pin = guess.pin.model_dump() if guess.pin else None
    if pin is None:
        named = country_by_name(world, guess.repository)
        pin = {"x": named["x"], "y": named["y"]} if named else None
    location = locate(world, (pin["x"], pin["y"])) if pin else {level: None for level in difficulty.levels}
    if guess.depth is not None:
        location.update({level: None for level in difficulty.levels[guess.depth + 1:]})
    if pin:
        distance = math.hypot(pin["x"] - answer["x"], pin["y"] - answer["y"])
        distance_points = round(DISTANCE_POINTS * math.exp(-distance / difficulty.distance_scale))
        repo_points = max(location_points(difficulty, location, answer), distance_points)
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
    penalty = sum(hint_costs(difficulty)[kind] for kind in round_.hints)
    repo_url = f"https://github.com/{full_name}"
    return {
        "score": max(0, sum(breakdown.values()) - penalty),
        "max_score": MAX_SCORE,
        "breakdown": breakdown,
        "penalty": penalty,
        "pin": pin,
        "location": {level: location[level] for level in difficulty.levels},
        "selected_repository_id": location["repository"],
        "answer": {
            **{key: answer[key] for key in (
                "repository_id", "full_name", "languages", "year", "stars", "size_mb", "x", "y",
                "region", "group", "folder", "folder_polygon",
            )},
            "url": repo_url,
            "files": [
                {"path": file["path"], "url": f"{repo_url}/blob/{quote(file['ref'], safe='')}/{quote(file['path'])}"}
                for file in answer["files"]
            ],
        },
    }
