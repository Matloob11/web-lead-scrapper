"""Shared UI components for the dashboard."""
# pylint: disable=no-name-in-module,too-few-public-methods

from typing import Any

from PySide6 import QtWidgets


class MetricCard(QtWidgets.QFrame):
    """Small dashboard card for a headline metric."""

    def __init__(self, title: str, accent: str) -> None:
        super().__init__()
        self.setObjectName("MetricCard")
        self.setMinimumHeight(60)
        self.setMaximumHeight(75)
        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred
        )

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(6)

        marker = QtWidgets.QFrame()
        marker.setFixedWidth(3)
        marker.setStyleSheet(f"background: {accent}; border-radius: 1px;")
        layout.addWidget(marker)

        content = QtWidgets.QVBoxLayout()
        content.setContentsMargins(0, 4, 0, 4)
        content.setSpacing(0)
        layout.addLayout(content, 1)

        self.title_label = QtWidgets.QLabel(title)
        self.title_label.setObjectName("MetricLabel")
        self.title_label.setWordWrap(True)

        self.value_label = QtWidgets.QLabel("0")
        self.value_label.setObjectName("MetricValue")

        content.addWidget(self.title_label)
        content.addWidget(self.value_label)
        content.addStretch(1)

    def set_metric(self, value: Any, _meta: str = "") -> None:
        """Update the visible metric value."""
        self.value_label.setText(str(value))


class Section(QtWidgets.QFrame):
    """Reusable bordered section with title and optional subtitle."""

    def __init__(self, title: str, _subtitle: str = "") -> None:
        super().__init__()
        self.setObjectName("Panel")

        self.body_layout = QtWidgets.QVBoxLayout(self)
        self.body_layout.setContentsMargins(12, 10, 12, 12)
        self.body_layout.setSpacing(8)

        if title:
            title_label = QtWidgets.QLabel(title)
            title_label.setObjectName("SectionTitle")
            self.body_layout.addWidget(title_label)
