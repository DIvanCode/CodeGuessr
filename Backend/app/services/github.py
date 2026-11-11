import os
import re
from urllib.parse import quote, urlsplit

import httpx

API_URL = "https://api.github.com"
RAW_URL = "https://raw.githubusercontent.com"
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})")
RESERVED_PREFIXES = {"orgs", "users"}


class GitHubError(Exception):
    pass


class OwnerNotFound(GitHubError):
    pass


class RateLimited(GitHubError):
    pass


def parse_owner(link: str) -> str:
    text = link.strip().lstrip("@")
    if "://" not in text and text.casefold().startswith(("github.com", "www.github.com")):
        text = "https://" + text
    if "://" in text:
        parts = urlsplit(text)
        if parts.hostname not in ("github.com", "www.github.com"):
            raise ValueError("Ссылка должна вести на github.com")
        segments = [segment for segment in parts.path.split("/") if segment]
        if segments and segments[0].casefold() in RESERVED_PREFIXES:
            segments = segments[1:]
        text = segments[0] if segments else ""
    if not LOGIN.fullmatch(text):
        raise ValueError("Укажите ссылку на пользователя или организацию GitHub")
    return text


class GitHubClient:
    def __init__(self, token: str | None = None) -> None:
        headers = {"Accept": "application/vnd.github+json", "User-Agent": "CodeGuessr"}
        token = token if token is not None else os.environ.get("GITHUB_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.api = httpx.AsyncClient(base_url=API_URL, headers=headers, timeout=15)
        self.raw = httpx.AsyncClient(base_url=RAW_URL, headers={"User-Agent": "CodeGuessr"}, timeout=15)

    async def close(self) -> None:
        await self.api.aclose()
        await self.raw.aclose()

    async def get(self, path: str, **params) -> dict | list:
        try:
            response = await self.api.get(path, params=params)
        except httpx.HTTPError as error:
            raise GitHubError("GitHub недоступен. Попробуйте позже.") from error
        if response.status_code == 404:
            raise OwnerNotFound("Пользователь или организация не найдены на GitHub.")
        if response.status_code in (403, 429) and response.headers.get("x-ratelimit-remaining") == "0":
            raise RateLimited("Исчерпан лимит запросов к GitHub API. Задайте GITHUB_TOKEN или попробуйте позже.")
        if response.is_error:
            raise GitHubError(f"GitHub ответил ошибкой {response.status_code}.")
        return response.json()

    async def owner(self, login: str) -> dict:
        return await self.get(f"/users/{login}")

    async def repositories(self, login: str) -> list[dict]:
        return await self.get(f"/users/{login}/repos", type="owner", sort="pushed", per_page=100)

    async def languages(self, full_name: str) -> dict[str, int]:
        return await self.get(f"/repos/{full_name}/languages")

    async def tree(self, full_name: str, branch: str) -> list[dict]:
        data = await self.get(f"/repos/{full_name}/git/trees/{quote(branch, safe='')}", recursive=1)
        return [item for item in data.get("tree", []) if item.get("type") == "blob"]

    async def file(self, full_name: str, branch: str, path: str) -> str | None:
        try:
            response = await self.raw.get(f"/{full_name}/{quote(branch, safe='')}/{quote(path)}")
        except httpx.HTTPError:
            return None
        if response.is_error:
            return None
        try:
            return response.content.decode("utf-8")
        except UnicodeDecodeError:
            return None
