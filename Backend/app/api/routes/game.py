import random
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from app.schemas.game import Guess, HintRequest, RoundRequest
from app.services.atlas import atlas
from app.services.catalog import catalog, demo_repositories
from app.services.rounds import GameRound, grade, make_snapshot, public_round

router = APIRouter()


@router.get("/map")
async def map_data() -> dict:
    return atlas()


@router.post("/rounds", status_code=201)
async def start_round(payload: RoundRequest, request: Request) -> dict:
    demos = demo_repositories()
    candidates = [
        repo for repo in catalog()["repositories"]
        if str(repo["id"]) in demos and repo["id"] not in payload.exclude
    ]
    if not candidates:
        raise HTTPException(409, "Демонстрационные задания закончились. Начните новую игру.")

    repo = random.choice(candidates)
    country = next(item for item in atlas()["repositories"] if item["id"] == repo["id"])
    demo = demos[str(repo["id"])]
    round_ = GameRound(id=uuid4(), snapshot=make_snapshot(repo, country, demo))
    rounds = request.app.state.rounds
    if len(rounds) >= 1000:
        del rounds[next(iter(rounds))]
    rounds[round_.id] = round_
    return public_round(round_)


def load_round(request: Request, round_id: UUID) -> GameRound:
    round_ = request.app.state.rounds.get(round_id)
    if round_ is None:
        raise HTTPException(404, "Раунд истёк. Начните новый раунд.")
    return round_


@router.get("/rounds/{round_id}")
async def get_round(round_id: UUID, request: Request) -> dict:
    return public_round(load_round(request, round_id))


@router.post("/rounds/{round_id}/hint")
async def hint(round_id: UUID, payload: HintRequest, request: Request) -> dict:
    round_ = load_round(request, round_id)
    if round_.result is not None:
        raise HTTPException(409, "Раунд уже завершён.")
    if payload.kind == "context" and not any(
        file["start"] > file["context_start"] for file in round_.snapshot["files"]
    ):
        raise HTTPException(409, "Для этих файлов нет дополнительных строк.")
    round_.hints[payload.kind] = True
    return public_round(round_)


@router.post("/rounds/{round_id}/guess")
async def submit_guess(round_id: UUID, guess: Guess, request: Request) -> dict:
    round_ = load_round(request, round_id)
    if round_.result is None:
        name = guess.repository.strip().casefold()
        repositories = atlas()["repositories"]
        selected = next((repo for repo in repositories if repo["name"].casefold() == name), None)
        if selected is None and name:
            matches = [repo for repo in repositories if repo["name"].rsplit("/", 1)[-1].casefold() == name]
            selected = matches[0] if len(matches) == 1 else None
        round_.result = grade(round_, guess, selected)
    return public_round(round_)
