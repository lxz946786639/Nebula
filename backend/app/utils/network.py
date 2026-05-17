import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import get_settings


class UrlValidationError(ValueError):
    pass


def _host_allowed_by_allowlist(host: str, allowlist: list[str]) -> bool:
    if not allowlist:
        return True
    return any(host == item or host.endswith(f".{item}") for item in allowlist)


async def validate_subscription_url(url: str) -> None:
    settings = get_settings()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UrlValidationError("Only http and https subscription URLs are allowed")
    if not parsed.hostname:
        raise UrlValidationError("Subscription URL must include a hostname")

    host = parsed.hostname.lower()
    if not _host_allowed_by_allowlist(host, settings.url_allowlist_list):
        raise UrlValidationError("Subscription URL is outside the configured allowlist")

    if not settings.URL_BLOCK_PRIVATE_NETWORKS:
        return

    try:
        addresses = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UrlValidationError("Unable to resolve subscription hostname") from exc

    for family, _, _, _, sockaddr in addresses:
        if family not in {socket.AF_INET, socket.AF_INET6}:
            continue
        ip = ipaddress.ip_address(sockaddr[0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise UrlValidationError("Private, loopback, reserved, and multicast subscription hosts are blocked")
