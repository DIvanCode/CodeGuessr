from fastapi import APIRouter, HTTPException

from app.services.catalog import catalog, demo_repositories

router = APIRouter()


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
async def ready() -> dict[str, str]:
    try:
        if catalog()["repositories"] and demo_repositories():
            return {"status": "ok"}
    except (OSError, ValueError, KeyError):
        pass
    raise HTTPException(503, "Demo catalogue unavailable")
