#!/usr/bin/env python3
"""帮助文档页面"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout

from qfluentwidgets import (
    CardWidget, BodyLabel, StrongBodyLabel, SubtitleLabel,
    FluentIcon as FIF, PrimaryPushButton, InfoBar,
)


class HelpSection(CardWidget):
    def __init__(self, title: str, content: str, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.addWidget(StrongBodyLabel(title, self))
        lbl = BodyLabel(content, self)
        lbl.setWordWrap(True)
        lbl.setStyleSheet("color: #bbb; line-height: 1.6; font-size: 13px;")
        layout.addWidget(lbl)


class HelpTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("helpTab")
        self._setup_ui()

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(24, 24, 24, 24)
        vbox.setSpacing(16)

        vbox.addWidget(SubtitleLabel("📖 使用帮助"))

        sections = [
            ("⚡ 速度测试",
             "• 选择下载服务器（海外 / 国内线路）\n"
             "• 点击「开始测速」自动进行下载 & 上传测试\n"
             "• 下载采用 6 路 HTTP Range 并发，上传采用 4 路并发 POST\n"
             "• 持续 15 秒，实时显示瞬时速率和趋势图\n"
             "• 支持多服务器切换对比测试结果"),
            ("📊 实时监控",
             "• 监控电脑当前网络接口的实时上下行速率\n"
             "• 顶部显示当前活动接口名称、类型（有线/无线）、链路速率\n"
             "• 折线图记录过去 60 秒的速率变化\n"
             "• 底部显示开机以来的总流量统计"),
            ("🌐 连通性测试",
             "• 对百度、腾讯、阿里、GitHub、谷歌进行 Ping 测试\n"
             "• 结果以延迟（ms）显示，颜色区分：\n"
             "  - 绿色 < 100ms（优秀）  |  橙色 < 300ms（一般）  |  红色 ≥ 300ms（差）\n"
             "• 支持「自动刷新」每 5 秒自动测试一次"),
            ("🌐 网络信息检测",
             "• 显示本地网络接口详细信息\n"
             "• 查询公网 IPv4 / IPv6 地址\n"
             "• 显示运营商 ISP、地理位置、ASN 信息\n"
             "• 检测 IPv4 / IPv6 DNS 解析和 HTTP 连通性\n"
             "• 显示 IPv4 / IPv6 延迟对比"),
            ("💡 使用提示",
             "• 测速时请关闭其他占用带宽的应用（视频、下载等）\n"
             "• 有线连接通常比无线更稳定、速度更快\n"
             "• 国内用户建议选择「腾讯云」或「浙江大学」线路测试\n"
             "• 海外用户建议选择「Tele2」或「OVH」线路\n"
             "• 多次测试取平均值结果更准确"),
        ]

        for title, content in sections:
            section = HelpSection(title, content, self)
            vbox.addWidget(section)

        vbox.addStretch()
