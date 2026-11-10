from fastapi import FastAPI

from app.api.router import api_router


def create_app() -> FastAPI:
    application = FastAPI(title="CodeGuessr API", version="0.1.0")
    application.state.rounds = {}
    application.include_router(api_router, prefix="/api")
    return application


app = create_app()
