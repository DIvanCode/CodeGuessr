import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.github import OwnerNotFound, RateLimited, parse_owner
from app.services.difficulty import DIFFICULTIES
from app.services.worlds import MAX_FOLDERS, OTHER_FOLDERS, folder_layout, language_shares, truncated_layout

PYTHON_SOURCE = "\n".join(f"def handler_{index}(request):\n    return request.value + {index}\n" for index in range(40))
GO_SOURCE = "\n".join(f"func Handler{index}() int {{\n    return {index}\n}}\n" for index in range(30))


def remote_repo(
    name: str, language: str | None, stars: int, *, fork: bool = False, size: int = 2048,
    description: str | None = None, topics: list[str] | None = None,
) -> dict:
    return {
        "full_name": f"acme/{name}", "fork": fork, "size": size, "language": language,
        "stargazers_count": stars, "default_branch": "main", "created_at": "2016-05-01T10:00:00Z",
        "description": description, "topics": topics or [],
    }


class FakeGitHub:
    def __init__(self, repositories: list[dict], *, failure: Exception | None = None) -> None:
        self.remote = repositories
        self.failure = failure
        self.trees = {
            "acme/api": [
                {"path": "server/app.py", "type": "blob", "size": len(PYTHON_SOURCE)},
                {"path": "client/main.go", "type": "blob", "size": len(GO_SOURCE)},
                {"path": "vendor/lib.py", "type": "blob", "size": len(PYTHON_SOURCE)},
                {"path": "README.md", "type": "blob", "size": 5000},
            ],
        }
        self.files = {"server/app.py": PYTHON_SOURCE, "client/main.go": GO_SOURCE}

    async def close(self) -> None:
        pass

    async def owner(self, login: str) -> dict:
        if self.failure:
            raise self.failure
        return {"login": "acme"}

    async def repositories(self, login: str, limit: int) -> list[dict]:
        return self.remote

    async def languages(self, full_name: str) -> dict[str, int]:
        return {"Python": 7000, "Go": 2500, "Shell": 500}

    async def tree(self, full_name: str, ref: str, *, recursive: bool = True) -> tuple[list[dict], bool]:
        return self.trees.get(full_name, []), False

    async def file(self, full_name: str, branch: str, path: str) -> str | None:
        return self.files.get(path)


@pytest.mark.parametrize("link", [
    "https://github.com/acme", "github.com/acme/", "@acme", "acme",
    "https://github.com/orgs/acme/repositories", "https://www.github.com/acme/api",
])
def test_owner_links_are_parsed(link: str) -> None:
    assert parse_owner(link) == "acme"


@pytest.mark.parametrize("link", ["https://gitlab.com/acme", "github.com/", "acme corp", "-acme"])
def test_invalid_owner_links_are_rejected(link: str) -> None:
    with pytest.raises(ValueError):
        parse_owner(link)


def test_language_shares_sum_to_one_hundred() -> None:
    assert language_shares({"Python": 2, "Go": 1}) == {"Python": 67, "Go": 33}
    assert language_shares({"C": 999, "Shell": 1}) == {"C": 100}
    assert language_shares({}) == {}


def test_world_groups_owner_repositories_into_topics() -> None:
    github = FakeGitHub([
        remote_repo("weather-bot", "Python", 500, topics=["telegram", "bot"]),
        remote_repo("notes-bot", "Go", 30, topics=["telegram", "bot"]),
        remote_repo("music-bot", None, 3, description="Discord bot for music"),
        remote_repo("snake", "Python", 20, topics=["game"]),
        remote_repo("tetris", "Go", 10, description="Tetris game in the terminal"),
        remote_repo("chess", "Rust", 5, topics=["game", "chess"]),
        remote_repo("forked", "Rust", 900, fork=True, topics=["game"]),
        remote_repo("empty", "Python", 1, size=0, topics=["bot"]),
    ])
    with TestClient(create_app(github)) as client:
        response = client.post("/api/worlds", json={"url": "https://github.com/acme"})
        assert response.status_code == 201
        world = response.json()
        assert world["owner"] == "acme"
        regions = {region["id"]: region["name"] for region in world["regions"]}
        members = {
            regions[region]: sorted(repo["name"] for repo in world["repositories"] if repo["region"] == region)
            for region in regions
        }
        assert members == {
            "bot · telegram": ["acme/music-bot", "acme/notes-bot", "acme/weather-bot"],
            "game": ["acme/chess", "acme/snake", "acme/tetris"],
        }
        assert {"Python", "Go", "Rust"}.issubset(world["language_options"])
        assert client.get(f"/api/worlds/{world['id']}").json() == world


def test_world_round_uses_repository_sources() -> None:
    github = FakeGitHub([remote_repo("api", "Python", 500), remote_repo("cli", "Go", 30)])
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme"}).json()
        response = client.post("/api/rounds", json={"world": world["id"]})
        assert response.status_code == 201
        round_ = response.json()
        assert len(round_["files"]) == 2
        assert all(file["start"] > 1 and len(file["lines"]) <= 60 for file in round_["files"])

        result = client.post(f"/api/rounds/{round_['id']}/guess", json={
            "repository": "api", "year": 2016, "languages": {"Python": 70, "Go": 25, "Shell": 5}, "stars": 500,
        }).json()["result"]
        assert result["score"] == result["max_score"]
        assert result["answer"]["full_name"] == "acme/api"
        assert sorted(file["path"] for file in result["answer"]["files"]) == ["client/main.go", "server/app.py"]
        assert result["answer"]["files"][0]["url"].startswith("https://github.com/acme/api/blob/main/")

        exhausted = client.post("/api/rounds", json={"world": world["id"], "exclude": [1]})
        assert exhausted.status_code == 409


@pytest.mark.parametrize(("extension", "caller", "callee"), [
    ("py", "def play():\n    return helper() + external()\n", "def helper():\n    return 1\n"),
    ("go", "package game\nfunc play() int { return helper() + external() }\n", "package game\nfunc helper() int { return 1 }\n"),
    ("ts", "const play = () => helper() + external();\n", "export function helper() { return 1; }\n"),
])
def test_world_round_builds_graph_from_selected_files(extension, caller, callee) -> None:
    github = FakeGitHub([remote_repo("api", "Python", 500)])
    comment = "#" if extension == "py" else "//"
    padding = f"{comment} Enough code lines to be selected for a round.\n" * 12
    github.files = {
        f"server/play.{extension}": caller + padding,
        f"shared/helper.{extension}": callee + padding,
    }
    github.trees["acme/api"] = [
        {"path": path, "type": "blob", "size": len(source)}
        for path, source in github.files.items()
    ]
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme"}).json()
        response = client.post("/api/rounds", json={"world": world["id"]})
        assert response.status_code == 201
        round_ = response.json()
        graph_url = f"/api/rounds/{round_['id']}/graph/"
        entries = {
            graph["node"]["name"]: graph
            for file in round_["files"]
            for graph in [client.get(graph_url + file["entry_node_id"]).json()]
        }
        play, helper = entries["play"], entries["helper"]
        external = next(node for node in play["callees"] if node["name"] == "external")
        assert set(node["name"] for node in play["callees"]) == {"helper", "external"}
        assert helper["callers"] == [play["node"]]
        assert helper["source"]["lines"]
        assert helper["source"]["name"].startswith("Файл ")
        assert client.get(graph_url + external["id"]).json()["source"] is None


def test_world_graph_can_open_source_outside_the_initial_clues() -> None:
    github = FakeGitHub([remote_repo("api", "Python", 500)])
    padding = "# Additional code in the same file.\n" * 70
    github.files = {
        "server/play.py": "def play():\n    return helper()\n" + padding,
        "client/other.py": "def other():\n    return 2\n" + padding,
        "server/helpers.py": "def helper():\n    return 1\n",
    }
    github.trees["acme/api"] = [
        {"path": path, "type": "blob", "size": len(source)}
        for path, source in github.files.items()
    ]
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme"}).json()
        response = client.post("/api/rounds", json={"world": world["id"]})
        assert response.status_code == 201
        round_ = response.json()
        assert len(round_["files"]) == 2
        assert all(len(file["lines"]) == 60 for file in round_["files"])
        base = f"/api/rounds/{round_['id']}"
        entries = [
            client.get(f"{base}/graph/{file['entry_node_id']}").json()
            for file in round_["files"]
        ]
        play = next(graph for graph in entries if graph["node"]["name"] == "play")
        assert len(play["source"]["lines"]) == 60
        [helper] = play["callees"]
        assert helper["name"] == "helper" and helper["has_source"]
        helper_url = f"{base}/graph/{helper['id']}"
        graph = client.get(helper_url).json()
        assert graph["source"]["file_id"] not in {file["id"] for file in round_["files"]}
        assert graph["source"]["name"] == "Файл 03"
        assert len(graph["source"]["lines"]) == 2
        assert graph["callers"] == [play["node"]]
        assert client.post(f"{base}/hint", json={"kind": "context"}).status_code == 200
        assert client.post(f"{base}/hint", json={"kind": "path"}).status_code == 200
        assert client.get(helper_url).json()["source"]["name"] == "server/helpers.py"


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
def test_graph_context_preserves_difficulty_and_folder_rounds(difficulty) -> None:
    github = FakeGitHub([remote_repo("api", "Python", 500)])
    expected = DIFFICULTIES[difficulty]
    # Leave room for the leading context as well as a complete snippet.
    padding = "# Additional code in this clue.\n" * (expected.context_length + expected.snippet_length)
    github.files = {
        f"server/play{index}.py": f"def play{index}():\n    return helper()\n" + padding
        for index in range(3)
    }
    # Small helper files are available to the graph without becoming round clues.
    github.files["server/helper.py"] = "\n" * 40 + "def helper():\n    return 1\n"
    github.trees["acme/api"] = [
        {"path": path, "type": "blob", "size": len(source)}
        for path, source in github.files.items()
    ]
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme", "difficulty": difficulty}).json()
        response = client.post("/api/rounds", json={"world": world["id"]})
        assert response.status_code == 201
        round_ = response.json()
        assert round_["difficulty"] == difficulty
        assert len(round_["files"]) == min(3, expected.files)
        assert all(len(file["lines"]) == expected.snippet_length for file in round_["files"])
        base = f"/api/rounds/{round_['id']}"
        entry = client.get(base + "/graph/" + round_["files"][0]["entry_node_id"]).json()
        assert len(entry["source"]["lines"]) == expected.snippet_length
        helper = next(node for node in entry["callees"] if node["name"] == "helper")
        assert helper["has_source"]
        helper_url = base + "/graph/" + helper["id"]
        before = client.get(helper_url).json()["source"]
        assert before["file_id"] not in {file["id"] for file in round_["files"]}
        assert before["start"] == 41
        assert client.post(base + "/hint", json={"kind": "context"}).status_code == 200
        after = client.get(helper_url).json()["source"]
        assert before["start"] - after["start"] == expected.context_length
        result = client.post(base + "/guess", json={"repository": "acme/api"}).json()["result"]
        assert (result["answer"]["folder"] is not None) == expected.folders
        assert len(result["answer"]["files"]) == len(round_["files"])


@pytest.mark.parametrize(("failure", "status"), [(OwnerNotFound("missing"), 404), (RateLimited("limit"), 503)])
def test_github_failures_are_reported(failure: Exception, status: int) -> None:
    with TestClient(create_app(FakeGitHub([], failure=failure))) as client:
        assert client.post("/api/worlds", json={"url": "acme"}).status_code == status


def test_owner_without_code_and_unknown_world() -> None:
    with TestClient(create_app(FakeGitHub([remote_repo("fork", "C", 1, fork=True)]))) as client:
        assert client.post("/api/worlds", json={"url": "acme"}).status_code == 409
        assert client.post("/api/worlds", json={"url": "https://gitlab.com/acme"}).status_code == 422
        unknown = "00000000-0000-0000-0000-000000000000"
        assert client.get(f"/api/worlds/{unknown}").status_code == 404
        assert client.post("/api/rounds", json={"world": unknown}).status_code == 404


def test_folder_layout_skips_shared_prefix_and_merges_small_folders() -> None:
    files = [{"path": f"src/pkg/mod{index}/file.py", "size": 1000 + index} for index in range(12)]
    files.append({"path": "src/pkg/setup.py", "size": 500})
    layout = folder_layout(files)
    ids = [folder["id"] for folder in layout]
    assert len(layout) == MAX_FOLDERS
    assert ids[0] == "src/pkg/mod11/"
    assert ids[-1] == OTHER_FOLDERS
    assert sum(len(folder["files"]) for folder in layout) == len(files)


def hard_world_github() -> FakeGitHub:
    github = FakeGitHub([
        {**remote_repo("api", "Python", 500), "created_at": "2014-01-01T00:00:00Z"},
        {**remote_repo("cli", "Python", 30), "created_at": "2021-01-01T00:00:00Z"},
    ])
    github.trees["acme/api"] = [
        {"path": "server/app.py", "type": "blob", "size": len(PYTHON_SOURCE)},
        {"path": "server/routes.py", "type": "blob", "size": len(PYTHON_SOURCE)},
        {"path": "client/main.go", "type": "blob", "size": len(GO_SOURCE)},
    ]
    github.files["server/routes.py"] = PYTHON_SOURCE
    return github


def test_medium_world_groups_repositories_by_primary_language() -> None:
    github = hard_world_github()
    github.remote[1]["language"] = "Go"
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme", "difficulty": "medium"}).json()
    assert world["difficulty"] == "medium"
    assert {group["name"] for group in world["groups"]} == {"Python", "Go"}
    assert all(repo["group"] for repo in world["repositories"])


def test_hard_round_targets_a_folder_and_scores_by_level() -> None:
    github = hard_world_github()
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme", "difficulty": "hard"}).json()
        folders = client.get(f"/api/worlds/{world['id']}/repositories/1/folders").json()["folders"]
        assert {folder["id"] for folder in folders} == {"server/", "client/"}

        round_ = client.post("/api/rounds", json={"world": world["id"], "exclude": [2]}).json()
        assert round_["difficulty"] == "hard"
        assert round_["hint_costs"]["path"] == 1500
        assert all(len(file["lines"]) <= 70 for file in round_["files"])

        result = client.post(f"/api/rounds/{round_['id']}/guess", json={"repository": "acme/cli"}).json()["result"]
        answer = result["answer"]
        assert answer["folder"] in {"server/", "client/"}
        assert result["location"]["repository"] == 2
        assert result["location"]["region"] == answer["region"]
        assert result["breakdown"]["repository"] >= 750

        target = next(folder for folder in folders if folder["id"] == answer["folder"])
        exact = client.post("/api/rounds", json={"world": world["id"], "exclude": [2]}).json()
        exact_result = client.post(f"/api/rounds/{exact['id']}/guess", json={
            "pin": {"x": target["x"], "y": target["y"]},
        }).json()["result"]
        expected = 5000 if exact_result["answer"]["folder"] == target["id"] else 3500
        assert exact_result["breakdown"]["repository"] >= expected
        assert exact_result["location"]["folder"] == target["id"]


def test_folders_are_available_only_on_hard_maps() -> None:
    with TestClient(create_app(hard_world_github())) as client:
        world = client.post("/api/worlds", json={"url": "acme"}).json()
        assert client.get(f"/api/worlds/{world['id']}/repositories/1/folders").status_code == 409


def test_guess_depth_limits_level_credit() -> None:
    with TestClient(create_app(hard_world_github())) as client:
        world = client.post("/api/worlds", json={"url": "acme", "difficulty": "medium"}).json()
        round_ = client.post("/api/rounds", json={"world": world["id"], "exclude": [2]}).json()
        country = next(repo for repo in world["repositories"] if repo["id"] == 1)
        result = client.post(f"/api/rounds/{round_['id']}/guess", json={
            "pin": {"x": country["x"], "y": country["y"]}, "depth": 1,
        }).json()["result"]
        assert result["location"] == {"region": country["region"], "group": country["group"], "repository": None}
        assert result["breakdown"]["repository"] == 4500


def test_truncated_tree_uses_top_level_directories() -> None:
    top = [
        {"path": "kernel", "type": "tree", "sha": "k"}, {"path": "vendor", "type": "tree", "sha": "v"},
        {"path": "mm", "type": "tree", "sha": "m"}, {"path": "init.c", "type": "blob", "size": 900},
    ]
    layout = truncated_layout(top, [{"path": "kernel/fork.c", "size": 4000}])
    assert {folder["id"]: folder.get("sha") for folder in layout} == {"kernel/": "k", "mm/": "m", "*": None}
    assert next(folder for folder in layout if folder["id"] == "mm/")["weight"] == 4000 ** 0.5


def test_github_rounds_show_snippets_and_call_graph() -> None:
    github = FakeGitHub([remote_repo("api", "Python", 500), remote_repo("cli", "Go", 30)])
    with TestClient(create_app(github)) as client:
        world = client.post("/api/worlds", json={"url": "acme"}).json()
        round_ = client.post("/api/rounds", json={"world": world["id"]}).json()
        path = f"/api/rounds/{round_['id']}"
        file = round_["files"][0]
        assert file["entry_node_id"] is not None
        graph = client.get(path + "/graph/" + file["entry_node_id"]).json()
        assert graph["node"]["has_source"]
        assert graph["source"]["lines"]
        assert file["lines"]
        expanded = client.post(path + "/hint", json={"kind": "context"}).json()["files"][0]
        assert expanded["start"] < file["start"]
