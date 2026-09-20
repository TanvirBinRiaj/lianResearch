from sqlalchemy import Column, String, Text, Integer, DateTime, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker
from pathlib import Path
from datetime import datetime, timezone

DB_PATH = Path(__file__).parent.parent.parent / "data" / "research.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()

class ResearchJob(Base):
    __tablename__ = "research_jobs"
    id = Column(String, primary_key=True)
    query = Column(Text)
    depth = Column(String)
    status = Column(String)  # planning, researching, synthesizing, done, error, interrupted
    plan_json = Column(Text)
    sources_json = Column(Text)
    report_md = Column(Text)
    progress_json = Column(Text, default="[]")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

Base.metadata.create_all(bind=engine)

# --- lightweight migration + crash recovery (runs once per process boot) ---
try:
    from sqlalchemy import inspect as _inspect, text as _text
    _cols = [c["name"] for c in _inspect(engine).get_columns("research_jobs")]
    with engine.begin() as _conn:
        if "progress_json" not in _cols:
            _conn.execute(_text("ALTER TABLE research_jobs ADD COLUMN progress_json TEXT DEFAULT '[]'"))
        # any job left 'researching' belongs to a dead process lifetime:
        # its asyncio worker + in-memory progress are gone, so mark it honestly
        # instead of spinning the UI forever.
        _conn.execute(_text(
            "UPDATE research_jobs SET status='interrupted', updated_at=CURRENT_TIMESTAMP "
            "WHERE status='researching'"))
except Exception as _e:
    print("db migrate/reconcile:", _e)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
