from fastapi import APIRouter

from app.api.routes import (
    ant_proxy,
    auth,
    dashboard,
    logs,
    nodes,
    rules,
    settings,
    smart_proxies,
    status_ws,
    sub_output,
    subscriptions,
    templates,
)


api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(subscriptions.router, prefix="/subscriptions", tags=["subscriptions"])
api_router.include_router(nodes.router, prefix="/nodes", tags=["nodes"])
api_router.include_router(smart_proxies.router, prefix="/smart-proxies", tags=["smart proxies"])
api_router.include_router(ant_proxy.router, prefix="/ant-proxy", tags=["ant proxy"])
api_router.include_router(rules.router, prefix="/rules", tags=["rules"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(settings.router, prefix="/settings", tags=["settings"])
api_router.include_router(logs.router, prefix="/logs", tags=["logs"])
api_router.include_router(sub_output.router, prefix="/sub", tags=["subscription output"])
api_router.include_router(status_ws.router, prefix="/ws", tags=["status websocket"])
