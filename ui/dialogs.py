import time
import os
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
from .system_scanner import _get_system_apps, _SCAN_IN_PROGRESS
from core.vision_engine import VisionEngine

class CameraFullscreenDialog(QDialog):
    def __init__(self, parent=None, on_close=None):
        super().__init__(parent)
        self._on_close = on_close
        self._last_image = None
        self.setWindowTitle("Camera Full Screen")
        self.setWindowFlag(Qt.Window, True)
        self.setModal(False)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(6)

        self.feed_label = QLabel("Camera feed will appear here...")
        self.feed_label.setObjectName("cameraFullscreen")
        self.feed_label.setAlignment(Qt.AlignCenter)
        self.feed_label.setScaledContents(False)
        self.feed_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        root.addWidget(self.feed_label, 1)

        hint = QLabel("Press Esc to exit fullscreen")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignCenter)
        root.addWidget(hint)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render_last_frame()

    def update_frame(self, image: QImage):
        self._last_image = image
        self._render_last_frame()

    def _render_last_frame(self):
        if self._last_image is None:
            return
        target_size = self.feed_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return
        pixmap = QPixmap.fromImage(self._last_image).scaled(
            target_size,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation
        )
        self.feed_label.setPixmap(pixmap)
        self.feed_label.setText("")

    def closeEvent(self, event):
        if callable(self._on_close):
            self._on_close()
        super().closeEvent(event)


class GestureRecordPopup(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Record Gesture")
        self.setModal(False)
        self.setFixedSize(720, 520)
        self._last_image = None
        self._trails = {"left": [], "right": [], "unknown": []}
        self._trail_colors = {
            "left": QColor("#35c5ff"),
            "right": QColor("#ffc247"),
            "unknown": QColor("#8a93a8"),
        }
        self._max_trail_points = 96

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.timer_label = QLabel("5.0s")
        self.timer_label.setAlignment(Qt.AlignCenter)
        self.timer_label.setObjectName("cgTitle")
        root.addWidget(self.timer_label)

        self.feed_label = QLabel("Camera preview will appear here...")
        self.feed_label.setObjectName("cameraFullscreen")
        self.feed_label.setAlignment(Qt.AlignCenter)
        self.feed_label.setScaledContents(False)
        self.feed_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
        root.addWidget(self.feed_label, 1)

        self.info_label = QLabel("Virtual canvas is ON: hold or move your hand to record full gesture path.")
        self.info_label.setAlignment(Qt.AlignCenter)
        self.info_label.setObjectName("muted")
        root.addWidget(self.info_label)

    def reset_canvas(self):
        self._trails = {"left": [], "right": [], "unknown": []}
        self._render()

    def update_hands(self, hands):
        for hand in (hands or []):
            label = str(hand.get("hand", "unknown")).strip().lower()
            if label not in self._trails:
                label = "unknown"
            wrist = hand.get("wrist") or {}
            x = wrist.get("x")
            y = wrist.get("y")
            if x is None or y is None:
                continue
            self._trails[label].append((float(x), float(y)))
            if len(self._trails[label]) > self._max_trail_points:
                self._trails[label] = self._trails[label][-self._max_trail_points:]
        self._render()

    def update_frame(self, image: QImage):
        if image is None:
            return
        self._last_image = image
        self._render()

    def _render(self):
        target_size = self.feed_label.size()
        if target_size.width() <= 0 or target_size.height() <= 0:
            return

        canvas = QPixmap(target_size)
        canvas.fill(QColor("#090c13"))
        painter = QPainter(canvas)
        draw_rect = None

        if self._last_image is not None:
            frame = QPixmap.fromImage(self._last_image).scaled(
                target_size,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )
            x = (target_size.width() - frame.width()) // 2
            y = (target_size.height() - frame.height()) // 2
            painter.drawPixmap(x, y, frame)
            draw_rect = (x, y, frame.width(), frame.height())

        if draw_rect is not None:
            rx, ry, rw, rh = draw_rect
            for key, points in self._trails.items():
                if len(points) < 2:
                    continue
                pen = QPen(self._trail_colors.get(key, QColor("#8a93a8")))
                pen.setWidth(3)
                painter.setPen(pen)
                for i in range(1, len(points)):
                    x1 = int(rx + points[i - 1][0] * rw)
                    y1 = int(ry + points[i - 1][1] * rh)
                    x2 = int(rx + points[i][0] * rw)
                    y2 = int(ry + points[i][1] * rh)
                    painter.drawLine(x1, y1, x2, y2)

                lx = int(rx + points[-1][0] * rw)
                ly = int(ry + points[-1][1] * rh)
                painter.setBrush(self._trail_colors.get(key, QColor("#8a93a8")))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(lx - 5, ly - 5, 10, 10)

        painter.end()
        self.feed_label.setPixmap(canvas)
        self.feed_label.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()


class CustomGestureBuilderDialog(QDialog):
    created = Signal(dict)
    FINGERS = ["thumb", "index", "middle", "ring", "pinky"]

    def __init__(self, parent=None, get_live_hands=None, get_live_frame=None, embedded=False):
        super().__init__(parent)
        self._embedded = embedded
        self.setWindowTitle("Create Custom Gesture")
        if embedded:
            self.setModal(False)
            self.setWindowFlags(Qt.Widget)
            self.setMinimumSize(0, 0)
            self.resize(720, 560)
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        else:
            self.setModal(True)
            self.setFixedSize(720, 560)
        self._get_live_hands = get_live_hands or (lambda: [])
        self._get_live_frame = get_live_frame or (lambda: None)
        self.result = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_live_preview)
        self._record_timer = QTimer(self)
        self._record_timer.timeout.connect(self._record_tick)
        self._record_samples = []
        self._record_remaining = 0
        self._record_popup = None
        self._build_ui()
        self._apply_style()
        self._timer.start(220)

    def _build_rule_group(self, title):
        wrap = QFrame()
        wrap.setObjectName("cgRuleGroup")
        layout = QVBoxLayout(wrap)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        heading = QLabel(title)
        heading.setObjectName("cgStep")
        heading.setContentsMargins(0, 10, 0, 5)
        layout.addWidget(heading)

        # Motion row
        motion_row = QFrame()
        motion_row.setObjectName("cgRuleRow")
        m_lay = QHBoxLayout(motion_row)
        m_lay.setContentsMargins(12, 6, 12, 6)
        m_lbl = QLabel("Motion")
        m_lbl.setObjectName("cgLbl")
        m_combo = QComboBox()
        m_combo.setObjectName("cgCombo")
        m_combo.setFixedWidth(120)
        m_combo.addItem("Ignore", "any")
        m_combo.addItem("Static", "static")
        m_combo.addItem("Moving", "move")
        m_combo.addItem("Move Left", "left")
        m_combo.addItem("Move Right", "right")
        m_combo.addItem("Move Up", "up")
        m_combo.addItem("Move Down", "down")
        m_lay.addWidget(m_lbl)
        m_lay.addStretch(1)
        m_lay.addWidget(m_combo)
        layout.addWidget(motion_row)

        combos = {}
        for finger in self.FINGERS:
            f_row = QFrame()
            f_row.setObjectName("cgRuleRow")
            f_lay = QHBoxLayout(f_row)
            f_lay.setContentsMargins(12, 6, 12, 6)
            f_lbl = QLabel(finger.capitalize())
            f_lbl.setObjectName("cgLbl")
            f_combo = QComboBox()
            f_combo.setObjectName("cgCombo")
            f_combo.setFixedWidth(120)
            f_combo.addItem("Ignore", "any")
            f_combo.addItem("Up", "up")
            f_combo.addItem("Down", "down")
            f_lay.addWidget(f_lbl)
            f_lay.addStretch(1)
            f_lay.addWidget(f_combo)
            layout.addWidget(f_row)
            combos[finger] = f_combo

        return wrap, combos, m_combo

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        header = QLabel("Custom Gesture Builder")
        header.setObjectName("cgHeroTitle")
        root.addWidget(header)

        main_row = QHBoxLayout()
        main_row.setSpacing(20)

        # --- LEFT: HAND SETUP ---
        hand_setup_scroll = QScrollArea()
        hand_setup_scroll.setWidgetResizable(True)
        hand_setup_scroll.setFrameShape(QFrame.NoFrame)
        hand_setup_scroll.setStyleSheet("background: transparent;")
        
        hand_setup_content = QFrame()
        hand_setup_content.setObjectName("cgPanel")
        hand_lay = QVBoxLayout(hand_setup_content)
        hand_lay.setContentsMargins(16, 16, 16, 16)
        hand_lay.setSpacing(12)

        hand_title = QLabel("\u270B  Hand Setup")
        hand_title.setObjectName("cgStep")
        hand_lay.addWidget(hand_title)

        # Visual Live Preview (Compact)
        self._live_preview = QLabel("Waiting...")
        self._live_preview.setObjectName("cgLive")
        self._live_preview.setFixedSize(300, 160)
        self._live_preview.setAlignment(Qt.AlignCenter)
        hand_lay.addWidget(self._live_preview, 0, Qt.AlignCenter)

        # Finger Visualizer (Icons)
        self._finger_viz = QWidget()
        fv_main_lay = QVBoxLayout(self._finger_viz)
        fv_main_lay.setContentsMargins(0, 0, 0, 0)
        fv_main_lay.setSpacing(6)

        # Left Hand Visualizer
        self._left_viz_row = QWidget()
        lv_lay = QHBoxLayout(self._left_viz_row)
        lv_lay.setContentsMargins(0, 0, 0, 0)
        lv_lay.setSpacing(6)
        lv_lay.addWidget(QLabel("L"))
        self._left_finger_labels = {}
        for f in ["Thumb", "Index", "Middle", "Ring", "Pinky"]:
            lbl = QLabel(f[0])
            lbl.setFixedSize(28, 28)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("fingerOff")
            lv_lay.addWidget(lbl)
            self._left_finger_labels[f.lower()] = lbl
        
        # Right Hand Visualizer
        self._right_viz_row = QWidget()
        rv_lay = QHBoxLayout(self._right_viz_row)
        rv_lay.setContentsMargins(0, 0, 0, 0)
        rv_lay.setSpacing(6)
        rv_lay.addWidget(QLabel("R"))
        self._right_finger_labels = {}
        for f in ["Thumb", "Index", "Middle", "Ring", "Pinky"]:
            lbl = QLabel(f[0])
            lbl.setFixedSize(28, 28)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setObjectName("fingerOff")
            rv_lay.addWidget(lbl)
            self._right_finger_labels[f.lower()] = lbl

        fv_main_lay.addWidget(self._left_viz_row)
        fv_main_lay.addWidget(self._right_viz_row)
        hand_lay.addWidget(self._finger_viz, 0, Qt.AlignCenter)

        # Hand Mode & Status
        mode_row = QHBoxLayout()
        self._mode = QComboBox()
        self._mode.setObjectName("cgCombo")
        self._mode.addItem("Any Hand", "any")
        self._mode.addItem("Left Only", "left")
        self._mode.addItem("Right Only", "right")
        self._mode.addItem("Both Hands", "both")
        self._mode.currentIndexChanged.connect(self._sync_mode_ui)
        self._record_status = QLabel("Ready")
        self._record_status.setObjectName("cgHint")
        mode_row.addWidget(self._mode, 1)
        mode_row.addWidget(self._record_status)
        hand_lay.addLayout(mode_row)

        # Capture Buttons (Visual Icons)
        btns_row = QHBoxLayout()
        btns_row.setSpacing(8)
        self._capture_btn = QPushButton("\u23F3  Capture")
        self._capture_btn.setObjectName("cgBtnPrimary")
        self._capture_btn.clicked.connect(self._capture_current_pose)
        self._record_btn = QPushButton("\u23F1  Record 5s")
        self._record_btn.setObjectName("cgBtn")
        self._record_btn.clicked.connect(self._start_recording)
        self._reset_btn = QPushButton("\u21BB")
        self._reset_btn.setObjectName("cgBtn")
        self._reset_btn.setFixedWidth(40)
        self._reset_btn.clicked.connect(self._reset_rules)
        btns_row.addWidget(self._capture_btn, 1)
        btns_row.addWidget(self._record_btn, 1)
        btns_row.addWidget(self._reset_btn)
        hand_lay.addLayout(btns_row)

        self._capture_summary = QLabel("")
        self._capture_summary.setObjectName("cgHintSoft")
        self._capture_summary.setWordWrap(True)
        hand_lay.addWidget(self._capture_summary)

        # Manual Finger Rules Section
        self._rules_wrap = QWidget()
        rules_lay = QVBoxLayout(self._rules_wrap)
        rules_lay.setContentsMargins(0, 0, 0, 0)
        rules_lay.setSpacing(10)
        
        self._any_frame, self._any_combos, self._any_motion = self._build_rule_group("Any-Hand Rules")
        self._left_frame, self._left_combos, self._left_motion = self._build_rule_group("Left Hand Rules")
        self._right_frame, self._right_combos, self._right_motion = self._build_rule_group("Right Hand Rules")
        
        rules_lay.addWidget(self._any_frame)
        rules_lay.addWidget(self._left_frame)
        rules_lay.addWidget(self._right_frame)
        hand_lay.addWidget(self._rules_wrap)
        
        hand_lay.addStretch(1)
        hand_setup_scroll.setWidget(hand_setup_content)

        # --- RIGHT: ACTION SETUP ---
        action_setup = QFrame()
        action_setup.setObjectName("cgPanel")
        act_lay = QVBoxLayout(action_setup)
        act_lay.setContentsMargins(16, 16, 16, 16)
        act_lay.setSpacing(12)

        act_title = QLabel("\u2699  Action Mapping")
        act_title.setObjectName("cgStep")
        act_lay.addWidget(act_title)

        self._name = QLineEdit()
        self._name.setObjectName("cgInput")
        self._name.setPlaceholderText("Name (e.g. Volume Up)")
        act_lay.addWidget(self._name)

        self._action_buttons = {}
        self._action_group = QButtonGroup(self)
        self._action_group.setExclusive(True)
        action_grid = QGridLayout()
        action_grid.setContentsMargins(0, 0, 0, 0)
        action_grid.setHorizontalSpacing(8)
        action_grid.setVerticalSpacing(8)
        action_defs = [
            ("shortcut", "\u2328", "Shortcut"),
            ("mouse_click", "\U0001F5B1", "Left Click"),
            ("mouse_right_click", "\U0001F5B1", "Right Click"),
            ("launch", "\U0001F680", "Launch App"),
        ]
        for idx, (atype, icon, label) in enumerate(action_defs):
            btn = QPushButton(f"{icon}\n{label}")
            btn.setObjectName("cgActionCard")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _=False, a=atype: self._set_action_type(a))
            self._action_group.addButton(btn)
            self._action_buttons[atype] = btn
            action_grid.addWidget(btn, idx // 2, idx % 2)
        act_lay.addLayout(action_grid)

        self._action_config_stack = QStackedWidget()
        no_cfg = QLabel("No extra settings needed.")
        no_cfg.setObjectName("cgHintSoft")
        no_cfg.setAlignment(Qt.AlignCenter)
        shortcut_cfg = QWidget()
        sc_lay = QVBoxLayout(shortcut_cfg)
        sc_lay.setContentsMargins(0, 0, 0, 0)
        self._shortcut_preset = QComboBox()
        self._shortcut_preset.setObjectName("cgCombo")
        self._shortcut_preset.addItem("Choose preset...", "")
        for p, k in SHORTCUT_PRESETS.items(): self._shortcut_preset.addItem(p, k)
        self._shortcut_preset.currentIndexChanged.connect(self._apply_shortcut_preset)
        sc_row = QHBoxLayout()
        self._shortcut_input = QLineEdit()
        self._shortcut_input.setObjectName("cgInput")
        self._record_keys_btn = QPushButton("\u2328")
        self._record_keys_btn.setCheckable(True)
        self._record_keys_btn.setObjectName("cgBtnSmall")
        self._record_keys_btn.setFixedWidth(40)
        self._record_keys_btn.toggled.connect(self._toggle_key_recording)
        sc_row.addWidget(self._shortcut_input, 1)
        sc_row.addWidget(self._record_keys_btn)
        sc_lay.addWidget(self._shortcut_preset)
        sc_lay.addLayout(sc_row)

        launch_cfg = QWidget()
        l_lay = QVBoxLayout(launch_cfg)
        l_lay.setContentsMargins(0, 0, 0, 0)
        self._launch_preset = QComboBox()
        self._launch_preset.setObjectName("cgCombo")
        self._launch_preset.addItem("Choose app...", "")
        for a, info in LAUNCHABLE_APPS.items(): self._launch_preset.addItem(a, info["cmd"])
        self._launch_preset.currentIndexChanged.connect(self._apply_launch_preset)
        self._launch_input = QLineEdit()
        self._launch_input.setObjectName("cgInput")
        self._launch_input.textChanged.connect(self._auto_suggest_name)
        l_lay.addWidget(self._launch_preset)
        l_lay.addWidget(self._launch_input)

        self._action_config_stack.addWidget(no_cfg)
        self._action_config_stack.addWidget(shortcut_cfg)
        self._action_config_stack.addWidget(launch_cfg)
        act_lay.addWidget(self._action_config_stack)

        test_row = QHBoxLayout()
        self._test_btn = QPushButton("\u25B6  Test Action")
        self._test_btn.setObjectName("cgBtnSmall")
        self._test_btn.clicked.connect(self._test_current_action)
        test_row.addStretch(1)
        test_row.addWidget(self._test_btn)
        act_lay.addLayout(test_row)

        act_lay.addStretch(1)
        self._error = QLabel("")
        self._error.setObjectName("cgError")
        self._error.setWordWrap(True)
        act_lay.addWidget(self._error)
        self._create_btn = QPushButton("Create Mapping")
        self._create_btn.setObjectName("cgSubmit")
        self._create_btn.clicked.connect(self._submit)
        act_lay.addWidget(self._create_btn)

        main_row.addWidget(hand_setup_scroll, 1)
        main_row.addWidget(action_setup, 1)
        root.addLayout(main_row)

        self._action_type = "shortcut"
        self._set_action_type("shortcut")
        self._sync_mode_ui()

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{ background: {CLR_BG}; color: {CLR_TEXT}; font-family: {FONT_FAMILY}; }}
            QFrame#cgPanel {{
                background: {CLR_CARD};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 12px;
            }}
            QFrame#cgRuleRow {{
                background: {CLR_BG_ALT};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 6px;
            }}
            QLabel#cgHeroTitle {{ color: {CLR_WHITE}; font-size: 20px; font-weight: 700; margin-bottom: 5px; }}
            QLabel#cgStep {{ color: {CLR_WHITE}; font-size: 13px; font-weight: 700; }}
            QLabel#cgLive {{
                background: {CLR_BG_ALT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                padding: 10px;
                color: {CLR_TEXT_DIM};
                font-size: 11px;
            }}
            QLabel#cgHint {{ color: {CLR_CYAN}; font-size: 11px; font-weight: 600; }}
            QLabel#cgHintSoft {{ color: {CLR_TEXT_MUTED}; font-size: 10px; }}
            QLabel#cgLbl {{ color: {CLR_TEXT_DIM}; font-size: 11px; font-weight: 600; }}
            
            QLineEdit#cgInput {{
                background: {CLR_INPUT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 34px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QLineEdit#cgInput:focus {{ border: 1px solid {CLR_ACCENT_GLOW}; background: {CLR_BG_ALT}; }}
            
            QComboBox#cgCombo {{
                background: {CLR_INPUT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 32px;
                padding: 0 10px;
                font-size: 11px;
            }}
            QComboBox#cgCombo:focus {{ border: 1px solid {CLR_ACCENT_GLOW}; }}
            
            QPushButton#cgBtn {{ 
                background: {CLR_ACCENT_DIM}; 
                color: {CLR_TEXT_DIM}; 
                border: 1px solid {CLR_BORDER}; 
                border-radius: 8px; 
                min-height: 32px; 
                padding: 0 12px; 
                font-size: 11px; 
            }}
            QPushButton#cgBtn:hover {{ background: {CLR_ACCENT}; color: {CLR_WHITE}; }}
            
            QPushButton#cgBtnPrimary {{ 
                background: {CLR_ACCENT}; 
                color: {CLR_WHITE}; 
                border: 1px solid {CLR_BORDER}; 
                border-radius: 8px; 
                min-height: 34px; 
                padding: 0 14px; 
                font-size: 11px; 
                font-weight: 700;
            }}
            QPushButton#cgBtnPrimary:hover {{ background: {CLR_ACCENT_HOVER}; border: 1px solid {CLR_ACCENT_GLOW}; }}

            QPushButton#cgBtnSmall {{
                background: {CLR_BG_ALT};
                color: {CLR_TEXT_MUTED};
                border: 1px solid {CLR_BORDER};
                border-radius: 6px;
                font-size: 10px;
                padding: 4px 10px;
            }}

            QPushButton#cgActionCard {{
                background: {CLR_BG_ALT};
                color: {CLR_TEXT_DIM};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 10px;
                text-align: center;
                padding: 12px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton#cgActionCard:hover {{ background: {CLR_CARD}; border: 1px solid {CLR_BORDER}; }}
            QPushButton#cgActionCard:checked {{
                background: {CLR_SELECTED};
                border: 1px solid {CLR_ACCENT_GLOW};
                color: {CLR_WHITE};
            }}

            QPushButton#cgSubmit {{
                background: {CLR_ACCENT};
                color: {CLR_WHITE};
                border: 1px solid {CLR_BORDER};
                border-radius: 10px;
                min-height: 42px;
                padding: 0 20px;
                font-weight: 700;
                font-size: 12px;
            }}
            QPushButton#cgSubmit:hover {{ background: {CLR_ACCENT_HOVER}; border: 1px solid {CLR_ACCENT_GLOW}; }}
            
            QLabel#cgError {{ color: {CLR_RED}; font-size: 11px; font-weight: 600; }}
            
            QLabel#fingerOff {{
                background: #1A1A1A;
                color: #444;
                border: 1px solid #333;
                border-radius: 14px;
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel#fingerLeftOn {{
                background: #35c5ff; /* Left: Cyan */
                color: #FFF;
                border: 1px solid #555;
                border-radius: 14px;
                font-size: 10px;
                font-weight: 700;
            }}
            QLabel#fingerRightOn {{
                background: #ffc247; /* Right: Orange */
                color: #FFF;
                border: 1px solid #555;
                border-radius: 14px;
                font-size: 10px;
                font-weight: 700;
            }}
        """)

    def _sync_mode_ui(self):
        mode = self._mode.currentData()
        self._refresh_rule_visibility(mode)
        
        # Show/hide visualizer rows based on mode
        if hasattr(self, "_left_viz_row"):
            self._left_viz_row.setVisible(mode in {"any", "left", "both"})
        if hasattr(self, "_right_viz_row"):
            self._right_viz_row.setVisible(mode in {"any", "right", "both"})

    def _toggle_advanced_rules(self, enabled):
        self._advanced_toggle.setText("Hide Rules" if enabled else "Show Rules")
        self._refresh_rule_visibility(self._mode.currentData())

    def _refresh_rule_visibility(self, mode):
        if hasattr(self, "_rules_wrap"):
            self._rules_wrap.setVisible(True)
        self._any_frame.setVisible(mode == "any")
        self._left_frame.setVisible(mode in {"left", "both"})
        self._right_frame.setVisible(mode in {"right", "both"})

    def _set_action_type(self, action_type):
        self._action_type = action_type
        for atype, btn in self._action_buttons.items():
            btn.setChecked(atype == action_type)

        if action_type == "shortcut":
            self._action_config_stack.setCurrentIndex(1)
            self._record_status.setText("Shortcut selected. Pick a preset or type your own keys.")
        elif action_type == "launch":
            self._action_config_stack.setCurrentIndex(2)
            self._record_status.setText("Launch action selected. Choose a quick app or enter any command / URL.")
        else:
            self._action_config_stack.setCurrentIndex(0)
            self._record_status.setText("Mouse action selected. You can create the gesture directly.")

    def _apply_shortcut_preset(self):
        value = self._shortcut_preset.currentData()
        if value:
            self._shortcut_input.setText(str(value))
            # Auto suggest name if empty
            if not self._name.text().strip():
                self._name.setText(self._shortcut_preset.currentText())

    def _apply_launch_preset(self):
        value = self._launch_preset.currentData()
        if value:
            self._launch_input.setText(str(value))
            # Auto suggest name if empty
            if not self._name.text().strip():
                self._name.setText(self._launch_preset.currentText())

    def _auto_suggest_name(self):
        # If user types a URL or app, try to suggest a name if empty
        if not self._name.text().strip():
            txt = self._launch_input.text().strip()
            if txt.startswith("http"):
                # extract domain
                match = re.search(r"https?://(?:www\.)?([^./]+)", txt)
                if match:
                    self._name.setText(f"Open {match.group(1).capitalize()}")
            elif txt.endswith(".exe") or len(txt) > 2:
                name = Path(txt).stem.capitalize()
                self._name.setText(f"Launch {name}")

    def _toggle_key_recording(self, enabled):
        if enabled:
            self._record_keys_btn.setText("Recording...")
            self._shortcut_input.setPlaceholderText("Press keys now...")
            self._shortcut_input.setEnabled(False)
            
            self._recorded_keys_str = ""
            def on_key(e):
                if e.event_type == "down":
                    hk = keyboard.get_hotkey_name()
                    if hk:
                        self._recorded_keys_str = hk
            
            self._kb_hook = keyboard.hook(on_key)
            QTimer.singleShot(3000, lambda: self._record_keys_btn.setChecked(False))
        else:
            if hasattr(self, "_kb_hook"):
                keyboard.unhook(self._kb_hook)
            self._shortcut_input.setEnabled(True)
            if hasattr(self, "_recorded_keys_str") and self._recorded_keys_str:
                self._shortcut_input.setText(self._recorded_keys_str)
            self._record_keys_btn.setText("\u2328  Record Keys")

    def _test_current_action(self):
        atype = self._action_type
        if atype == "shortcut":
            keys = self._shortcut_input.text().strip()
            if keys:
                self._record_status.setText(f"Testing shortcut: {keys} (3s delay...)")
                QTimer.singleShot(3000, lambda: keyboard.press_and_release(keys))
        elif atype == "mouse_click":
            self._record_status.setText("Testing click (3s delay...)")
            QTimer.singleShot(3000, lambda: pyautogui.click())
        elif atype == "mouse_right_click":
            self._record_status.setText("Testing right click (3s delay...)")
            QTimer.singleShot(3000, lambda: pyautogui.rightClick())
        elif atype == "launch":
            cmd = self._launch_input.text().strip()
            if cmd:
                self._record_status.setText(f"Testing launch: {cmd}")
                try:
                    os.startfile(cmd)
                except:
                    import subprocess
                    subprocess.Popen(["cmd", "/c", "start", "", cmd])

    def _has_active_rule(self):
        mode = self._mode.currentData()
        any_fingers = any(combo.currentData() != "any" for combo in self._any_combos.values())
        left_fingers = any(combo.currentData() != "any" for combo in self._left_combos.values())
        right_fingers = any(combo.currentData() != "any" for combo in self._right_combos.values())

        if mode == "any":
            return any_fingers or self._any_motion.currentData() != "any"
        if mode == "left":
            return left_fingers or self._left_motion.currentData() != "any"
        if mode == "right":
            return right_fingers or self._right_motion.currentData() != "any"
        return (
            left_fingers
            or right_fingers
            or self._left_motion.currentData() != "any"
            or self._right_motion.currentData() != "any"
        )

    def _reset_rules(self):
        self._error.setText("")
        self._record_status.setText("Cleared")
        self._capture_summary.clear()
        
        # Reset finger visualizers
        all_labels = list(self._left_finger_labels.values()) + list(self._right_finger_labels.values())
        for lbl in all_labels:
            lbl.setObjectName("fingerOff")
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)
            
        for combo in self._any_combos.values():
            combo.setCurrentIndex(max(0, combo.findData("any")))
        self._set_motion_combo(self._any_motion, "any")
        for combo in self._left_combos.values():
            combo.setCurrentIndex(max(0, combo.findData("any")))
        self._set_motion_combo(self._left_motion, "any")
        for combo in self._right_combos.values():
            combo.setCurrentIndex(max(0, combo.findData("any")))
        self._set_motion_combo(self._right_motion, "any")

    def _describe_hands(self, hands):
        if not hands:
            return "No hands detected right now. Show hand(s) to camera."
        parts = []
        for hand in hands:
            hand_name = hand.get("hand", "Unknown")
            fingers = hand.get("fingers", {})
            ftxt = ", ".join([f"{k}:{'up' if v else 'down'}" for k, v in fingers.items()])
            parts.append(f"{hand_name}: {ftxt}")
        return " | ".join(parts)

    @staticmethod
    def _infer_motion(points):
        valid = [p for p in points if p is not None]
        if len(valid) < 3:
            return "static"
        x0, y0 = valid[0]
        x1, y1 = valid[-1]
        dx = x1 - x0
        dy = y1 - y0
        if abs(dx) < 0.08 and abs(dy) < 0.08:
            return "static"
        if abs(dx) > abs(dy) * 1.2:
            return "left" if dx < 0 else "right"
        if abs(dy) > abs(dx) * 1.2:
            return "up" if dy < 0 else "down"
        return "move"

    def _infer_finger_rule(self, hand_samples):
        rules = {}
        for finger in self.FINGERS:
            values = [1 if sample.get("fingers", {}).get(finger, False) else 0 for sample in hand_samples]
            if not values:
                rules[finger] = "any"
                continue
            ratio = sum(values) / len(values)
            if ratio >= 0.65:
                rules[finger] = "up"
            elif ratio <= 0.35:
                rules[finger] = "down"
            else:
                rules[finger] = "any"
        return rules

    def _set_motion_combo(self, combo, value):
        idx = combo.findData(value)
        combo.setCurrentIndex(max(0, idx))

    def _apply_recording(self):
        if not self._record_samples:
            self._record_status.setText("No hand data recorded. Try again with hand in frame.")
            return

        left_samples = []
        right_samples = []
        any_samples = []
        both_count = 0
        for sample in self._record_samples:
            labels = {str(h.get("hand", "")).lower() for h in sample}
            if "left" in labels and "right" in labels:
                both_count += 1
            for hand in sample:
                label = str(hand.get("hand", "")).lower()
                any_samples.append(hand)
                if label == "left":
                    left_samples.append(hand)
                elif label == "right":
                    right_samples.append(hand)

        if both_count >= max(2, len(self._record_samples) // 3):
            mode = "both"
        elif len(left_samples) > len(right_samples) and left_samples:
            mode = "left"
        elif len(right_samples) > len(left_samples) and right_samples:
            mode = "right"
        else:
            mode = "any"

        idx = self._mode.findData(mode)
        self._mode.setCurrentIndex(max(0, idx))
        self._sync_mode_ui()

        if mode == "any" and any_samples:
            if left_samples or right_samples:
                dominant_samples = left_samples if len(left_samples) >= len(right_samples) else right_samples
            else:
                dominant_samples = any_samples
            rules = self._infer_finger_rule(dominant_samples)
            self._apply_pose_to_combos(self._any_combos, {k: v == "up" for k, v in rules.items() if v != "any"})
            for finger, state in rules.items():
                self._any_combos[finger].setCurrentIndex(max(0, self._any_combos[finger].findData(state)))
            self._set_motion_combo(self._any_motion, self._infer_motion([(
                h.get("wrist", {}).get("x"),
                h.get("wrist", {}).get("y"),
            ) for h in dominant_samples]))
        if mode in {"left", "both"} and left_samples:
            rules = self._infer_finger_rule(left_samples)
            for finger, state in rules.items():
                self._left_combos[finger].setCurrentIndex(max(0, self._left_combos[finger].findData(state)))
            self._set_motion_combo(self._left_motion, self._infer_motion([(
                h.get("wrist", {}).get("x"),
                h.get("wrist", {}).get("y"),
            ) for h in left_samples]))
        if mode in {"right", "both"} and right_samples:
            rules = self._infer_finger_rule(right_samples)
            for finger, state in rules.items():
                self._right_combos[finger].setCurrentIndex(max(0, self._right_combos[finger].findData(state)))
            self._set_motion_combo(self._right_motion, self._infer_motion([(
                h.get("wrist", {}).get("x"),
                h.get("wrist", {}).get("y"),
            ) for h in right_samples]))

        self._record_status.setText("Recording applied. Gesture setup is ready to review.")

    def _refresh_live_preview(self):
        hands = self._get_live_hands() or []
        frame = self._get_live_frame()
        
        # Update live feed
        if frame is not None:
            try:
                if isinstance(frame, QImage):
                    # Frame is already a QImage from MainWindow
                    pix = QPixmap.fromImage(frame).scaled(self._live_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                else:
                    # Fallback for numpy array
                    h, w, c = frame.shape
                    qimg = QImage(frame.data, w, h, c * w, QImage.Format_RGB888)
                    pix = QPixmap.fromImage(qimg).scaled(self._live_preview.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                
                self._live_preview.setPixmap(pix)
                self._live_preview.setText("")
            except Exception as e:
                print(f"Preview error: {e}")
        
        # Reset all labels first
        for lbl in self._left_finger_labels.values(): lbl.setObjectName("fingerOff")
        for lbl in self._right_finger_labels.values(): lbl.setObjectName("fingerOff")
        
        # Update labels based on detected hands
        for hand in hands:
            label = str(hand.get("hand", "")).lower()
            fingers = hand.get("fingers", {})
            if label == "left":
                for f, state in fingers.items():
                    if f in self._left_finger_labels:
                        self._left_finger_labels[f].setObjectName("fingerLeftOn" if state else "fingerOff")
            elif label == "right":
                for f, state in fingers.items():
                    if f in self._right_finger_labels:
                        self._right_finger_labels[f].setObjectName("fingerRightOn" if state else "fingerOff")
        
        # Refresh styles
        for lbl in list(self._left_finger_labels.values()) + list(self._right_finger_labels.values()):
            lbl.style().unpolish(lbl)
            lbl.style().polish(lbl)

        if self._record_popup and self._record_popup.isVisible():
            self._record_popup.update_frame(self._get_live_frame())
            self._record_popup.update_hands(hands)

    def _apply_pose_to_combos(self, combos, fingers):
        for fname, combo in combos.items():
            state = "up" if fingers.get(fname, False) else "down"
            idx = combo.findData(state)
            combo.setCurrentIndex(max(0, idx))

    def _capture_current_pose(self):
        self._error.setText("")
        hands = self._get_live_hands() or []
        if not hands:
            self._record_status.setText("No hand detected.")
            return
        
        mode = self._mode.currentData()
        left = next((h for h in hands if str(h.get("hand", "")).lower() == "left"), None)
        right = next((h for h in hands if str(h.get("hand", "")).lower() == "right"), None)
        
        captured_desc = []
        
        if mode == "any":
            target = hands[0] if hands else None
            if target:
                self._apply_pose_to_combos(self._any_combos, target.get("fingers", {}))
                self._set_motion_combo(self._any_motion, "static")
                self._record_status.setText("Pose captured!")
                captured_desc.append(f"Any: {self._get_finger_summary(target.get('fingers', {}))}")
        elif mode == "left":
            if left:
                self._apply_pose_to_combos(self._left_combos, left.get("fingers", {}))
                self._set_motion_combo(self._left_motion, "static")
                self._record_status.setText("Left hand captured!")
                captured_desc.append(f"Left: {self._get_finger_summary(left.get('fingers', {}))}")
            else:
                self._record_status.setText("Show left hand.")
        elif mode == "right":
            if right:
                self._apply_pose_to_combos(self._right_combos, right.get("fingers", {}))
                self._set_motion_combo(self._right_motion, "static")
                self._record_status.setText("Right hand captured!")
                captured_desc.append(f"Right: {self._get_finger_summary(right.get('fingers', {}))}")
            else:
                self._record_status.setText("Show right hand.")
        else:  # both
            if left:
                self._apply_pose_to_combos(self._left_combos, left.get("fingers", {}))
                self._set_motion_combo(self._left_motion, "static")
                captured_desc.append(f"Left: {self._get_finger_summary(left.get('fingers', {}))}")
            if right:
                self._apply_pose_to_combos(self._right_combos, right.get("fingers", {}))
                self._set_motion_combo(self._right_motion, "static")
                captured_desc.append(f"Right: {self._get_finger_summary(right.get('fingers', {}))}")
            if left and right:
                self._record_status.setText("Both hands captured!")
            else:
                self._record_status.setText("Partial capture.")

        if captured_desc:
            self._capture_summary.setText(" | ".join(captured_desc))

    def _get_finger_summary(self, fingers):
        up = [f.capitalize() for f, state in fingers.items() if state]
        return ", ".join(up) if up else "Closed Fist"

    def _start_recording(self):
        self._error.setText("")
        self._record_samples = []
        self._record_remaining = 5000
        self._record_btn.setEnabled(False)
        self._capture_btn.setEnabled(False)
        self._record_status.setText("Recording started. Hold or move your gesture naturally...")
        self._record_popup = GestureRecordPopup(self)
        self._record_popup.timer_label.setText("5.0s")
        self._record_popup.reset_canvas()
        self._record_popup.show()
        self._record_timer.start(120)

    def _record_tick(self):
        hands = self._get_live_hands() or []
        if hands:
            self._record_samples.append(copy.deepcopy(hands))
        if self._record_popup and self._record_popup.isVisible():
            self._record_popup.update_hands(hands)
        self._record_remaining -= 120
        seconds = max(0.0, self._record_remaining / 1000.0)
        if self._record_remaining > 0:
            self._record_status.setText(f"Recording... {seconds:.1f}s left")
            if self._record_popup and self._record_popup.isVisible():
                self._record_popup.timer_label.setText(f"{seconds:.1f}s")
            return
        self._record_timer.stop()
        self._record_btn.setEnabled(True)
        self._capture_btn.setEnabled(True)
        if self._record_popup is not None:
            self._record_popup.close()
            self._record_popup = None
        self._apply_recording()

    @staticmethod
    def _combos_to_rule(combos):
        return {fname: combo.currentData() for fname, combo in combos.items()}

    def _submit(self):
        self._error.setText("")
        name = self._name.text().strip()
        if not name:
            self._error.setText("Please enter a gesture name.")
            return
        
        # Duplicate check
        existing_names = []
        if hasattr(self.parent(), "action_mapper"):
            existing_names = [m.get("display_name", "").lower() for m in self.parent().action_mapper.mappings.values()]
        
        if name.lower() in existing_names:
            self._error.setText(f"A gesture named '{name}' already exists.")
            return

        if not self._has_active_rule():
            hands = self._get_live_hands() or []
            if hands:
                self._capture_current_pose()
            else:
                self._error.setText("Show your hand and use Capture Pose or Record 5s before creating.")
                return

        mode = self._mode.currentData()
        custom_rule = {"hand_mode": mode}
        if mode == "any":
            any_rule = self._combos_to_rule(self._any_combos)
            custom_rule["any_fingers"] = any_rule
            custom_rule["any_motion"] = self._any_motion.currentData()
            if custom_rule["any_motion"] == "any" and not any(v != "any" for v in any_rule.values()):
                self._error.setText("Set at least one finger rule or motion rule for Any One Hand mode.")
                return
        elif mode == "left":
            left_rule = self._combos_to_rule(self._left_combos)
            custom_rule["left_fingers"] = left_rule
            custom_rule["left_motion"] = self._left_motion.currentData()
            if not any(v != "any" for v in left_rule.values()) and custom_rule["left_motion"] == "any":
                self._error.setText("Set at least one finger rule or motion rule for Left Hand mode.")
                return
        elif mode == "right":
            right_rule = self._combos_to_rule(self._right_combos)
            custom_rule["right_fingers"] = right_rule
            custom_rule["right_motion"] = self._right_motion.currentData()
            if not any(v != "any" for v in right_rule.values()) and custom_rule["right_motion"] == "any":
                self._error.setText("Set at least one finger rule or motion rule for Right Hand mode.")
                return
        else:
            left_rule = self._combos_to_rule(self._left_combos)
            right_rule = self._combos_to_rule(self._right_combos)
            custom_rule["left_fingers"] = left_rule
            custom_rule["right_fingers"] = right_rule
            custom_rule["left_motion"] = self._left_motion.currentData()
            custom_rule["right_motion"] = self._right_motion.currentData()
            if (
                not any(v != "any" for v in left_rule.values())
                and not any(v != "any" for v in right_rule.values())
                and custom_rule["left_motion"] == "any"
                and custom_rule["right_motion"] == "any"
            ):
                self._error.setText("Set at least one finger rule or motion rule for Both Hands mode.")
                return

        action_type = getattr(self, "_action_type", "shortcut")
        keys = []
        description = ACTION_LABELS.get(action_type, "Custom Action")

        if action_type == "shortcut":
            raw = self._shortcut_input.text().strip()
            if not raw:
                self._error.setText("Enter shortcut keys, e.g. ctrl+c.")
                return
            keys = [k.strip() for k in raw.split("+") if k.strip()]
            if not keys:
                self._error.setText("Shortcut format is invalid.")
                return
            description = "Keyboard Shortcut"
        elif action_type == "launch":
            cmd = self._launch_input.text().strip()
            if not cmd:
                self._error.setText("Enter app command/path or URL.")
                return
            keys = [cmd]
            description = "Launch App"

        self.result = {
            "gesture_name": f"Custom:{name}",
            "display_name": name,
            "custom_rule": custom_rule,
            "action_type": action_type,
            "keys": keys,
            "description": description,
        }
        if self._embedded:
            self.created.emit(self.result)
            return
        self.accept()

    def reset_for_new(self):
        self.result = None
        self._error.setText("")
        self._name.clear()
        if hasattr(self, "_shortcut_input"):
            self._shortcut_input.clear()
        if hasattr(self, "_shortcut_preset"):
            self._shortcut_preset.setCurrentIndex(0)
        if hasattr(self, "_launch_input"):
            self._launch_input.clear()
        if hasattr(self, "_launch_preset"):
            self._launch_preset.setCurrentIndex(0)
        if hasattr(self, "_action_buttons"):
            self._set_action_type("shortcut")
        self._mode.setCurrentIndex(max(0, self._mode.findData("any")))
        self._reset_rules()
        if hasattr(self, "_advanced_toggle"):
            self._advanced_toggle.setChecked(False)
            self._toggle_advanced_rules(False)
        self._sync_mode_ui()
        self._record_status.setText("Ready to capture")
        self._capture_summary.clear()
        if hasattr(self, "_record_keys_btn"):
            self._record_keys_btn.setChecked(False)
        self._name.setFocus()

    def closeEvent(self, event):
        self._timer.stop()
        self._record_timer.stop()
        if self._record_popup is not None:
            self._record_popup.close()
            self._record_popup = None
        super().closeEvent(event)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  Simplified Gesture Selection Dialog
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
class NewGestureDialog(QDialog):
    def __init__(self, parent, existing_gestures, get_live_hands=None):
        super().__init__(parent)
        self.setWindowTitle("Add Gesture")
        self.setModal(True)
        self.setFixedSize(620, 560)
        self.result = None

        self._existing = set(existing_gestures)
        self._selected_gesture = None
        self._selected_custom_rule = None
        self._selected_preset_name = None
        self._all_app_items = []
        self._get_live_hands = get_live_hands or (lambda: [])
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(0)

        # â”€â”€ Header â”€â”€
        title = QLabel("Add Gesture Mapping")
        title.setObjectName("dlgTitle")
        root.addWidget(title)
        root.addSpacing(12)

        # â”€â”€ Step stack â”€â”€
        self._step_stack = QStackedWidget()

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        #  PAGE 0: Create custom gesture
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        page0 = QWidget()
        p0 = QVBoxLayout(page0)
        p0.setContentsMargins(0, 0, 0, 0)
        p0.setSpacing(8)

        p0_sub = QLabel("Create a custom gesture to continue.")
        p0_sub.setObjectName("dlgSub")
        p0_sub.setAlignment(Qt.AlignCenter)
        p0.addWidget(p0_sub)
        p0.addSpacing(12)

        self._gesture_buttons = {}

        custom_btn = QPushButton("Create Custom Gesture")
        custom_btn.setObjectName("submitBtn")
        custom_btn.setCursor(Qt.PointingHandCursor)
        custom_btn.clicked.connect(self._create_custom_gesture)
        p0.addWidget(custom_btn)
        p0.addStretch(1)

        self._step_stack.addWidget(page0)

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        #  PAGE 1: Pick action type (big clear buttons)
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        page1 = QWidget()
        p1 = QVBoxLayout(page1)
        p1.setContentsMargins(0, 0, 0, 0)
        p1.setSpacing(8)

        # Selected gesture bar
        self._sel_bar = QFrame()
        self._sel_bar.setObjectName("selBar")
        sb_lay = QHBoxLayout(self._sel_bar)
        sb_lay.setContentsMargins(10, 6, 10, 6)
        sb_lay.setSpacing(8)

        self._sel_icon = QLabel("")
        self._sel_icon.setStyleSheet(f"font-size: 22px; background: transparent; border: none;")
        self._sel_name = QLabel("")
        self._sel_name.setStyleSheet(f"font-size: 13px; font-weight: 700; color: {CLR_WHITE}; background: transparent; border: none;")
        back_btn = QPushButton("\u2190 Back")
        back_btn.setObjectName("backBtn")
        back_btn.setCursor(Qt.PointingHandCursor)
        back_btn.clicked.connect(lambda: self._step_stack.setCurrentIndex(0))

        sb_lay.addWidget(self._sel_icon)
        sb_lay.addWidget(self._sel_name, 1)
        sb_lay.addWidget(back_btn)
        p1.addWidget(self._sel_bar)

        p1_sub = QLabel("What should this gesture do?")
        p1_sub.setObjectName("dlgSub")
        p1.addWidget(p1_sub)
        p1.addSpacing(2)

        # Action type cards â€” vertical, clear descriptions
        action_defs = [
            ("shortcut", "\u2328", "Keyboard Shortcut", "Trigger a key combination like Ctrl+C, Alt+Tab, etc."),
            ("mouse_click", "\U0001F5B1", "Mouse Click", "Perform a left mouse click at current cursor position"),
            ("mouse_right_click", "\U0001F5B1", "Right Click", "Perform a right mouse click at current cursor position"),
            ("launch", "\U0001F680", "Launch App", "Open an application or website"),
        ]

        for atype, aicon, aname, adesc in action_defs:
            abtn = QPushButton()
            abtn.setObjectName("actionCard")
            abtn.setCursor(Qt.PointingHandCursor)
            abtn.setFixedHeight(52)

            ab_lay = QHBoxLayout(abtn)
            ab_lay.setContentsMargins(12, 6, 12, 6)
            ab_lay.setSpacing(10)

            a_ic = QLabel(aicon)
            a_ic.setFixedWidth(28)
            a_ic.setAlignment(Qt.AlignCenter)
            a_ic.setStyleSheet(f"font-size: 18px; background: transparent; border: none; color: {CLR_TEXT};")
            a_col = QVBoxLayout()
            a_col.setSpacing(0)
            a_n = QLabel(aname)
            a_n.setStyleSheet(f"font-size: 12px; font-weight: 700; color: {CLR_WHITE}; background: transparent; border: none;")
            a_d = QLabel(adesc)
            a_d.setStyleSheet(f"font-size: 10px; color: {CLR_TEXT_MUTED}; background: transparent; border: none;")
            a_col.addWidget(a_n)
            a_col.addWidget(a_d)

            arrow = QLabel("\u203A")
            arrow.setStyleSheet(f"font-size: 18px; color: {CLR_TEXT_MUTED}; background: transparent; border: none;")

            ab_lay.addWidget(a_ic)
            ab_lay.addLayout(a_col, 1)
            ab_lay.addWidget(arrow)

            abtn.clicked.connect(lambda c=False, at=atype: self._select_action_type(at))
            p1.addWidget(abtn)

        p1.addStretch(1)
        self._step_stack.addWidget(page1)

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        #  PAGE 2: Configure â€” Shortcut presets
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        page2 = QWidget()
        p2 = QVBoxLayout(page2)
        p2.setContentsMargins(0, 0, 0, 0)
        p2.setSpacing(6)

        p2_back = QPushButton("\u2190 Change Action")
        p2_back.setObjectName("backBtn")
        p2_back.setCursor(Qt.PointingHandCursor)
        p2_back.clicked.connect(lambda: self._step_stack.setCurrentIndex(1))
        p2.addWidget(p2_back, 0, Qt.AlignLeft)

        p2_sub = QLabel("Pick a shortcut or type a custom one")
        p2_sub.setObjectName("dlgSub")
        p2.addWidget(p2_sub)

        # Searchable shortcut list
        self._shortcut_search = QLineEdit()
        self._shortcut_search.setObjectName("searchInput")
        self._shortcut_search.setPlaceholderText("\U0001F50D  Search shortcuts... (e.g. copy, volume, tab)")
        self._shortcut_search.textChanged.connect(self._filter_shortcuts)
        p2.addWidget(self._shortcut_search)

        self._shortcut_list = QListWidget()
        self._shortcut_list.setObjectName("pickList")
        self._shortcut_list.itemClicked.connect(self._on_shortcut_picked)

        # Populate all presets
        self._all_preset_items = []
        for cat_name, preset_names in PRESET_CATEGORIES.items():
            for pname in preset_names:
                keys_str = SHORTCUT_PRESETS.get(pname, "")
                item = QListWidgetItem(f"  {pname}    {keys_str}")
                item.setData(Qt.UserRole, pname)
                item.setData(Qt.UserRole + 1, keys_str)
                self._shortcut_list.addItem(item)
                self._all_preset_items.append((pname.lower(), keys_str.lower(), item))

        p2.addWidget(self._shortcut_list, 1)

        # Custom shortcut input
        p2_or = QLabel("OR TYPE CUSTOM")
        p2_or.setObjectName("stepLabel")
        p2.addWidget(p2_or)

        self._custom_shortcut = QLineEdit()
        self._custom_shortcut.setObjectName("searchInput")
        self._custom_shortcut.setPlaceholderText("e.g. ctrl+shift+n")
        p2.addWidget(self._custom_shortcut)

        p2_submit = QPushButton("Create Mapping")
        p2_submit.setObjectName("submitBtn")
        p2_submit.setCursor(Qt.PointingHandCursor)
        p2_submit.clicked.connect(self._submit_shortcut)
        p2.addWidget(p2_submit)

        self._p2_error = QLabel("")
        self._p2_error.setObjectName("error")
        p2.addWidget(self._p2_error)

        self._step_stack.addWidget(page2)

        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        #  PAGE 3: Configure â€” Launch app search
        # â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
        page3 = QWidget()
        p3 = QVBoxLayout(page3)
        p3.setContentsMargins(0, 0, 0, 0)
        p3.setSpacing(6)

        p3_back = QPushButton("\u2190 Change Action")
        p3_back.setObjectName("backBtn")
        p3_back.setCursor(Qt.PointingHandCursor)
        p3_back.clicked.connect(lambda: self._step_stack.setCurrentIndex(1))
        p3.addWidget(p3_back, 0, Qt.AlignLeft)

        p3_sub = QLabel("Search and select an app, or type a custom path")
        p3_sub.setObjectName("dlgSub")
        p3.addWidget(p3_sub)

        self._app_search = QLineEdit()
        self._app_search.setObjectName("searchInput")
        self._app_search.setPlaceholderText("\U0001F50D  Search apps... (e.g. chrome, notepad, spotify)")
        self._app_search.textChanged.connect(self._filter_apps)
        p3.addWidget(self._app_search)

        self._app_list = QListWidget()
        self._app_list.setObjectName("pickList")
        self._app_list.itemClicked.connect(self._on_app_picked)

        # Populate apps with category headers + system scan
        self._all_app_items = []
        self._category_items = []

        # Add predefined categories first
        for cat_name, apps in LAUNCHABLE_APPS_BY_CATEGORY.items():
            # Category header (non-selectable)
            cat_item = QListWidgetItem(f"  \u2500\u2500  {cat_name.upper()}  \u2500\u2500")
            cat_item.setFlags(Qt.NoItemFlags)
            cat_item.setData(Qt.UserRole, None)
            cat_font = cat_item.font()
            cat_font.setBold(True)
            cat_font.setPointSize(8)
            cat_item.setFont(cat_font)
            cat_item.setForeground(QColor(CLR_TEXT_MUTED))
            self._app_list.addItem(cat_item)
            self._category_items.append(cat_item)

            for app_name, info in apps.items():
                icon = info["icon"]
                cmd = info["cmd"]
                item = QListWidgetItem(f"  {icon}  {app_name}    {cmd}")
                item.setData(Qt.UserRole, app_name)
                item.setData(Qt.UserRole + 1, cmd)
                item.setData(Qt.UserRole + 2, cat_name)
                self._app_list.addItem(item)
                self._all_app_items.append((app_name.lower(), cmd.lower(), cat_name.lower(), item))

        # Add "System Apps" category header for scanned apps
        sys_cat_item = QListWidgetItem(f"  \u2500\u2500  SYSTEM APPS (SCANNED)  \u2500\u2500")
        sys_cat_item.setFlags(Qt.NoItemFlags)
        sys_cat_item.setData(Qt.UserRole, None)
        sys_cat_font = sys_cat_item.font()
        sys_cat_font.setBold(True)
        sys_cat_font.setPointSize(8)
        sys_cat_item.setFont(sys_cat_font)
        sys_cat_item.setForeground(QColor(CLR_TEXT_MUTED))
        self._app_list.addItem(sys_cat_item)
        self._category_items.append(sys_cat_item)
        self._sys_cat_start_idx = self._app_list.count()

        # Populate with scanned system apps (non-blocking)
        self._populate_system_apps()

        p3.addWidget(self._app_list, 1)

        # Custom path input
        p3_or = QLabel("OR TYPE CUSTOM PATH")
        p3_or.setObjectName("stepLabel")
        p3.addWidget(p3_or)

        self._custom_app = QLineEdit()
        self._custom_app.setObjectName("searchInput")
        self._custom_app.setPlaceholderText("e.g. C:\\\\Program Files\\\\MyApp.exe or https://...")
        p3.addWidget(self._custom_app)

        p3_submit = QPushButton("Create Mapping")
        p3_submit.setObjectName("submitBtn")
        p3_submit.setCursor(Qt.PointingHandCursor)
        p3_submit.clicked.connect(self._submit_launch)
        p3.addWidget(p3_submit)

        self._p3_error = QLabel("")
        self._p3_error.setObjectName("error")
        p3.addWidget(self._p3_error)

        self._step_stack.addWidget(page3)

        root.addWidget(self._step_stack, 1)

    # â”€â”€ Navigation â”€â”€

    def _exec_centered_with_animation(self, dialog):
        host = self.parent() if isinstance(self.parent(), QWidget) else self
        if isinstance(host, QWidget) and host.isVisible():
            host_rect = host.frameGeometry()
            tx = host_rect.x() + (host_rect.width() - dialog.width()) // 2
            ty = host_rect.y() + (host_rect.height() - dialog.height()) // 2
            dialog.move(max(0, tx), max(0, ty))

        dialog.setWindowModality(Qt.WindowModal)
        dialog.setWindowFlag(Qt.Tool, True)
        dialog.setWindowOpacity(0.0)
        end_pos = dialog.pos()
        start_pos = end_pos + QPoint(0, 24)
        dialog.move(start_pos)

        fade_anim = QPropertyAnimation(dialog, b"windowOpacity", dialog)
        fade_anim.setDuration(180)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setEasingCurve(QEasingCurve.OutCubic)

        slide_anim = QPropertyAnimation(dialog, b"pos", dialog)
        slide_anim.setDuration(220)
        slide_anim.setStartValue(start_pos)
        slide_anim.setEndValue(end_pos)
        slide_anim.setEasingCurve(QEasingCurve.OutCubic)

        dialog._open_fade_anim = fade_anim
        dialog._open_slide_anim = slide_anim
        QTimer.singleShot(0, fade_anim.start)
        QTimer.singleShot(0, slide_anim.start)
        return dialog.exec()

    def _create_custom_gesture(self):
        host = self.parent() if isinstance(self.parent(), QWidget) else self
        dialog = CustomGestureBuilderDialog(
            host,
            get_live_hands=self._get_live_hands,
            get_live_frame=lambda: self.parent()._latest_camera_image if self.parent() else None,
        )
        if self._exec_centered_with_animation(dialog) != QDialog.Accepted or not dialog.result:
            return
        self.set_preselected_custom_gesture(
            dialog.result["gesture_name"],
            dialog.result["display_name"],
            dialog.result["custom_rule"],
        )

    def set_preselected_custom_gesture(self, gesture_name, display_name, custom_rule):
        if gesture_name in self._existing:
            QMessageBox.warning(self, "Duplicate Gesture", "Custom gesture with same name already exists.")
            return False
        self._selected_custom_rule = custom_rule
        self._selected_gesture = gesture_name
        self._sel_icon.setText("\U0001F4A1")
        self._sel_name.setText(display_name)
        self._step_stack.setCurrentIndex(1)
        return True

    def _select_gesture(self, gesture):
        self._selected_gesture = gesture
        self._selected_custom_rule = None
        self._sel_icon.setText(GESTURE_ICONS.get(gesture, "\u270B"))
        gesture_display = gesture.replace("_", " ")
        self._sel_name.setText(gesture_display)

        for g, btn in self._gesture_buttons.items():
            if g == gesture:
                btn.setStyleSheet(f"""
                    QPushButton#gestureCard {{
                        background: {CLR_SELECTED};
                        border: 1px solid {CLR_ACCENT_GLOW};
                        border-radius: 10px;
                    }}
                """)
            else:
                btn.setStyleSheet("")

        self._step_stack.setCurrentIndex(1)

    def _select_action_type(self, action_type):
        if not self._selected_gesture:
            return

        if action_type == "shortcut":
            self._step_stack.setCurrentIndex(2)
        elif action_type == "launch":
            self._step_stack.setCurrentIndex(3)
        elif action_type in ("mouse_click", "mouse_right_click"):
            # No config needed â€” create immediately
            self.result = {
                "gesture": self._selected_gesture,
                "action_type": action_type,
                "keys": [],
                "description": ACTION_LABELS.get(action_type, "Mouse Action"),
            }
            if self._selected_custom_rule:
                self.result["custom_rule"] = self._selected_custom_rule
            self.accept()

    # â”€â”€ Shortcut search & pick â”€â”€

    def _filter_shortcuts(self, text):
        query = text.strip().lower()
        for name_lower, keys_lower, item in self._all_preset_items:
            matches = not query or query in name_lower or query in keys_lower
            item.setHidden(not matches)

    def _on_shortcut_picked(self, item):
        name = item.data(Qt.UserRole)
        keys = item.data(Qt.UserRole + 1)
        if name and keys:
            self._custom_shortcut.setText(keys)
            self._selected_preset_name = name

            # Highlight selected row
            for _, _, it in self._all_preset_items:
                font = it.font()
                font.setBold(it is item)
                it.setFont(font)

    def _submit_shortcut(self):
        if not self._selected_gesture:
            self._p2_error.setText("Go back and select a gesture first.")
            return

        keys_raw = self._custom_shortcut.text().strip()
        if not keys_raw:
            self._p2_error.setText("Select a preset above or type a key combo.")
            return

        desc = self._selected_preset_name or keys_raw
        keys = [k.strip() for k in keys_raw.split("+") if k.strip()]
        self.result = {
            "gesture": self._selected_gesture,
            "action_type": "shortcut",
            "keys": keys,
            "description": desc,
        }
        if self._selected_custom_rule:
            self.result["custom_rule"] = self._selected_custom_rule
        self.accept()

    # â”€â”€ App search & pick â”€â”€

    def _filter_apps(self, text):
        query = text.strip().lower()
        if not query:
            for _, _, _, item in self._all_app_items:
                item.setHidden(False)
            for cat_item in self._category_items:
                cat_item.setHidden(False)
            return

        def match_score(name_lower: str, cmd_lower: str, cat_lower: str) -> int:
            if query == name_lower:
                return 1000
            if query == cmd_lower:
                return 950
            if name_lower.startswith(query):
                return 900
            if cmd_lower.startswith(query):
                return 850
            if f" {query}" in name_lower or f"{query} " in name_lower:
                return 800
            if query in name_lower:
                return 700
            if query in cmd_lower:
                return 600
            if query in cat_lower:
                return 500
            return 0

        ranked = []
        for idx, (name_lower, cmd_lower, cat_lower, item) in enumerate(self._all_app_items):
            score = match_score(name_lower, cmd_lower, cat_lower)
            if score > 0:
                ranked.append((score, -idx, cat_lower, item))

        for _, _, _, item in self._all_app_items:
            item.setHidden(True)
        for cat_item in self._category_items:
            cat_item.setHidden(True)

        if not ranked:
            return

        ranked.sort(reverse=True)
        best_cat = ranked[0][2]
        best_item = ranked[0][3]
        best_item.setHidden(False)

        for cat_item in self._category_items:
            cat_text = cat_item.text().strip().strip("\u2500").strip().lower()
            if cat_text == best_cat:
                cat_item.setHidden(False)
                break

    def _populate_system_apps(self):
        """Populate system-scanned apps asynchronously."""
        sys_apps = _get_system_apps()
        if _SCAN_IN_PROGRESS and not sys_apps:
            QTimer.singleShot(700, self._populate_system_apps)
            return
        if not sys_apps:
            return

        existing_names = {
            item.data(Qt.UserRole).lower()
            if item.data(Qt.UserRole)
            else ""
            for _, _, _, item in self._all_app_items
        }

        for app_name, info in sys_apps.items():
            if app_name.lower() in existing_names:
                continue
            icon = info.get("icon", "📦")
            cmd = str(info.get("cmd", "")).strip()
            if not cmd:
                continue
            cmd_preview = cmd if len(cmd) <= 46 else f"{cmd[:46]}..."
            item = QListWidgetItem(f"  {icon}  {app_name}    {cmd_preview}")
            item.setData(Qt.UserRole, app_name)
            item.setData(Qt.UserRole + 1, cmd)
            item.setData(Qt.UserRole + 2, "system apps")
            self._app_list.addItem(item)
            self._all_app_items.append((app_name.lower(), cmd.lower(), "system apps", item))

    def _on_app_picked(self, item):
        name = item.data(Qt.UserRole)
        cmd = item.data(Qt.UserRole + 1)
        if name and cmd:
            self._custom_app.setText(cmd)

            for name_lower, cmd_lower, cat_lower, it in self._all_app_items:
                font = it.font()
                font.setBold(it is item)
                it.setFont(font)

    def _submit_launch(self):
        if not self._selected_gesture:
            self._p3_error.setText("Go back and select a gesture first.")
            return

        app_raw = self._custom_app.text().strip()
        if not app_raw:
            self._p3_error.setText("Select an app above or type a path/command.")
            return

        # Find friendly name if it matches a known app
        desc = app_raw
        for app_name, info in LAUNCHABLE_APPS.items():
            if info["cmd"] == app_raw:
                desc = f"Launch {app_name}"
                break

        self.result = {
            "gesture": self._selected_gesture,
            "action_type": "launch",
            "keys": [app_raw],
            "description": desc,
        }
        if self._selected_custom_rule:
            self.result["custom_rule"] = self._selected_custom_rule
        self.accept()

    # â”€â”€ Styling â”€â”€

    def _apply_style(self):
        self.setStyleSheet(f"""
            QDialog {{
                background: {CLR_BG};
                color: {CLR_TEXT};
                font-family: {FONT_FAMILY};
            }}
            QLabel#dlgTitle {{
                color: {CLR_WHITE};
                font-size: 20px;
                font-weight: 700;
            }}
            QLabel#dlgSub {{
                color: {CLR_TEXT_DIM};
                font-size: 11px;
                margin-bottom: 2px;
            }}
            QLabel#stepLabel {{
                color: {CLR_TEXT_MUTED};
                font-size: 9px;
                font-weight: 700;
                letter-spacing: 1.5px;
                padding: 6px 0 2px 0;
            }}
            QLabel#error {{
                color: {CLR_RED};
                font-size: 10px;
                min-height: 14px;
            }}

            /* â”€â”€ Gesture cards â”€â”€ */
            QPushButton#gestureCard {{
                background: {CLR_CARD};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 10px;
            }}
            QPushButton#gestureCard:hover {{
                background: {CLR_CARD_HOVER};
                border: 1px solid {CLR_BORDER};
            }}

            /* â”€â”€ Selected gesture bar â”€â”€ */
            QFrame#selBar {{
                background: {CLR_GLASS};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 8px;
            }}

            /* â”€â”€ Back button â”€â”€ */
            QPushButton#backBtn {{
                background: transparent;
                color: {CLR_TEXT_DIM};
                border: none;
                font-size: 11px;
                font-weight: 600;
                padding: 4px 8px;
            }}
            QPushButton#backBtn:hover {{
                color: {CLR_WHITE};
            }}

            /* â”€â”€ Action type cards â”€â”€ */
            QPushButton#actionCard {{
                background: {CLR_CARD};
                border: 1px solid {CLR_BORDER_SOFT};
                border-radius: 10px;
                text-align: left;
            }}
            QPushButton#actionCard:hover {{
               (background: {CLR_CARD_HOVER};
                border: 1px solid {CLR_BORDER};
            }}

            /* â”€â”€ Search input â”€â”€ */
            QLineEdit#searchInput {{
                background: {CLR_INPUT};
                color: {CLR_TEXT};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 32px;
                padding: 4px 10px;
                font-size: 12px;
            }}
            QLineEdit#searchInput:focus {{
                border: 1px solid {CLR_ACCENT_GLOW};
            }}

            /* â”€â”€ Pick list (shortcuts / apps) â”€â”€ */
            QListWidget#pickList {{
                background: {CLR_SURFACE};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                color: {CLR_TEXT};
                padding: 4px;
                outline: none;
                font-size: 11px;
            }}
            QListWidget#pickList::item {{
                border: none;
                padding: 6px 8px;
                border-radius: 6px;
                margin: 1px 0;
            }}
            QListWidget#pickList::item:hover {{
                background: {CLR_ACCENT_DIM};
            }}
            QListWidget#pickList::item:selected {{
                background: {CLR_SELECTED};
                color: {CLR_WHITE};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}

            /* â”€â”€ Submit button â”€â”€ */
            QPushButton#submitBtn {{
                background: {CLR_ACCENT};
                color: {CLR_WHITE};
                border: 1px solid {CLR_BORDER};
                border-radius: 8px;
                min-height: 36px;
                font-weight: 700;
                font-size: 12px;
            }}
            QPushButton#submitBtn:hover {{
                background: {CLR_ACCENT_HOVER};
                border: 1px solid {CLR_ACCENT_GLOW};
            }}
        """)


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
#  Main Window
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
