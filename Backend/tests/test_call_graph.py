import json

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.catalog import demo_repositories


def start_demo(client, repo_id):
    exclude = [int(key) for key in demo_repositories() if key != str(repo_id)]
    return client.post("/api/rounds", json={"exclude": exclude}).json()


def test_graph_exposes_one_hop_and_can_be_traversed_both_ways():
    with TestClient(create_app()) as client:
        round_ = start_demo(client, 2)
        base = f"/api/rounds/{round_['id']}"
        graph_url = base + "/graph/"
        lookup = client.get(graph_url + round_["files"][0]["entry_node_id"]).json()
        assert lookup["node"]["name"] == "lookup"
        assert {node["name"] for node in lookup["callees"]} == {"slot_for", "table.type.keyCompare"}
        assert "table.type.hashFunction" not in json.dumps(lookup)
        slot_id = next(node["id"] for node in lookup["callees"] if node["name"] == "slot_for")
        slot = client.get(graph_url + slot_id).json()
        assert lookup["node"] in slot["callers"]
        insert = next(node for node in slot["callers"] if node["name"] == "insert_if_missing")
        added = client.get(graph_url + insert["id"]).json()
        assert added["source"]["start"] == 19
        assert len(added["source"]["lines"]) >= 15
        assert slot["callees"][0]["name"] == "table.type.hashFunction"
        assert slot["source"]["start"] == 1
        assert len(slot["source"]["lines"]) > 17
        assert slot["source"]["name"] == "Файл 01"
        assert "redis/redis" not in json.dumps(slot)
        external = client.get(graph_url + slot["callees"][0]["id"]).json()
        assert external["source"] is None
        assert external["callers"] == [slot["node"]]
        assert external["callees"] == []

        client.post(base + "/hint", json={"kind": "path"})
        revealed = client.get(graph_url + slot_id).json()
        assert revealed["source"]["name"] != "Файл 01"
        assert client.get(graph_url + "unknown").status_code == 404


def test_graph_context_hint_reveals_preceding_lines():
    with TestClient(create_app()) as client:
        round_ = start_demo(client, 2)
        base = f"/api/rounds/{round_['id']}"
        graph_url = base + "/graph/" + round_["files"][0]["entry_node_id"]
        before = client.get(graph_url).json()
        assert before["source"]["start"] == 7
        client.post(base + "/hint", json={"kind": "context"})
        after = client.get(graph_url).json()
        assert after["source"]["start"] == 1
        assert after["source"]["lines"][6:] == before["source"]["lines"]


def test_every_demo_has_valid_function_sources_and_round_local_edges():
    with TestClient(create_app()) as client:
        for repo_id, demo in demo_repositories().items():
            round_ = start_demo(client, repo_id)
            base = f"/api/rounds/{round_['id']}/graph/"
            queue = [file["entry_node_id"] for file in round_["files"]]
            for node_id in queue:
                entry = client.get(base + node_id).json()
                assert any(node["has_source"] for node in entry["callers"] + entry["callees"])
            # Also validate functions disconnected from the initial clues.
            count = sum(len(functions) for functions in demo["functions"])
            queue.extend(f"n{index}" for index in range(count))
            visited = set()
            while queue:
                node_id = queue.pop()
                if node_id in visited:
                    continue
                visited.add(node_id)
                response = client.get(base + node_id)
                assert response.status_code == 200
                graph = response.json()
                if graph["node"]["has_source"]:
                    source = graph["source"]
                    assert source["lines"]
                    assert source["start"] >= 1
                    assert "full_name" not in graph
                queue.extend(node["id"] for node in graph["callers"] + graph["callees"])
