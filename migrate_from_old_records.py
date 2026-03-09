# migrate_from_old_records.py
import sqlite3
import logging
import re
from datetime import datetime
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def extract_number_from_content(original_content):
    """从original_content中提取数字（第二行）"""
    if not original_content:
        return 0
    
    try:
        # 按行分割
        lines = original_content.strip().split('\n')
        if len(lines) >= 2:
            # 取第二行
            second_line = lines[1].strip()
            if second_line.isdigit():
                return int(second_line)
        
        # 尝试从文本中提取数字
        numbers = re.findall(r'\b\d+\b', original_content)
        if len(numbers) >= 2:
            # 取第二个数字
            return int(numbers[1])
        
        return 0
    except:
        return 0


def migrate_old_records(db_path, group_id, group_name):
    """从旧的records表迁移数据到新的records表"""
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            
            # 1. 检查旧的records表是否存在
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='records'")
            if not cur.fetchone():
                logger.warning(f"{group_name} 没有旧的records表")
                return 0
            
            # 2. 获取旧的records表中的所有记录
            cur.execute("""
            SELECT id, value, type, user_id, username, time, original_content, group_message_id
            FROM records
            WHERE value IS NOT NULL AND value != ''
            ORDER BY time ASC
            """)
            
            old_records = cur.fetchall()
            logger.info(f"{group_name} 找到 {len(old_records)} 条历史记录")
            
            if not old_records:
                return 0
            
            # 3. 迁移数据
            migrated = 0
            skipped = 0
            
            for row in old_records:
                try:
                    # 提取数据
                    data = row['value']
                    
                    # 从original_content中提取数字（第二行）
                    number = extract_number_from_content(row.get('original_content', ''))
                    
                    # 如果没有提取到数字，使用一个默认值
                    if number == 0:
                        # 根据数据类型使用不同的默认值
                        if row['type'] == '手机号':
                            number = 8  # 默认值
                        elif row['type'] == '13位数字':
                            number = 14  # 默认值
                        else:
                            number = 8
                    
                    user_id = row['user_id']
                    username = row['username']
                    created_at = row['time']
                    
                    # 使用原始的group_message_id（如果存在）
                    message_id = row.get('group_message_id', 0)
                    if message_id == 0 or message_id is None:
                        # 生成伪消息ID
                        message_id = abs(row['id'] * 1000 + hash(str(created_at)) % 1000)
                    
                    # 插入到新的records表
                    cur.execute("""
                    INSERT OR IGNORE INTO new_records 
                    (data, number, user_id, username, group_id, message_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (
                        str(data),
                        int(number),
                        int(user_id),
                        str(username),
                        group_id,
                        abs(message_id),
                        str(created_at)
                    ))
                    
                    if cur.rowcount > 0:
                        migrated += 1
                    else:
                        skipped += 1
                        
                except Exception as e:
                    logger.warning(f"迁移记录失败 (id={row['id']}): {e}")
                    skipped += 1
            
            conn.commit()
            logger.info(f"{group_name} 迁移 {migrated} 条记录，跳过 {skipped} 条")
            return migrated
            
    except Exception as e:
        logger.error(f"迁移 {group_name} 失败: {e}")
        return 0


def create_backup_table(db_path, group_name):
    """创建备份表来保存旧的records数据"""
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            
            # 检查是否已有备份表
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='old_records_backup'")
            if cur.fetchone():
                logger.info(f"{group_name} 已有备份表，跳过创建")
                return
            
            # 创建备份表
            cur.execute("""
            CREATE TABLE old_records_backup AS 
            SELECT * FROM records
            """)
            
            # 添加索引以便快速查找
            cur.execute("CREATE INDEX idx_backup_value ON old_records_backup(value)")
            cur.execute("CREATE INDEX idx_backup_time ON old_records_backup(time)")
            
            conn.commit()
            logger.info(f"{group_name} 创建备份表成功")
            
    except Exception as e:
        logger.error(f"{group_name} 创建备份表失败: {e}")


def main():
    """主迁移函数"""
    logger.info("🚀 开始从旧records表迁移历史数据...")
    
    databases = [
        (settings.GROUP_ONE_DB, settings.GROUP_ONE_ID, "群组一"),
        (settings.GROUP_TWO_DB, settings.GROUP_TWO_ID, "群组二")
    ]
    
    total_migrated = 0
    
    for db_path, group_id, group_name in databases:
        try:
            logger.info(f"\n📊 处理 {group_name}: {db_path}")
            
            # 1. 创建备份表
            create_backup_table(db_path, group_name)
            
            # 2. 重命名现有的新records表（避免冲突）
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                
                # 检查是否有我们创建的新records表
                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='new_records'")
                if cur.fetchone():
                    # 删除现有的新表
                    cur.execute("DROP TABLE IF EXISTS new_records")
                    logger.info(f"{group_name} 删除现有的new_records表")
                
                # 重命名当前的records表（我们创建的）为new_records
                cur.execute("ALTER TABLE records RENAME TO new_records")
                logger.info(f"{group_name} 重命名records表为new_records")
                
                conn.commit()
            
            # 3. 从旧的records表（现在应该是old_records_backup）迁移数据
            migrated = migrate_old_records(db_path, group_id, group_name)
            total_migrated += migrated
            
            # 4. 统计结果
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                
                # 统计new_records表（新数据）
                cur.execute("SELECT COUNT(*) FROM new_records")
                new_count = cur.fetchone()[0]
                
                # 统计备份表（旧数据）
                cur.execute("SELECT COUNT(*) FROM old_records_backup")
                old_count = cur.fetchone()[0]
                
                logger.info(f"{group_name} 迁移结果: 新表 {new_count} 条，备份表 {old_count} 条")
                
        except Exception as e:
            logger.error(f"处理 {group_name} 失败: {e}")
    
    logger.info(f"🎉 迁移完成！总共迁移 {total_migrated} 条历史记录")
    
    # 显示最终统计
    print("\n" + "=" * 60)
    print("📊 最终统计")
    print("=" * 60)
    
    for db_path, _, group_name in databases:
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                
                # 检查new_records表
                cur.execute("SELECT COUNT(*) FROM new_records")
                new_count = cur.fetchone()[0]
                
                # 检查备份表
                cur.execute("SELECT COUNT(*) FROM old_records_backup")
                backup_count = cur.fetchone()[0]
                
                print(f"{group_name}:")
                print(f"  新records表: {new_count} 条记录")
                print(f"  旧数据备份表: {backup_count} 条记录")
                
        except Exception as e:
            print(f"{group_name}: 查询失败 - {e}")


if __name__ == "__main__":
    main()