import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.github import OwnerNotFound, RateLimited, parse_owner
from app.services.worlds import language_shares

PYTHON_SOURCE = "\n".join(f"def handler_{index}(request):\n    return request.value + {index}\n" for index in range(40))
GO_SOURCE = "\n".join(f"func Handler{index}() int {{\n    return {index}\n}}\n" for index in range(30))


def remote_repo(name: str, language: str | None, stars: int, *, fork: bool = False, size: int = 2048) -> dict:
    return {
        "full_name": f"acme/{name}", "fork": fork, "size": size, "language": language,
        "stargazers_count": stars, "default_branch": "main", "created_at": "2016-05-01T10:00:00Z",
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

    async def repositories(self, login: str) -> list[dict]:
        return self.remote

    async def languages(self, full_name: str) -> dict[str, int]:
        return {"Python": 7000, "Go": 2500, "Shell": 500}

    async def tree(self, full_name: str, branch: str) -> list[dict]:
        return self.trees.get(full_name, [])

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


def test_world_groups_owner_repositories_by_primary_language() -> None:
    github = FakeGitHub([
        remote_repo("api", "Python", 500), remote_repo("cli", "Go", 30),
        remote_repo("docs", None, 3), remote_repo("forked", "Rust", 900, fork=True),
        remote_repo("empty", "Python", 1, size=0),
    ])
    with TestClient(create_app(github)) as client:
        response = client.post("/api/worlds", json={"url": "https://github.com/acme"})
        assert response.status_code == 201
        world = response.json()
        assert world["owner"] == "acme"
        assert [region["name"] for region in world["regions"]] == ["Python", "Go", "Другое"]
        assert [repo["name"] for repo in world["repositories"]] == ["acme/api", "acme/cli", "acme/docs"]
        assert {"Python", "Go"}.issubset(world["language_options"])
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
