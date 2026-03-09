# features/reply123/finder.py
from typing import Optional, Tuple

from config.settings import settings
from db.group_db import group_one_db, group_two_db


def find_latest_message(data: str) -> Optional[Tuple[int, int]]:
    """
    在群组数据库的 records 表中查找 data 的最近一条消息

    返回：
    (group_id, message_id)
    或 None
    """
    # 使用 group_db 的 find_latest_by_data 方法
    result_one = group_one_db.find_latest_by_data(data)
    result_two = group_two_db.find_latest_by_data(data)

    if result_one and result_two:
        # 两个群都有，取 message_id 较新的（数字越大越新）
        if result_one[1] > result_two[1]:
            return result_one
        else:
            return result_two

    return result_one or result_two


def find_all_messages(data: str) -> list[Tuple[int, int]]:
    """
    查找所有群组中该数据的消息记录
    返回所有匹配的记录列表
    """
    results = []
    
    result_one = group_one_db.find_latest_by_data(data)
    if result_one:
        results.append(("群组一", result_one[0], result_one[1]))
    
    result_two = group_two_db.find_latest_by_data(data)
    if result_two:
        results.append(("群组二", result_two[0], result_two[1]))
    
    return results