from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.execution_token import ExecutionToken, TokenStatus
from app.domain.repositories.execution_token_repository import ExecutionTokenRepository
from app.infrastructure.persistence.models.execution_token_model import ExecutionTokenModel


class SQLAlchemyExecutionTokenRepository(ExecutionTokenRepository):
    """SQLAlchemy adapter for ExecutionTokenRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_jti(self, tenant_id: str, jti: str) -> ExecutionToken | None:
        stmt = select(ExecutionTokenModel).where(
            ExecutionTokenModel.tenant_id == tenant_id,
            ExecutionTokenModel.jti == jti,
        )
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def list_by_agent(
        self,
        tenant_id: str,
        agent_id: str,
        status: TokenStatus | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[ExecutionToken], int]:
        stmt = select(ExecutionTokenModel).where(
            ExecutionTokenModel.tenant_id == tenant_id,
            ExecutionTokenModel.agent_id == agent_id,
        )
        count_stmt = select(ExecutionTokenModel).where(
            ExecutionTokenModel.tenant_id == tenant_id,
            ExecutionTokenModel.agent_id == agent_id,
        )
        if status is not None:
            stmt = stmt.where(ExecutionTokenModel.status == status.value)
            count_stmt = count_stmt.where(ExecutionTokenModel.status == status.value)
        total = len(self._session.scalars(count_stmt).all())
        stmt = stmt.order_by(ExecutionTokenModel.issued_at.desc()).limit(limit).offset(offset)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(m) for m in models], total

    async def save(self, token: ExecutionToken) -> ExecutionToken:
        stmt = select(ExecutionTokenModel).where(ExecutionTokenModel.token_id == token.token_id)
        model = self._session.scalar(stmt)
        if model is None:
            model = ExecutionTokenModel(
                token_id=token.token_id,
                tenant_id=token.tenant_id,
                jti=token.jti,
                agent_id=token.agent_id,
                tool=token.tool,
                status=token.status.value,
                issued_at=token.issued_at,
                expires_at=token.expires_at,
                consumed_at=token.consumed_at,
                revoked_at=token.revoked_at,
            )
            self._session.add(model)
        else:
            model.status = token.status.value
            model.consumed_at = token.consumed_at
            model.revoked_at = token.revoked_at
        self._session.flush()
        return self._to_entity(model)

    async def revoke(
        self,
        tenant_id: str,
        token_id: str,
        *,
        revoked_at: datetime | None = None,
    ) -> ExecutionToken | None:
        stmt = select(ExecutionTokenModel).where(
            ExecutionTokenModel.tenant_id == tenant_id,
            ExecutionTokenModel.token_id == token_id,
        )
        model = self._session.scalar(stmt)
        if model is None:
            return None
        model.status = TokenStatus.REVOKED.value
        model.revoked_at = revoked_at or datetime.now(UTC)
        self._session.flush()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: ExecutionTokenModel) -> ExecutionToken:
        return ExecutionToken(
            token_id=model.token_id,
            tenant_id=model.tenant_id,
            jti=model.jti,
            agent_id=model.agent_id,
            tool=model.tool,
            status=TokenStatus(model.status),
            issued_at=model.issued_at,
            expires_at=model.expires_at,
            consumed_at=model.consumed_at,
            revoked_at=model.revoked_at,
        )
