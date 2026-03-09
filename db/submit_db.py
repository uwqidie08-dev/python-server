# db/submit_db.py

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Optional

from config.settings import settings
from db.group_db import group_one_db, group_two_db

logger = logging.getLogger(__name__)


# ==================================================
# 内部：根据群组选择 DB
# ==================================================
def _get_db_path(tg_group_id: int) -> str:
    if tg_group_id == settings.GROUP_ONE_ID:
        return settings.GROUP_ONE_DB
    elif tg_group_id == settings.GROUP_TWO_ID:
        return settings.GROUP_TWO_DB
    else:
        raise ValueError(f"未知群组 ID: {tg_group_id}")


def _conn(db_path: str) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


# ==================================================
# 初始化表（不会影响旧数据）
# ==================================================
def init_submit_tables() -> None:
    """
    启动时调用
    若表已存在，不会做任何破坏性操作
    """
    for db_path in (settings.GROUP_ONE_DB, settings.GROUP_TWO_DB):
        with _conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL,
                number INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                username TEXT,
                created_at TEXT NOT NULL
            )
            """)
            conn.commit()

    logger.info("submit_db 表结构检查完成")


# ==================================================
# 5 分钟内重复提交（同人 + 同数据）
# ==================================================
def is_duplicate_recent(
    *,
    data: str,
    user_id: int,
    window_seconds: int
) -> bool:
    since = (datetime.now() - timedelta(seconds=window_seconds)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    for db_path in (settings.GROUP_ONE_DB, settings.GROUP_TWO_DB):
        with _conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT 1 FROM submissions
            WHERE data=? AND user_id=? AND created_at>=?
            LIMIT 1
            """, (data, user_id, since))
            if cur.fetchone():
                return True

    return False


# ==================================================
# 群组内是否已存在该数据
# ==================================================
def is_duplicate_data(data: str, tg_group_id: int) -> bool:
    db_path = _get_db_path(tg_group_id)

    with _conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 1 FROM submissions
        WHERE data=?
        LIMIT 1
        """, (data,))
        return cur.fetchone() is not None


# ==================================================
# 插入提交数据
# ==================================================
def insert_submission(
    *,
    data: str,
    number: int,
    user_id: int,
    username: Optional[str],
    tg_group_id: int
) -> None:
    db_path = _get_db_path(tg_group_id)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO submissions (
            data,
            number,
            user_id,
            username,
            created_at
        ) VALUES (?, ?, ?, ?, ?)
        """, (
            data,
            number,
            user_id,
            username,
            now
        ))
        conn.commit()

    logger.info(
        f"提交成功 data={data} user={user_id} group={tg_group_id}"
    )


# ==================================================
# 保存记录到群组数据库的 records 表（用于123定位）
# ==================================================
def save_to_group_records(
    *,
    data: str,
    number: int,
    user_id: int,
    username: str,
    tg_group_id: int,
    message_id: int
) -> None:
    """
    将提交记录保存到对应的群组数据库的 records 表中
    用于123定位功能
    """
    from config.settings import settings
    import sqlite3
    from datetime import datetime
    
    # 确定数据库路径
    if tg_group_id == settings.GROUP_ONE_ID:
        db_path = settings.GROUP_ONE_DB
    elif tg_group_id == settings.GROUP_TWO_ID:
        db_path = settings.GROUP_TWO_DB
    else:
        return
    
    # 保存记录
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        
        # 创建表（如果不存在）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            number INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT,
            group_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )
        """)
        
        cur.execute("""
        INSERT INTO records (data, number, user_id, username, group_id, message_id, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (data, number, user_id, username, tg_group_id, message_id, now))
        
        conn.commit()
    
    logger.info(
        f"记录保存成功 data={data} message_id={message_id} group={tg_group_id}"
    )


# ==================================================
# 获取群组记录（用于重复检查）
# ==================================================
def get_duplicate_records(data: str, tg_group_id: int) -> list:
    """
    获取指定数据在群组中的所有记录
    """
    db_path = _get_db_path(tg_group_id)
    
    with _conn(db_path) as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT username, created_at, number
        FROM submissions
        WHERE data=?
        ORDER BY created_at DESC
        LIMIT 10
        """, (data,))
        rows = cur.fetchall()
        
        records = []
        for row in rows:
            username, created_at, number = row
            records.append({
                "username": username or "未知用户",
                "time": created_at,
                "number": number
            })
        
        return records


# ==================================================
# 获取所有群组的重复记录
# ==================================================
def get_all_duplicate_records(data: str) -> dict:
    """
    获取指定数据在所有群组中的记录
    返回：{"group_one": [...], "group_two": [...]}
    """
    results = {}
    
    # 检查群组一
    try:
        results["group_one"] = get_duplicate_records(data, settings.GROUP_ONE_ID)
    except Exception as e:
        logger.error(f"获取群组一记录失败: {e}")
        results["group_one"] = []
    
    # 检查群组二
    try:
        results["group_two"] = get_duplicate_records(data, settings.GROUP_TWO_ID)
    except Exception as e:
        logger.error(f"获取群组二记录失败: {e}")
        results["group_two"] = []
    
    return results


# ==================================================
# 统计重复信息
# ==================================================
def get_duplicate_summary(data: str) -> dict:
    """
    获取重复数据的统计信息
    """
    records_group_one = get_duplicate_records(data, settings.GROUP_ONE_ID)
    records_group_two = get_duplicate_records(data, settings.GROUP_TWO_ID)
    
    all_records = records_group_one + records_group_two
    total_count = len(all_records)
    
    if total_count == 0:
        return {
            "total_count": 0,
            "first_time": None,
            "last_time": None,
            "user_count": 0,
            "total_records": []
        }
    
    # 提取时间信息
    times = [record["time"] for record in all_records if record["time"]]
    first_time = min(times) if times else None
    last_time = max(times) if times else None
    
    # 统计用户数
    users = set(record["username"] for record in all_records)
    user_count = len(users)
    
    # 格式化记录
    formatted_records = []
    for record in all_records[:10]:  # 只取最近10条
        time_str = record["time"]
        if time_str:
            try:
                dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                date = dt.strftime("%Y-%m-%d")
                time = dt.strftime("%H:%M")
                full_time = f"{date} {time}"
            except:
                date = "未知日期"
                time = "未知时间"
                full_time = time_str
        else:
            date = "未知日期"
            time = "未知时间"
            full_time = "未知时间"
        
        formatted_records.append({
            "username": record["username"],
            "date": date,
            "time": time,
            "full_time": full_time,
            "quantity": record["number"]
        })
    
    return {
        "total_count": total_count,
        "first_time": first_time,
        "last_time": last_time,
        "user_count": user_count,
        "total_records": formatted_records
    }


# ==================================================
# 新增：旧代码格式的重复记录获取函数
# ==================================================
def get_duplicate_summary_old_format(data: str) -> dict:
    """
    以旧代码格式获取重复数据的统计信息
    从两个群组的records表中获取完整记录
    """
    try:
        # 获取群组一的所有记录
        records_group_one = group_one_db.find_all_by_data(data)
        # 获取群组二的所有记录
        records_group_two = group_two_db.find_all_by_data(data)
        
        all_records = []
        
        # 处理群组一记录
        for record in records_group_one:
            all_records.append({
                "username": record.get("username", "未知用户"),
                "time": record.get("created_at", ""),
                "value": record.get("data", ""),
                "group_id": record.get("group_id", 0),
                "number": record.get("number", 0),
                "user_id": record.get("user_id", 0),
                "group": "群组一"
            })
        
        # 处理群组二记录
        for record in records_group_two:
            all_records.append({
                "username": record.get("username", "未知用户"),
                "time": record.get("created_at", ""),
                "value": record.get("data", ""),
                "group_id": record.get("group_id", 0),
                "number": record.get("number", 0),
                "user_id": record.get("user_id", 0),
                "group": "群组二"
            })
        
        total_count = len(all_records)
        
        if total_count == 0:
            return {
                "total_count": 0,
                "first_time": None,
                "last_time": None,
                "user_count": 0,
                "total_records": []
            }
        
        # 按时间排序
        all_records.sort(key=lambda x: x.get("time", ""), reverse=True)
        
        # 提取时间信息
        times = [record.get("time", "") for record in all_records if record.get("time")]
        first_time = min(times) if times else None
        last_time = max(times) if times else None
        
        # 统计用户数
        users = set(record.get("username", "未知用户") for record in all_records)
        user_count = len(users)
        
        # 格式化记录（兼容旧格式）
        formatted_records = []
        for record in all_records[:10]:  # 只取最近10条
            time_str = record.get("time", "")
            if time_str:
                try:
                    dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
                    date = dt.strftime("%Y-%m-%d")
                    time = dt.strftime("%H:%M")
                    full_time = f"{date} {time}"
                except:
                    date = "未知日期"
                    time = "未知时间"
                    full_time = time_str
            else:
                date = "未知日期"
                time = "未知时间"
                full_time = "未知时间"
            
            formatted_records.append({
                "username": record.get("username", "未知用户"),
                "date": date,
                "time": time,
                "full_time": full_time,
                "value": record.get("value", ""),
                "second_line": str(record.get("number", 0)),  # 注意：这里是字符串
                "group": record.get("group", "未知群组"),
                "quantity": record.get("number", 0)  # 数字类型
            })
        
        return {
            "total_count": total_count,
            "first_time": first_time,
            "last_time": last_time,
            "user_count": user_count,
            "total_records": formatted_records
        }
        
    except Exception as e:
        logger.error(f"获取重复摘要失败: {e}")
        return {
            "total_count": 0,
            "first_time": None,
            "last_time": None,
            "user_count": 0,
            "total_records": []
        }


# ==================================================
# 新增：获取提交历史
# ==================================================
def get_submission_history_by_data(data: str, user_id: int = None) -> list:
    """
    获取指定数据的所有提交历史
    user_id可选，如果提供则只返回该用户的记录
    """
    try:
        # 获取所有记录
        records_group_one = group_one_db.find_all_by_data(data)
        records_group_two = group_two_db.find_all_by_data(data)
        
        all_records = []
        
        # 处理群组一记录
        for record in records_group_one:
            if user_id is None or record.get("user_id") == user_id:
                all_records.append({
                    "id": record.get("id", 0),
                    "value": record.get("data", ""),
                    "user_id": record.get("user_id", 0),
                    "username": record.get("username", "未知用户"),
                    "time": record.get("created_at", ""),
                    "group_id": record.get("group_id", 0),
                    "group_message_id": record.get("message_id", 0),
                    "private_message_id": 0,  # 旧代码有，新代码没有这个字段
                    "original_content": f"{record.get('data', '')}\n{record.get('number', 0)}",
                    "number": record.get("number", 0)
                })
        
        # 处理群组二记录
        for record in records_group_two:
            if user_id is None or record.get("user_id") == user_id:
                all_records.append({
                    "id": record.get("id", 0),
                    "value": record.get("data", ""),
                    "user_id": record.get("user_id", 0),
                    "username": record.get("username", "未知用户"),
                    "time": record.get("created_at", ""),
                    "group_id": record.get("group_id", 0),
                    "group_message_id": record.get("message_id", 0),
                    "private_message_id": 0,
                    "original_content": f"{record.get('data', '')}\n{record.get('number', 0)}",
                    "number": record.get("number", 0)
                })
        
        # 按时间排序
        all_records.sort(key=lambda x: x.get("time", ""), reverse=True)
        return all_records
        
    except Exception as e:
        logger.error(f"获取提交历史失败: {e}")
        return []


# ==================================================
# 新增：根据消息ID获取用户ID
# ==================================================
def get_user_id_by_message(tg_group_id: int, message_id: int) -> Optional[int]:
    """
    根据群组ID和消息ID获取用户ID
    用于评分回复时找到原始发送者
    """
    try:
        db_path = _get_db_path(tg_group_id)
        
        with _conn(db_path) as conn:
            cur = conn.cursor()
            cur.execute("""
            SELECT user_id FROM records
            WHERE group_id=? AND message_id=?
            LIMIT 1
            """, (tg_group_id, message_id))
            
            result = cur.fetchone()
            if result:
                return result[0]
            return None
    except Exception as e:
        logger.error(f"获取用户ID失败: {e}")
        return None