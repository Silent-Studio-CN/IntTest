#!/usr/bin/env python3
"""网络信息检测 — 单击复制 + 导出（懒加载，不阻塞启动）"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QScrollArea,
    QFileDialog, QApplication,
)
from qfluentwidgets import (
    CardWidget, BodyLabel, StrongBodyLabel,
    PrimaryPushButton, SubtitleLabel, InfoBar, ComboBox,
    FluentIcon as FIF,
)
from app.core.workers import get_primary_interface, get_platform
from app.core.exporter import do_export, guess_extension


class InfoRow(CardWidget):
    def __init__(self, label: str, value: str = "--", color: str = "#e0e0e0", parent=None):
        super().__init__(parent)
        self.setFixedHeight(54)
        self._value = value
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 4, 20, 4)
        self.key_lbl = StrongBodyLabel(label, self)
        self.key_lbl.setFixedWidth(140)
        layout.addWidget(self.key_lbl)
        layout.addStretch()
        self.val_lbl = BodyLabel(value, self)
        self.val_lbl.setStyleSheet(f"color: {color}; font-size: 14px;")
        layout.addWidget(self.val_lbl)

    def mousePressEvent(self, event):
        QApplication.clipboard().setText(self._value)
        InfoBar.success(title="已复制", content=f"「{self.key_lbl.text()}」→ {self._value}", parent=self, duration=1500)
        super().mousePressEvent(event)

    def get_value(self) -> str:
        return self._value

    def set_value(self, value: str, color: str = "#e0e0e0"):
        self._value = value
        self.val_lbl.setText(value)
        self.val_lbl.setStyleSheet(f"color: {color}; font-size: 14px;")


class NetworkInfoTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("networkInfoTab")
        self.ip_worker = None
        self.net_worker = None
        self._loaded = False
        self._setup_ui()

    def showEvent(self, event):
        super().showEvent(event)
        # 首次显示时才启动网络查询，避免启动时创建线程导致 QThread:Destroyed
        if not self._loaded:
            self._loaded = True
            self._refresh()

    def stop_workers(self):
        for w in (self.ip_worker, self.net_worker):
            if w and w.isRunning():
                w.stop()
                w.wait(2000)

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollBar:vertical{width:6px;background:#1a1a2e;}"
            "QScrollBar::handle:vertical{background:#3a3a5e;border-radius:3px;}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}"
        )
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        vbox = QVBoxLayout(content)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(12)

        top = QHBoxLayout()
        top.addWidget(SubtitleLabel("🌐 网络信息检测（单击行即可复制）"))
        top.addStretch()
        self.refresh_btn = PrimaryPushButton("刷新", self)
        self.refresh_btn.setIcon(FIF.SYNC)
        self.refresh_btn.clicked.connect(self._refresh)
        top.addWidget(self.refresh_btn)
        self.export_btn = PrimaryPushButton("导出", self)
        self.export_btn.setIcon(FIF.SAVE)
        self.export_btn.clicked.connect(self._export)
        top.addWidget(self.export_btn)
        self.fmt_combo = ComboBox(self)
        self.fmt_combo.addItems(["TXT", "JSON", "SQL", "CSV"])
        self.fmt_combo.setMinimumWidth(80)
        top.addWidget(self.fmt_combo)
        vbox.addLayout(top)

        vbox.addWidget(StrongBodyLabel("📡 本地网络接口"))
        self.local_rows = {}
        for label, key in [
            ("操作系统","platform"),("接口名称","iface_name"),("接口类型","iface_type"),
            ("链路速率","iface_speed"),("IP 地址","iface_ip"),("MAC 地址","iface_mac"),
        ]:
            row = InfoRow(label,"--","#888")
            self.local_rows[key] = row
            vbox.addWidget(row)

        vbox.addSpacing(6)
        vbox.addWidget(StrongBodyLabel("☁️ 公网信息"))
        self.public_rows = {}
        for label, key in [
            ("公网 IPv4","ipv4"),("公网 IPv6","ipv6"),("运营商 ISP","isp"),
            ("所属组织","org"),("国家/地区","country"),("城市","city"),("ASN 编号","asn"),
        ]:
            row = InfoRow(label,"--","#888")
            self.public_rows[key] = row
            vbox.addWidget(row)

        vbox.addSpacing(6)
        vbox.addWidget(StrongBodyLabel("🔗 IPv4 / IPv6 支持性"))
        self.check_rows = {}
        for label, key in [
            ("IPv4 DNS 解析","ipv4_dns"),("IPv6 DNS 解析","ipv6_dns"),
            ("IPv4 HTTP 连通","ipv4_http"),("IPv6 HTTP 连通","ipv6_http"),
            ("IPv4 延迟","ipv4_latency"),("IPv6 延迟","ipv6_latency"),
        ]:
            row = InfoRow(label,"--","#888")
            self.check_rows[key] = row
            vbox.addWidget(row)

        vbox.addStretch()
        scroll.setWidget(content)
        root.addWidget(scroll)
        self._load_local()

    def _load_local(self):
        self.local_rows["platform"].set_value(get_platform())
        p = get_primary_interface()
        if p:
            self.local_rows["iface_name"].set_value(p.name)
            self.local_rows["iface_type"].set_value(p.type)
            speed_text = f"{p.speed_mbps} Mbps" if p.speed_mbps > 0 else "未知"
            self.local_rows["iface_speed"].set_value(speed_text)
            self.local_rows["iface_ip"].set_value(p.ip)
            self.local_rows["iface_mac"].set_value(p.mac)
        else:
            for r in self.local_rows.values():
                r.set_value("无活动接口","#d32f2f")

    def _refresh(self):
        self.stop_workers()
        self.refresh_btn.setEnabled(False)
        for r in self.public_rows.values():
            r.set_value("查询中…","#FF6D00")
        for k in self.check_rows:
            self.check_rows[k].set_value("检测中…","#FF6D00")
        from app.core.workers import IPInfoWorker, NetCheckWorker
        self.ip_worker = IPInfoWorker()
        self.ip_worker.result.connect(self._on_ip)
        self.ip_worker.start()
        self.net_worker = NetCheckWorker()
        self.net_worker.result.connect(self._on_net)
        self.net_worker.start()

    def _on_ip(self, data):
        self.refresh_btn.setEnabled(True)
        g,y = "#00C853","#FF6D00"
        self.public_rows["ipv4"].set_value(data.get("ipv4","--") or "无", g if data.get("ipv4") else y)
        v6 = data.get("ipv6","不支持")
        self.public_rows["ipv6"].set_value(v6 or "不支持", g if v6 and v6!="不支持" else y)
        self.public_rows["isp"].set_value(data.get("isp","--") or "未知")
        self.public_rows["org"].set_value(data.get("org","--") or "未知")
        cc = data.get("country_code","")
        c = data.get("country","--") or "未知"
        self.public_rows["country"].set_value(f"{c}({cc})" if cc else c)
        self.public_rows["city"].set_value(data.get("city","--") or "未知")
        a,ao = data.get("asn",""), data.get("asn_org","")
        self.public_rows["asn"].set_value(f"AS{a} {ao}" if a and ao else (f"AS{a}" if a else "--"))

    def _on_net(self, ck):
        def fb(v): return "✅ 支持" if v else "❌ 不支持"
        def fl(v): return f"{v:.0f}ms" if v>0 else "--"
        def col(v): return "#00C853" if v else "#d32f2f"
        self.check_rows["ipv4_dns"].set_value(fb(ck["ipv4_dns"]),col(ck["ipv4_dns"]))
        self.check_rows["ipv6_dns"].set_value(fb(ck["ipv6_dns"]),col(ck["ipv6_dns"]))
        self.check_rows["ipv4_http"].set_value(fb(ck["ipv4_http"]),col(ck["ipv4_http"]))
        self.check_rows["ipv6_http"].set_value(fb(ck["ipv6_http"]),col(ck["ipv6_http"]))
        self.check_rows["ipv4_latency"].set_value(fl(ck["ipv4_latency"]))
        self.check_rows["ipv6_latency"].set_value(fl(ck["ipv6_latency"]))

    def _build_export_data(self):
        d = {"本地接口":{},"公网信息":{},"IPv4_IPv6":{}}
        for k,r in self.local_rows.items(): d["本地接口"][k] = r.get_value()
        for k,r in self.public_rows.items(): d["公网信息"][k] = r.get_value()
        for k,r in self.check_rows.items(): d["IPv4_IPv6"][k] = r.get_value()
        return d

    def _export(self):
        fmt = self.fmt_combo.currentText().lower()
        data = self._build_export_data()
        default = f"IntTest_网络信息.{fmt}"
        path,_ = QFileDialog.getSaveFileName(self, "导出", default, f"*.{fmt}")
        if not path:
            return
        if not path.endswith(f".{fmt}"):
            path += guess_extension(fmt)
        do_export(data, path, fmt)
        InfoBar.success(title="导出成功", content=f"已保存", parent=self, duration=3000)
