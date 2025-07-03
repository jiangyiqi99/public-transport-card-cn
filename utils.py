"""工具函数模块"""
import logging
from datetime import datetime
from typing import Dict, Optional

def setup_logging(level='INFO'):
    """设置日志配置"""
    logging.basicConfig(level=getattr(logging, level))
    return logging.getLogger(__name__)

def parse_date_time(date_bytes, time_bytes) -> str:
    """解析日期时间"""
    try:
        date_str = ''.join(f"{byte:02X}" for byte in date_bytes)
        time_str = ''.join(f"{byte:02X}" for byte in time_bytes)
        transaction_datetime = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
        return transaction_datetime.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return "未知日期时间"

def format_card_date(date_raw: str) -> str:
    """格式化卡片日期"""
    try:
        return datetime.strptime(date_raw, "%Y%m%d").strftime("%Y/%m/%d")
    except ValueError:
        return "无效日期"
