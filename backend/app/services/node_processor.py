import hashlib
import re
from copy import deepcopy
from typing import Any

import yaml


COUNTRY_HINTS: list[tuple[str, str, str]] = [
    ("香港|Hong Kong|HK", "HongKong", "HK"),
    ("日本|Japan|JP|Tokyo|Osaka", "Japan", "JP"),
    ("美国|United States|USA|US|Los Angeles|San Jose|New York", "UnitedStates", "US"),
    ("新加坡|Singapore|SG", "Singapore", "SG"),
    ("台湾|Taiwan|TW", "Taiwan", "TW"),
    ("韩国|Korea|KR|Seoul", "Korea", "KR"),
    ("英国|United Kingdom|UK|London", "UnitedKingdom", "GB"),
    ("德国|Germany|DE|Frankfurt", "Germany", "DE"),
    ("法国|France|FR|Paris", "France", "FR"),
    ("加拿大|Canada|CA", "Canada", "CA"),
]

FLAG_BY_CODE = {
    "HK": "🇭🇰",
    "JP": "🇯🇵",
    "US": "🇺🇸",
    "SG": "🇸🇬",
    "TW": "🇹🇼",
    "KR": "🇰🇷",
    "GB": "🇬🇧",
    "DE": "🇩🇪",
    "FR": "🇫🇷",
    "CA": "🇨🇦",
}


def load_yaml_config(content: str) -> dict[str, Any]:
    loaded = yaml.safe_load(content) or {}
    return loaded if isinstance(loaded, dict) else {}


def dump_yaml_config(config: dict[str, Any]) -> str:
    return yaml.safe_dump(config, allow_unicode=True, sort_keys=False)


def extract_clash_proxies(content: str) -> list[dict[str, Any]]:
    config = load_yaml_config(content)
    proxies = config.get("proxies")
    if not isinstance(proxies, list):
        return []
    return [deepcopy(node) for node in proxies if isinstance(node, dict)]


def node_identity(node: dict[str, Any]) -> str:
    secret = node.get("uuid") or node.get("password") or node.get("cipher") or node.get("psk") or ""
    raw = f"{node.get('server')}|{node.get('port')}|{secret}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def detect_country(name: str, server: str | None = None) -> tuple[str | None, str | None]:
    haystack = f"{name} {server or ''}"
    for pattern, country, code in COUNTRY_HINTS:
        if re.search(pattern, haystack, re.IGNORECASE):
            return country, code
    return None, None


def _apply_rename(node: dict[str, Any], index: int, emoji: bool) -> None:
    country, code = detect_country(str(node.get("name", "")), str(node.get("server", "")))
    node["_country"] = country
    node["_country_code"] = code
    if country and code:
        prefix = f"{FLAG_BY_CODE.get(code, '')} " if emoji else ""
        node["name"] = f"{prefix}{code}-{country}-{index:02d}".strip()


def process_clash_yaml(
    content: str,
    *,
    emoji: bool,
    name_filter: str | None = None,
    rename: bool = True,
) -> tuple[str, list[dict[str, Any]]]:
    config = load_yaml_config(content)
    proxies = config.get("proxies")
    if not isinstance(proxies, list):
        return content, []

    seen: set[str] = set()
    processed: list[dict[str, Any]] = []
    for node in proxies:
        if not isinstance(node, dict):
            continue
        name = str(node.get("name", ""))
        if name_filter and name_filter.lower() not in name.lower():
            continue
        identity = node_identity(node)
        if identity in seen:
            continue
        seen.add(identity)
        processed.append(deepcopy(node))

    processed.sort(key=lambda item: (detect_country(str(item.get("name", "")))[1] or "ZZ", str(item.get("name", ""))))

    for index, node in enumerate(processed, start=1):
        if rename:
            _apply_rename(node, index, emoji)

    old_names = {str(old.get("name")) for old in proxies if isinstance(old, dict)}
    new_names = {str(new.get("name")) for new in processed}
    config["proxies"] = processed

    for group in config.get("proxy-groups", []) or []:
        if not isinstance(group, dict) or not isinstance(group.get("proxies"), list):
            continue
        static_items = [item for item in group["proxies"] if item not in old_names]
        group["proxies"] = static_items + sorted(new_names)

    public_nodes: list[dict[str, Any]] = []
    for node in processed:
        country = node.pop("_country", None)
        country_code = node.pop("_country_code", None)
        public_nodes.append(
            {
                "name": node.get("name"),
                "type": node.get("type"),
                "server": node.get("server"),
                "port": node.get("port"),
                "country": country,
                "country_code": country_code,
                "latency": None,
                "alive": None,
                "source": None,
                "raw": node,
            }
        )

    return dump_yaml_config(config), public_nodes
