import random
from collections import Counter
from dataclasses import dataclass, field
from math import floor
from pathlib import PurePosixPath
from uuid import UUID

from app.services.atlas import atlas, build_atlas
from app.services.catalog import catalog
from app.services.github import GitHubClient
from app.services.rounds import CONTEXT_LENGTH, SNIPPET_LENGTH, SourceFile

MAX_REPOSITORIES = 60
ROUND_ATTEMPTS = 4
OTHER_REGION = "Другое"
FILES_PER_ROUND = 2
MIN_FILE_BYTES = 300
MAX_FILE_BYTES = 200_000
MIN_CODE_LINES = 12
CODE_EXTENSIONS = {
    ".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh", ".cs", ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    ".swift", ".m", ".mm", ".py", ".rb", ".php", ".js", ".jsx", ".mjs", ".ts", ".tsx", ".vue", ".svelte",
    ".lua", ".pl", ".r", ".jl", ".hs", ".ml", ".ex", ".exs", ".erl", ".clj", ".dart", ".zig", ".nim",
    ".sh", ".bash", ".ps1", ".sql", ".mpl", ".f90", ".pas", ".groovy", ".elm", ".fs", ".v", ".sv", ".vhd",
}
SKIPPED_DIRECTORIES = {
    "vendor", "third_party", "thirdparty", "node_modules", "dist", "build", "out", "target", "external",
    "deps", "generated", "gen", ".github", "fixtures", "testdata", "__snapshots__",
}


@dataclass
class World:
    id: UUID
    owner: str
    catalog: dict
    atlas: dict
    skipped: set[int] = field(default_factory=set)


def owner_catalog(repositories: list[dict]) -> dict:
    eligible = [repo for repo in repositories if not repo.get("fork") and repo.get("size", 0) > 0]
    eligible.sort(key=lambda repo: (-repo.get("stargazers_count", 0), repo["full_name"].casefold()))
    eligible = eligible[:MAX_REPOSITORIES]

    outlines = catalog()["regions"]
    counts = Counter(repo.get("language") or OTHER_REGION for repo in eligible)
    if len(counts) <= len(outlines):
        named = [language for language, _ in counts.most_common()]
    else:
        named = [language for language, _ in counts.most_common() if language != OTHER_REGION][:len(outlines) - 1]
    region_of = {language: language if language in named else OTHER_REGION for language in counts}
    names = named + [OTHER_REGION] if OTHER_REGION in region_of.values() and OTHER_REGION not in named else named
    regions = [
        {**{key: outline[key] for key in ("color", "outline")}, "id": f"region-{index}", "name": name}
        for index, (outline, name) in enumerate(zip(outlines, names))
    ]
    region_ids = {region["name"]: region["id"] for region in regions}

    created_order = sorted(eligible, key=lambda repo: repo.get("created_at", ""))
    star_order = sorted(eligible, key=lambda repo: repo.get("stargazers_count", 0))
    repos = []
    for index, repo in enumerate(eligible, start=1):
        repos.append({
            "id": index,
            "full_name": repo["full_name"],
            "branch": repo.get("default_branch") or "main",
            "stars": repo.get("stargazers_count", 0),
            "region": region_ids[region_of[repo.get("language") or OTHER_REGION]],
            "size_mb": max(0.1, round(repo["size"] / 1024, 1)),
            "map_order": [created_order.index(repo), star_order.index(repo)],
            "year": int(repo["created_at"][:4]),
            "languages": {},
        })
    return {"regions": regions, "repositories": repos}


def build_world(world_id: UUID, owner: str, repositories: list[dict]) -> World:
    data = owner_catalog(repositories)
    regions = {region["id"]: region["name"] for region in data["regions"]}
    world_atlas = build_atlas(data)
    primary = {name for name in regions.values() if name != OTHER_REGION}
    world_atlas["language_options"] = sorted(primary | set(atlas()["language_options"]), key=str.casefold)
    return World(id=world_id, owner=owner, catalog=data, atlas=world_atlas)


def language_shares(sizes: dict[str, int]) -> dict[str, int]:
    total = sum(sizes.values())
    if not total:
        return {}
    exact = {name: size * 100 / total for name, size in sizes.items()}
    shares = {name: floor(value) for name, value in exact.items()}
    by_remainder = sorted(exact, key=lambda name: exact[name] - shares[name], reverse=True)
    for name in by_remainder[:100 - sum(shares.values())]:
        shares[name] += 1
    ordered = sorted(shares.items(), key=lambda item: -item[1])
    return {name: share for name, share in ordered if share > 0}


def is_code_file(item: dict) -> bool:
    path = PurePosixPath(item["path"])
    directories = {part.casefold() for part in path.parts[:-1]}
    return (
        path.suffix.casefold() in CODE_EXTENSIONS
        and MIN_FILE_BYTES <= item.get("size", 0) <= MAX_FILE_BYTES
        and not directories & SKIPPED_DIRECTORIES
        and ".min." not in path.name
    )


def snippet_start(lines: list[str], rng: random.Random) -> int:
    latest = len(lines) - SNIPPET_LENGTH
    if latest <= CONTEXT_LENGTH:
        return min(CONTEXT_LENGTH, max(0, len(lines) - 9))
    starts = [index for index in range(CONTEXT_LENGTH, latest + 1) if lines[index].strip()]
    return rng.choice(starts) if starts else CONTEXT_LENGTH


async def pick_sources(github: GitHubClient, repo: dict, rng: random.Random) -> list[SourceFile]:
    candidates = [item for item in await github.tree(repo["full_name"], repo["branch"]) if is_code_file(item)]
    rng.shuffle(candidates)
    sources, directories = [], set()
    for item in candidates[:12]:
        directory = str(PurePosixPath(item["path"]).parent)
        if directory in directories and len(candidates) > FILES_PER_ROUND:
            continue
        text = await github.file(repo["full_name"], repo["branch"], item["path"])
        if text is None or "\x00" in text:
            continue
        lines = text.splitlines()
        if sum(1 for line in lines if line.strip()) < MIN_CODE_LINES:
            continue
        sources.append(SourceFile(path=item["path"], text=text, start=snippet_start(lines, rng)))
        directories.add(directory)
        if len(sources) == FILES_PER_ROUND:
            break
    return sources


async def world_challenge(github: GitHubClient, world: World, exclude: list[int]) -> tuple[dict, list[SourceFile]] | None:
    rng = random.Random()
    candidates = [
        repo for repo in world.catalog["repositories"]
        if repo["id"] not in exclude and repo["id"] not in world.skipped
    ]
    rng.shuffle(candidates)
    for repo in candidates[:ROUND_ATTEMPTS]:
        sources = await pick_sources(github, repo, rng)
        if not sources:
            world.skipped.add(repo["id"])
            continue
        if not repo["languages"]:
            repo["languages"] = language_shares(await github.languages(repo["full_name"]))
        return repo, sources
    return None
