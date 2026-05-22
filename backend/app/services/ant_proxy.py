from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import hmac
import json
import os
import re
import socket
import ssl
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import aiohttp
import msgpack
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import BACKEND_DIR, get_settings
from app.models.ant_proxy_state import AntProxyState

try:
    from cryptography.hazmat.decrepit.ciphers import modes as decrepit_modes
except Exception:  # pragma: no cover - older cryptography versions do not expose decrepit modes
    decrepit_modes = None

CFB_MODE = decrepit_modes.CFB if decrepit_modes is not None else modes.CFB


DEFAULT_TEST_URL = "http://www.gstatic.com/generate_204"
DEFAULT_ANT_APP_VERSION = "2.0.9"
DEFAULT_ANT_LISTEN_PORT = 37890
DEFAULT_ANT_HEALTH_CHECK_INTERVAL = 300
DEFAULT_ANT_TOLERANCE = 100
ANT_MIHOMO_GROUP_NAME = "Nebula::AntProxy::蚂蚁代理"
ANT_MIHOMO_LISTENER_NAME = "nebula-ant-proxy"
ANT_API_URLS = [
    "https://antapi.djjecybb.org/api.php",
    "https://antapi2.djjecybb.org/api.php",
    "https://antapi3.djjecybb.org/api.php",
]
ANT_API_PASSWORD = "ce5298097d5ed5c5b4a9f3d67b131521"
ANT_API_SIGN_SECRET = "670a144397b862c514d40ae5f4d36a53"
ANT_API_APP_ID = "pc"
ANT_API_OAUTH_TYPE = "pc"
ANT_API_APP_TYPE = "local"
ANT_PROXY_STATE_VERSION = 1
ANT_PROXY_STATE_ALGORITHM = "aes-256-cfb+hmac-sha256+msgpack"
ANT_PROXY_STATE_NAME = "default"
ANT_PROXY_DYNAMIC_DATA_KEYS = {
    "connections",
    "connection",
    "online",
    "onlinecount",
    "online_count",
    "status",
    "latency",
    "latency_ms",
    "delay",
    "ping",
}


class AntProxyError(ValueError):
    pass


@dataclass(slots=True)
class AntNode:
    id: str
    source: str
    group: str
    name: str
    city: str
    country: str
    country_code: str
    pay_type: str
    line_type: str
    line_label: str
    online_connections: int | None
    status: int | None
    latency_ms: int | None
    server: str
    port: int
    password: str
    cipher: str
    transport: str
    tls: bool
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SocksTarget:
    atyp: int
    host: str
    port: int
    raw_address: bytes


class ShadowsocksStream:
    def __init__(self, method: str, password: str) -> None:
        if method.lower() != "aes-256-cfb":
            raise AntProxyError(f"暂不支持的加密方式：{method}")
        self.key = _evp_bytes_to_key(password.encode("utf-8"), 32)
        self.iv_length = 16
        self._encryptor = None
        self._decryptor = None
        self._decrypt_pending = b""

    def encrypt_first(self, data: bytes) -> bytes:
        iv = os.urandom(self.iv_length)
        cipher = Cipher(algorithms.AES(self.key), CFB_MODE(iv))
        self._encryptor = cipher.encryptor()
        return iv + self._encryptor.update(data)

    def encrypt(self, data: bytes) -> bytes:
        if not self._encryptor:
            return self.encrypt_first(data)
        return self._encryptor.update(data)

    def decrypt(self, data: bytes) -> bytes:
        if self._decryptor:
            return self._decryptor.update(data)

        self._decrypt_pending += data
        if len(self._decrypt_pending) <= self.iv_length:
            return b""

        iv = self._decrypt_pending[: self.iv_length]
        payload = self._decrypt_pending[self.iv_length :]
        self._decrypt_pending = b""
        cipher = Cipher(algorithms.AES(self.key), CFB_MODE(iv))
        self._decryptor = cipher.decryptor()
        return self._decryptor.update(payload)


class AntProxyService:
    def __init__(self) -> None:
        self.db_path: Path | None = None
        self.db_filename = ""
        self.source_type = "none"
        self.source_label = "未加载"
        self.client_id = ""
        self.api_url = ""
        self.app_version = DEFAULT_ANT_APP_VERSION
        self.data: dict[str, Any] | None = None
        self.nodes: list[AntNode] = []
        self.selected_node_id: str | None = None
        self.aff = 0
        self.user_summary: dict[str, Any] = {}
        self.last_loaded_at: datetime | None = None
        self.last_error: str | None = None
        self.last_latency_tested_at: datetime | None = None
        self.legacy_state_path = _resolve_backend_path(get_settings().ANT_PROXY_STATE_PATH)
        self.persisted = False
        self.last_persisted_at: datetime | None = None
        self.health_check_url = DEFAULT_TEST_URL
        self.health_check_interval = DEFAULT_ANT_HEALTH_CHECK_INTERVAL
        self.tolerance = DEFAULT_ANT_TOLERANCE

        self._adapter_servers: dict[str, asyncio.AbstractServer] = {}
        self._adapter_extra_servers: list[asyncio.AbstractServer] = []
        self._adapter_ports: dict[str, int] = {}
        self._adapter_bind_host = "127.0.0.1"
        self._adapter_connect_host = "127.0.0.1"
        self._listen_host = "127.0.0.1"
        self._listen_port = DEFAULT_ANT_LISTEN_PORT
        self._writers: set[asyncio.StreamWriter] = set()
        self._lock = asyncio.Lock()
        self.started_at: datetime | None = None
        self.active_connections = 0
        self.total_connections = 0
        self.upload_bytes = 0
        self.download_bytes = 0

    @property
    def running(self) -> bool:
        return bool(self._adapter_servers)

    @property
    def endpoint(self) -> str:
        return f"socks5://{self._listen_host}:{self._listen_port}"

    def load_db(self, db_path: str | None = None) -> None:
        if db_path:
            path = Path(db_path).expanduser()
        elif self.db_path is not None:
            path = self.db_path
        else:
            raise AntProxyError("请上传 ant.db 文件，或使用 Ant 账号登录")
        if not path.exists():
            raise AntProxyError(f"找不到 Ant 数据库：{path}")

        try:
            data = msgpack.unpackb(path.read_bytes(), raw=False, strict_map_key=False)
        except Exception as exc:
            raise AntProxyError(f"Ant 数据库解析失败：{exc}") from exc
        self._apply_data(
            data,
            source_type="local",
            source_label=path.name,
            db_path=path,
            db_filename=path.name,
        )

    def load_db_bytes(
        self,
        content: bytes,
        filename: str = "ant.db",
        app_version: str = DEFAULT_ANT_APP_VERSION,
    ) -> None:
        if not content:
            raise AntProxyError("上传的 ant.db 文件为空")
        app_version = app_version.strip() or DEFAULT_ANT_APP_VERSION
        try:
            data = msgpack.unpackb(content, raw=False, strict_map_key=False)
        except Exception as exc:
            raise AntProxyError(f"Ant 数据库解析失败：{exc}") from exc
        safe_name = Path(filename or "ant.db").name
        self._apply_data(
            data,
            source_type="upload",
            source_label=safe_name,
            db_path=None,
            db_filename=safe_name,
            app_version=app_version,
        )

    async def login(self, *, username: str, password: str, app_version: str = DEFAULT_ANT_APP_VERSION) -> None:
        username = username.strip()
        password = password.strip()
        app_version = app_version.strip() or DEFAULT_ANT_APP_VERSION
        if not username or not password:
            raise AntProxyError("请输入 Ant 账号和密码")

        client_id = self.client_id or _generate_client_id()
        api_urls = _api_urls_from_data(self.data) or ANT_API_URLS
        login_payload = {
            "mod": "user",
            "code": "userLogin",
            "username": username,
            "pwd": password,
            "type": "login",
        }
        login_response, api_url = await _ant_api_post(
            login_payload,
            client_id=client_id,
            app_version=app_version,
            api_urls=api_urls,
        )
        if not _ant_login_success(login_response):
            raise AntProxyError(_ant_response_message(login_response) or "Ant 账号登录失败")

        home_response, api_url = await _ant_api_post(
            {"mod": "index", "code": "homePage"},
            client_id=client_id,
            app_version=app_version,
            api_urls=_prioritized_urls(api_url, api_urls),
        )
        data = _normalize_api_home(home_response, client_id=client_id)
        self._apply_data(
            data,
            source_type="account",
            source_label=_mask_account(username),
            db_path=None,
            db_filename="",
            client_id=client_id,
            api_url=api_url,
            app_version=app_version,
        )

    async def refresh_account_nodes(self, *, line_type: str | None = None) -> dict[str, int]:
        self.ensure_loaded()
        if self.source_type != "account":
            raise AntProxyError("ant.db登录的数据只能通过重新上传 ant.db 更新")
        if not self.client_id:
            raise AntProxyError("缺少 Ant 登录标识，请重新登录")

        selected_line = _normalize_line_filter(line_type)
        refresh_groups = _account_refresh_groups(selected_line)
        data = copy.deepcopy(self.data or {})
        server_list = data.get("ServerList")
        if not isinstance(server_list, dict):
            server_list = {}
            data["ServerList"] = server_list
        group_tips = data.get("ServerGroupTips")
        if not isinstance(group_tips, dict):
            group_tips = {}
            data["ServerGroupTips"] = group_tips

        refresh_group_keys = {group for group, _, _ in refresh_groups}
        refresh_group_keys.update({"freegroup" if group == "1" else "paidgroup" for group, _, _ in refresh_groups})
        for key in list(server_list.keys()):
            if str(key).strip().lower() in refresh_group_keys:
                server_list.pop(key, None)

        api_urls = _api_urls_from_data(data) or ANT_API_URLS
        app_version = self.app_version or DEFAULT_ANT_APP_VERSION
        api_url = self.api_url
        refreshed: dict[str, int] = {"free": 0, "paid": 0}

        for group, ant_line_type, public_line_type in refresh_groups:
            response, api_url = await _ant_api_post(
                {
                    "cf": "",
                    "mod": "index",
                    "code": "index",
                    "line_type": ant_line_type,
                },
                client_id=self.client_id,
                app_version=app_version,
                api_urls=_prioritized_urls(api_url, api_urls) if api_url else api_urls,
            )
            raw_servers = _ensure_list(response.get("data"))
            servers = [_normalize_api_server(item) for item in raw_servers]
            normalized_servers = [item for item in servers if item is not None]
            normalized_servers.sort(key=_server_connections_sort_key)
            server_list[group] = normalized_servers
            group_tips[group] = str(response.get("servers_tip") or response.get("tip") or "")
            refreshed[public_line_type] = len(normalized_servers)
            api_urls = _prioritized_urls(api_url, api_urls)

        if selected_line is None:
            api_home = data.get("ApiHome")
            if isinstance(api_home, dict):
                api_home["Servers"] = []
            data.pop("UseServer", None)

        self._apply_data(
            data,
            source_type="account",
            source_label=self.source_label,
            db_path=None,
            db_filename="",
            client_id=self.client_id,
            api_url=api_url,
            app_version=app_version,
            selected_node_id=self.selected_node_id,
        )
        self.last_latency_tested_at = None
        return refreshed

    def ensure_loaded(self) -> None:
        if self.nodes:
            return
        raise AntProxyError("请先上传 ant.db 文件，或使用 Ant 账号登录")

    def status(self, *, auto_load: bool = True) -> dict[str, Any]:
        selected = self.selected_node
        return {
            "db_path": str(self.db_path) if self.db_path else "",
            "db_exists": bool(self.db_path and self.db_path.exists()),
            "db_filename": self.db_filename,
            "source_type": self.source_type,
            "source_label": self.source_label,
            "client_id": _mask_middle(self.client_id, keep_start=4, keep_end=4),
            "api_url": _redact_url(self.api_url),
            "app_version": self.app_version,
            "loaded": bool(self.nodes),
            "logged_in": bool(self.user_summary.get("logged_in")),
            "user": self.user_summary,
            "node_count": len(self.nodes),
            "free_node_count": len([node for node in self.nodes if node.line_type == "free"]),
            "paid_node_count": len([node for node in self.nodes if node.line_type == "paid"]),
            "selected_node": self.public_node(selected) if selected else None,
            "running": self.running,
            "listen_host": self._listen_host,
            "listen_port": self._listen_port,
            "endpoint": self.endpoint,
            "runtime_mode": "mihomo",
            "mihomo_group": ANT_MIHOMO_GROUP_NAME,
            "adapter_count": len(self._adapter_servers),
            "health_check_url": self.health_check_url,
            "health_check_interval": self.health_check_interval,
            "tolerance": self.tolerance,
            "active_connections": self.active_connections,
            "total_connections": self.total_connections,
            "upload_bytes": self.upload_bytes,
            "download_bytes": self.download_bytes,
            "started_at": self.started_at,
            "last_loaded_at": self.last_loaded_at,
            "last_latency_tested_at": self.last_latency_tested_at,
            "persisted": self.persisted,
            "last_persisted_at": self.last_persisted_at,
            "last_error": self.last_error,
        }

    async def restore(self, session: AsyncSession) -> bool:
        row = await session.scalar(select(AntProxyState).where(AntProxyState.name == ANT_PROXY_STATE_NAME))
        if row is not None and row.encrypted_payload:
            try:
                envelope = json.loads(row.encrypted_payload)
                self._restore_payload(_decrypt_state_payload(envelope))
                self.persisted = True
                self.last_persisted_at = _parse_datetime(str(envelope.get("saved_at") or "")) or row.updated_at
                self.last_error = None
                return True
            except Exception as exc:
                self.persisted = False
                self.last_persisted_at = None
                self.last_error = f"Ant 数据库状态恢复失败：{exc}"
                return False

        if not self.legacy_state_path.exists():
            self.persisted = False
            self.last_persisted_at = None
            return False

        try:
            envelope = json.loads(self.legacy_state_path.read_text(encoding="utf-8"))
            self._restore_payload(_decrypt_state_payload(envelope))
            await self.save_state(session)
            self.last_error = None
            return True
        except Exception as exc:
            self.persisted = False
            self.last_persisted_at = None
            self.last_error = f"Ant 旧版持久化状态导入失败：{exc}"
            return False

    def _restore_payload(self, payload: dict[str, Any]) -> None:
        if _safe_int(payload.get("version")) != ANT_PROXY_STATE_VERSION:
            raise AntProxyError("持久化状态版本不兼容")

        listen_host = str(payload.get("listen_host") or self._listen_host).strip() or self._listen_host
        listen_port = _safe_int(payload.get("listen_port")) or self._listen_port
        if listen_port < 1 or listen_port > 65535:
            listen_port = self._listen_port
        self.health_check_url = str(payload.get("health_check_url") or DEFAULT_TEST_URL).strip() or DEFAULT_TEST_URL
        self.health_check_interval = max(30, _safe_int(payload.get("health_check_interval")) or DEFAULT_ANT_HEALTH_CHECK_INTERVAL)
        self.tolerance = max(0, _safe_int(payload.get("tolerance")) if payload.get("tolerance") is not None else DEFAULT_ANT_TOLERANCE)

        self._apply_data(
            payload.get("data"),
            source_type=str(payload.get("source_type") or "persisted"),
            source_label=str(payload.get("source_label") or "已恢复"),
            db_path=None,
            db_filename=str(payload.get("db_filename") or ""),
            client_id=str(payload.get("client_id") or ""),
            api_url=str(payload.get("api_url") or ""),
            app_version=str(payload.get("app_version") or DEFAULT_ANT_APP_VERSION),
            selected_node_id=str(payload.get("selected_node_id") or "") or None,
            persist=False,
        )
        self._listen_host = listen_host
        self._listen_port = listen_port

    def _state_payload(self, *, saved_at: datetime) -> dict[str, Any]:
        if self.data is None:
            raise AntProxyError("没有可保存的 Ant 数据")
        return {
            "version": ANT_PROXY_STATE_VERSION,
            "saved_at": saved_at.isoformat(),
            "source_type": self.source_type,
            "source_label": self.source_label,
            "db_filename": self.db_filename,
            "client_id": self.client_id,
            "api_url": self.api_url,
            "app_version": self.app_version,
            "selected_node_id": self.selected_node_id,
            "listen_host": self._listen_host,
            "listen_port": self._listen_port,
            "health_check_url": self.health_check_url,
            "health_check_interval": self.health_check_interval,
            "tolerance": self.tolerance,
            "data": _static_ant_data(self.data),
        }

    async def save_state(self, session: AsyncSession) -> None:
        saved_at = datetime.now(timezone.utc)
        try:
            payload = self._state_payload(saved_at=saved_at)
            envelope = _encrypt_state_payload(payload, saved_at=saved_at)
            encrypted_payload = json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))
            row = await session.scalar(select(AntProxyState).where(AntProxyState.name == ANT_PROXY_STATE_NAME))
            if row is None:
                row = AntProxyState(name=ANT_PROXY_STATE_NAME, encrypted_payload=encrypted_payload)
                session.add(row)
            else:
                row.encrypted_payload = encrypted_payload
            await session.commit()
            self.persisted = True
            self.last_persisted_at = saved_at
            self.last_error = None
        except Exception as exc:
            await session.rollback()
            self.persisted = False
            self.last_error = f"Ant 状态保存到数据库失败：{exc}"
            raise AntProxyError(self.last_error) from exc

    def _apply_data(
        self,
        data: Any,
        *,
        source_type: str,
        source_label: str,
        db_path: Path | None,
        db_filename: str,
        client_id: str | None = None,
        api_url: str = "",
        app_version: str | None = None,
        selected_node_id: str | None = None,
        persist: bool = False,
    ) -> None:
        if not isinstance(data, dict):
            raise AntProxyError("Ant 数据格式不正确")

        nodes = _collect_nodes(data)
        if not nodes:
            raise AntProxyError("没有可用的 Ant 节点")

        previous_selected_id = selected_node_id or self.selected_node_id
        self.data = data
        self.nodes = nodes
        self.db_path = db_path
        self.db_filename = db_filename
        self.source_type = source_type
        self.source_label = source_label or source_type
        self.client_id = client_id or str(_dig(data, "ApiHome", "UserInfo", "MyData", "OauthId") or self.client_id or "")
        self.api_url = api_url or self.api_url
        self.app_version = app_version or self.app_version
        self.aff = _safe_int(_dig(data, "ApiHome", "UserInfo", "MyData", "Aff"))
        self.user_summary = _user_summary(data)
        self.last_loaded_at = datetime.now(timezone.utc)
        self.last_error = None

        selected = None
        if previous_selected_id:
            selected = self.find_node(previous_selected_id, required=False)
        if selected is None:
            selected = self._node_from_use_server()
        self.selected_node_id = selected.id if selected else nodes[0].id
        if persist:
            self.persisted = False

    @property
    def selected_node(self) -> AntNode | None:
        if not self.selected_node_id:
            return self.nodes[0] if self.nodes else None
        return self.find_node(self.selected_node_id, required=False) or (self.nodes[0] if self.nodes else None)

    def find_node(self, node_id: str, *, required: bool = True) -> AntNode | None:
        for node in self.nodes:
            if node.id == node_id:
                return node
        if required:
            raise AntProxyError("节点不存在或缓存已过期，请刷新 Ant 数据库")
        return None

    def select_node(self, node_id: str) -> AntNode:
        self.ensure_loaded()
        node = self.find_node(node_id)
        self.selected_node_id = node.id
        self.last_error = None
        return node

    async def start(
        self,
        *,
        listen_host: str = "127.0.0.1",
        listen_port: int = DEFAULT_ANT_LISTEN_PORT,
        node_id: str | None = None,
        adapter_bind_host: str = "127.0.0.1",
        adapter_connect_host: str = "127.0.0.1",
        health_check_url: str | None = None,
        health_check_interval: int | None = None,
        tolerance: int | None = None,
    ) -> None:
        async with self._lock:
            self.ensure_loaded()
            if node_id:
                self.select_node(node_id)
            if not self.selected_node:
                raise AntProxyError("请先选择一个 Ant 节点")

            listen_host = listen_host.strip() or "127.0.0.1"
            listen_port = int(listen_port)
            if listen_port < 1 or listen_port > 65535:
                raise AntProxyError("监听端口无效")
            self.health_check_url = (health_check_url or self.health_check_url or DEFAULT_TEST_URL).strip() or DEFAULT_TEST_URL
            self.health_check_interval = max(30, int(health_check_interval or self.health_check_interval or DEFAULT_ANT_HEALTH_CHECK_INTERVAL))
            self.tolerance = max(0, int(tolerance if tolerance is not None else self.tolerance))

            node_ids = {node.id for node in self.nodes}
            if (
                self.running
                and self._listen_host == listen_host
                and self._listen_port == listen_port
                and self._adapter_bind_host == adapter_bind_host
                and self._adapter_connect_host == adapter_connect_host
                and set(self._adapter_servers) == node_ids
            ):
                return

            if self.running:
                await self.stop()

            bind_hosts = _adapter_bind_hosts(adapter_bind_host)
            started_servers: dict[str, asyncio.AbstractServer] = {}
            started_extra_servers: list[asyncio.AbstractServer] = []
            started_ports: dict[str, int] = {}
            try:
                for node in self.nodes:
                    handler = lambda reader, writer, node_id=node.id: self._handle_client(reader, writer, node_id)
                    server = await asyncio.start_server(
                        handler,
                        bind_hosts[0],
                        0,
                    )
                    socket_info = server.sockets[0].getsockname() if server.sockets else None
                    if not socket_info:
                        raise AntProxyError("Ant 内部适配器端口分配失败")
                    port = int(socket_info[1])
                    for bind_host in bind_hosts[1:]:
                        try:
                            extra_server = await asyncio.start_server(handler, bind_host, port)
                            started_extra_servers.append(extra_server)
                        except OSError:
                            continue
                    started_servers[node.id] = server
                    started_ports[node.id] = port
            except Exception as exc:
                for server in [*started_servers.values(), *started_extra_servers]:
                    server.close()
                    await server.wait_closed()
                raise AntProxyError(f"启动 Ant 内部适配器失败：{exc}") from exc

            self._adapter_servers = started_servers
            self._adapter_extra_servers = started_extra_servers
            self._adapter_ports = started_ports
            self._adapter_bind_host = adapter_bind_host
            self._adapter_connect_host = adapter_connect_host
            self._listen_host = listen_host
            self._listen_port = listen_port
            self.started_at = datetime.now(timezone.utc)
            self.last_error = None

    async def stop(self) -> None:
        servers = [*self._adapter_servers.values(), *self._adapter_extra_servers]
        self._adapter_servers.clear()
        self._adapter_extra_servers.clear()
        self._adapter_ports.clear()
        for server in servers:
            server.close()
            await server.wait_closed()

        for writer in list(self._writers):
            _close_writer(writer)
        self._writers.clear()
        self.active_connections = 0
        self.started_at = None

    def mihomo_runtime_config(self, *, listen_host: str | None = None) -> dict[str, list[dict[str, Any]]] | None:
        if not self.running:
            return None

        proxies: list[dict[str, Any]] = []
        proxy_names: list[str] = []
        for node in self._runtime_nodes():
            port = self._adapter_ports.get(node.id)
            if not port:
                continue
            name = _mihomo_ant_node_name(node)
            proxies.append(
                {
                    "name": name,
                    "type": "socks5",
                    "server": self._adapter_connect_host,
                    "port": port,
                    "udp": False,
                }
            )
            proxy_names.append(name)

        if not proxies:
            return None

        return {
            "proxies": proxies,
            "proxy-groups": [
                {
                    "name": ANT_MIHOMO_GROUP_NAME,
                    "type": "url-test",
                    "proxies": proxy_names,
                    "url": self.health_check_url or DEFAULT_TEST_URL,
                    "interval": self.health_check_interval,
                    "tolerance": self.tolerance,
                }
            ],
            "listeners": [
                {
                    "name": ANT_MIHOMO_LISTENER_NAME,
                    "type": "socks",
                    "listen": listen_host or self._listen_host,
                    "port": self._listen_port,
                    "proxy": ANT_MIHOMO_GROUP_NAME,
                    "udp": False,
                }
            ],
        }

    def _runtime_nodes(self) -> list[AntNode]:
        selected = self.selected_node
        if selected is None:
            return list(self.nodes)
        return [selected, *[node for node in self.nodes if node.id != selected.id]]

    def mihomo_node_name(self, node: AntNode) -> str:
        return _mihomo_ant_node_name(node)

    def mihomo_proxy_config_for_node(self, node: AntNode) -> dict[str, Any] | None:
        port = self._adapter_ports.get(node.id)
        if not self.running or not port:
            return None
        return {
            "name": self.mihomo_node_name(node),
            "type": "socks5",
            "server": self._adapter_connect_host,
            "port": port,
            "udp": False,
        }

    async def test(self, url: str = DEFAULT_TEST_URL, timeout: float = 15) -> dict[str, Any]:
        self.ensure_loaded()
        parsed = urlsplit(url or DEFAULT_TEST_URL)
        if parsed.scheme != "http" or not parsed.hostname:
            raise AntProxyError("当前内置测试只支持 http URL")

        node = self.selected_node
        if not node:
            raise AntProxyError("请先选择一个 Ant 节点")

        port = parsed.port or 80
        target = SocksTarget(atyp=0x03, host=parsed.hostname, port=port, raw_address=parsed.hostname.encode("utf-8"))
        started = time.perf_counter()

        async def _run() -> dict[str, Any]:
            reader, writer, ws_rest = await self._connect_ant_remote(node)
            crypto = ShadowsocksStream(node.cipher, node.password)
            first = self._encode_first_packet(node, target)
            writer.write(crypto.encrypt_first(first))
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            request = (
                f"GET {path} HTTP/1.1\r\n"
                f"Host: {parsed.hostname}\r\n"
                "User-Agent: Nebula-AntProxy/1.0\r\n"
                "Connection: close\r\n\r\n"
            ).encode("ascii")
            writer.write(crypto.encrypt(request))
            await writer.drain()

            response = b""
            if ws_rest:
                response += crypto.decrypt(ws_rest)
            while b"\r\n\r\n" not in response and len(response) < 65536:
                chunk = await reader.read(8192)
                if not chunk:
                    break
                response += crypto.decrypt(chunk)
            _close_writer(writer)
            first_line = response.split(b"\r\n", 1)[0].decode("latin1", errors="replace") if response else ""
            status_code = 0
            parts = first_line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                status_code = int(parts[1])
            return {"ok": 200 <= status_code < 400, "status_code": status_code, "first_line": first_line}

        try:
            result = await asyncio.wait_for(_run(), timeout=timeout)
        except Exception as exc:
            self.last_error = f"代理测试失败：{exc}"
            raise AntProxyError(self.last_error) from exc

        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
        self.last_error = None if result["ok"] else result.get("first_line") or "代理测试失败"
        return result

    async def refresh_latencies(
        self,
        *,
        line_type: str | None = None,
        timeout_ms: int = 5000,
        concurrency: int = 20,
    ) -> dict[str, Any]:
        self.ensure_loaded()
        line_type = _normalize_line_filter(line_type)
        timeout_ms = max(300, min(int(timeout_ms), 15000))
        concurrency = max(1, min(int(concurrency), 100))
        selected_nodes = [node for node in self.nodes if line_type is None or node.line_type == line_type]
        semaphore = asyncio.Semaphore(concurrency)

        async def measure(node: AntNode) -> int | None:
            async with semaphore:
                latency = await self._measure_node_latency(node, timeout_ms)
                node.latency_ms = latency
                return latency

        started = time.perf_counter()
        results = await asyncio.gather(*(measure(node) for node in selected_nodes))
        self.last_latency_tested_at = datetime.now(timezone.utc)
        online = sum(1 for latency in results if latency is not None)
        return {
            "total": len(selected_nodes),
            "online": online,
            "failed": len(selected_nodes) - online,
            "elapsed_ms": round((time.perf_counter() - started) * 1000),
            "items": [self.public_node(node) for node in selected_nodes],
        }

    async def _measure_node_latency(self, node: AntNode, timeout_ms: int) -> int | None:
        started = time.perf_counter()
        writer: asyncio.StreamWriter | None = None
        try:
            _, writer, _ = await asyncio.wait_for(
                self._connect_ant_remote(node),
                timeout=max(0.3, timeout_ms / 1000),
            )
            return max(1, round((time.perf_counter() - started) * 1000))
        except Exception:
            return None
        finally:
            if writer is not None:
                _close_writer(writer)

    def public_node(self, node: AntNode | None) -> dict[str, Any] | None:
        if node is None:
            return None
        return {
            "id": node.id,
            "source": node.source,
            "group": node.group,
            "name": node.name,
            "city": node.city,
            "country": node.country,
            "country_code": node.country_code,
            "pay_type": node.pay_type,
            "line_type": node.line_type,
            "line_label": node.line_label,
            "online_connections": node.online_connections,
            "status": node.status,
            "latency_ms": node.latency_ms,
            "server": _redact_host(node.server),
            "port": node.port,
            "cipher": node.cipher,
            "transport": node.transport,
            "tls": node.tls,
            "selected": node.id == self.selected_node_id,
        }

    async def _handle_client(
        self,
        local_reader: asyncio.StreamReader,
        local_writer: asyncio.StreamWriter,
        node_id: str | None = None,
    ) -> None:
        self._writers.add(local_writer)
        self.active_connections += 1
        self.total_connections += 1
        remote_writer: asyncio.StreamWriter | None = None
        try:
            node = self.find_node(node_id, required=False) if node_id else self.selected_node
            if not node:
                raise AntProxyError("没有可用 Ant 节点")
            target = await _read_socks5_request(local_reader, local_writer)
            remote_reader, remote_writer, ws_rest = await self._connect_ant_remote(node)
            crypto = ShadowsocksStream(node.cipher, node.password)
            remote_writer.write(crypto.encrypt_first(self._encode_first_packet(node, target)))
            await remote_writer.drain()
            local_writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
            await local_writer.drain()

            tasks = [
                asyncio.create_task(self._pipe_local_to_remote(local_reader, remote_writer, crypto)),
                asyncio.create_task(self._pipe_remote_to_local(remote_reader, local_writer, crypto, ws_rest)),
            ]
            done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in pending:
                task.cancel()
            for task in done:
                task.result()
        except Exception as exc:
            self.last_error = str(exc)
            try:
                local_writer.write(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
                await local_writer.drain()
            except Exception:
                pass
        finally:
            if remote_writer is not None:
                _close_writer(remote_writer)
            _close_writer(local_writer)
            self._writers.discard(local_writer)
            self.active_connections = max(0, self.active_connections - 1)

    async def _pipe_local_to_remote(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        crypto: ShadowsocksStream,
    ) -> None:
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            self.upload_bytes += len(chunk)
            writer.write(crypto.encrypt(chunk))
            await writer.drain()

    async def _pipe_remote_to_local(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        crypto: ShadowsocksStream,
        initial: bytes = b"",
    ) -> None:
        if initial:
            plain = crypto.decrypt(initial)
            if plain:
                self.download_bytes += len(plain)
                writer.write(plain)
                await writer.drain()
        while True:
            chunk = await reader.read(65536)
            if not chunk:
                return
            plain = crypto.decrypt(chunk)
            if not plain:
                continue
            self.download_bytes += len(plain)
            writer.write(plain)
            await writer.drain()

    async def _connect_ant_remote(self, node: AntNode) -> tuple[asyncio.StreamReader, asyncio.StreamWriter, bytes]:
        use_ssl = node.port == 443 if str(node.group) == "16" else node.transport == "wss"
        ssl_context = None
        server_hostname = None
        if use_ssl:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            server_hostname = None if _is_ip(node.server) else node.server

        reader, writer = await asyncio.open_connection(
            node.server,
            node.port,
            ssl=ssl_context,
            server_hostname=server_hostname,
        )

        if str(node.group) == "16":
            return reader, writer, b""

        host_header = await _resolved_host_header(node.server, node.port)
        header = _ws_header(host_header).encode("utf-8")
        writer.write(header)
        await writer.drain()
        rest = await _read_http_upgrade(reader)
        return reader, writer, rest

    def _encode_first_packet(self, node: AntNode, target: SocksTarget) -> bytes:
        port = target.port.to_bytes(2, "big")
        if target.atyp == 0x03:
            address = bytes([target.atyp, len(target.raw_address)]) + target.raw_address + port
        else:
            address = bytes([target.atyp]) + target.raw_address + port
        if str(node.group) == "16" or not self.aff:
            return address
        return int(self.aff).to_bytes(4, "big") + address

    def _node_from_use_server(self) -> AntNode | None:
        use_server = self.data.get("UseServer") if isinstance(self.data, dict) else None
        if not isinstance(use_server, dict):
            return None
        candidate = _normalize_server("UseServer", str(use_server.get("Group") or ""), use_server)
        if not candidate:
            return None
        for node in self.nodes:
            if _node_dedupe_key(node) == _node_dedupe_key(candidate):
                return node
        return None


async def _read_socks5_request(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> SocksTarget:
    greeting = await reader.readexactly(2)
    if greeting[0] != 0x05:
        raise AntProxyError("仅支持 SOCKS5")
    methods = await reader.readexactly(greeting[1])
    if 0x00 not in methods:
        writer.write(b"\x05\xff")
        await writer.drain()
        raise AntProxyError("SOCKS5 认证方式不支持")
    writer.write(b"\x05\x00")
    await writer.drain()

    head = await reader.readexactly(4)
    if head[0] != 0x05 or head[1] != 0x01:
        raise AntProxyError("仅支持 SOCKS5 CONNECT")
    atyp = head[3]
    if atyp == 0x01:
        raw_address = await reader.readexactly(4)
        host = ".".join(str(item) for item in raw_address)
    elif atyp == 0x03:
        length = (await reader.readexactly(1))[0]
        raw_address = await reader.readexactly(length)
        host = raw_address.decode("utf-8", errors="replace")
    elif atyp == 0x04:
        raw_address = await reader.readexactly(16)
        host = str(socket.inet_ntop(socket.AF_INET6, raw_address))
    else:
        raise AntProxyError("不支持的 SOCKS5 地址类型")
    port = int.from_bytes(await reader.readexactly(2), "big")
    return SocksTarget(atyp=atyp, host=host, port=port, raw_address=raw_address)


async def _read_http_upgrade(reader: asyncio.StreamReader) -> bytes:
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 16384:
        chunk = await reader.read(4096)
        if not chunk:
            break
        data += chunk
    head, _, rest = data.partition(b"\r\n\r\n")
    first_line = head.split(b"\r\n", 1)[0].decode("latin1", errors="replace")
    if not first_line.startswith("HTTP/1.1 101"):
        raise AntProxyError(f"Ant 远端握手失败：{first_line or 'empty response'}")
    return rest


async def _resolved_host_header(host: str, port: int) -> str:
    try:
        infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        address = infos[0][4][0] if infos else host
    except Exception:
        address = host
    if ":" in address and not address.startswith("["):
        address = f"[{address}]"
    return f"{address}:{port}"


def _ws_header(host: str) -> str:
    key = base64.b64encode(os.urandom(16)).decode("ascii")
    return "\r\n".join(
        [
            "GET / HTTP/1.1",
            f"Host: {host}",
            "Connection: Upgrade",
            "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36",
            "Upgrade: websocket",
            "Sec-WebSocket-Version: 13",
            f"Sec-WebSocket-Key: {key}",
            "",
            "",
        ]
    )


def _collect_nodes(data: dict[str, Any]) -> list[AntNode]:
    nodes: list[AntNode] = []

    server_list = data.get("ServerList")
    if isinstance(server_list, dict):
        for group, items in server_list.items():
            if not isinstance(items, list):
                continue
            for item in items:
                node = _normalize_server("ServerList", str(group), item)
                if node:
                    nodes.append(node)

    api_servers = _dig(data, "ApiHome", "Servers")
    if isinstance(api_servers, list):
        for item in api_servers:
            group = str(item.get("PayType") or "") if isinstance(item, dict) else ""
            node = _normalize_server("ApiHome.Servers", group, item)
            if node:
                nodes.append(node)

    use_server = data.get("UseServer")
    node = _normalize_server("UseServer", str(use_server.get("Group") or "") if isinstance(use_server, dict) else "", use_server)
    if node:
        nodes.append(node)

    seen: dict[str, AntNode] = {}
    deduped: list[AntNode] = []
    for node in nodes:
        key = _node_dedupe_key(node)
        existing = seen.get(key)
        if existing is not None:
            _merge_node_metadata(existing, node)
            continue
        seen[key] = node
        deduped.append(node)
    return deduped


def _normalize_server(source: str, group: str, server: Any) -> AntNode | None:
    if not isinstance(server, dict):
        return None
    host = str(server.get("Address") or server.get("IP") or "").strip()
    port = _safe_int(server.get("Port"))
    password = str(server.get("Password") or "")
    cipher = str(server.get("Method") or "")
    if not host or not port or not password or not cipher:
        return None
    transport = str(server.get("Protocol") or "").lower()
    name = str(server.get("Description") or "-".join(str(item) for item in (server.get("Country") or server.get("City"), host, port) if item))
    pay_type = str(server.get("PayType") or "")
    line_type, line_label = _line_type_and_label(group, pay_type)
    node_id = hashlib.sha256(
        f"{line_type}\0{group}\0{host}\0{port}\0{password}\0{cipher}\0{transport}\0{name}".encode("utf-8")
    ).hexdigest()[:16]
    return AntNode(
        id=node_id,
        source=source,
        group=group,
        name=name,
        city=str(server.get("City") or ""),
        country=str(server.get("Country") or ""),
        country_code=str(server.get("CountryCode") or ""),
        pay_type=pay_type,
        line_type=line_type,
        line_label=line_label,
        online_connections=_optional_int(server.get("Connections")),
        status=_optional_int(server.get("Status")),
        latency_ms=None,
        server=host,
        port=port,
        password=password,
        cipher=cipher,
        transport=transport,
        tls=transport == "wss",
        raw=server,
    )


def _merge_node_metadata(target: AntNode, source: AntNode) -> None:
    if target.online_connections is None and source.online_connections is not None:
        target.online_connections = source.online_connections
    if target.status is None and source.status is not None:
        target.status = source.status
    if not target.pay_type and source.pay_type:
        target.pay_type = source.pay_type
    if target.line_type == "free" and source.line_type == "paid":
        target.line_type = source.line_type
        target.line_label = source.line_label
    if not target.country and source.country:
        target.country = source.country
    if not target.country_code and source.country_code:
        target.country_code = source.country_code


def _line_type_and_label(group: str, pay_type: str) -> tuple[str, str]:
    group_value = str(group or "").strip().lower()
    pay_value = str(pay_type or "").strip().lower()
    if group_value in {"1", "freegroup"}:
        return "free", "免费专线"
    if group_value in {"2", "paidgroup"}:
        return "paid", "付费专线"
    if pay_value == "charge":
        return "paid", "付费专线"
    return "free", "免费专线"


def _account_refresh_groups(line_type: str | None = None) -> list[tuple[str, str, str]]:
    groups = [
        ("1", "FreeGroup", "free"),
        ("2", "PaidGroup", "paid"),
    ]
    if line_type is None:
        return groups
    return [item for item in groups if item[2] == line_type]


def _adapter_bind_hosts(value: str) -> list[str]:
    hosts = [item.strip() for item in str(value or "").split(",") if item.strip()]
    return hosts or ["127.0.0.1"]


def _mihomo_ant_node_name(node: AntNode) -> str:
    return f"ant-{node.id} [{node.line_label}] {node.name}".strip()


def _server_connections_sort_key(server: dict[str, Any]) -> int:
    return _optional_int(server.get("Connections")) or 0


def _node_dedupe_key(node: AntNode) -> str:
    return "\0".join([node.line_type, node.server, str(node.port), node.password, node.cipher, node.transport])


def _user_summary(data: dict[str, Any]) -> dict[str, Any]:
    user = _dig(data, "ApiHome", "UserInfo")
    my_data = _dig(data, "ApiHome", "UserInfo", "MyData")
    if not isinstance(user, dict) or not isinstance(my_data, dict):
        return {"logged_in": False}
    oauth_id = str(my_data.get("OauthId") or "")
    uuid = str(my_data.get("Uuid") or "")
    bind_phone = str(my_data.get("BindPhone") or "")
    username = str(my_data.get("Username") or "")
    return {
        "logged_in": bool(oauth_id or uuid or bind_phone),
        "oauth_id": _mask_middle(oauth_id, keep_start=4, keep_end=4),
        "uuid": _mask_middle(uuid, keep_start=6, keep_end=6),
        "bind_phone": _mask_phone(bind_phone),
        "username": _mask_account(username),
        "aff_present": bool(my_data.get("Aff")),
        "vip_day": _safe_int(my_data.get("VipDay")),
        "expire_description": str(my_data.get("ExpireDescription") or ""),
        "is_sign": _safe_int(user.get("IsSign")),
        "website_url": str(user.get("WebsiteUrl") or ""),
        "ip": _mask_middle(str(user.get("IP") or ""), keep_start=4, keep_end=3),
    }


def _dig(data: Any, *keys: str) -> Any:
    current = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


async def _ant_api_post(
    values: dict[str, Any],
    *,
    client_id: str,
    app_version: str,
    api_urls: list[str],
) -> tuple[dict[str, Any], str]:
    payload = {
        "oauth_id": client_id,
        "oauth_type": ANT_API_OAUTH_TYPE,
        "version": app_version,
        "app_type": ANT_API_APP_TYPE,
        **{key: str(value) for key, value in values.items() if value is not None},
    }
    raw_data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    encrypted_data = _ant_api_encrypt(raw_data)
    timestamp = str(int(time.time() * 1000))
    form = {
        "appId": ANT_API_APP_ID,
        "appVersion": app_version,
        "timestamp": timestamp,
        "data": encrypted_data,
        "sign": _ant_api_sign(timestamp, encrypted_data, app_version),
    }
    timeout = aiohttp.ClientTimeout(total=15)
    last_error = ""
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for api_url in _normalize_api_urls(api_urls):
            try:
                async with session.post(api_url, data=form) as response:
                    text = await response.text()
                    if response.status != 200:
                        last_error = f"{_redact_url(api_url)} HTTP {response.status}"
                        continue
                    outer = json.loads(text)
                    encrypted_response = outer.get("data") if isinstance(outer, dict) else None
                    if not encrypted_response:
                        last_error = f"{_redact_url(api_url)} 返回格式不正确"
                        continue
                    decrypted = _ant_api_decrypt(str(encrypted_response))
                    result = json.loads(decrypted)
                    if not isinstance(result, dict):
                        last_error = f"{_redact_url(api_url)} 返回数据格式不正确"
                        continue
                    return result, api_url
            except Exception as exc:
                last_error = f"{_redact_url(api_url)} {exc}"
    raise AntProxyError(last_error or "Ant API 请求失败")


def _ant_api_encrypt(value: str) -> str:
    key, iv = _ant_api_key_iv()
    cipher = Cipher(algorithms.AES(key), CFB_MODE(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(value.encode("utf-8")) + encryptor.finalize()
    return (iv + encrypted).hex().upper()


def _ant_api_decrypt(value: str) -> str:
    raw = bytes.fromhex(value)
    if len(raw) <= 16:
        raise AntProxyError("Ant API 响应解密失败")
    key, _ = _ant_api_key_iv()
    iv = raw[:16]
    cipher = Cipher(algorithms.AES(key), CFB_MODE(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(raw[16:]) + decryptor.finalize()
    return decrypted.decode("utf-8")


def _ant_api_key_iv() -> tuple[bytes, bytes]:
    material = _evp_bytes_to_key(ANT_API_PASSWORD.encode("utf-8"), 48)
    return material[:32], material[32:48]


def _ant_api_sign(timestamp: str, encrypted_data: str, app_version: str) -> str:
    value = (
        f"appId={ANT_API_APP_ID}&appVersion={app_version}&data={encrypted_data}"
        f"&timestamp={timestamp}{ANT_API_SIGN_SECRET}"
    )
    sha = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return hashlib.md5(sha.encode("utf-8")).hexdigest()


def _normalize_api_home(response: dict[str, Any], *, client_id: str) -> dict[str, Any]:
    home_data = response.get("data")
    if not isinstance(home_data, dict):
        raise AntProxyError(_ant_response_message(response) or "Ant 首页数据格式不正确")

    servers = [_normalize_api_server(item) for item in _ensure_list(home_data.get("servers"))]
    servers = [item for item in servers if item is not None]
    cf_line = _normalize_api_server(home_data.get("cfLine"))
    user_info = _normalize_api_user_info(home_data, client_id=client_id)
    request_datas = [
        {
            "Area": str(item.get("area") or item.get("Area") or ""),
            "Url": str(item.get("url") or item.get("Url") or ""),
        }
        for item in _ensure_list(home_data.get("line"))
        if isinstance(item, dict)
    ]
    version = home_data.get("apk_version") if isinstance(home_data.get("apk_version"), dict) else {}
    traffic = home_data.get("transfer") if isinstance(home_data.get("transfer"), dict) else {}

    data: dict[str, Any] = {
        "ServerList": {},
        "ApiHome": {
            "Cfline": cf_line or {},
            "Servers": servers,
            "Version": {
                "Version": str(version.get("version") or ""),
                "DownloadUrl": str(version.get("download_url") or ""),
                "MustUpdate": str(version.get("must_update") or ""),
                "Type": str(version.get("type") or ""),
                "Tips": str(version.get("tips") or ""),
                "Message": str(version.get("message") or ""),
            },
            "Traffic": traffic,
            "UserInfo": user_info,
            "HomeUrl": str(home_data.get("home_url") or ""),
            "RequestDatas": request_datas,
            "AdApp": home_data.get("getApp") or {},
            "IsShowAdApp": bool(home_data.get("showApp")),
            "IsShowBuy": bool(home_data.get("open_vip", True)),
            "NeedCaptcha": str(home_data.get("msg_need_captcha") or ""),
            "AdUrl": str(home_data.get("auto_open_url") or ""),
            "IsSupportUDP": bool(home_data.get("udp_support")),
            "MessageDatas": [],
        },
    }
    if servers:
        data["UseServer"] = servers[0]
    return data


def _normalize_api_server(server: Any) -> dict[str, Any] | None:
    if not isinstance(server, dict):
        return None
    host = str(_pick(server, "ip", "IP", "Address") or "").strip()
    port = _safe_int(_pick(server, "port", "Port"))
    password = str(_pick(server, "passwd", "password", "Password") or "")
    method = str(_pick(server, "method", "Method") or "")
    if not host or not port or not password or not method:
        return None
    return {
        "Address": host,
        "IP": host,
        "Port": str(port),
        "Password": password,
        "Method": method,
        "Protocol": str(_pick(server, "protocol", "Protocol") or "").lower(),
        "Description": str(_pick(server, "descp", "description", "Description") or ""),
        "City": str(_pick(server, "city", "City") or ""),
        "Country": str(_pick(server, "country", "Country") or ""),
        "CountryCode": str(_pick(server, "country_code", "CountryCode") or "").upper(),
        "PayType": str(_pick(server, "payType", "pay_type", "PayType") or ""),
        "Connections": _optional_int(_pick(server, "connections", "Connections")),
        "Status": _optional_int(_pick(server, "status", "Status")),
    }


def _normalize_api_user_info(home_data: dict[str, Any], *, client_id: str) -> dict[str, Any]:
    home = home_data.get("home") if isinstance(home_data.get("home"), dict) else {}
    user = home.get("data") if isinstance(home.get("data"), dict) else {}
    return {
        "MyData": {
            "OauthId": str(user.get("oauth_id") or client_id),
            "Uuid": str(user.get("uuid") or ""),
            "BindPhone": str(user.get("bind_phone") or user.get("mobile") or ""),
            "Username": str(user.get("username") or ""),
            "Aff": _safe_int(user.get("aff")),
            "AffCode": str(user.get("aff_code") or ""),
            "InvitedBy": str(user.get("invited_by") or ""),
            "InvitedNum": _safe_int(user.get("invited_num")),
            "GroupUrl": str(user.get("group_url") or ""),
            "SubAff": str(user.get("sub_aff") or ""),
            "VipDay": _safe_int(user.get("vip_day")),
            "ExpireDescription": str(user.get("expire_description") or user.get("expire_desc") or ""),
        },
        "SiteUrl": str(home.get("web_url") or ""),
        "AffUrl": str(home.get("aff_url") or ""),
        "QuitMessage": str(home.get("quit_msg") or ""),
        "UploadImgUrl": str(home.get("upload_img_ticket") or ""),
        "WebsiteUrl": str(home.get("web_url") or ""),
        "EmailUrl": str(home.get("email") or ""),
        "QuestionUrl": str(home.get("question_url") or ""),
        "IsSign": _safe_int(home.get("is_sign")),
        "SignGetTraffic": _safe_int(home.get("sign_transfer_desc")),
        "AffGetTraffic": _safe_int(home.get("aff_transfer")),
        "SignDescription": str(home.get("sign_transfer_desc") or ""),
        "SignedDescription": str(home.get("sign_after_desc") or ""),
        "ShareDescription": str(home.get("aff_transfer_desc") or ""),
        "ShareQRcodeImg": str(home.get("aff_transfer_img") or ""),
        "BindMobileTip": str(home.get("bind_mobile_desc") or ""),
        "IsShowBindMobileTip": _safe_int(home.get("notice_bind_phone")),
        "IP": str(home.get("user_ip") or ""),
    }


def _ant_login_success(response: dict[str, Any]) -> bool:
    candidates = [response, response.get("data"), response.get("myData"), response.get("MyData")]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        code = item.get("code", item.get("Code", item.get("status", item.get("Status"))))
        if str(code) in {"1", "200", "True", "true"}:
            return True
    return False


def _ant_response_message(response: dict[str, Any]) -> str:
    candidates = [response, response.get("data"), response.get("myData"), response.get("MyData")]
    for item in candidates:
        if isinstance(item, dict):
            message = item.get("message") or item.get("Message") or item.get("msg") or item.get("Msg")
            if message:
                return str(message)
    return ""


def _api_urls_from_data(data: dict[str, Any] | None) -> list[str]:
    if not isinstance(data, dict):
        return []
    urls: list[str] = []
    for item in _ensure_list(_dig(data, "ApiHome", "RequestDatas")):
        if not isinstance(item, dict):
            continue
        url = str(item.get("Url") or item.get("url") or "").strip()
        if url:
            urls.append(_api_url(url))
    return urls


def _normalize_api_urls(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values or ANT_API_URLS:
        url = _api_url(value)
        if not url:
            continue
        if url in seen:
            continue
        seen.add(url)
        result.append(url)
    for url in ANT_API_URLS:
        if url not in seen:
            result.append(url)
    return result


def _prioritized_urls(first: str, values: list[str]) -> list[str]:
    return [first, *[item for item in values if item != first]]


def _api_url(value: str) -> str:
    url = value.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    if not url.endswith("/api.php"):
        url = f"{url.rstrip('/')}/api.php"
    return url


def _pick(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _ensure_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _generate_client_id() -> str:
    return base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")


def _safe_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_line_filter(value: str | None) -> str | None:
    if value is None or not str(value).strip():
        return None
    line_type = str(value).strip().lower()
    aliases = {
        "1": "free",
        "freegroup": "free",
        "vip": "free",
        "免费": "free",
        "免费专线": "free",
        "2": "paid",
        "paidgroup": "paid",
        "charge": "paid",
        "付费": "paid",
        "付费专线": "paid",
    }
    line_type = aliases.get(line_type, line_type)
    if line_type not in {"free", "paid"}:
        raise AntProxyError("线路类型只支持 free 或 paid")
    return line_type


def _evp_bytes_to_key(password: bytes, key_length: int) -> bytes:
    chunks: list[bytes] = []
    previous = b""
    while sum(len(item) for item in chunks) < key_length:
        previous = hashlib.md5(previous + password).digest()
        chunks.append(previous)
    return b"".join(chunks)[:key_length]


def _is_ip(value: str) -> bool:
    try:
        socket.inet_pton(socket.AF_INET, value)
        return True
    except OSError:
        pass
    try:
        socket.inet_pton(socket.AF_INET6, value)
        return True
    except OSError:
        return False


def _close_writer(writer: asyncio.StreamWriter) -> None:
    try:
        writer.close()
    except Exception:
        pass


def _redact_host(value: str) -> str:
    if len(value) <= 8:
        return value
    return f"{value[:3]}...{value[-3:]}"


def _redact_url(value: str) -> str:
    if not value:
        return ""
    try:
        parsed = urlsplit(value)
    except Exception:
        return _redact_host(value)
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    return _redact_host(host)


def _mask_middle(value: str, *, keep_start: int, keep_end: int) -> str:
    if not value:
        return ""
    if len(value) <= keep_start + keep_end:
        return value
    return f"{value[:keep_start]}***{value[-keep_end:]}"


def _mask_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) < 7:
        return _mask_middle(value, keep_start=2, keep_end=2)
    return f"{digits[:3]}****{digits[-4:]}"


def _mask_account(value: str) -> str:
    if not value:
        return ""
    if "@" in value:
        name, domain = value.split("@", 1)
        return f"{_mask_middle(name, keep_start=2, keep_end=1)}@{domain}"
    if value.isdigit() and len(value) >= 7:
        return _mask_phone(value)
    return _mask_middle(value, keep_start=3, keep_end=2)


def _resolve_backend_path(value: str) -> Path:
    path = Path(value or "./data/ant-proxy-state.json").expanduser()
    if path.is_absolute():
        return path
    return (BACKEND_DIR / path).resolve()


def _static_ant_data(value: Any) -> Any:
    if isinstance(value, dict):
        result: dict[Any, Any] = {}
        for key, item in value.items():
            if _is_dynamic_ant_key(key):
                continue
            result[key] = _static_ant_data(item)
        return result
    if isinstance(value, list):
        return [_static_ant_data(item) for item in value]
    return value


def _is_dynamic_ant_key(key: Any) -> bool:
    normalized = re.sub(r"[^a-z0-9]", "", str(key).lower())
    return normalized in ANT_PROXY_DYNAMIC_DATA_KEYS


def _state_keys() -> tuple[bytes, bytes]:
    secret = get_settings().SECRET_KEY.encode("utf-8")
    encryption_key = hashlib.sha256(b"nebula-ant-state:v1:enc:" + secret).digest()
    mac_key = hashlib.sha256(b"nebula-ant-state:v1:mac:" + secret).digest()
    return encryption_key, mac_key


def _encrypt_state_payload(payload: dict[str, Any], *, saved_at: datetime) -> dict[str, Any]:
    encryption_key, mac_key = _state_keys()
    iv = os.urandom(16)
    plaintext = msgpack.packb(payload, use_bin_type=True)
    cipher = Cipher(algorithms.AES(encryption_key), CFB_MODE(iv))
    encryptor = cipher.encryptor()
    ciphertext = encryptor.update(plaintext) + encryptor.finalize()
    signature = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).hexdigest()
    return {
        "version": ANT_PROXY_STATE_VERSION,
        "algorithm": ANT_PROXY_STATE_ALGORITHM,
        "saved_at": saved_at.isoformat(),
        "iv": base64.b64encode(iv).decode("ascii"),
        "payload": base64.b64encode(ciphertext).decode("ascii"),
        "mac": signature,
    }


def _decrypt_state_payload(envelope: Any) -> dict[str, Any]:
    if not isinstance(envelope, dict):
        raise AntProxyError("持久化状态格式不正确")
    if _safe_int(envelope.get("version")) != ANT_PROXY_STATE_VERSION:
        raise AntProxyError("持久化状态版本不兼容")
    if str(envelope.get("algorithm") or "") != ANT_PROXY_STATE_ALGORITHM:
        raise AntProxyError("持久化状态加密算法不兼容")

    try:
        iv = base64.b64decode(str(envelope.get("iv") or ""), validate=True)
        ciphertext = base64.b64decode(str(envelope.get("payload") or ""), validate=True)
    except Exception as exc:
        raise AntProxyError("持久化状态编码不正确") from exc
    if len(iv) != 16 or not ciphertext:
        raise AntProxyError("持久化状态密文不完整")

    encryption_key, mac_key = _state_keys()
    signature = hmac.new(mac_key, iv + ciphertext, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, str(envelope.get("mac") or "")):
        raise AntProxyError("持久化状态校验失败，请确认 SECRET_KEY 未变化")

    cipher = Cipher(algorithms.AES(encryption_key), CFB_MODE(iv))
    decryptor = cipher.decryptor()
    plaintext = decryptor.update(ciphertext) + decryptor.finalize()
    data = msgpack.unpackb(plaintext, raw=False, strict_map_key=False)
    if not isinstance(data, dict):
        raise AntProxyError("持久化状态内容不正确")
    return data


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


ant_proxy_service = AntProxyService()
