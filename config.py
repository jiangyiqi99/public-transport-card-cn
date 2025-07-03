"""常量定义模块"""

# 支持的AID列表
SUPPORTED_AIDS = [
    ("A000000632010105", "主要AID"),
    ("A000000632010106", "备选AID")
]

# 交易类型映射
TRANSACTION_TYPES = {
    0x09: "地铁",
    0x02: "充值",
    0x06: "公交",
    0x05: "消费"
}

# 默认配置
DEFAULT_CONFIG = {
    'max_records': 20,
    'possible_sfis': [24, 21, 18, 15, 3, 2],
    'log_level': 'INFO'
}

# UI配置
UI_CONFIG = {
    'window_title': "智能卡信息读取器",
    'window_size': "800x700",
    'column_widths': {
        "序号": 50,
        "时间": 150,
        "金额(元)": 80,
        "类型": 80,
        "详细信息": 120
    }
}

"""配置管理模块"""
from config import DEFAULT_CONFIG


class ConfigManager:
    """配置管理器"""

    @classmethod
    def get_config(cls):
        """获取配置"""
        return DEFAULT_CONFIG.copy()

