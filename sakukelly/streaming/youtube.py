"""Helpers de YouTube que no dependen de Qt: resolución de miniaturas."""
from sakukelly.config import YT_ID_RE

def youtube_thumb_url(video_id):
    """URL de miniatura estable de YouTube a partir del id de vídeo.

    yt-dlp con --flat-playlist no siempre entrega un campo "thumbnail" plano
    (a veces solo entrega "thumbnails", una lista, o nada). Esta URL de
    i.ytimg.com funciona para prácticamente cualquier vídeo público sin
    depender de esos datos, así que sirve como respaldo fiable para que el
    streaming siempre tenga portada, igual que la música local.
    """
    vid = str(video_id or "").strip()
    if not YT_ID_RE.match(vid):
        return ""
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def resolve_thumb(entry, video_id=None):
    """Devuelve la mejor URL de portada disponible para un resultado de YouTube."""
    thumb = str((entry or {}).get("thumbnail") or "") if isinstance(entry, dict) else str(entry or "")
    if thumb.startswith("http"):
        return thumb
    if isinstance(entry, dict):
        thumbs = entry.get("thumbnails") or []
        if isinstance(thumbs, list) and thumbs:
            last = thumbs[-1]
            if isinstance(last, dict) and str(last.get("url") or "").startswith("http"):
                return str(last["url"])
    vid = video_id if video_id else ((entry or {}).get("id") if isinstance(entry, dict) else None)
    return youtube_thumb_url(vid)

