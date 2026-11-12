from math import sqrt

Point = tuple[float, float]


def area(polygon: list[Point]) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]))) / 2


def clip(polygon: list[Point], axis: int, cut: float, *, lower: bool) -> list[Point]:
    output = []
    for start, end in zip(polygon[-1:] + polygon[:-1], polygon):
        start_in = start[axis] <= cut if lower else start[axis] >= cut
        end_in = end[axis] <= cut if lower else end[axis] >= cut
        if start_in != end_in:
            across = 1 - axis
            fraction = (cut - start[axis]) / (end[axis] - start[axis])
            other = start[across] + fraction * (end[across] - start[across])
            output.append((cut, other) if axis == 0 else (other, cut))
        if end_in:
            output.append(end)
    return output


def partition(polygon: list[Point], items: list[dict]):
    if len(items) == 1:
        yield items[0], polygon
        return

    bounds = [(min(p[axis] for p in polygon), max(p[axis] for p in polygon)) for axis in (0, 1)]
    axis = max(range(2), key=lambda axis: bounds[axis][1] - bounds[axis][0])
    ordered = sorted(items, key=lambda item: item["map_order"][axis])
    middle = len(ordered) // 2
    left, right = ordered[:middle], ordered[middle:]
    weights = [item["weight"] for item in ordered]
    target = area(polygon) * sum(weights[:middle]) / sum(weights)

    low, high = bounds[axis]
    for _ in range(20):
        cut = (low + high) / 2
        if area(clip(polygon, axis, cut, lower=True)) < target:
            low = cut
        else:
            high = cut
    cut = (low + high) / 2
    yield from partition(clip(polygon, axis, cut, lower=True), left)
    yield from partition(clip(polygon, axis, cut, lower=False), right)


def center(polygon: list[Point]) -> dict:
    return {key: round(sum(point[axis] for point in polygon) / len(polygon), 3) for axis, key in enumerate(("x", "y"))}


def rounded(polygon: list[Point]) -> list[list[float]]:
    return [[round(x, 3), round(y, 3)] for x, y in polygon]


def contains(polygon: list, point: Point) -> bool:
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(polygon, polygon[1:] + polygon[:1]):
        if (y1 > y) != (y2 > y) and x < x1 + (y - y1) * (x2 - x1) / (y2 - y1):
            inside = not inside
    return inside


def repository_weight(repo: dict) -> float:
    return sqrt(repo["size_mb"])


def group_items(members: list[dict]) -> list[dict]:
    names = sorted({repo["group"] for repo in members})
    groups = []
    for name in names:
        repos = [repo for repo in members if repo["group"] == name]
        groups.append({
            "name": name,
            "repos": repos,
            "weight": sum(repository_weight(repo) for repo in repos),
            "map_order": [sum(repo["map_order"][axis] for repo in repos) / len(repos) for axis in (0, 1)],
        })
    return groups


def build_atlas(data: dict) -> dict:
    regions, groups, repositories = [], [], []
    for region in data["regions"]:
        outline = [tuple(point) for point in region["outline"]]
        regions.append({**region, **center(outline)})
        members = [
            {**repo, "weight": repository_weight(repo)}
            for repo in data["repositories"] if repo["region"] == region["id"]
        ]
        if not members:
            continue
        if "group" in members[0]:
            parts = []
            for group, polygon in partition(outline, group_items(members)):
                group_id = f"{region['id']}:{group['name']}"
                groups.append({
                    "id": group_id, "name": group["name"], "region": region["id"],
                    "polygon": rounded(polygon), **center(polygon),
                })
                parts.extend((repo, part, group_id) for repo, part in partition(polygon, group["repos"]))
        else:
            parts = [(repo, part, None) for repo, part in partition(outline, members)]
        for repo, polygon, group_id in parts:
            repositories.append({
                "id": repo["id"],
                "name": repo["full_name"],
                "region": repo["region"],
                "group": group_id,
                "size_mb": repo["size_mb"],
                "polygon": rounded(polygon),
                **center(polygon),
            })
    languages = sorted({language for repo in data["repositories"] for language in repo["languages"]}, key=str.casefold)
    return {
        "regions": regions,
        "groups": groups,
        "repositories": sorted(repositories, key=lambda repo: repo["id"]),
        "language_options": languages,
    }
