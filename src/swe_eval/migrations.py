"""Additive, transactional migrations. Never reinterpret historical verdicts."""
from pathlib import Path


def migrate(db):
    version = db.execute('PRAGMA user_version').fetchone()[0]
    if version > 2:
        raise RuntimeError('unsupported database schema version')
    if version < 2:
        sql = (Path(__file__).parent / 'migrations' / '002_center.sql').read_text()
        db.executescript(sql)
