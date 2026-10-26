"""Descarga de audio (a MP3, con metadata y carátula incrustadas) de un
video de YouTube, vía yt-dlp + ffmpeg lanzados como QProcess."""
from pathlib import Path
from PyQt6.QtCore import QObject, QProcess, pyqtSignal
from sakukelly.config import get_ytdlp_bin, get_ffmpeg_bin


class YouTubeDownloader(QObject):
    started = pyqtSignal()
    progress = pyqtSignal(str)          # linea de progreso recortada, para la barra de estado
    finishedOk = pyqtSignal(str, str)   # folder, filepath (filepath puede venir vacío)
    failed = pyqtSignal()
    alreadyBusy = pyqtSignal()          # ya habia una descarga en curso

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None

    @property
    def busy(self):
        return bool(self._proc and self._proc.state() != QProcess.ProcessState.NotRunning)

    def cancel(self):
        if self.busy:
            self._proc.kill()

    def download(self, video_id, folder):
        if self.busy:
            self.alreadyBusy.emit()
            return False
        p = QProcess(self); self._proc = p; p.setProgram(get_ytdlp_bin())
        template = str(Path(folder) / "%(title).150s [%(id)s].%(ext)s")
        p.setArguments(["--no-playlist", "--no-warnings", "--geo-bypass", "--ffmpeg-location", get_ffmpeg_bin(),
            "-x", "--audio-format", "mp3", "--audio-quality", "0", "--embed-metadata",
            "--embed-thumbnail", "--print", "after_move:filepath", "-o", template,
            f"https://www.youtube.com/watch?v={video_id}"])
        p.readyReadStandardOutput.connect(lambda p=p: self.progress.emit(
            bytes(p.readAllStandardOutput()).decode("utf-8", "ignore").strip()[-180:]))
        p.finished.connect(lambda code, status, p=p, folder=folder: self._on_finished(p, code, folder))
        p.start()
        self.started.emit()
        return True

    def _on_finished(self, p, code, folder):
        if p is not self._proc:
            return
        if code == 0:
            output = bytes(p.readAllStandardOutput()).decode("utf-8", "ignore").strip().splitlines()
            path = next((x.strip() for x in reversed(output) if Path(x.strip()).exists()), "")
            self.finishedOk.emit(folder, path)
        else:
            self.failed.emit()
