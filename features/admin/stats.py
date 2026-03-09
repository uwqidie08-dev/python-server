# features/admin/stats.py
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from db.whitelist_db import has_role


async def handle_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stats - 显示使用说明
    任何白名单用户或管理员都可以使用
    """
    user = update.effective_user
    if not user:
        return
    
    user_id = user.id
    
    # 检查权限：管理员、普通白名单、评分白名单中的任意一种
    is_admin = user_id in settings.ADMINS
    has_team_role = has_role(user_id, "team")
    has_scorer_role = has_role(user_id, "scorer")
    has_query_role = has_role(user_id, "query")
    
    if not (is_admin or has_team_role or has_scorer_role or has_query_role):
        await update.message.reply_text("❌ 你没有权限查看使用说明")
        return
    
    stats_text = """🤖 使用说明：

📱 **团队数据提交（普通白名单）：**
格式：
第一行：数据（支持：11位数字/13位数字/邮箱/UUID）
第二行：数字

数据格式示例：
• 手机号：13800138000
• 13位数字：8613800138000
• 邮箱：test@example.com
• UUID：c398b651-e7fe-430b-b1f3-d046b06a22e3

规则：
- 第二行 < 14 → 群组一（重复则取消）
- 第二行 ≥ 14 → 群组二（显示重复记录）
- 5分钟内相同数据只能提交一次

🔍 **数据查询（普通白名单）：**
- 发送 8-13 位数字进行查询
- 查询结果：
  1 - 首次查询（显示上传时间）
  2 - 数字不存在
  3 - 已被查询过（显示上次查询时间）

🔄 **回复123：**（普通白名单）
格式：123 数据
示例：123 13800138000
      123 test@example.com
      123 c398b651-e7fe-430b-b1f3-d046b06a22e3

📤 **TXT文件上传（评分白名单专用）：**
- 直接发送TXT文件给机器人
- 自动提取13位数字并上传到查询数据库
- 只有评分白名单和管理员可以使用此功能

📊 **管理员命令（管理员自动拥有全部功能权限）：**
/report - 今日统计（按组别分组）
/clear_today - 清空分数

👥 **普通白名单管理：**
/wl_add - 批量添加用户到普通白名单
/wl_remove - 从普通白名单移除用户
/wl_list - 列出普通白名单用户

🔐 **评分白名单管理：**
/score_add - 批量添加用户到评分白名单
/score_remove - 批量从评分白名单移除用户
/score_list - 列出评分白名单用户"""

    await update.message.reply_text(stats_text)