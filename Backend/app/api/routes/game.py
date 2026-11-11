import random
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from app.schemas.game import Guess, HintRequest, RoundRequest, WorldRequest
from app.services.atlas import atlas
from app.services.call_graph import neighborhood
from app.services.catalog import catalog, demo_repositories
from app.services.github import GitHubError, OwnerNotFound, RateLimited, parse_owner
from app.services.rounds import (
    GameRound,
    demo_sources,
    grade,
    make_snapshot,
    public_round,
)
from app.services.worlds import World, build_world, world_challenge

router = APIRouter()
MAX_ROUNDS = 1000
MAX_WORLDS = 100


def remember(storage: dict, key, value, limit: int) -> None:
    if len(storage) >= limit:
        del storage[next(iter(storage))]
    storage[key] = value


def github_failure(error: GitHubError) -> HTTPException:
    if isinstance(error, OwnerNotFound):
        return HTTPException(404, str(error))
    if isinstance(error, RateLimited):
        return HTTPException(503, str(error))
    return HTTPException(502, str(error))


def world_response(world: World) -> dict:
    return {"id": str(world.id), "owner": world.owner, **world.atlas}


@router.get("/map")
async def map_data() -> dict:
    return atlas()


@router.post("/worlds", status_code=201)
async def create_world(payload: WorldRequest, request: Request) -> dict:
    try:
        login = parse_owner(payload.url)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    github = request.app.state.github
    try:
        owner = await github.owner(login)
        repositories = await github.repositories(owner["login"])
    except GitHubError as error:
        raise github_failure(error) from error

    world = build_world(uuid4(), owner["login"], repositories)
    if not world.catalog["repositories"]:
        raise HTTPException(
            409,
            f"У @{owner['login']} нет публичных репозиториев с кодом (форки не считаются).",
        )
    remember(request.app.state.worlds, world.id, world, MAX_WORLDS)
    return world_response(world)


def load_world(request: Request, world_id: UUID) -> World:
    world = request.app.state.worlds.get(world_id)
    if world is None:
        raise HTTPException(404, "Карта устарела. Постройте её заново.")
    return world


@router.get("/worlds/{world_id}")
async def get_world(world_id: UUID, request: Request) -> dict:
    return world_response(load_world(request, world_id))


async def demo_snapshot(exclude: list[int]) -> tuple[dict, list[dict]]:
    demos = demo_repositories()
    candidates = [
        repo
        for repo in catalog()["repositories"]
        if str(repo["id"]) in demos and repo["id"] not in exclude
    ]
    if not candidates:
        raise HTTPException(
            409, "Демонстрационные задания закончились. Начните новую игру."
        )

    repo = random.choice(candidates)
    country = next(item for item in atlas()["repositories"] if item["id"] == repo["id"])
    demo = demos[str(repo["id"])]
    return make_snapshot(
        repo, country, demo["year"], demo_sources(repo, demo), functions=demo.get("functions")
    ), atlas()["repositories"]


async def world_snapshot(
    request: Request, world: World, exclude: list[int]
) -> tuple[dict, list[dict]]:
    try:
        challenge = await world_challenge(request.app.state.github, world, exclude)
    except GitHubError as error:
        raise github_failure(error) from error
    if challenge is None:
        raise HTTPException(
            409, "Репозитории с подходящим кодом закончились. Начните новую игру."
        )
    repo, sources = challenge
    country = next(
        item for item in world.atlas["repositories"] if item["id"] == repo["id"]
    )
    return make_snapshot(repo, country, repo["year"], sources), world.atlas[
        "repositories"
    ]


@router.post("/rounds", status_code=201)
async def start_round(payload: RoundRequest, request: Request) -> dict:
    if payload.world is None:
        snapshot, repositories = await demo_snapshot(payload.exclude)
    else:
        snapshot, repositories = await world_snapshot(
            request, load_world(request, payload.world), payload.exclude
        )
    round_ = GameRound(id=uuid4(), snapshot=snapshot, repositories=repositories)
    remember(request.app.state.rounds, round_.id, round_, MAX_ROUNDS)
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
    if payload.kind == "context" and not (
        any(file["start"] > file["context_start"] for file in round_.snapshot["files"])
        or any(
            node["start"] > 1
            for node in round_.snapshot["call_graph"]["nodes"].values()
            if node["file_id"] is not None
        )
    ):
        raise HTTPException(409, "Для этих файлов нет дополнительных строк.")
    round_.hints[payload.kind] = True
    return public_round(round_)


@router.get("/rounds/{round_id}/graph/{node_id}")
async def get_call_graph(round_id: UUID, node_id: str, request: Request) -> dict:
    round_ = load_round(request, round_id)
    if node_id not in round_.snapshot["call_graph"]["nodes"]:
        raise HTTPException(404, "Функция не найдена в этом раунде.")
    return neighborhood(round_, node_id)


@router.post("/rounds/{round_id}/guess")
async def submit_guess(round_id: UUID, guess: Guess, request: Request) -> dict:
    round_ = load_round(request, round_id)
    if round_.result is None:
        repositories = round_.repositories
        name = guess.repository.strip().casefold()
        selected = next(
            (repo for repo in repositories if repo["name"].casefold() == name), None
        )
        if selected is None and name:
            matches = [
                repo
                for repo in repositories
                if repo["name"].rsplit("/", 1)[-1].casefold() == name
            ]
            selected = matches[0] if len(matches) == 1 else None
        round_.result = grade(round_, guess, selected)
    return public_round(round_)
