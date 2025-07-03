"""GUI界面模块"""
import tkinter as tk
from tkinter import ttk, messagebox
from smartcard.System import readers
from datetime import datetime

from card_reader import CardReader
from config import (UI_CONFIG)


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

        # 卡号显示
        self.card_number_var = tk.StringVar()
        card_number_label = ttk.Label(self.master, textvariable=self.card_number_var,
                                      font=("Arial", 12, "bold"))
        card_number_label.pack(pady=5)

        # 卡片日期信息
        self.card_dates_var = tk.StringVar()
        card_dates_label = ttk.Label(self.master, textvariable=self.card_dates_var,
                                    font=("Arial", 12))
        card_dates_label.pack(pady=5)

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
        self.card_number_var.set("")
        self.card_dates_var.set("")
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
                # 显示卡号和日期信息
                if 'card_info' in result and result['card_info']:
                    card_info = result['card_info']
                    self.card_number_var.set(f"卡号: {card_info['card_number']}")
                    self.card_dates_var.set(f"开卡日期: {card_info['start_date']}   有效期至: {card_info['valid_date']}")

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