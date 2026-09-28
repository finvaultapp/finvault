from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from pathlib import Path

from . import config

_connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(config.DATABASE_URL, connect_args=_connect_args, pool_pre_ping=True)

if config.DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def add_missing_columns() -> None:
    """Tiny forward-only migration: add columns that newer versions define but an older database lacks."""
    from sqlalchemy import inspect, text

    insp = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            have = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in have:
                    continue
                ddl = f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col.type.compile(engine.dialect)}'
                if col.server_default is not None:
                    ddl += f" DEFAULT '{col.server_default.arg}'"
                conn.execute(text(ddl))


def migrate_schema() -> None:
    """Run Alembic migrations, with the old additive migrator as a compatibility net."""
    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    if ini.exists():
        from alembic import command
        from alembic.config import Config

        command.upgrade(Config(str(ini)), "head")
        add_missing_columns()
        return
    Base.metadata.create_all(engine)
    add_missing_columns()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
