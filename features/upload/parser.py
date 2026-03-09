# features/upload/parser.py
import re
from typing import Set

DIGIT_13_RE = re.compile(r"\b\d{13}\b")


def extract_13_digits(text: str) -> Set[str]:
    """
    从文本中提取所有 13 位数字（自动去重）
    """
    return set(DIGIT_13_RE.findall(text))
