import sys
import os
import json
import subprocess
import webbrowser
from ctypes import windll, Structure, c_ulong, sizeof, byref, c_void_p

from PyQt6.QtCore import Qt, QTimer, QSize, QUrl, QPoint
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QDialog, QGridLayout, QLabel, QScrollArea, QFrame,
    QStyle, QGraphicsDropShadowEffect
)
from PyQt6.QtGui import QIcon, QColor, QPixmap, QPainter, QDesktopServices

# --- COSTANTI & STRUTTURE WINDOWS APPBAR ---
ABM_NEW = 0x00000000
ABM_REMOVE = 0x00000001
ABM_SETPOS = 0x00000003
ABE_LEFT = 0
ABE_RIGHT = 2

class RECT(Structure):
    _fields_ = [
        ('left', c_ulong), ('top', c_ulong),
        ('right', c_ulong), ('bottom', c_ulong)
    ]

class APPBARDATA(Structure):
    _fields_ = [
        ('cbSize', c_ulong), ('hWnd', c_void_p),
        ('uCallbackMessage', c_ulong), ('uEdge', c_ulong),
        ('rc', RECT), ('lParam', c_ulong)
    ]

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "dock_config.json")

# --- POPUP SELEZIONE ICONE PERSONALIZZATE ---
class IconPickerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Scegli un'icona")
        self.setFixedSize(320, 420)
        self.selected_icon_color = None

        layout = QGridLayout(self)
        colors = [
            "#e74c3c", "#e67e22", "#f1c40f", "#2ecc71", "#1abc9c", "#3498db", "#9b59b6", "#34495e",
            "#c0392b", "#d35400", "#f39c12", "#27ae60", "#16a085", "#2980b9", "#8e44ad", "#2c3e50",
            "#ff7675", "#fdcb6e", "#ffeaa7", "#55efc4", "#81ecec", "#74b9ff", "#a29bfe", "#6c5ce7",
            "#d63031", "#e17055", "#fd79a8", "#00b894", "#00cec9", "#0984e3", "#6c5ce7", "#b2bec3",
            "#fffa65", "#32ff7e", "#7d5fff", "#718093", "#ff3838", "#ff9f1a", "#18dcff", "#c56cf0",
            "#ffb8b8", "#ffccd5", "#c7ecee", "#dff9fb", "#f3a683", "#f8a5c2", "#78e08f", "#6a89cc"
        ]

        row, col = 0, 0
        for color in colors:
            btn = QPushButton()
            btn.setFixedSize(38, 38)
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(color))
            btn.setIcon(QIcon(pixmap))
            btn.setIconSize(QSize(32, 32))
            btn.clicked.connect(lambda _, c=color: self.select_color(c))
            layout.addWidget(btn, row, col)
            col += 1
            if col >= 6:
                col = 0
                row += 1

    def select_color(self, color):
        self.selected_icon_color = color
        self.accept()

# --- FINESTRA PRINCIPALE DOCK ---
class DockWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.dock_side = self.config.get("side", ABE_RIGHT)
        self.folder_path = self.config.get("path", "")
        self.custom_icons = self.config.get("custom_icons", {})
        self.is_dragging = False
        self.drag_start_x = 0

        self.init_ui()
        self.setup_system_bar()

        if not self.folder_path or not os.path.exists(self.folder_path):
            QTimer.singleShot(100, self.prompt_folder_path)
        else:
            self.load_items()

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self):
        self.config["side"] = self.dock_side
        self.config["path"] = self.folder_path
        self.config["custom_icons"] = self.custom_icons
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        # Colore barra Windows 11 (scuro/semitrasparente di default)
        self.setStyleSheet("QWidget#MainDock { background-color: #202020; border: 1px solid #333; }")
        self.setObjectName("MainDock")

        # Layout Principale
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Pulsante Opzioni (Alto)
        self.top_bar = QWidget()
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(2, 4, 2, 4)
        top_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.btn_settings = QPushButton("⋮")
        self.btn_settings.setStyleSheet("color: white; font-weight: bold; font-size: 16px; background: transparent; border: none;")
        self.btn_settings.clicked.connect(self.prompt_folder_path)
        top_layout.addWidget(self.btn_settings)
        self.main_layout.addWidget(self.top_bar)

        # 2. Pulsanti Scorrimento & Area Contenuto
        self.btn_up = QPushButton("▲")
        self.btn_up.setStyleSheet("color: #888; background: transparent; border: none;")
        self.main_layout.addWidget(self.btn_up)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(4, 4, 4, 4)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.container)

        self.main_layout.addWidget(self.scroll_area)

        self.btn_down = QPushButton("▼")
        self.btn_down.setStyleSheet("color: #888; background: transparent; border: none;")
        self.main_layout.addWidget(self.btn_down)

        # Timer Scorrimento al passaggio del mouse
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.handle_scroll)
        self.scroll_direction = 0

        self.btn_up.enterEvent = lambda e: self.start_scroll(-10)
        self.btn_up.leaveEvent = lambda e: self.stop_scroll()
        self.btn_down.enterEvent = lambda e: self.start_scroll(10)
        self.btn_down.leaveEvent = lambda e: self.stop_scroll()

        # 3. Pulsante Switch Desktop (Basso)
        self.bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(2, 4, 2, 4)
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.btn_switch = QPushButton()
        self.btn_switch.setStyleSheet("background-color: white; border: none;")
        self.btn_switch.clicked.connect(self.switch_desktop)
        bottom_layout.addWidget(self.btn_switch)
        self.main_layout.addWidget(self.bottom_bar)

        # Animation Pulsante Lampeggiante
        self.blink_timer = QTimer()
        self.blink_state = False
        self.blink_timer.timeout.connect(self.toggle_blink)
        self.blink_timer.start(500)

    def update_control_sizes(self, taskbar_height):
        # 1/5 della larghezza
        size = int(taskbar_height / 5)
        self.btn_settings.setFixedSize(size, size)
        self.btn_switch.setFixedSize(size, size)

    def toggle_blink(self):
        self.blink_state = not self.blink_state
        color = "white" if self.blink_state else "#222222"
        self.btn_switch.setStyleSheet(f"background-color: {color}; border: none;")

    def start_scroll(self, direction):
        self.scroll_direction = direction
        self.scroll_timer.start(30)

    def stop_scroll(self):
        self.scroll_timer.stop()

    def handle_scroll(self):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.value() + self.scroll_direction)

    # --- INTEGRAZIONE RISERVA SPAZIO SCHERMO (Windows AppBar) ---
    def setup_system_bar(self):
        screen = QApplication.primaryScreen().geometry()
        taskbar_height = 48  # Dimensione standard Taskbar Win11

        abd = APPBARDATA()
        abd.cbSize = sizeof(APPBARDATA)
        abd.hWnd = c_void_p(int(self.winId()))
        abd.uEdge = self.dock_side
        abd.rc = RECT(0, 0, 0, 0)

        windll.shell32.SHAppBarMessage(ABM_NEW, byref(abd))

        if self.dock_side == ABE_RIGHT:
            abd.rc.left = screen.width() - taskbar_height
            abd.rc.right = screen.width()
        else:
            abd.rc.left = 0
            abd.rc.right = taskbar_height

        abd.rc.top = 0
        abd.rc.bottom = screen.height() - taskbar_height

        windll.shell32.SHAppBarMessage(ABM_SETPOS, byref(abd))

        self.setGeometry(
            abd.rc.left, abd.rc.top,
            abd.rc.right - abd.rc.left, abd.rc.bottom - abd.rc.top
        )
        self.update_control_sizes(taskbar_height)

    def remove_system_bar(self):
        abd = APPBARDATA()
        abd.cbSize = sizeof(APPBARDATA)
        abd.hWnd = c_void_p(int(self.winId()))
        windll.shell32.SHAppBarMessage(ABM_REMOVE, byref(abd))

    def closeEvent(self, event):
        self.remove_system_bar()
        super().closeEvent(event)

    # --- TRASCINAMENTO E SWITCH LATO ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_start_x = event.globalPosition().x()

    def mouseReleaseEvent(self, event):
        if self.is_dragging:
            self.is_dragging = False
            screen_width = QApplication.primaryScreen().geometry().width()
            current_x = event.globalPosition().x()

            # Switch posizione oltre metà schermo
            if current_x < screen_width / 2 and self.dock_side != ABE_LEFT:
                self.dock_side = ABE_LEFT
                self.save_config()
                self.setup_system_bar()
            elif current_x >= screen_width / 2 and self.dock_side != ABE_RIGHT:
                self.dock_side = ABE_RIGHT
                self.save_config()
                self.setup_system_bar()

    # --- SELEZIONE PATHNAME ---
    def prompt_folder_path(self):
        dialog = QFileDialog(self, "Seleziona la cartella da mostrare nel Dock")
        dialog.setFileMode(QFileDialog.FileMode.Directory)
        if dialog.exec():
            paths = dialog.selectedFiles()
            if paths:
                self.folder_path = paths[0]
                self.save_config()
                self.load_items()

    # --- CARICAMENTO E GESTIONE ICONE ---
    def load_items(self):
        # Pulisci elementi vecchi
        for i in reversed(range(self.container_layout.count())): 
            widget = self.container_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        if not os.path.exists(self.folder_path):
            return

        for entry in os.listdir(self.folder_path):
            full_path = os.path.join(self.folder_path, entry)
            btn = QPushButton()
            btn.setFixedSize(36, 36)
            btn.setToolTip(entry)

            # Carica icona personalizzata o predefinita
            if full_path in self.custom_icons:
                pixmap = QPixmap(32, 32)
                pixmap.fill(QColor(self.custom_icons[full_path]))
                btn.setIcon(QIcon(pixmap))
            else:
                icon_provider = QStyle.StandardPixmap.SP_FileIcon
                if os.path.isdir(full_path):
                    icon_provider = QStyle.StandardPixmap.SP_DirIcon
                btn.setIcon(self.style().standardIcon(icon_provider))

            btn.setIconSize(QSize(28, 28))
            btn.setStyleSheet("border: none; background: transparent;")

            # Eventi Click
            btn.clicked.connect(lambda _, p=full_path: self.open_item(p))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, p=full_path, b=btn: self.customize_icon(p, b))

            self.container_layout.addWidget(btn)

    def open_item(self, path):
        if os.path.isdir(path):
            os.startfile(path)
        elif path.endswith(".url"):
            webbrowser.open(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def customize_icon(self, path, button):
        dialog = IconPickerDialog(self)
        if dialog.exec():
            color = dialog.selected_icon_color
            if color:
                self.custom_icons[path] = color
                self.save_config()
                pixmap = QPixmap(32, 32)
                pixmap.fill(QColor(color))
                button.setIcon(QIcon(pixmap))

    # --- CAMBIO DESKTOP VIRTUALE (WIN+CTRL+FRECCIA DESTRA) ---
    def switch_desktop(self):
        import win32api
        import win32con
        # Simula Windows + Ctrl + Freccia Destra
        win32api.keybd_event(win32con.VK_LWIN, 0, 0, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RIGHT, 0, 0, 0)
        win32api.keybd_event(win32con.VK_RIGHT, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
        win32api.keybd_event(win32con.VK_LWIN, 0, win32con.KEYEVENTF_KEYUP, 0)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    dock = DockWindow()
    dock.show()
    sys.exit(app.exec())
