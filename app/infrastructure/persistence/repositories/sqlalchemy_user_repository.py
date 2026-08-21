from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.entities.user import User
from app.domain.repositories.user_repository import UserRepository
from app.infrastructure.persistence.models.user_model import UserModel


class SQLAlchemyUserRepository(UserRepository):
    """SQLAlchemy adapter for UserRepository port."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        return self._to_entity(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        model = self._session.scalar(stmt)
        return self._to_entity(model) if model else None

    async def get_by_tenant(self, tenant_id: str) -> list[User]:
        stmt = select(UserModel).where(UserModel.tenant_id == tenant_id)
        models = self._session.scalars(stmt).all()
        return [self._to_entity(model) for model in models]

    async def save(self, user: User) -> User:
        model = self._session.get(UserModel, user.id)
        if model is None:
            model = UserModel(
                id=user.id,
                email=user.email,
                hashed_password=user.hashed_password,
                is_active=user.is_active,
                created_at=user.created_at,
                role=user.role,
                tenant_id=user.tenant_id,
                failed_login_attempts=user.failed_login_attempts,
                locked_until=user.locked_until,
                password_changed_at=user.password_changed_at,
            )
            self._session.add(model)
        else:
            model.email = user.email
            model.hashed_password = user.hashed_password
            model.is_active = user.is_active
            model.role = user.role
            model.tenant_id = user.tenant_id
            model.failed_login_attempts = user.failed_login_attempts
            model.locked_until = user.locked_until
            model.password_changed_at = user.password_changed_at

        self._session.flush()
        return self._to_entity(model)

    async def exists_by_email(self, email: str) -> bool:
        stmt = select(UserModel.id).where(UserModel.email == email)
        return self._session.scalar(stmt) is not None

    async def increment_failed_login(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        if model is None:
            return None
        model.failed_login_attempts = (model.failed_login_attempts or 0) + 1
        self._session.commit()
        return self._to_entity(model)

    async def reset_failed_login(self, user_id: UUID) -> User | None:
        model = self._session.get(UserModel, user_id)
        if model is None:
            return None
        model.failed_login_attempts = 0
        model.locked_until = None
        self._session.flush()
        return self._to_entity(model)

    async def update_password(self, user_id: UUID, hashed_password: str) -> User | None:
        model = self._session.get(UserModel, user_id)
        if model is None:
            return None
        model.hashed_password = hashed_password
        model.password_changed_at = datetime.now(tz=datetime.utcnow().astimezone().tzinfo)
        self._session.flush()
        return self._to_entity(model)

    async def lock_account(self, user_id: UUID, locked_until: datetime) -> User | None:
        model = self._session.get(UserModel, user_id)
        if model is None:
            return None
        model.locked_until = locked_until
        self._session.commit()
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            hashed_password=model.hashed_password,
            is_active=model.is_active,
            created_at=model.created_at,
            role=model.role,
            tenant_id=model.tenant_id,
            failed_login_attempts=model.failed_login_attempts or 0,
            locked_until=model.locked_until,
            password_changed_at=model.password_changed_at,
        )
