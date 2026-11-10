from math import sqrt

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.atlas import area
from app.services.catalog import demo_repositories


def test_map_partitions_each_continent_by_repository_size() -> None:
    with TestClient(create_app()) as client:
        data = client.get("/api/map").json()
    repos = data["repositories"]
    assert len({repo["id"] for repo in repos}) == len(repos) == 100
    for continent in data["regions"]:
        members = [repo for repo in repos if repo["region"] == continent["id"]]
        total_area = area(continent["outline"])
        weight = sum(sqrt(repo["size_mb"]) for repo in members)
        assert abs(sum(area(repo["polygon"]) for repo in members) - total_area) < 1
        for repo in members:
            expected = total_area * sqrt(repo["size_mb"]) / weight
            assert abs(area(repo["polygon"]) - expected) < expected * 0.02


def test_round_accepts_country_guesses_and_preserves_result() -> None:
    with TestClient(create_app()) as client:
        exclude = [int(repo_id) for repo_id in demo_repositories() if repo_id != "1"]
        response = client.post("/api/rounds", json={"exclude": exclude})
        assert response.status_code == 201
        round_ = response.json()
        assert all(file["name"].startswith("Файл ") for file in round_["files"])
        path = f"/api/rounds/{round_['id']}"
        assert client.post(path + "/hint", json={"kind": "region"}).json()["region"] == "systems"
        answer = client.post(path + "/guess", json={"repository": "torvalds/linux"}).json()["result"]
        assert answer["score"] == 4000
        assert answer["answer"]["size_mb"] > 0
        assert answer["selected_repository_id"] == 1
        assert client.post(path + "/guess", json={}).json()["result"] == answer


def test_language_shares_and_star_band_hints() -> None:
    exclude = [int(repo_id) for repo_id in demo_repositories() if repo_id != "1"]
    with TestClient(create_app()) as client:
        data = client.get("/api/map").json()
        assert {"C", "Assembly", "Shell"}.issubset(data["language_options"])
        assert all("languages" not in repo and "stars" not in repo for repo in data["repositories"])

        round_ = client.post("/api/rounds", json={"exclude": exclude}).json()
        path = f"/api/rounds/{round_['id']}"
        assert round_["hint_values"] == {}
        assert client.post(path + "/guess", json={"languages": {"C": 95, "Python": 6}}).status_code == 422
        assert client.post(path + "/guess", json={"stars": 254956}).status_code == 422

        languages = client.post(path + "/hint", json={"kind": "languages"}).json()
        assert languages["hint_values"] == {"languages": ["C", "Assembly", "Shell"]}
        assert languages["hint_costs"]["languages"] == languages["hint_costs"]["region"] == 1000
        stars = client.post(path + "/hint", json={"kind": "stars"}).json()
        assert stars["hint_values"]["stars"] == 254956
        assert client.post(path + "/hint", json={"kind": "stars"}).json() == stars

        result = client.post(path + "/guess", json={
            "repository": "torvalds/linux",
            "languages": {"c": 60, "Assembly": 8, "Python": 10},
            "stars": 250000,
        }).json()["result"]
        assert result["breakdown"] == {"repository": 5000, "year": 0, "languages": 650, "stars": 750}
        assert result["penalty"] == 1000 + result["breakdown"]["stars"]
        assert result["score"] == 4650
        assert result["answer"]["languages"] == {"C": 94, "Assembly": 5, "Shell": 1}


def test_exact_distributions_reach_the_round_maximum() -> None:
    exclude = [int(repo_id) for repo_id in demo_repositories() if repo_id != "1"]
    with TestClient(create_app()) as client:
        round_ = client.post("/api/rounds", json={"exclude": exclude}).json()
        response = client.post(f"/api/rounds/{round_['id']}/guess", json={
            "repository": "torvalds/linux",
            "year": 2011,
            "languages": {"C": 94, "Assembly": 5, "Shell": 1},
            "stars": 250000,
        })
    result = response.json()["result"]
    assert result["score"] == result["max_score"] == 8750
