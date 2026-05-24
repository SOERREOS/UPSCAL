# -*- coding: utf-8 -*-
"""
UPSCAL desktop UI.

The Real-ESRGAN processing code lives in upscaler.py. This file keeps the
native PyQt shell thin: queue images, collect settings, run the worker, and
render the final Claude-designed layout.
"""

from __future__ import annotations

import os
import sys
import math
import json
import hashlib
import locale
import platform
import subprocess
import tempfile
import traceback
import threading
import time
import ctypes
import urllib.request
from urllib.parse import unquote, urlparse
from dataclasses import dataclass, field
from pathlib import Path

if sys.platform == "win32":
    from ctypes import wintypes

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
else:
    wintypes = None

if sys.platform == "darwin":
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

from PIL import Image

from PyQt6.QtCore import (
    Qt,
    QEvent,
    QPoint,
    QPointF,
    QRect,
    QRectF,
    QSize,
    QThread,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetrics,
    QImage,
    QIcon,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPaintEvent,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractButton,
    QButtonGroup,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QProgressDialog,
    QScrollArea,
    QSizeGrip,
    QSizePolicy,
    QSlider,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


# Claude design tokens
BG_BASE = "#08080b"
BG_CANVAS = "#0d0d12"
BG_SURFACE = "#14141c"
BG_ELEVATED = "#1c1c26"
BG_HOVER = "#252533"
BG_INPUT = "#0a0a0f"
BORDER = "#20202b"
BORDER_SOFT = "#121219"
BORDER_STRONG = "#2d2d3d"
TEXT = "#ecedf2"
TEXT_SEC = "#9a9bab"
TEXT_MUTED = "#5e5f70"
TEXT_FAINT = "#3a3b48"
ACCENT = "#6366f1"
ACCENT_BRIGHT = "#818cf8"
ACCENT_DIM = "#4338ca"
SUCCESS = "#10b981"
ERROR = "#ef4444"
WARNING = "#f59e0b"

FONT = "Malgun Gothic"
MONO = "Consolas"

APP_VERSION = "0.1.0"
UPDATE_MANIFEST_URL = os.environ.get("UPSCAL_UPDATE_MANIFEST_URL", "").strip()
UPDATE_CHECK_TIMEOUT = 8

IMAGE_FILTER = "이미지 파일 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;모든 파일 (*)"
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")

WM_NCHITTEST = 0x0084
HTCLIENT = 1
HTCAPTION = 2
HTLEFT = 10
HTRIGHT = 11
HTTOP = 12
HTTOPLEFT = 13
HTTOPRIGHT = 14
HTBOTTOM = 15
HTBOTTOMLEFT = 16
HTBOTTOMRIGHT = 17
RESIZE_MARGIN = 8

APP_STYLE = f"""
QWidget {{
    background: {BG_BASE};
    color: {TEXT};
    font-family: '{FONT}', 'Segoe UI', sans-serif;
    font-size: 12px;
    border: none;
}}

QToolTip {{
    background: {BG_ELEVATED};
    color: {TEXT};
    border: 1px solid {BORDER_STRONG};
    padding: 6px 8px;
    border-radius: 4px;
}}

QScrollBar:horizontal {{
    background: {BG_SURFACE};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER_STRONG};
    border-radius: 4px;
    min-width: 24px;
}}
QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar:vertical {{
    background: {BG_SURFACE};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER_STRONG};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QSlider::groove:horizontal {{
    background: {BG_INPUT};
    height: 4px;
    border-radius: 2px;
}}
QSlider::sub-page:horizontal {{
    background: {ACCENT};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT_BRIGHT};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QPushButton {{
    background: {BG_ELEVATED};
    color: {TEXT};
    border: none;
    border-radius: 7px;
    padding: 7px 10px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: {BG_HOVER};
}}
QPushButton:disabled {{
    color: {TEXT_FAINT};
    background: {BG_SURFACE};
    border: none;
}}
"""


def qc(hex_color: str, alpha: int | None = None) -> QColor:
    color = QColor(hex_color)
    if alpha is not None:
        color.setAlpha(alpha)
    return color


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    path = base / name
    if path.exists():
        return path
    return Path(__file__).resolve().parent / name


def update_manifest_url() -> str:
    if UPDATE_MANIFEST_URL:
        return UPDATE_MANIFEST_URL

    candidates = [
        Path(sys.executable).resolve().parent / "update_config.json",
        resource_path("update_config.json"),
    ]
    for path in candidates:
        try:
            if path.exists():
                payload = json.loads(path.read_text(encoding="utf-8"))
                url = str(payload.get("manifest_url", "")).strip()
                if url:
                    return url
        except Exception:
            continue
    return ""


def update_platform_keys() -> tuple[str, ...]:
    machine = platform.machine().lower()
    if sys.platform == "win32":
        return ("windows-x64", "windows", "win32")
    if sys.platform == "darwin":
        arch_key = "macos-arm64" if machine in {"arm64", "aarch64"} else "macos-x64"
        return (arch_key, "macos", "darwin")
    if sys.platform.startswith("linux"):
        return ("linux-x64", "linux")
    return (sys.platform,)


def update_payload_for_current_platform(payload: dict) -> dict | None:
    platforms = payload.get("platforms")
    if isinstance(platforms, dict):
        for key in update_platform_keys():
            candidate = platforms.get(key)
            if isinstance(candidate, dict):
                merged = dict(payload)
                merged.update(candidate)
                merged["version"] = candidate.get("version") or payload.get("version")
                return merged
            if isinstance(candidate, str):
                merged = dict(payload)
                merged["url"] = candidate
                return merged
        if sys.platform == "win32" and payload.get("url"):
            return payload
        return None

    # The legacy manifest is Windows-only. Other platforms should not download
    # the Windows installer by mistake.
    if sys.platform != "win32":
        return None
    return payload


def update_download_filename(url: str, version: str) -> str:
    parsed_name = unquote(Path(urlparse(url).path).name).strip()
    if parsed_name:
        return parsed_name
    safe_version = "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in version)
    if sys.platform == "win32":
        return f"UPSCAL_Setup_{safe_version}.exe"
    if sys.platform == "darwin":
        return f"UPSCAL_macOS_{safe_version}.dmg"
    return f"UPSCAL_Update_{safe_version}"


def open_update_installer(path: str):
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def pil_to_pixmap(img: Image.Image) -> QPixmap:
    rgb = img.convert("RGB")
    data = rgb.tobytes("raw", "RGB")
    qimg = QImage(data, rgb.width, rgb.height, rgb.width * 3, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg)


def image_size_text(img: Image.Image | None) -> str:
    if img is None:
        return "-"
    return f"{img.width} x {img.height}"


def output_size_text(img: Image.Image | None, scale: int) -> str:
    if img is None:
        return "-"
    return f"{img.width * scale} x {img.height * scale}"


def format_duration(seconds: float | int | None) -> str:
    if seconds is None or seconds <= 0:
        return "곧 완료"
    seconds = int(seconds)
    minutes, sec = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"약 {hours}시간 {minutes}분"
    if minutes:
        return f"약 {minutes}분 {sec:02d}초"
    return f"약 {sec}초"


def estimate_duration_seconds(item: "QueueItem | None", scale: int, tile: int, gpu_info: str) -> float:
    if item is None:
        return 0.0
    out_mp = (item.source.width * scale) * (item.source.height * scale) / 1_000_000
    gpu = bool(gpu_info and "CPU" not in gpu_info.upper() and "감지" not in gpu_info)
    rate = 1.15 if gpu else 0.12
    tile_factor = 1.0 if tile >= 512 else 1.18
    scale_factor = 1.25 if scale == 8 else 1.0
    return max(12.0, (out_mp / rate) * tile_factor * scale_factor + 8.0)


def elided(text: str, font: QFont, width: int) -> str:
    return QFontMetrics(font).elidedText(text, Qt.TextElideMode.ElideMiddle, max(16, width))


def version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for chunk in str(value).replace("-", ".").replace("_", ".").split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits or 0))
    while len(parts) < 4:
        parts.append(0)
    return tuple(parts)


def is_korean_locale() -> bool:
    try:
        lang = locale.getlocale()[0] or ""
    except Exception:
        lang = ""
    return lang.lower().startswith("ko")


@dataclass
class OutputSettings:
    model_type: str = "general"
    scale: int = 4
    dpi: int = 300
    fmt: str = "JPG"
    tile: int = 512
    detail: int = 65


@dataclass
class QueueItem:
    item_id: int
    path: str
    source: Image.Image
    settings: OutputSettings = field(default_factory=OutputSettings)
    result: Image.Image | None = None
    state: str = "pending"
    progress: int = 0
    error: str = ""

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass
class UpdateInfo:
    version: str
    url: str
    sha256: str = ""
    notes_ko: str = ""
    notes_en: str = ""


class UpdateCheckWorker(QThread):
    update_available = pyqtSignal(object)
    no_update = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, manifest_url: str, current_version: str):
        super().__init__()
        self._manifest_url = manifest_url
        self._current_version = current_version

    def run(self):
        try:
            req = urllib.request.Request(
                self._manifest_url,
                headers={"User-Agent": f"UPSCAL/{self._current_version}"},
            )
            with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT) as response:
                payload = json.loads(response.read().decode("utf-8"))

            platform_payload = update_payload_for_current_platform(payload)
            if platform_payload is None:
                self.no_update.emit()
                return

            version = str(platform_payload.get("version", "")).strip()
            url = str(platform_payload.get("url") or platform_payload.get("installer_url") or "").strip()
            if not version or not url:
                self.no_update.emit()
                return

            if version_key(version) > version_key(self._current_version):
                self.update_available.emit(
                    UpdateInfo(
                        version=version,
                        url=url,
                        sha256=str(platform_payload.get("sha256", "")).strip(),
                        notes_ko=str(platform_payload.get("notes_ko") or payload.get("notes_ko") or payload.get("notes") or "").strip(),
                        notes_en=str(platform_payload.get("notes_en") or payload.get("notes_en") or payload.get("notes") or "").strip(),
                    )
                )
            else:
                self.no_update.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class UpdateDownloadWorker(QThread):
    progress = pyqtSignal(int)
    downloaded = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, info: UpdateInfo):
        super().__init__()
        self._info = info
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            out_path = Path(tempfile.gettempdir()) / update_download_filename(self._info.url, self._info.version)
            req = urllib.request.Request(self._info.url, headers={"User-Agent": f"UPSCAL/{APP_VERSION}"})
            hasher = hashlib.sha256()

            with urllib.request.urlopen(req, timeout=UPDATE_CHECK_TIMEOUT) as response, open(out_path, "wb") as out:
                total = int(response.headers.get("Content-Length") or 0)
                received = 0
                while True:
                    if self._cancelled:
                        raise RuntimeError("cancelled")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    hasher.update(chunk)
                    received += len(chunk)
                    if total:
                        self.progress.emit(max(0, min(100, int(received * 100 / total))))

            expected = self._info.sha256.lower().replace(" ", "")
            if expected and hasher.hexdigest().lower() != expected:
                out_path.unlink(missing_ok=True)
                raise ValueError("downloaded installer verification failed")

            self.progress.emit(100)
            self.downloaded.emit(str(out_path))
        except Exception as exc:
            if str(exc) != "cancelled":
                self.error.emit(str(exc))


class NodeState:
    IDLE = "idle"
    ACTIVE = "active"
    DONE = "done"
    ERROR = "error"


class UpscaleWorker(QThread):
    progress = pyqtSignal(float, str)
    finished = pyqtSignal(object)
    error = pyqtSignal(str)

    def __init__(
        self,
        pil_image: Image.Image,
        model_type: str,
        target_scale: int,
        output_dpi: int,
        tile_size: int,
        detail_strength: float,
    ):
        super().__init__()
        self._pil_image = pil_image
        self._model_type = model_type
        self._target_scale = target_scale
        self._output_dpi = output_dpi
        self._tile_size = tile_size
        self._detail_strength = detail_strength

    def run(self):
        try:
            from upscaler import upscale_image

            result = upscale_image(
                pil_image=self._pil_image,
                model_type=self._model_type,
                target_scale=self._target_scale,
                output_dpi=self._output_dpi,
                tile_size=self._tile_size,
                detail_strength=self._detail_strength,
                progress_cb=self._progress_cb,
            )
            self.finished.emit(result)
        except Exception:
            self.error.emit(traceback.format_exc())

    def _progress_cb(self, frac: float, msg: str):
        self.progress.emit(frac, msg)


class LogoWidget(QWidget):
    def __init__(self, size: int = 22, parent=None):
        super().__init__(parent)
        self._size = size
        self._pixmap = QPixmap(str(resource_path("Icon.png")))
        self.setFixedSize(size, size)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)
        if not self._pixmap.isNull():
            painter.drawPixmap(rect.toRect(), self._pixmap)
            return

        grad = QLinearGradient(rect.topLeft(), rect.bottomRight())
        grad.setColorAt(0, qc(ACCENT_BRIGHT))
        grad.setColorAt(1, qc(ACCENT_DIM))
        painter.setBrush(grad)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 6, 6)

        pen = QPen(qc("#ffffff"), max(1.4, self._size * 0.08), Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        w = self.width()
        h = self.height()
        path = QPainterPath()
        path.moveTo(w * 0.34, h * 0.36)
        path.lineTo(w * 0.34, h * 0.58)
        path.cubicTo(w * 0.34, h * 0.76, w * 0.66, h * 0.76, w * 0.66, h * 0.58)
        path.lineTo(w * 0.66, h * 0.36)
        painter.drawPath(path)
        painter.drawLine(QPointF(w * 0.5, h * 0.18), QPointF(w * 0.5, h * 0.38))
        painter.drawLine(QPointF(w * 0.5, h * 0.18), QPointF(w * 0.38, h * 0.30))
        painter.drawLine(QPointF(w * 0.5, h * 0.18), QPointF(w * 0.62, h * 0.30))


class ChromeButton(QPushButton):
    def __init__(self, text: str, parent=None, danger: bool = False):
        super().__init__(text, parent)
        self._danger = danger
        self.setFixedSize(44, 40)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setStyleSheet(
            f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {TEXT_SEC};
                border-radius: 0;
                font-size: 15px;
                padding: 0;
                font-family: 'Segoe UI Symbol';
            }}
            QPushButton:hover {{
                background: {'#b91c1c' if danger else BG_HOVER};
                color: {TEXT};
            }}
            """
        )


class TitleBar(QWidget):
    def __init__(self, parent: QMainWindow):
        super().__init__(parent)
        self._window = parent
        self._drag_pos: QPoint | None = None
        self.setFixedHeight(52)
        self.setObjectName("titleBar")
        self.setStyleSheet(f"QWidget#titleBar {{ background: {BG_BASE}; border: none; }}")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(LogoWidget(20))

        title = QLabel("UPSCAL")
        title.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 800; background: transparent;")
        title.setContentsMargins(9, 0, 0, 1)
        layout.addWidget(title)

        sep = QFrame()
        sep.setFixedSize(1, 16)
        sep.setStyleSheet(f"background: {BG_SURFACE};")
        layout.addSpacing(14)
        layout.addWidget(sep)
        layout.addSpacing(14)

        file_icon = QLabel("□")
        file_icon.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 13px; background: transparent;")
        layout.addWidget(file_icon)

        self.file_label = QLabel("이미지를 추가하세요")
        self.file_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px; font-weight: 600; background: transparent;")
        self.file_label.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(self.file_label)

        self.size_label = QLabel("")
        self.size_label.setStyleSheet(f"color: {TEXT_FAINT}; font-size: 11px; font-family: {MONO}; background: transparent;")
        self.size_label.setContentsMargins(8, 0, 0, 0)
        layout.addWidget(self.size_label)

        layout.addStretch(1)

        self.gpu_label = QLabel("GPU 감지 중")
        self.gpu_label.setStyleSheet(
            f"color: {WARNING}; background: {BG_ELEVATED}; border: none; border-radius: 9px;"
            "padding: 3px 8px; font-size: 11px;"
        )
        layout.addWidget(self.gpu_label)
        layout.addSpacing(10)

        self.status_pill = QLabel("")
        self.status_pill.setVisible(False)
        self.status_pill.setStyleSheet(
            f"color: {TEXT}; background: rgba(99, 102, 241, 0.16); border: none;"
            "border-radius: 11px; padding: 4px 10px; font-size: 11px; font-weight: 700;"
        )
        layout.addWidget(self.status_pill)
        layout.addSpacing(8)

        min_btn = ChromeButton("─", self)
        min_btn.clicked.connect(parent.showMinimized)
        layout.addWidget(min_btn)

        self.max_btn = ChromeButton("□", self)
        self.max_btn.clicked.connect(self._toggle_maximized)
        layout.addWidget(self.max_btn)

        close_btn = ChromeButton("×", self, danger=True)
        close_btn.clicked.connect(parent.close)
        layout.addWidget(close_btn)

    def set_file(self, item: QueueItem | None, scale: int):
        if not item:
            self.file_label.setText("이미지를 추가하세요")
            self.size_label.setText("")
            return
        self.file_label.setText(item.name)
        src = image_size_text(item.source)
        out = image_size_text(item.result) if item.result else output_size_text(item.source, scale)
        self.size_label.setText(f"{src} -> {out}")

    def set_status(self, text: str = "", progress: int | None = None):
        self.status_pill.setVisible(False)

    def set_gpu(self, text: str, ok: bool):
        self.gpu_label.setText(text)
        color = SUCCESS if ok else WARNING
        self.gpu_label.setStyleSheet(
            f"color: {color}; background: {BG_ELEVATED}; border: none; border-radius: 9px;"
            "padding: 3px 8px; font-size: 11px;"
        )

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self._window.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton and not self._window.isMaximized():
            self._window.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_maximized()

    def _toggle_maximized(self):
        if self._window.isMaximized():
            self._window.showNormal()
            self.max_btn.setText("□")
        else:
            self._window.showMaximized()
            self.max_btn.setText("❐")


class SegmentedControl(QWidget):
    value_changed = pyqtSignal(object)

    def __init__(self, options: list[tuple[str, object]], default=None, parent=None, accent: bool = False):
        super().__init__(parent)
        self._buttons: list[QPushButton] = []
        self._values: dict[QPushButton, object] = {}
        self._value = default if default is not None else (options[0][1] if options else None)
        self._accent = accent

        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)
        self.setMinimumHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(f"background: {BG_INPUT}; border: none; border-radius: 7px;")

        for label, value in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
            btn.setFixedHeight(30)
            btn.setMinimumWidth(0)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            self.group.addButton(btn)
            self._buttons.append(btn)
            self._values[btn] = value
            layout.addWidget(btn, 1)
            btn.clicked.connect(lambda checked, b=btn: self._set_from_button(b))

        self.set_value(self._value)

    @property
    def value(self):
        return self._value

    def set_value(self, value):
        self._value = value
        for btn in self._buttons:
            btn.setChecked(self._values[btn] == value)
        self._sync_styles()

    def _set_from_button(self, btn: QPushButton):
        self._value = self._values[btn]
        self._sync_styles()
        self.value_changed.emit(self._value)

    def _sync_styles(self):
        for btn in self._buttons:
            checked = btn.isChecked()
            bg = ACCENT if checked and self._accent else BG_ELEVATED if checked else "transparent"
            color = "#ffffff" if checked and self._accent else TEXT if checked else TEXT_SEC
            weight = "800" if checked else "600"
            btn.setStyleSheet(
                f"""
                QPushButton {{
                    background: {bg};
                    color: {color};
                    border: none;
                    border-radius: 5px;
                    padding: 0;
                    font-family: {MONO}, '{FONT}';
                    font-size: 11px;
                    font-weight: {weight};
                }}
                QPushButton:hover {{
                    background: {ACCENT if checked and self._accent else BG_HOVER};
                }}
                """
            )


class ProgressButton(QAbstractButton):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        self._progress = 0
        self._processing = False
        self.setText(text)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setFixedHeight(50)

    def set_processing(self, processing: bool, progress: int = 0):
        self._processing = processing
        self._progress = max(0, min(100, progress))
        self.setEnabled(not processing)
        self.update()

    def set_progress(self, progress: int):
        self._progress = max(0, min(100, progress))
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)

        is_save = "저장" in self.text()
        if self.isEnabled():
            bg = qc(SUCCESS if is_save else ACCENT)
            text_color = qc("#ffffff")
            border = qc(SUCCESS if is_save else ACCENT)
        else:
            bg = qc(BG_ELEVATED)
            text_color = qc(TEXT)
            border = qc(BG_ELEVATED)

        painter.setBrush(bg)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 9, 9)

        if self._processing:
            overlay = QRectF(rect.left(), rect.top(), rect.width() * self._progress / 100, rect.height())
            grad = QLinearGradient(overlay.topLeft(), overlay.topRight())
            grad.setColorAt(0, qc(ACCENT, 125))
            grad.setColorAt(1, qc(ACCENT_BRIGHT, 60))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(grad)
            painter.drawRoundedRect(overlay, 9, 9)

        painter.setPen(text_color)
        font = QFont(FONT, 11)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text())


class WorkflowCanvas(QWidget):
    STEPS = [
        ("input", "이미지 입력"),
        ("analyze", "사전 분석"),
        ("denoise", "노이즈 제거"),
        ("restore", "디테일 복원"),
        ("upscale", "업스케일링"),
        ("color", "색상 보정"),
        ("export", "결과 출력"),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(620)
        self._states = {step_id: NodeState.IDLE for step_id, _ in self.STEPS}
        self._progress = 0
        self._tick = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._animate)
        self._timer.start(33)

    def _animate(self):
        self._tick += 1
        if NodeState.ACTIVE in self._states.values():
            self.update()

    def reset(self):
        self._states = {step_id: NodeState.IDLE for step_id, _ in self.STEPS}
        self._progress = 0
        self.update()

    def set_loaded(self):
        self.reset()
        self._states["input"] = NodeState.DONE
        self._states["analyze"] = NodeState.DONE
        self.update()

    def set_running(self, frac: float):
        self._progress = int(frac * 100)
        for step_id, _ in self.STEPS:
            self._states[step_id] = NodeState.IDLE

        self._states["input"] = NodeState.DONE
        self._states["analyze"] = NodeState.DONE

        if frac < 0.12:
            self._states["denoise"] = NodeState.ACTIVE
        elif frac < 0.92:
            self._states["denoise"] = NodeState.DONE
            self._states["restore"] = NodeState.ACTIVE
        elif frac < 0.97:
            self._states["denoise"] = NodeState.DONE
            self._states["restore"] = NodeState.DONE
            self._states["upscale"] = NodeState.ACTIVE
        else:
            self._states["denoise"] = NodeState.DONE
            self._states["restore"] = NodeState.DONE
            self._states["upscale"] = NodeState.DONE
            self._states["color"] = NodeState.DONE
            self._states["export"] = NodeState.ACTIVE
        self.update()

    def set_done(self):
        for step_id, _ in self.STEPS:
            self._states[step_id] = NodeState.DONE
        self._progress = 100
        self.update()

    def set_error(self):
        active = None
        for step_id, state in self._states.items():
            if state == NodeState.ACTIVE:
                active = step_id
                break
        self._states[active or "upscale"] = NodeState.ERROR
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), qc(BG_CANVAS))

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qc(BORDER_STRONG, 118))
        for x in range(12, self.width(), 28):
            for y in range(12, self.height(), 28):
                painter.drawEllipse(QPointF(x, y), 1.2, 1.2)

        side = 18
        node = 108
        inner = max(210, self.width() - side * 2)
        col_l = 0
        col_r = inner - node
        step_y = min(92, max(78, (self.height() - node - 12) // max(1, len(self.STEPS) - 1)))
        total_h = step_y * (len(self.STEPS) - 1) + node
        top = max(8, (self.height() - total_h) // 2)

        positions: list[tuple[float, float]] = []
        for idx in range(len(self.STEPS)):
            x = col_l if idx % 2 == 0 else col_r
            y = top + idx * step_y
            positions.append((side + x, y))

        for idx in range(len(self.STEPS) - 1):
            self._draw_connector(painter, positions[idx], positions[idx + 1], node, idx)

        for idx, (step_id, label) in enumerate(self.STEPS):
            x, y = positions[idx]
            self._draw_node(painter, QRectF(x, y, node, node), step_id, label, self._states[step_id])

    def _draw_connector(self, painter: QPainter, a: tuple[float, float], b: tuple[float, float], node: int, idx: int):
        state_a = self._states[self.STEPS[idx][0]]
        state_b = self._states[self.STEPS[idx + 1][0]]
        if state_a == NodeState.ERROR or state_b == NodeState.ERROR:
            color = ERROR
        elif state_b == NodeState.ACTIVE:
            color = ACCENT
        elif state_a == NodeState.DONE and state_b == NodeState.DONE:
            color = SUCCESS
        else:
            color = BORDER

        going_right = b[0] > a[0]
        x1 = a[0] + node if going_right else a[0]
        y1 = a[1] + node / 2
        x2 = b[0] if going_right else b[0] + node
        y2 = b[1] + node / 2
        dy = (y2 - y1) * 0.55

        path = QPainterPath(QPointF(x1, y1))
        path.cubicTo(QPointF(x1, y1 + dy), QPointF(x2, y2 - dy), QPointF(x2, y2))

        painter.setPen(QPen(qc(color, 170 if color == BORDER else 230), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        flowing = state_b == NodeState.ACTIVE or (state_a == NodeState.DONE and state_b == NodeState.DONE)
        if flowing:
            painter.setPen(QPen(qc(ACCENT_BRIGHT if state_b == NodeState.ACTIVE else SUCCESS, 210), 2.5, Qt.PenStyle.DashLine, Qt.PenCapStyle.RoundCap))
            painter.drawPath(path)
            for i in range(3):
                t = (self._tick * 0.018 + i / 3.0) % 1.0
                pt = path.pointAtPercent(t)
                alpha = int(80 + 175 * math.sin(t * math.pi))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(qc(ACCENT_BRIGHT if state_b == NodeState.ACTIVE else SUCCESS, alpha))
                painter.drawEllipse(pt, 3.5, 3.5)

    def _draw_node(self, painter: QPainter, rect: QRectF, step_id: str, label: str, state: str):
        active = state == NodeState.ACTIVE
        done = state == NodeState.DONE
        error = state == NodeState.ERROR

        border = ACCENT_BRIGHT if active else SUCCESS if done else ERROR if error else BORDER_STRONG
        bg = "#1b1a3a" if active else "#07372f" if done else "#2a151d" if error else BG_SURFACE
        wash = qc(bg)
        if active:
            pulse = 0.5 + 0.5 * math.sin(self._tick * 0.12)
            glow = qc(ACCENT, int(80 * pulse))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(glow)
            painter.drawRoundedRect(rect.adjusted(-8, -8, 8, 8), 18, 18)

        painter.setPen(QPen(qc(border, 235 if state != NodeState.IDLE else 110), 1.7))
        painter.setBrush(wash)
        painter.drawRoundedRect(rect, 11, 11)

        icon_color = ACCENT_BRIGHT if active else SUCCESS if done else ERROR if error else TEXT_SEC
        self._draw_step_icon(painter, step_id, QRectF(rect.left() + 22, rect.top() + 20, rect.width() - 44, 42), icon_color, active)

        if done:
            badge = QRectF(rect.right() - 25, rect.top() + 13, 16, 16)
            painter.setBrush(qc(SUCCESS))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(badge)
            painter.setPen(QPen(qc("#ffffff"), 1.8))
            painter.drawLine(QPointF(badge.left() + 4, badge.center().y()), QPointF(badge.left() + 7, badge.bottom() - 4))
            painter.drawLine(QPointF(badge.left() + 7, badge.bottom() - 4), QPointF(badge.right() - 4, badge.top() + 4))
        elif active:
            pulse = 0.45 + 0.55 * math.sin(self._tick * 0.16)
            painter.setBrush(qc(ACCENT_BRIGHT, int(145 + 95 * pulse)))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(rect.right() - 30, rect.top() + 19), 3.3, 3.3)
            run_font = QFont(MONO, 6)
            run_font.setBold(True)
            painter.setFont(run_font)
            painter.setPen(qc(ACCENT_BRIGHT))
            painter.drawText(QRectF(rect.right() - 25, rect.top() + 12, 22, 14).toRect(), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, "RUN")
        elif error:
            badge = QRectF(rect.right() - 25, rect.top() + 13, 16, 16)
            painter.setBrush(qc(ERROR))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(badge)
            painter.setPen(QPen(qc("#ffffff"), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            painter.drawLine(QPointF(badge.left() + 5, badge.top() + 5), QPointF(badge.right() - 5, badge.bottom() - 5))
            painter.drawLine(QPointF(badge.right() - 5, badge.top() + 5), QPointF(badge.left() + 5, badge.bottom() - 5))
        else:
            idle_font = QFont(MONO, 6)
            idle_font.setBold(True)
            painter.setFont(idle_font)
            painter.setPen(qc(TEXT_FAINT))
            painter.drawText(QRectF(rect.right() - 31, rect.top() + 11, 25, 14).toRect(), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, "IDLE")

        label_font = QFont(FONT, 10)
        label_font.setBold(True)
        painter.setFont(label_font)
        painter.setPen(qc(TEXT if state != NodeState.IDLE else TEXT_SEC))
        painter.drawText(QRectF(rect.left() + 8, rect.top() + 71, rect.width() - 16, 24).toRect(), Qt.AlignmentFlag.AlignCenter, label)

        if active:
            bar = QRectF(rect.left() + 16, rect.bottom() - 11, rect.width() - 32, 3)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qc(BG_INPUT))
            painter.drawRoundedRect(bar, 2, 2)
            fill = QRectF(bar.left(), bar.top(), bar.width() * max(0.08, self._progress / 100.0), bar.height())
            painter.setBrush(qc(ACCENT_BRIGHT))
            painter.drawRoundedRect(fill, 2, 2)

    def _draw_step_icon(self, painter: QPainter, step_id: str, rect: QRectF, color: str, active: bool = False):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        line_width = 2.7
        painter.setBrush(Qt.BrushStyle.NoBrush)

        cx = rect.center().x()
        cy = rect.center().y()
        phase = self._tick * 0.12 if active else 0.0

        def set_pen(alpha: int = 255, width: float = line_width):
            painter.setPen(QPen(qc(color, alpha), width, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))

        set_pen()
        if step_id == "input":
            dy = math.sin(phase) * 2.4 if active else 0.0
            painter.drawLine(QPointF(cx, cy - 17 + dy), QPointF(cx, cy + 7 + dy))
            painter.drawLine(QPointF(cx - 9, cy - 2 + dy), QPointF(cx, cy + 8 + dy))
            painter.drawLine(QPointF(cx + 9, cy - 2 + dy), QPointF(cx, cy + 8 + dy))
            painter.drawLine(QPointF(cx - 16, cy + 18), QPointF(cx + 16, cy + 18))
        elif step_id == "analyze":
            painter.drawEllipse(QPointF(cx - 4, cy - 5), 10.5, 10.5)
            painter.drawLine(QPointF(cx + 4, cy + 4), QPointF(cx + 17, cy + 17))
            if active:
                scan_y = cy - 13 + (math.sin(phase) + 1.0) * 8
                set_pen(190, 2.0)
                painter.drawLine(QPointF(cx - 13, scan_y), QPointF(cx + 5, scan_y))
                set_pen()
        elif step_id == "denoise":
            angle_offset = self._tick * 0.06 if active else 0.0
            for i in range(10):
                a = math.pi * 2 * i / 10 + angle_offset
                alpha = 110 + int(120 * ((i + (self._tick if active else 0)) % 10) / 9)
                set_pen(alpha, 2.4)
                painter.drawLine(
                    QPointF(cx + math.cos(a) * 8, cy + math.sin(a) * 8),
                    QPointF(cx + math.cos(a) * 17, cy + math.sin(a) * 17),
                )
        elif step_id == "upscale":
            travel = (math.sin(phase) + 1.0) * 2.0 if active else 2.0
            painter.drawLine(QPointF(cx - 14, cy - 14), QPointF(cx + 12 + travel, cy + 12 + travel))
            painter.drawLine(QPointF(cx + 12 + travel, cy + 12 + travel), QPointF(cx + 2 + travel, cy + 12 + travel))
            painter.drawLine(QPointF(cx + 12 + travel, cy + 12 + travel), QPointF(cx + 12 + travel, cy + 2 + travel))
            painter.drawLine(QPointF(cx - 15, cy - 5), QPointF(cx - 15, cy - 15))
            painter.drawLine(QPointF(cx - 15, cy - 15), QPointF(cx - 5, cy - 15))
        elif step_id == "restore":
            size = 11.0
            gap = 5.0
            start_x = cx - size - gap / 2
            start_y = cy - size - gap / 2
            for idx, (col, row) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
                pulse = 0.0
                if active:
                    pulse = (math.sin(phase + idx * 0.9) + 1.0) * 1.1
                box = QRectF(start_x + col * (size + gap) - pulse / 2, start_y + row * (size + gap) - pulse / 2, size + pulse, size + pulse)
                painter.drawRoundedRect(box, 1.6, 1.6)
        elif step_id == "color":
            pts = [
                QPointF(cx - 10, cy - 7),
                QPointF(cx + 10, cy - 7),
                QPointF(cx, cy + 10),
            ]
            set_pen(150, 2.0)
            painter.drawLine(pts[0], pts[1])
            painter.drawLine(pts[1], pts[2])
            painter.drawLine(pts[2], pts[0])
            set_pen()
            for idx, pt in enumerate(pts):
                wobble = math.sin(phase + idx * 1.8) * 1.3 if active else 0.0
                painter.drawEllipse(QPointF(pt.x(), pt.y() + wobble), 5.6, 5.6)
        elif step_id == "export":
            dy = -math.sin(phase) * 2.4 if active else 0.0
            painter.drawLine(QPointF(cx, cy + 17 + dy), QPointF(cx, cy - 8 + dy))
            painter.drawLine(QPointF(cx - 9, cy + 1 + dy), QPointF(cx, cy - 9 + dy))
            painter.drawLine(QPointF(cx + 9, cy + 1 + dy), QPointF(cx, cy - 9 + dy))
            painter.drawLine(QPointF(cx - 16, cy - 18), QPointF(cx + 16, cy - 18))

        painter.restore()


class WorkflowPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(280)
        self.setStyleSheet(f"background: {BG_CANVAS}; border: none;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedHeight(62)
        h = QHBoxLayout(header)
        h.setContentsMargins(18, 12, 18, 8)
        left = QVBoxLayout()
        left.setSpacing(1)
        title = QLabel("처리 흐름")
        title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 900; background: transparent;")
        left.addWidget(title)
        h.addLayout(left)
        h.addStretch()
        self.counter = QLabel("0 / 7")
        self.counter.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.counter.setStyleSheet(
            f"color: {TEXT}; background: {BG_ELEVATED}; border: none; border-radius: 10px;"
            f"font-family: {MONO}; font-size: 11px; padding: 3px 9px;"
        )
        h.addWidget(self.counter)
        layout.addWidget(header)

        self.canvas = WorkflowCanvas()
        layout.addWidget(self.canvas, 1)

        footer = QWidget()
        footer.setFixedHeight(46)
        footer.setStyleSheet(f"background: {BG_SURFACE}; border: none;")
        f = QHBoxLayout(footer)
        f.setContentsMargins(18, 0, 18, 0)
        self.footer_label = QLabel("대기 중")
        self.footer_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-family: {MONO}; background: transparent;")
        f.addWidget(self.footer_label)
        f.addStretch()
        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet(f"color: {ACCENT_BRIGHT}; font-size: 11px; font-family: {MONO}; background: transparent;")
        f.addWidget(self.eta_label)
        layout.addWidget(footer)

    def reset(self):
        self.canvas.reset()
        self.set_counter(0)
        self.footer_label.setText("대기 중")
        self.eta_label.setText("")

    def set_counter(self, done_count: int):
        self.counter.setText(f"{done_count} / 7")

    def set_loaded(self):
        self.canvas.set_loaded()
        self.set_counter(2)
        self.footer_label.setText("이미지 준비 완료")

    def set_running(self, frac: float, msg: str):
        self.canvas.set_running(frac)
        current = 3
        if frac >= 0.12:
            current = 4
        if frac >= 0.92:
            current = 5
        if frac >= 0.97:
            current = 7
        self.set_counter(current)
        self.footer_label.setText(f"{int(frac * 100):02d}%")
        self.eta_label.setText(msg[:18])

    def set_done(self):
        self.canvas.set_done()
        self.set_counter(7)
        self.footer_label.setText("완료")
        self.eta_label.setText("100%")

    def set_error(self):
        self.canvas.set_error()
        self.footer_label.setText("오류")
        self.eta_label.setText("")


class PreviewComparison(QWidget):
    files_dropped = pyqtSignal(list)
    browse_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._before: Image.Image | None = None
        self._after: Image.Image | None = None
        self._before_pix: QPixmap | None = None
        self._after_pix: QPixmap | None = None
        self._checker_tile: QPixmap | None = None
        self._split = 0.5
        self._dragging = False
        self._panning = False
        self._last_pan_pos = QPointF()
        self._zoom = 1.0
        self._pan = QPointF(0, 0)

    def set_images(self, before: Image.Image | None, after: Image.Image | None = None):
        if before is self._before and after is self._after:
            return

        source_changed = before is not self._before
        self._before = before
        self._after = after
        self._before_pix = pil_to_pixmap(before) if before else None
        self._after_pix = pil_to_pixmap(after) if after else None
        if source_changed:
            self._zoom = 1.0
            self._pan = QPointF(0, 0)
            self._split = 0.5
        elif after is not None:
            self._split = 0.5
        self.update()

    def resizeEvent(self, event):
        self._constrain_pan()
        super().resizeEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._before is None:
                self.browse_requested.emit()
                return
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._panning = True
                self._last_pan_pos = event.position()
                self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))
                return
            if self._after is not None:
                self._dragging = True
                self._set_split(event.position().x())
        elif event.button() in (Qt.MouseButton.RightButton, Qt.MouseButton.MiddleButton) and self._before is not None:
            self._panning = True
            self._last_pan_pos = event.position()
            self.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def mouseMoveEvent(self, event: QMouseEvent):
        if self._panning:
            delta = event.position() - self._last_pan_pos
            self._last_pan_pos = event.position()
            self._pan += delta
            self._constrain_pan()
            self.update()
        elif self._dragging:
            self._set_split(event.position().x())

    def mouseReleaseEvent(self, event: QMouseEvent):
        self._dragging = False
        self._panning = False
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        if self._before is not None:
            self._zoom = 1.0
            self._pan = QPointF(0, 0)
            self.update()

    def wheelEvent(self, event):
        if self._before is None:
            return
        old_zoom = self._zoom
        factor = 1.18 if event.angleDelta().y() > 0 else 1 / 1.18
        self._zoom = max(1.0, min(6.0, self._zoom * factor))
        if abs(self._zoom - old_zoom) < 1e-3:
            return

        base = self._base_image_rect(self._after or self._before)
        cursor = event.position()
        center = QPointF(base.center()) + self._pan
        rel = cursor - center
        if old_zoom > 0:
            self._pan -= rel * (self._zoom / old_zoom - 1.0)
        self._constrain_pan()
        self.update()

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(p.lower().endswith(IMAGE_EXTS) for p in paths):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent):
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.toLocalFile().lower().endswith(IMAGE_EXTS)]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def _set_split(self, x: float):
        if self._before is None:
            return
        rect = self._image_rect(self._after or self._before)
        if rect.width() <= 0:
            return
        clamped = max(rect.left(), min(rect.right(), x))
        self._split = max(0.0, min(1.0, (clamped - rect.left()) / rect.width()))
        self.update()

    def _base_image_rect(self, img: Image.Image) -> QRect:
        margin = 22
        avail_w = max(1, self.width() - margin * 2)
        avail_h = max(1, self.height() - margin * 2)
        aspect = img.width / max(1, img.height)
        if avail_w / avail_h > aspect:
            h = avail_h
            w = int(h * aspect)
        else:
            w = avail_w
            h = int(w / aspect)
        return QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def _image_rect(self, img: Image.Image) -> QRect:
        base = self._base_image_rect(img)
        w = max(1, int(base.width() * self._zoom))
        h = max(1, int(base.height() * self._zoom))
        center = QPointF(base.center()) + self._pan
        return QRect(int(center.x() - w / 2), int(center.y() - h / 2), w, h)

    def _constrain_pan(self):
        if self._before is None:
            return
        base = self._base_image_rect(self._after or self._before)
        view_w = base.width() * self._zoom
        view_h = base.height() * self._zoom
        max_x = max(0.0, (view_w - base.width()) / 2)
        max_y = max(0.0, (view_h - base.height()) / 2)
        self._pan.setX(max(-max_x, min(max_x, self._pan.x())))
        self._pan.setY(max(-max_y, min(max_y, self._pan.y())))

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, self._zoom < 2.5)
        painter.fillRect(self.rect(), qc(BG_CANVAS))
        self._draw_checker(painter, self.rect())

        if self._before is None:
            self._draw_empty(painter)
            return

        display_img = self._after or self._before
        rect = self._image_rect(display_img)

        clip = QPainterPath()
        clip.addRoundedRect(QRectF(rect), 8, 8)
        painter.setClipPath(clip)

        if self._after is None:
            if self._before_pix:
                painter.drawPixmap(QRectF(rect), self._before_pix, QRectF(self._before_pix.rect()))
        else:
            split_x = int(rect.left() + self._split * rect.width())
            if self._after_pix:
                painter.drawPixmap(QRectF(rect), self._after_pix, QRectF(self._after_pix.rect()))
            if self._before_pix:
                painter.setClipRect(QRect(rect.left(), rect.top(), split_x - rect.left(), rect.height()))
                painter.drawPixmap(QRectF(rect), self._before_pix, QRectF(self._before_pix.rect()))
                painter.setClipping(False)
                painter.setClipPath(clip)

        painter.setClipping(False)

        if self._after is not None:
            split_x = int(rect.left() + self._split * rect.width())
            painter.setPen(QPen(qc("#ffffff"), 2))
            painter.drawLine(split_x, rect.top(), split_x, rect.bottom())
            painter.setBrush(qc("#ffffff"))
            painter.setPen(QPen(qc(BG_INPUT), 2))
            painter.drawEllipse(QPointF(split_x, rect.center().y()), 15, 15)
            painter.setPen(qc(BG_INPUT))
            handle_font = QFont(MONO, 8)
            handle_font.setBold(True)
            painter.setFont(handle_font)
            painter.drawText(QRect(split_x - 15, rect.center().y() - 8, 30, 16), Qt.AlignmentFlag.AlignCenter, "<>")

        self._draw_badge(painter, rect.left() + 12, rect.top() + 12, "BEFORE", BG_INPUT)
        if self._after is not None:
            self._draw_badge(painter, rect.right() - 82, rect.top() + 12, "AFTER", ACCENT)
        else:
            self._draw_badge(painter, rect.right() - 82, rect.top() + 12, "SOURCE", ACCENT_DIM)

        zoom_text = f"{int(self._zoom * 100)}%"
        self._draw_badge(painter, rect.right() - 82, rect.bottom() - 34, zoom_text, BG_ELEVATED)

    def _draw_checker(self, painter: QPainter, rect: QRect):
        size = 8
        if self._checker_tile is None:
            self._checker_tile = QPixmap(size * 2, size * 2)
            self._checker_tile.fill(qc(BG_INPUT))
            tile_painter = QPainter(self._checker_tile)
            tile_painter.fillRect(QRect(size, 0, size, size), qc("#0d0d13"))
            tile_painter.fillRect(QRect(0, size, size, size), qc("#0d0d13"))
            tile_painter.end()
        painter.drawTiledPixmap(rect, self._checker_tile)

    def _draw_empty(self, painter: QPainter):
        box = QRectF(self.width() / 2 - 185, self.height() / 2 - 64, 370, 128)
        painter.setBrush(qc(BG_SURFACE, 235))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(box, 10, 10)

        title_font = QFont(FONT, 13)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(qc(TEXT))
        painter.drawText(box.adjusted(20, 26, -20, -64).toRect(), Qt.AlignmentFlag.AlignCenter, "이미지를 드래그하거나 클릭해서 추가")

        sub_font = QFont(MONO, 9)
        painter.setFont(sub_font)
        painter.setPen(qc(TEXT_MUTED))
        painter.drawText(box.adjusted(20, 68, -20, -22).toRect(), Qt.AlignmentFlag.AlignCenter, "PNG · JPG · WEBP · BMP · TIFF")

    def _draw_badge(self, painter: QPainter, x: int, y: int, text: str, bg: str):
        rect = QRectF(x, y, 70, 22)
        painter.setBrush(qc(bg, 230))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 4, 4)
        font = QFont(MONO, 8)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(qc("#ffffff"))
        painter.drawText(rect.toRect(), Qt.AlignmentFlag.AlignCenter, text)


class QueueThumb(QAbstractButton):
    TILE = 96

    def __init__(self, item: QueueItem | None, active: bool = False, add_tile: bool = False, parent=None):
        super().__init__(parent)
        self.item = item
        self.active = active
        self.add_tile = add_tile
        self._thumb: QPixmap | None = None
        self.setFixedSize(self.TILE, self.TILE)
        self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        if item:
            self.setToolTip(item.name)
            self._thumb = pil_to_pixmap(item.source)
        elif add_tile:
            self.setToolTip("이미지 추가")

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(1, 1, self.width() - 2, self.height() - 2)

        if self.add_tile:
            painter.setBrush(qc(BG_SURFACE))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 10, 10)
            painter.setPen(qc(TEXT_SEC))
            plus_font = QFont(FONT, 20)
            plus_font.setBold(True)
            painter.setFont(plus_font)
            painter.drawText(self.rect().adjusted(0, -10, 0, 0), Qt.AlignmentFlag.AlignCenter, "+")
            painter.setFont(QFont(FONT, 8))
            painter.setPen(qc(TEXT_MUTED))
            painter.drawText(self.rect().adjusted(0, 30, 0, 0), Qt.AlignmentFlag.AlignCenter, "추가")
            return

        if not self.item:
            return

        state = self.item.state
        ring = ACCENT if state == "active" else SUCCESS if state == "done" else ERROR if state == "error" else BG_SURFACE
        painter.setBrush(qc(BG_SURFACE))
        painter.setPen(QPen(qc(ring), 2) if state == "active" else Qt.PenStyle.NoPen)
        painter.drawRoundedRect(rect, 10, 10)

        clip = QPainterPath()
        clip.addRoundedRect(rect.adjusted(1, 1, -1, -1), 9, 9)
        painter.setClipPath(clip)
        if self._thumb and not self._thumb.isNull():
            scaled = self._thumb.scaled(QSize(self.TILE, self.TILE), Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
            sx = max(0, (scaled.width() - self.TILE) // 2)
            sy = max(0, (scaled.height() - self.TILE) // 2)
            painter.drawPixmap(QRect(0, 0, self.TILE, self.TILE), scaled, QRect(sx, sy, self.TILE, self.TILE))

        if state != "active":
            overlay = qc("#000000", 108 if state == "pending" else 72)
            if state == "error":
                overlay = qc(ERROR, 70)
            elif state == "done":
                overlay = qc(SUCCESS, 45)
            painter.fillRect(self.rect(), overlay)

        painter.setClipping(False)

        if self.active:
            painter.setPen(QPen(qc(ACCENT_BRIGHT), 2.4))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 8, 8)

        dot_color = ACCENT if state == "active" else SUCCESS if state == "done" else ERROR if state == "error" else TEXT_FAINT
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(qc(dot_color))
        painter.drawEllipse(QPointF(13, 13), 4.2, 4.2)

        if state == "active":
            pct_rect = QRectF(self.width() - 52, 6, 46, 24)
            painter.setBrush(qc(BG_INPUT, 190))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(pct_rect, 5, 5)
            painter.setPen(qc("#ffffff"))
            font = QFont(MONO, 11)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(pct_rect.toRect(), Qt.AlignmentFlag.AlignCenter, f"{self.item.progress}%")
            painter.fillRect(QRectF(0, self.height() - 6, self.width() * self.item.progress / 100, 6), qc(ACCENT))
        elif state == "done":
            self._draw_center_mark(painter, SUCCESS, "✓")
        elif state == "error":
            self._draw_center_mark(painter, ERROR, "×")
        elif state == "pending":
            painter.setPen(qc(TEXT_SEC))
            font = QFont(MONO, 8)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "READY")

    def _draw_center_mark(self, painter: QPainter, color: str, mark: str):
        painter.setBrush(qc(color))
        painter.setPen(Qt.PenStyle.NoPen)
        center = QPointF(self.width() / 2, self.height() / 2)
        painter.drawEllipse(center, 17, 17)
        painter.setPen(qc("#ffffff"))
        font = QFont("Segoe UI Symbol", 15)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRect(int(center.x()) - 17, int(center.y()) - 17, 34, 34), Qt.AlignmentFlag.AlignCenter, mark)


class QueueIcon(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(14, 14)

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(qc(TEXT), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for idx, y in enumerate((3.5, 7.0, 10.5)):
            painter.drawLine(QPointF(5.2, y), QPointF(12.2, y))
            painter.setBrush(qc(ACCENT if idx == 0 else SUCCESS if idx == 1 else ERROR))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(2.2, y), 1.5, 1.5)
            painter.setPen(QPen(qc(TEXT), 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))


class QueueStats(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._counts = {"active": 0, "done": 0, "error": 0, "pending": 0}
        self.setFixedHeight(22)
        self.setMinimumWidth(116)

    def set_counts(self, counts: dict[str, int]):
        self._counts = counts.copy()
        self.update()

    def paintEvent(self, event: QPaintEvent):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(MONO, 9)
        font.setBold(True)
        painter.setFont(font)
        entries = [
            ("active", ACCENT),
            ("done", SUCCESS),
            ("error", ERROR),
            ("pending", TEXT_FAINT),
        ]
        x = 0
        y = self.height() / 2
        for key, color in entries:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(qc(color))
            painter.drawEllipse(QPointF(x + 4, y), 3.2, 3.2)
            painter.setPen(qc(TEXT_SEC if key != "pending" else TEXT_MUTED))
            text = str(self._counts.get(key, 0))
            painter.drawText(QRectF(x + 12, 0, 18, self.height()).toRect(), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
            x += 28


class QueueStrip(QWidget):
    add_requested = pyqtSignal()
    selected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(132)
        self.setStyleSheet(f"background: {BG_BASE}; border: none;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setFixedWidth(168)
        header.setStyleSheet(f"border: none; background: {BG_BASE};")
        h = QVBoxLayout(header)
        h.setContentsMargins(22, 14, 18, 14)
        h.addStretch()
        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(7)
        title_row.addWidget(QueueIcon())
        title = QLabel("작업 큐")
        title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 900; background: transparent;")
        title_row.addWidget(title)
        self.count_label = QLabel("0")
        self.count_label.setStyleSheet(f"color: {TEXT_MUTED}; font-family: {MONO}; font-size: 10px; font-weight: 700; background: transparent;")
        title_row.addWidget(self.count_label)
        title_row.addStretch()
        h.addLayout(title_row)
        self.stats = QueueStats()
        h.addWidget(self.stats)
        h.addStretch()
        layout.addWidget(header)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setStyleSheet(f"QScrollArea {{ background: {BG_BASE}; border: none; }}")
        self.content = QWidget()
        self.content.setStyleSheet(f"background: {BG_BASE};")
        self.row = QHBoxLayout(self.content)
        self.row.setContentsMargins(18, 18, 18, 18)
        self.row.setSpacing(12)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)

    def update_items(self, items: list[QueueItem], active_id: int | None):
        while self.row.count():
            item = self.row.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        counts = {"active": 0, "done": 0, "error": 0, "pending": 0}
        for item in items:
            counts[item.state] = counts.get(item.state, 0) + 1
            thumb = QueueThumb(item, active=item.item_id == active_id)
            thumb.clicked.connect(lambda checked=False, iid=item.item_id: self.selected.emit(iid))
            self.row.addWidget(thumb)

        add = QueueThumb(None, add_tile=True)
        add.clicked.connect(self.add_requested.emit)
        self.row.addWidget(add)
        self.row.addStretch(1)

        self.count_label.setText(f"{len(items)}개")
        self.stats.set_counts(counts)


class InfoRow(QWidget):
    def __init__(self, key: str, value: str = "-", parent=None, accent: bool = False):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 4)
        layout.setSpacing(3)
        self.k = QLabel(key)
        self.k.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; font-weight: 700; background: transparent;")
        self.v = QLabel(value)
        self.v.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.v.setWordWrap(True)
        self.v.setStyleSheet(
            f"color: {ACCENT_BRIGHT if accent else TEXT}; font-size: 15px; font-family: {MONO}; font-weight: 900; background: transparent;"
        )
        layout.addWidget(self.k)
        layout.addWidget(self.v)

    def set_value(self, value: str):
        self.v.setText(value)


class RightDock(QWidget):
    start_requested = pyqtSignal()
    save_requested = pyqtSignal()
    autosave_requested = pyqtSignal()
    batch_save_requested = pyqtSignal()
    reset_requested = pyqtSignal()
    settings_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedWidth(304)
        self.setStyleSheet(f"background: {BG_SURFACE}; border: none;")
        self._loading_settings = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        settings = QWidget()
        s = QVBoxLayout(settings)
        s.setContentsMargins(18, 18, 18, 16)
        s.setSpacing(11)
        title = QLabel("출력 설정")
        title.setStyleSheet(f"color: {TEXT}; font-size: 14px; font-weight: 900; background: transparent;")
        s.addWidget(title)

        self.model = self._control_row(s, "모델", [("사진", "general"), ("그림", "anime")], "general")
        self.scale = self._control_row(s, "배율", [("2x", 2), ("4x", 4), ("8x", 8)], 4, accent=True)
        self.dpi = self._control_row(s, "DPI", [("72", 72), ("150", 150), ("300", 300)], 300)
        self.fmt = self._control_row(s, "포맷", [("JPG", "JPG"), ("PNG", "PNG"), ("TIFF", "TIFF"), ("WEBP", "WEBP")], "JPG")
        self.tile = self._control_row(s, "타일", [("256", 256), ("512", 512), ("1024", 1024)], 512)

        detail_row = QHBoxLayout()
        detail_row.setContentsMargins(0, 0, 0, 0)
        detail_label = QLabel("디테일")
        detail_label.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; background: transparent;")
        self.detail_value = QLabel("65%")
        self.detail_value.setStyleSheet(f"color: {ACCENT_BRIGHT}; font-size: 11px; font-family: {MONO}; font-weight: 700; background: transparent;")
        detail_row.addWidget(detail_label)
        detail_row.addStretch()
        detail_row.addWidget(self.detail_value)
        s.addLayout(detail_row)

        self.detail = QSlider(Qt.Orientation.Horizontal)
        self.detail.setRange(0, 100)
        self.detail.setValue(65)
        self.detail.valueChanged.connect(self._on_detail_changed)
        s.addWidget(self.detail)

        layout.addWidget(settings)
        self._separator(layout)

        info = QWidget()
        i = QVBoxLayout(info)
        i.setContentsMargins(16, 16, 16, 14)
        i.setSpacing(9)
        ititle = QLabel("선택 이미지")
        ititle.setStyleSheet(f"color: {TEXT}; font-size: 13px; font-weight: 900; background: transparent;")
        i.addWidget(ititle)

        thumb_row = QHBoxLayout()
        thumb_row.setSpacing(10)
        self.thumb = QLabel()
        self.thumb.setFixedSize(56, 56)
        self.thumb.setStyleSheet(f"background: {BG_INPUT}; border: none; border-radius: 7px;")
        self.name_label = QLabel("없음")
        self.name_label.setWordWrap(False)
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.name_label.setStyleSheet(f"color: {TEXT}; font-size: 12px; font-weight: 700; background: transparent;")
        self.size_label = QLabel("-")
        self.size_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-family: {MONO}; background: transparent;")
        name_col = QVBoxLayout()
        name_col.setSpacing(3)
        name_col.addStretch()
        name_col.addWidget(self.name_label)
        name_col.addWidget(self.size_label)
        name_col.addStretch()
        thumb_row.addWidget(self.thumb)
        thumb_row.addLayout(name_col, 1)
        i.addLayout(thumb_row)

        self.original_row = InfoRow("원본", "-")
        self.result_row = InfoRow("결과", "-", accent=True)
        self.model_row = InfoRow("AI 모델", "ESRGAN x4")
        i.addWidget(self.original_row)
        i.addWidget(self.result_row)
        i.addWidget(self.model_row)
        layout.addWidget(info)
        layout.addStretch(1)

        self._separator(layout)

        actions = QWidget()
        a = QVBoxLayout(actions)
        a.setContentsMargins(14, 14, 14, 14)
        a.setSpacing(9)

        self.progress_panel = QFrame()
        self.progress_panel.setStyleSheet(
            f"QFrame {{ background: {BG_INPUT}; border: none; border-radius: 9px; }}"
        )
        p = QVBoxLayout(self.progress_panel)
        p.setContentsMargins(13, 10, 13, 10)
        p.setSpacing(4)
        progress_head = QHBoxLayout()
        progress_head.setContentsMargins(0, 0, 0, 0)
        progress_head.setSpacing(8)
        self.progress_stage = QLabel("예상 소요")
        self.progress_stage.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.progress_stage.setStyleSheet(f"color: {TEXT_SEC}; font-size: 12px; font-weight: 800; background: transparent;")
        self.progress_percent = QLabel("-")
        self.progress_percent.setStyleSheet(f"color: {ACCENT_BRIGHT}; font-size: 34px; font-family: {MONO}; font-weight: 900; background: transparent;")
        self.progress_eta = QLabel("")
        self.progress_eta.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-family: {MONO}; font-weight: 700; background: transparent;")
        progress_head.addWidget(self.progress_percent, 1)
        progress_head.addWidget(self.progress_stage)
        p.addLayout(progress_head)
        p.addWidget(self.progress_eta)
        self.progress_panel.setVisible(False)
        a.addWidget(self.progress_panel)

        self.autosave_label = QLabel("자동 저장 꺼짐")
        self.autosave_label.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px; font-family: {MONO}; font-weight: 700; background: transparent;")
        a.addWidget(self.autosave_label)

        save_tools = QHBoxLayout()
        save_tools.setSpacing(8)
        self.autosave_btn = QPushButton("저장 폴더")
        self.autosave_btn.setFixedHeight(34)
        self.autosave_btn.clicked.connect(self.autosave_requested.emit)
        self.batch_save_btn = QPushButton("일괄 저장")
        self.batch_save_btn.setFixedHeight(34)
        self.batch_save_btn.clicked.connect(self.batch_save_requested.emit)
        save_tools.addWidget(self.autosave_btn)
        save_tools.addWidget(self.batch_save_btn)
        a.addLayout(save_tools)

        self.start_btn = ProgressButton("업스케일 시작")
        self.start_btn.clicked.connect(self.start_requested.emit)
        a.addWidget(self.start_btn)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.save_btn = QPushButton("저장")
        self.save_btn.setFixedHeight(34)
        self.save_btn.clicked.connect(self.save_requested.emit)
        self.save_btn.setVisible(False)
        self.reset_btn = QPushButton("초기화")
        self.reset_btn.setFixedHeight(34)
        self.reset_btn.clicked.connect(self.reset_requested.emit)
        row.addWidget(self.save_btn)
        row.addWidget(self.reset_btn)
        a.addLayout(row)
        layout.addWidget(actions)

        for ctrl in (self.model, self.scale, self.dpi, self.fmt, self.tile):
            ctrl.value_changed.connect(self.settings_changed.emit)

    def _separator(self, layout: QVBoxLayout):
        sep = QFrame()
        sep.setFixedHeight(0)
        sep.setStyleSheet("background: transparent;")
        layout.addWidget(sep)

    def _on_detail_changed(self, value: int):
        self.detail_value.setText(f"{value}%")
        if not self._loading_settings:
            self.settings_changed.emit()

    def get_settings(self) -> OutputSettings:
        return OutputSettings(
            model_type=self.model.value,
            scale=self.scale.value,
            dpi=self.dpi.value,
            fmt=self.fmt.value,
            tile=self.tile.value,
            detail=self.detail.value(),
        )

    def set_settings(self, settings: OutputSettings):
        self._loading_settings = True
        try:
            for control, value in (
                (self.model, settings.model_type),
                (self.scale, settings.scale),
                (self.dpi, settings.dpi),
                (self.fmt, settings.fmt),
                (self.tile, settings.tile),
            ):
                control.set_value(value)
                if hasattr(control, "display_value"):
                    control.display_value.setText(str(value).replace("general", "사진").replace("anime", "그림"))
            self.detail.blockSignals(True)
            self.detail.setValue(settings.detail)
            self.detail.blockSignals(False)
            self.detail_value.setText(f"{settings.detail}%")
        finally:
            self._loading_settings = False

    def set_output_controls_enabled(self, enabled: bool):
        for widget in (self.model, self.scale, self.dpi, self.fmt, self.tile, self.detail):
            widget.setEnabled(enabled)

    def set_auto_save_folder(self, folder: str | None):
        if folder:
            shown = elided(folder, self.autosave_label.font(), 238)
            self.autosave_label.setText(f"자동 저장: {shown}")
        else:
            self.autosave_label.setText("자동 저장 꺼짐")

    def set_batch_enabled(self, enabled: bool):
        self.batch_save_btn.setEnabled(enabled)

    def _control_row(self, parent: QVBoxLayout, label: str, options: list[tuple[str, object]], default, accent: bool = False) -> SegmentedControl:
        wrap = QWidget()
        l = QVBoxLayout(wrap)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(6)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        text = QLabel(label)
        text.setStyleSheet(f"color: {TEXT_SEC}; font-size: 11px; background: transparent;")
        display_default = str(default).replace("general", "사진").replace("anime", "그림")
        value = QLabel(display_default)
        value.setMinimumWidth(60)
        value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        value.setStyleSheet(f"color: {ACCENT_BRIGHT if accent else TEXT_MUTED}; font-size: 11px; font-family: {MONO}; font-weight: 700; background: transparent;")
        top.addWidget(text)
        top.addStretch()
        top.addWidget(value)
        l.addLayout(top)
        control = SegmentedControl(options, default=default, accent=accent)
        control.display_value = value
        control.value_changed.connect(lambda v, label=value: label.setText(str(v).replace("general", "사진").replace("anime", "그림")))
        l.addWidget(control)
        parent.addWidget(wrap)
        return control

    def update_info(self, item: QueueItem | None, gpu: str):
        if not item:
            self.name_label.setText("없음")
            self.size_label.setText("-")
            self.thumb.clear()
            self.original_row.set_value("-")
            self.result_row.set_value("-")
            settings = self.get_settings()
            self.model_row.set_value(f"{'그림' if settings.model_type == 'anime' else '사진'} x{settings.scale}")
            return

        settings = item.settings
        self.name_label.setText(elided(item.name, self.name_label.font(), 154))
        self.size_label.setText(image_size_text(item.source))
        thumb = pil_to_pixmap(item.source).scaled(56, 56, Qt.AspectRatioMode.KeepAspectRatioByExpanding, Qt.TransformationMode.SmoothTransformation)
        self.thumb.setPixmap(thumb)
        self.original_row.set_value(image_size_text(item.source))
        self.result_row.set_value(image_size_text(item.result) if item.result else output_size_text(item.source, settings.scale))
        self.model_row.set_value(f"{'그림' if settings.model_type == 'anime' else '사진'} x{settings.scale}")

    def set_progress_info(self, visible: bool, stage: str = "", percent: int | None = None, eta: str = ""):
        self.progress_panel.setVisible(visible)
        if not visible:
            return
        self.progress_stage.setText(stage)
        self.progress_percent.setText("-" if percent is None else f"{percent}%")
        self.progress_eta.setText(eta)
        self.progress_eta.setVisible(bool(eta))


class MainWindow(QMainWindow):
    _gpu_detected = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("UPSCAL")
        icon_path = resource_path("Icon.png")
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self.setMinimumSize(1100, 720)
        self.resize(1280, 820)

        self._items: list[QueueItem] = []
        self._active_id: int | None = None
        self._next_id = 1
        self._worker: UpscaleWorker | None = None
        self._running_item_id: int | None = None
        self._gpu_info = "감지 중"
        self._start_time: float | None = None
        self._estimated_total = 0.0
        self._last_real_frac = 0.0
        self._queue_active = False
        self._queue_errors: list[str] = []
        self._auto_save_dir: str | None = None
        self._loading_item_settings = False
        self._update_check_worker: UpdateCheckWorker | None = None
        self._update_download_worker: UpdateDownloadWorker | None = None
        self._update_progress_dialog: QProgressDialog | None = None

        self._gpu_detected.connect(self._on_gpu_detected)
        self._build_ui()

        self._progress_timer = QTimer(self)
        self._progress_timer.timeout.connect(self._tick_estimated_progress)

        threading.Thread(target=self._detect_gpu_thread, daemon=True).start()
        QTimer.singleShot(1500, self._check_for_updates_on_startup)

    def nativeEvent(self, event_type, message):
        if sys.platform != "win32":
            return super().nativeEvent(event_type, message)

        try:
            msg = wintypes.MSG.from_address(int(message))
        except Exception:
            return False, 0

        if msg.message != WM_NCHITTEST:
            return False, 0

        lp = int(msg.lParam)
        x = ctypes.c_short(lp & 0xFFFF).value
        y = ctypes.c_short((lp >> 16) & 0xFFFF).value
        pos = self.mapFromGlobal(QPoint(x, y))
        if not self.rect().contains(pos):
            return False, 0

        if not self.isMaximized():
            left = pos.x() <= RESIZE_MARGIN
            right = pos.x() >= self.width() - RESIZE_MARGIN
            top = pos.y() <= RESIZE_MARGIN
            bottom = pos.y() >= self.height() - RESIZE_MARGIN

            if top and left:
                return True, HTTOPLEFT
            if top and right:
                return True, HTTOPRIGHT
            if bottom and left:
                return True, HTBOTTOMLEFT
            if bottom and right:
                return True, HTBOTTOMRIGHT
            if left:
                return True, HTLEFT
            if right:
                return True, HTRIGHT
            if top:
                return True, HTTOP
            if bottom:
                return True, HTBOTTOM

        if pos.y() <= self.title_bar.height() + 6:
            child = self.childAt(pos)
            if isinstance(child, ChromeButton):
                return True, HTCLIENT
            return True, HTCAPTION

        return False, 0

    def _build_ui(self):
        root = QWidget()
        root.setStyleSheet(f"background: {BG_BASE};")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.title_bar = TitleBar(self)
        layout.addWidget(self.title_bar)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        layout.addWidget(body, 1)

        self.workflow = WorkflowPanel()
        body_layout.addWidget(self.workflow)

        center = QWidget()
        center.setStyleSheet(f"background: {BG_CANVAS};")
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(0)
        body_layout.addWidget(center, 1)

        preview_wrap = QWidget()
        preview_layout = QVBoxLayout(preview_wrap)
        preview_layout.setContentsMargins(22, 16, 22, 22)
        preview_layout.setSpacing(14)

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        self.preview_title = QLabel("업스케일링")
        self.preview_title.setStyleSheet(f"color: {TEXT}; font-size: 16px; font-weight: 900; background: transparent;")
        self.preview_meta = QLabel("UPSCALE · RESOLUTION")
        self.preview_meta.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px; font-family: {MONO}; background: transparent;")
        top.addWidget(self.preview_title)
        top.addSpacing(10)
        top.addWidget(self.preview_meta)
        top.addStretch(1)
        self.view_mode = QLabel("B / A 슬라이드")
        self.view_mode.setStyleSheet(
            f"color: {TEXT}; background: {BG_ELEVATED}; border: none; border-radius: 7px;"
            f"padding: 5px 12px; font-size: 11px; font-weight: 700;"
        )
        top.addWidget(self.view_mode)
        preview_layout.addLayout(top)

        self.preview = PreviewComparison()
        self.preview.files_dropped.connect(self._add_files)
        self.preview.browse_requested.connect(self._browse_files)
        preview_layout.addWidget(self.preview, 1)
        center_layout.addWidget(preview_wrap, 1)

        self.queue = QueueStrip()
        self.queue.add_requested.connect(self._browse_files)
        self.queue.selected.connect(self._select_item)
        center_layout.addWidget(self.queue)

        self.right = RightDock()
        self.right.start_requested.connect(self._on_start)
        self.right.save_requested.connect(self._on_save)
        self.right.autosave_requested.connect(self._choose_auto_save_folder)
        self.right.batch_save_requested.connect(self._on_batch_save)
        self.right.reset_requested.connect(self._on_reset)
        self.right.settings_changed.connect(self._on_settings_changed)
        body_layout.addWidget(self.right)

        self.size_grip = QSizeGrip(root)
        self.size_grip.setFixedSize(18, 18)
        self.size_grip.setStyleSheet("background: transparent;")
        self.size_grip.raise_()

        self._update_ui()

    def _detect_gpu_thread(self):
        try:
            import torch

            force_cpu = os.environ.get("UPSCAL_FORCE_CPU", "").strip().lower() in {"1", "true", "yes", "on"}
            if not force_cpu and torch.cuda.is_available():
                name = torch.cuda.get_device_name(0)
                vram = torch.cuda.get_device_properties(0).total_memory / 1024**3
                self._gpu_detected.emit(f"{name} · {vram:.1f} GB")
            elif (
                not force_cpu
                and getattr(getattr(torch, "backends", None), "mps", None)
                and torch.backends.mps.is_available()
            ):
                self._gpu_detected.emit("Apple Metal (MPS)")
            else:
                self._gpu_detected.emit(None)
        except Exception:
            self._gpu_detected.emit(None)

    def _on_gpu_detected(self, info):
        if info:
            self._gpu_info = info
            self.title_bar.set_gpu(f"GPU {info}", True)
        else:
            self._gpu_info = "CPU 모드"
            self.title_bar.set_gpu("CPU 모드", False)
        self._update_ui()

    def _tr(self, ko: str, en: str) -> str:
        return ko if is_korean_locale() else en

    def _check_for_updates_on_startup(self):
        manifest_url = update_manifest_url()
        if not manifest_url:
            return
        if self._update_check_worker and self._update_check_worker.isRunning():
            return

        worker = UpdateCheckWorker(manifest_url, APP_VERSION)
        self._update_check_worker = worker
        worker.update_available.connect(self._show_update_available)
        worker.error.connect(lambda _message: None)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "_update_check_worker", None))
        worker.start()

    def _show_update_available(self, info: UpdateInfo):
        notes = info.notes_ko if is_korean_locale() else info.notes_en
        if not notes:
            notes = info.notes_ko or info.notes_en

        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle(self._tr("UPSCAL 업데이트", "UPSCAL Update"))
        box.setText(
            self._tr(
                f"새 버전 {info.version}이 있습니다.\n현재 버전: {APP_VERSION}",
                f"Version {info.version} is available.\nCurrent version: {APP_VERSION}",
            )
        )
        detail = self._tr(
            "다운로드 후 설치 마법사를 실행할까요?",
            "Download it and start the installer?",
        )
        if notes:
            detail += f"\n\n{notes}"
        box.setInformativeText(detail)
        install_btn = box.addButton(
            self._tr("다운로드 및 설치", "Download and Install"),
            QMessageBox.ButtonRole.AcceptRole,
        )
        box.addButton(self._tr("나중에", "Later"), QMessageBox.ButtonRole.RejectRole)
        box.exec()

        if box.clickedButton() is install_btn:
            self._download_update(info)

    def _download_update(self, info: UpdateInfo):
        if self._update_download_worker and self._update_download_worker.isRunning():
            return

        dialog = QProgressDialog(
            self._tr("업데이트 다운로드 중...", "Downloading update..."),
            self._tr("취소", "Cancel"),
            0,
            100,
            self,
        )
        dialog.setWindowTitle(self._tr("UPSCAL 업데이트", "UPSCAL Update"))
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.setValue(0)
        self._update_progress_dialog = dialog

        worker = UpdateDownloadWorker(info)
        self._update_download_worker = worker
        dialog.canceled.connect(worker.cancel)
        worker.progress.connect(dialog.setValue)
        worker.downloaded.connect(self._on_update_downloaded)
        worker.error.connect(self._on_update_download_error)
        worker.finished.connect(worker.deleteLater)
        worker.finished.connect(lambda: setattr(self, "_update_download_worker", None))
        worker.start()

    def _on_update_downloaded(self, installer_path: str):
        if self._update_progress_dialog:
            self._update_progress_dialog.setValue(100)
            self._update_progress_dialog.close()
            self._update_progress_dialog = None

        try:
            open_update_installer(installer_path)
        except Exception as exc:
            QMessageBox.critical(
                self,
                self._tr("업데이트 오류", "Update Error"),
                self._tr(
                    f"설치 마법사를 실행할 수 없습니다:\n{exc}",
                    f"Could not start the installer:\n{exc}",
                ),
            )
            return

        self.title_bar.set_status(self._tr("업데이트 설치 시작", "Starting update installer"))
        QTimer.singleShot(500, QApplication.instance().quit)

    def _on_update_download_error(self, message: str):
        if self._update_progress_dialog:
            self._update_progress_dialog.close()
            self._update_progress_dialog = None
        QMessageBox.warning(
            self,
            self._tr("업데이트 오류", "Update Error"),
            self._tr(
                f"업데이트를 다운로드할 수 없습니다:\n{message}",
                f"Could not download the update:\n{message}",
            ),
        )

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "이미지 추가", "", IMAGE_FILTER)
        if paths:
            self._add_files(paths)

    def _add_files(self, paths: list[str]):
        added = []
        for path in paths:
            if not path.lower().endswith(IMAGE_EXTS):
                continue
            try:
                image = Image.open(path).convert("RGB")
                item = QueueItem(self._next_id, path, image, settings=self.right.get_settings())
                self._next_id += 1
                self._items.append(item)
                added.append(item)
            except Exception as exc:
                QMessageBox.warning(self, "이미지 오류", f"이미지를 열 수 없습니다:\n{path}\n\n{exc}")

        if added:
            self._active_id = added[0].item_id
            self.workflow.set_loaded()
            self.title_bar.set_status("준비 완료")
            self._update_ui()

    def _select_item(self, item_id: int):
        self._active_id = item_id
        self._sync_workflow_to_item()
        self._update_ui()

    def _active_item(self) -> QueueItem | None:
        for item in self._items:
            if item.item_id == self._active_id:
                return item
        return None

    def _on_settings_changed(self):
        if self._loading_item_settings:
            return
        item = self._active_item()
        if item:
            if item.state == "active" and item.item_id == self._running_item_id:
                return
            new_settings = self.right.get_settings()
            if item.settings != new_settings:
                item.settings = new_settings
                if item.result is not None or item.state in ("done", "error"):
                    item.result = None
                    item.state = "pending"
                    item.progress = 0
                    item.error = ""
                self._sync_workflow_to_item()
        self._update_ui()

    def _on_start(self):
        if self._worker and self._worker.isRunning():
            return

        item = self._active_item()
        pending = self._pending_items()
        if item and item.result is not None:
            if pending:
                item = pending[0]
            else:
                self._on_save()
                return
        elif item is None:
            item = pending[0] if pending else None

        if item is None:
            return

        remaining_count = len(pending)
        if item.state == "error" and item.result is None:
            remaining_count += 1
        self._queue_active = remaining_count > 1
        self._queue_errors = []
        self._start_processing_item(item, select=True)

    def _pending_items(self) -> list[QueueItem]:
        return [item for item in self._items if item.result is None and item.state == "pending"]

    def _next_pending_item(self) -> QueueItem | None:
        pending = self._pending_items()
        return pending[0] if pending else None

    def _start_processing_item(self, item: QueueItem, select: bool = True):
        if item is None or (self._worker and self._worker.isRunning()):
            return

        settings = item.settings
        if select:
            self._active_id = item.item_id
        item.state = "active"
        item.progress = 0
        item.error = ""
        item.result = None
        self._running_item_id = item.item_id
        self._start_time = time.perf_counter()
        self._last_real_frac = 0.0
        self._estimated_total = estimate_duration_seconds(item, settings.scale, settings.tile, self._gpu_info)

        self.workflow.set_running(0.01, "시작")
        self._set_preview_stage(0.01)
        self.title_bar.set_status("", None)
        self.right.set_progress_info(True, "처리 중", 0, f"남은 {format_duration(self._estimated_total)}")
        self.right.start_btn.setText("처리 중 · 0%")
        self.right.start_btn.set_processing(True, 0)
        self._update_ui()
        self._progress_timer.start(500)

        self._worker = UpscaleWorker(
            pil_image=item.source,
            model_type=settings.model_type,
            target_scale=settings.scale,
            output_dpi=settings.dpi,
            tile_size=settings.tile,
            detail_strength=settings.detail / 100.0,
        )
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, frac: float, msg: str):
        item = self._item_by_id(self._running_item_id)
        pct = max(0, min(100, int(frac * 100)))
        self._last_real_frac = max(self._last_real_frac, frac)
        eta = self._eta_text(frac)
        if item:
            item.progress = pct
            item.state = "active"

        self.workflow.set_running(frac, msg)
        self._set_preview_stage(frac)
        self.title_bar.set_status("", None)
        self.right.set_progress_info(True, msg or "처리 중", pct, eta)
        self.right.start_btn.setText(f"처리 중 · {pct}%")
        self.right.start_btn.set_progress(pct)
        self._update_ui()

    def _eta_text(self, frac: float | None = None) -> str:
        if self._start_time is None:
            return ""
        elapsed = max(0.0, time.perf_counter() - self._start_time)
        if frac and frac > 0.05:
            total = elapsed / max(0.01, min(frac, 0.98))
        else:
            total = self._estimated_total
        remain = max(0.0, total - elapsed)
        return f"남은 {format_duration(remain)}"

    def _set_preview_stage(self, frac: float):
        if frac >= 0.98:
            self.preview_title.setText("결과 출력")
            self.preview_meta.setText("EXPORT · SAVE")
        elif frac >= 0.92:
            self.preview_title.setText("디테일 복원")
            self.preview_meta.setText("RESTORE · EDGE · TEXTURE")
        else:
            self.preview_title.setText("업스케일링")
            self.preview_meta.setText("UPSCALE · RESOLUTION")

    def _tick_estimated_progress(self):
        if not (self._worker and self._worker.isRunning()) or self._start_time is None:
            self._progress_timer.stop()
            return
        item = self._item_by_id(self._running_item_id)
        if item is None:
            return

        elapsed = max(0.0, time.perf_counter() - self._start_time)
        estimate_frac = elapsed / max(1.0, self._estimated_total)
        cap = 0.88 if self._last_real_frac < 0.90 else 0.97
        display_frac = max(self._last_real_frac, min(cap, estimate_frac))
        pct = max(item.progress, min(98, int(display_frac * 100)))
        item.progress = pct
        item.state = "active"

        self.workflow.set_running(display_frac, "처리 중")
        self._set_preview_stage(display_frac)
        self.right.set_progress_info(True, "처리 중", pct, self._eta_text(display_frac))
        self.right.start_btn.setText(f"처리 중 · {pct}%")
        self.right.start_btn.set_progress(pct)
        self.queue.update_items(self._items, self._active_id)

    def _on_finished(self, result: Image.Image):
        self._progress_timer.stop()
        item = self._item_by_id(self._running_item_id)
        selected_running_item = bool(item and self._active_id == item.item_id)
        if item:
            item.result = result
            item.state = "done"
            item.progress = 100
            if self._auto_save_dir:
                try:
                    self._save_item_to_folder(item, self._auto_save_dir)
                except Exception as exc:
                    item.error = f"자동 저장 실패: {exc}"

        finished_worker = self._worker
        self._worker = None
        if finished_worker:
            finished_worker.deleteLater()
        self._running_item_id = None

        next_item = self._next_pending_item() if self._queue_active else None
        if next_item:
            self.workflow.set_done()
            self._set_preview_stage(1.0)
            self.right.set_progress_info(True, "다음 작업 준비", 100, "")
            self.right.start_btn.setText("다음 이미지 준비 중")
            self._update_ui()
            QTimer.singleShot(180, lambda item_id=next_item.item_id, select=selected_running_item: self._start_next_queued_item(item_id, select))
            return

        self._queue_active = False
        self.workflow.set_done()
        self._set_preview_stage(1.0)
        self.title_bar.set_status("", None)
        self.right.set_progress_info(True, "완료됨", 100, "")
        self.right.start_btn.setText("저장하기")
        self.right.start_btn.set_processing(False)
        self._update_ui()

    def _on_error(self, tb: str):
        self._progress_timer.stop()
        item = self._item_by_id(self._running_item_id)
        selected_running_item = bool(item and self._active_id == item.item_id)
        if item:
            item.state = "error"
            item.error = tb
            self._queue_errors.append(item.name)

        failed_worker = self._worker
        self._worker = None
        if failed_worker:
            failed_worker.deleteLater()
        self._running_item_id = None

        next_item = self._next_pending_item() if self._queue_active else None
        if next_item:
            self.workflow.set_error()
            self.right.set_progress_info(True, "다음 작업 준비", None, "")
            self._update_ui()
            QTimer.singleShot(180, lambda item_id=next_item.item_id, select=selected_running_item: self._start_next_queued_item(item_id, select))
            return

        self._queue_active = False
        self.workflow.set_error()
        self.title_bar.set_status("", None)
        self.right.set_progress_info(True, "오류", None, "오류 내용을 확인하세요")
        self.right.start_btn.setText("업스케일 시작")
        self.right.start_btn.set_processing(False)
        self._update_ui()
        self._show_error_dialog(tb)

    def _start_next_queued_item(self, item_id: int, select: bool = True):
        item = self._item_by_id(item_id)
        if item and item.result is None and item.state == "pending":
            self._start_processing_item(item, select=select)

    def _on_save(self):
        item = self._active_item()
        if not item or item.result is None:
            return

        ext = self._extension_for_item(item)
        default_name = f"{Path(item.path).stem}_upscaled{ext}"
        filters = "PNG (*.png);;JPEG (*.jpg *.jpeg);;TIFF (*.tif *.tiff);;WEBP (*.webp)"
        path, _ = QFileDialog.getSaveFileName(self, "결과 저장", default_name, filters)
        if not path:
            return

        if not os.path.splitext(path)[1]:
            path += ext

        try:
            self._save_item_to_path(item, path)
            self.title_bar.set_status("저장 완료")
            QMessageBox.information(self, "저장 완료", f"파일이 저장되었습니다:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "저장 오류", f"저장 중 오류가 발생했습니다:\n{exc}")

    def _choose_auto_save_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "자동 저장 폴더 선택", self._auto_save_dir or "")
        if not folder:
            return
        self._auto_save_dir = folder
        self.right.set_auto_save_folder(folder)

    def _on_batch_save(self):
        done_items = [item for item in self._items if item.result is not None]
        if not done_items:
            QMessageBox.information(self, "일괄 저장", "저장할 완료 이미지가 없습니다.")
            return

        folder = self._auto_save_dir or QFileDialog.getExistingDirectory(self, "일괄 저장 폴더 선택", "")
        if not folder:
            return
        self._auto_save_dir = folder
        self.right.set_auto_save_folder(folder)

        saved = 0
        failed: list[str] = []
        for item in done_items:
            try:
                self._save_item_to_folder(item, folder)
                saved += 1
            except Exception as exc:
                failed.append(f"{item.name}: {exc}")

        self.title_bar.set_status(f"{saved}개 저장 완료")
        if failed:
            QMessageBox.warning(self, "일괄 저장", f"{saved}개 저장 완료\n\n실패:\n" + "\n".join(failed[:6]))
        else:
            QMessageBox.information(self, "일괄 저장", f"{saved}개 이미지가 저장되었습니다:\n{folder}")

    def _extension_for_item(self, item: QueueItem) -> str:
        return {"PNG": ".png", "JPG": ".jpg", "TIFF": ".tiff", "WEBP": ".webp"}[item.settings.fmt]

    def _save_item_to_folder(self, item: QueueItem, folder: str) -> str:
        folder_path = Path(folder)
        folder_path.mkdir(parents=True, exist_ok=True)
        ext = self._extension_for_item(item)
        stem = f"{Path(item.path).stem}_upscaled"
        path = folder_path / f"{stem}{ext}"
        index = 2
        while path.exists():
            path = folder_path / f"{stem}_{index}{ext}"
            index += 1
        self._save_item_to_path(item, str(path))
        return str(path)

    def _save_item_to_path(self, item: QueueItem, path: str):
        if item.result is None:
            raise ValueError("저장할 결과 이미지가 없습니다.")

        settings = item.settings
        dpi = (settings.dpi, settings.dpi)
        image = item.result
        lower = path.lower()
        if lower.endswith((".jpg", ".jpeg")):
            image.convert("RGB").save(path, "JPEG", quality=92, subsampling=0, optimize=True, progressive=True, dpi=dpi)
        elif lower.endswith((".tif", ".tiff")):
            image.save(path, "TIFF", dpi=dpi)
        elif lower.endswith(".webp"):
            image.convert("RGB").save(path, "WEBP", quality=92, method=4)
        else:
            image.save(path, "PNG", optimize=True, compress_level=6, dpi=dpi)

    def _on_reset(self):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "처리 중", "현재 처리 중인 작업이 끝난 뒤 초기화할 수 있습니다.")
            return
        self._items.clear()
        self._active_id = None
        self._running_item_id = None
        self._start_time = None
        self._last_real_frac = 0.0
        self._estimated_total = 0.0
        self._queue_active = False
        self._queue_errors = []
        self._progress_timer.stop()
        self.workflow.reset()
        self.title_bar.set_status("")
        self._update_ui()

    def _item_by_id(self, item_id: int | None) -> QueueItem | None:
        if item_id is None:
            return None
        for item in self._items:
            if item.item_id == item_id:
                return item
        return None

    def _sync_workflow_to_item(self):
        item = self._active_item()
        if not item:
            self.workflow.reset()
        elif item.state == "active":
            self.workflow.set_running(max(0.01, item.progress / 100.0), "처리 중")
        elif item.state == "done":
            self.workflow.set_done()
        elif item.state == "error":
            self.workflow.set_loaded()
            self.workflow.set_error()
        else:
            self.workflow.set_loaded()

    def _update_ui(self):
        item = self._active_item()
        running = bool(self._worker and self._worker.isRunning())
        if item:
            self._loading_item_settings = True
            try:
                self.right.set_settings(item.settings)
            finally:
                self._loading_item_settings = False
        scale = item.settings.scale if item else self.right.get_settings().scale
        self.title_bar.set_file(item, scale)
        self.queue.update_items(self._items, self._active_id)
        self.right.update_info(item, self._gpu_info)

        if item:
            self.preview.set_images(item.source, item.result)
        else:
            self.preview.set_images(None, None)

        pending_count = len(self._pending_items())
        self.right.start_btn.setEnabled((item is not None or pending_count > 0) and not running)
        selected_running = bool(running and item and item.item_id == self._running_item_id)
        self.right.set_output_controls_enabled(not selected_running)
        if not running:
            self.right.start_btn.set_processing(False)
            if item and item.result is not None:
                if pending_count:
                    self.right.start_btn.setText(f"남은 {pending_count}개 시작")
                    self.right.set_progress_info(True, "대기 중", None, f"남은 작업 {pending_count}개")
                else:
                    self.right.start_btn.setText("저장하기")
                    self.right.set_progress_info(True, "완료됨", 100, "")
            elif item:
                eta = estimate_duration_seconds(item, item.settings.scale, item.settings.tile, self._gpu_info)
                if item.state == "error":
                    self.right.start_btn.setText("다시 시작")
                else:
                    self.right.start_btn.setText("전체 업스케일 시작" if pending_count > 1 else "업스케일 시작")
                self.right.set_progress_info(True, "예상 소요", None, format_duration(eta))
            else:
                self.right.start_btn.setText("업스케일 시작")
                self.right.set_progress_info(False)
        self.right.save_btn.setEnabled(False)
        self.right.reset_btn.setEnabled(bool(self._items) and not running)
        self.right.set_batch_enabled(any(item.result is not None for item in self._items))
        self.right.set_auto_save_folder(self._auto_save_dir)

    def _show_error_dialog(self, tb: str):
        dlg = QDialog(self)
        dlg.setWindowTitle("오류")
        dlg.resize(680, 420)
        dlg.setStyleSheet(f"background: {BG_SURFACE}; color: {TEXT};")

        layout = QVBoxLayout(dlg)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("처리 중 오류가 발생했습니다. 아래 내용을 복사해서 공유해주세요.")
        title.setWordWrap(True)
        title.setStyleSheet(f"color: {ERROR}; font-size: 13px; font-weight: 800; background: transparent;")
        layout.addWidget(title)

        text = QTextEdit()
        text.setPlainText(tb)
        text.setReadOnly(True)
        text.setStyleSheet(
            f"""
            QTextEdit {{
                background: {BG_INPUT};
                color: {TEXT_SEC};
                border: 1px solid {BORDER};
                border-radius: 7px;
                font-family: {MONO};
                font-size: 11px;
                padding: 8px;
            }}
            """
        )
        layout.addWidget(text)

        buttons = QHBoxLayout()
        buttons.addStretch()
        copy_btn = QPushButton("전체 복사")
        copy_btn.clicked.connect(lambda: (QApplication.clipboard().setText(tb), copy_btn.setText("복사됨")))
        close_btn = QPushButton("닫기")
        close_btn.clicked.connect(dlg.accept)
        buttons.addWidget(copy_btn)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        dlg.exec()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        super().closeEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "size_grip"):
            self.size_grip.move(self.width() - 20, self.height() - 20)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLE)
    app.setFont(QFont(FONT, 10))
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
