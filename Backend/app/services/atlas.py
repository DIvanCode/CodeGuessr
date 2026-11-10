from functools import cache
from math import sqrt

from app.services.catalog import catalog

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


def countries(polygon: list[Point], repos: list[dict]):
    if len(repos) == 1:
        yield repos[0], polygon
        return

    bounds = [(min(p[axis] for p in polygon), max(p[axis] for p in polygon)) for axis in (0, 1)]
    axis = max(range(2), key=lambda axis: bounds[axis][1] - bounds[axis][0])
    ordered = sorted(repos, key=lambda repo: repo["map_order"][axis])
    middle = len(ordered) // 2
    left, right = ordered[:middle], ordered[middle:]
    weights = [sqrt(repo["size_mb"]) for repo in ordered]
    target = area(polygon) * sum(weights[:middle]) / sum(weights)

    # Move one straight border until the first half gets its share of the land.
    low, high = bounds[axis]
    for _ in range(14):
        cut = (low + high) / 2
        if area(clip(polygon, axis, cut, lower=True)) < target:
            low = cut
        else:
            high = cut
    cut = (low + high) / 2
    yield from countries(clip(polygon, axis, cut, lower=True), left)
    yield from countries(clip(polygon, axis, cut, lower=False), right)


def center(polygon: list[Point]) -> dict:
    return {key: round(sum(point[axis] for point in polygon) / len(polygon), 2) for axis, key in enumerate(("x", "y"))}


@cache
def atlas() -> dict:
    regions, repositories = [], []
    data = catalog()
    for region in data["regions"]:
        outline = [tuple(point) for point in region["outline"]]
        regions.append({**region, **center(outline)})
        members = [repo for repo in data["repositories"] if repo["region"] == region["id"]]
        if not members:
            continue
        for repo, polygon in countries(outline, members):
            repositories.append({
                "id": repo["id"],
                "name": repo["full_name"],
                "region": repo["region"],
                "size_mb": repo["size_mb"],
                "polygon": [[round(x, 3), round(y, 3)] for x, y in polygon],
                **center(polygon),
            })
    languages = sorted({language for repo in data["repositories"] for language in repo["languages"]}, key=str.casefold)
    return {
        "regions": regions,
        "repositories": sorted(repositories, key=lambda repo: repo["id"]),
        "language_options": languages,
    }
