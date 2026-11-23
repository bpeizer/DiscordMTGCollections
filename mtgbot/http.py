"""Tiny async HTTP helper with a polite User-Agent and simple rate limiting."""
import asyncio
import time

import aiohttp

USER_AGENT = "DiscordMTGCollectionsBot/0.1 (self-hosted Discord bot)"


class HttpError(Exception):
    def __init__(self, status: int, url: str):
        super().__init__(f"HTTP {status} from {url}")
        self.status = status


class Http:
    def __init__(self, min_interval: float = 0.12):
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._min_interval = min_interval  # Scryfall asks for <=10 requests/s

    async def _sess(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=aiohttp.ClientTimeout(total=30))
        return self._session

    async def _throttle(self):
        async with self._lock:
            wait = self._last + self._min_interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()

    async def get_json(self, url: str, params: dict | None = None):
        await self._throttle()
        s = await self._sess()
        async with s.get(url, params=params) as r:
            if r.status >= 400:
                raise HttpError(r.status, url)
            return await r.json(content_type=None)

    async def post_json(self, url: str, body: dict):
        await self._throttle()
        s = await self._sess()
        async with s.post(url, json=body) as r:
            if r.status >= 400:
                raise HttpError(r.status, url)
            return await r.json(content_type=None)

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
