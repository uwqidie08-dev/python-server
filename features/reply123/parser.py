# features/reply123/parser.py
from typing import Optional


def parse_reply123(text: str) -> Optional[str]:
    """
    解析 123 指令

    正确格式：
    123 <data>

    返回：
    - data（字符串）
    - None（格式不匹配）
    """
    text = text.strip()

    if not text.startswith("123 "):
        return None

    data = text[4:].strip()
    if not data:
        return None

    return data
