from fastapi import APIRouter

from app.api.routes import game, health

api_router = APIRouter()
api_router.include_router(health.router, tags=["health"])
api_router.include_router(game.router, tags=["game"])
