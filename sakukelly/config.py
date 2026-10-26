"""Configuración y constantes compartidas de Sakukelly.

Módulo sin dependencias de Qt más allá de Path, para que cualquier otro
módulo (database, dsp, metadata, streaming, lyrics, services, ui) lo pueda
importar sin arrastrar toda la aplicación.
"""
from pathlib import Path
import re, sys, shutil

IS_WINDOWS = (sys.platform == "win32")

if IS_WINDOWS:
    HOME = Path.home() / "AppData" / "Local" / "sakukelly"
    APP_ICON = str(Path(__file__).parent / "assets" / "sakukelly.svg")
else:
    HOME = Path.home() / ".local/share/sakukelly"
    APP_ICON = "/usr/share/icons/hicolor/scalable/apps/sakukelly.svg"

HOME.mkdir(parents=True, exist_ok=True)

def get_ytdlp_bin():
    if IS_WINDOWS:
        _bin_dir = Path(__file__).parent.parent / "bin"
        _yt_exe = _bin_dir / "yt-dlp.exe"
        return str(_yt_exe) if _yt_exe.exists() else (shutil.which("yt-dlp") or "yt-dlp")
    user_yt = HOME / "bin" / "yt-dlp"
    if user_yt.exists():
        return str(user_yt)
    pkg_yt = Path(__file__).parent / "bin" / "yt-dlp"
    if pkg_yt.exists():
        return str(pkg_yt)
    sys_yt = Path("/usr/lib/sakukelly/bin/yt-dlp")
    if sys_yt.exists():
        return str(sys_yt)
    return shutil.which("yt-dlp") or "/usr/bin/yt-dlp"

def get_ffmpeg_bin():
    if IS_WINDOWS:
        _bin_dir = Path(__file__).parent.parent / "bin"
        _ff_exe = _bin_dir / "ffmpeg.exe"
        return str(_ff_exe) if _ff_exe.exists() else (shutil.which("ffmpeg") or "ffmpeg")
    user_ff = HOME / "bin" / "ffmpeg"
    if user_ff.exists():
        return str(user_ff)
    pkg_ff = Path(__file__).parent / "bin" / "ffmpeg"
    if pkg_ff.exists():
        return str(pkg_ff)
    sys_ff = Path("/usr/lib/sakukelly/bin/ffmpeg")
    if sys_ff.exists():
        return str(sys_ff)
    return shutil.which("ffmpeg") or "/usr/bin/ffmpeg"

YTDLP = get_ytdlp_bin()
FFMPEG = get_ffmpeg_bin()
EXT={".mp3",".flac",".wav",".ogg",".m4a",".aac",".opus",".wma",".ape",".mka"}
SETTINGS_FILE = HOME/"settings.json"
APP_ID = "sakukelly"
APP_NAME = "Sakukelly Music"
APP_VERSION = "6.5.2"
YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")
SINGLE_INSTANCE_KEY = "sakukelly-single-instance-v1"

COVER_CACHE=HOME/"covers"
COVER_CACHE.mkdir(parents=True,exist_ok=True)
AMBIENT_CACHE=HOME/"ambient_bg.png"
LYRICS_CACHE=HOME/"lyrics"
LYRICS_CACHE.mkdir(parents=True,exist_ok=True)
GAPLESS_MS=120  # ventana de traspaso casi instantáneo entre pistas (modo gapless)
REPLAYGAIN_TARGET_LUFS=-14.0  # mismo objetivo que usan Spotify/YouTube Music
MPRIS_ART_CACHE=HOME/"mpris_art.png"
MPRIS_BUS_NAME="org.mpris.MediaPlayer2.sakukelly"
MPRIS_OBJECT_PATH="/org/mpris/MediaPlayer2"
MPRIS_ROOT_IFACE="org.mpris.MediaPlayer2"
MPRIS_PLAYER_IFACE="org.mpris.MediaPlayer2.Player"


THEMES = {
 "noche":  {"deep":"#0d1233","mid":"#1a2050","accent":"#7c5cff","accent2":"#33e0ff","text":"#f2f3fb","dim":"#a9adcf"},
 "sunset": {"deep":"#2b0f2e","mid":"#4a1942","accent":"#ff6b6b","accent2":"#ffb347","text":"#fff3f3","dim":"#d6afc9"},
 "forest": {"deep":"#0b1f19","mid":"#123329","accent":"#3ddc97","accent2":"#9be15d","text":"#effff8","dim":"#9fc8b8"},
 "mono":   {"deep":"#0e0e10","mid":"#1c1c1f","accent":"#e5e5e5","accent2":"#8a8a8a","text":"#f5f5f5","dim":"#a0a0a0"},
 "candy":  {"deep":"#1a0b2e","mid":"#2e1065","accent":"#ff4fd8","accent2":"#4facfe","text":"#fff1fd","dim":"#c4acd9"},
}

