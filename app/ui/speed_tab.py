#!/usr/bin/env python3
"""下载/上传速度测试 — qfluentwidgets + 极限模式 + 波动检测 + 导出"""

import time
from collections import deque

from PySide6.QtCore import Qt, QRectF, QPoint
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath, QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
    QApplication, QToolTip,
)
from qfluentwidgets import (
    CardWidget, BodyLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, ProgressBar,
    ComboBox, SubtitleLabel, InfoBar, SwitchButton,
    FluentIcon as FIF,
)
from app.core.workers import DOWNLOAD_URLS
from app.core.exporter import do_export


# ── 折线图 ───────────────────────────────────────────────
class SpeedSparkLine(QWidget):
    def __init__(self, max_points=60, parent=None):
        super().__init__(parent)
        self._data = deque(maxlen=max_points)
        self._times = deque(maxlen=max_points)
        self._max_val = 100
        self._hover_idx = -1
        self.setMinimumHeight(120)
        self.setMouseTracking(True)

    def add_point(self, mbps):
        self._data.append(mbps)
        self._times.append(time.time())
        if self._data:
            self._max_val = max(max(self._data) * 1.2, 10)
        self.update()

    def reset(self):
        self._data.clear()
        self._times.clear()
        self._max_val = 100
        self._hover_idx = -1
        self.update()

    def mouseMoveEvent(self, event):
        if not self._data:
            self._hover_idx = -1
            self.update()
            return
        w, pad = self.width(), 12
        pw, n = w - pad * 2, len(self._data)
        pos = event.position() if hasattr(event, 'position') else QPoint(event.x(), event.y())
        idx = int((pos.x() - pad) / pw * (n - 1)) if n > 1 else 0
        idx = max(0, min(n - 1, idx))
        if idx != self._hover_idx:
            self._hover_idx = idx
            self.update()
            val, t = self._data[idx], self._times[idx] if idx < len(self._times) else 0
            elapsed = t - self._times[0] if self._times and t else 0
            gp = event.globalPosition().toPoint() if hasattr(event, 'globalPosition') else event.globalPos()
            QToolTip.showText(gp, f"{val:.2f} Mbps\n+{elapsed:.1f}s", self)

    def leaveEvent(self, event):
        self._hover_idx = -1
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if not self._data:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        w, h, pad = self.width(), self.height(), 12
        pw, ph, n = w - pad * 2, h - pad * 2, len(self._data)
        p.fillRect(self.rect(), QColor("#0e0e1e"))
        p.setPen(QPen(QColor("#1e1e34"), 0.3))
        for i in range(5):
            y = pad + ph * i // 4
            p.drawLine(pad, y, pad + pw, y)

        path = QPainterPath()
        for i, v in enumerate(self._data):
            x = pad + (i / max(n - 1, 1)) * pw
            y = pad + ph - (v / self._max_val) * ph
            y = max(pad, min(pad + ph, y))
            (path.moveTo if i == 0 else path.lineTo)(x, y)

        p.setPen(QPen(QColor("#00E676"), 2))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        if n > 1:
            fill = QPainterPath(path)
            lx = pad + ((n - 1) / max(n - 1, 1)) * pw
            fill.lineTo(lx, pad + ph)
            fill.lineTo(pad, pad + ph)
            fill.closeSubpath()
            p.setBrush(QColor(0, 230, 118, 30))
            p.setPen(Qt.NoPen)
            p.drawPath(fill)

        if 0 <= self._hover_idx < n:
            v = self._data[self._hover_idx]
            hx = pad + (self._hover_idx / max(n - 1, 1)) * pw
            hy = pad + ph - (v / self._max_val) * ph
            hy = max(pad, min(pad + ph, hy))
            p.setPen(QPen(QColor("#fff"), 1, Qt.DashLine))
            p.drawLine(hx, pad, hx, pad + ph)
            p.drawLine(pad, hy, pad + pw, hy)
            p.setPen(QPen(QColor("#00E676"), 2))
            p.setBrush(QColor("#00E676"))
            p.drawEllipse(QPoint(int(hx), int(hy)), 4, 4)
        p.end()


class SpeedCard(CardWidget):
    def __init__(self, title, color="#009fef", parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedHeight(170)
        l = QVBoxLayout(self)
        l.setAlignment(Qt.AlignCenter)
        l.setSpacing(2)
        self.t = StrongBodyLabel(title, self)
        self.t.setAlignment(Qt.AlignCenter)
        self.t.setStyleSheet(f"color:{color};font-size:14px;background:transparent;")
        self.s = BodyLabel("0.00", self)
        self.s.setAlignment(Qt.AlignCenter)
        self.s.setStyleSheet(f"color:{color};font-size:48px;font-weight:bold;background:transparent;")
        self.u = BodyLabel("Mbps", self)
        self.u.setAlignment(Qt.AlignCenter)
        self.u.setStyleSheet("color:#888;font-size:12px;background:transparent;")
        l.addWidget(self.t); l.addWidget(self.s); l.addWidget(self.u)

    def set_speed(self, mbps):
        self.s.setText(f"{mbps:.2f}")
    def reset(self):
        self.s.setText("0.00")


# ── 速度测试页面 ─────────────────────────────────────────
class SpeedTestTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("speedTestTab")
        self.dl_worker = None
        self.ul_worker = None
        self.jitter_worker = None
        self._last_dl = (0, 0)
        self._last_ul = (0, 0)
        self._last_jitter = None
        self._setup_ui()

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(12)
        vbox.addWidget(SubtitleLabel("⚡ 下载 & 上传速度测试"))

        cards = QHBoxLayout(); cards.setSpacing(20)
        self.dl_card = SpeedCard("下载速度", "#00C853")
        self.ul_card = SpeedCard("上传速度", "#FF6D00")
        cards.addWidget(self.dl_card); cards.addWidget(self.ul_card)
        vbox.addLayout(cards)

        # 图表
        ct = StrongBodyLabel("实时速度趋势（鼠标悬停查看详情）")
        ct.setStyleSheet("color:#999;font-size:11px;")
        vbox.addWidget(ct)
        self.chart = SpeedSparkLine(60)
        vbox.addWidget(self.chart)

        # 控制栏
        ctrl = QHBoxLayout(); ctrl.setSpacing(10)
        ctrl.addWidget(BodyLabel("服务器:"))
        self.server_combo = ComboBox(self)
        for l, u in DOWNLOAD_URLS:
            self.server_combo.addItem(l, u)
        self.server_combo.setMinimumWidth(200)
        ctrl.addWidget(self.server_combo)
        ctrl.addStretch()

        self.start_btn = PrimaryPushButton("开始测速", self)
        self.start_btn.setIcon(FIF.SPEED_HIGH)
        self.start_btn.clicked.connect(self._start)
        ctrl.addWidget(self.start_btn)

        self.stop_btn = PushButton("停止", self)
        self.stop_btn.setEnabled(False)
        self.stop_btn.clicked.connect(self._stop)
        ctrl.addWidget(self.stop_btn)
        vbox.addLayout(ctrl)

        # 极限模式 + 波动测试 + 导出
        opt = QHBoxLayout(); opt.setSpacing(16)
        opt.addWidget(BodyLabel("⚡ 极限模式："))
        self.stress_switch = SwitchButton(self)
        self.stress_switch.setText("关闭")
        self.stress_switch.checkedChanged.connect(
            lambda c: self.stress_switch.setText("开启" if c else "关闭")
        )
        opt.addWidget(self.stress_switch)
        opt.addSpacing(20)

        self.jitter_btn = PushButton("📊 波动测试", self)
        self.jitter_btn.clicked.connect(self._run_jitter)
        opt.addWidget(self.jitter_btn)

        self.export_btn = PushButton("💾 导出结果", self)
        self.export_btn.clicked.connect(self._export)
        opt.addWidget(self.export_btn)
        opt.addStretch()
        vbox.addLayout(opt)

        self.progress = ProgressBar(self)
        self.progress.setRange(0, 100); self.progress.setValue(0)
        vbox.addWidget(self.progress)

        self.status_lbl = BodyLabel("就绪，点击「开始测速」", self)
        self.status_lbl.setStyleSheet("color:#888;")
        vbox.addWidget(self.status_lbl)

        self.result_lbl = BodyLabel("", self)
        self.result_lbl.setStyleSheet("color:#ccc;")
        vbox.addWidget(self.result_lbl)
        vbox.addStretch()

    def _stress_params(self):
        if self.stress_switch.isChecked():
            return {"duration": 30, "dl_streams": 12, "ul_streams": 8}
        return {"duration": 15, "dl_streams": 6, "ul_streams": 4}

    def _start(self):
        from app.core.workers import DownloadWorker, UploadWorker
        # 清理旧 worker，防止内存泄漏
        for w in (self.dl_worker, self.ul_worker):
            if w:
                if w.isRunning():
                    w.stop()
                    w.wait(2000)
                w.deleteLater()
        self.dl_worker = None
        self.ul_worker = None
        url = self.server_combo.currentData()
        sp = self._stress_params()
        self.dl_card.reset(); self.ul_card.reset(); self.chart.reset()
        self.progress.setValue(0); self.result_lbl.setText("")
        self.start_btn.setEnabled(False); self.stop_btn.setEnabled(True)
        # 测速期间禁用控件
        self.server_combo.setEnabled(False)
        self.stress_switch.setEnabled(False)
        self.jitter_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        label = "极限" if self.stress_switch.isChecked() else "普通"
        self.status_lbl.setText(f"⏳ {label}模式测试中…")

        self.dl_worker = DownloadWorker(url=url, duration=sp["duration"], streams=sp["dl_streams"])
        self.dl_worker.speed.connect(self.dl_card.set_speed)
        self.dl_worker.speed.connect(self.chart.add_point)
        self.dl_worker.progress.connect(self.progress.setValue)
        self.dl_worker.status_msg.connect(lambda m: self.status_lbl.setText(f"⏳ {m}"))
        self.dl_worker.finished.connect(self._on_dl_done)
        self.dl_worker.error.connect(self._on_error)
        self.dl_worker.start()

        self.ul_worker = UploadWorker(duration=sp["duration"], streams=sp["ul_streams"])
        self.ul_worker.speed.connect(self.ul_card.set_speed)
        self.ul_worker.finished.connect(self._on_ul_done)
        self.ul_worker.error.connect(self._on_error)
        self.ul_worker.start()

    def _stop(self):
        for w in (self.dl_worker, self.ul_worker, self.jitter_worker):
            if w and w.isRunning():
                w.stop(); w.wait(2000)
        self._reset_ui("已手动停止")

    def _on_dl_done(self, avg, mb):
        self._last_dl = (avg, mb)
        self.progress.setValue(50)  # 下载完成给 50%
        self.result_lbl.setText(self.result_lbl.text() + f"▸ 下载: {avg:.2f} Mbps（{mb:.1f} MB）")
        self._check_done()

    def _on_ul_done(self, avg, mb):
        self._last_ul = (avg, mb)
        self.progress.setValue(90)  # 上传完成给 90%，避免回退
        self.result_lbl.setText(self.result_lbl.text() + f"\n▸ 上传: {avg:.2f} Mbps（{mb:.1f} MB）")
        self._check_done()

    def _on_error(self, msg):
        self.status_lbl.setText(f"错误: {msg}"); self.status_lbl.setStyleSheet("color:#d32f2f;")
        self._reset_ui("")

    def _check_done(self):
        dl = self.dl_worker and not self.dl_worker.isRunning()
        ul = self.ul_worker and not self.ul_worker.isRunning()
        if dl and ul:
            self._reset_ui("测速完成")
            InfoBar.success(title="完成", content="下载/上传速度测试已结束", parent=self)

    def _reset_ui(self, text):
        self.start_btn.setEnabled(True); self.stop_btn.setEnabled(False)
        self.server_combo.setEnabled(True)
        self.stress_switch.setEnabled(True)
        self.jitter_btn.setEnabled(True)
        self.export_btn.setEnabled(True)
        self.progress.setValue(100)
        if text:
            self.status_lbl.setStyleSheet("color:#888;"); self.status_lbl.setText(text)

    def _run_jitter(self):
        from app.core.workers import JitterWorker
        self.jitter_btn.setEnabled(False)
        self.status_lbl.setText("⏳ 波动测试中 (20次Ping)…")
        url = self.server_combo.currentData()
        if not url:
            target = "www.baidu.com"
        else:
            target = url.split("/")[2] if "//" in url else "www.baidu.com"
        self.jitter_worker = JitterWorker(target=target, count=20)
        self.jitter_worker.result.connect(self._on_jitter)
        self.jitter_worker.start()

    def _on_jitter(self, data):
        self._last_jitter = data
        self.jitter_btn.setEnabled(True)
        txt = (f"\n📊 波动: 最小 {data['min']}ms / 平均 {data['avg']}ms / "
               f"最大 {data['max']}ms / 抖动 {data['jitter']}ms / 丢包 {data['loss']}%")
        self.result_lbl.setText(self.result_lbl.text() + txt)
        self.status_lbl.setText("波动测试完成")

    def _export(self):
        dl_avg, dl_mb = self._last_dl
        ul_avg, ul_mb = self._last_ul
        data = {"速度测试": {"下载_Mbps": dl_avg, "下载_MB": dl_mb, "上传_Mbps": ul_avg, "上传_MB": ul_mb}}
        if self._last_jitter:
            j = self._last_jitter
            data["波动测试"] = {"最小_ms": j["min"], "平均_ms": j["avg"], "最大_ms": j["max"],
                               "抖动_ms": j["jitter"], "丢包率": f"{j['loss']}%"}
        path, _ = QFileDialog.getSaveFileName(self, "导出结果", "IntTest_测速结果.txt", "*.txt;;*.json;;*.sql;;*.csv")
        if not path:
            return
        fmt = path.rsplit(".", 1)[-1]
        do_export(data, path, fmt)
        InfoBar.success(title="导出成功", content=f"已保存", parent=self, duration=2000)

    def stop_workers(self):
        self._stop()
