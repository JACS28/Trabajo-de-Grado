import sys
import unicodedata
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout,
    QVBoxLayout, QPushButton, QLabel, QFrame, QSizePolicy, QTabWidget
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
import pyqtgraph as pg

from motion_profiles import (
    MOVEMENT_LABELS,
    MOVEMENT_TABLE,
    FINGER_LABELS,
    MOTOR_GROUP_LABELS,
    finger_motor_series,
)

STYLE_PATH = Path(__file__).with_name("styles.qss")

BG_PANEL = "#ffffff"
BTN_BORDER = "#c8d0da"
TEXT_PRIMARY = "#1a2332"
TEXT_MUTED = "#57606a"


def _slugify(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return "_".join(part for part in ascii_text.lower().replace("-", " ").split())


def load_stylesheet() -> str:
    try:
        return STYLE_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


class SidebarButton(QPushButton):

    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self.setObjectName("sidebarButton")
        self.setFixedHeight(48)
        self.setFixedWidth(150)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(True)

class StatusIndicator(QWidget):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("statusIndicator")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 16, 6)
        layout.setSpacing(10)

        self.dot = QLabel("●")
        self.dot.setObjectName("statusDot")
        layout.addWidget(self.dot)

        self.text_label = QLabel("Sin conexión")
        self.text_label.setObjectName("statusText")
        layout.addWidget(self.text_label)
        self.set_connected(False)

    def set_connected(self, connected: bool):
        if connected:
            msg   = "Conexión establecida — listo para recibir"
        else:
            msg   = "Sin conexión"

        self.setProperty("connected", connected)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()
        self.text_label.setText(msg)

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Robot Arm Monitor")
        self.setMinimumSize(900, 600)
        self._photo_cache: dict[str, QPixmap] = {}
        self.current_movement_index = 0
        self._build_ui()

    # ── UI construction ────────────────────────────────────────────────────

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)

        main_vbox = QVBoxLayout(root)
        main_vbox.setContentsMargins(20, 16, 20, 16)
        main_vbox.setSpacing(14)

        # ── Top bar ────────────────────────────────────────────────────────
        top_bar = QHBoxLayout()
        top_bar.setSpacing(16)

        self.status_indicator = StatusIndicator()
        top_bar.addWidget(self.status_indicator)

        top_bar.addStretch()

        device_frame = QFrame()
        device_frame.setObjectName("deviceFrame")
        dev_layout = QHBoxLayout(device_frame)
        dev_layout.setContentsMargins(12, 6, 16, 6)
        dev_layout.setSpacing(8)

        dev_icon = QLabel("⬡")
        dev_icon.setObjectName("deviceIcon")
        dev_layout.addWidget(dev_icon)

        dev_caption = QLabel("Dispositivo:")
        dev_caption.setObjectName("deviceCaption")
        dev_layout.addWidget(dev_caption)

        self.device_name_label = QLabel("—")
        self.device_name_label.setObjectName("deviceName")
        dev_layout.addWidget(self.device_name_label)

        top_bar.addWidget(device_frame)
        main_vbox.addLayout(top_bar)

        # ── Divider ────────────────────────────────────────────────────────
        divider = QFrame()
        divider.setFrameShape(QFrame.Shape.HLine)
        divider.setObjectName("divider")
        main_vbox.addWidget(divider)

        # ── Content row ────────────────────────────────────────────────────
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        sidebar = self._build_sidebar()
        content_row.addWidget(sidebar, 0)

        plot_panel = self._build_plot_panel()
        content_row.addWidget(plot_panel, 1)

        main_vbox.addLayout(content_row, 1)

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(175)

        vbox = QVBoxLayout(sidebar)
        vbox.setContentsMargins(12, 16, 12, 16)
        vbox.setSpacing(10)

        heading = QLabel("Movimientos")
        heading.setObjectName("sidebarHeading")
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vbox.addWidget(heading)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setObjectName("sidebarSeparator")
        vbox.addWidget(sep)
        vbox.addSpacing(4)

        self.sidebar_buttons: list[SidebarButton] = []
        labels = ["Base", "Agarre de barril", "Agarre esférico", "Agarre de llave", "Agarre de pinza"]

        for label in labels:
            btn = SidebarButton(label)
            btn.toggled.connect(lambda checked, b=btn: self._on_sidebar_toggle(b, checked))
            vbox.addWidget(btn, 0, Qt.AlignmentFlag.AlignHCenter)
            self.sidebar_buttons.append(btn)

        vbox.addStretch()
        return sidebar

    def _build_plot_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("plotPanel")

        vbox = QVBoxLayout(panel)
        vbox.setContentsMargins(16, 14, 16, 14)
        vbox.setSpacing(10)

        title_row = QHBoxLayout()
        plot_title = QLabel("GRÁFICAS DE MOVIMIENTO")
        plot_title.setObjectName("plotTitle")
        title_row.addWidget(plot_title)
        title_row.addStretch()

        self.channel_label = QLabel("CH: —")
        self.channel_label.setObjectName("channelLabel")
        title_row.addWidget(self.channel_label)
        vbox.addLayout(title_row)

        self.profile_tabs = QTabWidget()
        self.profile_tabs.setObjectName("graphTabs")
        self.profile_tabs.setDocumentMode(True)

        self.live_plot, self.live_curves = self._build_live_plot()
        self.curves = self.live_curves

        self.angle_plot, self.angle_curves = self._build_angle_plot()
        self._populate_angle_plot(self.current_movement_index)

        self.profile_tabs.addTab(self.live_plot, "Prevista del movimiento")
        self.profile_tabs.addTab(self.angle_plot, "Ángulos")

        self._update_live_photo(MOVEMENT_LABELS[0])

        vbox.addWidget(self.profile_tabs)

        return panel

    def _configure_plot_widget(self, widget: pg.PlotWidget):
        pg.setConfigOption("background", BG_PANEL)
        pg.setConfigOption("foreground", TEXT_PRIMARY)
        widget.setBackground(BG_PANEL)
        widget.setObjectName("plotWidget")
        widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        widget.showGrid(x=True, y=True, alpha=0.25)
        for axis in ("bottom", "left"):
            widget.getAxis(axis).setPen(pg.mkPen(color=BTN_BORDER, width=1))
            widget.getAxis(axis).setTextPen(pg.mkPen(color=TEXT_MUTED))

    def _style_legend(self, legend):
        legend.setBrush(pg.mkBrush(BG_PANEL))
        legend.setPen(pg.mkPen(BTN_BORDER, width=1))
        legend.setLabelTextColor(TEXT_PRIMARY)

    def _build_angle_plot(self):
        page = QFrame()
        page.setObjectName("anglesTab")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        plot = pg.PlotWidget()
        self._configure_plot_widget(plot)
        plot.getAxis("bottom").setLabel("Dedo", color=TEXT_MUTED)
        plot.getAxis("bottom").setTicks([
            [(index, label) for index, label in enumerate(FINGER_LABELS)]
        ])
        plot.getAxis("left").setLabel("Grados (°)", color=TEXT_MUTED)
        plot.getAxis("left").setTicks([
            [(0, "0"), (30, "30"), (60, "60"), (90, "90"), (120, "120"), (150, "150"), (180, "180")]
        ])
        plot.setXRange(-0.5, 6.0)
        plot.setYRange(0, 185)

        for boundary in (0.5, 1.5, 2.5, 3.5):
            separator = pg.InfiniteLine(
                pos=boundary,
                angle=90,
                pen=pg.mkPen(BTN_BORDER, width=1, style=Qt.PenStyle.DashLine),
            )
            separator.setZValue(0)
            plot.addItem(separator)

        legend = plot.addLegend()
        legend.anchor((1, 0), (1, 0), offset=(-12, 12))
        self._style_legend(legend)

        curves = []
        series_specs = [
            (MOTOR_GROUP_LABELS[0], "#0969da", -0.12),
            (MOTOR_GROUP_LABELS[1], "#e36209", 0.12),
        ]
        for name, color, _ in series_specs:
            curve = pg.PlotDataItem(
                [],
                [],
                pen=None,
                symbol="o",
                symbolSize=8,
                symbolBrush=pg.mkBrush(color),
                symbolPen=pg.mkPen(color, width=1),
                antialias=True,
            )
            plot.addItem(curve)
            legend.addItem(curve, name)
            curves.append(curve)

        layout.addWidget(plot)
        return page, curves

    def _build_live_plot(self):
        page = QFrame()
        page.setObjectName("liveTab")

        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.live_photo_label = QLabel()
        self.live_photo_label.setObjectName("livePhoto")
        self.live_photo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.live_photo_label.setMinimumHeight(300)
        self.live_photo_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.live_hint = QLabel("Vista del movimiento")
        self.live_hint.setObjectName("liveHint")
        self.live_hint.setWordWrap(True)
        self.live_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self.live_photo_label)
        layout.addWidget(self.live_hint)
        
        return page, []

    def _populate_live_plot(self):
        self.update_live_preview(0)

    def _populate_angle_plot(self, movement_index: int):
        if movement_index < 0 or movement_index >= len(MOVEMENT_TABLE):
            return

        extension_flextion, abduction_adduction = finger_motor_series(MOVEMENT_TABLE[movement_index])
        x_values = list(range(5))
        x_offset = 0.12

        self.angle_curves[0].setData([x - x_offset for x in x_values], extension_flextion)
        self.angle_curves[1].setData([x + x_offset for x in x_values], abduction_adduction)


    # ── Picture data ──────────────────────────────────────────────────────────

    def _seed_demo_plot(self):
        self._populate_live_plot()

    # ── Sidebar logic ──────────────────────────────────────────────────────

    def _on_sidebar_toggle(self, sender: SidebarButton, checked: bool):
        if checked:
            for btn in self.sidebar_buttons:
                if btn is not sender and btn.isChecked():
                    btn.blockSignals(True)
                    btn.setChecked(False)
                    btn.blockSignals(False)
            self.channel_label.setText(f"CH: {sender.text()}")
            movement_index = self._movement_index_for_label(sender.text())
            if movement_index is not None:
                self.current_movement_index = movement_index
                self._update_live_photo(sender.text())
                self._populate_angle_plot(movement_index)
        else:
            if not any(b.isChecked() for b in self.sidebar_buttons):
                self.channel_label.setText("CH: —")

    # ── Public helpers ──────────────────────────────

    def set_connection(self, connected: bool):
        self.status_indicator.set_connected(connected)

    def set_device_name(self, name: str):
        self.device_name_label.setText(name)

    def update_plot(self, x, y, motor_index: int = 0):
        self.curves[motor_index].setData(x, y)

    def update_live_preview(self, movement_index: int):
        if movement_index < 0 or movement_index >= len(MOVEMENT_TABLE):
            return
        self._update_live_photo(MOVEMENT_LABELS[movement_index])

    def _movement_index_for_label(self, label: str) -> int | None:
        try:
            return MOVEMENT_LABELS.index(label)
        except ValueError:
            return None

    def _photo_candidates(self, label: str) -> list[Path]:
        base_dir = Path(__file__).with_name("photo")
        stems = [f"{label}"]
        extensions = [".png", ".PNG", ".jpg", ".JPG", ".jpeg", ".JPEG"]
        candidates: list[Path] = []

        for stem in stems:
            for extension in extensions:
                candidates.append(base_dir / f"{stem}{extension}")
                candidates.append(Path(__file__).with_name(f"{stem}{extension}"))

        return [
            Path(__file__).with_name("photo.png"),
            *candidates,
        ]

    def _update_live_photo(self, label: str):
        cached_pixmap = self._photo_cache.get(label)
        if cached_pixmap is None:
            for candidate in self._photo_candidates(label):
                if candidate.is_file():
                    pixmap = QPixmap(str(candidate))
                    if not pixmap.isNull():
                        cached_pixmap = pixmap
                        self._photo_cache[label] = pixmap
                        break

        if cached_pixmap is not None:
            target_size = self.live_photo_label.size().expandedTo(self.live_photo_label.minimumSizeHint())
            self.live_photo_label.setPixmap(
                cached_pixmap.scaled(
                    target_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )
            self.live_photo_label.setText("")
            return

        self.live_photo_label.setPixmap(QPixmap())
        self.live_photo_label.setText(f"Sin foto disponible para {label}")




# if __name__ == "__main__":
#     app = QApplication(sys.argv)
#     app.setStyle("Fusion")
#     app.setStyleSheet(load_stylesheet())

#     win = MainWindow()

#     # ── Demo: show a connected device ─────────────────────────────────────
#     win.set_connection(True)
#     win.set_device_name("ESP32 / COM3")

#     win.show()
#     sys.exit(app.exec())