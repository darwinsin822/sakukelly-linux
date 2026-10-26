"""Parseo y localización de letras: formato LRC, letras incrustadas en
etiquetas del propio archivo, y limpieza de consultas de búsqueda a partir
de títulos "sucios" de vídeos de streaming."""
import re, hashlib
try:
    from mutagen import File as MF
except Exception:
    MF = None

def parse_lrc(text):
    """Convierte texto en formato LRC ('[mm:ss.xx]texto por línea') en una
    lista ordenada de tuplas (segundos:float, texto). Soporta el tag
    [offset:+/-N] y calcula fracciones precisas de milisegundos."""
    if not text: return []
    offset_ms = 0
    off_m = re.search(r"\[offset:\s*([+-]?\d+)\s*\]", text, re.I)
    if off_m:
        try: offset_ms = int(off_m.group(1))
        except Exception: offset_ms = 0
    offset_sec = offset_ms / 1000.0

    tag_re = re.compile(r"\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]")
    out = []
    for line in text.splitlines():
        if line.strip().lower().startswith("[offset:"): continue
        tags = list(tag_re.finditer(line))
        if not tags: continue
        content = tag_re.sub("", line).strip()
        for m in tags:
            mm = int(m.group(1)); ss = int(m.group(2)); frac = m.group(3) or "0"
            if len(frac) == 1:
                frac_val = int(frac) / 10.0
            elif len(frac) == 2:
                frac_val = int(frac) / 100.0
            else:
                frac_val = int(frac) / (10 ** len(frac))
            ts = mm * 60.0 + ss + frac_val + offset_sec
            out.append((max(0.0, ts), content if content else "♪"))
    out.sort(key=lambda x: x[0])
    return out


def embedded_synced_lyrics(path):
    """Busca letras sincronizadas incrustadas en las etiquetas del propio
    archivo: marco SYLT de ID3 (MP3) o comentarios tipo Vorbis en FLAC/OGG.
    Devuelve texto en formato LRC, o None si no hay nada usable."""
    if MF is None:return None
    try:
        f=MF(path);tags=getattr(f,"tags",None) if f else None
        if tags is None:return None
        getall=getattr(tags,"getall",None)
        if getall:
            for frame in getall("SYLT"):
                if getattr(frame,"format",2)==2 and getattr(frame,"text",None):
                    out=[]
                    for txt,ts in frame.text:
                        secs=ts/1000.0;mm=int(secs//60);ss=secs-mm*60
                        out.append(f"[{mm:02d}:{ss:05.2f}]{txt}")
                    if out:return "\n".join(out)
        for key in ("SYNCEDLYRICS","LYRICS","LRC","UNSYNCEDLYRICS"):
            try:
                if key in tags:
                    val=tags[key];val=val[0] if isinstance(val,list) else val;val=str(val)
                    if "[" in val and ":" in val:return val
            except Exception:continue
    except Exception:pass
    return None


def lyrics_cache_key(artist,title):
    raw=f"{(artist or '').strip().lower()}::{(title or '').strip().lower()}"
    return hashlib.md5(raw.encode("utf-8","ignore")).hexdigest()


def clean_lyrics_query(title,artist):
    """A partir del título "crudo" de un vídeo de streaming (a menudo con ruido
    tipo "(Video Oficial) | Sello") y su canal, deduce una lista de pares
    (artista, título) candidatos para buscar letras, del más preciso al más
    permisivo. No modifica los datos originales que se muestran en la
    interfaz: solo se usa como entrada para la búsqueda de letras."""
    raw_title=str(title or "").strip();raw_artist=str(artist or "").strip()
    if not raw_title and not raw_artist:return []

    # Limpiar canal de YouTube (ej. "TaylorSwiftVEVO" -> "Taylor Swift", "Ed Sheeran - Topic" -> "Ed Sheeran")
    clean_artist=re.sub(r"(?i)\s*(?:VEVO|\bTopic\b|-?\s*Topic|\bOfficial\b)\s*$", "", raw_artist).strip()
    if clean_artist and re.match(r"^[A-Z][a-z]+([A-Z][a-z]+)+$", clean_artist):
        clean_artist=re.sub(r"([a-z])([A-Z])", r"\1 \2", clean_artist)

    def strip_noise(s):
        s=re.sub(r"\(feat\.?[^)]*\)"," ",s,flags=re.I)
        s=re.sub(r"\[[^\]]*\]"," ",s)
        s=re.sub(r"\([^)]*\)"," ",s)
        s=re.sub(r"\{[^}]*\}"," ",s)
        s=re.sub(r"(?i)\b(video\s*oficial|audio\s*oficial|official\s*(music\s*)?video|official\s*audio|lyrics?\s*video|lyric\s*video|video\s*l[ií]rico|letra(?:s)?|lyrics?|visualizer|remaster(?:ed|izado)?|en\s*vivo|live|hd|4k|8k|full\s*hd)\b"," ",s)
        s=re.sub(r"\s*[|•·].*$","",s)  # corta lo que venga tras separador de canal/sello
        s=re.sub(r"\s{2,}"," ",s).strip(" -–—:")
        return s.strip()

    working=strip_noise(raw_title)
    parsed_artist=parsed_title=""
    m=re.match(r"^\s*(.+?)\s*[-–—]\s*(.+?)\s*$",working)
    if m:parsed_artist,parsed_title=m.group(1).strip(),m.group(2).strip()

    candidates=[]
    if parsed_artist and parsed_title:
        candidates.append((parsed_artist,parsed_title))
    if working and clean_artist:
        candidates.append((clean_artist,working))
    if working and raw_artist and raw_artist!=clean_artist:
        candidates.append((raw_artist,working))
    if working:
        candidates.append(("",working))
    if clean_artist or raw_title:
        candidates.append((clean_artist or raw_artist,working or raw_title))

    seen=set();out=[]
    for a,t in candidates:
        key=(a.strip().lower(),t.strip().lower())
        if t.strip() and key not in seen:
            seen.add(key);out.append((a,t))
    return out

