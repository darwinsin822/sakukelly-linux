"""Cliente de la API de Last.fm (ws.audioscrobbler.com).

Este módulo no conoce nada de la ventana principal ni de Qt Widgets: solo
sabe firmar peticiones, llamarlas por HTTP y parsear la respuesta. Las
credenciales (api_key, secret, session key) se pasan explícitamente en cada
llamada — quien las posea (la ventana principal, hoy) sigue siendo la única
fuente de verdad, evitando tener el mismo dato duplicado en dos sitios.
"""
import hashlib, json
from PyQt6.QtCore import QUrl, QUrlQuery
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtNetwork import QNetworkRequest
from sakukelly.config import APP_VERSION

LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"


class LastFmService:
    def __init__(self, network_manager):
        self.net = network_manager

    # ---- Bajo nivel: firma y llamada HTTP --------------------------------
    def sign(self, params, secret):
        items = sorted((k, v) for k, v in params.items() if k not in ("format", "callback"))
        raw = "".join(f"{k}{v}" for k, v in items) + secret
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def call(self, key, secret, method, params, http_method="GET", on_done=None):
        p = dict(params); p["method"] = method; p["api_key"] = key
        p["api_sig"] = self.sign(p, secret); p["format"] = "json"
        req = QNetworkRequest(); req.setRawHeader(b"User-Agent", f"Mozilla/5.0 Sakukelly/{APP_VERSION}".encode())
        if http_method == "POST":
            req.setUrl(QUrl(LASTFM_API_URL))
            req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/x-www-form-urlencoded")
            q = QUrlQuery()
            for k, v in p.items(): q.addQueryItem(k, str(v))
            data = q.toString(QUrl.ComponentFormattingOption.FullyEncoded).encode("utf-8")
            rep = self.net.post(req, data)
        else:
            url = QUrl(LASTFM_API_URL); q = QUrlQuery()
            for k, v in p.items(): q.addQueryItem(k, str(v))
            url.setQuery(q); req.setUrl(url)
            rep = self.net.get(req)
        if on_done: rep.finished.connect(lambda r=rep: on_done(r))
        return rep

    # ---- Scrobbling --------------------------------------------------------
    def now_playing(self, key, secret, session, meta):
        params = {"artist": meta["artist"], "track": meta["title"], "sk": session}
        if meta.get("album"): params["album"] = meta["album"]
        if meta.get("duration_s"): params["duration"] = int(meta["duration_s"])
        self.call(key, secret, "track.updateNowPlaying", params, http_method="POST")

    def submit_scrobble(self, key, secret, session, sid, artist, title, album, dur, ts, on_result):
        """on_result(sid, ok:bool) se llama siempre, tanto en éxito como en fallo."""
        params = {"artist": artist, "track": title, "timestamp": int(ts), "sk": session}
        if album: params["album"] = album
        if dur: params["duration"] = int(dur)
        def handle(rep):
            try:
                data = json.loads(bytes(rep.readAll()).decode("utf-8", "ignore"))
                ok = "scrobbles" in data
            except Exception:
                ok = False
            on_result(sid, ok)
            rep.deleteLater()
        self.call(key, secret, "track.scrobble", params, http_method="POST", on_done=handle)

    # ---- Autenticación (flujo de token web) --------------------------------
    def start_auth(self, key, secret, on_token, on_error):
        """Pide un token, abre el navegador para que el usuario autorice la
        app, y entrega el token pendiente vía on_token(token) para guardarlo
        y usarlo luego en finish_auth."""
        if not key or not secret:
            on_error("Ingresa tu API key y secret de Last.fm primero")
            return
        def handle(rep):
            try:
                data = json.loads(bytes(rep.readAll()).decode("utf-8", "ignore"))
                token = data.get("token")
                if not token: raise ValueError("sin token")
                QDesktopServices.openUrl(QUrl(f"https://www.last.fm/api/auth/?api_key={key}&token={token}"))
                on_token(token)
            except Exception:
                on_error("No se pudo iniciar la conexión con Last.fm — revisa la API key/secret")
            rep.deleteLater()
        self.call(key, secret, "auth.getToken", {}, on_done=handle)

    def finish_auth(self, key, secret, token, on_session, on_error):
        def handle(rep):
            try:
                data = json.loads(bytes(rep.readAll()).decode("utf-8", "ignore"))
                session_key = data.get("session", {}).get("key")
                if not session_key: raise ValueError("sin session key")
                on_session(session_key)
            except Exception:
                on_error("Todavía no autorizaste en el navegador, o el enlace expiró")
            rep.deleteLater()
        self.call(key, secret, "auth.getSession", {"token": token}, on_done=handle)
