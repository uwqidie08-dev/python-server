# utils/extract.py
import re
import logging

logger = logging.getLogger(__name__)


def extract_logical_group(text: str) -> str:
    """
    从消息文本中提取逻辑分组名

    规则（严格按你的说明）：
    1. 如果包含“XX组” → 返回“XX组”（组字前面 2 个字）
       例：
         世豪组 X34   → 世豪组
         A2♐️阿光组  → 阿光组
         七条组 Q15  → 七条组
         李四组王五  → 李四组

    2. 如果不包含“组”字 → 归为“其他组”

    3. 默认兜底：世豪组（仅用于异常情况）
    """
    try:
        if not text:
            return "世豪组"

        # 匹配“任意两个字符 + 组”
        # 使用非贪婪，避免表情/前缀干扰
        match = re.search(r"(.{2})组", text)
        if match:
            return f"{match.group(1)}组"

        # 不包含“组”字
        return "其他组"

    except Exception as e:
        logger.error(f"提取逻辑分组失败: {e}")
        return "世豪组"
