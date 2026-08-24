from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlencode

import aiohttp
from asyncio import TimeoutError as AsyncTimeoutError
from yarl import URL

from app.core.config import get_settings


Target = Literal["clash", "clashmeta", "singbox", "v2ray"]


@dataclass(frozen=True)
class ConvertRequest:
    target: Target
    urls: list[str]
    config_url: str | None = None
    emoji: bool = True


class SubconverterError(RuntimeError):
    pass


def build_subconverter_query(params: dict[str, str]) -> str:
    return urlencode(params, quote_via=quote, safe="")


class SubconverterClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.settings = get_settings()

    async def health(self) -> bool:
        try:
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{self.base_url}/version") as response:
                    return 200 <= response.status < 400
        except (aiohttp.ClientError, AsyncTimeoutError):
            return False

    async def convert(self, request: ConvertRequest) -> str:
        if not request.urls:
            raise SubconverterError("No enabled subscriptions found")

        timeout = aiohttp.ClientTimeout(total=self.settings.SUBCONVERTER_TIMEOUT_SECONDS)
        # subconverter v0.9 会把调用方请求的 User-Agent 透传给机场抓取请求；
        # 部分机场 WAF 只放行代理客户端 UA（Clash 系），默认 aiohttp UA 会被 403 拦截。
        headers = {"User-Agent": "ClashforWindows/0.20.39"}
        params: dict[str, str] = {
            "target": request.target,
            "url": "|".join(request.urls),
            "emoji": "true" if request.emoji else "false",
        }
        if request.config_url:
            params["config"] = request.config_url

        request_url = URL(f"{self.base_url}/sub?{build_subconverter_query(params)}", encoded=True)

        try:
            async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
                async with session.get(request_url) as response:
                    body = await response.text()
                    if response.status >= 400:
                        raise SubconverterError(f"subconverter returned {response.status}: {body[:500]}")
                    if "failed" in body.lower() and "no nodes" in body.lower():
                        raise SubconverterError(body[:500])
                    return body
        except AsyncTimeoutError as exc:
            raise SubconverterError(f"subconverter request timed out: {self.base_url}") from exc
        except aiohttp.ClientError as exc:
            raise SubconverterError(f"cannot connect to subconverter at {self.base_url}: {exc}") from exc


class PySubconverterAdapter:
    async def convert(self, request: ConvertRequest) -> str:
        raise SubconverterError("py-subconverter adapter is not enabled in this build")
