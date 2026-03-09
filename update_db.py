# update_db.py
import sqlite3
import sys
import os

# 添加项目根目录到Python路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from config.settings import settings
except ImportError:
    print("❌ 无法导入settings，请确保在项目根目录运行此脚本")
    print("📁 当前目录:", os.getcwd())
    sys.exit(1)

def add_missing_columns():
    """添加缺失的列到数据库中"""
    db_path = settings.SCORE_DB
    
    print(f"🔍 正在检查数据库: {db_path}")
    print(f"📁 数据库文件是否存在: {os.path.exists(db_path)}")
    
    if not os.path.exists(db_path):
        print("❌ 数据库文件不存在，请先启动机器人创建数据库")
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            
            # 检查列是否存在
            cur.execute('PRAGMA table_info(score_ledger)')
            columns_info = cur.fetchall()
            columns = [col[1] for col in columns_info]
            
            print(f"📋 当前表结构:")
            for col in columns_info:
                print(f"   - {col[1]} ({col[2]})")
            
            # 检查是否需要添加 original_sender_name 列
            if 'original_sender_name' not in columns:
                print("\n🔄 正在添加 original_sender_name 列...")
                try:
                    cur.execute('ALTER TABLE score_ledger ADD COLUMN original_sender_name TEXT')
                    conn.commit()
                    print("✅ original_sender_name 列添加成功！")
                except sqlite3.OperationalError as e:
                    if "duplicate column name" in str(e):
                        print("⚠️  列已存在（忽略重复错误）")
                    else:
                        print(f"❌ 添加列时出错: {e}")
                        return
            else:
                print("\n✅ original_sender_name 列已存在")
            
            # 检查表结构
            cur.execute('PRAGMA table_info(score_ledger)')
            updated_columns = cur.fetchall()
            
            print(f"\n📋 更新后的表结构:")
            for col in updated_columns:
                print(f"   - {col[1]} ({col[2]})")
            
            # 检查是否有数据
            cur.execute("SELECT COUNT(*) FROM score_ledger")
            count = cur.fetchone()[0]
            print(f"\n📊 表中现有记录数: {count}")
            
            if count > 0:
                # 显示一些示例数据
                print("\n📝 示例数据（前5条）:")
                cur.execute("""
                SELECT id, created_at, logical_group, operator_name, 
                       original_sender_id, original_sender_name, score_delta
                FROM score_ledger 
                ORDER BY created_at DESC 
                LIMIT 5
                """)
                
                for row in cur.fetchall():
                    id, created_at, logical_group, operator_name, sender_id, sender_name, score = row
                    print(f"   - ID:{id} [{created_at[11:19]}] {logical_group}")
                    print(f"     操作员: {operator_name}")
                    print(f"     发送者ID: {sender_id}")
                    print(f"     发送者名称: {sender_name or 'NULL'}")
                    print(f"     分数: {score:+}")
                    print()
            
    except sqlite3.Error as e:
        print(f"❌ 数据库错误: {e}")
    except Exception as e:
        print(f"❌ 未知错误: {e}")

def check_other_tables():
    """检查其他表的结构"""
    db_path = settings.SCORE_DB
    
    if not os.path.exists(db_path):
        return
    
    try:
        with sqlite3.connect(db_path) as conn:
            cur = conn.cursor()
            
            # 获取所有表
            cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cur.fetchall()
            
            print(f"\n📁 数据库中的所有表:")
            for table in tables:
                table_name = table[0]
                print(f"\n🔹 {table_name}:")
                
                # 获取表结构
                cur.execute(f"PRAGMA table_info({table_name})")
                columns = cur.fetchall()
                
                for col in columns:
                    col_name = col[1]
                    col_type = col[2]
                    not_null = "NOT NULL" if col[3] else ""
                    pk = "PRIMARY KEY" if col[5] else ""
                    print(f"   - {col_name} ({col_type}) {not_null} {pk}")
                
    except Exception as e:
        print(f"❌ 检查表结构时出错: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("📊 数据库更新工具")
    print("=" * 60)
    
    add_missing_columns()
    check_other_tables()
    
    print("\n" + "=" * 60)
    print("✅ 数据库检查完成")
    print("=" * 60)