#!/usr/bin/env python3
"""主窗口 — qfluentwidgets FluentWindow 多页面导航"""

from PySide6.QtCore import QTimer
from qfluentwidgets import FluentWindow, FluentIcon as FIF, NavigationItemPosition
from app.ui.speed_tab import SpeedTestTab
from app.ui.monitor_tab import MonitorTab
from app.ui.ping_tab import PingTab
from app.ui.network_info_tab import NetworkInfoTab
from app.ui.settings_tab import SettingsTab
from app.ui.help_tab import HelpTab


class MainWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("IntTest — 网络连通性与速度测试工具")
        self.setMinimumSize(1100, 780)
        self._closing = False

        self.speed_tab = SpeedTestTab(self)
        self.monitor_tab = MonitorTab(self)
        self.ping_tab = PingTab(self)
        self.netinfo_tab = NetworkInfoTab(self)
        self.settings_tab = SettingsTab(self)
        self.help_tab = HelpTab(self)

        self.addSubInterface(self.speed_tab, FIF.SPEED_HIGH, "速度测试", NavigationItemPosition.TOP)
        self.addSubInterface(self.monitor_tab, FIF.PIE_SINGLE, "实时监控", NavigationItemPosition.TOP)
        self.addSubInterface(self.ping_tab, FIF.WIFI, "连通性测试", NavigationItemPosition.TOP)
        self.addSubInterface(self.netinfo_tab, FIF.GLOBE, "网络信息", NavigationItemPosition.TOP)
        self.addSubInterface(self.settings_tab, FIF.SETTING, "设置", NavigationItemPosition.BOTTOM)
        self.addSubInterface(self.help_tab, FIF.HELP, "帮助", NavigationItemPosition.BOTTOM)

        self.navigationInterface.setExpandWidth(180)
        self.navigationInterface.setCollapsible(False)
        self.switchTo(self.speed_tab)

    def closeEvent(self, event):
        self._closing = True
        # 停止所有页面的后台线程
        for tab in (self.speed_tab, self.monitor_tab, self.netinfo_tab, self.ping_tab):
            for name in ("stop_workers", "stop_monitor"):
                fn = getattr(tab, name, None)
                if fn:
                    fn()
        super().closeEvent(event)
