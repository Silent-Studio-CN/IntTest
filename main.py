#!/usr/bin/env python3
"""入口文件"""

import sys
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s][%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("IntTest")

# 全局未捕获异常处理
def _excepthook(etype, value, tb):
    log.critical("未捕获异常", exc_info=(etype, value, tb))
sys.excepthook = _excepthook

from PySide6.QtWidgets import QApplication
from app.main_window import MainWindow

if __name__ == "__main__":
    log.info("启动 IntTest…")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    exit_code = app.exec()
    log.info(f"IntTest 退出 (code={exit_code})")
    sys.exit(exit_code)
