#!/usr/bin/env python3
"""网络连通性 (Ping) 测试 — qfluentwidgets + 导出"""

import logging

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog

from qfluentwidgets import (
    CardWidget, BodyLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton,
    SubtitleLabel, SwitchButton, InfoBar,
    FluentIcon as FIF,
)

from app.core.workers import PING_TARGETS
from app.core.exporter import do_export

log = logging.getLogger("IntTest")


class PingItem(CardWidget):
    def __init__(self, name, address, parent=None):
        super().__init__(parent)
        self._name, self._address = name, address
        self._latency = 0
        self._ok = False
        self.setFixedHeight(70)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        self.name_lbl = StrongBodyLabel(name, self)
        self.name_lbl.setFixedWidth(80)
        layout.addWidget(self.name_lbl)
        self.addr_lbl = BodyLabel(address, self); self.addr_lbl.setStyleSheet("color:#888;")
        layout.addWidget(self.addr_lbl); layout.addStretch()
        self.status_lbl = BodyLabel("⏳", self); self.status_lbl.setFixedWidth(30)
        self.status_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_lbl)
        self.latency_lbl = BodyLabel("--", self); self.latency_lbl.setFixedWidth(80)
        self.latency_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.latency_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#888;")
        layout.addWidget(self.latency_lbl)

    def set_result(self, ok, latency_ms):
        self._ok, self._latency = ok, latency_ms
        if ok:
            self.status_lbl.setText("✅")
            c = "#00C853" if latency_ms < 100 else "#FF6D00" if latency_ms < 300 else "#D50000"
            self.latency_lbl.setStyleSheet(f"font-size:16px;font-weight:bold;color:{c};")
            self.latency_lbl.setText(f"{latency_ms:.0f} ms")
        else:
            self.status_lbl.setText("❌")
            self.latency_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#D50000;")
            self.latency_lbl.setText("超时")

    def reset(self):
        self._ok, self._latency = False, 0
        self.status_lbl.setText("⏳")
        self.latency_lbl.setStyleSheet("font-size:16px;font-weight:bold;color:#888;")
        self.latency_lbl.setText("--")


class PingTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("pingTab")
        self.ping_worker = None
        self._auto_timer = QTimer(self)
        self._auto_timer.timeout.connect(self._run)
        self._setup_ui()

    def stop_workers(self):
        """关闭时清理，避免 QThread:Destroyed"""
        self._auto_timer.stop()
        if self.ping_worker and self.ping_worker.isRunning():
            self.ping_worker.quit()
            self.ping_worker.wait(2000)

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(14)

        top = QHBoxLayout()
        top.addWidget(SubtitleLabel("🌐 网络连通性测试"))
        top.addStretch()
        self.auto_switch = SwitchButton(self)
        self.auto_switch.setText("自动刷新")
        self.auto_switch.checkedChanged.connect(self._on_auto)
        top.addWidget(self.auto_switch)
        self.refresh_btn = PrimaryPushButton("刷新", self)
        self.refresh_btn.setIcon(FIF.SYNC)
        self.refresh_btn.clicked.connect(self._run)
        top.addWidget(self.refresh_btn)
        self.export_btn = PushButton("💾 导出", self)
        self.export_btn.clicked.connect(self._export)
        top.addWidget(self.export_btn)
        vbox.addLayout(top)

        self.ping_items = []
        for name, addr in PING_TARGETS:
            item = PingItem(name, addr, self)
            self.ping_items.append(item)
            vbox.addWidget(item)

        self.summary_lbl = BodyLabel("点击「刷新」测试", self)
        self.summary_lbl.setStyleSheet("color:#888;")
        vbox.addWidget(self.summary_lbl)
        vbox.addStretch()

    def _run(self):
        from app.core.workers import PingWorker
        # 清理旧 worker
        if self.ping_worker and self.ping_worker.isRunning():
            self.ping_worker.quit()
            self.ping_worker.wait(1000)
        for item in self.ping_items:
            item.reset()
        self.summary_lbl.setText("正在测试…")
        self.refresh_btn.setEnabled(False); self.auto_switch.setEnabled(False)
        self.ping_worker = PingWorker(targets=PING_TARGETS)
        self.ping_worker.result.connect(self._on_result)
        self.ping_worker.finished.connect(self._on_done)
        log.debug("PingWorker 启动")
        self.ping_worker.start()

    def _on_result(self, name, addr, ok, latency):
        for item in self.ping_items:
            if item._name == name:
                item.set_result(ok, latency)
                break

    def _on_done(self):
        self.refresh_btn.setEnabled(True); self.auto_switch.setEnabled(True)
        ok_count = sum(1 for it in self.ping_items if "✅" in it.status_lbl.text())
        self.summary_lbl.setText(f"测试完成: {ok_count}/{len(self.ping_items)} 个可达")
        log.debug(f"Ping 完成: {ok_count}/{len(self.ping_items)}")

    def _on_auto(self, checked):
        if checked:
            self._auto_timer.start(5000); self._run()
        else:
            self._auto_timer.stop()

    def _export(self):
        data = {"连通性测试": {}}
        for it in self.ping_items:
            data["连通性测试"][it._name] = f"{it._latency:.0f}ms" if it._ok else "超时"
        path, _ = QFileDialog.getSaveFileName(self, "导出", "IntTest_Ping.txt", "*.txt;;*.json;;*.sql;;*.csv")
        if not path:
            return
        fmt = path.rsplit(".", 1)[-1]
        do_export(data, path, fmt)
        InfoBar.success(title="导出成功", content="已保存", parent=self, duration=2000)
