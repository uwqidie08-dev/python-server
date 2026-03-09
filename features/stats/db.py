# features/stats/db.py
import sqlite3
from datetime import date

from config.settings import settings


def _conn():
    return sqlite3.connect(settings.STATS_DB)


def increase(group_type: str) -> None:
    today = date.today().isoformat()

    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO daily_stats (date, group_type, count)
            VALUES (?, ?, 1)
            ON CONFLICT(date, group_type)
            DO UPDATE SET count = count + 1
            """,
            (today, group_type),
        )


def get_today():
    today = date.today().isoformat()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT group_type, count FROM daily_stats WHERE date = ?",
            (today,),
        )
        return dict(cur.fetchall())


def clear_today():
    today = date.today().isoformat()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM daily_stats WHERE date = ?", (today,))
