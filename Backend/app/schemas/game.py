from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

STAR_BANDS = (0, 10, 100, 300, 500, 1000, 10000, 25000, 50000, 100000, 250000)
Percentage = Annotated[int, Field(strict=True, ge=1, le=100)]


class RoundRequest(BaseModel):
    exclude: list[int] = Field(default_factory=list, max_length=20)


class Pin(BaseModel):
    x: float = Field(ge=0, le=1000)
    y: float = Field(ge=0, le=800)


class Guess(BaseModel):
    repository: str = Field(default="", max_length=200)
    pin: Pin | None = None
    languages: dict[str, Percentage] = Field(default_factory=dict, max_length=30)
    year: int | None = Field(default=None, ge=2008, le=2100)
    stars: int | None = None

    @field_validator("languages")
    @classmethod
    def validate_language_shares(cls, shares: dict[str, int]) -> dict[str, int]:
        normalized = {name.strip().casefold(): share for name, share in shares.items()}
        if "" in normalized or "none" in normalized or len(normalized) != len(shares):
            raise ValueError("Language names must be distinct, nonempty, and different from None")
        if sum(shares.values()) > 100:
            raise ValueError("Language shares may not exceed 100%")
        return normalized

    @field_validator("stars")
    @classmethod
    def validate_star_band(cls, value: int | None) -> int | None:
        if value is not None and value not in STAR_BANDS:
            raise ValueError("Use the lower bound of a star band")
        return value


class HintRequest(BaseModel):
    kind: Literal["context", "path", "region", "stars", "languages"]
