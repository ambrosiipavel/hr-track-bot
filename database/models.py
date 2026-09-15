"""Модели базы данных.

Три таблицы:
  User          — сотрудники: рекрутеры, координаторы, администраторы
  Candidate     — кандидаты
  StatusHistory — история изменений статуса, кто и когда менял
"""

from datetime import datetime
from enum import Enum

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, String, Text, Enum as SAEnum
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Role(str, Enum):
    RECRUITER = "recruiter"
    COORDINATOR = "coordinator"
    ADMIN = "admin"


class Status(str, Enum):
    NEW = "new"                  # добавлен, ещё не в работе
    CONTACTED = "contacted"      # связались
    NO_ANSWER = "no_answer"      # не удалось связаться
    CALLBACK = "callback"        # перезвонить
    IN_PROGRESS = "in_progress"  # кандидат в процессе
    HIRED = "hired"              # финальный: вышел на работу
    REJECTED = "rejected"        # финальный: отказ


# Статусы, после которых кандидат считается закрытым
FINAL_STATUSES = {Status.HIRED, Status.REJECTED}

# Подписи для интерфейса
ROLE_LABELS = {
    Role.RECRUITER: "Рекрутер",
    Role.COORDINATOR: "Координатор",
    Role.ADMIN: "Администратор",
}

STATUS_LABELS = {
    Status.NEW: "Новый",
    Status.CONTACTED: "Связались",
    Status.NO_ANSWER: "Не удалось связаться",
    Status.CALLBACK: "Перезвонить",
    Status.IN_PROGRESS: "В процессе",
    Status.HIRED: "Вышел на работу",
    Status.REJECTED: "Отказ",
}


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(128))
    role: Mapped[Role] = mapped_column(SAEnum(Role))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # кандидаты, где этот пользователь — координатор
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="coordinator", foreign_keys="Candidate.coordinator_id"
    )

    def __repr__(self) -> str:
        return f"<User {self.full_name} ({self.role.value})>"


class Candidate(Base):
    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(64))
    last_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(32))
    position: Mapped[str] = mapped_column(String(128))

    status: Mapped[Status] = mapped_column(SAEnum(Status), default=Status.NEW)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    coordinator_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # когда координатор запланировал следующий контакт (статус «перезвонить»)
    next_contact_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    coordinator: Mapped["User"] = relationship(
        back_populates="candidates", foreign_keys=[coordinator_id]
    )
    created_by: Mapped["User"] = relationship(foreign_keys=[created_by_id])
    history: Mapped[list["StatusHistory"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan"
    )

    @property
    def full_name(self) -> str:
        return f"{self.last_name} {self.first_name}"

    @property
    def is_closed(self) -> bool:
        return self.status in FINAL_STATUSES

    @property
    def days_open(self) -> int:
        """Сколько дней кандидат в работе (или сколько шёл до закрытия)."""
        end = self.closed_at or datetime.now()
        return (end - self.created_at).days

    def __repr__(self) -> str:
        return f"<Candidate {self.full_name} [{self.status.value}]>"


class StatusHistory(Base):
    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    old_status: Mapped[Status | None] = mapped_column(SAEnum(Status), nullable=True)
    new_status: Mapped[Status] = mapped_column(SAEnum(Status))
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    candidate: Mapped["Candidate"] = relationship(back_populates="history")
    user: Mapped["User"] = relationship()
