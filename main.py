"""主程序入口"""
import tkinter as tk
from tkinter import ttk, messagebox
import logging

from config import ConfigManager
from utils import setup_logging
from ui import CardReaderApp


def main():
    """主函数"""
    try:
        # 加载配置
        config = ConfigManager.get_config()

        # 设置日志
        setup_logging(config.get('log_level', 'INFO'))
        logger = logging.getLogger(__name__)

        # 创建主窗口
        root = tk.Tk()

        # 设置窗口图标和样式
        try:
            root.iconbitmap('icon.ico')
        except:
            pass

        # 设置主题
        style = ttk.Style()
        try:
            style.theme_use('clam')
        except:
            pass

        # 创建应用
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
