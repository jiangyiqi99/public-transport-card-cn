import tkinter as tk
from tkinter import ttk, messagebox
from smartcard.System import readers
from smartcard.util import toHexString, toBytes
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
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

        return result


class CardReaderApp:
    """主应用程序界面"""

    def __init__(self, master):
        self.master = master
        self.setup_ui()
        self.refresh_readers()

    def setup_ui(self):
        """设置用户界面"""
        self.master.title("智能卡信息读取器")
        self.master.geometry("800x700")

        # 读卡器选择
        reader_frame = ttk.Frame(self.master)
        reader_frame.pack(pady=10, fill='x', padx=10)

        ttk.Label(reader_frame, text="选择读卡器:").pack(side='left')
        self.reader_var = tk.StringVar()
        self.reader_combo = ttk.Combobox(reader_frame, textvariable=self.reader_var, width=50)
        self.reader_combo.pack(side='left', padx=(10, 0), fill='x', expand=True)

        ttk.Button(reader_frame, text="刷新", command=self.refresh_readers).pack(side='right', padx=(10, 0))

        # 操作按钮
        button_frame = ttk.Frame(self.master)
        button_frame.pack(pady=10)

        self.read_btn = ttk.Button(button_frame, text="读取卡片", command=self.read_card)
        self.read_btn.pack(side='left', padx=5)

        ttk.Button(button_frame, text="清空数据", command=self.clear_data).pack(side='left', padx=5)

        # 余额显示
        self.balance_var = tk.StringVar()
        balance_label = ttk.Label(self.master, textvariable=self.balance_var,
                                  font=("Arial", 14, "bold"), foreground="blue")
        balance_label.pack(pady=10)

        # 交易记录表格
        ttk.Label(self.master, text="交易记录:", font=("Arial", 12, "bold")).pack(pady=(10, 5))

        # 创建表格框架
        tree_frame = ttk.Frame(self.master)
        tree_frame.pack(pady=5, padx=10, fill='both', expand=True)

        # 表格
        columns = ("序号", "时间", "金额(元)", "类型", "详细信息")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=8)

        # 设置列
        column_widths = {"序号": 50, "时间": 150, "金额(元)": 80, "类型": 80, "详细信息": 120}
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, width=column_widths.get(col, 100), anchor="center")

        # 滚动条
        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

        # 日志区域
        ttk.Label(self.master, text="操作日志:", font=("Arial", 12, "bold")).pack(pady=(10, 5))

        log_frame = ttk.Frame(self.master)
        log_frame.pack(pady=5, padx=10, fill='both', expand=True)

        self.log_text = tk.Text(log_frame, height=8, wrap='word')
        log_scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side='left', fill='both', expand=True)
        log_scrollbar.pack(side='right', fill='y')

    def refresh_readers(self):
        """刷新读卡器列表"""
        try:
            reader_list = readers()
            reader_names = [str(reader) for reader in reader_list]
            self.reader_combo['values'] = reader_names

            if reader_names:
                self.reader_combo.current(0)
                self.log_message(f"发现 {len(reader_names)} 个读卡器")
            else:
                self.log_message("未发现读卡器")

        except Exception as e:
            self.log_message(f"刷新读卡器失败: {e}")
            messagebox.showerror("错误", f"刷新读卡器失败: {e}")

    def clear_data(self):
        """清空显示数据"""
        self.balance_var.set("")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.log_text.delete("1.0", tk.END)

    def log_message(self, message):
        """添加日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        self.log_text.see(tk.END)
        self.master.update_idletasks()

    def read_card(self):
        """读取卡片信息"""
        selected_reader = self.reader_var.get()
        if not selected_reader:
            messagebox.showerror("错误", "请选择读卡器")
            return

        # 找到对应的读卡器
        reader_list = readers()
        reader = next((r for r in reader_list if str(r) == selected_reader), None)
        if reader is None:
            messagebox.showerror("错误", "选择的读卡器无效")
            return

        self.clear_data()
        self.read_btn.config(state='disabled', text='读取中...')

        try:
            self.log_message("正在连接读卡器...")
            connection = reader.createConnection()
            connection.connect()
            self.log_message("读卡器连接成功")

            # 创建卡片读取器并读取信息
            card_reader = CardReader(connection)
            result = card_reader.read_card_info()

            # 显示日志
            for log_msg in result['logs']:
                self.log_message(log_msg)

            if result['success']:
                # 显示余额
                if result['balance'] is not None:
                    self.balance_var.set(f"余额: {result['balance']:.2f} 元")
                # 显示交易记录
                transactions = result['transactions']
                if transactions:
                    for idx, tx in enumerate(transactions, 1):
                        self.tree.insert("", "end", values=(
                            f"{idx:02d}",
                            tx["datetime"],
                            f"{tx['amount']:.2f}",
                            tx["transport_type"],
                            tx["station_gate_info"]
                        ))

                    self.log_message(f"显示 {len(transactions)} 条交易记录")
                else:
                    self.log_message("未找到交易记录")
            else:
                messagebox.showerror("错误", result['message'])

        except Exception as e:
            error_msg = f"读取失败: {str(e)}"
            self.log_message(error_msg)
            messagebox.showerror("错误", error_msg)

        finally:
            self.read_btn.config(state='normal', text='读取卡片')
            try:
                connection.disconnect()
                self.log_message("读卡器连接已断开")
            except:
                pass


class ConfigManager:
    """配置管理器"""

    DEFAULT_CONFIG = {
        'max_records': 20,
        'possible_sfis': [24, 21, 18, 15, 3, 2],
        'log_level': 'INFO'
    }

    @classmethod
    def get_config(cls):
        """获取配置"""
        # 这里可以扩展为从文件读取配置
        return cls.DEFAULT_CONFIG.copy()


def main():
    """主函数"""
    try:
        root = tk.Tk()

        # 设置窗口图标和样式
        try:
            root.iconbitmap('icon.ico')  # 如果有图标文件
        except:
            pass

        # 设置主题
        style = ttk.Style()
        try:
            style.theme_use('clam')  # 使用更现代的主题
        except:
            pass

        app = CardReaderApp(root)

        # 设置窗口关闭事件
        def on_closing():
            if messagebox.askokcancel("退出", "确定要退出程序吗？"):
                root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_closing)

        # 居中显示窗口
        root.update_idletasks()
        width = root.winfo_width()
        height = root.winfo_height()
        x = (root.winfo_screenwidth() // 2) - (width // 2)
        y = (root.winfo_screenheight() // 2) - (height // 2)
        root.geometry(f'{width}x{height}+{x}+{y}')

        root.mainloop()

    except Exception as e:
        messagebox.showerror("启动错误", f"程序启动失败: {e}")
        logger.error(f"程序启动失败: {e}")


if __name__ == '__main__':
    main()
