import tkinter as tk
from tkinter import ttk, messagebox
from smartcard.System import readers
from smartcard.util import toHexString, toBytes
from datetime import datetime


def transmit_select(apdu, connection):
    data, sw1, sw2 = connection.transmit(apdu)
    return data, sw1, sw2

def parse_balance(data):
    balance_bytes = data[:4]
    balance = int.from_bytes(balance_bytes, "big") / 100
    return balance

def parse_transaction(record_hex_str):
    data = bytes.fromhex(record_hex_str.replace(" ", ""))
    if len(data) < 23:
        return None

    amount = int.from_bytes(data[5:9], "big") / 100
    date_bytes = data[16:20]
    date_str = ''.join(f"{byte:02X}" for byte in date_bytes)
    time_bytes = data[20:23]
    time_str = ''.join(f"{byte:02X}" for byte in time_bytes)

    try:
        transaction_datetime = datetime.strptime(date_str + time_str, "%Y%m%d%H%M%S")
        datetime_str = transaction_datetime.strftime("%Y-%m-%d %H:%M:%S")
    except:
        datetime_str = "未知日期时间"

    trans_type_code = data[9]
    trans_type = {0x09: "地铁", 0x02: "充值"}.get(trans_type_code, "未知方式")

    station_gate_info = data[10:16].hex().upper()

    return {
        "amount": amount,
        "datetime": datetime_str,
        "transport_type": trans_type,
        "station_gate_info": station_gate_info,
        "raw": record_hex_str
    }

def read_transactions(connection, possible_sfis=[2, 18], num_records=10):
    transactions = []
    for sfi in possible_sfis:
        for record in range(1, num_records + 1):
            apdu = [0x00, 0xB2, record, (sfi << 3) | 0x04, 0x00]
            data, sw1, sw2 = transmit_select(apdu, connection)
            if sw1 == 0x90 and sw2 == 0x00 and data and any(data):
                record_hex = toHexString(data)
                parsed_tx = parse_transaction(record_hex)
                if parsed_tx:
                    transactions.append(parsed_tx)
            else:
                break
        if transactions:
            break
    return transactions

# 修改后的 read_card，返回结果字符串
def read_card(connection):
    result_output = ""

    def output(msg):
        nonlocal result_output
        result_output += msg + '\n'

    try:
        aid_cj = toBytes("A000000632010105")
        apdu_select_cj = [0x00, 0xA4, 0x04, 0x00, len(aid_cj)] + aid_cj
        _, sw1, sw2 = transmit_select(apdu_select_cj, connection)
        if (sw1, sw2) != (0x90, 0x00):
            raise Exception("住建部标准AID选择失败")

        output("住建部标准卡识别成功")
        data, sw1, sw2 = transmit_select([0x80, 0x5C, 0x00, 0x02, 0x04], connection)
        if (sw1, sw2) != (0x90, 0x00):
            raise Exception("住建部标准查询余额失败")

        balance = parse_balance(data)
        output(f"余额: {balance:.2f} 元")

        transactions = read_transactions(connection, possible_sfis=[24,21,18,15,3,2])
        if transactions:
            output("交易记录如下：")
            for idx, tx in enumerate(transactions, start=1):
                output(f"{idx:02d}: {tx['datetime']} - 金额: {tx['amount']:.2f}元 - {tx['transport_type']}")
        else:
            output("未读取到有效交易记录。")

    except Exception as e:
        output(f"住建部标准失败: {e}\n尝试交通联合标准...")

        aid_t_union = toBytes("A000000632010106")
        apdu_select_union = [0x00, 0xA4, 0x04, 0x00, len(aid_t_union)] + aid_t_union
        _, sw1, sw2 = transmit_select(apdu_select_union, connection)
        if (sw1, sw2) != (0x90, 0x00):
            output(f"交通联合标准失败 (SW1 SW2: {hex(sw1)} {hex(sw2)})")
            return result_output

        output("交通联合卡识别成功")
        data, sw1, sw2 = transmit_select([0x80, 0x5C, 0x00, 0x02, 0x04], connection)
        if (sw1, sw2) != (0x90, 0x00):
            output("余额查询失败。")
            return result_output

        balance = parse_balance(data)
        output(f"余额: {balance:.2f} 元")

        transactions = read_transactions(connection, possible_sfis=[2,3,18])
        if transactions:
            output("交易记录如下：")
            for idx, tx in enumerate(transactions, start=1):
                output(f"{idx:02d}: {tx['datetime']} - 金额: {tx['amount']:.2f}元 - {tx['transport_type']}")
        else:
            output("未读取到有效交易记录。")

    return result_output

# UI主界面代码
class CardReaderApp:
    def __init__(self, master):
        self.master = master
        master.title("公交卡信息读取")

        ttk.Label(master, text="选择读卡器:").pack(pady=5)
        self.reader_var = tk.StringVar()
        self.reader_combo = ttk.Combobox(master, textvariable=self.reader_var)
        self.reader_combo.pack(pady=5)

        self.read_btn = ttk.Button(master, text="读 卡", command=self.read_btn_clicked)
        self.read_btn.pack(pady=10)

        # 新增余额显示框
        self.balance_var = tk.StringVar()
        ttk.Label(master, textvariable=self.balance_var, font=("Helvetica", 12, "bold"), foreground="blue").pack(pady=5)

        # 新增交易记录表格
        columns = ("序号", "时间", "金额 (元)", "类型")
        self.tree = ttk.Treeview(master, columns=columns, show="headings", height=10)
        for col in columns:
            self.tree.heading(col, text=col)
            self.tree.column(col, anchor="center")
        self.tree.pack(pady=10, fill="x")

        # 原始日志文本框的label提示
        ttk.Label(master, text="原始数据日志：").pack(pady=(5, 0))
        self.result_txt = tk.Text(master, height=15, width=70)
        self.result_txt.pack(pady=10)

        # 初始化读卡器列表
        self.refresh_readers()

    # UI更新-新增函数以清空之前数据
    def clear_data(self):
        self.balance_var.set("")
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.result_txt.delete("1.0", tk.END)

    def refresh_readers(self):
        reader_list = readers()
        reader_names = [str(reader) for reader in reader_list]
        self.reader_combo['values'] = reader_names
        if reader_names:
            self.reader_combo.current(0)

    def read_btn_clicked(self):
        selected_reader = self.reader_var.get()
        reader_list = readers()
        reader = next((r for r in reader_list if str(r) == selected_reader), None)
        if reader is None:
            messagebox.showerror("错误", "未选择读卡器")
            return

        self.clear_data()  # 先清除旧数据显示
        try:
            connection = reader.createConnection()
            connection.connect()

            # 调用 read_card 获取数据。
            result_output = ""
            balance_message = ""
            transactions = []

            def output(msg):
                nonlocal result_output
                result_output += msg + '\n'

            try:
                aid_cj = toBytes("A000000632010105")
                apdu_select_cj = [0x00, 0xA4, 0x04, 0x00, len(aid_cj)] + aid_cj
                _, sw1, sw2 = transmit_select(apdu_select_cj, connection)
                if (sw1, sw2) != (0x90, 0x00):
                    raise Exception("住建部标准AID选择失败")

                output("住建部标准卡识别成功")
                data, sw1, sw2 = transmit_select([0x80, 0x5C, 0x00, 0x02, 0x04], connection)
                if (sw1, sw2) != (0x90, 0x00):
                    raise Exception("住建部标准查询余额失败")

                balance = parse_balance(data)
                balance_message = f"余额: {balance:.2f} 元"

                transactions = read_transactions(connection, possible_sfis=[24, 21, 18, 15, 3, 2])

            except Exception as e:
                output(f"住建部标准失败: {e}\n尝试交通联合标准...")
                aid_t_union = toBytes("A000000632010106")
                apdu_select_union = [0x00, 0xA4, 0x04, 0x00, len(aid_t_union)] + aid_t_union
                _, sw1, sw2 = transmit_select(apdu_select_union, connection)
                if (sw1, sw2) != (0x90, 0x00):
                    output(f"交通联合标准失败 (SW1 SW2: {hex(sw1)} {hex(sw2)})")
                    return

                output("交通联合卡识别成功")
                data, sw1, sw2 = transmit_select([0x80, 0x5C, 0x00, 0x02, 0x04], connection)
                if (sw1, sw2) != (0x90, 0x00):
                    output("余额查询失败。")
                    return

                balance = parse_balance(data)
                balance_message = f"余额: {balance:.2f} 元"
                transactions = read_transactions(connection, possible_sfis=[2, 3, 18])

            # 显示余额
            self.balance_var.set(balance_message)

            # 显示交易记录到表格
            if transactions:
                for idx, tx in enumerate(transactions, start=1):
                    self.tree.insert("", "end", values=(f"{idx:02d}", tx["datetime"], f"{tx['amount']:.2f}", tx["transport_type"]))
                    output(tx['raw'])
            else:
                output("未读取到有效交易记录。")

        except Exception as e:
            result_output = f"错误: 没有检测到卡片或连接失败。\n详细信息: {e}"

        # 将原始日志数据显示到文本框
        self.result_txt.delete("1.0", tk.END)
        self.result_txt.insert(tk.END, result_output)



if __name__ == '__main__':
    root = tk.Tk()
    app = CardReaderApp(root)
    root.mainloop()
