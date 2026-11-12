import random
from uuid import UUID, uuid4

from fastapi import APIRouter, HTTPException, Request

from app.schemas.game import Guess, HintRequest, RoundRequest, WorldRequest
from app.services.call_graph import neighborhood
from app.services.catalog import demo_repositories
from app.services.difficulty import DIFFICULTIES, DifficultyName
from app.services.github import GitHubError, OwnerNotFound, RateLimited, parse_owner
from app.services.rounds import GameRound, demo_sources, grade, make_snapshot, public_round
from app.services.worlds import (
    World, build_demo_world, build_world, public_folders, repository_folders, world_challenge,
)

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
    return {"id": str(world.id), "owner": world.owner, "difficulty": world.difficulty.name, **world.atlas}


def demo_world(request: Request, difficulty: DifficultyName) -> World:
    worlds = request.app.state.demo_worlds
    if difficulty not in worlds:
        worlds[difficulty] = build_demo_world(DIFFICULTIES[difficulty])
    return worlds[difficulty]


@router.get("/map")
async def map_data(request: Request, difficulty: DifficultyName = "easy") -> dict:
    return world_response(demo_world(request, difficulty))


@router.post("/worlds", status_code=201)
async def create_world(payload: WorldRequest, request: Request) -> dict:
    try:
        login = parse_owner(payload.url)
    except ValueError as error:
        raise HTTPException(422, str(error)) from error

    difficulty = DIFFICULTIES[payload.difficulty]
    github = request.app.state.github
    try:
        owner = await github.owner(login)
        repositories = await github.repositories(owner["login"], difficulty.max_repositories)
    except GitHubError as error:
        raise github_failure(error) from error

    world = build_world(uuid4(), owner["login"], repositories, difficulty)
    if not world.catalog["repositories"]:
        raise HTTPException(
            409,
            f"У @{owner['login']} нет публичных репозиториев с кодом (форки не считаются).",
        )
    remember(request.app.state.worlds, world.id, world, MAX_WORLDS)
    return world_response(world)


def load_world(request: Request, world_id: UUID) -> World:
    world = request.app.state.worlds.get(world_id)
    world = world or next((demo for demo in request.app.state.demo_worlds.values() if demo.id == world_id), None)
    if world is None:
        raise HTTPException(404, "Карта устарела. Постройте её заново.")
    return world


@router.get("/worlds/{world_id}")
async def get_world(world_id: UUID, request: Request) -> dict:
    return world_response(load_world(request, world_id))


@router.get("/worlds/{world_id}/repositories/{repo_id}/folders")
async def get_folders(world_id: UUID, repo_id: int, request: Request) -> dict:
    world = load_world(request, world_id)
    if not world.difficulty.folders:
        raise HTTPException(409, "Папки показываются только на сложном уровне.")
    if not any(repo["id"] == repo_id for repo in world.catalog["repositories"]):
        raise HTTPException(404, "Репозиторий не найден на карте.")
    try:
        folders = await repository_folders(request.app.state.github, world, repo_id)
    except GitHubError as error:
        raise github_failure(error) from error
    return {"repository": repo_id, "folders": public_folders(folders)}


def demo_snapshot(world: World, exclude: list[int]) -> dict:
    demos = demo_repositories()
    candidates = [
        repo for repo in world.catalog["repositories"]
        if str(repo["id"]) in demos and repo["id"] not in exclude
    ]
    if not candidates:
        raise HTTPException(
            409, "Демонстрационные задания закончились. Начните новую игру."
        )

    repo = random.choice(candidates)
    demo = demos[str(repo["id"])]
    return make_snapshot(world, repo, demo["year"], demo_sources(repo, demo), functions=demo.get("functions"))


async def world_snapshot(request: Request, world: World, exclude: list[int]) -> dict:
    try:
        challenge = await world_challenge(request.app.state.github, world, exclude)
    except GitHubError as error:
        raise github_failure(error) from error
    if challenge is None:
        raise HTTPException(409, "Репозитории с подходящим кодом закончились. Начните новую игру.")
    repo, sources, folder, graph_sources = challenge
    return make_snapshot(world, repo, repo["year"], sources, folder=folder, graph_sources=graph_sources)


@router.post("/rounds", status_code=201)
async def start_round(payload: RoundRequest, request: Request) -> dict:
    if payload.world is None:
        world = demo_world(request, payload.difficulty)
    else:
        world = load_world(request, payload.world)
    if world.owner is None and world.difficulty.name == "easy":
        snapshot = demo_snapshot(world, payload.exclude)
    else:
        snapshot = await world_snapshot(request, world, payload.exclude)
    round_ = GameRound(id=uuid4(), snapshot=snapshot, world=world)
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
        any(file["start"] > file["context_start"] for file in round_.snapshot["files"][:round_.snapshot["clue_file_count"]])
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
        round_.result = grade(round_, guess)
    return public_round(round_)
