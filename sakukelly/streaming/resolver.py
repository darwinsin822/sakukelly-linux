"""Búsqueda en YouTube y resolución de la URL directa de streaming, vía
yt-dlp lanzado como QProcess.

Estas dos clases no tocan ningún widget: reciben una consulta o una fila
de resultado y emiten señales Qt con el resultado ya parseado. Quien las
use (hoy, la ventana principal) decide qué hacer con la lista de
resultados o con la URL resuelta — pintar la lista, reproducir, etc.
"""
import json, time
try:
    from PyQt6.QtCore import QObject, QProcess, pyqtSignal, QTimer
except ImportError:
    class QObject:
        def __init__(self, parent=None): pass
    class QProcess: pass
    class pyqtSignal:
        def __init__(self, *args): pass
    class QTimer: pass
from sakukelly.config import get_ytdlp_bin, YT_ID_RE
from sakukelly.streaming.youtube import resolve_thumb


def valid_video_id(vid):
    return bool(YT_ID_RE.fullmatch(str(vid or "")))


# Caché en memoria para URLs resueltas de streaming (TTL: 45 minutos)
_STREAM_URL_CACHE = {}  # {video_id: (url, timestamp)}
_SEARCH_CACHE = {}      # {query: (rows, timestamp)}
CACHE_TTL = 2700        # 45 minutos
SEARCH_CACHE_TTL = 1200 # 20 minutos


class YouTubeSearcher(QObject):
    """Busca canciones en YouTube (ytsearchN:) y entrega filas ya listas
    para guardar en la base de datos / pintar en una lista."""
    resultsReady = pyqtSignal(list)   # [{"id","title","artist","duration","thumb"}, ...]
    searchFailed = pyqtSignal(str)    # mensaje de error (stderr de yt-dlp, puede venir vacío)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None

    @property
    def busy(self):
        return bool(self._proc and self._proc.state() != QProcess.ProcessState.NotRunning)

    def cancel(self):
        if self.busy:
            self._proc.kill()

    def search(self, query, limit=12):
        q = str(query or "").strip().lower()
        now = time.time()
        if q in _SEARCH_CACHE:
            cached_rows, ts = _SEARCH_CACHE[q]
            if now - ts < 1200:  # 20 minutos de caché de búsqueda
                QTimer.singleShot(0, lambda: self.resultsReady.emit(cached_rows))
                return

        self.cancel()
        p = QProcess(self); self._proc = p
        p.setProgram(get_ytdlp_bin())
        p.setArguments([
            "--flat-playlist", "--dump-single-json", "--no-warnings",
            "--no-playlist", "--no-check-certificates", "--geo-bypass",
            "--extractor-args", "youtube:player_client=android,web",
            f"ytsearch{limit}:{query}"
        ])
        p.finished.connect(lambda code, status, p=p, q_key=q: self._on_finished(p, code, q_key))
        p.start()

    def _on_finished(self, p, code, q_key):
        if p is not self._proc:
            return
        if code != 0:
            msg = bytes(p.readAllStandardError()).decode("utf-8", "ignore").strip()
            self.searchFailed.emit(msg)
            return
        try:
            data = json.loads(bytes(p.readAllStandardOutput()).decode("utf-8", "ignore"))
            entries = data.get("entries") or []
        except Exception:
            entries = []
        rows = []
        for e in entries:
            vid = str(e.get("id") or "")
            if not valid_video_id(vid):
                continue
            title = str(e.get("title") or "Sin título")
            artist = str(e.get("channel") or e.get("uploader") or "YouTube")
            dur = int(e.get("duration") or 0)
            rows.append({"id": vid, "title": title, "artist": artist, "duration": dur, "thumb": resolve_thumb(e, vid)})
        if rows and q_key:
            _SEARCH_CACHE[q_key] = (rows, time.time())
        self.resultsReady.emit(rows)


class YouTubeStreamResolver(QObject):
    """Resuelve la URL directa (CDN de YouTube) de un video_id, para poder
    pasársela tal cual a QMediaPlayer."""
    resolved = pyqtSignal(dict, str)  # row original, url resuelta
    failed = pyqtSignal(dict, str)    # row original, mensaje de error

    def __init__(self, parent=None):
        super().__init__(parent)
        self._proc = None

    @property
    def busy(self):
        try:
            return bool(self._proc and self._proc.state() != QProcess.ProcessState.NotRunning)
        except Exception:
            return False

    def cancel(self):
        try:
            if self.busy and self._proc:
                self._proc.kill()
        except Exception:
            pass

    def resolve(self, row, fallback=False):
        vid = row.get("id")
        if not valid_video_id(vid):
            self.failed.emit(row, "ID de video inválido")
            return

        now = time.time()
        if vid in _STREAM_URL_CACHE:
            cached_url, ts = _STREAM_URL_CACHE[vid]
            if now - ts < CACHE_TTL:
                QTimer.singleShot(0, lambda r=row, u=cached_url: self.resolved.emit(r, u))
                return

        self.cancel()
        p = QProcess(self); self._proc = p
        p.setProgram(get_ytdlp_bin())
        fmt = "bestaudio[ext=m4a]/bestaudio[acodec=aac]/bestaudio[ext=mp4]/bestaudio/best" if fallback else "bestaudio[ext=m4a][abr<=160]/bestaudio[ext=m4a]/bestaudio[acodec=aac]/bestaudio[ext=mp4]/bestaudio/best"
        p.setArguments([
            "-g", "-f", fmt, "--no-playlist", "--no-warnings",
            "--no-check-certificates", "--geo-bypass",
            "--extractor-args", "youtube:player_client=android,web",
            f"https://www.youtube.com/watch?v={vid}"
        ])
        p.finished.connect(lambda code, status, p=p, row=row, fb=fallback, v=vid: self._on_finished(p, code, row, fb, v))
        p.start()

    def _on_finished(self, p, code, row, fallback, vid):
        try:
            if p is not self._proc:
                return
            if code != 0:
                if not fallback:
                    self.resolve(row, fallback=True)
                    return
                self.failed.emit(row, "YouTube no respondió. La biblioteca y otros proveedores siguen disponibles.")
                return
            out_lines = bytes(p.readAllStandardOutput()).decode("utf-8", "ignore").strip().splitlines()
        except Exception:
            return
        urls = [line.strip() for line in out_lines if line.strip().startswith("http://") or line.strip().startswith("https://")]
        url = urls[0] if urls else ""
        if not url:
            if not fallback:
                self.resolve(row, fallback=True)
                return
            self.failed.emit(row, "Fuente de streaming no válida")
            return
        _STREAM_URL_CACHE[vid] = (url, time.time())
        self.resolved.emit(row, url)


