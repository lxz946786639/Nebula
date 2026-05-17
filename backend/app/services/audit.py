from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


async def write_audit(
    session: AsyncSession,
    *,
    actor: str,
    action: str,
    resource: str,
    detail: str | None = None,
) -> None:
    session.add(AuditLog(actor=actor, action=action, resource=resource, detail=detail))
