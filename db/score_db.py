import sqlite3
import logging
import os
import json
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple, Any
from contextlib import contextmanager

from config.settings import settings

logger = logging.getLogger(__name__)

DB_PATH = settings.SCORE_DB


# ==========================================================
# 内部：数据库连接（使用连接池和超时设置）
# ==========================================================

@contextmanager
def _get_conn():
    """
    使用上下文管理器处理数据库连接
    增加超时和检查相同线程设置，避免锁死
    """
    conn = None
    try:
        conn = sqlite3.connect(
            DB_PATH, 
            check_same_thread=False,
            timeout=20.0  # 增加超时时间
        )
        conn.execute("PRAGMA journal_mode=WAL")  # 使用WAL模式提高并发性能
        conn.execute("PRAGMA synchronous=NORMAL")  # 降低同步级别
        yield conn
    except sqlite3.OperationalError as e:
        logger.error(f"数据库连接错误: {e}")
        raise
    finally:
        if conn:
            conn.close()


# ==========================================================
# 初始化表结构（启动时调用一次）
# ==========================================================

def init_score_tables() -> None:
    with _get_conn() as conn:
        cur = conn.cursor()

        # 评分流水表（权威事实）- 新增 original_sender_name 列
        cur.execute("""
        CREATE TABLE IF NOT EXISTS score_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_group_id INTEGER NOT NULL,
            logical_group TEXT NOT NULL,
            operator_id INTEGER NOT NULL,
            operator_name TEXT,
            target_msg_id INTEGER NOT NULL,
            original_sender_id INTEGER,
            original_sender_name TEXT,  -- ✅ 新增：原始发送者的显示名称
            action_type TEXT NOT NULL,
            score_delta INTEGER DEFAULT 0,
            reply_content TEXT,
            created_at TEXT NOT NULL
        )
        """)

        # 今日统计表（缓存）
        cur.execute("""
        CREATE TABLE IF NOT EXISTS daily_score_summary (
            date TEXT NOT NULL,
            tg_group_id INTEGER NOT NULL,
            logical_group TEXT NOT NULL,
            total_score INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (date, tg_group_id, logical_group)
        )
        """)

        # 创建索引以提高查询性能
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_group_msg 
        ON score_ledger(tg_group_id, target_msg_id)
        """)
        
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_group_date 
        ON score_ledger(tg_group_id, DATE(created_at))
        """)
        
        cur.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_operator_date 
        ON score_ledger(operator_id, DATE(created_at))
        """)

        conn.commit()

    logger.info("score_db 表结构初始化完成")


# ==========================================================
# 内部：写入评分流水
# ==========================================================

def _insert_ledger(
    *,
    tg_group_id: int,
    logical_group: str,
    operator_id: int,
    operator_name: str,
    target_msg_id: int,
    original_sender_id: Optional[int],
    original_sender_name: Optional[str],  # ✅ 新增
    action_type: str,
    score_delta: int = 0,
    reply_content: Optional[str] = None
) -> None:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO score_ledger (
            tg_group_id,
            logical_group,
            operator_id,
            operator_name,
            target_msg_id,
            original_sender_id,
            original_sender_name,  -- ✅ 新增
            action_type,
            score_delta,
            reply_content,
            created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            tg_group_id,
            logical_group,
            operator_id,
            operator_name,
            target_msg_id,
            original_sender_id,
            original_sender_name,  # ✅ 新增
            action_type,
            score_delta,
            reply_content,
            now
        ))
        conn.commit()


# ==========================================================
# 对外 API：评分（普通 / 强制）- 移除重复评分检查
# ==========================================================

def record_score(
    *,
    tg_group_id: int,
    logical_group: str,
    operator_id: int,
    operator_name: str,
    target_msg_id: int,
    original_sender_id: int,
    original_sender_name: str,  # ✅ 新增
    score_delta: int,
    force: bool = False
) -> None:
    """
    记录评分，移除重复评分检查，允许对同一消息多次评分
    """
    action = "force_score" if force else "score"

    # ✅ 移除重复评分检查，允许对同一消息多次评分
    
    _insert_ledger(
        tg_group_id=tg_group_id,
        logical_group=logical_group,
        operator_id=operator_id,
        operator_name=operator_name,
        target_msg_id=target_msg_id,
        original_sender_id=original_sender_id,
        original_sender_name=original_sender_name,  # ✅ 新增
        action_type=action,
        score_delta=score_delta
    )

    _update_daily_summary(
        tg_group_id=tg_group_id,
        logical_group=logical_group,
        delta=score_delta
    )


# ==========================================================
# 对外 API：失败
# ==========================================================

def record_fail(
    *,
    tg_group_id: int,
    logical_group: str,
    operator_id: int,
    operator_name: str,
    target_msg_id: int,
    original_sender_id: int,
    original_sender_name: str  # ✅ 新增
) -> None:
    _insert_ledger(
        tg_group_id=tg_group_id,
        logical_group=logical_group,
        operator_id=operator_id,
        operator_name=operator_name,
        target_msg_id=target_msg_id,
        original_sender_id=original_sender_id,
        original_sender_name=original_sender_name,  # ✅ 新增
        action_type="fail"
    )


# ==========================================================
# 对外 API：回复（文字 / 图片）
# ==========================================================

def record_reply(
    *,
    tg_group_id: int,
    logical_group: str,
    operator_id: int,
    operator_name: str,
    target_msg_id: int,
    original_sender_id: int,
    original_sender_name: str,  # ✅ 新增
    reply_type: str,
    content: str
) -> None:
    _insert_ledger(
        tg_group_id=tg_group_id,
        logical_group=logical_group,
        operator_id=operator_id,
        operator_name=operator_name,
        target_msg_id=target_msg_id,
        original_sender_id=original_sender_id,
        original_sender_name=original_sender_name,  # ✅ 新增
        action_type=reply_type,
        reply_content=content
    )


# ==========================================================
# 今日统计（缓存）
# ==========================================================

def _update_daily_summary(
    *,
    tg_group_id: int,
    logical_group: str,
    delta: int
) -> None:
    today = date.today().strftime("%Y-%m-%d")
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with _get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
        SELECT total_score FROM daily_score_summary
        WHERE date=? AND tg_group_id=? AND logical_group=?
        """, (today, tg_group_id, logical_group))

        row = cur.fetchone()

        if row:
            new_total = row[0] + delta
            cur.execute("""
        UPDATE daily_score_summary
        SET total_score=?, updated_at=?
        WHERE date=? AND tg_group_id=? AND logical_group=?
        """, (new_total, now, today, tg_group_id, logical_group))
        else:
            cur.execute("""
        INSERT INTO daily_score_summary
        (date, tg_group_id, logical_group, total_score, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """, (today, tg_group_id, logical_group, delta, now))

        conn.commit()


# ==========================================================
# 查询：群组最近评分记录（修复版，获取整个群组的记录）
# ==========================================================

def get_recent_scores(tg_group_id: int, limit: int = 5) -> List[Dict]:
    """
    获取群组最近评分记录（整个群组）
    返回完整的记录信息，包括被评分的用户信息
    """
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 
            sl.created_at,
            sl.logical_group,
            sl.score_delta,
            sl.original_sender_name,  -- ✅ 使用新字段
            sl.operator_name as rater_name
        FROM score_ledger sl
        WHERE sl.tg_group_id=? AND sl.action_type IN ('score', 'force_score')
        ORDER BY sl.created_at DESC, sl.id DESC
        LIMIT ?
        """, (tg_group_id, limit))

        rows = cur.fetchall()

    recent_scores = []
    for row in rows:
        created_at, logical_group, score_delta, original_sender_name, rater_name = row
        
        # 处理被评分用户的显示名
        if original_sender_name and original_sender_name.strip():
            user_display = original_sender_name
        else:
            user_display = "未知用户"
        
        recent_scores.append({
            "time": created_at.split(" ")[1] if " " in created_at else created_at,  # 只取时间部分
            "group": logical_group,
            "user": user_display,  # 被评分的用户
            "score": score_delta,
            "rater": rater_name  # 评分者（管理员）
        })

    return recent_scores


# ==========================================================
# 查询：今日统计（按组）
# ==========================================================

def get_today_summary(tg_group_id: int) -> Dict[str, int]:
    today = date.today().strftime("%Y-%m-%d")

    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT logical_group, total_score
        FROM daily_score_summary
        WHERE date=? AND tg_group_id=?
        """, (today, tg_group_id))

        rows = cur.fetchall()

    return {group: score for group, score in rows}


def get_today_total(tg_group_id: int) -> int:
    today = date.today().strftime("%Y-%m-%d")

    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT SUM(total_score)
        FROM daily_score_summary
        WHERE date=? AND tg_group_id=?
        """, (today, tg_group_id))

        result = cur.fetchone()[0]
        return result or 0


# ==========================================================
# 用户评分统计：按原始发送者统计今日评分
# ==========================================================

def get_user_score_statistics(tg_group_id: int) -> Dict[str, Dict[str, Any]]:
    """
    获取用户评分统计的详细信息（按原始发送者分组）
    返回格式：
    {
        "group_total": int,
        "user_stats": {
            "逻辑组名": {
                "total_score": int,
                "user_count": int,
                "users": [
                    {"username": str, "score": int}
                ]
            }
        }
    }
    """
    today = date.today().strftime("%Y-%m-%d")
    
    with _get_conn() as conn:
        cur = conn.cursor()
        
        # 获取群组总分
        cur.execute("""
        SELECT SUM(score_delta)
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND action_type IN ('score', 'force_score')
            AND DATE(created_at)=?
        """, (tg_group_id, today))
        
        group_total = cur.fetchone()[0] or 0
        
        # 获取详细的用户评分统计
        cur.execute("""
        SELECT 
            logical_group,
            original_sender_name,
            SUM(score_delta) as total_score
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND action_type IN ('score', 'force_score')
            AND DATE(created_at)=?
            AND original_sender_name IS NOT NULL
            AND original_sender_name != ''
        GROUP BY logical_group, original_sender_name
        ORDER BY logical_group, SUM(score_delta) DESC
        """, (tg_group_id, today))
        
        rows = cur.fetchall()
    
    # 组织数据
    result = {
        "group_total": group_total,
        "user_stats": {}
    }
    
    current_group = None
    group_data = None
    
    for group, original_sender, total_score in rows:
        if not original_sender:
            continue
        
        # 确保用户名包含"组"字
        if "组" not in original_sender:
            username = f"{original_sender}组"
        else:
            username = original_sender
        
        # 如果是新组
        if group != current_group:
            if group_data and current_group:
                result["user_stats"][current_group] = {
                    "total_score": sum(u["score"] for u in group_data["users"]),
                    "user_count": len(group_data["users"]),
                    "users": group_data["users"]
                }
            
            current_group = group
            group_data = {
                "users": []
            }
        
        # 添加用户（只保留用户名和分数）
        group_data["users"].append({
            "username": username,
            "score": total_score
        })
    
    # 添加最后一组
    if group_data and current_group:
        result["user_stats"][current_group] = {
            "total_score": sum(u["score"] for u in group_data["users"]),
            "user_count": len(group_data["users"]),
            "users": group_data["users"]
        }
    
    return result


# ==========================================================
# 获取用户的总分统计（不分组）
# ==========================================================

def get_user_total_scores(tg_group_id: int) -> Dict[str, int]:
    """
    获取所有用户的总分统计（不按逻辑分组）
    返回：{username: total_score}
    """
    today = date.today().strftime("%Y-%m-%d")
    
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT original_sender_name, SUM(score_delta)
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND action_type IN ('score', 'force_score')
            AND DATE(created_at)=?
            AND original_sender_name IS NOT NULL
            AND original_sender_name != ''
        GROUP BY original_sender_name
        ORDER BY SUM(score_delta) DESC
        """, (tg_group_id, today))
        
        rows = cur.fetchall()
    
    result = {}
    for username, total in rows:
        if not username:
            continue
        
        # 确保用户名包含"组"字
        if "组" not in username:
            display_name = f"{username}组"
        else:
            display_name = username
        
        result[display_name] = total
    
    return result


# ==========================================================
# 获取用户评分记录详情
# ==========================================================

def get_user_score_details(tg_group_id: int, username: str) -> List[Dict]:
    """
    获取指定用户的详细评分记录
    返回评分历史列表
    """
    today = date.today().strftime("%Y-%m-%d")
    
    # 处理用户名（确保包含"组"字）
    if "组" not in username:
        search_name = f"{username}组"
    else:
        search_name = username
    
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 
            created_at,
            logical_group,
            score_delta,
            operator_name
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND original_sender_name=?
            AND action_type IN ('score', 'force_score')
            AND DATE(created_at)=?
        ORDER BY created_at DESC
        """, (tg_group_id, search_name, today))
        
        rows = cur.fetchall()
    
    details = []
    for created_at, logical_group, score_delta, operator_name in rows:
        # 处理operator_name
        if not operator_name or operator_name.strip() == "":
            operator_display = "未知管理员"
        elif operator_name.isdigit():
            operator_display = f"用户{operator_name}"
        else:
            operator_display = operator_name
        
        details.append({
            "time": created_at,
            "group": logical_group,
            "score": score_delta,
            "operator": operator_display
        })
    
    return details


# ==========================================================
# 管理员操作：清空今日统计（不删流水）
# ==========================================================

def clear_today_summary(tg_group_id: int) -> int:
    today = date.today().strftime("%Y-%m-%d")

    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        DELETE FROM daily_score_summary
        WHERE date=? AND tg_group_id=?
        """, (today, tg_group_id))

        affected = cur.rowcount
        conn.commit()

    logger.warning(
        f"今日统计已清空 tg_group_id={tg_group_id}, rows={affected}"
    )
    return affected


# ==========================================================
# 管理员操作：彻底清空今日所有相关数据
# ==========================================================

def clear_today_completely(tg_group_id: int) -> Dict[str, int]:
    """
    彻底清空今日所有相关数据：
    1. 清空 score_ledger 表的今日评分记录
    2. 清空 daily_score_summary 表的今日缓存
    3. 清除强制统计备份文件
    4. 清理内存中的强制统计缓存
    返回：各表删除的记录数统计
    """
    today = date.today().strftime("%Y-%m-%d")
    
    result = {
        "ledger_deleted": 0,
        "summary_deleted": 0,
        "backup_deleted": 0
    }

    with _get_conn() as conn:
        cur = conn.cursor()
        
        # 1. 删除 score_ledger 表中的今日评分记录
        cur.execute("""
        DELETE FROM score_ledger
        WHERE 
            tg_group_id=?
            AND DATE(created_at)=?
            AND action_type IN ('score', 'force_score')
        """, (tg_group_id, today))
        
        result["ledger_deleted"] = cur.rowcount
        
        # 2. 删除 daily_score_summary 表中的今日记录
        cur.execute("""
        DELETE FROM daily_score_summary
        WHERE date=? AND tg_group_id=?
        """, (today, tg_group_id))
        
        result["summary_deleted"] = cur.rowcount
        
        conn.commit()

    # 3. 删除强制统计备份文件
    backup_file = "data/force_stats_backup.json"
    if os.path.exists(backup_file):
        try:
            # 检查备份文件是否属于当前群组
            with open(backup_file, 'r', encoding='utf-8') as f:
                backup_data = json.load(f)
                if backup_data.get("tg_group_id") == tg_group_id:
                    os.remove(backup_file)
                    result["backup_deleted"] = 1
                    logger.info(f"🗑 删除群组 {tg_group_id} 的强制统计备份文件")
        except Exception as e:
            logger.error(f"处理备份文件失败: {e}")

    # 4. 清理内存中的强制统计缓存
    try:
        from features.score.handler import clear_force_stats_cache
        clear_force_stats_cache(tg_group_id)
    except ImportError:
        logger.warning("无法导入 clear_force_stats_cache，跳过内存缓存清理")

    logger.warning(
        f"✅ 今日数据已彻底清空 tg_group_id={tg_group_id}, "
        f"评分记录: {result['ledger_deleted']}条, "
        f"缓存记录: {result['summary_deleted']}条, "
        f"备份文件: {result['backup_deleted']}个"
    )
    
    return result


# ==========================================================
# 管理员操作：删除并重新创建所有评分相关的表
# ==========================================================

def drop_and_recreate_tables() -> Dict[str, bool]:
    """
    删除并重新创建所有评分相关的表
    注意：这会丢失所有历史数据！
    """
    result = {}
    
    try:
        with _get_conn() as conn:
            cur = conn.cursor()
            
            # 1. 删除 score_ledger 表
            cur.execute("DROP TABLE IF EXISTS score_ledger")
            result["score_ledger_dropped"] = True
            
            # 2. 删除 daily_score_summary 表
            cur.execute("DROP TABLE IF EXISTS daily_score_summary")
            result["daily_score_summary_dropped"] = True
            
            # 3. 重新创建表
            init_score_tables()
            result["tables_recreated"] = True
            
            conn.commit()
        
        logger.warning("⚠️  评分相关表已删除并重新创建，所有历史数据已丢失！")
        
    except Exception as e:
        logger.error(f"删除并重新创建表失败: {e}")
        result["error"] = str(e)
    
    return result


# ==========================================================
# 新增：检查消息是否已被评分（可选，用于调试）
# ==========================================================

def is_message_scored(tg_group_id: int, target_msg_id: int) -> bool:
    """
    检查消息是否已被评分
    可选功能，用于调试或信息展示
    """
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 1 FROM score_ledger
        WHERE
            tg_group_id=?
            AND target_msg_id=?
            AND action_type IN ('score', 'force_score')
        LIMIT 1
        """, (tg_group_id, target_msg_id))
        return cur.fetchone() is not None


# ==========================================================
# 新增：获取消息的评分历史
# ==========================================================

def get_message_score_history(tg_group_id: int, target_msg_id: int) -> List[Dict]:
    """
    获取消息的评分历史
    """
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 
            operator_name,
            score_delta,
            created_at,
            action_type
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND target_msg_id=?
            AND action_type IN ('score', 'force_score')
        ORDER BY created_at DESC
        """, (tg_group_id, target_msg_id))

        rows = cur.fetchall()

    history = []
    for row in rows:
        operator_name, score_delta, created_at, action_type = row
        
        # 处理operator_name
        if not operator_name or operator_name.strip() == "":
            display_name = "未知用户"
        elif operator_name.isdigit():
            display_name = f"用户{operator_name}"
        else:
            display_name = operator_name
            
        history.append({
            "operator": display_name,
            "score": score_delta,
            "time": created_at,
            "type": action_type
        })
    
    return history


# ==========================================================
# 新增：从备份恢复统计信息
# ==========================================================

def recover_stats_from_backup(tg_group_id: int, backup_data: dict) -> None:
    """
    从备份恢复统计信息
    用于当数据库统计失败时手动恢复
    """
    try:
        today = date.today().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        with _get_conn() as conn:
            cur = conn.cursor()
            
            # 清空今天的统计
            cur.execute("DELETE FROM daily_score_summary WHERE date=? AND tg_group_id=?", 
                       (today, tg_group_id))
            
            # 重新插入备份的统计
            for logical_group, operators in backup_data.get("detail", {}).items():
                group_total = sum(operators.values())
                cur.execute("""
                INSERT INTO daily_score_summary
                (date, tg_group_id, logical_group, total_score, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """, (today, tg_group_id, logical_group, group_total, now))
            
            conn.commit()
        
        logger.info(f"✅ 从备份恢复统计完成 tg_group_id={tg_group_id}")
    except Exception as e:
        logger.error(f"从备份恢复统计失败: {e}")
        raise


# ==========================================================
# 新增：获取所有评分记录（用于重建统计）
# ==========================================================

def get_all_today_scores(tg_group_id: int) -> List[Dict]:
    """
    获取今天的所有评分记录
    用于重建统计或验证数据一致性
    """
    today = date.today().strftime("%Y-%m-%d")
    
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT 
            logical_group,
            operator_name,
            score_delta,
            created_at,
            original_sender_name  -- ✅ 新增
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND action_type IN ('score', 'force_score')
            AND DATE(created_at)=?
        ORDER BY created_at ASC
        """, (tg_group_id, today))

        rows = cur.fetchall()

    scores = []
    for row in rows:
        group, operator, score, created_at, original_sender_name = row
        
        # 处理operator_name
        if not operator or operator.strip() == "":
            display_name = "未知用户"
        elif operator.isdigit():
            display_name = f"用户{operator}"
        else:
            display_name = operator
            
        scores.append({
            "group": group,
            "operator": display_name,
            "score": score,
            "time": created_at,
            "original_sender": original_sender_name or "未知用户"  # ✅ 新增
        })

    return scores


# ==========================================================
# 新增：修复旧的operator_name记录
# ==========================================================

def fix_operator_names():
    """
    修复数据库中旧的operator_name记录
    将数字ID转换为用户名格式
    """
    try:
        with _get_conn() as conn:
            cur = conn.cursor()
            
            # 获取所有operator_name是数字的记录
            cur.execute("""
            SELECT DISTINCT operator_name 
            FROM score_ledger 
            WHERE operator_name GLOB '[0-9]*' 
            AND LENGTH(operator_name) > 5
            """)
            
            numeric_names = cur.fetchall()
            
            for (name,) in numeric_names:
                if name.isdigit():
                    # 更新为"用户{ID}"格式
                    new_name = f"用户{name}"
                    cur.execute("""
                    UPDATE score_ledger 
                    SET operator_name = ? 
                    WHERE operator_name = ?
                    """, (new_name, name))
                    logger.info(f"✅ 修复operator_name: {name} -> {new_name}")
            
            conn.commit()
            logger.info("✅ operator_name修复完成")
            
    except Exception as e:
        logger.error(f"修复operator_names失败: {e}")


# ==========================================================
# 新增：获取群组评分统计（用于/report命令）
# ==========================================================

def get_group_statistics(tg_group_id: int) -> Dict[str, Dict]:
    """
    获取群组详细统计信息
    用于生成/report命令的报告
    返回：{
        "group_total": int,
        "group_stats": {
            "逻辑组名": {
                "total_score": int,
                "member_count": int,
                "members": [
                    {"username": str, "score": int}
                ]
            }
        }
    }
    """
    today = date.today().strftime("%Y-%m-%d")
    
    with _get_conn() as conn:
        cur = conn.cursor()
        
        # 获取群组总分
        cur.execute("""
        SELECT SUM(total_score)
        FROM daily_score_summary
        WHERE date=? AND tg_group_id=?
        """, (today, tg_group_id))
        
        group_total = cur.fetchone()[0] or 0
        
        # 获取详细统计
        cur.execute("""
        SELECT logical_group, original_sender_name, SUM(score_delta)
        FROM score_ledger
        WHERE
            tg_group_id=?
            AND action_type IN ('score', 'force_score')
            AND DATE(created_at)=?
        GROUP BY logical_group, original_sender_name
        ORDER BY logical_group, SUM(score_delta) DESC
        """, (tg_group_id, today))
        
        rows = cur.fetchall()
    
    # 组织数据
    result = {
        "group_total": group_total,
        "group_stats": {}
    }
    
    current_group = None
    group_data = None
    
    for group, original_sender, total in rows:
        if not original_sender:
            continue
        
        # 处理用户名
        if "组" not in original_sender:
            username = f"{original_sender}组"
        else:
            username = original_sender
        
        # 如果是新组
        if group != current_group:
            if group_data and current_group:
                result["group_stats"][current_group] = {
                    "total_score": sum(m["score"] for m in group_data["members"]),
                    "member_count": len(group_data["members"]),
                    "members": group_data["members"]
                }
            
            current_group = group
            group_data = {
                "members": []
            }
        
        # 添加成员
        group_data["members"].append({
            "username": username,
            "score": total
        })
    
    # 添加最后一组
    if group_data and current_group:
        result["group_stats"][current_group] = {
            "total_score": sum(m["score"] for m in group_data["members"]),
            "member_count": len(group_data["members"]),
            "members": group_data["members"]
        }
    
    return result


# ==========================================================
# 新增：获取被评分用户的详细信息
# ==========================================================

def get_scored_user_info(tg_group_id: int, target_msg_id: int) -> Optional[Dict]:
    """
    获取被评分用户的详细信息
    用于显示在"最近评分记录"中
    """
    with _get_conn() as conn:
        cur = conn.cursor()
        
        # 获取原始发送者ID和名称
        cur.execute("""
        SELECT original_sender_id, original_sender_name, created_at, score_delta
        FROM score_ledger
        WHERE tg_group_id=? AND target_msg_id=? 
        AND action_type IN ('score', 'force_score')
        ORDER BY created_at DESC
        LIMIT 1
        """, (tg_group_id, target_msg_id))
        
        row = cur.fetchone()
        
        if not row:
            return None
        
        original_sender_id, original_sender_name, created_at, score_delta = row
        
        # 使用保存的用户显示名称
        if original_sender_name and original_sender_name.strip():
            display_name = original_sender_name
        elif original_sender_id:
            display_name = f"用户{original_sender_id}"
        else:
            display_name = "未知用户"
        
        return {
            "user_id": original_sender_id,
            "user_name": original_sender_name,
            "time": created_at,
            "score": score_delta,
            "display_name": display_name
        }


# ==========================================================
# 新增：获取群组最近评分记录（简化版）
# ==========================================================

def get_group_recent_scores_simple(tg_group_id: int, limit: int = 5) -> List[Tuple]:
    """
    获取群组最近评分记录（简化版，返回元组）
    格式：(created_at, logical_group, score_delta, original_sender_name)
    """
    with _get_conn() as conn:
        cur = conn.cursor()
        cur.execute("""
        SELECT created_at, logical_group, score_delta, original_sender_name
        FROM score_ledger
        WHERE tg_group_id=? AND action_type IN ('score', 'force_score')
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """, (tg_group_id, limit))
        
        return cur.fetchall()


# ==========================================================
# 新增：添加缺失的列（兼容旧版本）
# ==========================================================

def add_missing_columns():
    """
    添加缺失的列到表中（用于升级兼容）
    """
    try:
        with _get_conn() as conn:
            cur = conn.cursor()
            
            # 检查 original_sender_name 列是否存在
            cur.execute("PRAGMA table_info(score_ledger)")
            columns = [col[1] for col in cur.fetchall()]
            
            if 'original_sender_name' not in columns:
                # 添加 missing columns
                cur.execute("ALTER TABLE score_ledger ADD COLUMN original_sender_name TEXT")
                logger.info("✅ 已添加 original_sender_name 列到 score_ledger 表")
            
            conn.commit()
            
    except Exception as e:
        logger.error(f"添加缺失列失败: {e}")