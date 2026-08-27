import sys
import os
import json
import webbrowser
from ctypes import windll, Structure, c_ulong, sizeof, byref, c_void_p

from PyQt6.QtCore import Qt, QTimer, QSize, QUrl, QFileSystemWatcher, QPointF
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QFileDialog, QDialog, QGridLayout, QLabel, QScrollArea, QFrame,
    QColorDialog, QCheckBox, QFileIconProvider, QToolTip
)
from PyQt6.QtGui import QIcon, QColor, QPixmap, QPainter, QPainterPath, QFont, QDesktopServices, QFileInfo

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

# --- GENERATORE DI 48 ICONE MATERIAL VECTORIALI (SVG/PAINTER) ---
def draw_material_icon(index, size=32):
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    
    # Palette e disegno icone stile Material
    colors = ["#2196F3", "#4CAF50", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4", "#FF5722", "#607D8B"]
    color = QColor(colors[index % len(colors)])
    painter.setBrush(color)
    painter.setPen(Qt.PenStyle.NoPen)
    
    path = QPainterPath()
    # Esempi di forme geometriche/simboli stile Material
    mode = index % 6
    if mode == 0:  # Cartella / Blocco
        path.addRoundedRect(4, 8, 24, 18, 3, 3)
        path.addRect(4, 5, 10, 4)
    elif mode == 1:  # Lente d'ingrandimento / Cerchio
        path.addEllipse(6, 6, 14, 14)
        path.addRect(18, 18, 8, 4)
    elif mode == 2:  # Lampadina / Stella
        path.addEllipse(8, 4, 16, 16)
        path.addRect(12, 22, 8, 6)
    elif mode == 3:  # Ingranaggio / Quadrato
        path.addRoundedRect(6, 6, 20, 20, 4, 4)
    elif mode == 4:  # Documento
        path.addRoundedRect(6, 4, 20, 24, 2, 2)
    elif mode == 5:  # Simbolo Play/Azione
        path.moveTo(8, 6)
        path.lineTo(26, 16)
        path.lineTo(8, 26)
        path.closeSubpath()

    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


# --- POPUP SELEZIONE ICONE PERSONALIZZATE + NASCONDI ---
class IconPickerDialog(QDialog):
    def __init__(self, current_hidden=False, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Personalizza Icona")
        self.setFixedSize(320, 440)
        self.selected_icon_index = None

        layout = QVBoxLayout(self)

        # Checkbox per nascondere
        self.chk_hide = QCheckBox("Nascondi questa icona dalla barra")
        self.chk_hide.setChecked(current_hidden)
        layout.addWidget(self.chk_hide)

        grid_widget = QWidget()
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)

        # 48 icone disposte 6 x 8
        for i in range(48):
            btn = QPushButton()
            btn.setFixedSize(38, 38)
            icon = draw_material_icon(i)
            btn.setIcon(icon)
            btn.setIconSize(QSize(28, 28))
            btn.clicked.connect(lambda _, idx=i: self.select_icon(idx))
            row = i // 6
            col = i % 6
            grid.addWidget(btn, row, col)

        scroll = QScrollArea()
        scroll.setWidget(grid_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        btn_confirm = QPushButton("Conferma")
        btn_confirm.clicked.connect(self.accept)
        layout.addWidget(btn_confirm)

    def select_icon(self, index):
        self.selected_icon_index = index

    def is_hidden(self):
        return self.chk_hide.isChecked()


# --- FINESTRA PRINCIPALE DOCK ---
class DockWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.config = self.load_config()
        self.dock_side = self.config.get("side", ABE_RIGHT)
        self.folder_path = self.config.get("path", "")
        self.custom_icons = self.config.get("custom_icons", {})  # {path: icon_index}
        self.hidden_items = set(self.config.get("hidden_items", []))
        self.bg_color = self.config.get("bg_color", None)

        self.is_dragging = False
        self.drag_start_x = 0

        # Monitoring cartella
        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(self.load_items)

        self.init_ui()
        self.setup_system_bar()

        if not self.folder_path or not os.path.exists(self.folder_path):
            QTimer.singleShot(100, self.prompt_folder_path)
        else:
            self.set_watched_directory(self.folder_path)
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
        self.config["hidden_items"] = list(self.hidden_items)
        self.config["bg_color"] = self.bg_color
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.config, f, indent=4)

    def init_ui(self):
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setObjectName("MainDock")
        self.update_background_style()

        # Layout Principale
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 1. Barra Superiore (Tre pallini a sx, X a dx)
        self.top_bar = QWidget()
        top_layout = QHBoxLayout(self.top_bar)
        top_layout.setContentsMargins(2, 2, 2, 2)

        self.btn_settings = QPushButton("⋮")
        self.btn_settings.setStyleSheet("color: white; font-weight: bold; font-size: 14px; background: transparent; border: none;")
        self.btn_settings.clicked.connect(self.prompt_folder_path)

        self.btn_close = QPushButton("✕")
        self.btn_close.setStyleSheet("color: white; font-weight: bold; font-size: 14px; background: transparent; border: none;")
        self.btn_close.clicked.connect(self.close)

        top_layout.addWidget(self.btn_settings, 0, Qt.AlignmentFlag.AlignLeft)
        top_layout.addStretch()
        top_layout.addWidget(self.btn_close, 0, Qt.AlignmentFlag.AlignRight)
        self.main_layout.addWidget(self.top_bar)

        # 2. Frecce Schiacciate e Area Scorrimento
        self.btn_up = QPushButton("▲")
        self.btn_up.setStyleSheet("color: #AAA; background: rgba(255,255,255,0.05); border: none; font-size: 8px;")
        self.main_layout.addWidget(self.btn_up)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll_area.setStyleSheet("background: transparent; border: none;")

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(2, 4, 2, 4)
        self.container_layout.setSpacing(6)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.container)

        self.main_layout.addWidget(self.scroll_area)

        self.btn_down = QPushButton("▼")
        self.btn_down.setStyleSheet("color: #AAA; background: rgba(255,255,255,0.05); border: none; font-size: 8px;")
        self.main_layout.addWidget(self.btn_down)

        # Timer Scorrimento al passaggio del mouse (Senza click)
        self.scroll_timer = QTimer()
        self.scroll_timer.timeout.connect(self.handle_scroll)
        self.scroll_direction = 0

        self.btn_up.enterEvent = lambda e: self.start_scroll(-8)
        self.btn_up.leaveEvent = lambda e: self.stop_scroll()
        self.btn_down.enterEvent = lambda e: self.start_scroll(8)
        self.btn_down.leaveEvent = lambda e: self.stop_scroll()

        # 3. Pulsante Basso a Destra (Desktop Switcher Lampeggiante)
        self.bottom_bar = QWidget()
        bottom_layout = QHBoxLayout(self.bottom_bar)
        bottom_layout.setContentsMargins(2, 2, 2, 2)
        bottom_layout.setAlignment(Qt.AlignmentFlag.AlignRight)

        self.btn_switch = QPushButton()
        self.btn_switch.clicked.connect(self.switch_desktop)
        bottom_layout.addWidget(self.btn_switch)
        self.main_layout.addWidget(self.bottom_bar)

        # Lampeggio
        self.blink_timer = QTimer()
        self.blink_state = False
        self.blink_timer.timeout.connect(self.toggle_blink)
        self.blink_timer.start(500)

    def update_background_style(self):
        if self.bg_color:
            self.setStyleSheet(f"QWidget#MainDock {{ background-color: {self.bg_color}; }}")
        else:
            # Colore predefinito Tema Windows 11 (Scuro)
            self.setStyleSheet("QWidget#MainDock { background-color: #202020; }")

    def update_control_sizes(self, bar_width):
        # 1/5 della larghezza della barra
        size = max(12, int(bar_width / 5))
        self.btn_settings.setFixedSize(size, size)
        self.btn_close.setFixedSize(size, size)
        self.btn_switch.setFixedSize(size, size)
        self.btn_up.setFixedHeight(12)
        self.btn_down.setFixedHeight(12)

    def toggle_blink(self):
        self.blink_state = not self.blink_state
        color = "white" if self.blink_state else "#111111"
        self.btn_switch.setStyleSheet(f"background-color: {color}; border: none;")

    def start_scroll(self, direction):
        self.scroll_direction = direction
        self.scroll_timer.start(25)

    def stop_scroll(self):
        self.scroll_timer.stop()

    def handle_scroll(self):
        bar = self.scroll_area.verticalScrollBar()
        bar.setValue(bar.value() + self.scroll_direction)

    # --- REGISTRAZIONE APPBAR WINDOWS ---
    def setup_system_bar(self):
        screen = QApplication.primaryScreen().geometry()
        taskbar_height = 48  # Larghezza standard equivalente alla taskbar

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

    # --- TRASCINAMENTO & MENU CONTESTUALE SFONDO ---
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_start_x = event.globalPosition().x()

    def mouseReleaseEvent(self, event):
        if self.is_dragging and event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = False
            screen_width = QApplication.primaryScreen().geometry().width()
            current_x = event.globalPosition().x()

            if current_x < screen_width / 2 and self.dock_side != ABE_LEFT:
                self.dock_side = ABE_LEFT
                self.save_config()
                self.setup_system_bar()
            elif current_x >= screen_width / 2 and self.dock_side != ABE_RIGHT:
                self.dock_side = ABE_RIGHT
                self.save_config()
                self.setup_system_bar()

    def contextMenuEvent(self, event):
        # Selezione colore di sfondo al clic destro sullo sfondo
        color = QColorDialog.getColor()
        if color.isValid():
            self.bg_color = color.name()
            self.update_background_style()
            self.save_config()

    # --- SELEZIONE E WATCHER PATHNAME ---
    def set_watched_directory(self, path):
        directories = self.watcher.directories()
        if directories:
            self.watcher.removePaths(directories)
        if os.path.exists(path):
            self.watcher.addPath(path)

    def prompt_folder_path(self):
        while True:
            dialog = QFileDialog(self, "Seleziona la cartella da mostrare")
            dialog.setFileMode(QFileDialog.FileMode.Directory)
            if dialog.exec():
                paths = dialog.selectedFiles()
                if paths and os.path.exists(paths[0]):
                    self.folder_path = paths[0]
                    self.save_config()
                    self.set_watched_directory(self.folder_path)
                    self.load_items()
                    break
            else:
                # Rimane aperto finché non viene fornito un pathname valido se manca
                if not self.folder_path or not os.path.exists(self.folder_path):
                    continue
                else:
                    break

    # --- CARICAMENTO ITEM & TOOLTIP ARIAL 14 ---
    def load_items(self):
        # Svuota container
        for i in reversed(range(self.container_layout.count())):
            widget = self.container_layout.itemAt(i).widget()
            if widget:
                widget.setParent(None)

        if not os.path.exists(self.folder_path):
            return

        icon_provider = QFileIconProvider()

        for entry in os.listdir(self.folder_path):
            full_path = os.path.join(self.folder_path, entry)

            if full_path in self.hidden_items:
                continue

            btn = QPushButton()
            btn.setFixedSize(36, 36)

            # Tooltip Arial 14
            QToolTip.setFont(QFont("Arial", 14))
            btn.setToolTip(entry)

            # Gestione Icona (Custom o Sistema Originario)
            if full_path in self.custom_icons:
                idx = self.custom_icons[full_path]
                btn.setIcon(draw_material_icon(idx))
            else:
                info = QFileInfo(full_path)
                btn.setIcon(icon_provider.icon(info))

            btn.setIconSize(QSize(28, 28))
            btn.setStyleSheet("border: none; background: transparent;")

            btn.clicked.connect(lambda _, p=full_path: self.open_item(p))
            btn.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            btn.customContextMenuRequested.connect(lambda pos, p=full_path, b=btn: self.customize_item(p, b))

            self.container_layout.addWidget(btn)

    def open_item(self, path):
        if os.path.isdir(path):
            os.startfile(path)
        elif path.endswith(".url"):
            webbrowser.open(path)
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    def customize_item(self, path, button):
        is_hidden = path in self.hidden_items
        dialog = IconPickerDialog(current_hidden=is_hidden, parent=self)
        if dialog.exec():
            # Gestione Nascondi
            if dialog.is_hidden():
                self.hidden_items.add(path)
            else:
                self.hidden_items.discard(path)

            # Gestione Icona
            if dialog.selected_icon_index is not None:
                self.custom_icons[path] = dialog.selected_icon_index

            self.save_config()
            self.load_items()

    # --- CAMBIO CICLICO DESKTOP VIRTUALE ---
    def switch_desktop(self):
        import win32api
        import win32con
        # Invia la combinazione Win + Ctrl + Freccia Destra per scorrere al desktop successivo
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
