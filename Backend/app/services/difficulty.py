from dataclasses import dataclass
from typing import Literal

DifficultyName = Literal["easy", "medium", "hard"]


@dataclass(frozen=True)
class Difficulty:
    name: DifficultyName
    max_repositories: int
    levels: tuple[str, ...]
    level_points: tuple[int, ...]
    distance_scale: float
    files: int
    snippet_length: int
    context_length: int

    @property
    def grouped(self) -> bool:
        return "group" in self.levels

    @property
    def folders(self) -> bool:
        return "folder" in self.levels


DIFFICULTIES: dict[str, Difficulty] = {
    "easy": Difficulty(
        name="easy", max_repositories=20, levels=("region", "repository"), level_points=(1500, 5000),
        distance_scale=135, files=2, snippet_length=35, context_length=8,
    ),
    "medium": Difficulty(
        name="medium", max_repositories=80, levels=("region", "group", "repository"), level_points=(1000, 2500, 5000),
        distance_scale=90, files=3, snippet_length=50, context_length=15,
    ),
    "hard": Difficulty(
        name="hard", max_repositories=300, levels=("region", "group", "repository", "folder"),
        level_points=(750, 1750, 3500, 5000), distance_scale=60, files=4, snippet_length=70, context_length=25,
    ),
}
