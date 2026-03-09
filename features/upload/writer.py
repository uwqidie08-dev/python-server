# features/upload/writer.py
import sqlite3
from typing import Iterable, Tuple

from config.settings import settings


def write_numbers(numbers: Iterable[str]) -> Tuple[int, int]:
    """
    写入 phone_bot.db

    返回：
    (新增数量, 已存在数量)
    """
    added = 0
    skipped = 0

    conn = sqlite3.connect(settings.PHONE_BOT_DB)
    cur = conn.cursor()

    for num in numbers:
        try:
            cur.execute(
                "INSERT INTO phones (number) VALUES (?)",
                (num,),
            )
            added += 1
        except sqlite3.IntegrityError:
            skipped += 1

    conn.commit()
    conn.close()

    return added, skipped
