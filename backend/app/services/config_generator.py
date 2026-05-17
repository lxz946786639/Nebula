from __future__ import annotations

import base64
import hashlib
import json
import re
from copy import deepcopy
from typing import Any
from urllib.parse import quote, urlencode

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.cache import cache_get_text, cache_set_text
from app.models.config_template import ConfigTemplate
from app.models.node import Node
from app.services.node_pool import sync_node_pool
from app.services.node_processor import dump_yaml_config, load_yaml_config
from app.services.settings import get_cache_ttl
from app.services.subconverter import SubconverterError


TEST_URL = "http://www.gstatic.com/generate_204"
RULESET_BASE = "https://cdn.jsdelivr.net/gh/Loyalsoldier/clash-rules@release"
COUNTRY_LABEL_BY_CODE = {
    "HK": "香港",
    "JP": "日本",
    "US": "美国",
    "SG": "新加坡",
    "TW": "台湾",
    "KR": "韩国",
    "GB": "英国",
    "DE": "德国",
    "FR": "法国",
    "CA": "加拿大",
}


def _label(icon: str, text: str, *, emoji: bool) -> str:
    return f"{icon} {text}" if emoji else text


def _country_label(node: Node) -> str:
    if node.country_code and node.country_code in COUNTRY_LABEL_BY_CODE:
        return COUNTRY_LABEL_BY_CODE[node.country_code]
    return str(node.country or node.country_code or "节点").strip()


def _node_counter_key(node: Node) -> tuple[str, str]:
    source = str(node.source_subscription_id or node.source_subscription_name or "").strip()
    return source, _country_label(node)


def _clean_node_suffix(raw_name: str, country_label: str) -> str:
    text = " ".join(raw_name.split())
    for _ in range(2):
        text = re.sub(r"^\s*[\U0001F1E6-\U0001F1FF]{2}\s*", "", text)
        text = re.sub(r"^\s*【[^】]{1,20}】\s*", "", text)
    text = re.sub(rf"^\s*{re.escape(country_label)}\s*[-_ ]?\d{{1,3}}\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*[A-Z]{2,4}\s*[-_ ]?\d{1,3}\s*", "", text)
    text = text.lstrip(" -_|丨/").strip()
    return text or raw_name


def _node_display_name(node: Node, index: int, *, emoji: bool) -> str:
    country_label = _country_label(node)
    raw_name = str(node.name or (node.raw or {}).get("name") or "Node").strip()
    raw_name = _clean_node_suffix(raw_name, country_label)
    source_name = str(node.source_subscription_name or "").strip()
    source_prefix = f"【{source_name}】" if source_name else ""
    return f"{source_prefix}{country_label}{index:02d} {raw_name}".strip()


def _string(value: Any) -> str:
    return "" if value is None else str(value).strip()


def _host_port(server: str, port: str) -> str:
    host = f"[{server}]" if ":" in server and not server.startswith("[") else server
    return f"{host}:{port}"


def _query(params: dict[str, Any]) -> str:
    filtered = {key: _string(value) for key, value in params.items() if _string(value)}
    return urlencode(filtered, quote_via=quote, safe=",/")


def _safe_fragment(name: str) -> str:
    return quote(name, safe="")


def _b64_url(content: str) -> str:
    return base64.urlsafe_b64encode(content.encode("utf-8")).decode("ascii").rstrip("=")


def _b64_std(content: str) -> str:
    return base64.b64encode(content.encode("utf-8")).decode("ascii")


def _proxy_names_by_code(nodes: list[Node], names: dict[int, str], codes: set[str]) -> list[str]:
    return [names[node.id] for node in nodes if node.country_code in codes]


def _http_rule_provider(name: str, behavior: str = "domain") -> dict[str, Any]:
    return {
        "type": "http",
        "behavior": behavior,
        "url": f"{RULESET_BASE}/{name}.txt",
        "path": f"./ruleset/{name}.yaml",
        "interval": 86400,
    }


def _default_dns() -> dict[str, Any]:
    return {
        "enable": True,
        "listen": "0.0.0.0:1053",
        "ipv6": False,
        "enhanced-mode": "fake-ip",
        "fake-ip-range": "198.18.0.1/16",
        "nameserver": ["https://223.5.5.5/dns-query", "https://doh.pub/dns-query"],
        "fallback": ["https://1.1.1.1/dns-query", "https://8.8.8.8/dns-query"],
    }


def _default_rule_providers() -> dict[str, Any]:
    return {
        "private": _http_rule_provider("private", "classical"),
        "direct": _http_rule_provider("direct", "domain"),
        "apple": _http_rule_provider("apple", "domain"),
        "google": _http_rule_provider("google", "domain"),
        "gfw": _http_rule_provider("gfw", "domain"),
    }


def _default_rules(group_names: dict[str, str]) -> list[str]:
    return [
        "RULE-SET,private,DIRECT",
        "RULE-SET,direct,DIRECT",
        "RULE-SET,apple,DIRECT",
        f"RULE-SET,google,{group_names['select']}",
        f"RULE-SET,gfw,{group_names['select']}",
        f"DOMAIN-SUFFIX,openai.com,{group_names['gpt']}",
        f"DOMAIN-SUFFIX,chatgpt.com,{group_names['gpt']}",
        f"DOMAIN-SUFFIX,oaistatic.com,{group_names['gpt']}",
        f"DOMAIN-SUFFIX,oaiusercontent.com,{group_names['gpt']}",
        f"DOMAIN-SUFFIX,netflix.com,{group_names['media']}",
        f"DOMAIN-SUFFIX,nflxvideo.net,{group_names['media']}",
        f"DOMAIN-SUFFIX,youtube.com,{group_names['media']}",
        "GEOIP,CN,DIRECT",
        f"MATCH,{group_names['final']}",
    ]


def _select_group(name: str, proxies: list[str]) -> dict[str, Any]:
    return {"name": name, "type": "select", "proxies": proxies}


def _auto_group(name: str, group_type: str, proxies: list[str]) -> dict[str, Any]:
    group: dict[str, Any] = {
        "name": name,
        "type": group_type,
        "proxies": proxies,
        "url": TEST_URL,
        "interval": 300,
    }
    if group_type == "url-test":
        group["tolerance"] = 50
    if group_type == "load-balance":
        group["strategy"] = "consistent-hashing"
    return group


def _generated_proxy_groups(nodes: list[Node], names: dict[int, str], *, emoji: bool) -> tuple[list[dict[str, Any]], dict[str, str]]:
    group_names = {
        "select": _label("🚀", "节点选择", emoji=emoji),
        "auto": _label("♻️", "自动选择", emoji=emoji),
        "fallback": _label("🛟", "故障转移", emoji=emoji),
        "load_balance": _label("⚖️", "负载均衡", emoji=emoji),
        "hk": _label("🇭🇰", "香港节点", emoji=emoji),
        "jp": _label("🇯🇵", "日本节点", emoji=emoji),
        "us": _label("🇺🇸", "美国节点", emoji=emoji),
        "media": _label("🎬", "流媒体", emoji=emoji),
        "gpt": _label("🤖", "ChatGPT", emoji=emoji),
        "final": _label("🐟", "漏网之鱼", emoji=emoji),
    }
    all_names = [names[node.id] for node in nodes]
    hk_nodes = _proxy_names_by_code(nodes, names, {"HK"}) or all_names
    jp_nodes = _proxy_names_by_code(nodes, names, {"JP"}) or all_names
    us_nodes = _proxy_names_by_code(nodes, names, {"US"}) or all_names
    media_nodes = _proxy_names_by_code(nodes, names, {"HK", "JP", "SG", "US", "TW", "KR"}) or all_names
    gpt_nodes = _proxy_names_by_code(nodes, names, {"US", "JP", "SG", "HK", "TW"}) or all_names

    entry_groups = [
        group_names["auto"],
        group_names["fallback"],
        group_names["load_balance"],
        group_names["hk"],
        group_names["jp"],
        group_names["us"],
        group_names["media"],
        group_names["gpt"],
        "DIRECT",
    ]
    groups = [
        _select_group(group_names["select"], entry_groups + all_names),
        _auto_group(group_names["auto"], "url-test", all_names),
        _auto_group(group_names["fallback"], "fallback", all_names),
        _auto_group(group_names["load_balance"], "load-balance", all_names),
        _select_group(group_names["hk"], hk_nodes),
        _select_group(group_names["jp"], jp_nodes),
        _select_group(group_names["us"], us_nodes),
        _select_group(group_names["media"], media_nodes),
        _select_group(group_names["gpt"], gpt_nodes),
        _select_group(group_names["final"], [group_names["select"], "DIRECT"] + all_names),
    ]
    return groups, group_names


def generate_clash_config(
    nodes: list[Node],
    *,
    template_content: str | None = None,
    emoji: bool = True,
) -> str:
    if not nodes:
        raise SubconverterError("No enabled nodes found in node pool")

    config = load_yaml_config(template_content) if template_content else {}
    generated_names: dict[int, str] = {}
    name_counters: dict[tuple[str, str], int] = {}
    used_names: set[str] = set()
    proxies: list[dict[str, Any]] = []

    for node in nodes:
        proxy = deepcopy(node.raw or {})
        counter_key = _node_counter_key(node)
        name_counters[counter_key] = name_counters.get(counter_key, 0) + 1
        index = name_counters[counter_key]
        name = _node_display_name(node, index, emoji=emoji)
        if name in used_names:
            name = f"{name} #{node.id}"
        used_names.add(name)
        generated_names[node.id] = name
        proxy["name"] = name
        proxies.append(proxy)

    proxy_groups, group_names = _generated_proxy_groups(nodes, generated_names, emoji=emoji)
    output: dict[str, Any] = {
        "mixed-port": config.get("mixed-port", 7890),
        "allow-lan": config.get("allow-lan", True),
        "mode": config.get("mode", "rule"),
        "log-level": config.get("log-level", "info"),
        "external-controller": config.get("external-controller", "127.0.0.1:9090"),
        "dns": config.get("dns") if isinstance(config.get("dns"), dict) else _default_dns(),
        "proxies": proxies,
        "proxy-groups": proxy_groups,
        "rule-providers": config.get("rule-providers")
        if isinstance(config.get("rule-providers"), dict)
        else _default_rule_providers(),
        "rules": config.get("rules") if isinstance(config.get("rules"), list) else _default_rules(group_names),
    }
    return dump_yaml_config(output)


async def _template_yaml_content(session: AsyncSession, template: str | None, target: str) -> str | None:
    supported_targets = [target, "mihomo", "clashmeta", "clash"]
    stmt = select(ConfigTemplate).where(ConfigTemplate.target.in_(supported_targets))
    if template:
        stmt = stmt.where(ConfigTemplate.name == template)
    else:
        stmt = stmt.where(ConfigTemplate.is_default.is_(True))
    item = await session.scalar(stmt.order_by(ConfigTemplate.id.asc()))
    return item.yaml_content if item and item.yaml_content else None


async def _enabled_nodes(session: AsyncSession, *, group: str | None = None) -> list[Node]:
    stmt = select(Node).where(Node.enabled.is_(True))
    if group:
        stmt = stmt.where(Node.source_group == group)
    stmt = stmt.order_by(Node.country_code.is_(None), Node.country_code.asc(), Node.name.asc(), Node.id.asc())
    return list((await session.scalars(stmt)).all())


def _node_pool_cache_key(
    *,
    target: str,
    group: str | None,
    template: str | None,
    emoji: bool,
    template_content: str | None,
    nodes: list[Node],
) -> str:
    hasher = hashlib.sha256()
    hasher.update(f"{target}|{group or ''}|{template or ''}|{emoji}|".encode("utf-8"))
    hasher.update((template_content or "").encode("utf-8"))
    for node in nodes:
        payload = {
            "id": node.id,
            "name": node.name,
            "raw": node.raw or {},
            "source_subscription_id": node.source_subscription_id,
            "source_subscription_name": node.source_subscription_name,
            "source_group": node.source_group,
            "updated_at": node.updated_at.isoformat() if node.updated_at else None,
        }
        hasher.update(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
    return f"sub:pool:{target}:{hasher.hexdigest()}"


async def build_clash_subscription_from_pool(
    session: AsyncSession,
    *,
    target: str,
    group: str | None,
    template: str | None,
    emoji: bool,
) -> str:
    nodes = await _enabled_nodes(session, group=group)
    if not nodes:
        sync_result = await sync_node_pool(
            session,
            group=group,
            emoji=emoji,
            audit_actor="system",
            audit_reason="客户端订阅自动补齐",
        )
        nodes = await _enabled_nodes(session, group=group)
        if not nodes:
            detail = "; ".join(sync_result.errors[:3])
            raise SubconverterError(detail or "No enabled nodes found in node pool")

    template_content = await _template_yaml_content(session, template, target)
    cache_key = _node_pool_cache_key(
        target=target,
        group=group,
        template=template,
        emoji=emoji,
        template_content=template_content,
        nodes=nodes,
    )
    cached = await cache_get_text(cache_key)
    if cached is not None:
        return cached

    content = generate_clash_config(nodes, template_content=template_content, emoji=emoji)
    await cache_set_text(cache_key, content, await get_cache_ttl(session))
    return content


def _trojan_link(raw: dict[str, Any], name: str) -> str | None:
    server = _string(raw.get("server"))
    port = _string(raw.get("port"))
    password = _string(raw.get("password"))
    if not server or not port or not password:
        return None
    params = {
        "security": "tls",
        "sni": raw.get("sni") or raw.get("servername"),
        "allowInsecure": "1" if raw.get("skip-cert-verify") else "",
        "type": raw.get("network") or "tcp",
    }
    return f"trojan://{quote(password, safe='')}@{_host_port(server, port)}?{_query(params)}#{_safe_fragment(name)}"


def _shadowsocks_link(raw: dict[str, Any], name: str) -> str | None:
    server = _string(raw.get("server"))
    port = _string(raw.get("port"))
    method = _string(raw.get("cipher") or raw.get("method"))
    password = _string(raw.get("password"))
    if not server or not port or not method or not password:
        return None
    userinfo = _b64_url(f"{method}:{password}")
    params: dict[str, Any] = {}
    if raw.get("plugin"):
        plugin = _string(raw.get("plugin"))
        opts = raw.get("plugin-opts")
        if isinstance(opts, dict):
            opts_text = ";".join(f"{key}={value}" for key, value in opts.items() if value is not None)
            plugin = f"{plugin};{opts_text}" if opts_text else plugin
        params["plugin"] = plugin
    suffix = f"?{_query(params)}" if params else ""
    return f"ss://{userinfo}@{_host_port(server, port)}{suffix}#{_safe_fragment(name)}"


def _hysteria2_link(raw: dict[str, Any], name: str) -> str | None:
    server = _string(raw.get("server"))
    port = _string(raw.get("port"))
    password = _string(raw.get("password"))
    if not server or not port or not password:
        return None
    params = {
        "sni": raw.get("sni"),
        "insecure": "1" if raw.get("skip-cert-verify") else "",
        "obfs": raw.get("obfs"),
        "obfs-password": raw.get("obfs-password"),
    }
    alpn = raw.get("alpn")
    if isinstance(alpn, list):
        params["alpn"] = ",".join(str(item) for item in alpn)
    elif alpn:
        params["alpn"] = alpn
    return f"hysteria2://{quote(password, safe='')}@{_host_port(server, port)}?{_query(params)}#{_safe_fragment(name)}"


def _vmess_link(raw: dict[str, Any], name: str) -> str | None:
    server = _string(raw.get("server"))
    port = _string(raw.get("port"))
    uuid = _string(raw.get("uuid"))
    if not server or not port or not uuid:
        return None
    network = _string(raw.get("network")) or "tcp"
    ws_opts = raw.get("ws-opts") if isinstance(raw.get("ws-opts"), dict) else {}
    grpc_opts = raw.get("grpc-opts") if isinstance(raw.get("grpc-opts"), dict) else {}
    headers = ws_opts.get("headers") if isinstance(ws_opts.get("headers"), dict) else {}
    payload = {
        "v": "2",
        "ps": name,
        "add": server,
        "port": port,
        "id": uuid,
        "aid": _string(raw.get("alterId") or raw.get("alterid") or raw.get("aid") or "0"),
        "scy": _string(raw.get("cipher") or raw.get("security") or "auto"),
        "net": network,
        "type": _string(raw.get("headerType") or "none") if network == "tcp" else "none",
        "host": _string(headers.get("Host") or raw.get("servername") or raw.get("sni")),
        "path": _string(ws_opts.get("path") or grpc_opts.get("grpc-service-name") or raw.get("path")),
        "tls": "tls" if raw.get("tls") or raw.get("sni") else "",
        "sni": _string(raw.get("sni") or raw.get("servername")),
    }
    return f"vmess://{_b64_std(json.dumps(payload, ensure_ascii=False, separators=(',', ':')))}"


def _vless_link(raw: dict[str, Any], name: str) -> str | None:
    server = _string(raw.get("server"))
    port = _string(raw.get("port"))
    uuid = _string(raw.get("uuid"))
    if not server or not port or not uuid:
        return None
    network = _string(raw.get("network")) or "tcp"
    ws_opts = raw.get("ws-opts") if isinstance(raw.get("ws-opts"), dict) else {}
    grpc_opts = raw.get("grpc-opts") if isinstance(raw.get("grpc-opts"), dict) else {}
    headers = ws_opts.get("headers") if isinstance(ws_opts.get("headers"), dict) else {}
    params = {
        "encryption": raw.get("encryption") or "none",
        "security": "tls" if raw.get("tls") or raw.get("sni") else "none",
        "sni": raw.get("sni") or raw.get("servername"),
        "type": network,
        "host": headers.get("Host"),
        "path": ws_opts.get("path"),
        "serviceName": grpc_opts.get("grpc-service-name"),
        "flow": raw.get("flow"),
    }
    return f"vless://{quote(uuid, safe='')}@{_host_port(server, port)}?{_query(params)}#{_safe_fragment(name)}"


def _share_link(raw: dict[str, Any], name: str) -> str | None:
    node_type = _string(raw.get("type")).lower()
    if node_type == "trojan":
        return _trojan_link(raw, name)
    if node_type in {"ss", "shadowsocks"}:
        return _shadowsocks_link(raw, name)
    if node_type in {"hysteria2", "hy2"}:
        return _hysteria2_link(raw, name)
    if node_type == "vmess":
        return _vmess_link(raw, name)
    if node_type == "vless":
        return _vless_link(raw, name)
    return None


def generate_v2ray_subscription(nodes: list[Node], *, emoji: bool = True) -> str:
    links: list[str] = []
    name_counters: dict[tuple[str, str], int] = {}
    for node in nodes:
        raw = deepcopy(node.raw or {})
        counter_key = _node_counter_key(node)
        name_counters[counter_key] = name_counters.get(counter_key, 0) + 1
        index = name_counters[counter_key]
        name = _node_display_name(node, index, emoji=emoji)
        link = _share_link(raw, name)
        if link:
            links.append(link)
    if not links:
        raise SubconverterError("No v2rayN-compatible nodes found in node pool")
    return _b64_std("\n".join(links))


async def build_v2ray_subscription_from_pool(
    session: AsyncSession,
    *,
    group: str | None,
    emoji: bool,
) -> str:
    nodes = await _enabled_nodes(session, group=group)
    if not nodes:
        sync_result = await sync_node_pool(
            session,
            group=group,
            emoji=emoji,
            audit_actor="system",
            audit_reason="客户端订阅自动补齐",
        )
        nodes = await _enabled_nodes(session, group=group)
        if not nodes:
            detail = "; ".join(sync_result.errors[:3])
            raise SubconverterError(detail or "No enabled nodes found in node pool")
    cache_key = _node_pool_cache_key(
        target="v2ray",
        group=group,
        template=None,
        emoji=emoji,
        template_content=None,
        nodes=nodes,
    )
    cached = await cache_get_text(cache_key)
    if cached is not None:
        return cached

    content = generate_v2ray_subscription(nodes, emoji=emoji)
    await cache_set_text(cache_key, content, await get_cache_ttl(session))
    return content
