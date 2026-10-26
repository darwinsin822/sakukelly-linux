"""Extracción y procesado de carátulas: portada incrustada en el archivo,
portada en la carpeta, escalado/recorte redondeado y desenfoque ambiental."""
import hashlib
from pathlib import Path
from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QPixmap, QPainter, QPainterPath, QColor, QLinearGradient, QFont, QRadialGradient
from PyQt6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
try:
    from mutagen import File as MF
except Exception:
    MF = None
from sakukelly.config import COVER_CACHE

# Paletas para las portadas genéricas: varias combinaciones "bonitas" en vez
# de un único degradado plano repetido en todas las canciones sin carátula.
_GENERIC_PALETTES = [
    ("#7c5cff", "#33e0ff"), ("#ff6b6b", "#ffb347"), ("#3ddc97", "#9be15d"),
    ("#ff4fd8", "#4facfe"), ("#f7971e", "#ffd200"), ("#8e2de2", "#4a00e0"),
    ("#11998e", "#38ef7d"), ("#ee0979", "#ff6a00"), ("#2193b0", "#6dd5ed"),
    ("#ba5370", "#f4e2d8"),
]

def cover_pixmap(src,size=300,radius=26):
    """Escala cubriendo el cuadro, recorta al centro y redondea las esquinas.
    Sin esto, una imagen de carátula se veía cuadrada asomando por fuera del
    marco de cristal redondeado (QSS no recorta el contenido de un QPixmap)."""
    if src is None or src.isNull():return QPixmap()
    scaled=src.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
    x=max(0,(scaled.width()-size)//2);y=max(0,(scaled.height()-size)//2)
    cropped=scaled.copy(x,y,size,size)
    out=QPixmap(size,size);out.fill(Qt.GlobalColor.transparent)
    painter=QPainter(out);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path=QPainterPath();path.addRoundedRect(QRectF(0,0,size,size),radius,radius)
    painter.setClipPath(path);painter.drawPixmap(0,0,cropped);painter.end()
    return out


def blurred_pixmap(src,radius=80,target_size=None):
    """Difumina una imagen (carátula) para el fondo ambiental estilo Liquid Glass.
    Es un desenfoque 'horneado' en una imagen estática: Qt/QSS no soporta un
    backdrop-filter en vivo, así que este es el equivalente práctico."""
    if src is None or src.isNull():return QPixmap()
    if target_size is not None:
        src=src.scaled(target_size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
    scene=QGraphicsScene();item=QGraphicsPixmapItem(src)
    effect=QGraphicsBlurEffect();effect.setBlurRadius(radius);item.setGraphicsEffect(effect);scene.addItem(item)
    result=QPixmap(src.size());result.fill(Qt.GlobalColor.transparent)
    painter=QPainter(result);scene.render(painter,QRectF(0,0,src.width(),src.height()),QRectF(0,0,src.width(),src.height()));painter.end()
    return result


def embedded_or_folder_cover(path,size=150):
    """Load embedded artwork first; then common cover files beside the song."""
    try:
        key=hashlib.sha1(str(path).encode("utf-8","ignore")).hexdigest()
        cache=COVER_CACHE/(key+".png")
        if cache.exists():
            px=QPixmap(str(cache))
            if not px.isNull():
                return px.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
        data=None;audio=None
        if MF:
            audio=MF(path)
            if audio and getattr(audio,"tags",None):
                for k in audio.tags.keys():
                    tag=audio.tags[k]
                    if str(k).startswith("APIC") and hasattr(tag,"data"):
                        data=tag.data;break
                if data is None and hasattr(audio,"pictures") and audio.pictures:
                    data=audio.pictures[0].data
                if data is None and "covr" in audio.tags:
                    data=bytes(audio.tags["covr"][0])
        if data is None and audio is not None:
            pics=getattr(audio,"pictures",None)
            if pics:data=getattr(pics[0],"data",None)
            tags=getattr(audio,"tags",None)
            if data is None and tags:
                for key in ("covr","metadata_block_picture","coverart"):
                    try:
                        val=tags.get(key)
                        if not val:continue
                        raw=val[0] if isinstance(val,(list,tuple)) else val
                        if key=="covr":data=bytes(raw)
                        elif isinstance(raw,str):
                            import base64
                            decoded=base64.b64decode(raw)
                            if key=="metadata_block_picture":
                                try:
                                    from mutagen.flac import Picture
                                    data=Picture(decoded).data
                                except Exception:data=decoded
                            else:data=decoded
                        elif isinstance(raw,(bytes,bytearray)):data=bytes(raw)
                        if data:break
                    except Exception:pass
        px=QPixmap()
        if data and px.loadFromData(data):
            px.save(str(cache),"PNG")
            return px.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
        folder=Path(path).parent
        for name in ("cover.jpg","cover.jpeg","cover.png","cover.webp","folder.jpg","folder.jpeg","folder.png","front.jpg","front.jpeg","front.png","album.jpg","album.jpeg","album.png","artwork.jpg","artwork.png","AlbumArtSmall.jpg"):
            f=folder/name
            if f.exists():
                px=QPixmap(str(f))
                if not px.isNull():
                    return px.scaled(size,size,Qt.AspectRatioMode.KeepAspectRatioByExpanding,Qt.TransformationMode.SmoothTransformation)
    except Exception:
        pass
    return None


def artwork_for_rows(rows,size=150):
    for row in rows:
        px=embedded_or_folder_cover(row[0],size)
        if px is not None:
            return px
    return None


def gradient_pixmap(size, c1, c2):
    pm=QPixmap(size,size); pm.fill(Qt.GlobalColor.transparent)
    p=QPainter(pm); g=QLinearGradient(0,0,size,size); g.setColorAt(0,QColor(c1)); g.setColorAt(1,QColor(c2))
    p.setBrush(g); p.setPen(Qt.PenStyle.NoPen); p.drawRoundedRect(0,0,size,size,16,16); p.end()
    return pm


def generic_cover_pixmap(seed_text, size=300, radius=26):
    """Portada genérica "bonita" para canciones sin carátula (ni incrustada,
    ni en la carpeta, ni descargable): degradado con brillo radial suave,
    una nota musical y el monograma del título/artista, en vez de un
    cuadro liso o directamente vacío. El color se deriva de forma estable
    de `seed_text` (título+artista) para que cada canción/álbum tenga una
    variante distinta pero siempre la misma entre sesiones."""
    seed=str(seed_text or "?").strip()
    idx=int(hashlib.md5(seed.encode("utf-8","ignore")).hexdigest(),16)%len(_GENERIC_PALETTES)
    c1,c2=_GENERIC_PALETTES[idx]
    pm=QPixmap(size,size); pm.fill(Qt.GlobalColor.transparent)
    p=QPainter(pm); p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path=QPainterPath(); path.addRoundedRect(QRectF(0,0,size,size),radius,radius); p.setClipPath(path)
    g=QLinearGradient(0,0,size,size); g.setColorAt(0,QColor(c1)); g.setColorAt(1,QColor(c2))
    p.fillRect(0,0,size,size,g)
    glow=QRadialGradient(size*0.32,size*0.28,size*0.85)
    glow.setColorAt(0.0,QColor(255,255,255,70)); glow.setColorAt(1.0,QColor(255,255,255,0))
    p.setBrush(glow); p.setPen(Qt.PenStyle.NoPen); p.drawRect(0,0,size,size)
    letter=next((ch for ch in seed.upper() if ch.isalnum()),"♪")
    font=QFont("Inter"); font.setPixelSize(int(size*0.42)); font.setWeight(QFont.Weight.Black)
    p.setFont(font); p.setPen(QColor(255,255,255,235))
    p.drawText(QRectF(0,0,size,size),Qt.AlignmentFlag.AlignCenter,letter)
    note_font=QFont("Inter"); note_font.setPixelSize(int(size*0.16))
    p.setFont(note_font); p.setPen(QColor(255,255,255,160))
    p.drawText(QRectF(size*0.06,size*0.06,size*0.88,size*0.88),
               Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignBottom,"♪")
    p.end()
    return pm


def cache_path_for(path):
    key=hashlib.sha1(str(path).encode("utf-8","ignore")).hexdigest()
    return COVER_CACHE/(key+".png")


def has_cached_cover(path):
    return cache_path_for(path).exists()


def save_generic_cover_to_cache(path, seed_text, size=300):
    """Genera y guarda en la caché de carátulas (misma ubicación que usan
    embedded_or_folder_cover y las descargas automáticas) una portada
    genérica bonita, para que todas las vistas (lista, tarjetas de álbum,
    reproductor) la encuentren igual que si fuera una carátula real, y para
    no reintentar la descarga en cada sesión."""
    try:
        px=generic_cover_pixmap(seed_text,size)
        px.save(str(cache_path_for(path)),"PNG")
        return px
    except Exception:
        return None

