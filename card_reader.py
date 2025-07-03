"""智能卡读取器模块"""
from smartcard.util import toHexString, toBytes
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from config import SUPPORTED_AIDS, TRANSACTION_TYPES
from utils import parse_date_time, format_card_date

logger = logging.getLogger(__name__)

class CardReader:
    """智能卡读取器类，封装所有卡片操作"""

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

    def __init__(self, connection):
        self.connection = connection
        self.selected_aid = None


    def read_card_number(self) -> Optional[Dict[str, str]]:
        """读取卡号，并解析开卡日期和有效期"""
        try:
            data, sw1, sw2 = self.transmit_apdu([0x00, 0xB0, 0x95, 0x00, 0x00])
            if (sw1, sw2) != (0x90, 0x00) or not data:
                raise Exception(f"卡号读取失败: SW={sw1:02X}{sw2:02X}")

            full_data_hex = ''.join(f"{byte:02X}" for byte in data)

            card_number = full_data_hex[20:40]
            start_date_raw = full_data_hex[40:48]  # 开卡日期(YYYYMMDD)
            valid_date_raw = full_data_hex[48:56]  # 卡有效期(YYYYMMDD)

            start_date = datetime.strptime(start_date_raw, "%Y%m%d").strftime("%Y/%m/%d")
            valid_date = datetime.strptime(valid_date_raw, "%Y%m%d").strftime("%Y/%m/%d")

            logger.info(f"卡号读取成功: {full_data_hex}")
            return {
                "card_number": card_number,
                "start_date": start_date,
                "valid_date": valid_date
            }

        except Exception as e:
            logger.error(f"读取卡号失败: {e}")
            return None


    def transmit_apdu(self, apdu: List[int]) -> Tuple[List[int], int, int]:
        """发送APDU命令并返回响应"""
        try:
            data, sw1, sw2 = self.connection.transmit(apdu)
            logger.debug(f"APDU: {apdu} -> SW: {sw1:02X}{sw2:02X}")
            return data, sw1, sw2
        except Exception as e:
            logger.error(f"APDU传输失败: {e}")
            raise

    def select_application(self) -> bool:
        """选择应用程序"""
        for aid_hex, aid_name in self.SUPPORTED_AIDS:
            try:
                aid_bytes = toBytes(aid_hex)
                apdu = [0x00, 0xA4, 0x04, 0x00, len(aid_bytes)] + aid_bytes
                _, sw1, sw2 = self.transmit_apdu(apdu)

                if (sw1, sw2) == (0x90, 0x00):
                    self.selected_aid = aid_name
                    logger.info(f"成功选择应用: {aid_name}")
                    return True

            except Exception as e:
                logger.warning(f"选择{aid_name}失败: {e}")
                continue

        logger.error("所有AID选择失败")
        return False

    def read_balance(self) -> Optional[float]:
        """读取余额"""
        try:
            data, sw1, sw2 = self.transmit_apdu([0x80, 0x5C, 0x00, 0x02, 0x04])
            if (sw1, sw2) != (0x90, 0x00):
                raise Exception(f"余额查询失败: SW={sw1:02X}{sw2:02X}")

            if len(data) < 4:
                raise Exception("余额数据长度不足")

            balance = int.from_bytes(data[:4], "big") / 100
            logger.info(f"读取余额成功: {balance:.2f}元")
            return balance

        except Exception as e:
            logger.error(f"读取余额失败: {e}")
            return None

    def parse_transaction_record(self, record_hex: str) -> Optional[Dict]:
        """解析交易记录"""
        try:
            data = bytes.fromhex(record_hex.replace(" ", ""))
            if len(data) < 23:
                return None

            # 解析金额
            amount = int.from_bytes(data[5:9], "big") / 100

            # 解析日期时间
            date_bytes = data[16:20]
            time_bytes = data[20:23]
            date_str = ''.join(f"{byte:02X}" for byte in date_bytes)
            time_str = ''.join(f"{byte:02X}" for byte in time_bytes)

            try:
                transaction_datetime = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
                datetime_str = transaction_datetime.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                datetime_str = "未知日期时间"

            # 解析交易类型
            trans_type_code = data[9]
            trans_type = self.TRANSACTION_TYPES.get(trans_type_code, f"未知({trans_type_code:02X})")

            # 站点/闸机信息
            station_gate_info = data[10:16].hex().upper()

            return {
                "amount": amount,
                "datetime": datetime_str,
                "transport_type": trans_type,
                "station_gate_info": station_gate_info,
                "raw": record_hex
            }

        except Exception as e:
            logger.warning(f"解析交易记录失败: {e}")
            return None

    def read_transactions(self, possible_sfis: List[int] = None, max_records: int = 10) -> List[Dict]:
        """读取交易记录"""
        if possible_sfis is None:
            possible_sfis = [24, 21, 18, 15, 3, 2]

        transactions = []

        for sfi in possible_sfis:
            sfi_transactions = []

            for record_num in range(1, max_records + 1):
                try:
                    apdu = [0x00, 0xB2, record_num, (sfi << 3) | 0x04, 0x00]
                    data, sw1, sw2 = self.transmit_apdu(apdu)

                    if sw1 == 0x90 and sw2 == 0x00 and data and any(data):
                        record_hex = toHexString(data)
                        parsed_tx = self.parse_transaction_record(record_hex)
                        if parsed_tx:
                            sfi_transactions.append(parsed_tx)
                    else:
                        # 当前SFI没有更多记录
                        break

                except Exception as e:
                    logger.warning(f"读取SFI {sfi} 记录 {record_num} 失败: {e}")
                    break

            if sfi_transactions:
                transactions.extend(sfi_transactions)
                logger.info(f"从SFI {sfi} 读取到 {len(sfi_transactions)} 条记录")
                break  # 找到有效记录后停止尝试其他SFI

        # 按时间排序（最新的在前）
        transactions.sort(key=lambda x: x['datetime'], reverse=True)
        return transactions

    def read_card_info(self) -> Dict:
        """读取卡片完整信息"""
        result = {
            'success': False,
            'message': '',
            'balance': None,
            'transactions': [],
            'logs': []
        }

        def log(msg):
            result['logs'].append(msg)
            logger.info(msg)

        try:
            # 选择应用
            if not self.select_application():
                result['message'] = "无法识别卡片类型"
                return result

            log(f"卡片识别成功 ({self.selected_aid})")

            # 读取余额
            balance = self.read_balance()
            if balance is not None:
                result['balance'] = balance
                log(f"余额: {balance:.2f} 元")
            else:
                log("余额读取失败")

            # 读取交易记录
            transactions = self.read_transactions()
            result['transactions'] = transactions

            if transactions:
                log(f"成功读取 {len(transactions)} 条交易记录")
            else:
                log("未读取到交易记录")

            result['success'] = True
            result['message'] = "读取成功"

        except Exception as e:
            result['message'] = f"读取失败: {str(e)}"
            log(result['message'])

        # 读取余额
        balance = self.read_balance()
        if balance is not None:
            result['balance'] = balance
            log(f"余额: {balance:.2f} 元")

            # 读取卡号 (余额成功读取后立即读取卡号)
            card_info = self.read_card_number()
            if card_info:
                result['card_info'] = card_info
                log(f"卡号: {card_info['card_number']}")
                log(f"开卡日期: {card_info['start_date']}")
                log(f"有效期至: {card_info['valid_date']}")
            else:
                log("卡号读取失败")
        return result

