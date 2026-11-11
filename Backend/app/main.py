from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.router import api_router
from app.services.github import GitHubClient


def create_app(github: GitHubClient | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.github = github or GitHubClient()
        yield
        await application.state.github.close()

    application = FastAPI(title="CodeGuessr API", version="0.1.0", lifespan=lifespan)
    application.state.rounds = {}
    application.state.worlds = {}
    application.include_router(api_router, prefix="/api")
    return application


app = create_app()
