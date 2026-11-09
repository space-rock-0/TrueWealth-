from datetime import datetime, timezone
import os
from typing import Optional

from sqlalchemy import inspect, text
from sqlmodel import Field, Session, SQLModel, create_engine, select

from app.core.config import SQLITE_PATH

# SQLModel.metadata.create_all only creates missing tables, it never alters existing ones,
# so a column added after the table already exists on disk needs an explicit ALTER TABLE
_ADDED_COLUMNS = [
    ("model_used", "TEXT"),
    ("fallback_used", "BOOLEAN DEFAULT FALSE"),
    ("compliance_violations", "TEXT"),
    ("verification_risk", "TEXT"),
    ("needs_review", "BOOLEAN DEFAULT FALSE"),
    ("review_status", "TEXT DEFAULT 'none'"),
    ("human_verdict", "TEXT"),
    ("reviewed_at", "TIMESTAMP"),
    ("user_id", "INTEGER"),
]


def _utcnow():
    return datetime.now(timezone.utc)


class QueryLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str
    question: str
    answer: str
    source: str
    agents_run: str
    latency_ms: float
    tokens_used: Optional[int] = None
    degraded: Optional[str] = None
    model_used: Optional[str] = None
    fallback_used: bool = False
    compliance_violations: Optional[str] = None
    verification_risk: Optional[str] = None
    needs_review: bool = False
    review_status: str = "none"
    human_verdict: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    user_id: Optional[int] = Field(default=None, foreign_key="appuser.id", index=True)
    created_at: datetime = Field(default_factory=_utcnow)


class AppUser(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=254)
    username: str = Field(index=True, unique=True, max_length=32)
    password_hash: str
    email_verified: bool = False
    is_active: bool = True
    created_at: datetime = Field(default_factory=_utcnow)


class AuthSession(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="appuser.id", index=True)
    token_digest: str = Field(index=True, unique=True, max_length=64)
    csrf_digest: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime


class AuthToken(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="appuser.id", index=True)
    purpose: str = Field(index=True, max_length=32)
    token_digest: str = Field(index=True, unique=True, max_length=64)
    created_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime


_database_url = os.getenv("DATABASE_URL", f"sqlite:///{SQLITE_PATH}")
if _database_url.startswith("postgres://"):
    _database_url = "postgresql+psycopg://" + _database_url[len("postgres://"):]
elif _database_url.startswith("postgresql://"):
    _database_url = "postgresql+psycopg://" + _database_url[len("postgresql://"):]
_connect_args = {"check_same_thread": False} if _database_url.startswith("sqlite") else {}
engine = create_engine(_database_url, connect_args=_connect_args, pool_pre_ping=True)


def init_db():
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        existing = {column["name"] for column in inspect(engine).get_columns("querylog")}
        for name, coltype in _ADDED_COLUMNS:
            if name not in existing:
                conn.execute(text(f"ALTER TABLE querylog ADD COLUMN {name} {coltype}"))
        conn.commit()
    if inspect(engine).has_table('statement'):
        columns = {column['name'] for column in inspect(engine).get_columns('statement')}
        if 'processing_started_at' not in columns:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE statement ADD COLUMN processing_started_at TIMESTAMP'))


def log_query(session_id, question, answer, source, agents_run, latency_ms, tokens_used=None,
              degraded=None, model_used=None, fallback_used=False, compliance_violations=None,
              verification_risk=None, needs_review=False, user_id=None):
    with Session(engine) as session:
        entry = QueryLog(
            session_id=session_id,
            question=question,
            answer=answer,
            source=source,
            agents_run=",".join(agents_run),
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            degraded=degraded,
            model_used=model_used,
            fallback_used=fallback_used,
            compliance_violations=",".join(compliance_violations) if compliance_violations else None,
            verification_risk=verification_risk,
            needs_review=needs_review,
            review_status="pending" if needs_review else "none",
            user_id=user_id,
        )
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def get_history(limit=50, offset=0, user_id=None):
    with Session(engine) as session:
        stmt = select(QueryLog).order_by(QueryLog.id.desc()).offset(offset).limit(limit)
        if user_id is not None:
            stmt = stmt.where(QueryLog.user_id == user_id)
        return session.exec(stmt).all()


def get_session_history(session_id, limit=10, user_id=None):
    with Session(engine) as session:
        stmt = select(QueryLog).where(QueryLog.session_id == session_id)
        if user_id is not None:
            stmt = stmt.where(QueryLog.user_id == user_id)
        stmt = stmt.order_by(QueryLog.id.desc()).limit(limit)
        rows = session.exec(stmt).all()
    return list(reversed(rows))


def get_review_queue(limit=50, offset=0, status="pending", user_id=None):
    with Session(engine) as session:
        stmt = select(QueryLog).where(QueryLog.needs_review.is_(True))
        if user_id is not None:
            stmt = stmt.where(QueryLog.user_id == user_id)
        if status:
            stmt = stmt.where(QueryLog.review_status == status)
        stmt = stmt.order_by(QueryLog.id.desc()).offset(offset).limit(limit)
        return session.exec(stmt).all()


def submit_review(query_id, verdict, user_id=None):
    with Session(engine) as session:
        entry = session.get(QueryLog, query_id)
        if entry is None or (user_id is not None and entry.user_id != user_id):
            return None
        entry.human_verdict = verdict
        entry.review_status = "reviewed"
        entry.reviewed_at = _utcnow()
        session.add(entry)
        session.commit()
        session.refresh(entry)
        return entry


def get_stats(user_id=None):
    with Session(engine) as session:
        stmt = select(QueryLog)
        if user_id is not None:
            stmt = stmt.where(QueryLog.user_id == user_id)
        rows = session.exec(stmt).all()

    count = len(rows)
    avg_latency_ms = sum(r.latency_ms for r in rows) / count if count else 0
    degraded_count = sum(1 for r in rows if r.degraded)
    fallback_count = sum(1 for r in rows if r.fallback_used)
    compliance_violation_count = sum(1 for r in rows if r.compliance_violations)
    high_risk_count = sum(1 for r in rows if r.verification_risk == "high")
    source_counts = {}
    model_counts = {}
    for r in rows:
        source_counts[r.source] = source_counts.get(r.source, 0) + 1
        if r.model_used:
            model_counts[r.model_used] = model_counts.get(r.model_used, 0) + 1

    reviewed = [r for r in rows if r.review_status == "reviewed"]
    review_pending_count = sum(1 for r in rows if r.review_status == "pending")
    review_completed_count = len(reviewed)
    approved_count = sum(1 for r in reviewed if r.human_verdict == "approved")
    human_agreement_rate = approved_count / review_completed_count if review_completed_count else None

    return {
        "total_queries": count,
        "avg_latency_ms": avg_latency_ms,
        "degraded_count": degraded_count,
        "fallback_count": fallback_count,
        "compliance_violation_count": compliance_violation_count,
        "high_risk_count": high_risk_count,
        "source_counts": source_counts,
        "model_counts": model_counts,
        "review_pending_count": review_pending_count,
        "review_completed_count": review_completed_count,
        "human_agreement_rate": human_agreement_rate,
    }
