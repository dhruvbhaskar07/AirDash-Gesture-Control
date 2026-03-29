import time
import os
import json
import winreg
import shlex
import re
import cv2
import copy
import keyboard
import pyautogui
from pathlib import Path
from typing import Optional
from threading import Thread

from PySide6.QtCore import QObject, Qt, QTimer, Signal, QSize, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QCloseEvent, QImage, QPixmap, QFont, QPainter, QColor, QPen, QBrush
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QGraphicsOpacityEffect,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from .constants import *
from .system_scanner import (
    _get_system_apps,
    _discover_cameras,
    _get_preferred_start_camera,
    _get_directshow_camera_names,
    _is_virtual_camera_name,
)
from .dialogs import CameraFullscreenDialog, GestureRecordPopup, CustomGestureBuilderDialog, NewGestureDialog
from core.vision_engine import VisionEngine

class UiBridge(QObject):
    frame_ready = Signal(object)
    gesture_ready = Signal(str)
    camera_ready = Signal()
    hands_ready = Signal(object)
    camera_scan_ready = Signal(object, bool, int)

    def on_frame(self, frame):
        self.frame_ready.emit(frame)

    def on_gesture(self, gesture):
        self.gesture_ready.emit(gesture)

    def on_camera_ready(self):
        self.camera_ready.emit()

    def on_hands(self, hands):
        self.hands_ready.emit(hands)

    def on_camera_scan_ready(self, devices, keep_current, previous_index):
        self.camera_scan_ready.emit(devices, keep_current, previous_index)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("AirDash \u2014 Hand Gesture Control")
        self.setMinimumSize(1020, 660)
        self.resize(1280, 780)

        self.camera_on = True
        self._is_resizing = False
        self._resume_timer = QTimer(self)
        self._resume_timer.setSingleShot(True)
        self._resume_timer.timeout.connect(self._finish_resize)
        self._last_geom = None
        self._last_frame_ts = 0.0
        self._max_fps = 60
        self._min_frame_interval = 1.0 / self._max_fps
        self._camera_devices = []
        self._camera_scan_in_progress = False
        self._camera_scan_pending = False
        self._camera_scan_pending_keep_current = True
        self._last_render_mode = "cpu"
        self._camera_fullscreen_dialog = None
        self._latest_hands_snapshot = []
        self._latest_camera_image = None

        # Session stats
        self._gesture_count = 0
        self._action_count = 0
        self._session_start = time.time()
        self._last_gesture = ""
        self._last_gesture_time = 0.0
        self._cooldown_timer = QTimer(self)
        self._cooldown_timer.setSingleShot(True)
        self._cooldown_timer.timeout.connect(self._reset_gesture_highlight)

        self.bridge = UiBridge()
        self.bridge.frame_ready.connect(self._on_frame_ready)
        self.bridge.gesture_ready.connect(self._on_gesture_ready)
        self.bridge.camera_ready.connect(self._on_camera_ready)
        self.bridge.hands_ready.connect(self._on_hands_ready)
        self.bridge.camera_scan_ready.connect(self._on_camera_scan_ready)

        self.vision_engine = VisionEngine(
            update_image_callback=self.bridge.on_frame,
            update_gesture_callback=self.bridge.on_gesture,
            camera_ready_callback=self.bridge.on_camera_ready,
            update_hands_callback=self.bridge.on_hands,
        )
        self.vision_engine.set_target_fps(self._max_fps)
        self._last_render_mode = self.vision_engine.get_render_device()
        self.action_mapper = self.vision_engine.action_mapper

        self._build_ui()
        self._apply_theme()
        self._init_render_options()
        self._prime_camera_selector()
        self.vision_engine.start()
        QTimer.singleShot(1500, lambda: self._refresh_camera_devices(keep_current=True))
        self._animate_entry()
        self.refresh_mappings()

        # Start session timer for uptime display
        self._uptime_timer = QTimer(self)
        self._uptime_timer.timeout.connect(self._update_footer_stats)
        self._uptime_timer.start(1000)

    def _build_ui(self):
        root = QWidget(self)
        self.setCentralWidget(root)

        shell = QHBoxLayout(root)
        shell.setContentsMargins(12, 12, 12, 12)
        shell.setSpacing(12)

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        #  SIDEBAR
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(360)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(16, 16, 16, 16)
        side.setSpacing(10)

        # Brand header
        brand_row = QHBoxLayout()
        brand_icon = QLabel("\u270B")
        brand_icon.setStyleSheet(f"font-size: 22px; background: transparent; border: none;")
        brand = QLabel("AirDash")
        brand.setObjectName("brand")
        brand_row.addWidget(brand_icon)
        brand_row.addWidget(brand)
        brand_row.addStretch(1)
        side.addLayout(brand_row)

        sub_brand = QLabel("Hand Gesture Control System")
        sub_brand.setObjectName("muted")
        side.addWidget(sub_brand)

        side.addSpacing(4)

        # â”€â”€ Camera section â”€â”€
        cam_row = QHBoxLayout()
        cam_label = QLabel("LIVE FEED")
        cam_label.setObjectName("section")
        self.camera_indicator = QLabel("")
        self.camera_indicator.setObjectName("indicatorIdle")
        self.camera_status_label = QLabel("STARTING")
        self.camera_status_label.setObjectName("statusBadge")
        self.camera_status_label.setProperty("state", "connecting")
        cam_row.addWidget(cam_label)
        cam_row.addStretch(1)
        cam_row.addWidget(self.camera_status_label)
        cam_row.addWidget(self.camera_indicator)

        cam_pick_row = QHBoxLayout()
        cam_pick_row.setContentsMargins(0, 0, 0, 0)
        cam_pick_row.setSpacing(6)
        self.camera_selector = QComboBox()
        self.camera_selector.setObjectName("cameraSelect")
        self.camera_selector.currentIndexChanged.connect(self._on_camera_selected)
        self.camera_refresh_btn = QPushButton("Scan")
        self.camera_refresh_btn.setObjectName("cameraScanBtn")
        self.camera_refresh_btn.setCursor(Qt.PointingHandCursor)
        self.camera_refresh_btn.clicked.connect(lambda _: self._refresh_camera_devices(keep_current=True))
        cam_pick_row.addWidget(self.camera_selector, 1)
        cam_pick_row.addWidget(self.camera_refresh_btn)

        fps_row = QHBoxLayout()
        fps_row.setContentsMargins(0, 0, 0, 0)
        fps_row.setSpacing(6)
        fps_label = QLabel("MAX FPS")
        fps_label.setObjectName("section")
        self.fps_selector = QComboBox()
        self.fps_selector.setObjectName("fpsSelect")
        self.fps_selector.addItem("60 FPS", 60)
        self.fps_selector.addItem("90 FPS", 90)
        self.fps_selector.addItem("120 FPS", 120)
        self.fps_selector.addItem("System FPS", 0)
        self.fps_selector.currentIndexChanged.connect(self._on_fps_selected)
        fps_row.addWidget(fps_label)
        fps_row.addStretch(1)
        fps_row.addWidget(self.fps_selector)

        render_row = QHBoxLayout()
        render_row.setContentsMargins(0, 0, 0, 0)
        render_row.setSpacing(6)
        render_label = QLabel("RENDER MODE")
        render_label.setObjectName("section")
        self.render_selector = QComboBox()
        self.render_selector.setObjectName("renderSelect")
        self.render_selector.currentIndexChanged.connect(self._on_render_mode_selected)
        render_row.addWidget(render_label)
        render_row.addStretch(1)
        render_row.addWidget(self.render_selector)

        self.camera_label = QLabel("Initializing Camera...")
        self.camera_label.setObjectName("camera")
        self.camera_label.setAlignment(Qt.AlignCenter)
        self.camera_label.setMinimumHeight(220)

        self.camera_toggle_btn = QPushButton("\u23F8  Pause Camera")
        self.camera_toggle_btn.setObjectName("cameraBtn")
        self.camera_toggle_btn.setCursor(Qt.PointingHandCursor)
        self.camera_toggle_btn.clicked.connect(self.toggle_camera)

        self.camera_fullscreen_btn = QPushButton("\u26F6  Full Screen")
        self.camera_fullscreen_btn.setObjectName("cameraSecondaryBtn")
        self.camera_fullscreen_btn.setCursor(Qt.PointingHandCursor)
        self.camera_fullscreen_btn.clicked.connect(self.toggle_camera_fullscreen)

        cam_btn_row = QHBoxLayout()
        cam_btn_row.setContentsMargins(0, 0, 0, 0)
        cam_btn_row.setSpacing(6)
        cam_btn_row.addWidget(self.camera_toggle_btn, 1)
        cam_btn_row.addWidget(self.camera_fullscreen_btn)

        side.addLayout(cam_row)
        side.addLayout(cam_pick_row)
        side.addLayout(fps_row)
        side.addLayout(render_row)
        side.addWidget(self.camera_label)
        side.addLayout(cam_btn_row)

        side.addSpacing(4)

        # â”€â”€ Detected gesture panel â”€â”€
        status_title = QLabel("DETECTED GESTURE")
        status_title.setObjectName("section")
        self.status_panel = QFrame()
        self.status_panel.setObjectName("statusPanel")
        status_layout = QHBoxLayout(self.status_panel)
        status_layout.setContentsMargins(12, 10, 12, 10)
        status_layout.setSpacing(10)

        self.status_icon = QLabel("\u2022")
        self.status_icon.setObjectName("statusIcon")
        self.status_icon.setFixedSize(QSize(44, 44))
        self.status_icon.setAlignment(Qt.AlignCenter)

        status_col = QVBoxLayout()
        status_col.setSpacing(1)
        self.status_label = QLabel("Waiting...")
        self.status_label.setObjectName("statusMain")
        self.status_action_label = QLabel("Move your hand to activate")
        self.status_action_label.setObjectName("statusSub")
        status_col.addWidget(self.status_label)
        status_col.addWidget(self.status_action_label)

        self.cooldown_bar = QProgressBar()
        self.cooldown_bar.setObjectName("cooldownBar")
        self.cooldown_bar.setFixedHeight(3)
        self.cooldown_bar.setRange(0, 100)
        self.cooldown_bar.setValue(0)
        self.cooldown_bar.setTextVisible(False)

        status_layout.addWidget(self.status_icon)
        status_layout.addLayout(status_col, 1)

        side.addWidget(status_title)
        side.addWidget(self.status_panel)
        side.addWidget(self.cooldown_bar)

        side.addSpacing(4)

        # â”€â”€ Active bindings quick view â”€â”€
        guide_row = QHBoxLayout()
        guide_row.setContentsMargins(0, 0, 2, 0)
        guide_row.setSpacing(6)
        guide_title = QLabel("ACTIVE BINDINGS")
        guide_title.setObjectName("section")
        self.binding_count_label = QLabel("0")
        self.binding_count_label.setObjectName("countBadge")
        self.binding_count_label.setAlignment(Qt.AlignCenter)
        self.binding_count_label.setFixedHeight(20)
        self.binding_count_label.setMinimumWidth(28)
        guide_row.addWidget(guide_title)
        guide_row.addStretch(1)
        guide_row.addWidget(self.binding_count_label, 0, Qt.AlignRight | Qt.AlignVCenter)

        self.guide_list = QListWidget()
        self.guide_list.setObjectName("guide")

        side.addLayout(guide_row)
        side.addWidget(self.guide_list, 1)

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        #  MAIN CONTENT PANEL
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        main_frame = QFrame()
        main_frame.setObjectName("main")
        main_layout = QVBoxLayout(main_frame)
        main_layout.setContentsMargins(20, 18, 20, 14)
        main_layout.setSpacing(10)

        # â”€â”€ Header row â”€â”€
        top = QHBoxLayout()
        top_col = QVBoxLayout()
        top_col.setSpacing(2)
        top_title = QLabel("Command Center")
        top_title.setObjectName("header")
        self.stats_label = QLabel("0 active bindings")
        self.stats_label.setObjectName("muted")
        top_col.addWidget(top_title)
        top_col.addWidget(self.stats_label)

        self.refresh_btn = QPushButton("\u21BB  Refresh")
        self.refresh_btn.setObjectName("headerBtn")
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_mappings)

        self.add_btn = QPushButton("+  New Gesture")
        self.add_btn.setObjectName("addBtn")
        self.add_btn.setCursor(Qt.PointingHandCursor)
        self.add_btn.clicked.connect(self.open_inline_new_gesture)

        top.addLayout(top_col)
        top.addStretch(1)
        top.addWidget(self.refresh_btn)
        top.addSpacing(6)
        top.addWidget(self.add_btn)

        main_layout.addLayout(top)
        main_layout.addSpacing(4)

        # â”€â”€ Center content stack â”€â”€
        self.center_stack = QStackedWidget()

        self._map_page = QWidget()
        map_page_layout = QVBoxLayout(self._map_page)
        map_page_layout.setContentsMargins(0, 0, 0, 0)
        map_page_layout.setSpacing(0)
        self.mapping_list = QListWidget()
        self.mapping_list.setObjectName("mapping")
        map_page_layout.addWidget(self.mapping_list, 1)
        self.center_stack.addWidget(self._map_page)

        self._inline_builder_page = QWidget()
        inline_layout = QVBoxLayout(self._inline_builder_page)
        inline_layout.setContentsMargins(0, 0, 0, 0)
        inline_layout.setSpacing(8)

        inline_top = QHBoxLayout()
        inline_title = QLabel("Create Custom Gesture")
        inline_title.setObjectName("header")
        inline_title.setStyleSheet("font-size: 18px;")
        self.inline_back_btn = QPushButton("\u2190 Back to Mappings")
        self.inline_back_btn.setObjectName("headerBtn")
        self.inline_back_btn.setCursor(Qt.PointingHandCursor)
        self.inline_back_btn.clicked.connect(self.close_inline_new_gesture)
        inline_top.addWidget(inline_title)
        inline_top.addStretch(1)
        inline_top.addWidget(self.inline_back_btn)
        inline_layout.addLayout(inline_top)

        self.inline_builder = CustomGestureBuilderDialog(
            self,
            get_live_hands=lambda: self._latest_hands_snapshot,
            get_live_frame=lambda: self._latest_camera_image,
            embedded=True,
        )
        self.inline_builder.created.connect(self._on_inline_custom_created)

        inline_scroll = QScrollArea()
        inline_scroll.setObjectName("inlineScroll")
        inline_scroll.setWidgetResizable(True)
        inline_scroll.setFrameShape(QFrame.NoFrame)
        inline_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inline_scroll.setWidget(self.inline_builder)
        inline_layout.addWidget(inline_scroll, 1)
        self.center_stack.addWidget(self._inline_builder_page)
        self.center_stack.setCurrentWidget(self._map_page)

        main_layout.addWidget(self.center_stack, 1)

        # â”€â”€ Footer stats bar â”€â”€
        footer = QFrame()
        footer.setObjectName("footer")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(12, 8, 12, 8)
        footer_layout.setSpacing(16)

        self._foot_gestures = QLabel("Gestures: 0")
        self._foot_gestures.setObjectName("footStat")
        self._foot_actions = QLabel("Actions: 0")
        self._foot_actions.setObjectName("footStat")
        self._foot_uptime = QLabel("Uptime: 0:00")
        self._foot_uptime.setObjectName("footStat")
        self._foot_status = QLabel("\u2022  System Ready")
        self._foot_status.setObjectName("footStatus")

        footer_layout.addWidget(self._foot_gestures)
        footer_layout.addWidget(self._foot_actions)
        footer_layout.addWidget(self._foot_uptime)
        footer_layout.addStretch(1)
        footer_layout.addWidget(self._foot_status)

        main_layout.addWidget(footer)

        shell.addWidget(self.sidebar)
        shell.addWidget(main_frame, 1)

    def _apply_theme(self):
        self.setStyleSheet(f"""
            QMainWindow {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {CLR_BG}, stop:0.55 {CLR_BG_ALT}, stop:1 #060606);
                color: {CLR_TEXT};
                font-family: {FONT_FAMILY};
            }}

            /* â”€â”€ Sidebar â”€â”€ */
            QFrame#sidebar {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #0E0E0E, stop:1 #070707);
                border: 1px solid {CLR_BORDER};
                border-radius: 14px;
            }}
            QLabel#brand {{
                color: {CLR_WHITE};
                font-size: 28px;
                font-weight: 700;
                letter-spacing: 0.5px;
                background: transparent;
                border: none;
            }}
            QLabel#section {{
                color: {CLR_TEXT_MUTED};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.5px;
                background: transparent;
                border: none;
            }}
            QLabel#muted {{
                color: {CLR_TEXT_DIM};
                font-size: 11px;
                background: transparent;
                border: none;
            }}

            /* â”€â”€ Camera â”€â”€ */
            QLabel#camera {{
                background: {CLR_GLASS_ALT};
                border: 1px solid {CLR_BORDER};
                border-radius: 12px;
                color: {CLR_TEXT_MUTED};
                font-size: 12px;
            }}
            QPushButton#cameraBtn {{
                background: {CLR_ACCENT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 32px;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton#cameraBtn:hover {{
                background: {CLR_ACCENT_HOVER};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
            QPushButton#cameraSecondaryBtn {{
                background: {CLR_ACCENT_DIM};
                color: {CLR_TEXT_DIM};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 32px;
                padding: 0 12px;
                font-weight: 600;
                font-size: 11px;
            }}
            QPushButton#cameraSecondaryBtn:hover {{
                background: {CLR_ACCENT};
                color: {CLR_WHITE};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
            QLabel#cameraFullscreen {{
                background: #000000;
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                color: {CLR_TEXT_MUTED};
                font-size: 14px;
            }}
            QComboBox#cameraSelect {{
                background: {CLR_INPUT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 28px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QComboBox#cameraSelect:focus {{
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
            QComboBox#cameraSelect QAbstractItemView {{
                background: {CLR_SURFACE};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                selection-background-color: {CLR_SELECTED};
            }}
            QComboBox#fpsSelect {{
                background: {CLR_INPUT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 28px;
                min-width: 120px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QComboBox#fpsSelect:focus {{
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
            QComboBox#fpsSelect QAbstractItemView {{
                background: {CLR_SURFACE};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                selection-background-color: {CLR_SELECTED};
            }}
            QComboBox#renderSelect {{
                background: {CLR_INPUT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 28px;
                min-width: 120px;
                padding: 2px 8px;
                font-size: 11px;
            }}
            QComboBox#renderSelect:focus {{
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
            QComboBox#renderSelect QAbstractItemView {{
                background: {CLR_SURFACE};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                selection-background-color: {CLR_SELECTED};
            }}
            QPushButton#cameraScanBtn {{
                background: {CLR_ACCENT_DIM};
                color: {CLR_TEXT_DIM};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 28px;
                padding: 0 10px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#cameraScanBtn:hover {{
                background: {CLR_ACCENT};
                color: {CLR_WHITE};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}

            /* â”€â”€ Camera status badge â”€â”€ */
            QLabel#statusBadge {{
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 0.5px;
                padding: 2px 8px;
                border-radius: 4px;
                background: transparent;
                border: none;
            }}
            QLabel#statusBadge[state="connecting"] {{
                color: {CLR_ORANGE};
            }}
            QLabel#statusBadge[state="active"] {{
                color: {CLR_GREEN};
            }}
            QLabel#statusBadge[state="paused"] {{
                color: {CLR_RED};
            }}

            /* â”€â”€ Indicators â”€â”€ */
            QLabel#indicatorIdle {{
                background: {CLR_ORANGE};
                border-radius: 5px;
                min-width: 10px; max-width: 10px;
                min-height: 10px; max-height: 10px;
            }}
            QLabel#indicatorActive {{
                background: {CLR_GREEN};
                border-radius: 5px;
                min-width: 10px; max-width: 10px;
                min-height: 10px; max-height: 10px;
            }}
            QLabel#indicatorPaused {{
                background: {CLR_RED};
                border-radius: 5px;
                min-width: 10px; max-width: 10px;
                min-height: 10px; max-height: 10px;
            }}

            /* â”€â”€ Gesture status panel â”€â”€ */
            QFrame#statusPanel {{
                background: {CLR_GLASS};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 12px;
            }}
            QFrame#statusPanel[active="true"] {{
                border: 1px solid {CLR_GREEN_DIM};
            }}
            QLabel#statusIcon {{
                background: {CLR_ACCENT_DIM};
                border: 1px solid {CLR_BORDER};
                border-radius: 10px;
                color: {CLR_WHITE};
                font-size: 20px;
            }}
            QLabel#statusMain {{
                color: {CLR_WHITE};
                font-size: 20px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}
            QLabel#statusSub {{
                color: {CLR_TEXT_DIM};
                font-size: 11px;
                background: transparent;
                border: none;
            }}

            /* â”€â”€ Cooldown bar â”€â”€ */
            QProgressBar#cooldownBar {{
                background: {CLR_BORDER_SOFT};
                border: none;
                border-radius: 1px;
            }}
            QProgressBar#cooldownBar::chunk {{
                background: {CLR_GREEN};
                border-radius: 1px;
            }}

            /* â”€â”€ Count badge â”€â”€ */
            QLabel#countBadge {{
                background: {CLR_ACCENT};
                color: {CLR_TEXT_DIM};
                border-radius: 10px;
                min-width: 28px;
                min-height: 20px;
                font-size: 10px;
                font-weight: 700;
                padding: 0 6px;
                border: none;
            }}

            /* â”€â”€ Active bindings list â”€â”€ */
            QListWidget#guide {{
                background: {CLR_SURFACE};
                border: 1px solid {CLR_BORDER};
                border-radius: 10px;
                color: {CLR_TEXT};
                padding: 6px;
                outline: none;
                font-size: 11px;
            }}
            QListWidget#guide::item {{
                border: none;
                margin: 1px 0px;
                padding: 5px 8px;
                border-radius: 6px;
            }}
            QListWidget#guide::item:hover {{
                background: {CLR_ACCENT_DIM};
            }}

            /* â”€â”€ Main panel â”€â”€ */
            QFrame#main {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 #111111, stop:1 #0A0A0A);
                border: 1px solid {CLR_BORDER};
                border-radius: 14px;
            }}
            QLabel#header {{
                color: {CLR_WHITE};
                font-size: 30px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            /* â”€â”€ Header buttons â”€â”€ */
            QPushButton#headerBtn {{
                background: {CLR_ACCENT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 34px;
                padding: 0 14px;
                font-weight: 600;
                font-size: 12px;
            }}
            QPushButton#headerBtn:hover {{
                background: {CLR_ACCENT_HOVER};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
            QPushButton#addBtn {{
                background: {CLR_ACCENT};
                color: {CLR_WHITE};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 34px;
                padding: 0 16px;
                font-weight: 700;
                font-size: 12px;
            }}
            QPushButton#addBtn:hover {{
                background: {CLR_ACCENT_HOVER};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}

            QScrollArea#inlineScroll {{
                background: transparent;
                border: none;
            }}
            QScrollArea#inlineScroll > QWidget > QWidget {{
                background: transparent;
            }}
            QScrollBar:vertical {{
                background: {CLR_SURFACE};
                width: 8px;
                margin: 2px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {CLR_ACCENT_DIM};
                min-height: 24px;
                border-radius: 4px;
            }}
            QScrollBar::handle:vertical:hover {{
                background: {CLR_ACCENT};
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}

            /* â”€â”€ Mapping list â”€â”€ */
            QListWidget#mapping {{
                background: {CLR_SURFACE};
                border: 1px solid {CLR_BORDER};
                border-radius: 12px;
                color: {CLR_TEXT};
                padding: 8px;
                outline: none;
            }}
            QListWidget#mapping::item {{
                border: none;
                margin: 3px 2px;
                padding: 0px;
                border-radius: 10px;
            }}

            /* â”€â”€ Footer â”€â”€ */
            QFrame#footer {{
                background: {CLR_GLASS};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 10px;
            }}
            QLabel#footStat {{
                color: {CLR_TEXT_MUTED};
                font-size: 10px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            QLabel#footStatus {{
                color: {CLR_GREEN};
                font-size: 10px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}

            /* â”€â”€ Generic mapping card buttons â”€â”€ */
            QPushButton#removeBtn {{
                background: {CLR_RED_BG};
                color: {CLR_RED};
                border: 1px solid {CLR_RED_DIM};
                border-radius: 6px;
                min-height: 28px;
                min-width: 70px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#removeBtn:hover {{
                background: {CLR_RED_DIM};
                color: {CLR_WHITE};
            }}
        """)

    def _animate_entry(self):
        self.setWindowOpacity(0.0)
        self._entry_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._entry_anim.setDuration(400)
        self._entry_anim.setStartValue(0.0)
        self._entry_anim.setEndValue(1.0)
        self._entry_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._entry_anim.start()

    # â”€â”€ Mapping list â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def refresh_mappings(self):
        self.mapping_list.clear()
        self.guide_list.clear()

        mapping_count = len(self.action_mapper.mappings)
        builtin_count = sum(1 for g in self.action_mapper.mappings if g in AVAILABLE_GESTURES)
        avail_count = max(0, len(AVAILABLE_GESTURES) - builtin_count)
        self.stats_label.setText(f"{mapping_count} active  \u00B7  {avail_count} available")
        self.binding_count_label.setText(str(mapping_count))

        if not self.action_mapper.mappings:
            empty_item = QListWidgetItem(self.mapping_list)
            empty_item.setSizeHint(QSize(0, 80))
            empty_widget = QWidget()
            empty_layout = QVBoxLayout(empty_widget)
            empty_layout.setAlignment(Qt.AlignCenter)
            empty_label = QLabel("No gesture mappings yet")
            empty_label.setAlignment(Qt.AlignCenter)
            empty_label.setStyleSheet(f"color: {CLR_TEXT_MUTED}; font-size: 14px;")
            empty_sub = QLabel("Click \"+ New Gesture\" to create your first mapping")
            empty_sub.setAlignment(Qt.AlignCenter)
            empty_sub.setStyleSheet(f"color: {CLR_TEXT_MUTED}; font-size: 11px;")
            empty_layout.addWidget(empty_label)
            empty_layout.addWidget(empty_sub)
            self.mapping_list.addItem(empty_item)
            self.mapping_list.setItemWidget(empty_item, empty_widget)
            self.guide_list.addItem("No bindings configured")
            return

        for gesture_name, mapping in self.action_mapper.mappings.items():
            display_keys = " + ".join(mapping.get("keys", [])) or mapping.get("description", "")
            is_custom = str(gesture_name).startswith("Custom:")
            gesture_icon = "\U0001F4A1" if is_custom else GESTURE_ICONS.get(gesture_name, "\u2022")
            gesture_display = gesture_name.replace("Custom:", "").replace("_", " ")
            self.guide_list.addItem(f"  {gesture_icon}  {gesture_display}  \u2192  {display_keys}")
            self._create_mapping_card(gesture_name, mapping)

    def _create_mapping_card(self, gesture_name, mapping):
        item = QListWidgetItem(self.mapping_list)
        item.setSizeHint(QSize(0, 74))

        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {CLR_CARD};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 10px;
            }}
            QFrame:hover {{
                background: {CLR_CARD_HOVER};
                border: 1px solid {CLR_BORDER};
            }}
        """)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Gesture emoji icon
        is_custom = str(gesture_name).startswith("Custom:")
        icon = QLabel("\U0001F4A1" if is_custom else GESTURE_ICONS.get(gesture_name, "\u2022"))
        icon.setFixedSize(40, 40)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"""
            background: {CLR_ACCENT_DIM};
            border: 1px solid {CLR_BORDER};
            border-radius: 10px;
            font-size: 18px;
        """)

        # Text column
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name = QLabel(gesture_name.replace("Custom:", "").replace("_", " "))
        name.setStyleSheet(f"color: {CLR_WHITE}; font-size: 14px; font-weight: 700; border: none; background: transparent;")

        action_type = mapping.get("action_type", "shortcut")
        keys = " + ".join(mapping.get("keys", [])).upper()
        desc = mapping.get("description", "Custom action")
        action_icon = ACTION_ICONS.get(action_type, "\u2328")

        detail = QLabel(f"{action_icon}  {ACTION_LABELS.get(action_type, action_type)}  \u00B7  {keys or desc}")
        detail.setStyleSheet(f"color: {CLR_TEXT_DIM}; font-size: 11px; border: none; background: transparent;")

        text_col.addWidget(name)
        text_col.addWidget(detail)

        # Remove button
        remove_btn = QPushButton("Remove")
        remove_btn.setObjectName("removeBtn")
        remove_btn.setCursor(Qt.PointingHandCursor)
        remove_btn.setFixedWidth(70)
        remove_btn.clicked.connect(lambda _=False, g=gesture_name: self.delete_mapping(g))

        layout.addWidget(icon)
        layout.addLayout(text_col, 1)
        layout.addWidget(remove_btn)

        self.mapping_list.addItem(item)
        self.mapping_list.setItemWidget(item, card)

    # â”€â”€ Camera feed â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _on_hands_ready(self, hands):
        self._latest_hands_snapshot = hands or []

    def _on_frame_ready(self, rgb_frame):
        if not self.camera_on or self._is_resizing:
            return

        now = time.perf_counter()
        if self._min_frame_interval > 0 and (now - self._last_frame_ts) < self._min_frame_interval:
            return
        self._last_frame_ts = now

        if rgb_frame is None:
            return

        h, w, c = rgb_frame.shape
        if c != 3:
            return

        bytes_per_line = c * w
        image = QImage(rgb_frame.data, w, h, bytes_per_line, QImage.Format_RGB888).copy()
        self._latest_camera_image = image
        target_w = max(220, self.sidebar.width() - 38)
        target_h = max(140, int((target_w / max(1, w)) * h))
        pixmap = QPixmap.fromImage(image).scaled(target_w, target_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.camera_label.setPixmap(pixmap)
        self.camera_label.setText("")

        if self._camera_fullscreen_dialog and self._camera_fullscreen_dialog.isVisible():
            self._camera_fullscreen_dialog.update_frame(image)

    # â”€â”€ Gesture detection feedback â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _on_gesture_ready(self, text):
        if not text:
            return

        self._gesture_count += 1
        self._last_gesture = text
        self._last_gesture_time = time.time()

        self.status_label.setText(text.replace("_", " "))
        self.status_icon.setText(GESTURE_ICONS.get(text, "\u2022"))

        if text in self.action_mapper.mappings:
            mapping = self.action_mapper.mappings[text]
            desc = mapping.get("description", "")
            keys = " + ".join(mapping.get("keys", [])).upper()
            self.status_action_label.setText(f"\u2713  {desc or keys or 'Executing action...'}")
            self.status_action_label.setStyleSheet(f"color: {CLR_GREEN}; font-size: 11px; background: transparent; border: none;")
            self._action_count += 1

            # Show cooldown feedback
            self.cooldown_bar.setValue(100)
            self.status_panel.setProperty("active", "true")
            self.status_panel.style().unpolish(self.status_panel)
            self.status_panel.style().polish(self.status_panel)

            self._cooldown_timer.start(1000)
        else:
            self.status_action_label.setText("No action mapped")
            self.status_action_label.setStyleSheet(f"color: {CLR_TEXT_DIM}; font-size: 11px; background: transparent; border: none;")

    def _reset_gesture_highlight(self):
        self.cooldown_bar.setValue(0)
        self.status_panel.setProperty("active", "false")
        self.status_panel.style().unpolish(self.status_panel)
        self.status_panel.style().polish(self.status_panel)

    # â”€â”€ Camera state â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _on_fullscreen_closed(self):
        self.camera_fullscreen_btn.setText("\u26F6  Full Screen")

    def toggle_camera_fullscreen(self):
        if self._camera_fullscreen_dialog and self._camera_fullscreen_dialog.isVisible():
            self._camera_fullscreen_dialog.close()
            self._camera_fullscreen_dialog = None
            return

        self._camera_fullscreen_dialog = CameraFullscreenDialog(self, on_close=self._on_fullscreen_closed)
        self._camera_fullscreen_dialog.showFullScreen()
        self.camera_fullscreen_btn.setText("\u2715  Exit Full")

    def _set_camera_badge(self, text, state="connecting", indicator="idle"):
        self.camera_status_label.setText(text)
        self.camera_status_label.setProperty("state", state)
        if indicator == "active":
            self.camera_indicator.setObjectName("indicatorActive")
        elif indicator == "paused":
            self.camera_indicator.setObjectName("indicatorPaused")
        else:
            self.camera_indicator.setObjectName("indicatorIdle")
        self.camera_status_label.style().unpolish(self.camera_status_label)
        self.camera_status_label.style().polish(self.camera_status_label)
        self.camera_indicator.style().unpolish(self.camera_indicator)
        self.camera_indicator.style().polish(self.camera_indicator)

    def _on_camera_ready(self):
        self._set_camera_badge("LIVE", state="active", indicator="active")
        self._foot_status.setText(f"\u2022  Camera Active")
        self._foot_status.setStyleSheet(f"color: {CLR_GREEN}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    def _init_render_options(self):
        _ = self.vision_engine.get_available_render_devices()
        self.render_selector.blockSignals(True)
        self.render_selector.clear()
        self.render_selector.addItem("CPU", "cpu")
        self.render_selector.addItem("GPU", "gpu")
        cpu_idx = self.render_selector.findData("cpu")
        self.render_selector.setCurrentIndex(max(0, cpu_idx))
        self.render_selector.blockSignals(False)

        response = self.vision_engine.set_render_device("cpu")
        msg = response.get("message", "CPU mode enabled")
        self._foot_status.setText(f"\u2022  {msg}")
        self._foot_status.setStyleSheet(f"color: {CLR_GREEN}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    def _on_fps_selected(self, combo_index):
        fps_value = self.fps_selector.itemData(combo_index)
        if fps_value is None:
            return
        try:
            target_fps = int(fps_value)
        except (TypeError, ValueError):
            return
        if target_fps < 0:
            return

        self._max_fps = target_fps
        self._min_frame_interval = 0.0 if target_fps == 0 else (1.0 / target_fps)
        self.vision_engine.set_target_fps(target_fps)

        if target_fps == 0:
            msg = "Max FPS set to System FPS"
        else:
            msg = f"Max FPS set to {target_fps}"
        self._foot_status.setText(f"\u2022  {msg}")
        self._foot_status.setStyleSheet(f"color: {CLR_GREEN}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    def _on_render_mode_selected(self, combo_index):
        mode = self.render_selector.itemData(combo_index)
        if mode is None:
            return
        mode = str(mode).lower()
        previous = self.vision_engine.get_render_device()
        if mode == previous:
            return

        response = self.vision_engine.set_render_device(mode)
        ok = bool(response.get("ok"))
        active = str(response.get("active", self.vision_engine.get_render_device())).lower()
        msg = response.get("message", f"Render mode: {mode.upper()}")
        color = CLR_GREEN if ok else CLR_RED

        self._set_camera_badge("APPLYING MODE", state="connecting", indicator="idle")
        self._foot_status.setText(f"\u2022  {msg}")
        self._foot_status.setStyleSheet(f"color: {color}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
        self._last_render_mode = active

        if ok and active == "gpu":
            QMessageBox.information(self, "GPU Activated", "GPU mode is active and rendering is now on GPU.")
        elif ok and active == "cpu":
            QMessageBox.information(self, "CPU Activated", "CPU mode is active and rendering is now on CPU.")

        if mode == "gpu" and not ok:
            QMessageBox.warning(self, "GPU Not Connecting", "GPU is not connecting. Software switched to CPU mode.")
            self.vision_engine.set_render_device("cpu")
            cpu_idx = self.render_selector.findData("cpu")
            if cpu_idx >= 0:
                self.render_selector.blockSignals(True)
                self.render_selector.setCurrentIndex(cpu_idx)
                self.render_selector.blockSignals(False)
            self._last_render_mode = "cpu"
            self._foot_status.setText("\u2022  GPU is not connecting. Running on CPU.")
            self._foot_status.setStyleSheet(f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    def _prime_camera_selector(self):
        """Populate a safe default camera immediately so stream startup can begin."""
        saved_camera = self._load_saved_camera_index()
        auto_preferred_camera = _get_preferred_start_camera(max_index=8, fallback=0)
        preferred_camera = auto_preferred_camera

        if saved_camera is not None:
            names = _get_directshow_camera_names()
            saved_name = ""
            if 0 <= int(saved_camera) < len(names):
                saved_name = str(names[int(saved_camera)] or "")
            if names and not (0 <= int(saved_camera) < len(names)):
                preferred_camera = auto_preferred_camera
            elif saved_name and _is_virtual_camera_name(saved_name) and auto_preferred_camera != saved_camera:
                preferred_camera = auto_preferred_camera
            elif (not names) and int(saved_camera) == 0 and auto_preferred_camera != int(saved_camera):
                # No camera-name metadata: if auto probe found a better camera,
                # do not lock startup to index 0 (often virtual cam on Windows).
                preferred_camera = auto_preferred_camera
            else:
                preferred_camera = saved_camera
        self._camera_devices = [preferred_camera]
        self.camera_selector.blockSignals(True)
        self.camera_selector.clear()
        self.camera_selector.addItem(self._camera_label_for_index(preferred_camera), preferred_camera)
        self.camera_selector.setCurrentIndex(0)
        self.camera_selector.setEnabled(True)
        self.camera_selector.blockSignals(False)
        self.vision_engine.set_camera_index(preferred_camera)

        if self.camera_on:
            self._set_camera_badge("CONNECTING", state="connecting", indicator="idle")
            self._foot_status.setText(f"\u2022  Initializing Camera {preferred_camera}...")
            self._foot_status.setStyleSheet(
                f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;"
            )

    def _camera_settings_path(self) -> Path:
        return Path(__file__).resolve().parent.parent / "config" / "settings.json"

    def _load_saved_camera_index(self):
        config_path = self._camera_settings_path()
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            camera_data = data.get("camera", {})
            value = camera_data.get("preferred_index")
            if value is None:
                return None
            idx = int(value)
            if idx < 0:
                return None
            return idx
        except Exception:
            return None

    def _save_preferred_camera_index(self, index):
        try:
            idx = int(index)
        except (TypeError, ValueError):
            return
        if idx < 0:
            return

        config_path = self._camera_settings_path()
        data = {}
        try:
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                    if isinstance(loaded, dict):
                        data = loaded
        except Exception:
            data = {}

        camera_data = data.get("camera")
        if not isinstance(camera_data, dict):
            camera_data = {}
            data["camera"] = camera_data
        camera_data["preferred_index"] = idx

        try:
            config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception:
            return

    def _camera_label_for_index(self, idx: int) -> str:
        label = f"Camera {idx}"
        try:
            names = _get_directshow_camera_names()
        except Exception:
            names = []
        if 0 <= int(idx) < len(names):
            pretty_name = str(names[int(idx)] or "").strip()
            if pretty_name:
                if _is_virtual_camera_name(pretty_name):
                    label = f"{pretty_name} (Virtual)"
                else:
                    label = pretty_name
        return label

    def _pick_non_virtual_camera(self, devices):
        if not devices:
            return -1
        try:
            names = _get_directshow_camera_names()
        except Exception:
            names = []

        for idx in devices:
            camera_name = ""
            if 0 <= int(idx) < len(names):
                camera_name = str(names[int(idx)] or "").strip()
            if camera_name and _is_virtual_camera_name(camera_name):
                continue
            return idx
        return devices[0]

    def _refresh_camera_devices(self, keep_current=True):
        if self._camera_scan_in_progress:
            self._camera_scan_pending = True
            self._camera_scan_pending_keep_current = bool(keep_current)
            return

        previous_index = self.vision_engine.get_camera_index()
        self._camera_scan_in_progress = True
        self._camera_scan_pending = False
        self.camera_refresh_btn.setEnabled(False)
        self.camera_refresh_btn.setText("Scanning...")

        if self.camera_on:
            self._set_camera_badge("SCANNING", state="connecting", indicator="idle")
            self._foot_status.setText("\u2022  Scanning cameras...")
            self._foot_status.setStyleSheet(
                f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;"
            )

        def scan_worker():
            try:
                # Probing camera hardware while stream is active can trigger
                # native OpenCV/driver crashes on some Windows systems.
                if self.camera_on:
                    names = _get_directshow_camera_names()
                    if names:
                        devices = list(range(min(len(names), 8)))
                    else:
                        current = self.vision_engine.get_camera_index()
                        devices = [current] if current >= 0 else []
                else:
                    devices = _discover_cameras(max_index=8)
            except Exception:
                devices = []
            self.bridge.on_camera_scan_ready(devices, bool(keep_current), int(previous_index))

        Thread(target=scan_worker, daemon=True).start()

    def _on_camera_scan_ready(self, devices, keep_current, previous_index):
        self._camera_scan_in_progress = False
        self.camera_refresh_btn.setEnabled(True)
        self.camera_refresh_btn.setText("Scan")

        normalized = []
        for idx in devices or []:
            try:
                value = int(idx)
            except (TypeError, ValueError):
                continue
            if value >= 0:
                normalized.append(value)

        active_index = self.vision_engine.get_camera_index()
        if active_index >= 0:
            normalized.append(active_index)

        deduped = []
        seen = set()
        for idx in normalized:
            if idx in seen:
                continue
            seen.add(idx)
            deduped.append(idx)
        devices = deduped
        self._camera_devices = devices

        self.camera_selector.blockSignals(True)
        self.camera_selector.clear()

        if not devices:
            self.camera_selector.addItem("No camera found", -1)
            self.camera_selector.setEnabled(False)
            self.camera_selector.blockSignals(False)
            self._set_camera_badge("NO CAMERA", state="paused", indicator="paused")
            self._foot_status.setText("\u2022  No Camera Found")
            self._foot_status.setStyleSheet(
                f"color: {CLR_RED}; font-size: 10px; font-weight: 600; background: transparent; border: none;"
            )
            return

        for idx in devices:
            self.camera_selector.addItem(self._camera_label_for_index(idx), idx)
        self.camera_selector.setEnabled(True)

        if keep_current and previous_index in devices:
            selected_camera = previous_index
        else:
            selected_camera = self._pick_non_virtual_camera(devices)

        combo_pos = self.camera_selector.findData(selected_camera)
        self.camera_selector.setCurrentIndex(max(0, combo_pos))
        self.camera_selector.blockSignals(False)

        current_index = self.vision_engine.get_camera_index()
        if selected_camera != current_index:
            self.vision_engine.set_camera_index(selected_camera)
            self._save_preferred_camera_index(selected_camera)

            if self.camera_on:
                self._set_camera_badge("CONNECTING", state="connecting", indicator="idle")
                self._foot_status.setText(f"\u2022  Initializing Camera {selected_camera}...")
                self._foot_status.setStyleSheet(
                    f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;"
                )

        if self._camera_scan_pending:
            next_keep_current = self._camera_scan_pending_keep_current
            self._camera_scan_pending = False
            QTimer.singleShot(0, lambda: self._refresh_camera_devices(keep_current=next_keep_current))

    def _on_camera_selected(self, combo_index):
        data = self.camera_selector.itemData(combo_index)
        if data is None:
            return
        try:
            target_index = int(data)
        except (TypeError, ValueError):
            return
        if target_index < 0:
            return

        current_index = self.vision_engine.get_camera_index()
        if target_index == current_index:
            return

        self.vision_engine.set_camera_index(target_index)
        self._save_preferred_camera_index(target_index)

        if self.camera_on:
            self._set_camera_badge("SWITCHING CAM", state="connecting", indicator="idle")
            self._foot_status.setText(f"\u2022  Switching to Camera {target_index}...")
            self._foot_status.setStyleSheet(f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
        else:
            self._foot_status.setText(f"\u2022  Camera {target_index} selected (paused)")
            self._foot_status.setStyleSheet(f"color: {CLR_TEXT_DIM}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    def toggle_camera(self):
        self.camera_on = not self.camera_on
        self.vision_engine.set_camera_active(self.camera_on)

        if self.camera_on:
            self.camera_toggle_btn.setText("\u23F8  Pause Camera")
            self._set_camera_badge("RECONNECTING", state="connecting", indicator="idle")
            self._foot_status.setText(f"\u2022  Reconnecting...")
            self._foot_status.setStyleSheet(f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
        else:
            self.camera_toggle_btn.setText("\u25B6  Resume Camera")
            self._set_camera_badge("PAUSED", state="paused", indicator="paused")
            self.status_label.setText("Paused")
            self.status_action_label.setText("Camera is paused")
            self.status_action_label.setStyleSheet(f"color: {CLR_TEXT_DIM}; font-size: 11px; background: transparent; border: none;")
            self._foot_status.setText(f"\u2022  Camera Paused")
            self._foot_status.setStyleSheet(f"color: {CLR_RED}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    # â”€â”€ Mapping CRUD â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _animate_center_page(self, page):
        self.center_stack.setCurrentWidget(page)
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        anim = QPropertyAnimation(effect, b"opacity", page)
        anim.setDuration(220)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _cleanup():
            page.setGraphicsEffect(None)

        anim.finished.connect(_cleanup)
        self._center_page_anim = anim
        anim.start()

    def open_inline_new_gesture(self):
        self.inline_builder.reset_for_new()
        self._animate_center_page(self._inline_builder_page)

    def close_inline_new_gesture(self):
        self._animate_center_page(self._map_page)

    def _on_inline_custom_created(self, custom_result):
        if not custom_result:
            return

        # New inline flow: custom builder also captures action mapping details.
        if all(k in custom_result for k in ("action_type", "keys", "description")):
            gesture_name = custom_result.get("gesture_name")
            if gesture_name in self.action_mapper.mappings:
                QMessageBox.warning(self, "Duplicate Gesture", "Custom gesture with same name already exists.")
                return

            self.action_mapper.add_mapping(
                gesture_name,
                custom_result.get("keys", []),
                custom_result.get("action_type", "shortcut"),
                custom_result.get("description", "Custom Action"),
                custom_rule=custom_result.get("custom_rule"),
            )
            self.refresh_mappings()
            self._foot_status.setText("\u2022  Custom gesture created")
            self._foot_status.setStyleSheet(f"color: {CLR_GREEN}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
            self.close_inline_new_gesture()
            return

        dialog = NewGestureDialog(self, list(self.action_mapper.mappings.keys()), get_live_hands=lambda: self._latest_hands_snapshot)
        ok = dialog.set_preselected_custom_gesture(
            custom_result["gesture_name"],
            custom_result["display_name"],
            custom_result["custom_rule"],
        )
        if ok and dialog.exec() == QDialog.Accepted and dialog.result:
            r = dialog.result
            self.action_mapper.add_mapping(
                r["gesture"],
                r["keys"],
                r["action_type"],
                r["description"],
                custom_rule=r.get("custom_rule"),
            )
            self.refresh_mappings()
            self._foot_status.setText("\u2022  Custom gesture created")
            self._foot_status.setStyleSheet(f"color: {CLR_GREEN}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

        self.close_inline_new_gesture()

    def add_mapping(self):
        dialog = NewGestureDialog(self, list(self.action_mapper.mappings.keys()), get_live_hands=lambda: self._latest_hands_snapshot)
        if dialog.exec() == QDialog.Accepted and dialog.result:
            r = dialog.result
            self.action_mapper.add_mapping(
                r["gesture"],
                r["keys"],
                r["action_type"],
                r["description"],
                custom_rule=r.get("custom_rule"),
            )
            self.refresh_mappings()

    def delete_mapping(self, gesture):
        self.action_mapper.delete_mapping(gesture)
        self.refresh_mappings()

    # â”€â”€ Footer stats â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _update_footer_stats(self):
        elapsed = int(time.time() - self._session_start)
        mins, secs = divmod(elapsed, 60)
        hrs, mins = divmod(mins, 60)
        if hrs > 0:
            uptime_str = f"{hrs}:{mins:02d}:{secs:02d}"
        else:
            uptime_str = f"{mins}:{secs:02d}"

        self._foot_gestures.setText(f"Gestures: {self._gesture_count}")
        self._foot_actions.setText(f"Actions: {self._action_count}")
        self._foot_uptime.setText(f"Uptime: {uptime_str}")

        current_render = self.vision_engine.get_render_device()
        if current_render != self._last_render_mode:
            self._last_render_mode = current_render
            if current_render == "gpu":
                self._foot_status.setText("\u2022  GPU activated automatically")
                self._foot_status.setStyleSheet(f"color: {CLR_GREEN}; font-size: 10px; font-weight: 600; background: transparent; border: none;")
            else:
                self._foot_status.setText("\u2022  GPU unavailable, running on CPU")
                self._foot_status.setStyleSheet(f"color: {CLR_ORANGE}; font-size: 10px; font-weight: 600; background: transparent; border: none;")

    # â”€â”€ Resize handling â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def resizeEvent(self, event):
        super().resizeEvent(event)
        new_geom = (event.size().width(), event.size().height())
        if self._last_geom == new_geom:
            return
        self._last_geom = new_geom

        self._is_resizing = True
        self.vision_engine.processing_paused = True

        sidebar_w = max(300, min(400, int(new_geom[0] * 0.30)))
        self.sidebar.setFixedWidth(sidebar_w)

        self._resume_timer.start(120)

    def _finish_resize(self):
        self._is_resizing = False
        self.vision_engine.processing_paused = False

    # â”€â”€ Cleanup â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def closeEvent(self, event: Optional[QCloseEvent]):
        self.vision_engine.stop()
        self._uptime_timer.stop()
        if self._camera_fullscreen_dialog is not None:
            self._camera_fullscreen_dialog.close()
            self._camera_fullscreen_dialog = None
        if event is not None:
            event.accept()


def run_window():
    app = QApplication.instance() or QApplication([])
    win = MainWindow()
    win.show()
    return app.exec()

