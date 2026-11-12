from dataclasses import dataclass


@dataclass
class SourceFile:
    path: str
    text: str
    start: int
