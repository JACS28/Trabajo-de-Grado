"""
Uso rápido
──────────
    from wifi_comm import RobotCommThread

    comm = RobotCommThread(host="192.168.1.100", port=8080)
    comm.connected_signal.connect(win.set_connection)
    comm.device_signal.connect(win.set_device_name)
    comm.response_signal.connect(my_handler)
    comm.start()

    # Enviar un movimiento:
    comm.send_movement(2)   # 0-4

    # Al cerrar la app:
    comm.stop()
"""

import json
import socket
import threading
import time

from PyQt6.QtCore import QThread, pyqtSignal

from motion_profiles import MOVEMENT_LABELS


# ─────────────────────────────────────────────────────────────────────────────
class RobotCommThread(QThread):
    """
    Hilo persistente que:
      • Intenta conectar al ESP32 por TCP.
      • Emite señales Qt compatibles con la GUI ya existente.
      • Reintenta automáticamente si se pierde la conexión.
      • Envía índices de movimiento y recibe confirmaciones JSON.
    """

    # ── Señales públicas ────────────────────────────────────────────────────
    connected_signal  = pyqtSignal(bool)        # True = conectado
    device_signal     = pyqtSignal(str)         # nombre del dispositivo
    response_signal   = pyqtSignal(dict)        # respuesta JSON del ESP32
    log_signal        = pyqtSignal(str)         # mensajes de debug/log

    RETRY_DELAY   = 3.0   
    RECV_TIMEOUT  = 5.0   

    def __init__(self, host: str, port: int = 8080, parent=None):
        super().__init__(parent)
        self.host   = host
        self.port   = port
        self._sock: socket.socket | None = None
        self._running   = False
        self._send_lock = threading.Lock()
        self._pending_mov: int | None = None   

    # ── Interfaz pública ────────────────────────────────────────────────────

    def send_movement(self, mov: int):
        if mov < 0 or mov > 4:
            self.log_signal.emit(f"[WARN] Movimiento inválido: {mov}")
            return
        with self._send_lock:
            self._pending_mov = mov

    def stop(self):
        self._running = False
        self._close_socket()
        self.wait(3000)

    # ── Ciclo principal del hilo ────────────────────────────────────────────

    def run(self):
        self._running = True
        while self._running:
            self.log_signal.emit(f"[INFO] Intentando conectar a {self.host}:{self.port}…")
            if self._connect():
                self._loop()
            if self._running:
                self.log_signal.emit(f"[INFO] Reintentando en {self.RETRY_DELAY:.0f} s…")
                time.sleep(self.RETRY_DELAY)

    # ── Conexión ────────────────────────────────────────────────────────────

    def _connect(self) -> bool:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(5.0)
            sock.connect((self.host, self.port))
            sock.settimeout(self.RECV_TIMEOUT)
            self._sock = sock
            self.log_signal.emit(f"[OK] Conectado a {self.host}:{self.port}")
            self.connected_signal.emit(True)
            self.device_signal.emit(f"ESP32 / {self.host}")
            return True
        except (OSError, TimeoutError) as exc:
            self.log_signal.emit(f"[ERR] No se pudo conectar: {exc}")
            self.connected_signal.emit(False)
            return False

    # ── Bucle de comunicación ───────────────────────────────────────────────

    def _loop(self):
        buf = ""
        while self._running and self._sock:
            with self._send_lock:
                mov = self._pending_mov
                self._pending_mov = None

            if mov is not None:
                try:
                    msg = f"{mov}\n"
                    self._sock.sendall(msg.encode())
                    self.log_signal.emit(f"[TX] Enviado movimiento: {mov}")
                except OSError as exc:
                    self.log_signal.emit(f"[ERR] Error al enviar: {exc}")
                    break

            self._sock.settimeout(0.2)
            try:
                chunk = self._sock.recv(256).decode(errors="ignore")
                if not chunk:
                    self.log_signal.emit("[WARN] Conexión cerrada por el ESP32")
                    break
                buf += chunk
                while "\n" in buf:
                    line, buf = buf.split("\n", 1)
                    line = line.strip()
                    if line:
                        self._handle_response(line)
            except socket.timeout:
                pass  
            except OSError as exc:
                self.log_signal.emit(f"[ERR] Error de lectura: {exc}")
                break

        self._close_socket()
        self.connected_signal.emit(False)
        self.device_signal.emit("—")
        self.log_signal.emit("[INFO] Desconectado del ESP32")

    # ── Parseo de respuestas ────────────────────────────────────────────────

    def _handle_response(self, raw: str):
        try:
            data = json.loads(raw)
            self.log_signal.emit(f"[RX] {data}")
            self.response_signal.emit(data)
        except json.JSONDecodeError:
            self.log_signal.emit(f"[RX-raw] {raw}")

    # ── Limpieza ────────────────────────────────────────────────────────────

    def _close_socket(self):
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None


# ─────────────────────────────────────────────────────────────────────────────
# Integración con el MainWindow
# ─────────────────────────────────────────────────────────────────────────────

def wire_comm_to_gui(win, comm: RobotCommThread):
    SIDEBAR_MOV_MAP = {label: index for index, label in enumerate(MOVEMENT_LABELS)}

    comm.connected_signal.connect(win.set_connection)
    comm.device_signal.connect(win.set_device_name)
    comm.log_signal.connect(print)

    def on_response(data: dict):
        if data.get("status") == "ok":
            mov = data.get("mov")
            if isinstance(mov, int) and hasattr(win, "update_live_preview"):
                win.update_live_preview(mov)

    comm.response_signal.connect(on_response)

    for btn in win.sidebar_buttons:
        label = btn.text()
        mov_idx = SIDEBAR_MOV_MAP.get(label)
        if mov_idx is not None:
            btn.clicked.connect(
                lambda checked, m=mov_idx: comm.send_movement(m)
            )


# ─────────────────────────────────────────────────────────────────────────────
# Demo / punto de entrada standalone
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QWidget, QHBoxLayout,
        QVBoxLayout, QPushButton, QLabel, QFrame, QSizePolicy
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont
    import pyqtgraph as pg
    import numpy as np
    try:
        from GUI import MainWindow
    except ImportError:
        print("[ERROR] No se encontró robot_arm_gui.py en el mismo directorio.")
        print("        Renombra tu archivo GUI a 'robot_arm_gui.py' o ajusta el import.")
        sys.exit(1)

    ESP32_HOST = "192.168.4.1"  
    ESP32_PORT = 8080

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    win = MainWindow()

    comm = RobotCommThread(host=ESP32_HOST, port=ESP32_PORT)
    wire_comm_to_gui(win, comm)
    comm.start()

    win.show()

    def on_exit():
        comm.stop()

    app.aboutToQuit.connect(on_exit)
    sys.exit(app.exec())