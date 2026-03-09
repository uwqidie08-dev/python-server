# db/phone_db.py

import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple

from config.settings import settings

logger = logging.getLogger(__name__)

DB_PATH = settings.PHONE_DB


class PhoneDB:
    """
    手机号数据库（提交 / 查询 / 上传 共用）
    兼容旧版 phone_bot.db 结构
    支持后8位以上模糊匹配
    """

    def __init__(self):
        self._init_table()

    def _conn(self):
        return sqlite3.connect(DB_PATH)

    # ==================================================
    # 初始化表 - 兼容旧表结构
    # ==================================================
    def _init_table(self):
        with self._conn() as conn:
            cur = conn.cursor()
            
            try:
                # 首先检查表是否存在
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='phones'")
                table_exists = cur.fetchone()
                
                if not table_exists:
                    # 如果表不存在，创建新表
                    cur.execute("""
                    CREATE TABLE phones (
                        number TEXT PRIMARY KEY,
                        upload_time TEXT,
                        last_query_time TEXT,
                        created_at TEXT
                    )
                    """)
                    logger.info("创建新表 phones")
                else:
                    # 如果表已存在，检查列结构并动态添加缺失的列
                    self._add_missing_columns(cur)
                    
                conn.commit()
                logger.info("phone_db 表结构初始化完成")
            except Exception as e:
                logger.error(f"初始化表结构失败: {e}")
                conn.rollback()
                raise

    def _add_missing_columns(self, cur):
        """动态添加缺失的列"""
        # 获取当前表的所有列
        cur.execute("PRAGMA table_info(phones)")
        columns = cur.fetchall()
        existing_columns = [col[1] for col in columns]
        
        # 需要确保存在的列
        required_columns = ['number', 'upload_time', 'last_query_time', 'created_at']
        
        for column in required_columns:
            if column not in existing_columns:
                if column == 'number':
                    # number 是主键，如果不存在说明表结构有问题
                    logger.error("表 phones 缺少主键列 number")
                    continue
                    
                # 添加缺失的列
                try:
                    cur.execute(f"ALTER TABLE phones ADD COLUMN {column} TEXT")
                    logger.info(f"添加列 {column} 到 phones 表")
                    
                    # 如果是 upload_time 或 created_at 列，为现有记录设置默认值
                    if column in ['upload_time', 'created_at']:
                        default_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        cur.execute(f"UPDATE phones SET {column} = ? WHERE {column} IS NULL", 
                                  (default_time,))
                        logger.info(f"为现有记录设置 {column} 默认值")
                        
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        logger.warning(f"列 {column} 可能已存在")
                    else:
                        logger.error(f"添加列 {column} 失败: {e}")

    # ==================================================
    # TXT 批量导入（upload 用）- 更健壮的版本
    # ==================================================
    def insert_numbers(self, numbers: List[str], clean_days: int = 7) -> Dict[str, int]:
        """
        批量插入号码并清理旧数据
        
        返回：{
            "inserted": x,      # 成功添加
            "duplicate": y,     # 重复跳过
            "invalid": z,       # 无效格式
            "cleaned": c,       # 清理旧数据
            "total": t          # 数据库现有总数
        }
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        inserted = 0
        duplicate = 0
        invalid = 0
        cleaned = 0

        with self._conn() as conn:
            cur = conn.cursor()
            
            # 在批量插入前再次确保表结构正确
            try:
                self._ensure_table_columns(cur)
            except Exception as e:
                logger.error(f"确保表结构失败: {e}")
                return {
                    "inserted": 0, 
                    "duplicate": 0, 
                    "invalid": len(numbers),
                    "cleaned": 0,
                    "total": self.count_all(),
                    "error": str(e)
                }
            
            # 步骤1：清理7天前的旧数据
            cleaned = self._clean_old_data(cur, clean_days)
            
            # 步骤2：批量插入新数据
            for num in numbers:
                try:
                    # 验证数据格式（只接受13位数字）
                    if not self._is_valid_number(num):
                        invalid += 1
                        continue
                    
                    # 检查号码是否已存在
                    cur.execute("SELECT 1 FROM phones WHERE number=?", (num,))
                    if cur.fetchone():
                        duplicate += 1
                        continue
                    
                    # 插入新号码
                    cur.execute(
                        "INSERT INTO phones (number, upload_time, created_at) VALUES (?, ?, ?)",
                        (num, now, now)
                    )
                    inserted += 1
                    
                except sqlite3.IntegrityError:
                    duplicate += 1
                except sqlite3.OperationalError as e:
                    # 如果出现列不存在的错误，尝试修复并重试
                    if "no column named" in str(e):
                        logger.warning(f"检测到列缺失错误，尝试修复: {e}")
                        try:
                            # 重新检查并添加缺失的列
                            self._add_missing_columns(cur)
                            # 重新尝试插入
                            cur.execute(
                                "INSERT INTO phones (number, upload_time, created_at) VALUES (?, ?, ?)",
                                (num, now, now)
                            )
                            inserted += 1
                        except Exception as retry_error:
                            logger.error(f"重试插入失败 {num}: {retry_error}")
                            invalid += 1
                    else:
                        logger.error(f"插入号码失败 {num}: {e}")
                        invalid += 1
                except Exception as e:
                    logger.error(f"插入号码失败 {num}: {e}")
                    invalid += 1
            
            conn.commit()

        total = self.count_all()
        
        logger.info(
            f"批量插入完成: "
            f"插入 {inserted} 条, "
            f"重复 {duplicate} 条, "
            f"无效 {invalid} 条, "
            f"清理 {cleaned} 条, "
            f"总计 {total} 条"
        )
        
        return {
            "inserted": inserted,
            "duplicate": duplicate,
            "invalid": invalid,
            "cleaned": cleaned,
            "total": total
        }
    
    def _is_valid_number(self, num: str) -> bool:
        """
        验证号码格式
        目前只接受13位数字
        """
        # 去除空格和特殊字符
        num = num.strip()
        
        # 检查是否是13位数字
        if len(num) == 13 and num.isdigit():
            return True
        
        return False
    
    def _clean_old_data(self, cur, days: int = 7) -> int:
        """
        清理指定天数前的旧数据
        返回清理的记录数
        """
        try:
            # 计算截止日期
            cutoff_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            
            # 删除旧数据
            cur.execute("DELETE FROM phones WHERE upload_time < ?", (cutoff_date,))
            cleaned = cur.rowcount
            
            if cleaned > 0:
                logger.info(f"清理 {days} 天前的旧数据: {cleaned} 条")
            
            return cleaned
            
        except Exception as e:
            logger.error(f"清理旧数据失败: {e}")
            return 0
    
    def _ensure_table_columns(self, cur):
        """确保表有必要的列"""
        cur.execute("PRAGMA table_info(phones)")
        columns = cur.fetchall()
        existing_columns = [col[1] for col in columns]
        
        # 检查必要列是否存在
        required_columns = ['number', 'upload_time', 'last_query_time', 'created_at']
        missing_columns = [col for col in required_columns if col not in existing_columns]
        
        if missing_columns:
            logger.warning(f"发现缺失的列: {missing_columns}")
            for column in missing_columns:
                if column != 'number':  # number 是主键，不能动态添加
                    try:
                        cur.execute(f"ALTER TABLE phones ADD COLUMN {column} TEXT")
                        logger.info(f"动态添加列: {column}")
                    except Exception as e:
                        logger.error(f"动态添加列 {column} 失败: {e}")

    # ==================================================
    # 查询号码（query 用）- 支持模糊匹配
    # ==================================================
    def query_number(self, query_str: str) -> Tuple[int, Optional[Dict]]:
        """
        查询号码，支持后8位以上模糊匹配
        
        返回：(状态码, 数据字典)
        状态码：
        1 = 首次查询
        2 = 不存在
        3 = 已被查询过
        
        数据字典包含：
        - full_number: 完整号码
        - upload_time: 上传时间
        - last_query_time: 上次查询时间
        """
        if not query_str.isdigit() or len(query_str) < 8:
            return 2, None
        
        try:
            with self._conn() as conn:
                cur = conn.cursor()
                
                # 优先尝试精确匹配
                cur.execute(
                    "SELECT number, upload_time, last_query_time FROM phones WHERE number=?",
                    (query_str,)
                )
                exact_match = cur.fetchone()
                
                if exact_match:
                    # 精确匹配找到
                    full_number, upload_time, last_query_time = exact_match
                    
                    if last_query_time is None:
                        # 首次查询，更新查询时间
                        self._update_query_time(full_number)
                        return 1, {
                            "full_number": full_number,
                            "upload_time": upload_time,
                            "last_query_time": None
                        }
                    else:
                        # 已被查询过
                        return 3, {
                            "full_number": full_number,
                            "upload_time": upload_time,
                            "last_query_time": last_query_time
                        }
                
                # 如果没有精确匹配，尝试模糊匹配（后8位以上）
                if len(query_str) >= 8:
                    # 构建模糊查询：以查询字符串结尾的号码
                    fuzzy_pattern = f"%{query_str}"
                    cur.execute(
                        "SELECT number, upload_time, last_query_time FROM phones WHERE number LIKE ?",
                        (fuzzy_pattern,)
                    )
                    fuzzy_matches = cur.fetchall()
                    
                    if fuzzy_matches:
                        # 取第一个匹配结果（最长的匹配）
                        # 按号码长度排序，取最长的（最完整的）号码
                        fuzzy_matches.sort(key=lambda x: len(x[0]), reverse=True)
                        full_number, upload_time, last_query_time = fuzzy_matches[0]
                        
                        if last_query_time is None:
                            # 首次查询，更新查询时间
                            self._update_query_time(full_number)
                            return 1, {
                                "full_number": full_number,
                                "upload_time": upload_time,
                                "last_query_time": None,
                                "query_match": query_str,
                                "full_match": full_number
                            }
                        else:
                            # 已被查询过
                            return 3, {
                                "full_number": full_number,
                                "upload_time": upload_time,
                                "last_query_time": last_query_time,
                                "query_match": query_str,
                                "full_match": full_number
                            }
                
                # 没有找到匹配
                return 2, None
                
        except sqlite3.OperationalError as e:
            if "no column named" in str(e):
                logger.warning(f"列缺失错误，尝试修复后重试: {e}")
                # 尝试修复表结构
                with self._conn() as conn:
                    cur = conn.cursor()
                    self._add_missing_columns(cur)
                return self.query_number(query_str)  # 重试
            raise

    def _update_query_time(self, number: str):
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with self._conn() as conn:
            conn.execute(
                "UPDATE phones SET last_query_time=? WHERE number=?",
                (now, number)
            )
            conn.commit()

    # ==================================================
    # 获取总记录数
    # ==================================================
    def count_all(self) -> int:
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM phones")
            return cur.fetchone()[0]
    
    # ==================================================
    # 获取数据库信息（调试用）
    # ==================================================
    def get_table_info(self) -> Dict:
        """获取表结构信息，用于调试"""
        with self._conn() as conn:
            cur = conn.cursor()
            
            # 获取所有表
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            
            # 获取 phones 表结构
            cur.execute("PRAGMA table_info(phones)")
            columns = cur.fetchall()
            
            # 获取记录数
            cur.execute("SELECT COUNT(*) FROM phones")
            count = cur.fetchone()[0]
            
            return {
                "tables": [t[0] for t in tables],
                "phones_columns": [
                    {"name": col[1], "type": col[2], "notnull": col[3], "default": col[4], "pk": col[5]}
                    for col in columns
                ],
                "total_records": count
            }
    
    # ==================================================
    # 手动清理旧数据（管理员命令用）
    # ==================================================
    def clean_old_data_manual(self, days: int = 7) -> Dict[str, int]:
        """
        手动清理旧数据
        返回清理统计
        """
        with self._conn() as conn:
            cur = conn.cursor()
            
            # 获取清理前的记录数
            cur.execute("SELECT COUNT(*) FROM phones")
            before_count = cur.fetchone()[0]
            
            # 执行清理
            cleaned = self._clean_old_data(cur, days)
            
            # 获取清理后的记录数
            cur.execute("SELECT COUNT(*) FROM phones")
            after_count = cur.fetchone()[0]
            
            conn.commit()
            
            return {
                "before": before_count,
                "after": after_count,
                "cleaned": cleaned,
                "remaining": after_count
            }


# ✅ 全局唯一实例（所有地方都 import 这个）
phone_db = PhoneDB()