# features/admin/whitelist.py
import re
import logging
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.whitelist_db import (
    add_user_role,
    remove_user_role,
    get_users_by_role,
)

logger = logging.getLogger(__name__)

# ===============================
# 工具：提取用户 ID
# ===============================

def extract_user_ids(text: str) -> list[int]:
    """
    从文本中提取所有数字 user_id
    支持：
    - 空格
    - 换行
    - 逗号
    """
    ids = re.findall(r"\d+", text)
    return [int(x) for x in ids]


# ==================================================
# 普通白名单管理（同时添加 team 和 query 角色）
# ==================================================

async def wl_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /wl_add 123 456 789
    添加用户到普通白名单（同时获得提交权限和查询权限）
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以操作白名单")
        return

    args = update.message.text.split()[1:]  # 去掉命令本身
    if not args:
        await update.message.reply_text("❌ 请提供用户ID，例如：/wl_add 123 456")
        return
    
    ids = extract_user_ids(" ".join(args))
    if not ids:
        await update.message.reply_text("❌ 未检测到任何用户 ID")
        return

    team_success = 0
    query_success = 0
    
    for user_id in ids:
        try:
            # 添加 team 角色（提交权限）
            add_user_role(user_id, "team")
            team_success += 1
            
            # 添加 query 角色（查询权限）
            add_user_role(user_id, "query")
            query_success += 1
            
        except Exception as e:
            logger.error(f"添加用户到白名单失败: {user_id}, {e}")
    
    await update.message.reply_text(
        f"✅ 已添加 {len(ids)} 个用户到【普通白名单】\n"
        f"• 提交权限：{team_success} 个\n"
        f"• 查询权限：{query_success} 个"
    )


async def wl_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /wl_remove 123 456
    从普通白名单移除用户（同时移除提交权限和查询权限）
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以操作白名单")
        return

    args = update.message.text.split()[1:]
    if not args:
        await update.message.reply_text("❌ 请提供用户ID，例如：/wl_remove 123 456")
        return
    
    ids = extract_user_ids(" ".join(args))
    if not ids:
        await update.message.reply_text("❌ 未检测到任何用户 ID")
        return

    team_removed = 0
    query_removed = 0
    
    for user_id in ids:
        try:
            # 移除 team 角色
            affected = remove_user_role(user_id, "team")
            team_removed += affected
            
            # 移除 query 角色
            affected = remove_user_role(user_id, "query")
            query_removed += affected
            
        except Exception as e:
            logger.error(f"从白名单移除用户失败: {user_id}, {e}")
    
    await update.message.reply_text(
        f"🗑 已从【普通白名单】移除 {len(ids)} 个用户\n"
        f"• 提交权限：{team_removed} 个\n"
        f"• 查询权限：{query_removed} 个"
    )


async def wl_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /wl_list
    查看普通白名单用户（有提交权限的用户）
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以操作白名单")
        return

    users = get_users_by_role("team")
    if not users:
        await update.message.reply_text("📭 普通白名单(提交权限)为空")
        return

    text = "👥 普通白名单用户(提交权限)：\n"
    text += "\n".join(str(u) for u in users)
    
    # 可以同时显示哪些用户也有查询权限
    query_users = get_users_by_role("query")
    query_set = set(query_users)
    team_set = set(users)
    
    # 找出有提交权限但没有查询权限的用户
    no_query = [u for u in users if u not in query_set]
    if no_query:
        text += f"\n\n⚠️ 以下用户有提交权限但无查询权限：\n"
        text += "\n".join(str(u) for u in no_query)
    
    await update.message.reply_text(text)


# ==================================================
# 数据库调试命令
# ==================================================

async def debug_db(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /debug_db - 查看数据库状态
    """
    user = update.effective_user
    if user.id not in settings.ADMINS:
        await update.message.reply_text("❌ 只有管理员可以使用该命令")
        return
    
    try:
        from db.phone_db import phone_db
        
        # 获取数据库信息
        info = phone_db.get_table_info()
        
        text = "📊 数据库状态信息：\n\n"
        text += f"📁 表数量：{len(info['tables'])}\n"
        text += f"📋 表名：{', '.join(info['tables'])}\n\n"
        text += f"📝 phones 表记录数：{info['total_records']}\n\n"
        text += "📋 phones 表结构：\n"
        
        for col in info['phones_columns']:
            text += f"  • {col['name']} ({col['type']})"
            if col['pk']:
                text += " [主键]"
            if col['notnull']:
                text += " [非空]"
            text += "\n"
        
        await update.message.reply_text(text)
        
    except Exception as e:
        logger.error(f"获取数据库信息失败: {e}", exc_info=True)
        await update.message.reply_text(f"❌ 获取数据库信息失败：{str(e)}")