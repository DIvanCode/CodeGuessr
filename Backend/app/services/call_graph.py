"""Call relationships curated alongside the demo sources (not a repository index)."""


def make_call_graph(demo: dict) -> dict:
    nodes = []
    definitions = {}
    for file_id, functions in enumerate(demo["functions"]):
        for function in functions:
            node = {**function, "id": f"n{len(nodes)}", "file_id": file_id}
            nodes.append(node)
            definitions[function["name"]] = node["id"]

    edges = set()
    external = {}
    for node in list(nodes):
        for name in node.pop("calls"):
            target = definitions.get(name)
            if target is None:
                if name not in external:
                    external[name] = f"n{len(nodes)}"
                    nodes.append({"id": external[name], "name": name, "file_id": None})
                target = external[name]
            edges.add((node["id"], target))
    return {"nodes": {node["id"]: node for node in nodes}, "edges": sorted(edges)}


def entry_node(snapshot: dict, file_id: int) -> str:
    nodes = [node for node in snapshot["call_graph"]["nodes"].values() if node["file_id"] == file_id]
    line = snapshot["files"][file_id]["start"]
    # Prefer the innermost function containing the initial clue.
    containing = [node for node in nodes if node["start"] <= line <= node["end"]]
    return min(containing or nodes, key=lambda node: node["end"] - node["start"])["id"]


def neighborhood(round_, node_id: str) -> dict:
    graph = round_.snapshot["call_graph"]
    node = graph["nodes"][node_id]

    def summary(item: dict) -> dict:
        return {"id": item["id"], "name": item["name"], "has_source": item["file_id"] is not None}

    callers = [summary(graph["nodes"][source]) for source, target in graph["edges"] if target == node_id]
    callees = [summary(graph["nodes"][target]) for source, target in graph["edges"] if source == node_id]
    source = None
    if node["file_id"] is not None:
        file = round_.snapshot["files"][node["file_id"]]
        start = max(1, node["start"] - 8) if round_.hints.get("context") else node["start"]
        source = {
            "file_id": node["file_id"],
            "name": file["path"] if round_.hints.get("path") or round_.result else f"Файл {node['file_id'] + 1:02d}",
            "start": start,
            "lines": file["full_lines"][start - 1:node["end"]],
            "has_context": node["start"] > 1,
        }
    return {
        "node": summary(node), "callers": callers, "callees": callees,
        "source": source,
    }
