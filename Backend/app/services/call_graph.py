"""Build and traverse the call graph for a round's source files."""

from collections import defaultdict

from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_for_filename
from pygments.lexers.special import TextLexer
from pygments.util import ClassNotFound


def highlight_lines(path: str, text: str) -> list[str]:
    try:
        lexer = get_lexer_for_filename(path, stripnl=False)
    except ClassNotFound:
        lexer = TextLexer(stripnl=False)
    return highlight(text, lexer, HtmlFormatter(nowrap=True)).split("\n")


def make_call_graph(functions_by_file: list[list[dict]]) -> dict:
    nodes = []
    definitions = defaultdict(list)
    local_definitions = defaultdict(list)
    for file_id, functions in enumerate(functions_by_file):
        for function in functions:
            node = {**function, "id": f"n{len(nodes)}", "file_id": file_id}
            nodes.append(node)
            key = (function.get("language"), function["name"])
            definitions[key].append(node["id"])
            local_definitions[file_id, key].append(node["id"])

    edges = set()
    external = {}
    for node in list(nodes):
        language = node.pop("language", None)
        for name in node.pop("calls"):
            key = (language, name)
            candidates = local_definitions.get((node["file_id"], key)) or definitions.get(key, [])
            if len(candidates) == 1:
                target = candidates[0]
            else:
                if key not in external:
                    external[key] = f"n{len(nodes)}"
                    nodes.append({"id": external[key], "name": name, "file_id": None})
                target = external[key]
            edges.add((node["id"], target))
    return {"nodes": {node["id"]: node for node in nodes}, "edges": sorted(edges)}


def entry_node(snapshot: dict, file_id: int) -> str | None:
    nodes = [node for node in snapshot["call_graph"]["nodes"].values() if node["file_id"] == file_id]
    if not nodes:
        return None
    line = snapshot["files"][file_id]["start"]
    def proximity(node: dict) -> tuple[int, int]:
        distance = max(node["start"] - line, line - node["end"], 0)
        return distance, node["end"] - node["start"]

    return min(nodes, key=proximity)["id"]


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
        start = max(1, node["start"] - round_.snapshot["graph_context_lines"]) if round_.hints.get("context") else node["start"]
        end = max(node["end"], node["start"] + round_.snapshot["graph_min_lines"] - 1)
        lines = file["source_text"].splitlines()[start - 1:end]
        highlighted = highlight_lines(file["path"], "\n".join(lines))[:len(lines)]
        source = {
            "file_id": node["file_id"],
            "name": file["path"] if round_.hints.get("path") or round_.result else f"Файл {node['file_id'] + 1:02d}",
            "start": start,
            "lines": highlighted,
            "has_context": node["start"] > 1,
        }
    return {
        "node": summary(node), "callers": callers, "callees": callees,
        "source": source,
    }
