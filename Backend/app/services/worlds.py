import random
from asyncio import gather
from collections import Counter
from dataclasses import dataclass, field
from math import floor, sqrt
from pathlib import PurePosixPath
from statistics import median
from uuid import NAMESPACE_URL, UUID, uuid5

from app.services.atlas import build_atlas, center, contains, partition, rounded
from app.services.catalog import catalog
from app.services.difficulty import Difficulty
from app.services.function_analysis import LANGUAGES
from app.services.github import GitHubClient
from app.services.sources import SourceFile
from app.services.topics import cluster_repositories

ROUND_ATTEMPTS = 4
EXTRA_GRAPH_FILES = 6
MAX_GRAPH_FILE_BYTES = 64_000
MISC_TOPIC = "Разное"
OTHER_LANGUAGES = "Другие языки"
MAX_LANGUAGE_GROUPS = 5
OTHER_FOLDERS = "…"
MAX_FOLDERS = 9
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
LANGUAGE_FAMILIES = {
    "C и C++": {"C", "C++", "Zig", "Nim", "V", "Crystal", "Assembly"},
    "JVM": {"Java", "Kotlin", "Scala", "Clojure", "Groovy"},
    "JavaScript и TypeScript": {"JavaScript", "TypeScript"},
    "Python и данные": {"Python", "Julia", "R", "Jupyter Notebook"},
    "Go": {"Go"},
    "Rust": {"Rust"},
    "Скриптовые": {"Ruby", "PHP", "Lua", "Shell", "Perl"},
    "Функциональные": {"Haskell", "OCaml", "Elixir", "Erlang", "F#", "Elm"},
    "Swift, C# и Dart": {"Swift", "C#", "Dart", "Objective-C"},
}
OTHER_FAMILY = "Прочие языки"


@dataclass
class World:
    id: UUID
    owner: str | None
    difficulty: Difficulty
    catalog: dict
    atlas: dict
    skipped: set[int] = field(default_factory=set)
    trees: dict[int, list[dict]] = field(default_factory=dict)
    folders: dict[int, list[dict]] = field(default_factory=dict)

    def repository(self, repo_id: int) -> dict:
        return next(repo for repo in self.catalog["repositories"] if repo["id"] == repo_id)

    def country(self, repo_id: int) -> dict:
        return next(repo for repo in self.atlas["repositories"] if repo["id"] == repo_id)


def language_groups(repos: list[dict], regions: list[dict]) -> None:
    for region in regions:
        members = [repo for repo in repos if repo["region"] == region["id"]]
        counts = Counter(repo["language"] or OTHER_LANGUAGES for repo in members)
        kept = {language for language, _ in counts.most_common(MAX_LANGUAGE_GROUPS) if language != OTHER_LANGUAGES}
        if len(counts) <= MAX_LANGUAGE_GROUPS:
            kept = set(counts) - {OTHER_LANGUAGES}
        for repo in members:
            repo["group"] = repo["language"] if repo["language"] in kept else OTHER_LANGUAGES


def owner_catalog(repositories: list[dict], difficulty: Difficulty) -> dict:
    eligible = [repo for repo in repositories if not repo.get("fork") and repo.get("size", 0) > 0]
    eligible.sort(key=lambda repo: (-repo.get("stargazers_count", 0), repo["full_name"].casefold()))
    eligible = eligible[:difficulty.max_repositories]

    outlines = catalog()["regions"]
    labels, names = cluster_repositories(eligible, len(outlines), MISC_TOPIC)
    regions = [
        {**{key: outline[key] for key in ("color", "outline")}, "id": f"region-{index}", "name": name}
        for index, (outline, name) in enumerate(zip(outlines, names))
    ]

    created_order = sorted(eligible, key=lambda repo: repo.get("created_at", ""))
    star_order = sorted(eligible, key=lambda repo: repo.get("stargazers_count", 0))
    repos = []
    for index, (repo, label) in enumerate(zip(eligible, labels), start=1):
        repos.append({
            "id": index,
            "full_name": repo["full_name"],
            "branch": repo.get("default_branch") or "main",
            "stars": repo.get("stargazers_count", 0),
            "region": regions[label]["id"],
            "language": repo.get("language"),
            "size_mb": max(0.1, round(repo["size"] / 1024, 1)),
            "map_order": [created_order.index(repo), star_order.index(repo)],
            "year": int(repo["created_at"][:4]),
            "languages": {},
        })
    if difficulty.grouped:
        language_groups(repos, regions)
    return {"regions": regions, "repositories": repos}


def language_family(languages: dict[str, int]) -> str:
    primary = max(languages, key=languages.get) if languages else ""
    return next((name for name, members in LANGUAGE_FAMILIES.items() if primary in members), OTHER_FAMILY)


def demo_catalog(difficulty: Difficulty) -> dict:
    data = catalog()
    repos = [{**repo, "languages": dict(repo["languages"])} for repo in data["repositories"]]
    if difficulty.grouped:
        for repo in repos:
            repo["group"] = language_family(repo["languages"])
    return {"regions": data["regions"], "repositories": repos}


def with_language_options(world_atlas: dict, extra: set[str]) -> dict:
    world_atlas["language_options"] = sorted(set(world_atlas["language_options"]) | extra, key=str.casefold)
    return world_atlas


def build_world(world_id: UUID, owner: str, repositories: list[dict], difficulty: Difficulty) -> World:
    data = owner_catalog(repositories, difficulty)
    primary = {repo["language"] for repo in data["repositories"] if repo["language"]}
    demo_languages = {language for repo in catalog()["repositories"] for language in repo["languages"]}
    world_atlas = with_language_options(build_atlas(data), primary | demo_languages)
    return World(id=world_id, owner=owner, difficulty=difficulty, catalog=data, atlas=world_atlas)


def demo_world_id(difficulty: Difficulty) -> UUID:
    return uuid5(NAMESPACE_URL, f"codeguessr:demo:{difficulty.name}")


def build_demo_world(difficulty: Difficulty) -> World:
    data = demo_catalog(difficulty)
    return World(id=demo_world_id(difficulty), owner=None, difficulty=difficulty, catalog=data, atlas=build_atlas(data))


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


def is_code_file(item: dict, min_bytes: int = MIN_FILE_BYTES) -> bool:
    path = PurePosixPath(item["path"])
    directories = {part.casefold() for part in path.parts[:-1]}
    return (
        path.suffix.casefold() in CODE_EXTENSIONS
        and min_bytes <= item.get("size", 0) <= MAX_FILE_BYTES
        and not directories & SKIPPED_DIRECTORIES
        and ".min." not in path.name
    )


def folder_layout(files: list[dict]) -> list[dict]:
    parts = [PurePosixPath(item["path"]).parts for item in files]
    depth = 0
    while parts and all(len(path) > depth + 1 for path in parts) and len({path[depth] for path in parts}) == 1:
        depth += 1
    buckets: dict[str, list[dict]] = {}
    for item, path in zip(files, parts):
        if len(path) > depth + 1:
            key = "/".join(path[:depth + 1]) + "/"
        else:
            key = "/".join(path[:depth] + ("*",))
        buckets.setdefault(key, []).append(item)

    return arrange([
        {"id": key, "files": items, "size": sum(item["size"] for item in items)} for key, items in buckets.items()
    ])


def arrange(buckets: list[dict]) -> list[dict]:
    ordered = sorted(buckets, key=lambda bucket: (-bucket["size"], bucket["id"]))
    if len(ordered) > MAX_FOLDERS:
        rest = ordered[MAX_FOLDERS - 1:]
        ordered = ordered[:MAX_FOLDERS - 1] + [{
            "id": OTHER_FOLDERS,
            "files": [item for bucket in rest for item in bucket["files"]],
            "size": sum(bucket["size"] for bucket in rest),
        }]
    by_name = sorted(bucket["id"] for bucket in ordered)
    return [
        {**bucket, "weight": sqrt(bucket["size"]), "map_order": [by_name.index(bucket["id"]), -rank]}
        for rank, bucket in enumerate(ordered)
    ]


def truncated_layout(top: list[dict], partial: list[dict]) -> list[dict]:
    directories = [
        entry for entry in top
        if entry["type"] == "tree" and entry["path"].casefold() not in SKIPPED_DIRECTORIES
    ]
    root_files = code_files(top)
    sizes = Counter()
    for item in partial:
        sizes[PurePosixPath(item["path"]).parts[0]] += item["size"]
    fallback = median(sizes.values()) if sizes else 1
    buckets = [
        {"id": entry["path"] + "/", "files": [], "size": sizes[entry["path"]] or fallback, "sha": entry["sha"]}
        for entry in directories
    ]
    if root_files:
        buckets.append({"id": "*", "files": root_files, "size": sum(item["size"] for item in root_files)})
    return arrange(buckets)


def code_files(entries: list[dict], prefix: str = "", *, min_bytes: int = MIN_FILE_BYTES) -> list[dict]:
    files = [{**entry, "path": prefix + entry["path"]} for entry in entries if entry["type"] == "blob"]
    return [item for item in files if is_code_file(item, min_bytes=min_bytes)]


async def repository_tree(github: GitHubClient, world: World, repo: dict) -> dict:
    if repo["id"] not in world.trees:
        entries, truncated = await github.tree(repo["full_name"], repo["branch"])
        tree = {"files": code_files(entries), "graph_files": code_files(entries, min_bytes=1), "top": None}
        if truncated:
            tree["top"], _ = await github.tree(repo["full_name"], repo["branch"], recursive=False)
        world.trees[repo["id"]] = tree
    return world.trees[repo["id"]]


async def repository_folders(github: GitHubClient, world: World, repo_id: int) -> list[dict]:
    if repo_id not in world.folders:
        tree = await repository_tree(github, world, world.repository(repo_id))
        polygon = [tuple(point) for point in world.country(repo_id)["polygon"]]
        if tree["top"] is None:
            layout = folder_layout(tree["files"])
        else:
            layout = truncated_layout(tree["top"], tree["files"])
        world.folders[repo_id] = [
            {
                **{key: value for key, value in folder.items() if key in ("id", "files", "sha")},
                "polygon": rounded(part), **center(part),
            }
            for folder, part in (partition(polygon, layout) if layout else [])
        ]
    return world.folders[repo_id]


async def folder_files(github: GitHubClient, repo: dict, folder: dict) -> list[dict]:
    if "sha" in folder:
        entries, _ = await github.tree(repo["full_name"], folder["sha"])
        folder["files"] = code_files(entries, folder["id"])
        folder["graph_files"] = code_files(entries, folder["id"], min_bytes=1)
        del folder["sha"]
    return folder["files"]


def public_folders(folders: list[dict]) -> list[dict]:
    return [{key: folder[key] for key in ("id", "polygon", "x", "y")} for folder in folders]


def locate(world: World, point: tuple[float, float]) -> dict:
    found = {"region": None, "group": None, "repository": None, "folder": None}
    found["region"] = next((region["id"] for region in world.atlas["regions"] if contains(region["outline"], point)), None)
    found["group"] = next((group["id"] for group in world.atlas["groups"] if contains(group["polygon"], point)), None)
    country = next((repo for repo in world.atlas["repositories"] if contains(repo["polygon"], point)), None)
    if country:
        found["repository"] = country["id"]
        found["folder"] = next(
            (folder["id"] for folder in world.folders.get(country["id"], []) if contains(folder["polygon"], point)), None,
        )
    return found


def snippet_start(lines: list[str], rng: random.Random, difficulty: Difficulty) -> int:
    context, latest = difficulty.context_length, len(lines) - difficulty.snippet_length
    if latest <= context:
        return min(context, max(0, len(lines) - 9))
    starts = [index for index in range(context, latest + 1) if lines[index].strip()]
    return rng.choice(starts) if starts else context


async def pick_sources(
    github: GitHubClient, repo: dict, candidates: list[dict], difficulty: Difficulty, rng: random.Random,
) -> list[SourceFile]:
    candidates = candidates[:]
    rng.shuffle(candidates)
    sources, directories = [], set()
    for item in candidates[:difficulty.files * 5]:
        directory = str(PurePosixPath(item["path"]).parent)
        if directory in directories and len(candidates) > difficulty.files * 2:
            continue
        text = await github.file(repo["full_name"], repo["branch"], item["path"])
        if text is None or "\x00" in text:
            continue
        lines = text.splitlines()
        if sum(1 for line in lines if line.strip()) < MIN_CODE_LINES:
            continue
        sources.append(SourceFile(path=item["path"], text=text, start=snippet_start(lines, rng, difficulty)))
        directories.add(directory)
        if len(sources) == difficulty.files:
            break
    return sources


async def repository_sources(
    github: GitHubClient, world: World, repo: dict, rng: random.Random,
) -> tuple[list[SourceFile], dict | None]:
    difficulty = world.difficulty
    if not difficulty.folders:
        files = (await repository_tree(github, world, repo))["files"]
        return await pick_sources(github, repo, files, difficulty, rng), None
    folders = [folder for folder in await repository_folders(github, world, repo["id"]) if folder["id"] != OTHER_FOLDERS]
    rng.shuffle(folders)
    folders.sort(key=lambda folder: "sha" not in folder and len(folder["files"]) < difficulty.files)
    for folder in folders[:3]:
        sources = await pick_sources(github, repo, await folder_files(github, repo, folder), difficulty, rng)
        if sources:
            return sources, folder
    return [], None


async def additional_graph_sources(
    github: GitHubClient, world: World, repo: dict, sources: list[SourceFile], folder: dict | None,
) -> list[SourceFile]:
    tree = await repository_tree(github, world, repo)
    candidates = {item["path"]: item for item in tree["graph_files"]}
    if folder:
        candidates.update({item["path"]: item for item in folder.get("graph_files", [])})
    selected = {source.path for source in sources}
    languages = {LANGUAGES.get(PurePosixPath(source.path).suffix.casefold()) for source in sources}
    directories = {str(PurePosixPath(source.path).parent) for source in sources}
    paths = [
        PurePosixPath(item["path"])
        for item in candidates.values()
        if item["path"] not in selected
        and item["size"] <= MAX_GRAPH_FILE_BYTES
        and PurePosixPath(item["path"]).suffix.casefold() in LANGUAGES
    ]
    paths.sort(key=lambda path: (
        LANGUAGES[path.suffix.casefold()] not in languages,
        str(path.parent) not in directories,
        str(path),
    ))
    paths = [str(path) for path in paths[:EXTRA_GRAPH_FILES]]
    texts = await gather(*(github.file(repo["full_name"], repo["branch"], path) for path in paths))
    return [
        SourceFile(path=path, text=text, start=0)
        for path, text in zip(paths, texts, strict=True)
        if text and "\x00" not in text and len(text.encode()) <= MAX_GRAPH_FILE_BYTES
    ]


async def world_challenge(
    github: GitHubClient, world: World, exclude: list[int],
) -> tuple[dict, list[SourceFile], dict | None, list[SourceFile]] | None:
    rng = random.Random()
    candidates = [
        repo for repo in world.catalog["repositories"]
        if repo["id"] not in exclude and repo["id"] not in world.skipped
    ]
    rng.shuffle(candidates)
    for repo in candidates[:ROUND_ATTEMPTS]:
        sources, folder = await repository_sources(github, world, repo, rng)
        if not sources:
            world.skipped.add(repo["id"])
            continue
        if not repo["languages"]:
            repo["languages"] = language_shares(await github.languages(repo["full_name"]))
        if "year" not in repo:
            repo["year"] = int((await github.repository(repo["full_name"]))["created_at"][:4])
        graph_sources = await additional_graph_sources(github, world, repo, sources, folder)
        return repo, sources, folder, graph_sources
    return None
