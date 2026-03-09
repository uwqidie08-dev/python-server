# fix_records_table.py
import sqlite3
import logging
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(message)s",
)

logger = logging.getLogger(__name__)


def fix_table_structure():
    """修复records表结构，将旧字段名改为新字段名"""
    
    databases = [
        (settings.GROUP_ONE_DB, "群组一"),
        (settings.GROUP_TWO_DB, "群组二")
    ]
    
    for db_path, group_name in databases:
        try:
            logger.info(f"🔧 修复 {group_name} 表结构...")
            
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                
                # 1. 检查当前表结构
                cur.execute("PRAGMA table_info(records)")
                columns = cur.fetchall()
                column_names = [col['name'] for col in columns]
                
                logger.info(f"当前表字段: {column_names}")
                
                # 2. 如果表是旧结构（有value字段但没有data字段）
                if 'value' in column_names and 'data' not in column_names:
                    logger.info(f"检测到旧表结构，开始修复...")
                    
                    # 创建新表
                    cur.execute("""
                    CREATE TABLE IF NOT EXISTS records_new (
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
                    
                    # 从旧表复制数据
                    cur.execute("""
                    INSERT INTO records_new (id, data, number, user_id, username, group_id, message_id, created_at)
                    SELECT 
                        id,
                        value as data,  -- 将value重命名为data
                        8 as number,    -- 默认值
                        user_id,
                        username,
                        -1002934657245 as group_id,  -- 群组ID（稍后修正）
                        0 as message_id,              -- 默认值
                        time as created_at
                    FROM records
                    """)
                    
                    # 删除旧表
                    cur.execute("DROP TABLE records")
                    
                    # 重命名新表
                    cur.execute("ALTER TABLE records_new RENAME TO records")
                    
                    logger.info(f"✅ 表结构修复完成")
                    
                elif 'data' in column_names:
                    logger.info(f"✅ 表已经是新结构，无需修复")
                    
                    # 确保其他字段都存在
                    missing_fields = []
                    required_fields = ['number', 'group_id', 'message_id']
                    
                    for field in required_fields:
                        if field not in column_names:
                            missing_fields.append(field)
                    
                    if missing_fields:
                        logger.info(f"添加缺失字段: {missing_fields}")
                        
                        # 添加缺失字段
                        if 'number' in missing_fields:
                            cur.execute("ALTER TABLE records ADD COLUMN number INTEGER DEFAULT 8")
                        
                        if 'group_id' in missing_fields:
                            # 根据数据库路径设置群组ID
                            if "group_one" in db_path or "group_one" in db_path.lower():
                                group_id = settings.GROUP_ONE_ID
                            else:
                                group_id = settings.GROUP_TWO_ID
                            cur.execute(f"ALTER TABLE records ADD COLUMN group_id INTEGER DEFAULT {group_id}")
                        
                        if 'message_id' in missing_fields:
                            cur.execute("ALTER TABLE records ADD COLUMN message_id INTEGER DEFAULT 0")
                    
                else:
                    logger.warning(f"未知的表结构")
                
                # 3. 更新群组ID（根据数据库）
                if 'group_one' in db_path or str(settings.GROUP_ONE_ID) in db_path:
                    group_id = settings.GROUP_ONE_ID
                else:
                    group_id = settings.GROUP_TWO_ID
                
                cur.execute(f"UPDATE records SET group_id = {group_id} WHERE group_id != {group_id} OR group_id IS NULL")
                
                # 4. 生成message_id（如果没有）
                cur.execute("UPDATE records SET message_id = id * 1000 WHERE message_id = 0 OR message_id IS NULL")
                
                conn.commit()
                
                # 5. 显示修复结果
                cur.execute("SELECT COUNT(*) FROM records")
                count = cur.fetchone()[0]
                
                cur.execute("PRAGMA table_info(records)")
                new_columns = [col['name'] for col in cur.fetchall()]
                
                logger.info(f"修复后: {count} 条记录，字段: {new_columns}")
                
        except Exception as e:
            logger.error(f"修复 {group_name} 失败: {e}")


def check_data_quality():
    """检查数据质量"""
    
    databases = [
        (settings.GROUP_ONE_DB, "群组一"),
        (settings.GROUP_TWO_DB, "群组二")
    ]
    
    print("\n" + "=" * 60)
    print("📊 数据质量检查")
    print("=" * 60)
    
    for db_path, group_name in databases:
        try:
            with sqlite3.connect(db_path) as conn:
                cur = conn.cursor()
                
                # 总记录数
                cur.execute("SELECT COUNT(*) FROM records")
                total = cur.fetchone()[0]
                
                # 有数据的记录数
                cur.execute("SELECT COUNT(*) FROM records WHERE data IS NOT NULL AND data != ''")
                with_data = cur.fetchone()[0]
                
                # 有用户名的记录数
                cur.execute("SELECT COUNT(*) FROM records WHERE username IS NOT NULL AND username != ''")
                with_username = cur.fetchone()[0]
                
                # 有时间戳的记录数
                cur.execute("SELECT COUNT(*) FROM records WHERE created_at IS NOT NULL AND created_at != ''")
                with_time = cur.fetchone()[0]
                
                print(f"\n{group_name}:")
                print(f"  总记录数: {total}")
                print(f"  有数据: {with_data} ({with_data/total*100:.1f}%)")
                print(f"  有用户名: {with_username} ({with_username/total*100:.1f}%)")
                print(f"  有时间戳: {with_time} ({with_time/total*100:.1f}%)")
                
                # 显示前3条记录
                if total > 0:
                    print(f"\n  示例记录:")
                    cur.execute("SELECT id, data, username, created_at FROM records LIMIT 3")
                    for row in cur.fetchall():
                        print(f"    ID:{row[0]} 数据:{row[1][:20]}... 用户:{row[2]} 时间:{row[3]}")
                
        except Exception as e:
            print(f"{group_name}: 检查失败 - {e}")


def main():
    print("=" * 60)
    print("🔧 修复records表结构")
    print("=" * 60)
    
    # 修复表结构
    fix_table_structure()
    
    # 检查数据质量
    check_data_quality()
    
    print("\n" + "=" * 60)
    print("✅ 修复完成！")
    print("=" * 60)
    print("💡 现在records表有正确的结构，可以用于:")
    print("  1. 123定位功能")
    print("  2. 历史数据查询")
    print("  3. 数据去重检查")


if __name__ == "__main__":
    main()