import os
from pathlib import Path
from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATA_DIR = Path(os.environ.get('QISHU_DATA_DIR', Path(__file__).resolve().parents[2] / 'data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = os.environ.get('QISHU_DATABASE_URL', f'sqlite:///{DATA_DIR / "qishu.sqlite3"}')
engine = create_engine(DATABASE_URL, connect_args={'check_same_thread': False} if DATABASE_URL.startswith('sqlite') else {})
if DATABASE_URL.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _record):
        cursor = connection.cursor()
        cursor.execute('PRAGMA foreign_keys=ON')
        cursor.close()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

class Base(DeclarativeBase):
    pass
