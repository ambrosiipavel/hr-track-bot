"""Подключение к базе и типовые запросы."""

from datetime import datetime, timedelta

from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import selectinload

from config import DATABASE_URL, ADMIN_ID
from database.models import (
    Base, User, Candidate, StatusHistory, Role, Status, FINAL_STATUSES
)

engine = create_async_engine(DATABASE_URL, echo=False)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db() -> None:
    """Создаёт таблицы и заводит администратора из .env при первом запуске."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with SessionLocal() as session:
        admin = await get_user_by_tg(session, ADMIN_ID)
        if admin is None:
            session.add(User(
                telegram_id=ADMIN_ID,
                full_name="Администратор",
                role=Role.ADMIN,
            ))
            await session.commit()


# ---------- пользователи ----------

async def get_user_by_tg(session: AsyncSession, telegram_id: int) -> User | None:
    result = await session.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    return result.scalar_one_or_none()


async def get_coordinators(session: AsyncSession) -> list[User]:
    result = await session.execute(
        select(User)
        .where(User.role == Role.COORDINATOR, User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
    )
    return list(result.scalars())


# ---------- кандидаты ----------

async def create_candidate(
    session: AsyncSession,
    first_name: str,
    last_name: str,
    phone: str,
    position: str,
    coordinator_id: int,
    created_by_id: int,
) -> Candidate:
    candidate = Candidate(
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        position=position,
        coordinator_id=coordinator_id,
        created_by_id=created_by_id,
        status=Status.NEW,
    )
    session.add(candidate)
    await session.flush()  # нужен id кандидата для записи в историю

    session.add(StatusHistory(
        candidate_id=candidate.id,
        user_id=created_by_id,
        old_status=None,
        new_status=Status.NEW,
        comment="Кандидат добавлен",
    ))
    await session.commit()
    return candidate


async def get_candidate(session: AsyncSession, candidate_id: int) -> Candidate | None:
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.coordinator), selectinload(Candidate.created_by))
        .where(Candidate.id == candidate_id)
    )
    return result.scalar_one_or_none()


async def get_candidates_for_coordinator(
    session: AsyncSession, coordinator_id: int, only_open: bool = True
) -> list[Candidate]:
    """Кандидаты конкретного координатора. Чужих он не увидит."""
    query = select(Candidate).where(Candidate.coordinator_id == coordinator_id)
    if only_open:
        query = query.where(Candidate.status.notin_(list(FINAL_STATUSES)))
    query = query.order_by(Candidate.created_at.desc())

    result = await session.execute(query)
    return list(result.scalars())


async def change_status(
    session: AsyncSession,
    candidate: Candidate,
    new_status: Status,
    user_id: int,
    comment: str | None = None,
    next_contact_at: datetime | None = None,
) -> None:
    """Меняет статус и обязательно пишет запись в историю."""
    old_status = candidate.status

    candidate.status = new_status
    candidate.next_contact_at = next_contact_at

    if new_status in FINAL_STATUSES:
        candidate.closed_at = datetime.now()
        if new_status == Status.REJECTED:
            candidate.reject_reason = comment
    else:
        candidate.closed_at = None

    session.add(StatusHistory(
        candidate_id=candidate.id,
        user_id=user_id,
        old_status=old_status,
        new_status=new_status,
        comment=comment,
    ))
    await session.commit()


async def get_history(session: AsyncSession, candidate_id: int) -> list[StatusHistory]:
    result = await session.execute(
        select(StatusHistory)
        .options(selectinload(StatusHistory.user))
        .where(StatusHistory.candidate_id == candidate_id)
        .order_by(StatusHistory.created_at)
    )
    return list(result.scalars())


# ---------- статистика ----------

async def get_stats(session: AsyncSession) -> dict[str, int]:
    result = await session.execute(
        select(Candidate.status, func.count(Candidate.id)).group_by(Candidate.status)
    )
    by_status = {status: count for status, count in result.all()}

    total = sum(by_status.values())
    closed = sum(by_status.get(s, 0) for s in FINAL_STATUSES)

    return {
        "total": total,
        "open": total - closed,
        "closed": closed,
        "by_status": by_status,
    }


# ---------- пользователи: управление ----------

async def get_all_users(session: AsyncSession) -> list[User]:
    result = await session.execute(select(User).order_by(User.role, User.full_name))
    return list(result.scalars())


async def create_user(
    session: AsyncSession, telegram_id: int, full_name: str, role: Role
) -> User | None:
    """Возвращает None, если такой telegram_id уже занят."""
    if await get_user_by_tg(session, telegram_id) is not None:
        return None

    user = User(telegram_id=telegram_id, full_name=full_name, role=role)
    session.add(user)
    await session.commit()
    return user


async def deactivate_user(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    user.is_active = False
    await session.commit()
    return user


# ---------- выборки для админки и напоминаний ----------

async def get_all_candidates(session: AsyncSession) -> list[Candidate]:
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.coordinator), selectinload(Candidate.created_by))
        .order_by(Candidate.id)
    )
    return list(result.scalars())


async def get_all_history(session: AsyncSession) -> list[StatusHistory]:
    result = await session.execute(
        select(StatusHistory)
        .options(selectinload(StatusHistory.user), selectinload(StatusHistory.candidate))
        .order_by(StatusHistory.candidate_id, StatusHistory.created_at)
    )
    return list(result.scalars())


async def get_open_candidates(session: AsyncSession) -> list[Candidate]:
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.coordinator))
        .where(Candidate.status.notin_(list(FINAL_STATUSES)))
        .order_by(Candidate.created_at)
    )
    return list(result.scalars())


async def search_candidates(session: AsyncSession, query: str) -> list[Candidate]:
    """Поиск по фамилии, имени, телефону и должности.

    Фильтрация идёт в Python, а не в SQL: встроенная функция LOWER() в SQLite
    работает только с латиницей, поэтому «Сидоров» и «сидоров» в запросе
    не совпали бы. На PostgreSQL можно вернуться к ILIKE на стороне базы.
    """
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.coordinator))
        .order_by(Candidate.id.desc())
    )
    needle = query.strip().lower()

    return [
        c for c in result.scalars()
        if needle in c.last_name.lower()
        or needle in c.first_name.lower()
        or needle in c.phone.lower()
        or needle in c.position.lower()
    ]


async def get_due_callbacks(session: AsyncSession) -> list[Candidate]:
    """Кандидаты, у которых наступила дата перезвона."""
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.coordinator))
        .where(
            Candidate.status == Status.CALLBACK,
            Candidate.next_contact_at.is_not(None),
            Candidate.next_contact_at <= datetime.now(),
        )
        .order_by(Candidate.next_contact_at)
    )
    return list(result.scalars())


async def get_stale_candidates(session: AsyncSession, days: int) -> list[Candidate]:
    """Открытые кандидаты, созданные раньше чем N дней назад."""
    threshold = datetime.now() - timedelta(days=days)
    result = await session.execute(
        select(Candidate)
        .options(selectinload(Candidate.coordinator))
        .where(
            Candidate.status.notin_(list(FINAL_STATUSES)),
            Candidate.created_at <= threshold,
        )
        .order_by(Candidate.created_at)
    )
    return list(result.scalars())
