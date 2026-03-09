# extract_numbers.py
import sqlite3
import re
import logging
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


def extract_numbers_from_backup():
    """从备份表中提取数字并更新到主表"""
    
    databases = [
        (settings.GROUP_ONE_DB, "群组一"),
        (settings.GROUP_TWO_DB, "群组二")
    ]
    
    updated_count = 0
    
    for db_path, group_name in databases:
        try:
            logger.info(f"📝 从备份表提取数字: {group_name}")
            
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # 检查是否有备份表
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_records_backup'")
                if not cur.fetchone():
                    logger.warning(f"没有找到备份表，跳过")
                    continue
                
                # 从备份表读取original_content
                cur.execute("""
                SELECT id, value, original_content 
                FROM old_records_backup 
                WHERE original_content IS NOT NULL AND original_content != ''
                """)
                
                updated = 0
                for row in cur.fetchall():
                    try:
                        backup_id = row['id']
                        value = row['value']
                        original_content = row['original_content']
                        
                        # 从original_content提取数字
                        number = 8  # 默认值
                        
                        if original_content:
                            # 按行分割
                            lines = original_content.strip().split('\n')
                            
                            # 方法1：找第二行数字
                            if len(lines) >= 2:
                                second_line = lines[1].strip()
                                if second_line.isdigit():
                                    number = int(second_line)
                                else:
                                    # 方法2：从整个内容中提取数字
                                    numbers = re.findall(r'\b\d+\b', original_content)
                                    if len(numbers) >= 2:
                                        number = int(numbers[1])
                            
                            # 更新主表
                            cur.execute("""
                            UPDATE records 
                            SET number = ? 
                            WHERE data = ? AND number = 8
                            """, (number, value))
                            
                            if cur.rowcount > 0:
                                updated += 1
                                
                    except Exception as e:
                        continue
                
                conn.commit()
                updated_count += updated
                logger.info(f"✅ 更新 {updated} 条记录的数字字段")
                
                # 显示统计
                cur.execute("SELECT number, COUNT(*) as count FROM records GROUP BY number ORDER BY count DESC LIMIT 5")
                stats = cur.fetchall()
                logger.info(f"数字分布: {[(row['number'], row['count']) for row in stats]}")
                
        except Exception as e:
            logger.error(f"提取数字失败 {group_name}: {e}")
    
    return updated_count


def main():
    print("=" * 60)
    print("🔢 从备份表提取数字信息")
    print("=" * 60)
    
    updated = extract_numbers_from_backup()
    
    print("\n" + "=" * 60)
    print(f"✅ 提取完成！更新了 {updated} 条记录的数字字段")
    print("=" * 60)


if __name__ == "__main__":
    main()