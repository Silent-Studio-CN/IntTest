#!/usr/bin/env python3
"""设置页面 — User-Agent 自定义"""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout
from qfluentwidgets import (
    CardWidget, BodyLabel, StrongBodyLabel, SubtitleLabel,
    ComboBox, PrimaryPushButton, InfoBar,
    FluentIcon as FIF,
)
from app.core.config import PRESET_UA, set_user_agent


class SettingsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("settingsTab")
        self._setup_ui()

    def _setup_ui(self):
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(30, 24, 30, 24)
        vbox.setSpacing(16)
        vbox.addWidget(SubtitleLabel("⚙️ 设置"))

        # ── User-Agent ──
        card = CardWidget(self)
        layout = QVBoxLayout(card)
        layout.setSpacing(12)

        layout.addWidget(StrongBodyLabel("浏览器 User-Agent（仅用于测速请求）"))

        hint = BodyLabel(
            "某些 CDN / 镜像站会根据 User-Agent 限速或返回不同内容。\n"
            "选择不同的 UA 可以绕过部分限速策略，获得更真实的测速结果。",
            card
        )
        hint.setStyleSheet("color: #888; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        row = QHBoxLayout()
        self.ua_combo = ComboBox(card)
        for label in PRESET_UA:
            self.ua_combo.addItem(label)
        # 当前无 UA → 默认选中第一项
        row.addWidget(BodyLabel("User-Agent:", card))
        row.addWidget(self.ua_combo)
        row.addStretch()

        self.save_btn = PrimaryPushButton("保存", card)
        self.save_btn.setIcon(FIF.SAVE)
        self.save_btn.clicked.connect(self._save)
        row.addWidget(self.save_btn)
        layout.addLayout(row)

        vbox.addWidget(card)

        # ── 信息提示 ──
        info_card = CardWidget(self)
        info_layout = QVBoxLayout(info_card)
        info_layout.addWidget(StrongBodyLabel("💡 说明"))
        info_text = BodyLabel(
            "• 默认「不覆盖」使用 requests 库自带的 User-Agent\n"
            "• 不同 UA 可能影响 CDN 节点的选择\n"
            "• 保存后对后续所有测速请求生效\n"
            "• 无需重启应用", info_card
        )
        info_text.setStyleSheet("color: #bbb; font-size: 13px;")
        info_text.setWordWrap(True)
        info_layout.addWidget(info_text)
        vbox.addWidget(info_card)

        # ── 版权信息 ──
        copyright_card = CardWidget(self)
        copyright_card.setFixedHeight(200)
        copyright_card.setStyleSheet("""
            CardWidget {
                background-color: #0f1b33;
                border: 1px solid #1e3a5f;
                border-top: 3px solid #0f9b8e;
                border-radius: 12px;
            }
        """)
        c_layout = QVBoxLayout(copyright_card)
        c_layout.setAlignment(Qt.AlignCenter)
        c_layout.setSpacing(6)

        ver_lbl = StrongBodyLabel("Internet Test v2.3.0", copyright_card)
        ver_lbl.setAlignment(Qt.AlignCenter)
        ver_lbl.setStyleSheet("font-size: 22px; font-weight: bold; color: #e0e0e0; background: transparent;")

        div_lbl = BodyLabel("———————————————————", copyright_card)
        div_lbl.setAlignment(Qt.AlignCenter)
        div_lbl.setStyleSheet("color: #1e3a5f; font-size: 10px; background: transparent;")

        copy_lbl = BodyLabel(
            "© SilentStudio\n"
            "一款由 Silent Net. 团队开发，隶属于 SilentCodeTeams 旗下，\n"
            "并由 SilentStudio 管理的网络工具。",
            copyright_card
        )
        copy_lbl.setAlignment(Qt.AlignCenter)
        copy_lbl.setStyleSheet("color: #8899aa; font-size: 12px; line-height: 1.6; background: transparent;")
        copy_lbl.setWordWrap(True)

        c_layout.addWidget(ver_lbl)
        c_layout.addWidget(div_lbl)
        c_layout.addWidget(copy_lbl)
        vbox.addWidget(copyright_card)

    def _save(self):
        label = self.ua_combo.currentText()
        ua = PRESET_UA.get(label, "")
        set_user_agent(ua)
        InfoBar.success(title="已保存", content=f"User-Agent 已切换为: {label}", parent=self)
