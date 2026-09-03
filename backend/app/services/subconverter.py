from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote, urlencode

import aiohttp
from asyncio import TimeoutError as AsyncTimeoutError
from yarl import URL

from app.core.config import get_settings


Target = Literal["clash", "clashmeta", "singbox", "v2ray"]

# 机场 WAF 通常只放行特定代理客户端 User-Agent，且策略会随时波动（实测同一 UA
# 可能前一小时被 reset、后一小时放行；高峰期甚至全部拦截）。subconverter v0.9
# 会把调用方请求的 User-Agent 原样透传给机场抓取请求，因此这里按顺序尝试多个
# Clash 系 UA 并回退，避免单一 UA 被拦导致整个订阅刷新失败。
SUBSCRIPTION_UA_CANDIDATES = [
    "ClashforWindows/0.20.39",
    "clash-verge/v2.0.0",
    "ClashMeta/v1.8.6",
    "mihomo/v1.19.30",
]


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
        params: dict[str, str] = {
            "target": request.target,
            "url": "|".join(request.urls),
            "emoji": "true" if request.emoji else "false",
        }
        if request.config_url:
            params["config"] = request.config_url

        request_url = URL(f"{self.base_url}/sub?{build_subconverter_query(params)}", encoded=True)

        last_error: SubconverterError | None = None
        for ua in SUBSCRIPTION_UA_CANDIDATES:
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": ua}) as session:
                    async with session.get(request_url) as response:
                        body = await response.text()
                        if response.status >= 400:
                            raise SubconverterError(f"subconverter returned {response.status}: {body[:500]}")
                        if "failed" in body.lower() and "no nodes" in body.lower():
                            raise SubconverterError(body[:500])
                        return body
            except SubconverterError as exc:
                # 400 / 无节点多为机场 WAF 拦截当前 UA 所致，换下一个 UA 重试。
                last_error = exc
                continue
            except AsyncTimeoutError as exc:
                last_error = SubconverterError(f"subconverter request timed out: {self.base_url}")
                continue
            except aiohttp.ClientError as exc:
                raise SubconverterError(f"cannot connect to subconverter at {self.base_url}: {exc}") from exc

        raise SubconverterError(
            f"all user agents failed to fetch nodes from {self.base_url}: {last_error}"
        )

    async def fetch_raw(self, url: str) -> str:
        """抓取订阅原始内容（不经过 subconverter），使用同一组 UA 回退。

        tindy2013/subconverter（C++ v0.9）的解析器不认识 Clash YAML 中的 vless
        等节点类型会直接丢弃，节点池同步时用原始文本兜底补全，避免这类节点丢失。
        """
        timeout = aiohttp.ClientTimeout(total=self.settings.SUBCONVERTER_TIMEOUT_SECONDS)
        last_error: SubconverterError | None = None
        for ua in SUBSCRIPTION_UA_CANDIDATES:
            try:
                async with aiohttp.ClientSession(timeout=timeout, headers={"User-Agent": ua}) as session:
                    async with session.get(URL(url, encoded=True)) as response:
                        body = await response.text()
                        if response.status >= 400:
                            raise SubconverterError(
                                f"subscription fetch returned {response.status}: {body[:200]}"
                            )
                        if not body.strip():
                            raise SubconverterError("subscription returned empty content")
                        return body
            except SubconverterError as exc:
                # 机场 WAF 拦截当前 UA 时换下一个 UA 重试。
                last_error = exc
                continue
            except AsyncTimeoutError:
                last_error = SubconverterError(f"subscription fetch timed out: {url}")
                continue
            except aiohttp.ClientError as exc:
                raise SubconverterError(f"cannot fetch subscription {url}: {exc}") from exc

        raise SubconverterError(f"all user agents failed to fetch raw subscription {url}: {last_error}")


class PySubconverterAdapter:
    async def convert(self, request: ConvertRequest) -> str:
        raise SubconverterError("py-subconverter adapter is not enabled in this build")
