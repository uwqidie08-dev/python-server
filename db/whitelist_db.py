# db/whitelist_db.py
import sqlite3
import logging
from typing import Iterable, List, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)

# 注意：白名单数据库是独立的，不与 phone_bot.db 共用
DB_PATH = settings.WHITELIST_DB


# ==========================================================
# 数据库连接
# ==========================================================

def _conn() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


# ==========================================================
# 初始化表结构（启动时调用一次）
# ==========================================================

def init_whitelist_tables() -> None:
    """
    白名单表：
    - user_id : Telegram user id
    - role    : admin / scorer / team / query
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS whitelist (
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (user_id, role)
        )
        """)
        conn.commit()

    logger.info("whitelist 表初始化完成")


# ==========================================================
# 基础操作
# ==========================================================

def add_user_role(user_id: int, role: str) -> None:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT OR IGNORE INTO whitelist (user_id, role, added_at)
        VALUES (?, ?, datetime('now'))
        """, (user_id, role))
        conn.commit()


def remove_user_role(user_id: int, role: str) -> int:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        DELETE FROM whitelist
        WHERE user_id=? AND role=?
        """, (user_id, role))
        affected = cur.rowcount
        conn.commit()
        return affected


# ==========================================================
# 批量操作（TXT / 管理员命令）
# ==========================================================

def batch_add_users(
    user_ids: Iterable[int],
    role: str
) -> Tuple[int, int]:
    """
    返回：(成功添加, 已存在)
    """
    success = 0
    skipped = 0

    with _conn() as conn:
        cur = conn.cursor()
        for uid in user_ids:
            cur.execute("""
            INSERT OR IGNORE INTO whitelist (user_id, role, added_at)
            VALUES (?, ?, datetime('now'))
            """, (uid, role))
            if cur.rowcount == 1:
                success += 1
            else:
                skipped += 1
        conn.commit()

    return success, skipped


def batch_remove_users(
    user_ids: Iterable[int],
    role: str
) -> int:
    removed = 0

    with _conn() as conn:
        cur = conn.cursor()
        for uid in user_ids:
            cur.execute("""
            DELETE FROM whitelist
            WHERE user_id=? AND role=?
            """, (uid, role))
            removed += cur.rowcount
        conn.commit()

    return removed


# ==========================================================
# 查询 / 判断
# ==========================================================

def has_role(user_id: int, role: str) -> bool:
    """
    auth.team / auth.scorer 使用
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 1 FROM whitelist
        WHERE user_id=? AND role=?
        LIMIT 1
        """, (user_id, role))
        return cur.fetchone() is not None


def get_roles(user_id: int) -> List[str]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT role FROM whitelist
        WHERE user_id=?
        """, (user_id,))
        rows = cur.fetchall()

    return [r[0] for r in rows]


def get_users_by_role(role: str) -> List[int]:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT user_id FROM whitelist
        WHERE role=?
        ORDER BY user_id
        """, (role,))
        rows = cur.fetchall()

    return [r[0] for r in rows]


# ==========================================================
# 管理员辅助
# ==========================================================

def clear_role(role: str) -> int:
    """
    清空某个角色（极少用，慎用）
    """
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        DELETE FROM whitelist
        WHERE role=?
        """, (role,))
        affected = cur.rowcount
        conn.commit()

    logger.warning(f"已清空角色 {role}, rows={affected}")
    return affected