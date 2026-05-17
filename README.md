# Nebula Subscriptions

Nebula Subscriptions 是一个现代化代理订阅聚合与运行编排平台。它负责订阅源管理、节点池归一化、客户端配置生成、流量快照、智能代理入口和 Web 管理后台；复杂协议解析与格式转换交给 `subconverter`，真实 HTTP/SOCKS/Mixed 代理入口由 `Mihomo` runtime 提供。

当前版本：`v1.0.0`

## 功能概览

- 订阅管理：支持新增、编辑、删除、启用/停用订阅源，维护分组、标签、优先级、备注和更新间隔。
- URL 安全校验：订阅 URL 仅允许 `http`/`https`，默认阻止私网、回环、保留地址和组播地址，可配置域名白名单。
- 统一节点池：每个启用订阅先经 `subconverter` 转为 Clash YAML，再解析 `proxies` 入库，保留来源订阅、分组、协议、国家/地区、标签和原始节点字段。
- 安全同步：节点池同步会先暂存新节点，只有目标范围全部成功后才替换旧节点；如果部分订阅失败，会保留原节点池并记录错误。
- 节点过滤与去重：按 `server + port + uuid/password/cipher/psk` 去重，支持 `node_filter_patterns` 通配符过滤伪节点。
- 客户端输出：`/api/sub/clash` 和 `/api/sub/mihomo` 从节点池动态生成配置；`/api/sub/v2ray` 从节点池生成 v2rayN 分享链接订阅；`/api/sub/singbox` 由 `subconverter` 聚合转换。
- 代理组生成：Clash/Mihomo 输出内置节点选择、自动选择、故障转移、负载均衡、香港/日本/美国、流媒体、ChatGPT、漏网之鱼等策略组。
- 订阅流量：解析订阅源 `subscription-userinfo` 响应头，保存流量快照，展示已用、总量、剩余、到期时间和异常原因。
- 配置模板：支持按目标客户端维护模板，Clash/Mihomo 生成器会读取模板 YAML 中的 `mixed-port`、`dns`、`rule-providers`、`rules` 等配置。
- 规则模板：内置 ACL4SSR Online，可维护远程配置 URL 或自定义 YAML。
- 智能代理：基于 Mihomo `listeners` 生成 HTTP、SOCKS5、Mixed 代理入口，支持端口自动分配、账号密码、访问 Token、IP 白名单、运行状态、健康检测和切换日志。
- 智能调度：代理候选节点可按全部节点、订阅来源、国家/地区、标签或手动节点筛选，并支持 `select`、`stable`、`fallback`、`url-test`、`load-balance`、`relay`、`round-robin` 策略。
- 流量保护：智能代理生成 runtime 时可排除已过期/耗尽订阅节点，对低剩余流量或临近到期节点降权排序。
- 实时状态：WebSocket 推送 Dashboard 和智能代理状态，页面可实时看到 Mihomo 可用性、连接数、速率、当前节点和异常信息。
- 审计日志：登录、订阅、节点池、节点、智能代理、配置、规则和模板操作会写入日志中心。
- 鉴权与限流：后台使用 JWT access/refresh token；公开订阅接口使用独立 `subscription_token`；后端带按 IP+路径分桶的请求限流。

## 技术栈

| 层级 | 实现 |
| --- | --- |
| 前端 | Vue 3、Vue Router、Pinia、Element Plus、Vite |
| 后端 | FastAPI、SQLAlchemy Async、Pydantic、APScheduler |
| 存储 | SQLite 默认，支持 PostgreSQL 连接串；Redis 用于订阅转换缓存 |
| 转换 | subconverter |
| 代理核心 | Mihomo |
| 部署 | Docker Compose，包含 `backend`、`frontend`、`redis`、`subconverter`、`mihomo` |

## 项目结构

```text
.
├── backend/
│   ├── app/
│   │   ├── api/routes/        # FastAPI 路由
│   │   ├── core/              # 配置、数据库、缓存、鉴权、限流
│   │   ├── models/            # SQLAlchemy 模型
│   │   ├── schemas/           # Pydantic schema
│   │   ├── services/          # 订阅转换、节点池、配置生成、智能代理等业务逻辑
│   │   └── tasks/             # APScheduler 后台任务
│   ├── alembic/               # 数据库迁移骨架
│   └── data/                  # SQLite、Mihomo runtime、GeoIP 等运行数据
├── frontend/
│   ├── src/views/             # 管理后台页面
│   ├── src/layouts/           # 应用布局
│   └── src/composables/       # 主题和状态 WebSocket
├── docker-compose.yml
├── .env.example
├── README.md
└── 使用说明文档.md
```

## 快速启动

```bash
cp .env.example .env
docker compose up -d --build
```

默认访问地址：

| 服务 | 地址 |
| --- | --- |
| Web 管理后台 | `http://localhost:8088` |
| 后端 API 文档 | `http://localhost:8000/docs` |
| 后端健康检查 | `http://localhost:8000/health` |
| subconverter | `http://localhost:25500` |
| Mihomo API | `http://localhost:9090/version` |

开发/本地测试默认管理员：

```text
用户名：admin
密码：admin123456
```

生产环境至少修改：

```env
SECRET_KEY=your-random-secret-at-least-32-chars
ADMIN_PASSWORD=your-strong-password
SUBSCRIPTION_TOKEN=your-random-subscription-token
```

`APP_ENV=production` 时后端会拒绝默认弱密钥启动；首次部署需要在 `.env` 中设置强密码和随机 Token，仅可信本地测试可临时设置 `ALLOW_INSECURE_DEFAULTS=true`。

Docker Compose 默认使用 `TZ=Asia/Shanghai`，后端业务时间、调度器和容器系统时区均按中国时区运行。

Docker Compose 默认只把前端、后端、Redis、subconverter、Mihomo API 和智能代理端口绑定到 `127.0.0.1`。如果需要局域网访问管理后台或代理端口，请显式设置 `FRONTEND_BIND_HOST=0.0.0.0` 或 `SMART_PROXY_BIND_HOST=0.0.0.0`，并配置强密码、Token 和防火墙。

智能代理端口默认映射 `37890-37900`，由 `SMART_PROXY_PORT_START` 和 `SMART_PROXY_PORT_END` 控制。

## 公开订阅接口

```text
GET /api/sub/mihomo?token=nebula-sub-token&group=default&emoji=true
GET /api/sub/clash?token=nebula-sub-token&group=default&emoji=true
GET /api/sub/singbox?token=nebula-sub-token&group=default&emoji=true
GET /api/sub/v2ray?token=nebula-sub-token&group=default&emoji=true
```

参数：

| 参数 | 必填 | 说明 |
| --- | --- | --- |
| `token` | 是 | 公开订阅 Token，对应系统设置 `subscription_token` 或环境变量 `SUBSCRIPTION_TOKEN` |
| `group` | 否 | 仅输出指定订阅分组 |
| `template` | 否 | 指定配置模板名称 |
| `emoji` | 否 | 是否启用 Emoji，默认 `true` |

输出逻辑：

- `mihomo`/`clash`：读取已启用节点池，动态生成 YAML 配置；节点池为空时会自动同步一次。
- `v2ray`：读取节点池并生成 `vmess://`、`vless://`、`trojan://`、`ss://`、`hysteria2://` 分享链接后做 Base64 编码。
- `singbox`：直接把启用订阅 URL 聚合后交给 `subconverter` 转换。

## 后台 API

后台接口均以 `/api` 为前缀，除公开订阅接口外需要 JWT 登录。

| 模块 | 主要接口 |
| --- | --- |
| 认证 | `POST /api/auth/login`、`POST /api/auth/refresh`、`GET /api/auth/me` |
| Dashboard | `GET /api/dashboard`、`POST /api/dashboard/traffic/refresh` |
| 订阅 | `GET/POST /api/subscriptions`、`PUT/DELETE /api/subscriptions/{id}`、`POST /api/subscriptions/{id}/refresh`、`POST /api/subscriptions/traffic/refresh` |
| 节点 | `GET /api/nodes`、`POST /api/nodes/refresh`、`POST /api/nodes/test-latency`、`PUT /api/nodes/{id}` |
| 智能代理 | `GET/POST /api/smart-proxies`、`PUT/DELETE /api/smart-proxies/{id}`、`POST /api/smart-proxies/{id}/start`、`POST /api/smart-proxies/{id}/stop` |
| Mihomo runtime | `POST /api/smart-proxies/reload`、`GET /api/smart-proxies/runtime`、`GET /api/smart-proxies/core/status` |
| 智能代理配置 | `GET/PUT /api/smart-proxies/config/global`、`GET/PUT /api/smart-proxies/{id}/config` |
| 智能代理检测 | `POST /api/smart-proxies/access/enforce`、`GET /api/smart-proxies/{id}/status`、`POST /api/smart-proxies/{id}/health-check`、`GET /api/smart-proxies/{id}/health-logs`、`GET /api/smart-proxies/{id}/switch-logs` |
| 规则与模板 | `GET/POST/PUT/DELETE /api/rules`、`GET/POST/PUT/DELETE /api/templates` |
| 设置与日志 | `GET/PUT /api/settings`、`GET /api/settings/health`、`GET /api/logs`、`GET /api/logs/types` |
| 实时状态 | `WS /api/ws/status?token=<access_token>&topics=dashboard,smart_proxies&interval_ms=10000` |

## 智能代理说明

智能代理不在 Nebula 内实现 HTTP/SOCKS 协议栈。Nebula 会根据节点池和代理配置生成 Mihomo runtime YAML，并写入：

```text
backend/data/mihomo-runtime.yaml
```

Docker Compose 中该目录会同时挂载给 Mihomo：

```text
宿主机 ./backend/data
Mihomo 容器 /root/.config/mihomo
```

因此 Docker 部署的典型路径是：

```env
MIHOMO_RUNTIME_CONFIG_PATH=/app/data/mihomo-runtime.yaml
MIHOMO_CORE_CONFIG_PATH=/root/.config/mihomo/mihomo-runtime.yaml
MIHOMO_API_URL=http://mihomo:9090
```

宿主机本地开发的典型路径是：

```env
MIHOMO_RUNTIME_CONFIG_PATH=./data/mihomo-runtime.yaml
MIHOMO_CORE_CONFIG_PATH=/root/.config/mihomo/mihomo-runtime.yaml
MIHOMO_API_URL=http://127.0.0.1:9090
```

支持的代理类型：

| 类型 | Mihomo listener |
| --- | --- |
| HTTP / HTTPS CONNECT | `http` |
| SOCKS5 | `socks` |
| Mixed | `mixed` |

支持的策略：

| 策略 | Mihomo group 行为 |
| --- | --- |
| `select` | 手动选择 |
| `stable` | 稳定优先，底层使用 `fallback`，当前节点变化后会优先保留当前可用节点 |
| `fallback` | 故障转移 |
| `url-test` | 自动测速选择 |
| `load-balance` | 一致性哈希负载均衡 |
| `relay` | 链式代理，至少需要 2 个候选/策略节点 |
| `round-robin` | 轮询，底层使用 `load-balance` 的 `round-robin` 策略 |

## 系统设置

启动时会初始化管理员、默认 ACL4SSR 规则、默认 Mihomo 模板和系统设置。设置项按页面拆分：

| 页面/范围 | 设置项 |
| --- | --- |
| 系统设置 | `redis_url`、`subconverter_url`、`acl4ssr_config_url` |
| 订阅管理 > 订阅配置 | `subscription_token`、`cache_ttl_seconds`、`traffic_poll_interval_minutes` |
| 节点管理 > 节点池配置 | `node_filter_patterns`、`node_pool_sync_interval_minutes` |
| 智能代理 > 全局配置 | 智能代理定时任务、`mihomo_*`、流量保护相关设置；端口范围由部署环境变量控制 |

`APP_ENV=development` 时，应用启动会用 `backend/.env.development` 同步 `redis_url`、`subconverter_url`、`mihomo_api_url`、`mihomo_runtime_config_path`、`mihomo_core_config_path`，避免 SQLite 中残留 Docker 服务名导致宿主机开发无法连接。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `APP_ENV` | `development` | 运行环境；Docker Compose 默认传入 `production` |
| `ALLOW_INSECURE_DEFAULTS` | `false` | 生产环境是否允许默认弱密钥；只建议本地测试临时开启 |
| `TZ` | `Asia/Shanghai` | 容器系统时区；后端业务时间统一使用中国时区 |
| `SECRET_KEY` | `change-me-in-production` | JWT 签名密钥 |
| `ADMIN_USERNAME` | `admin` | 首次初始化管理员用户名 |
| `ADMIN_PASSWORD` | `admin123456` | 首次初始化管理员密码 |
| `SUBSCRIPTION_TOKEN` | `nebula-sub-token` | 公开订阅接口 Token |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/nebula.db` | 数据库连接串 |
| `SQL_ECHO` | `false` | 是否输出 SQL 调试日志 |
| `REDIS_URL` | Docker: `redis://redis:6379/0` | Redis 连接串 |
| `CACHE_TTL_SECONDS` | `600` | subconverter 最终输出缓存时间 |
| `SUBCONVERTER_URL` | Docker: `http://subconverter:25500` | subconverter HTTP API 地址 |
| `SUBCONVERTER_TIMEOUT_SECONDS` | `45` | subconverter 请求超时时间 |
| `ACL4SSR_CONFIG_URL` | ACL4SSR Online | 默认规则/转换配置 URL |
| `MIHOMO_API_URL` | Docker: `http://mihomo:9090` | Mihomo external-controller 地址 |
| `MIHOMO_API_SECRET` | 空 | Mihomo API Bearer Token |
| `MIHOMO_RUNTIME_CONFIG_PATH` | Docker: `/app/data/mihomo-runtime.yaml` | Nebula 写入 runtime YAML 的路径 |
| `MIHOMO_CORE_CONFIG_PATH` | Docker: `/root/.config/mihomo/mihomo-runtime.yaml` | Mihomo 进程/容器内看到的同一配置路径 |
| `INTERNAL_BIND_HOST` | `127.0.0.1` | Redis、subconverter、Mihomo API、后端 API 暴露到宿主机的绑定地址 |
| `FRONTEND_BIND_HOST` | `127.0.0.1` | 前端管理后台暴露到宿主机的绑定地址 |
| `BACKEND_PORT` | `8000` | 后端 API 暴露端口 |
| `SUBCONVERTER_PORT` | `25500` | subconverter 暴露端口 |
| `MIHOMO_API_PORT` | `9090` | Mihomo API 暴露端口 |
| `SMART_PROXY_PORT_START` | `37890` | 智能代理自动分配端口起点 |
| `SMART_PROXY_PORT_END` | `37900` | 智能代理自动分配端口终点 |
| `SMART_PROXY_BIND_HOST` | `127.0.0.1` | 智能代理端口暴露到宿主机的绑定地址 |
| `SMART_PROXY_AUTO_APPLY_INTERVAL_MINUTES` | `0` | 定时重新应用并热重载 Mihomo；`0` 关闭 |
| `SMART_PROXY_MONITOR_INTERVAL_MINUTES` | `1` | 智能代理运行状态监控间隔；`0` 关闭 |
| `SMART_PROXY_TRAFFIC_GUARD_ENABLED` | `true` | 是否启用智能代理流量保护 |
| `SMART_PROXY_MIN_REMAINING_MB` | `0` | 剩余流量小于等于该值时排除节点 |
| `SMART_PROXY_LOW_REMAINING_MB` | `2048` | 剩余流量小于等于该值时降权排序 |
| `SMART_PROXY_EXPIRE_SOON_DAYS` | `3` | 订阅将在该天数内到期时降权排序 |
| `SMART_PROXY_EXCLUDE_UNKNOWN_TRAFFIC` | `false` | 是否排除没有流量响应头的订阅节点 |
| `CORS_ORIGINS` | `http://localhost:5173,http://localhost:8088` | 允许跨域来源，逗号分隔 |
| `FRONTEND_PORT` | `8088` | 前端容器暴露端口 |
| `REDIS_PORT` | `6379` | Redis 暴露到宿主机的端口 |
| `URL_BLOCK_PRIVATE_NETWORKS` | `true` | 是否阻止私网/回环/保留订阅地址 |
| `URL_ALLOWLIST` | 空 | 允许的订阅域名，逗号分隔；为空表示不限制域名 |
| `RATE_LIMIT_REQUESTS` | `180` | 限流窗口内最大请求数 |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | 限流窗口秒数 |
| `RATE_LIMIT_TRUST_PROXY_HEADERS` | `true` | 限流是否优先使用 `X-Real-IP` / `X-Forwarded-For` |

## 本地开发

后端本地开发配置不会提交到仓库。可以先复制示例文件：

```powershell
Copy-Item backend\.env.development.example backend\.env.development
```

[backend/.env.development.example](D:/AppData/Nebula/backend/.env.development.example:1) 默认适配本项目 Compose Redis、subconverter 和 Mihomo：

```env
APP_ENV=development
TZ=Asia/Shanghai
REDIS_URL=redis://127.0.0.1:6379/0
SUBCONVERTER_URL=http://127.0.0.1:25500
MIHOMO_API_URL=http://127.0.0.1:9090
MIHOMO_RUNTIME_CONFIG_PATH=./data/mihomo-runtime.yaml
MIHOMO_CORE_CONFIG_PATH=/root/.config/mihomo/mihomo-runtime.yaml
```

如果你使用的 Redis 设置了密码，请把 `backend/.env.development` 改成：

```env
REDIS_URL=redis://:your-password@127.0.0.1:6379/0
```

启动依赖：

```bash
docker compose up -d redis subconverter mihomo
```

启动后端：

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

启动前端：

```powershell
cd frontend
npm install
npm run dev
```

开发访问：

```text
前端：http://localhost:5173
后端：http://localhost:8000
```

Vite 已配置 `/api` 和 `/health` 代理到 `http://localhost:8000`，并支持 WebSocket 代理。

## 数据库

默认使用 SQLite：

```text
backend/data/nebula.db
```

PostgreSQL 示例：

```env
DATABASE_URL=postgresql+asyncpg://nebula:password@postgres:5432/nebula
```

项目提供 Alembic 迁移骨架：

```bash
cd backend
alembic upgrade head
```

应用启动时也会执行 `init_db()` 建表，并通过 `bootstrap_defaults()` 初始化默认数据。

## 后台任务

APScheduler 启动后每分钟检查一次配置，并按设置决定是否执行实际任务：

后端调度器使用 `Asia/Shanghai`，模型默认时间、订阅刷新时间、流量快照时间、智能代理检测时间和 WebSocket 推送时间也按中国时区生成。

| 任务 | 设置项 | 默认 |
| --- | --- | --- |
| 节点池同步 | `node_pool_sync_interval_minutes` | `30` 分钟 |
| 订阅流量轮询 | `traffic_poll_interval_minutes` | `30` 分钟 |
| 智能代理应用到 Mihomo | `smart_proxy_auto_apply_interval_minutes` | `0`，关闭 |
| 智能代理状态监控和 IP 白名单巡检 | `smart_proxy_monitor_interval_minutes` | `1` 分钟 |
| sing-box 默认缓存预热 | 固定任务 | `30` 分钟 |

## 开源协议

本项目以 GNU General Public License v3.0 开源发布，详见 [LICENSE](D:/AppData/Nebula/LICENSE:1)。

## 设计边界

- Nebula 不自行实现 vmess、vless、ss、trojan 等复杂订阅协议解析；节点解析依赖 `subconverter` 先输出 Clash YAML。
- Nebula 不自行实现 HTTP/SOCKS 代理协议栈；智能代理入口由 Mihomo `listeners` 提供。
- IP 白名单不是 listener 原生 ACL，而是 Nebula 通过 Mihomo `/connections` API 巡检并关闭未授权连接。
- `sing-box` 当前仍走 `subconverter` 聚合转换，不从统一节点池生成原生 sing-box 配置。
