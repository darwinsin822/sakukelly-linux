"""Cliente de la API de ListenBrainz (api.listenbrainz.org).

Igual que services/lastfm.py: sin estado propio de credenciales, sin
dependencia de la ventana principal. El token se pasa en cada llamada.
"""
import json
from PyQt6.QtCore import QUrl
from PyQt6.QtNetwork import QNetworkRequest
from sakukelly.config import APP_NAME, APP_VERSION

LISTENBRAINZ_SUBMIT_URL = "https://api.listenbrainz.org/1/submit-listens"


class ListenBrainzService:
    def __init__(self, network_manager):
        self.net = network_manager

    def track_metadata(self, artist, title, album, dur_s):
        info = {"media_player": APP_NAME, "submission_client": APP_NAME, "submission_client_version": APP_VERSION}
        if dur_s: info["duration_ms"] = int(float(dur_s) * 1000)
        meta = {"artist_name": artist, "track_name": title}
        if album: meta["release_name"] = album
        meta["additional_info"] = info
        return meta

    def _request(self, token, listen_type, payload, on_result=None, sid=None):
        try:
            body = json.dumps({"listen_type": listen_type, "payload": payload}).encode("utf-8")
            req = QNetworkRequest(QUrl(LISTENBRAINZ_SUBMIT_URL))
            req.setHeader(QNetworkRequest.KnownHeaders.ContentTypeHeader, "application/json")
            req.setRawHeader(b"Authorization", ("Token " + token).encode("utf-8"))
            req.setRawHeader(b"User-Agent", f"Mozilla/5.0 Sakukelly/{APP_VERSION} (+scrobbling)".encode())
            rep = self.net.post(req, body)
            def handle(r=rep):
                ok = False
                try:
                    status = r.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
                    ok = bool(status) and 200 <= int(status) < 300
                except Exception:
                    ok = False
                if on_result: on_result(sid, ok)
                r.deleteLater()
            rep.finished.connect(handle)
        except Exception:
            if on_result: on_result(sid, False)

    def now_playing(self, token, artist, title, album, duration_s):
        self._request(token, "playing_now", [{"track_metadata": self.track_metadata(artist, title, album, duration_s)}])

    def submit_scrobble(self, token, sid, artist, title, album, dur, ts, on_result):
        """on_result(sid, ok:bool) se llama siempre, tanto en éxito como en fallo."""
        payload = [{"listened_at": int(ts), "track_metadata": self.track_metadata(artist, title, album, dur)}]
        self._request(token, "single", payload, on_result=on_result, sid=sid)
