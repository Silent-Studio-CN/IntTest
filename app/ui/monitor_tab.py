#!/usr/bin/env python3
"""实时网络流量监控 — 含折线图 + 网络接口信息"""

from collections import deque

from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    CardWidget, BodyLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, SubtitleLabel, InfoBar,
    FluentIcon as FIF,
)

from app.core.workers import get_primary_interface


# ── 折线图 ───────────────────────────────────────────────
class SparkLine(QWidget):
    def __init__(self, max_points=60, parent=None):
        super().__init__(parent)
        self._dl = deque(maxlen=max_points)
        self._ul = deque(maxlen=max_points)
        self._max_val = 100
        self.setMinimumHeight(200)

    def add_point(self, dl_kbps, ul_kbps):
        self._dl.append(dl_kbps)
        self._ul.append(ul_kbps)
        all_vals = list(self._dl) + list(self._ul)
        if all_vals:
            self._max_val = max(max(all_vals) * 1.2, 10)
        self.update()

    def paintEvent(self, event):
        if not self._dl:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        pad = 40
        pw, ph = w - pad * 2, h - pad * 2

        p.fillRect(self.rect(), QColor("#1a1a2e"))
        p.setPen(QPen(QColor("#2a2a3e"), 0.5))
        for i in range(1, 5):
            y = pad + ph * i // 5
            p.drawLine(pad, y, pad + pw, y)

        def _line(data, color):
            if not data:
                return
            path = QPainterPath()
            n = len(data)
            for i, v in enumerate(data):
                x = pad + (i / max(n - 1, 1)) * pw
                y = pad + ph - (v / self._max_val) * ph
                y = max(pad, min(pad + ph, y))
                if i == 0:
                    path.moveTo(x, y)
                else:
                    path.lineTo(x, y)
            p.setPen(QPen(color, 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        _line(self._dl, QColor("#00C853"))
        _line(self._ul, QColor("#FF6D00"))

        p.setPen(QColor("#00C853"))
        p.drawText(QRectF(pad, 4, 100, 20), Qt.AlignLeft, "↓ 下行")
        p.setPen(QColor("#FF6D00"))
        p.drawText(QRectF(pad + 80, 4, 100, 20), Qt.AlignLeft, "↑ 上行")

        p.setPen(QColor("#666"))
        f = p.font()
        f.setPointSize(8)
        p.setFont(f)
        for i in range(5):
            val = self._max_val * (1 - i / 4)
            y = pad + ph * i // 4
            p.drawText(
                QRectF(0, y - 10, pad - 4, 20),
                Qt.AlignRight | Qt.AlignVCenter,
                f"{val/1024:.1f}MB/s" if val >= 1024 else f"{val:.0f}KB/s",
            )
        p.end()


# ── 监控页面 ─────────────────────────────────────────────
class MonitorTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("monitorTab")
        self.monitor_worker = None
        self._setup_ui()

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(16)

        # 标题行
        top = QHBoxLayout()
        top.addWidget(SubtitleLabel("📊 实时网络流量监控"))
        top.addStretch()

        # 接口信息
        self.iface_lbl = BodyLabel("", self)
        self.iface_lbl.setStyleSheet("color: #888; font-size: 12px;")
        top.addWidget(self.iface_lbl)
        top.addSpacing(10)

        self.toggle_btn = PrimaryPushButton("开始监控", self)
        self.toggle_btn.setIcon(FIF.PLAY)
        self.toggle_btn.clicked.connect(self._toggle)
        top.addWidget(self.toggle_btn)
        vbox.addLayout(top)

        # 速率卡片
        cards = QHBoxLayout()
        cards.setSpacing(20)
        for obj, color, title_text in [
            ("dl", "#00C853", "↓ 下行速率"),
            ("ul", "#FF6D00", "↑ 上行速率"),
        ]:
            card = CardWidget(self)
            card.setFixedHeight(130)
            layout = QVBoxLayout(card)
            layout.setAlignment(Qt.AlignCenter)
            layout.setSpacing(2)
            lbl_title = StrongBodyLabel(title_text, card)
            lbl_title.setStyleSheet(f"color: {color}; font-size: 14px;")
            layout.addWidget(lbl_title)
            lbl = BodyLabel("0.00 KB/s", card)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet(f"font-size: 34px; font-weight: bold; color: {color};")
            layout.addWidget(lbl)
            setattr(self, f"{obj}_speed_lbl", lbl)
            cards.addWidget(card)
        vbox.addLayout(cards)

        # 折线图
        self.chart = SparkLine(60)
        vbox.addWidget(self.chart, stretch=1)

        # 底部：总计 + 接口
        bottom = QHBoxLayout()
        self.total_dl = BodyLabel("总下行: 0.00 MB", self)
        self.total_ul = BodyLabel("总上行: 0.00 MB", self)
        self.total_dl.setStyleSheet("color: #888;")
        self.total_ul.setStyleSheet("color: #888;")
        bottom.addWidget(self.total_dl)
        bottom.addStretch()
        bottom.addWidget(self.total_ul)
        vbox.addLayout(bottom)

        # 初始显示接口信息
        self._update_iface_info()

    def _update_iface_info(self):
        primary = get_primary_interface()
        if primary:
            speed_text = f"{primary.speed_mbps}Mbps" if primary.speed_mbps > 0 else "未知"
            self.iface_lbl.setText(f"{primary.name} | {primary.type} | {speed_text}")
        else:
            self.iface_lbl.setText("")

    def _toggle(self):
        if self.monitor_worker and self.monitor_worker.isRunning():
            self._stop()
        else:
            self._start()

    def _start(self):
        from app.core.workers import MonitorWorker

        self.monitor_worker = MonitorWorker(interval=1.0)
        self.monitor_worker.data.connect(self._on_data)
        self.monitor_worker.interface_changed.connect(self._on_iface)
        self.monitor_worker.start()
        self.toggle_btn.setText("停止监控")
        self.toggle_btn.setIcon(FIF.CLOSE)

    def _stop(self):
        if self.monitor_worker:
            self.monitor_worker.stop()
            self.monitor_worker.wait(2000)  # 等待线程安全退出，避免 QThread:Destroyed
            self.monitor_worker.deleteLater()
            self.monitor_worker = None
        self.toggle_btn.setText("开始监控")
        self.toggle_btn.setIcon(FIF.PLAY)

    def _on_data(self, dl_kbps, ul_kbps, total_dl_mb, total_ul_mb):
        def fmt(kbps):
            return f"{kbps/1024:.2f} MB/s" if kbps >= 1024 else f"{kbps:.2f} KB/s"
        self.dl_speed_lbl.setText(fmt(dl_kbps))
        self.ul_speed_lbl.setText(fmt(ul_kbps))
        self.total_dl.setText(f"总下行: {total_dl_mb:.2f} MB")
        self.total_ul.setText(f"总上行: {total_ul_mb:.2f} MB")
        self.chart.add_point(dl_kbps, ul_kbps)

    def _on_iface(self, name, iface_type, speed):
        speed_text = f"{speed}Mbps" if speed > 0 else "未知"
        self.iface_lbl.setText(f"{name} | {iface_type} | {speed_text}")

    def stop_monitor(self):
        self._stop()
