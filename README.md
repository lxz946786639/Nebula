# Nebula Subscriptions

Nebula Subscriptions 是一个自托管的代理订阅聚合与智能代理管理平台。

它适合需要同时管理多个订阅源、统一生成客户端订阅地址、查看节点和流量状态，并为局域网设备或应用提供稳定代理入口的个人或小团队使用。

当前版本：`v1.1.0`

开源协议：GNU General Public License v3.0，详见 [LICENSE](LICENSE)。

## 项目能做什么

- 订阅聚合：集中管理多个订阅源，按分组、标签和优先级组织节点。
- 客户端订阅：生成 Clash、Mihomo、sing-box、v2rayN 可用的订阅地址。
- 节点管理：同步节点池，支持筛选、去重、启用/停用、延迟检测和来源追踪。
- 流量状态：展示订阅剩余流量、到期时间和异常状态。
- 智能代理：创建 HTTP、SOCKS5、Mixed 代理入口，支持认证、访问 Token、IP 白名单和健康检测。
- 智能调度：按订阅、国家/地区、标签或手动节点选择代理候选，并支持故障转移、测速选择、稳定优先等策略。
- 流量保护：订阅到期或流量用完后，可自动避开不可用节点；订阅恢复后可自动重新纳入候选。
- Web 管理后台：提供订阅、节点、智能代理、配置、日志和实时状态页面。

## v1.1.0 更新要点

- 移动端体验升级：顶部固定、底部导航、分页、主要操作按钮、列表卡片和弹窗均适配小屏使用。
- 首页、订阅管理、节点管理、智能代理、规则管理、配置模板和日志中心完成移动端布局优化，减少横向滚动和按钮溢出。
- 智能代理移动端优化诊断弹窗、节点选择弹窗、运行状态和健康检测信息密度，提升触控操作效率。
- 新增 PWA 支持：内置 Web App Manifest、Service Worker、离线兜底页、安装按钮、iOS 主屏图标和前端更新提示。
- PWA 采用应用壳缓存策略，静态资源可离线打开；订阅、节点、日志、代理状态等实时业务数据仍需连接后端。

## v1.0.1 更新要点

- 系统设置拆分「订阅公开访问地址」和「代理公开访问地址」，适配管理后台、订阅接口和代理端口不同的部署方式。
- Redis 地址从页面隐藏，固定为部署环境配置；subconverter 和 Mihomo API 移入系统设置，生产环境修改前会先连通性检测。
- 本地开发环境中 subconverter 和 Mihomo API 配置由环境变量控制，页面只读，避免误把 Docker 内网地址写入开发配置。
- Docker 默认不暴露 Redis、subconverter、Mihomo API 到宿主机；本机调试可叠加 `docker-compose.debug.yml`。
- 智能代理页面和首页完整展示 Mixed 代理的 HTTP(S) 与 SOCKS5 地址，并优化复制体验。
- 订阅到期、失效或流量耗尽时，智能代理会在必要时检测节点并按冷却策略自动重新应用 Mihomo runtime。

## 快速开始

准备环境：

- Git
- Docker
- Docker Compose v2

克隆项目：

```bash
git clone https://github.com/lxz946786639/Nebula.git
cd Nebula
```

创建环境配置：

```bash
cp .env.example .env
```

首次部署前请至少修改 `.env` 中的这些配置：

```env
SECRET_KEY=your-random-secret-at-least-32-chars
ADMIN_PASSWORD=your-strong-password
SUBSCRIPTION_TOKEN=your-random-subscription-token
```

启动服务：

```bash
docker compose up -d --build
```

访问地址：

| 服务 | 地址 |
| --- | --- |
| Web 管理后台 | `http://localhost:8088` |
| 后端 API 文档 | `http://localhost:8000/docs` |
| 后端健康检查 | `http://localhost:8000/health` |

默认管理员用户名为 `admin`。生产环境会拒绝默认弱密码和默认弱 Token，请在启动前完成 `.env` 修改。

## 首次使用流程

1. 登录 Web 管理后台。
2. 进入「订阅管理」，添加一个或多个订阅源。
3. 进入「节点管理」，同步节点池并确认节点可用。
4. 在首页复制客户端订阅地址，导入 Clash、Mihomo、sing-box 或 v2rayN。
5. 如需给设备或应用提供固定代理入口，进入「智能代理」创建代理并应用运行配置。

公开订阅地址格式：

```text
/api/sub/mihomo?token=<SUBSCRIPTION_TOKEN>&group=default&emoji=true
/api/sub/clash?token=<SUBSCRIPTION_TOKEN>&group=default&emoji=true
/api/sub/singbox?token=<SUBSCRIPTION_TOKEN>&group=default&emoji=true
/api/sub/v2ray?token=<SUBSCRIPTION_TOKEN>&group=default&emoji=true
```

## Docker 部署说明

默认部署会启动 Web、后端、缓存、订阅转换和代理运行所需服务。常规使用只需要执行：

```bash
docker compose up -d
```

查看状态和日志：

```bash
docker compose ps
docker compose logs -f backend
```

停止服务：

```bash
docker compose down
```

默认网络暴露策略：

- Web 管理后台默认绑定 `127.0.0.1:8088`。
- 后端 API 默认绑定 `127.0.0.1:8000`。
- 智能代理端口默认映射 `127.0.0.1:37890-37900`。
- Redis、subconverter、Mihomo API 默认不暴露到宿主机，只在 Docker 内部网络使用。

如需局域网访问管理后台或智能代理，请在 `.env` 中显式调整：

```env
FRONTEND_BIND_HOST=0.0.0.0
SMART_PROXY_BIND_HOST=0.0.0.0
```

开放到局域网前请确认已设置强密码、随机 Token，并配置好防火墙。

## 生产环境更新

进入部署目录后按顺序执行：

```bash
cd /opt/Nebula

# 备份生产配置和运行数据
cp .env .env.bak.$(date +%Y%m%d%H%M%S)
tar -czf nebula-data-bak-$(date +%Y%m%d%H%M%S).tar.gz backend/data

# 拉取新版本并检查 Compose 配置
git pull --ff-only
docker compose config --quiet

# 重建并滚动更新容器
docker compose up -d --build

# 查看运行状态
docker compose ps
docker compose logs -f backend
```

如果只更新前后端镜像，也可以执行：

```bash
docker compose up -d --build backend frontend
```

但当 `docker-compose.yml`、环境变量或运行时相关配置发生变化时，建议使用完整的 `docker compose up -d --build`。不要用新的 `.env.example` 直接覆盖生产 `.env`，只对照新增配置补齐。

## 本地开发

本地开发通常是在宿主机运行后端和前端，同时用 Docker 启动依赖服务。因为默认部署不会把内部依赖端口暴露到宿主机，所以开发时需要叠加调试 Compose 文件：

```bash
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d redis subconverter mihomo
```

复制后端开发配置：

```powershell
Copy-Item backend\.env.development.example backend\.env.development
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

开发访问地址：

| 服务 | 地址 |
| --- | --- |
| 前端开发服务 | `http://localhost:5173` |
| 后端 API | `http://localhost:8000` |
| API 文档 | `http://localhost:8000/docs` |

开发环境示例默认使用：

```env
REDIS_URL=redis://127.0.0.1:6379/0
SUBCONVERTER_URL=http://127.0.0.1:25500
MIHOMO_API_URL=http://127.0.0.1:9090
```

如果没有叠加 `docker-compose.debug.yml`，宿主机后端无法访问这些 `127.0.0.1` 调试端口。

`APP_ENV=development` 时，系统设置中的 `subconverter_url`、`mihomo_api_url`、`mihomo_api_secret` 会以环境变量为准，页面只读；生产环境才允许在页面修改这些连接地址。

## 系统设置

系统设置用于维护运行后的业务配置：

| 配置 | 说明 |
| --- | --- |
| 订阅公开访问地址 | 用于首页和 WebSocket 推送里的客户端订阅地址；留空时按当前访问地址生成 |
| 代理公开访问地址 | 用于智能代理和首页代理地址；只填域名时保留每个代理自己的端口，填写端口时统一使用该公开端口 |
| subconverter 服务地址 | 生产环境可修改，保存前会检测新地址是否可用；修改成功后会清理订阅缓存并触发节点池同步 |
| Mihomo API 地址 / 密钥 | 生产环境可修改，保存前会检测 `/version`；修改成功后会刷新智能代理运行状态 |
| ACL4SSR 远程规则地址 | 默认规则模板和转换链路使用的远程规则配置 |

Redis 连接地址不在页面中维护，只能在部署时通过 `REDIS_URL` 配置。

## 常用配置

完整配置请参考 [.env.example](.env.example)，其中 `【必改】` 标记的是生产环境部署前必须修改的项目。

| 配置 | 说明 |
| --- | --- |
| `SECRET_KEY` | JWT 签名密钥，生产环境必须使用随机强密钥 |
| `ADMIN_USERNAME` | 首次初始化管理员用户名 |
| `ADMIN_PASSWORD` | 首次初始化管理员密码 |
| `SUBSCRIPTION_TOKEN` | 公开订阅接口 Token |
| `TZ` | 容器和后端时区，默认 `Asia/Shanghai` |
| `FRONTEND_PORT` / `BACKEND_PORT` | Web 和后端 API 暴露端口 |
| `SMART_PROXY_PORT_START` / `SMART_PROXY_PORT_END` | 智能代理端口池范围 |
| `SMART_PROXY_TRAFFIC_GUARD_ENABLED` | 是否启用智能代理流量保护 |

`.env` 修改后通常需要重启服务：

```bash
docker compose up -d
```

## 项目结构

```text
.
├── backend/                  # FastAPI 后端
│   ├── app/                  # API、模型、服务、任务和核心配置
│   ├── alembic/              # 数据库迁移骨架
│   └── data/                 # SQLite、运行配置和运行数据
├── frontend/                 # Vue 管理后台
│   └── src/
├── docker-compose.yml        # 默认部署配置
├── docker-compose.debug.yml  # 本机开发调试端口映射
├── .env.example              # 生产环境配置示例
├── 使用说明文档.md             # 更完整的功能使用说明
└── LICENSE
```

## 开发检查

后端基础检查：

```powershell
cd backend
.\.venv\Scripts\activate
python -m compileall app
```

前端构建检查：

```powershell
cd frontend
npm run build
```

Docker Compose 配置检查：

```bash
docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.debug.yml config --quiet
```

## 文档

- [使用说明文档.md](使用说明文档.md)：面向使用者的完整操作说明和常见问题。
- [.env.example](.env.example)：生产部署环境变量示例。
- [backend/.env.development.example](backend/.env.development.example)：宿主机本地开发配置示例。

## 贡献

欢迎提交 Issue 和 Pull Request。提交前建议：

- 保持功能边界清晰，避免把部署环境、用户数据或本地密钥提交到仓库。
- 新增配置时同步更新 `.env.example` 和相关文档。
- 涉及后端、前端或 Compose 的改动，请尽量附上可复现的验证步骤。

## License

Nebula Subscriptions is released under the GNU General Public License v3.0. See [LICENSE](LICENSE) for details.
