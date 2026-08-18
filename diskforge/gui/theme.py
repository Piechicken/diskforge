"""Polished, accessibility-conscious application themes for DiskForge."""
from __future__ import annotations

from PySide6.QtWidgets import QApplication


_LIGHT = """
QWidget { background: #F6F8FC; color: #172033; font-family: "Noto Sans", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow { background: #F6F8FC; }
QLabel { background: transparent; }
QMenuBar { background: #101B35; color: #F8FAFC; padding: 5px 9px; border: 0; }
QMenuBar::item { background: transparent; border-radius: 6px; padding: 6px 10px; }
QMenuBar::item:selected { background: #243B68; }
QMenu { background: #FFFFFF; border: 1px solid #D9E2F2; border-radius: 8px; padding: 6px; }
QMenu::item { border-radius: 5px; padding: 7px 26px 7px 12px; }
QMenu::item:selected { background: #E9F0FF; color: #173F8A; }
QToolBar { background: #FFFFFF; border: 0; border-bottom: 1px solid #D9E2F2; padding: 7px 10px; spacing: 5px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 7px; color: #1B2D4D; padding: 6px 9px; }
QToolButton:hover { background: #EEF4FF; border-color: #C6D8FA; }
QToolButton:disabled { color: #9BA7B8; }
QFrame#workspaceHeader { background: #101B35; border: 0; border-radius: 12px; margin: 8px 10px 4px 10px; }
QLabel#workspaceTitle { color: #FFFFFF; font-size: 19px; font-weight: 700; }
QLabel#workspaceSubtitle { color: #B9C8E6; font-size: 11px; }
QLabel#workspaceBadge { background: #2563EB; color: #FFFFFF; border-radius: 10px; font-weight: 600; padding: 4px 9px; }
QTreeWidget, QTableWidget, QTextBrowser, QPlainTextEdit { background: #FFFFFF; alternate-background-color: #F7FAFF; border: 1px solid #D9E2F2; border-radius: 8px; gridline-color: #EAF0F8; selection-background-color: #DDEAFF; selection-color: #142B54; }
QTreeWidget::item, QTableWidget::item { padding: 5px; border: 0; }
QTreeWidget::item:hover, QTableWidget::item:hover { background: #F0F5FF; }
QHeaderView::section { background: #EDF2FA; color: #43536F; border: 0; border-bottom: 1px solid #D9E2F2; font-weight: 700; padding: 7px; }
QTabWidget::pane { border: 1px solid #D9E2F2; border-radius: 8px; background: #FFFFFF; top: -1px; }
QTabBar::tab { background: #EAF0F8; color: #52627D; border: 1px solid #D9E2F2; border-bottom: 0; border-top-left-radius: 7px; border-top-right-radius: 7px; padding: 7px 14px; margin-right: 2px; }
QTabBar::tab:selected { background: #FFFFFF; color: #183D88; font-weight: 700; }
QPushButton { background: #FFFFFF; border: 1px solid #C8D5E9; border-radius: 7px; color: #1A315A; font-weight: 600; min-height: 22px; padding: 5px 11px; }
QPushButton:hover { background: #EEF4FF; border-color: #7FA7EE; }
QPushButton:pressed { background: #DCE9FF; }
QPushButton:disabled { background: #F2F4F8; border-color: #E2E7EF; color: #A3ADBB; }
QLineEdit, QComboBox, QSpinBox, QDateTimeEdit, QPlainTextEdit { background: #FFFFFF; border: 1px solid #C8D5E9; border-radius: 6px; padding: 5px; selection-background-color: #2563EB; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus, QPlainTextEdit:focus { border: 2px solid #4C83E9; }
QStatusBar { background: #FFFFFF; border-top: 1px solid #D9E2F2; color: #52627D; padding: 4px 10px; }
QProgressBar { background: #E9EEF6; border: 0; border-radius: 6px; color: #183D88; text-align: center; min-height: 14px; }
QProgressBar::chunk { background: #2563EB; border-radius: 6px; }
QSplitter::handle { background: #E3EAF5; width: 2px; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 4px; }
QScrollBar::handle:vertical { background: #B8C6DC; border-radius: 5px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: #8CA4C8; }
"""

_DARK = """
QWidget { background: #111827; color: #E5EDF9; font-family: "Noto Sans", "Segoe UI", sans-serif; font-size: 13px; }
QMainWindow { background: #111827; }
QLabel { background: transparent; }
QMenuBar { background: #081121; color: #F8FAFC; padding: 5px 9px; border: 0; }
QMenuBar::item { background: transparent; border-radius: 6px; padding: 6px 10px; }
QMenuBar::item:selected { background: #263A61; }
QMenu { background: #1B263B; border: 1px solid #34445F; border-radius: 8px; padding: 6px; }
QMenu::item { border-radius: 5px; padding: 7px 26px 7px 12px; }
QMenu::item:selected { background: #294E95; }
QToolBar { background: #172137; border: 0; border-bottom: 1px solid #30405D; padding: 7px 10px; spacing: 5px; }
QToolButton { background: transparent; border: 1px solid transparent; border-radius: 7px; color: #DFE9FA; padding: 6px 9px; }
QToolButton:hover { background: #253D6D; border-color: #4875BC; }
QToolButton:disabled { color: #65748B; }
QFrame#workspaceHeader { background: #0B1730; border: 1px solid #25385C; border-radius: 12px; margin: 8px 10px 4px 10px; }
QLabel#workspaceTitle { color: #FFFFFF; font-size: 19px; font-weight: 700; }
QLabel#workspaceSubtitle { color: #AFC3E6; font-size: 11px; }
QLabel#workspaceBadge { background: #2563EB; color: #FFFFFF; border-radius: 10px; font-weight: 600; padding: 4px 9px; }
QTreeWidget, QTableWidget, QTextBrowser, QPlainTextEdit { background: #172137; alternate-background-color: #1A2943; border: 1px solid #31425F; border-radius: 8px; gridline-color: #2A3B56; selection-background-color: #294E95; selection-color: #FFFFFF; }
QTreeWidget::item, QTableWidget::item { padding: 5px; border: 0; }
QTreeWidget::item:hover, QTableWidget::item:hover { background: #223658; }
QHeaderView::section { background: #202E48; color: #BCCBE3; border: 0; border-bottom: 1px solid #31425F; font-weight: 700; padding: 7px; }
QTabWidget::pane { border: 1px solid #31425F; border-radius: 8px; background: #172137; top: -1px; }
QTabBar::tab { background: #202E48; color: #AAB9D1; border: 1px solid #31425F; border-bottom: 0; border-top-left-radius: 7px; border-top-right-radius: 7px; padding: 7px 14px; margin-right: 2px; }
QTabBar::tab:selected { background: #172137; color: #8AB4FF; font-weight: 700; }
QPushButton { background: #202E48; border: 1px solid #3A4E73; border-radius: 7px; color: #E4EEFF; font-weight: 600; min-height: 22px; padding: 5px 11px; }
QPushButton:hover { background: #294E95; border-color: #6F9CE8; }
QPushButton:pressed { background: #203F7D; }
QPushButton:disabled { background: #1C2739; border-color: #293750; color: #687993; }
QLineEdit, QComboBox, QSpinBox, QDateTimeEdit, QPlainTextEdit { background: #172137; border: 1px solid #3A4E73; border-radius: 6px; padding: 5px; selection-background-color: #3972CF; }
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDateTimeEdit:focus, QPlainTextEdit:focus { border: 2px solid #72A5FF; }
QStatusBar { background: #172137; border-top: 1px solid #30405D; color: #AAB9D1; padding: 4px 10px; }
QProgressBar { background: #25324A; border: 0; border-radius: 6px; color: #FFFFFF; text-align: center; min-height: 14px; }
QProgressBar::chunk { background: #3972CF; border-radius: 6px; }
QSplitter::handle { background: #2A3B56; width: 2px; }
QScrollBar:vertical { background: transparent; width: 11px; margin: 4px; }
QScrollBar::handle:vertical { background: #536A92; border-radius: 5px; min-height: 26px; }
QScrollBar::handle:vertical:hover { background: #7592C2; }
"""


def apply_theme(app: QApplication, mode: str = "light") -> str:
    """Apply a named global theme and return the normalized mode."""
    normalized = "dark" if mode.strip().lower() in {"dark", "midnight"} else "light"
    app.setStyleSheet(_DARK if normalized == "dark" else _LIGHT)
    return normalized
