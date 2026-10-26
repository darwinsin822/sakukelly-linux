"""Módulo de actualización y autoreparación automática para yt-dlp.

Descarga y actualiza de forma transparente la versión más reciente oficial
de yt-dlp directamente desde GitHub en caso de desactualización o error de streaming.
"""
import os, sys, urllib.request
from pathlib import Path
from PyQt6.QtCore import QThread, pyqtSignal
from sakukelly.config import HOME

YTDLP_URL = "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"

class YtDlpUpdaterThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def run(self):
        try:
            bin_dir = HOME / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            target_path = bin_dir / "yt-dlp"
            temp_path = bin_dir / "yt-dlp.tmp"

            req = urllib.request.Request(
                YTDLP_URL,
                headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = resp.read()
                if len(data) < 100000:
                    self.finished_signal.emit(False, "Descarga corrupta o incompleta")
                    return
                with open(temp_path, "wb") as f:
                    f.write(data)

            os.chmod(temp_path, 0o755)
            temp_path.replace(target_path)
            self.finished_signal.emit(True, str(target_path))
        except Exception as e:
            self.finished_signal.emit(False, str(e))
