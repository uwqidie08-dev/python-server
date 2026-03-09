# diagnose_tables.py
import sqlite3
from config.settings import settings
import json

def diagnose_database(db_path, db_name):
    print(f"\n🔍 诊断数据库: {db_name} ({db_path})")
    print("=" * 60)
    
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # 1. 获取所有表
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = cur.fetchall()
        
        print(f"📋 表列表 ({len(tables)} 个):")
        for table in tables:
            table_name = table[0]
            
            # 2. 获取表结构
            cur.execute(f"PRAGMA table_info({table_name})")
            columns = cur.fetchall()
            
            # 3. 获取记录数
            cur.execute(f"SELECT COUNT(*) as count FROM {table_name}")
            count = cur.fetchone()[0]
            
            print(f"\n📊 表: {table_name} ({count} 条记录)")
            print("  列结构:")
            for col in columns:
                col_info = f"    {col['name']} ({col['type']})"
                if col['pk']:
                    col_info += " [主键]"
                if col['notnull']:
                    col_info += " [非空]"
                print(col_info)
            
            # 4. 显示部分数据（对于可能有提交数据的表）
            if count > 0 and count < 20:
                cur.execute(f"SELECT * FROM {table_name} LIMIT 3")
                rows = cur.fetchall()
                if rows:
                    print("  示例数据:")
                    for row in rows:
                        # 将行转换为字典
                        row_dict = dict(row)
                        # 只显示前几个字段
                        preview = {k: v for i, (k, v) in enumerate(row_dict.items()) if i < 3}
                        print(f"    {preview}")
            elif count >= 20:
                # 显示列名和数据类型
                cur.execute(f"SELECT * FROM {table_name} LIMIT 1")
                sample = cur.fetchone()
                if sample:
                    print("  数据示例（第一行）:")
                    for i, col_name in enumerate(sample.keys()):
                        value = sample[i]
                        if value is None:
                            continue
                        # 只显示字符串或数字的前50个字符
                        if isinstance(value, str):
                            display = value[:50] + ("..." if len(value) > 50 else "")
                        else:
                            display = str(value)
                        print(f"    {col_name}: {display}")
                        if i >= 2:  # 只显示前3列
                            print("    ...")
                            break

def main():
    print("🕵️ 数据库结构诊断工具")
    print("=" * 60)
    
    databases = [
        (settings.GROUP_ONE_DB, "群组一"),
        (settings.GROUP_TWO_DB, "群组二")
    ]
    
    for db_path, db_name in databases:
        diagnose_database(db_path, db_name)

if __name__ == "__main__":
    main()