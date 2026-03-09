# db/group_db.py
import sqlite3
from typing import Optional, Tuple, List, Dict

from config.settings import settings


class GroupDatabase:
    """
    群组数据库读取封装（只读）
    用于读取群组中的记录
    """

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _get_conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def find_latest_by_data(
        self, data: str
    ) -> Optional[Tuple[int, int]]:
        """
        根据 data 查找最近一条记录
        
        返回：
        (group_id, message_id)
        或 None
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT group_id, message_id
                    FROM records
                    WHERE data = ?
                    ORDER BY created_at DESC, id DESC
                    LIMIT 1
                    """,
                    (data,),
                )
                result = cur.fetchone()
                if result:
                    return result
                return None
        except sqlite3.OperationalError as e:
            # 如果表不存在或字段不存在，返回 None
            print(f"查询失败，可能表结构不匹配: {e}")
            return None
    
    def find_all_by_data(
        self, data: str
    ) -> List[Dict]:
        """
        查找所有匹配该数据的记录
        返回完整记录信息
        """
        try:
            with self._get_conn() as conn:
                cur = conn.cursor()
                cur.execute(
                    """
                    SELECT data, number, user_id, username, group_id, message_id, created_at
                    FROM records
                    WHERE data = ?
                    ORDER BY created_at DESC, id DESC
                    """,
                    (data,),
                )
                rows = cur.fetchall()
                
                records = []
                for row in rows:
                    records.append({
                        "data": row[0],
                        "number": row[1],
                        "user_id": row[2],
                        "username": row[3],
                        "group_id": row[4],
                        "message_id": row[5],
                        "created_at": row[6]
                    })
                return records
        except sqlite3.OperationalError as e:
            print(f"查询失败，可能表结构不匹配: {e}")
            return []


# 全局实例
group_one_db = GroupDatabase(settings.GROUP_ONE_DB)
group_two_db = GroupDatabase(settings.GROUP_TWO_DB)