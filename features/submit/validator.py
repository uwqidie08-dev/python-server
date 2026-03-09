# features/submit/validator.py
import re
from typing import Tuple


# ===== 正则规则 =====

PHONE_11_RE = re.compile(r"^\d{11}$")
PHONE_13_RE = re.compile(r"^\d{13}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{12}$"
)


def validate_submission(lines: list[str]) -> Tuple[bool, str]:
    """
    校验两行提交格式

    返回：
    (True, "")               -> 合法
    (False, "错误原因")      -> 非法
    """
    if len(lines) != 2:
        return False, "❌ 提交格式错误：必须为两行"

    data, number = lines

    # 校验第二行必须是数字
    if not number.isdigit():
        return False, "❌ 第二行必须是数字"

    # 校验第一行数据格式
    if (
        PHONE_11_RE.fullmatch(data)
        or PHONE_13_RE.fullmatch(data)
        or EMAIL_RE.fullmatch(data)
        or UUID_RE.fullmatch(data)
    ):
        return True, ""

    return False, "❌ 第一行数据格式不支持"
