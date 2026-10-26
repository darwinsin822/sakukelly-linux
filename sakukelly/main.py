"""Punto de entrada de Sakukelly Music.

Configura la aplicación Qt, aplica el candado de instancia única (evita que
se abran dos sesiones del reproductor a la vez, peleando por el mismo
dispositivo de audio) y lanza la ventana principal.
"""
import sys
from PyQt6.QtGui import QIcon
from PyQt6.QtNetwork import QLocalServer, QLocalSocket
from PyQt6.QtWidgets import QApplication

try:
    from dbus.mainloop.pyqt6 import DBusQtMainLoop
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False

from sakukelly.config import APP_ID, APP_NAME, APP_ICON, SINGLE_INSTANCE_KEY
from sakukelly.ui.main_window import Win


def main():
    if DBUS_AVAILABLE:
        try: DBusQtMainLoop(set_as_default=True)
        except Exception: pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # cerrar minimiza a la bandeja; sólo "Salir" cierra de verdad
    # Keep the Linux desktop identity identical to sakukelly.desktop. This lets
    # Cinnamon/X11/Wayland associate the running window with its launcher icon.
    app.setApplicationName(APP_ID)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName("Sakukelly Project")
    app.setDesktopFileName(APP_ID)
    app.setWindowIcon(QIcon(APP_ICON))

    # ---- Instancia única ----------------------------------------------
    probe = QLocalSocket()
    probe.connectToServer(SINGLE_INSTANCE_KEY)
    if probe.waitForConnected(1000):
        try:
            arg = sys.argv[1] if len(sys.argv) > 1 else ""
            msg = f"open:{arg}".encode("utf-8") if arg else b"show"
            probe.write(msg)
            probe.waitForBytesWritten(500)
            probe.disconnectFromServer()
        except Exception:
            pass
        probe.close()
        return

    err = probe.error()
    probe.close()
    if err == QLocalSocket.LocalSocketError.ConnectionRefusedError:
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)

    instanceServer = QLocalServer()
    if not instanceServer.listen(SINGLE_INSTANCE_KEY):
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        instanceServer.listen(SINGLE_INSTANCE_KEY)

    w = Win(); w.show()
    w._single_instance_server = instanceServer

    def _on_second_instance():
        conn = instanceServer.nextPendingConnection()
        if conn:
            def _read_conn():
                try:
                    data = bytes(conn.readAll()).decode("utf-8", "ignore").strip()
                    if data.startswith("open:"):
                        filepath = data[5:].strip()
                        if filepath and hasattr(w, "play_file_external"):
                            w.play_file_external(filepath)
                except Exception:
                    pass
                w.showNormal(); w.raise_(); w.activateWindow()
            conn.readyRead.connect(_read_conn)
            conn.disconnected.connect(conn.deleteLater)
        else:
            w.showNormal(); w.raise_(); w.activateWindow()
    instanceServer.newConnection.connect(_on_second_instance)

    sys.exit(app.exec())

