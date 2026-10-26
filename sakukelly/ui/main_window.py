"""Ventana principal de Sakukelly: SettingsDialog, Win (QMainWindow) y
VideoPlayer.

Esta es, por ahora, una reubicacion literal del antiguo app.py monolitico
(fase de reorganizacion pura, sin tocar una sola linea de logica interna).
El motor de reproduccion (QMediaPlayer, crossfade, cola) sigue viviendo
dentro de Win: separarlo de verdad en core/playback_engine.py y
core/queue.py queda pendiente para una fase futura, cuando se pueda
verificar interactivamente (crossfade, drag&drop) en una maquina real.
"""
#!/usr/bin/env python3
import os, json, time, hashlib, subprocess, re
from pathlib import Path
from PyQt6.QtCore import Qt, QUrl, QUrlQuery, QSize, QProcess, QTimer, QPropertyAnimation, QEasingCurve, QItemSelectionModel
from PyQt6.QtGui import QDesktopServices, QPixmap, QColor, QPainter, QIcon
from PyQt6.QtMultimedia import QAudioOutput, QMediaPlayer
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWidgets import *

try:
    from mutagen import File as MF
except Exception:
    MF = None

try:
    import dbus, dbus.service
    DBUS_AVAILABLE=True
except Exception:
    DBUS_AVAILABLE=False

from sakukelly.config import (EXT, SETTINGS_FILE, APP_NAME, APP_VERSION, APP_ICON,
    YTDLP, FFMPEG, YT_ID_RE, COVER_CACHE, AMBIENT_CACHE, LYRICS_CACHE,
    GAPLESS_MS, REPLAYGAIN_TARGET_LUFS, MPRIS_ART_CACHE, MPRIS_BUS_NAME,
    MPRIS_PLAYER_IFACE, THEMES)
from sakukelly.database.database import DB, folder_rows, child_folders
from sakukelly.dsp.audio_backend import DSPBackend
from sakukelly.metadata.artwork import (cover_pixmap, blurred_pixmap, embedded_or_folder_cover, artwork_for_rows,
    gradient_pixmap, generic_cover_pixmap, has_cached_cover, save_generic_cover_to_cache)
from sakukelly.streaming.youtube import resolve_thumb
from sakukelly.lyrics.lyrics import parse_lrc, embedded_synced_lyrics, lyrics_cache_key, clean_lyrics_query
from sakukelly.services.mpris import MPRISService
from sakukelly.ui.widgets import KaraokeLabel, WaveformWidget, TrackListWidget, DropPlayerFrame, PowerampPlayButton, hex_to_rgb, glass_shadow
from sakukelly.ui.icons import get_icon, render_icon_pixmap
from sakukelly.services.lastfm import LastFmService
from sakukelly.services.listenbrainz import ListenBrainzService
from sakukelly.streaming.resolver import YouTubeSearcher, YouTubeStreamResolver
from sakukelly.streaming.downloader import YouTubeDownloader
from sakukelly.core.queue import next_index, prev_index



from sakukelly.ui.settings_dialog import SettingsDialog
from sakukelly.ui.video_player import VideoPlayer


class Win(QMainWindow):
    def __init__(self):
        super().__init__(); self.d=DB(); self.rows=[]; self.i=-1; self.queue=[]; self.view="Inicio"; self.filter=None
        self.shuffle=False; self.repeat=False; self.currentFolder=None; self.theme="noche"
        self.stream_rows=[]; self.stream_current=None; self.local_current=None; self.video_player=None; self.hybrid_process=None; self.hybrid_token=0; self.net=QNetworkAccessManager(self)
        self.lastfm_service=LastFmService(self.net)
        self.lb_service=ListenBrainzService(self.net)
        # ---- Streaming: busqueda, resolucion de URL y descarga -------------
        # La orquestacion de QProcess/yt-dlp vive en sakukelly/streaming/;
        # aqui solo se conectan las senales a los slots que actualizan la UI.
        self.youtube_searcher=YouTubeSearcher(self)
        self.youtube_searcher.resultsReady.connect(self._on_youtube_results)
        self.youtube_searcher.searchFailed.connect(self._on_youtube_search_failed)
        self.youtube_resolver=YouTubeStreamResolver(self)
        self.youtube_resolver.resolved.connect(self._on_stream_resolved)
        self.youtube_resolver.failed.connect(self._on_stream_resolve_failed)
        self.youtube_downloader=YouTubeDownloader(self)
        self.youtube_downloader.progress.connect(lambda msg:self.statusBar().showMessage(msg,2500))
        self.youtube_downloader.finishedOk.connect(self._on_download_finished)
        self.youtube_downloader.failed.connect(lambda:self.statusBar().showMessage("La descarga no pudo completarse",7000))
        self.stream_search_timer=QTimer(self); self.stream_search_timer.setSingleShot(True); self.stream_search_timer.setInterval(380); self.stream_search_timer.timeout.connect(self.search_youtube)
        self.deezer_timer=QTimer(self);self.deezer_timer.setSingleShot(True);self.deezer_timer.setInterval(800);self.deezer_timer.timeout.connect(self.search_deezer)
        self.load_settings()
        self.dsp=DSPBackend()
        self.setWindowTitle(APP_NAME); self.setWindowIcon(QIcon(APP_ICON)); self.resize(1450,880); self.setMinimumSize(900,560)
        self.au=QAudioOutput(); self.au.setVolume(.78); self.base_volume=.78; self.p=QMediaPlayer(); self.p.setAudioOutput(self.au)
        self._gain_mult=1.0; self._gain_mult2=1.0
        # Reproductor de sombra: solo se usa para solapar audio durante un crossfade real.
        self.au2=QAudioOutput(); self.au2.setVolume(0.0); self.p2=QMediaPlayer(); self.p2.setAudioOutput(self.au2)
        self.crossfade_started=False; self.fadeTimer=QTimer(self); self.fadeTimer.setInterval(40); self.fadeTimer.timeout.connect(self._fade_step); self.fadeStart=0
        self._pending_next=None

        base=QWidget(); base.setObjectName("base"); self.setCentralWidget(base); outer=QVBoxLayout(base); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)

        # Topbar del mockup
        top=QFrame(); top.setObjectName("topbar"); top.setFixedHeight(66); th=QHBoxLayout(top); th.setContentsMargins(18,8,24,8)
        self.topbarFrame=top
        topBrand=QLabel("♪  Sakukelly Music"); topBrand.setObjectName("topBrand"); topBrand.setMinimumWidth(255); th.addWidget(topBrand)
        th.addStretch()
        self.search=QLineEdit(); self.search.setObjectName("search"); self.search.setPlaceholderText("⌕  ¿Qué quieres reproducir?"); self.search.setMaximumWidth(450); self.search.setMinimumWidth(320)
        self.search.textChanged.connect(self.search_changed); self.search.returnPressed.connect(self.search_youtube); th.addWidget(self.search,1); th.addStretch()
        cfg=QPushButton("⚙"); cfg.setObjectName("circle"); cfg.clicked.connect(self.settings); th.addWidget(cfg)
        self.avatar=QLabel("D"); self.avatar.setObjectName("avatar"); self.avatar.setAlignment(Qt.AlignmentFlag.AlignCenter); self.avatar.setFixedSize(40,40); th.addWidget(self.avatar)
        outer.addWidget(top)

        body=QHBoxLayout(); body.setSpacing(0); outer.addLayout(body,1)

        # Biblioteca lateral, como el mockup
        side=QFrame(); side.setObjectName("sidebar"); side.setFixedWidth(190); sv=QVBoxLayout(side); sv.setContentsMargins(12,16,10,14); sv.setSpacing(5)
        self.sidebarFrame=side
        glass_shadow(side,blur=46,dx=6,dy=0,alpha=110)
        lib=QLabel("TU BIBLIOTECA"); lib.setObjectName("eyebrow"); sv.addWidget(lib)
        for icon,n in [("⌂","Inicio"),("◉","Streaming"),("🎵","Spotify"),("⇩","Offline"),("♥","Favoritos"),("♫","Canciones"),("▤","Carpetas"),("▣","Álbumes"),("♟","Artistas"),("≡","Géneros"),("◫","Playlists")]:
            b=QPushButton(f"{icon}   {n}"); b.setObjectName("nav"); b.clicked.connect(lambda _,x=n:self.nav(x)); sv.addWidget(b)
        sv.addStretch(1)
        add=QPushButton("＋ Añadir música"); add.setObjectName("primary"); add.clicked.connect(self.folder); sv.addWidget(add)
        body.addWidget(side)

        # Contenido central
        main=QWidget(); mv=QVBoxLayout(main); mv.setContentsMargins(20,16,18,12); mv.setSpacing(10)
        self.heading=QLabel("Elegidos para ti"); self.heading.setObjectName("heading"); mv.addWidget(self.heading)
        self.hero=QFrame(); self.hero.setObjectName("hero"); hh=QHBoxLayout(self.hero)
        glass_shadow(self.hero,blur=34,dx=0,dy=10,alpha=95)
        self.folderText=QLabel("Tu música, tu pasión."); self.folderText.setObjectName("heroText"); hh.addWidget(self.folderText,1)
        rs=QPushButton("↻ Reescanear"); rs.clicked.connect(self.rescan); hh.addWidget(rs); mv.addWidget(self.hero)

        self.cards=QListWidget(); self.cards.setObjectName("cards"); self.cards.setViewMode(QListView.ViewMode.IconMode); self.cards.setResizeMode(QListView.ResizeMode.Adjust)
        self.cards.setMovement(QListView.Movement.Static); self.cards.setIconSize(QSize(150,150)); self.cards.setGridSize(QSize(174,202)); self.cards.setMinimumHeight(215); self.cards.setMaximumHeight(228); self.cards.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.cards.itemClicked.connect(self.card_activate);mv.addWidget(self.cards)

        self.section=QLabel("Descubre"); self.section.setObjectName("sectionTitle"); mv.addWidget(self.section)
        self.list=TrackListWidget(); self.list.setObjectName("tracks"); self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection); self.list.itemClicked.connect(self._list_item_clicked); self.list.setDragEnabled(True)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.list.customContextMenuRequested.connect(self.menu)
        self.list.model().rowsMoved.connect(self.queue_reordered); mv.addWidget(self.list,1)

        # Panel de letras sincronizadas (estilo Apple Music): ocupa el mismo
        # espacio que la lista de canciones, alternando visibilidad con ella.
        self.lyricsPanel=QWidget();self.lyricsPanel.setObjectName("lyricsPanel");self.lyricsPanel.hide()
        lv=QVBoxLayout(self.lyricsPanel);lv.setContentsMargins(0,0,0,0);lv.setSpacing(6)
        
        lyricsHeader=QHBoxLayout()
        badge=QLabel("LETRAS · KARAOKE");badge.setObjectName("lyricsBadge");lyricsHeader.addWidget(badge)
        lyricsHeader.addStretch()
        
        self.lyrics_offset = getattr(self, "lyrics_offset", 0.0)
        offBox=QHBoxLayout();offBox.setSpacing(3)
        btnM5=QPushButton("-0.5s");btnM5.setToolTip("Adelantar letra 0.5s");btnM5.clicked.connect(lambda:self._adjust_lyrics_offset(-0.5))
        btnM1=QPushButton("-0.1s");btnM1.setToolTip("Adelantar letra 0.1s");btnM1.clicked.connect(lambda:self._adjust_lyrics_offset(-0.1))
        
        sign = "+" if self.lyrics_offset > 0 else ""
        self.offset_label=QLabel(f"Sync: {sign}{self.lyrics_offset:.1f}s")
        self.offset_label.setStyleSheet("font-size:11px;font-weight:700;color:rgba(255,255,255,0.7);padding:0 4px;")
        
        btnP1=QPushButton("+0.1s");btnP1.setToolTip("Retrasar letra 0.1s");btnP1.clicked.connect(lambda:self._adjust_lyrics_offset(0.1))
        btnP5=QPushButton("+0.5s");btnP5.setToolTip("Retrasar letra 0.5s");btnP5.clicked.connect(lambda:self._adjust_lyrics_offset(0.5))
        btnRst=QPushButton("↺");btnRst.setToolTip("Restablecer a 0.0s");btnRst.clicked.connect(self._reset_lyrics_offset)
        
        for b in (btnM5, btnM1, btnP1, btnP5, btnRst):
            b.setStyleSheet("font-size:11px;padding:3px 6px;border-radius:6px;background:rgba(255,255,255,0.08);")
        
        offBox.addWidget(btnM5);offBox.addWidget(btnM1);offBox.addWidget(self.offset_label);offBox.addWidget(btnP1);offBox.addWidget(btnP5);offBox.addWidget(btnRst)
        lyricsHeader.addLayout(offBox)
        lv.addLayout(lyricsHeader)
        self.lyricsScroll=QScrollArea();self.lyricsScroll.setObjectName("lyricsScroll");self.lyricsScroll.setWidgetResizable(True)
        self.lyricsScroll.setFrameShape(QFrame.Shape.NoFrame);self.lyricsScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        lyricsInner=QWidget();lyricsInner.setObjectName("lyricsInner")
        self.lyricsLayout=QVBoxLayout(lyricsInner);self.lyricsLayout.setContentsMargins(24,40,24,260);self.lyricsLayout.setSpacing(18)
        self.lyricsLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.lyricsScroll.setWidget(lyricsInner);lv.addWidget(self.lyricsScroll,1)
        self.lyricsEmpty=QLabel("");self.lyricsEmpty.setObjectName("lyricsEmpty");self.lyricsEmpty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lyricsEmpty.setWordWrap(True);self.lyricsEmpty.hide();lv.addWidget(self.lyricsEmpty,1)
        self._lyrics_labels=[];self._lyrics_lines=[];self._lyrics_synced=False;self._lyrics_current_idx=-1;self._lyrics_token=0
        mv.addWidget(self.lyricsPanel,1)
        body.addWidget(main,1)

        # ---- Panel Spotify (se instala en el contenido central) ----
        # Se crea una sola vez aquí y se muestra/oculta con nav("Spotify").
        self._build_spotify_panel(mv)

        # Player principal derecho: siempre visible, sin ocupar el borde inferior.
        player=DropPlayerFrame(); player.setObjectName("player"); player.setFixedWidth(340); player.dropped.connect(self.player_drop)
        self.playerFrame=player
        glass_shadow(player,blur=52,dx=-6,dy=0,alpha=140)
        ph=QVBoxLayout(player); ph.setContentsMargins(16,18,16,16); ph.setSpacing(10)
        pt=QLabel("AHORA SUENA");pt.setObjectName("eyebrow");ph.addWidget(pt)
        self.cover=QLabel("♪"); self.cover.setObjectName("cover"); self.cover.setFixedSize(300,300)
        self.cover.setAlignment(Qt.AlignmentFlag.AlignCenter); ph.addWidget(self.cover,0,Qt.AlignmentFlag.AlignHCenter)
        self.wave=WaveformWidget(self);ph.addWidget(self.wave)
        self.now=QLabel("Nada reproduciéndose\nBiblioteca local"); self.now.setObjectName("now")
        self.now.setWordWrap(True);self.now.setAlignment(Qt.AlignmentFlag.AlignCenter);ph.addWidget(self.now)
        actions=QHBoxLayout();actions.setSpacing(12);actions.addStretch()
        self.favBtn=QPushButton();self.favBtn.setObjectName("actionBtn");self.favBtn.setIconSize(QSize(20,20));self.favBtn.setToolTip("Favorito");self.favBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.favBtn.clicked.connect(self.favorite);actions.addWidget(self.favBtn)
        self.dlBtn=QPushButton();self.dlBtn.setObjectName("actionBtn");self.dlBtn.setIconSize(QSize(20,20));self.dlBtn.setToolTip("Descargar contenido autorizado");self.dlBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.dlBtn.clicked.connect(self.download_current_stream);actions.addWidget(self.dlBtn)
        self.miniBtn=QPushButton();self.miniBtn.setObjectName("actionBtn");self.miniBtn.setIconSize(QSize(20,20));self.miniBtn.setToolTip("Abrir mini-player");self.miniBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.miniBtn.clicked.connect(self.open_video_player);actions.addWidget(self.miniBtn)
        self.ytBtn=QPushButton();self.ytBtn.setObjectName("actionBtn");self.ytBtn.setIconSize(QSize(20,20));self.ytBtn.setToolTip("Ver vídeo en YouTube");self.ytBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.ytBtn.clicked.connect(self.open_current_on_youtube);actions.addWidget(self.ytBtn)
        self.lyricsBtn=QPushButton();self.lyricsBtn.setObjectName("actionBtn");self.lyricsBtn.setCheckable(True);self.lyricsBtn.setIconSize(QSize(20,20));self.lyricsBtn.setToolTip("Letras sincronizadas");self.lyricsBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.lyricsBtn.toggled.connect(self.toggle_lyrics);actions.addWidget(self.lyricsBtn)
        actions.addStretch();ph.addLayout(actions)
        buttons=QHBoxLayout();buttons.setSpacing(14);buttons.addStretch()
        self.shuffleBtn=QPushButton();self.shuffleBtn.setObjectName("playerToggleBtn");self.shuffleBtn.setIconSize(QSize(19,19));self.shuffleBtn.setCheckable(True);self.shuffleBtn.setToolTip("Aleatorio");self.shuffleBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.shuffleBtn.toggled.connect(self._set_shuffle);buttons.addWidget(self.shuffleBtn)
        self.prevBtn=QPushButton();self.prevBtn.setObjectName("playerNavBtn");self.prevBtn.setIconSize(QSize(22,22));self.prevBtn.setToolTip("Anterior");self.prevBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.prevBtn.clicked.connect(self.prev);buttons.addWidget(self.prevBtn)
        self.play=PowerampPlayButton();self.play.setObjectName("play");self.play.setToolTip("Reproducir / pausar");self.play.clicked.connect(self.toggle);buttons.addWidget(self.play)
        self.nextBtn=QPushButton();self.nextBtn.setObjectName("playerNavBtn");self.nextBtn.setIconSize(QSize(22,22));self.nextBtn.setToolTip("Siguiente");self.nextBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.nextBtn.clicked.connect(self.next);buttons.addWidget(self.nextBtn)
        self.repeatBtn=QPushButton();self.repeatBtn.setObjectName("playerToggleBtn");self.repeatBtn.setIconSize(QSize(19,19));self.repeatBtn.setCheckable(True);self.repeatBtn.setToolTip("Repetir");self.repeatBtn.setCursor(Qt.CursorShape.PointingHandCursor);self.repeatBtn.toggled.connect(self._set_repeat);buttons.addWidget(self.repeatBtn)
        buttons.addStretch();ph.addLayout(buttons)
        timeline=QHBoxLayout();self.tm=QLabel("0:00");timeline.addWidget(self.tm)
        self.sl=QSlider(Qt.Orientation.Horizontal);self.sl.setCursor(Qt.CursorShape.PointingHandCursor);self.sl.sliderMoved.connect(self.p.setPosition);timeline.addWidget(self.sl,1)
        self.tt=QLabel("0:00");timeline.addWidget(self.tt);ph.addLayout(timeline)
        ph.addStretch(1)
        body.addWidget(player)

        self.p.positionChanged.connect(self.pos); self.p.durationChanged.connect(self.sl.setMaximum); self.p.mediaStatusChanged.connect(self.end)
        self.p.sourceChanged.connect(lambda _u:QTimer.singleShot(0,self._on_track_settled))
        self.p.errorOccurred.connect(self._on_player_error)
        self.p.playbackStateChanged.connect(lambda s:(self._update_play_icon(s),self._mpris_update()))
        self._really_quit=True
        self._setup_mpris()
        self.tray=None
        self._scrobbleFlushTimer=QTimer(self); self._scrobbleFlushTimer.setInterval(90000); self._scrobbleFlushTimer.timeout.connect(self.flush_scrobble_queue); self._scrobbleFlushTimer.start()
        self._lyrics_timer=QTimer(self); self._lyrics_timer.setInterval(33); self._lyrics_timer.timeout.connect(self._tick_lyrics_smooth); self._lyrics_timer.start()
        self.apply_theme(self.theme, save=False); self.reload_playlists(); self.nav("Inicio"); QTimer.singleShot(350,self.restore_session)
        # Barrido automático de carátulas faltantes en segundo plano, unos
        # segundos después de abrir, para no competir con el arranque.
        QTimer.singleShot(6000,self.start_cover_backfill)

    def label(self,t):
        x=QLabel(t); x.setObjectName("eyebrow"); return x

    def load_settings(self):
        try:
            data=json.loads(SETTINGS_FILE.read_text())
            self.theme=data.get("theme","noche")
            self.eq_values=data.get("eq",[0,0,0,0,0,0,0,0]); self.wallpaper=data.get("wallpaper",""); self.crossfade=data.get("crossfade",True); self.crossfade_ms=int(data.get("crossfade_ms",4000)); self.gapless=data.get("gapless",False)
            self.replaygain=data.get("replaygain",False)
            self.mpris_enabled=data.get("mpris_enabled",True); self.tray_enabled=data.get("tray_enabled",False)
            self.lb_token=data.get("listenbrainz_token",""); self.lb_enabled=data.get("listenbrainz_enabled",False)
            self.lastfm_key=data.get("lastfm_api_key",""); self.lastfm_secret=data.get("lastfm_api_secret",""); self.lastfm_session=data.get("lastfm_session_key",""); self.lastfm_enabled=data.get("lastfm_enabled",False)
        except Exception:
            self.theme="noche"; self.eq_values=[0,0,0,0,0,0,0,0]; self.wallpaper=""; self.crossfade=True; self.crossfade_ms=4000; self.gapless=False
            self.replaygain=False; self.mpris_enabled=True; self.tray_enabled=False
            self.lb_token="";self.lb_enabled=False;self.lastfm_key="";self.lastfm_secret="";self.lastfm_session="";self.lastfm_enabled=False
    def save_settings(self):
        try:
            old={}
            if SETTINGS_FILE.exists():
                try:old=json.loads(SETTINGS_FILE.read_text())
                except Exception:old={}
            old.update({"theme":self.theme,"eq":self.eq_values,"wallpaper":self.wallpaper,"crossfade":self.crossfade,"crossfade_ms":self.crossfade_ms,"gapless":self.gapless,
                "replaygain":self.replaygain,"mpris_enabled":self.mpris_enabled,"tray_enabled":self.tray_enabled,
                "listenbrainz_token":self.lb_token,"listenbrainz_enabled":self.lb_enabled,
                "lastfm_api_key":self.lastfm_key,"lastfm_api_secret":self.lastfm_secret,"lastfm_session_key":self.lastfm_session,"lastfm_enabled":self.lastfm_enabled})
            SETTINGS_FILE.write_text(json.dumps(old))
        except Exception: pass
    def set_equalizer(self,values):
        self.eq_values=list(values); self.save_settings()
        ok,msg=self.dsp.apply(self.eq_values)
        if ok:
            # QtMultimedia crea su stream dinámicamente. Se mueve el stream de Sakukelly
            # al sink DSP cuando aparece; se repite unos instantes para cubrir play/pause.
            self.route_timer=QTimer(self); self.route_timer.timeout.connect(self.route_to_dsp)
            self.route_timer.start(350); QTimer.singleShot(3500,self.route_timer.stop)
            self.route_to_dsp()
        return ok,msg
    def route_to_dsp(self):
        if not self.dsp.available or not self.dsp.module_id:return
        try:
            r=subprocess.run(["pactl","list","sink-inputs"],capture_output=True,text=True,timeout=3).stdout
            blocks=r.split("Sink Input #")[1:]
            for b in blocks:
                first=b.splitlines()[0].strip()
                low=b.lower()
                if "sakukell" in low or "python" in low or "qt" in low:
                    subprocess.run(["pactl","move-sink-input",first,self.dsp.sink_name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        except Exception:pass

    def apply_theme(self,name,save=True):
        self.theme=name if name in THEMES else "noche"; t=THEMES[self.theme]
        ar,ag,ab=hex_to_rgb(t['accent']); a2r,a2g,a2b=hex_to_rgb(t['accent2'])
        self.setStyleSheet(f"""
        QWidget#base{{background:qradialgradient(cx:.5,cy:-.05,radius:1.15,fx:.5,fy:-.05,stop:0 {t['mid']},stop:.55 {t['deep']},stop:1 {t['deep']});color:{t['text']};font-family:'Inter','SF Pro Display','Segoe UI Variable','Segoe UI',-apple-system,'Ubuntu','Cantarell','Noto Sans',sans-serif;font-size:14px}}
        QWidget{{color:{t['text']};selection-background-color:rgba({ar},{ag},{ab},.55)}}
        QToolTip{{background:rgba(9,11,24,.97);color:{t['text']};border:1px solid rgba(255,255,255,.16);border-radius:9px;padding:6px 10px;font-size:12px}}
        #topbar{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.05),stop:1 rgba(255,255,255,.015));border-bottom:1px solid rgba(255,255,255,.09)}} #brand{{font-size:19px;font-weight:800}} #brandDot{{color:{t['accent']};font-size:22px}}
        #sidebar{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,.06),stop:.5 rgba(6,8,20,.62),stop:1 rgba(6,8,20,.76));border-top:1px solid rgba(255,255,255,.14);border-right:1px solid rgba(255,255,255,.06);border-bottom:1px solid rgba(0,0,0,.2)}}
        #topBrand{{font-size:20px;font-weight:800;padding:4px 10px;letter-spacing:.3px;color:{t['text']}}} #eyebrow{{color:{t['accent2']};font-size:11px;font-weight:800;letter-spacing:1.6px;margin:6px 8px}}
        #nav{{text-align:left;background:transparent;border:1px solid transparent;border-radius:17px;padding:9px 14px;color:{t['dim']};font-weight:600}}
        #nav:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba({ar},{ag},{ab},.26),stop:1 rgba({ar},{ag},{ab},.04));border-left:3px solid {t['accent']};color:{t['text']}}}
        #search{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.10),stop:1 rgba(255,255,255,.045));border:1px solid rgba(255,255,255,.14);border-radius:22px;padding:11px 18px;color:{t['text']}}}
        #search:focus{{border:1px solid rgba({a2r},{a2g},{a2b},.85);background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.13),stop:1 rgba(255,255,255,.06))}}
        QLineEdit{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.09),stop:1 rgba(255,255,255,.04));border:1px solid rgba(255,255,255,.14);border-radius:14px;padding:8px 12px;color:{t['text']}}}
        QLineEdit:focus{{border:1px solid rgba({a2r},{a2g},{a2b},.85)}}
        #avatar{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['accent']},stop:1 {t['accent2']});border-radius:20px;font-weight:800;color:{t['deep']}}}
        #heading{{font-size:28px;font-weight:800;letter-spacing:-.2px}} #sectionTitle{{font-size:20px;font-weight:800;letter-spacing:-.1px}}
        #hero{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.10),stop:1 rgba(255,255,255,.03));border-top:1px solid rgba(255,255,255,.22);border-left:1px solid rgba(255,255,255,.10);border-right:1px solid rgba(255,255,255,.05);border-bottom:1px solid rgba(0,0,0,.18);border-radius:20px}}
        #heroText{{font-size:15px;font-weight:600}}
        QPushButton{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.11),stop:1 rgba(255,255,255,.035));border-top:1px solid rgba(255,255,255,.22);border-left:1px solid rgba(255,255,255,.09);border-right:1px solid rgba(255,255,255,.05);border-bottom:1px solid rgba(0,0,0,.16);border-radius:17px;padding:8px 14px;color:{t['text']};font-weight:600}}
        QPushButton:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.18),stop:1 rgba(255,255,255,.06))}} QPushButton:pressed{{background:rgba(255,255,255,.05)}} QPushButton:disabled{{color:{t['dim']};background:rgba(255,255,255,.03)}}
        #primary{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['accent']},stop:1 {t['accent2']});color:{t['deep']};font-weight:800;border:1px solid rgba(255,255,255,.35)}} #primary:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['accent2']},stop:1 {t['accent']})}}
        #circle{{min-width:38px;min-height:38px;border-radius:19px;padding:0}}
        #cards{{background:transparent;border:0;outline:0}}
        #cards::item{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.09),stop:1 rgba(255,255,255,.03));border-top:1px solid rgba(255,255,255,.20);border-left:1px solid rgba(255,255,255,.08);border-right:1px solid rgba(255,255,255,.04);border-bottom:1px solid rgba(0,0,0,.18);border-radius:20px;padding:9px}}
        #cards::item:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba({ar},{ag},{ab},.20),stop:1 rgba(255,255,255,.05));border-top:1px solid rgba({a2r},{a2g},{a2b},.55)}}
        #cards::item:selected{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba({ar},{ag},{ab},.32),stop:1 rgba({ar},{ag},{ab},.10));border-top:1px solid rgba({a2r},{a2g},{a2b},.75)}}
        #tracks,#miniList{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.045),stop:1 rgba(0,0,0,.18));border-top:1px solid rgba(255,255,255,.14);border-left:1px solid rgba(255,255,255,.06);border-right:1px solid rgba(255,255,255,.03);border-bottom:1px solid rgba(0,0,0,.2);border-radius:18px;outline:0;padding:4px}}
        #tracks::item,#miniList::item{{padding:10px 12px;border-radius:12px;margin:1px 2px}} #tracks::item:hover,#miniList::item:hover{{background:rgba(255,255,255,.09)}}
        #tracks::item:selected,#miniList::item:selected{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba({ar},{ag},{ab},.6),stop:1 rgba({a2r},{a2g},{a2b},.42));color:{t['deep']}}}
        #player{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.075),stop:.4 rgba(10,9,24,.86),stop:1 rgba(8,7,20,.94));border-top:1px solid rgba(255,255,255,.20);border-left:1px solid rgba(255,255,255,.12);border-bottom:1px solid rgba(0,0,0,.2);border-radius:28px 0 0 28px}}
        #cover{{background:qradialgradient(cx:.5,cy:.35,radius:1,fx:.5,fy:.35,stop:0 rgba(255,255,255,.14),stop:1 rgba(255,255,255,.04));border-top:1px solid rgba(255,255,255,.28);border-left:1px solid rgba(255,255,255,.14);border-right:1px solid rgba(255,255,255,.06);border-bottom:1px solid rgba(0,0,0,.22);border-radius:26px;font-size:44px}}
        #waveform{{background:transparent;border:0}} #now{{font-weight:700;font-size:15px;padding:4px;letter-spacing:.1px}}
        #player QPushButton#actionBtn{{min-width:34px;min-height:34px;max-width:34px;max-height:34px;border-radius:17px;padding:0;background:rgba(255,255,255,.03);border:1px solid rgba(255,255,255,.07)}}
        #player QPushButton#actionBtn:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.14),stop:1 rgba(255,255,255,.04));border-top:1px solid rgba(255,255,255,.30);border-bottom:1px solid rgba(0,0,0,.40)}}
        #player QPushButton#actionBtn:pressed{{background:rgba(0,0,0,.35);padding-top:1px;border:1px solid rgba(0,0,0,.50)}}
        #player QPushButton#actionBtn:checked{{background:qradialgradient(cx:.5,cy:.5,radius:.8,fx:.5,fy:.5,stop:0 rgba({ar},{ag},{ab},.45),stop:1 rgba({a2r},{a2g},{a2b},.20));border:1.5px solid {t['accent2']}}}
        #player QPushButton#actionBtn:disabled{{opacity:0.4}}

        #player QPushButton#playerNavBtn{{min-width:44px;min-height:44px;max-width:44px;max-height:44px;border-radius:22px;padding:0;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(45,42,60,.90),stop:.4 rgba(25,23,35,.95),stop:1 rgba(14,12,20,1));border-top:1.5px solid rgba(255,255,255,.28);border-left:1px solid rgba(255,255,255,.14);border-right:1px solid rgba(0,0,0,.40);border-bottom:2px solid rgba(0,0,0,.70)}}
        #player QPushButton#playerNavBtn:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(65,60,88,.95),stop:.4 rgba(35,32,50,.98),stop:1 rgba(18,15,26,1));border-top:1.5px solid rgba(255,255,255,.50);border-left:1.5px solid rgba({a2r},{a2g},{a2b},.50);border-bottom:2px solid rgba(0,0,0,.80)}}
        #player QPushButton#playerNavBtn:pressed{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(10,8,16,1),stop:1 rgba(25,22,35,.90));border-top:1.5px solid rgba(0,0,0,.70);border-bottom:1px solid rgba(255,255,255,.15);padding-top:1.5px}}

        #player QPushButton#playerToggleBtn{{min-width:38px;min-height:38px;max-width:38px;max-height:38px;border-radius:19px;padding:0;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(35,32,48,.80),stop:1 rgba(16,14,24,.90));border-top:1px solid rgba(255,255,255,.18);border-left:1px solid rgba(255,255,255,.08);border-bottom:1.5px solid rgba(0,0,0,.55)}}
        #player QPushButton#playerToggleBtn:hover{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(50,46,70,.85),stop:1 rgba(22,19,34,.95));border-top:1.2px solid rgba(255,255,255,.35)}}
        #player QPushButton#playerToggleBtn:checked{{background:qradialgradient(cx:.5,cy:.5,radius:.8,fx:.5,fy:.5,stop:0 rgba({ar},{ag},{ab},.50),stop:1 rgba({a2r},{a2g},{a2b},.22));border:1.5px solid {t['accent2']}}}
        #player QPushButton#playerToggleBtn:pressed{{background:rgba(10,8,16,.90);border-top:1.5px solid rgba(0,0,0,.60);padding-top:1px}}

        #player QPushButton#play,#play{{background:transparent;border:none;min-width:68px;min-height:68px;max-width:68px;max-height:68px;padding:0;margin:0}}
        QSlider::groove:horizontal{{height:5px;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(0,0,0,.65),stop:1 rgba(255,255,255,.06));border-radius:2.5px;border-top:1px solid rgba(0,0,0,.8);border-bottom:1px solid rgba(255,255,255,.12)}}
        QSlider::sub-page:horizontal{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {t['accent']},stop:1 {t['accent2']});border-radius:2.5px;border-top:1px solid rgba(255,255,255,.45)}}
        QSlider::handle:horizontal{{background:qradialgradient(cx:.4,cy:.4,radius:1,fx:.4,fy:.4,stop:0 #ffffff,stop:.45 {t['accent2']},stop:1 {t['accent']});width:16px;height:16px;margin:-5.5px 0;border-radius:8px;border:1.5px solid #ffffff}}
        QSlider::handle:horizontal:hover{{background:qradialgradient(cx:.4,cy:.4,radius:1,fx:.4,fy:.4,stop:0 #ffffff,stop:.55 #ffffff,stop:1 {t['accent2']});width:18px;height:18px;margin:-6.5px 0;border-radius:9px}}
        QSlider::groove:vertical{{width:5px;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba(0,0,0,.65),stop:1 rgba(255,255,255,.06));border-radius:2.5px}}
        QSlider::add-page:vertical{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['accent']},stop:1 {t['accent2']});border-radius:2.5px}} QSlider::sub-page:vertical{{background:rgba(0,0,0,.5);border-radius:2.5px}}
        QSlider::handle:vertical{{background:qradialgradient(cx:.4,cy:.4,radius:1,fx:.4,fy:.4,stop:0 #ffffff,stop:.45 {t['accent2']},stop:1 {t['accent']});width:16px;height:16px;margin:0 -5.5px;border-radius:8px;border:1.5px solid #ffffff}}
        QCheckBox{{color:{t['text']};spacing:8px}} QCheckBox::indicator{{width:17px;height:17px;border-radius:6px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.22)}}
        QCheckBox::indicator:hover{{border:1px solid rgba({a2r},{a2g},{a2b},.6)}} QCheckBox::indicator:checked{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['accent']},stop:1 {t['accent2']});border:1px solid rgba(255,255,255,.5)}}
        QDialog{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['mid']},stop:1 {t['deep']});color:{t['text']}}}
        QMenu{{background:{t['mid']};color:{t['text']};border:1px solid rgba(255,255,255,.14);border-radius:12px;padding:6px}} QMenu::item{{padding:8px 14px;border-radius:8px}}
        QMenu::item:selected{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 rgba({ar},{ag},{ab},.55),stop:1 rgba({a2r},{a2g},{a2b},.35))}} QMenu::separator{{height:1px;background:rgba(255,255,255,.12);margin:6px 4px}}
        #dialogTitle{{font-size:23px;font-weight:800;letter-spacing:-.2px}}
        QScrollBar:vertical{{background:transparent;width:11px;margin:4px 2px}} QScrollBar::handle:vertical{{background:rgba(255,255,255,.18);border-radius:5px;min-height:28px}} QScrollBar::handle:vertical:hover{{background:rgba({a2r},{a2g},{a2b},.55)}}
        QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0px;background:none;border:none}} QScrollBar::add-page:vertical,QScrollBar::sub-page:vertical{{background:none}}
        QScrollBar::horizontal{{background:transparent;height:11px;margin:2px 4px}} QScrollBar::handle:horizontal{{background:rgba(255,255,255,.18);border-radius:5px;min-width:28px}} QScrollBar::handle:horizontal:hover{{background:rgba({a2r},{a2g},{a2b},.55)}}
        QScrollBar::add-line:horizontal,QScrollBar::sub-line:horizontal{{width:0px;background:none;border:none}} QScrollBar::add-page:horizontal,QScrollBar::sub-page:horizontal{{background:none}}
        QStatusBar{{background:rgba(255,255,255,.035);color:{t['dim']};border-top:1px solid rgba(255,255,255,.06)}}
        #lyricsPanel,#lyricsScroll,#lyricsScroll QWidget#lyricsInner{{background:transparent;border:0}}
        QLabel#lyricLine{{color:{t['dim']};font-size:19px;font-weight:700;padding:3px 6px}}
        QLabel#lyricLine[current="true"]{{color:{t['text']};font-size:27px;font-weight:800}}
        #lyricsEmpty{{color:{t['dim']};font-size:15px;font-weight:600;padding:40px}}
        #lyricsBadge{{color:{t['accent2']};font-size:11px;font-weight:800;letter-spacing:1.4px}}
        """)
        self._refresh_player_icons()
        if save: self.save_settings()
        if getattr(self,"_ambient_blur_base",None) is not None: self._refresh_ambient_tint()
        else: self.apply_wallpaper()
        self.populate_cards()

    def _update_play_icon(self, s=None):
        if s is None:
            s = self.p.playbackState()
        t = THEMES.get(self.theme, THEMES["noche"])
        is_playing = (s == QMediaPlayer.PlaybackState.PlayingState)
        if isinstance(self.play, PowerampPlayButton):
            self.play.set_theme_colors(t["accent"], t["accent2"])
            self.play.set_playing_state(is_playing)
        else:
            self.play.setIcon(get_icon("pause" if is_playing else "play", t["deep"], size=36))

    def update_fav_btn(self):
        if not hasattr(self, "favBtn"):
            return
        t = THEMES.get(self.theme, THEMES["noche"])
        p = (self.local_current.get("path") if self.local_current else None) or (self.stream_current.get("id") if self.stream_current else None) or self.selected()
        is_faved = self.d.is_fav(p) if p else False
        if is_faved:
            self.favBtn.setIcon(get_icon("heart_filled", "#ff4d6d", 24))
            self.favBtn.setToolTip("En favoritos (clic para quitar)")
        else:
            self.favBtn.setIcon(get_icon("heart", t.get("text", "#f2f3fb"), 24))
            self.favBtn.setToolTip("Añadir a favoritos")

    def _refresh_player_icons(self):
        t = THEMES.get(self.theme, THEMES["noche"])
        icon_color = t.get("text", "#f2f3fb")
        accent_color = t.get("accent2", "#33e0ff")

        if hasattr(self, "dlBtn"):
            self.dlBtn.setIcon(get_icon("download", icon_color, 24))
        if hasattr(self, "miniBtn"):
            self.miniBtn.setIcon(get_icon("miniplayer", icon_color, 24))
        if hasattr(self, "ytBtn"):
            self.ytBtn.setIcon(get_icon("youtube", icon_color, 24))
        if hasattr(self, "lyricsBtn"):
            self.lyricsBtn.setIcon(get_icon("lyrics", icon_color, 24, active_color_hex=accent_color))

        if hasattr(self, "prevBtn"):
            self.prevBtn.setIcon(get_icon("prev", icon_color, 26))
        if hasattr(self, "nextBtn"):
            self.nextBtn.setIcon(get_icon("next", icon_color, 26))
        if hasattr(self, "shuffleBtn"):
            self.shuffleBtn.setIcon(get_icon("shuffle", icon_color, 22, active_color_hex=accent_color))
        if hasattr(self, "repeatBtn"):
            self.repeatBtn.setIcon(get_icon("repeat", icon_color, 22, active_color_hex=accent_color))

        self._update_play_icon()
        self.update_fav_btn()

    def apply_wallpaper(self):
        if self.wallpaper and Path(self.wallpaper).exists():
            # Escape backslashes and quotes so a path can't break out of the
            # CSS string or inject additional style rules.
            safe=self.wallpaper.replace("\\","/").replace('"','\\"')
            self.centralWidget().setStyleSheet(f'QWidget#base{{border-image:url("{safe}") 0 0 0 0 stretch stretch;}}')
        elif getattr(self,"_has_ambient",False) and AMBIENT_CACHE.exists():
            # Sin wallpaper propio: el fondo ambiental (carátula difuminada y
            # teñida con el color del tema) hace de "cristal líquido" detrás
            # de los paneles translúcidos.
            self.centralWidget().setStyleSheet(f'QWidget#base{{border-image:url("{AMBIENT_CACHE}") 0 0 0 0 stretch stretch;}}')
        else:
            self.centralWidget().setStyleSheet("")

    def set_cover(self,px,placeholder="♪"):
        """Punto único para actualizar la carátula grande del reproductor.
        Si la imagen es válida, también refresca el fondo ambiental difuminado."""
        valid=px is not None and not px.isNull()
        pm=cover_pixmap(px,300,26) if valid else QPixmap()
        self.cover.setPixmap(pm)
        self.cover.setText("" if valid else placeholder)
        if valid:
            self.update_ambient(px)
            try:px.scaled(300,300,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation).save(str(MPRIS_ART_CACHE),"PNG")
            except Exception:pass
        elif MPRIS_ART_CACHE.exists():
            try:MPRIS_ART_CACHE.unlink()
            except Exception:pass

    def update_ambient(self,px):
        """Genera (una vez, en memoria) la versión difuminada de la carátula
        actual y la deja lista para pintarse teñida con el color del tema."""
        try:
            blurred=blurred_pixmap(px,radius=85,target_size=QSize(720,720))
            if blurred.isNull():return
            self._ambient_blur_base=blurred
            self._refresh_ambient_tint()
        except Exception:pass

    def _refresh_ambient_tint(self):
        """Re-tiñe el desenfoque en caché con el color 'deep' del tema activo
        y lo aplica. Barato (sin volver a difuminar), así que puede llamarse
        también al cambiar de tema."""
        base=getattr(self,"_ambient_blur_base",None)
        if base is None or base.isNull():return
        try:
            tinted=QPixmap(base);t=THEMES.get(self.theme,THEMES["noche"])
            tint=QColor(t["deep"]);tint.setAlpha(178)
            pt=QPainter(tinted);pt.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            pt.fillRect(tinted.rect(),tint);pt.end()
            tinted.save(str(AMBIENT_CACHE),"PNG");self._has_ambient=True
            self.apply_wallpaper()
        except Exception:pass
    def open_queue_panel(self):
        dlg=QDialog(self);dlg.setWindowTitle("A continuación");dlg.resize(460,620);dlg.setObjectName("queueDialog")
        v=QVBoxLayout(dlg);v.setContentsMargins(18,18,18,16)
        h=QLabel("A continuación");h.setObjectName("dialogTitle");v.addWidget(h)
        sub=QLabel("Arrastra las canciones para cambiar el orden.");sub.setObjectName("eyebrow");v.addWidget(sub)
        lst=QListWidget();lst.setObjectName("miniList");lst.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove);v.addWidget(lst,1)
        def fill():
            lst.clear()
            if self.local_current or self.stream_current:
                r=self.local_current or self.stream_current
                now=QListWidgetItem(f"▮▮  REPRODUCIENDO\n{r.get('title','')}\n{r.get('artist','')}")
                now.setFlags(Qt.ItemFlag.NoItemFlags);lst.addItem(now)
            for idx,entry in enumerate(self.queue):
                kind=entry[0] if isinstance(entry,tuple) else "local";payload=entry[1] if isinstance(entry,tuple) else entry
                if kind=="stream":
                    r=self.d.stream(payload);title=r["title"] if r else str(payload);artist=r["artist"] if r else ""
                else:
                    r=next((x for x in self.d.songs() if x[0]==payload),None);title=r[1] if r else Path(str(payload)).name;artist=r[2] if r else ""
                it=QListWidgetItem(f"{idx+1:02d}  {title}\n     {artist}");it.setData(Qt.ItemDataRole.UserRole,("q",idx));lst.addItem(it)
        def moved(*_):
            ordered=[]
            for n in range(lst.count()):
                d=lst.item(n).data(Qt.ItemDataRole.UserRole)
                if isinstance(d,tuple) and d[0]=="q" and d[1]<len(self.queue):ordered.append(self.queue[d[1]])
            if len(ordered)==len(self.queue):self.queue=ordered;QTimer.singleShot(0,fill)
        lst.model().rowsMoved.connect(moved)
        row=QHBoxLayout();remove=QPushButton("Quitar");clear=QPushButton("Vaciar cola");close=QPushButton("Cerrar")
        def rm():
            it=lst.currentItem();d=it.data(Qt.ItemDataRole.UserRole) if it else None
            if isinstance(d,tuple) and d[0]=="q" and d[1]<len(self.queue):self.queue.pop(d[1]);fill()
        remove.clicked.connect(rm);clear.clicked.connect(lambda:(self.queue.clear(),fill()));close.clicked.connect(dlg.accept)
        row.addWidget(remove);row.addWidget(clear);row.addStretch();row.addWidget(close);v.addLayout(row);fill();dlg.exec()

    def settings(self):
        SettingsDialog(self).exec()

    def reload_playlists(self):
        # Las playlists se muestran en su vista principal; sin mini-lista lateral.
        return

    def open_mini_playlist(self,it):
        self.view="Playlists"; self.filter=("playlist",it.data(Qt.ItemDataRole.UserRole)); self.search.clear(); self.heading.setText(self.filter[1]); self.refresh()

    def folder(self):
        f=QFileDialog.getExistingDirectory(self,"Selecciona tu carpeta de música")
        if f:
            QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            try: n=self.d.scan(f)
            finally: QApplication.restoreOverrideCursor()
            self.folderText.setText(f); self.reload_playlists(); self.refresh(); self.populate_cards()
            self.statusBar().showMessage(f"Escaneo completado: {n} archivos",4500)
            QTimer.singleShot(1200,self.start_cover_backfill)

    def rescan(self):
        fs=[x[0] for x in self.d.c.execute("SELECT path FROM folders")]; n=0
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            for f in fs:
                if Path(f).exists(): n+=self.d.scan(f)
        finally: QApplication.restoreOverrideCursor()
        self.refresh(); self.populate_cards(); self.statusBar().showMessage(f"Biblioteca actualizada: {n} archivos revisados",4500)
        QTimer.singleShot(1200,self.start_cover_backfill)


    # ============================================================
    # SPOTIFY PANEL  (Liquid Glass Design)
    # ============================================================
    def _build_spotify_panel(self, parent_layout):
        """Panel Spotify con estética Liquid Glass. Se muestra/oculta al cambiar sección."""
        panel = QWidget(); panel.setObjectName("spotifyPanel"); panel.hide()
        self.spotifyPanel = panel
        pv = QVBoxLayout(panel); pv.setContentsMargins(0, 4, 0, 0); pv.setSpacing(0)

        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}"
                             "QScrollBar:vertical{width:5px;background:transparent;}"
                             "QScrollBar::handle:vertical{background:rgba(255,255,255,0.18);border-radius:3px;}"
                             "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")

        inner = QWidget(); inner.setStyleSheet("background:transparent;")
        iv = QVBoxLayout(inner); iv.setContentsMargins(20, 14, 20, 36); iv.setSpacing(16)

        # ─── Estilos Liquid Glass ────────────────────────────────
        LG_CARD = ("QFrame{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                   "stop:0 rgba(255,255,255,0.11),stop:0.6 rgba(255,255,255,0.07),stop:1 rgba(255,255,255,0.04));"
                   "border:1.5px solid rgba(255,255,255,0.20);border-radius:20px;}"
                   "QFrame:hover{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                   "stop:0 rgba(255,255,255,0.18),stop:1 rgba(255,255,255,0.08));"
                   "border:1.5px solid rgba(255,255,255,0.36);}")
        LG_TITLE   = "font-size:17px;font-weight:800;color:#ffffff;letter-spacing:0.2px;background:transparent;border:none;"
        LG_EYE     = "font-size:10px;font-weight:700;letter-spacing:2.5px;color:rgba(255,255,255,0.45);background:transparent;border:none;"
        LG_DESC    = "font-size:12px;color:rgba(255,255,255,0.58);font-weight:400;background:transparent;border:none;"
        LG_URL     = "font-size:10px;color:rgba(255,255,255,0.35);background:transparent;border:none;"
        LG_INPUT   = ("QLineEdit{background:rgba(255,255,255,0.08);border:1.5px solid rgba(255,255,255,0.18);"
                      "border-radius:14px;padding:0 16px;font-size:13px;color:#fff;}"
                      "QLineEdit:focus{background:rgba(255,255,255,0.12);border:1.5px solid rgba(255,255,255,0.36);}"
                      "QLineEdit::placeholder{color:rgba(255,255,255,0.35);}")

        def lg_btn(label, color):
            b = QPushButton(label)
            b.setFixedHeight(38)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            r,g,bl = int(color[1:3],16), int(color[3:5],16), int(color[5:7],16)
            b.setStyleSheet(
                f"QPushButton{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
                f"stop:0 rgba({r},{g},{bl},210),stop:1 rgba({r},{g},{bl},140));"
                f"color:#fff;font-size:13px;font-weight:700;"
                f"border:1.5px solid rgba({r},{g},{bl},200);border-radius:12px;padding:0 18px;}}"
                f"QPushButton:hover{{background:rgba({r},{g},{bl},255);"
                f"border:1.5px solid rgba(255,255,255,0.55);color:#fff;}}"
                f"QPushButton:pressed{{background:rgba({r},{g},{bl},180);}}"
            )
            return b

        # ─── Entrada de enlace ───────────────────────────────────
        inputRow = QHBoxLayout(); inputRow.setSpacing(10)
        self.spotifyInput = QLineEdit()
        self.spotifyInput.setStyleSheet(LG_INPUT)
        self.spotifyInput.setPlaceholderText("✦  Pega tu enlace de Spotify — playlist, álbum, artista o canción…")
        self.spotifyInput.setMinimumHeight(48)
        self.spotifyInput.textChanged.connect(self._on_spotify_input_changed)
        inputRow.addWidget(self.spotifyInput, 1)
        clrBtn = QPushButton("✕"); clrBtn.setFixedSize(44, 44)
        clrBtn.setStyleSheet("QPushButton{background:rgba(255,255,255,0.08);border:1.5px solid rgba(255,255,255,0.15);"
                             "border-radius:14px;color:rgba(255,255,255,0.60);font-size:14px;font-weight:700;}"
                             "QPushButton:hover{background:rgba(255,80,80,0.25);border:1.5px solid rgba(255,80,80,0.50);color:#fff;}")
        clrBtn.clicked.connect(lambda: self.spotifyInput.clear())
        inputRow.addWidget(clrBtn)
        iv.addLayout(inputRow)

        # Badge detección
        self.spotifyDetectLabel = QLabel("")
        self.spotifyDetectLabel.setWordWrap(True)
        self.spotifyDetectLabel.setStyleSheet("font-size:12px;font-weight:700;padding:4px 2px;background:transparent;border:none;")
        self.spotifyDetectLabel.setVisible(False)
        iv.addWidget(self.spotifyDetectLabel)

        # ─── Tarjeta Spotify Web ─────────────────────────────────
        spotCard = QFrame(); spotCard.setStyleSheet(LG_CARD)
        glass_shadow(spotCard, blur=24, dx=0, dy=8, alpha=65)
        scl = QVBoxLayout(spotCard); scl.setContentsMargins(22, 16, 22, 16); scl.setSpacing(10)
        eyeRow = QHBoxLayout()
        spotEye = QLabel("SPOTIFY · ESCUCHA EN LA WEB"); spotEye.setStyleSheet(LG_EYE)
        eyeRow.addWidget(spotEye); eyeRow.addStretch()
        scl.addLayout(eyeRow)
        titleRow = QHBoxLayout(); titleRow.setSpacing(12)
        spotIco = QLabel("🎵"); spotIco.setStyleSheet("font-size:28px;background:transparent;border:none;")
        titleRow.addWidget(spotIco)
        spotTitle = QLabel("Spotify Web"); spotTitle.setStyleSheet(LG_TITLE)
        titleRow.addWidget(spotTitle, 1)
        scl.addLayout(titleRow)
        spotDesc = QLabel("Abre Spotify en tu navegador o lleva tu enlace directamente a los servicios de descarga.")
        spotDesc.setWordWrap(True); spotDesc.setStyleSheet(LG_DESC)
        scl.addWidget(spotDesc)
        btnRow = QHBoxLayout(); btnRow.setSpacing(10)
        b1 = lg_btn("  Abrir Spotify Web  ↗", "#1DB954")
        b1.clicked.connect(lambda: QDesktopServices.openUrl(QUrl("https://open.spotify.com/")))
        btnRow.addWidget(b1, 1)
        scl.addLayout(btnRow)
        iv.addWidget(spotCard)

        # ─── Separador ──────────────────────────────────────────
        sepRow = QHBoxLayout(); sepRow.setSpacing(14)
        for _ in range(2):
            ln = QFrame(); ln.setFrameShape(QFrame.Shape.HLine)
            ln.setStyleSheet("background:rgba(255,255,255,0.13);border:none;max-height:1px;min-height:1px;")
            sepRow.addWidget(ln, 1)
            if _ == 0:
                lbl = QLabel("SERVICIOS DE DESCARGA"); lbl.setStyleSheet(LG_EYE)
                sepRow.addWidget(lbl)
        iv.addLayout(sepRow)

        # hint
        hint = QLabel("Pega tu enlace de Spotify arriba → haz clic en el servicio → el enlace se pasa automáticamente.")
        hint.setWordWrap(True)
        hint.setStyleSheet("font-size:12px;color:rgba(255,255,255,0.48);padding:0 2px 2px 2px;background:transparent;border:none;")
        iv.addWidget(hint)

        # ─── Tarjetas de servicios ───────────────────────────────
        SERVICES = [
            ("SpotDown",    "Descarga playlists y álbumes completos · Sin registro · MP3 de alta calidad",
             "https://spotdown.org/es8",       "⬇", "#1DB954"),
            ("SoundLoaders","Descarga canciones, playlists y podcasts · Rápido · Sin límite diario",
             "https://soundloaders.app/",      "🔊", "#4c97f8"),
            ("SpotMate",    "Conversor de Spotify · Interfaz limpia · Soporta playlists privadas",
             "https://spotmate.online/en1",    "✦", "#a78bfa"),
        ]
        self.spotifyServiceBtns = []
        for sname, sdesc, surl, sico, scol in SERVICES:
            r,g,bl = int(scol[1:3],16), int(scol[3:5],16), int(scol[5:7],16)
            scard = QFrame()
            scard.setStyleSheet(
                f"QFrame{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 rgba({r},{g},{bl},38),stop:1 rgba({r},{g},{bl},14));"
                f"border:1.5px solid rgba({r},{g},{bl},80);"
                f"border-top:1.5px solid rgba({r},{g},{bl},140);"
                f"border-radius:18px;}}"
                f"QFrame:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,"
                f"stop:0 rgba({r},{g},{bl},65),stop:1 rgba({r},{g},{bl},25));"
                f"border:1.5px solid rgba({r},{g},{bl},200);}}"
            )
            glass_shadow(scard, blur=16, dx=0, dy=4, alpha=45)
            scard.setCursor(Qt.CursorShape.PointingHandCursor)
            cl = QVBoxLayout(scard); cl.setContentsMargins(18, 14, 18, 14); cl.setSpacing(8)

            hdr = QHBoxLayout(); hdr.setSpacing(14)
            # Ícono pill
            icoFrame = QFrame(); icoFrame.setFixedSize(48, 48)
            icoFrame.setStyleSheet(f"QFrame{{background:rgba({r},{g},{bl},50);"
                                   f"border:1px solid rgba({r},{g},{bl},120);border-radius:15px;}}")
            icoLay = QVBoxLayout(icoFrame); icoLay.setContentsMargins(0,0,0,0)
            icoLbl = QLabel(sico)
            icoLbl.setStyleSheet("font-size:20px;color:#fff;background:transparent;border:none;")
            icoLbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            icoLay.addWidget(icoLbl)
            hdr.addWidget(icoFrame)

            nameCol = QVBoxLayout(); nameCol.setSpacing(2)
            tl = QLabel(sname); tl.setStyleSheet(f"font-size:16px;font-weight:800;color:#ffffff;background:transparent;border:none;")
            dl = QLabel(sdesc); dl.setWordWrap(True); dl.setStyleSheet(LG_DESC)
            nameCol.addWidget(tl); nameCol.addWidget(dl)
            hdr.addLayout(nameCol, 1)

            obtn = lg_btn("Abrir  ↗", scol); obtn.setFixedWidth(110)
            obtn.clicked.connect(lambda chk=False, u=surl, n=sname: self._spotify_open_service(u, n))
            hdr.addWidget(obtn)
            cl.addLayout(hdr)

            urlLbl = QLabel(f'<a href="{surl}" style="color:{scol};text-decoration:none;">{surl}</a>')
            urlLbl.setOpenExternalLinks(True)
            urlLbl.setStyleSheet(LG_URL)
            cl.addWidget(urlLbl)

            iv.addWidget(scard)
            self.spotifyServiceBtns.append((obtn, surl))

        iv.addStretch(1)
        scroll.setWidget(inner)
        pv.addWidget(scroll, 1)
        parent_layout.addWidget(panel, 1)


    def _on_spotify_input_changed(self, text):
        text = text.strip()
        if not text:
            self.spotifyDetectLabel.setVisible(False)
            return
        import re
        if not re.search(r'open\.spotify\.com', text):
            self.spotifyDetectLabel.setText("⚠  No parece un enlace de Spotify — pega algo como https://open.spotify.com/playlist/…")
            self.spotifyDetectLabel.setStyleSheet("color:rgba(255,180,0,0.85);font-size:12px;font-weight:700;")
            self.spotifyDetectLabel.setVisible(True)
            return
        # Detect type
        m = re.search(r'spotify\.com/(?:intl-[a-z]+/)?([a-z]+)/([A-Za-z0-9]+)', text)
        kind_map = {"playlist":"Playlist","album":"Álbum","artist":"Artista","track":"Canción","episode":"Episodio","show":"Podcast"}
        if m:
            kind = kind_map.get(m.group(1), m.group(1).capitalize())
            self.spotifyDetectLabel.setText(f"✓  {kind} de Spotify detectado — elige un servicio de descarga abajo ↓")
            self.spotifyDetectLabel.setStyleSheet("color:rgba(29,185,84,0.95);font-size:12px;font-weight:700;")
        else:
            self.spotifyDetectLabel.setText("✓  Enlace de Spotify detectado — elige un servicio de descarga abajo ↓")
            self.spotifyDetectLabel.setStyleSheet("color:rgba(29,185,84,0.95);font-size:12px;font-weight:700;")
        self.spotifyDetectLabel.setVisible(True)

    def _spotify_open_service(self, base_url, service_name):
        url = self.spotifyInput.text().strip() if hasattr(self,"spotifyInput") else ""
        import re, urllib.parse
        if url and re.search(r'open\.spotify\.com', url):
            # Pass the spotify link to the service if possible
            if "spotdown.org" in base_url:
                final = f"https://spotdown.org/es8?q={urllib.parse.quote(url)}"
            elif "soundloaders.app" in base_url:
                final = f"https://soundloaders.app/?sp_url={urllib.parse.quote(url)}"
            elif "spotmate.online" in base_url:
                final = f"https://spotmate.online/en1?url={urllib.parse.quote(url)}"
            else:
                final = base_url
        else:
            final = base_url
        QDesktopServices.openUrl(QUrl(final))
        self.statusBar().showMessage(f"Abriendo {service_name} en tu navegador…", 3000)

    def _show_spotify_panel(self):
        if not hasattr(self,"spotifyPanel"):return
        # hide list / hero / cards / lyrics
        self.list.hide(); self.section.hide()
        if hasattr(self,"hero"):self.hero.hide()
        if hasattr(self,"cards"):self.cards.hide()
        if hasattr(self,"lyricsPanel") and self.lyricsPanel.isVisible():
            self.lyricsPanel.hide()
        self.spotifyPanel.show()

    def nav(self,n):
        if getattr(self,"lyricsPanel",None) and self.lyricsPanel.isVisible():
            self.lyricsPanel.hide();self.section.show();self.list.show();self.lyricsBtn.setChecked(False)
        if hasattr(self,"spotifyPanel") and self.spotifyPanel.isVisible():
            self.spotifyPanel.hide();self.section.show();self.list.show()
        self.view=n; self.filter=None
        self.stream_search_timer.stop()
        if n!="Carpetas": self.currentFolder=None
        self.search.blockSignals(True); self.search.clear(); self.search.blockSignals(False)
        self.heading.setText("Para ti" if n=="Inicio" else ("YouTube · Streaming" if n=="Streaming" else ("Spotify · Descargador" if n=="Spotify" else n)))
        self.hero.setVisible(n in ("Inicio","Canciones","Carpetas"))
        self.cards.setVisible(n in ("Inicio","Álbumes","Artistas","Géneros"))
        if hasattr(self,"spotifyPanel"):self.spotifyPanel.setVisible(n=="Spotify")
        self.populate_cards()
        if n=="Streaming":
            self.cards.hide(); self.list.clear(); self.rows=[]; self.stream_rows=[]
            self.section.setText("Busca canciones, artistas o álbumes")
            it=QListWidgetItem("Escribe en el buscador superior para escuchar música desde YouTube\nLa descarga está disponible para contenido que tengas derecho a guardar.")
            it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it); return
        if n=="Spotify":
            self.cards.hide(); self.list.clear(); self.rows=[]; self.stream_rows=[]
            self.heading.setText("Spotify · Descargador de Playlists")
            self.section.setText("Detecta tu enlace de Spotify y elige el servicio de descarga")
            self._show_spotify_panel()
            return
        self.list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove if n=="Cola" else QAbstractItemView.DragDropMode.NoDragDrop)
        if n=="Cola":
            self.cards.hide(); self.rows=[]
            self.section.setText("Arrastra para ordenar · lo que suena y lo que sigue")
            self.render_queue(); return
        if n=="Recientes":
            self.cards.hide();self.rows=self.d.recent();self.section.setText("Continuar escuchando · reproducido recientemente")
            self.list.clear();self.render_rows(self.rows);self.render_stream_rows(self.d.recent_streams(),"Streaming reciente");return
        if n in ("Descargas","Offline"):
            self.cards.hide();self.rows=[];self.heading.setText("Offline");self.section.setText("Tu música descargada · disponible sin conexión");self.render_downloads();return
        else:
            self.section.setText("Descubre" if n=="Inicio" else "Tu colección")
        if n=="Estadísticas":self.show_stats()
        elif n=="Smart Playlists":
            self.list.clear();self.rows=[]
            for name in ("Más escuchadas","No escuchadas recientemente","Favoritas","Mejor valoradas"):
                it=QListWidgetItem("◉  "+name);it.setData(Qt.ItemDataRole.UserRole,("smart",name));self.list.addItem(it)
        else:
            self.refresh()
            if n in ("Inicio","Artistas","Álbumes","Top Picks"):
                QTimer.singleShot(120,lambda v=n:self.load_hybrid_view(v))

    def populate_cards(self):
        if not hasattr(self,"cards"):return
        self.cards.clear();theme=THEMES.get(self.theme,THEMES["noche"]);allrows=self.d.songs()
        if self.view=="Álbumes":
            groups=[("album",name) for name,_ in self.d.groups("album")][:14]
        elif self.view=="Artistas":
            groups=[("artist",name) for name,_ in self.d.groups("artist")][:14]
        elif self.view=="Géneros":
            groups=[("genre",name) for name,_ in self.d.groups("genre")][:14]
        else:
            # Recomendaciones: favoritos y mejor valoradas, evitando repetir álbum.
            ordered=sorted(allrows,key=lambda r:(r[7],r[8]),reverse=True)
            groups=[];seen=set()
            for r in ordered:
                name=r[3] or r[2]
                kind="album" if r[3] else "artist"
                if name and (kind,name) not in seen:
                    seen.add((kind,name));groups.append((kind,name))
                if len(groups)>=10:break
        indexes={"artist":2,"album":3,"genre":4}
        for kind,name in groups:
            rows=[r for r in allrows if r[indexes[kind]]==name]
            px=artwork_for_rows(rows,150)
            if px is None:
                # Nunca dejar un cuadro vacío: portada genérica bonita
                # (degradado + monograma), no un simple rectángulo plano.
                px=generic_cover_pixmap(name,150,16)
            else:
                px=cover_pixmap(px,150,16)
            item=QListWidgetItem(QIcon(px),f"{name}\n{len(rows)} canciones")
            item.setData(Qt.ItemDataRole.UserRole,(kind,name))
            self.cards.addItem(item)

    def card_activate(self,it):
        d=it.data(Qt.ItemDataRole.UserRole)
        if not d:return
        if isinstance(d,tuple) and d and d[0]=="online_search":
            self.search.setText(d[1]); self.search_youtube(); return
        views={"album":"Álbumes","artist":"Artistas","genre":"Géneros"}
        self.filter=d; self.view=views.get(d[0],self.view); self.heading.setText(d[1]); self.cards.hide(); self.refresh()

    def _hybrid_seed(self,view):
        rows=self.d.songs()
        fav=[r for r in rows if r[7]]
        rated=sorted(rows,key=lambda r:(r[8],r[7]),reverse=True)
        src=fav[:20]+rated[:20]+rows[:20]
        artists=[]
        albums=[]
        for r in src:
            if r[2] and r[2]!="Artista desconocido" and r[2] not in artists:artists.append(r[2])
            if r[3] and r[3]!="Álbum desconocido" and r[3] not in albums:albums.append(r[3])
        if view=="Artistas":
            return ((artists[0]+" artistas similares música") if artists else "artistas música popular")
        if view=="Álbumes":
            return ((artists[0]+" álbum canciones") if artists else "álbumes música populares")
        if view=="Top Picks":
            return ((" ".join(artists[:2])+" mejores canciones") if artists else "música tendencias éxitos")
        return ((artists[0]+" mix canciones") if artists else "música recomendada tendencias")

    def load_hybrid_view(self,view):
        if self.view!=view or self.search.text().strip():return
        if self.hybrid_process and self.hybrid_process.state()!=QProcess.ProcessState.NotRunning:
            self.hybrid_process.kill()
        self.hybrid_token+=1;token=self.hybrid_token
        q=self._hybrid_seed(view)
        p=QProcess(self);self.hybrid_process=p;p.setProgram(YTDLP)
        p.setArguments(["--flat-playlist","--dump-single-json","--no-warnings","--no-playlist",f"ytsearch8:{q}"])
        p.finished.connect(lambda code,status,v=view,tok=token:self._hybrid_results(p,code,v,tok))
        p.start()

    def _hybrid_results(self,p,code,view,token):
        try:
            if p is not self.hybrid_process or token!=self.hybrid_token or self.view!=view or self.search.text().strip():return
        except Exception:
            return
        if code!=0:return
        try:entries=(json.loads(bytes(p.readAllStandardOutput()).decode("utf-8","ignore")).get("entries") or [])
        except Exception:return
        found=[]
        for e in entries:
            vid=str(e.get("id") or "")
            if not self._valid_video_id(vid):continue
            r={"id":vid,"title":str(e.get("title") or "Sin título"),"artist":str(e.get("channel") or e.get("uploader") or "YouTube"),
               "thumb":resolve_thumb(e,vid),"duration":int(e.get("duration") or 0)}
            self.d.upsert_stream(r);found.append(r)
        if not found:return
        if view=="Inicio":
            self._render_hybrid_tracks(found,"Recomendaciones para ti")
        elif view=="Top Picks":
            self._render_hybrid_tracks(found,"Tendencias para descubrir")
        elif view=="Artistas":
            self._render_hybrid_cards(found,"También podrían gustarte",artist_mode=True)
        elif view=="Álbumes":
            self._render_hybrid_cards(found,"Nuevos álbumes y canciones",artist_mode=False)

    def load_home_trending(self):
        if self.view!="Inicio" or self.search.text().strip():return
        p=QProcess(self);p.setProgram(YTDLP)
        p.setArguments(["--flat-playlist","--dump-single-json","--no-warnings","--no-playlist","ytsearch6:música tendencias éxitos"])
        def done(code,status):
            if code!=0 or self.view!="Inicio":return
            try:entries=(json.loads(bytes(p.readAllStandardOutput()).decode("utf-8","ignore")).get("entries") or [])
            except Exception:return
            rows=[]
            for e in entries:
                vid=str(e.get("id") or "")
                if not self._valid_video_id(vid):continue
                r={"id":vid,"title":str(e.get("title") or "Sin título"),"artist":str(e.get("channel") or e.get("uploader") or "YouTube"),
                   "thumb":resolve_thumb(e,vid),"duration":int(e.get("duration") or 0)}
                self.d.upsert_stream(r);rows.append((vid,r["title"],r["artist"],r["thumb"],r["duration"],0))
            if rows:self.render_stream_rows(rows,"Tendencias ahora")
        p.finished.connect(done);p.start()
        # Keep a reference so QProcess is not garbage-collected.
        self._home_trending_process=p

    def render_discover(self,rows,append=False):
        if not append:self.discoverList.clear()
        existing=set()
        for n in range(self.discoverList.count()):
            d=self.discoverList.item(n).data(Qt.ItemDataRole.UserRole)
            if isinstance(d,dict):existing.add(d.get("id"))
        for r in rows[:8]:
            if r.get("id") in existing:continue
            it=QListWidgetItem(f"▶  {r.get('title','')}\n    {r.get('artist','')}")
            it.setData(Qt.ItemDataRole.UserRole,dict(r));self.discoverList.addItem(it)

    def discover_activate(self,it):
        r=it.data(Qt.ItemDataRole.UserRole)
        if isinstance(r,dict):self.play_stream_dict(r)

    def _render_hybrid_tracks(self,rows,title):
        # Evita duplicados visuales con canciones locales del mismo título/artista.
        local={(r[1].strip().lower(),r[2].strip().lower()) for r in self.d.songs()}
        clean=[];seen=set()
        for r in rows:
            k=(r["title"].strip().lower(),r["artist"].strip().lower())
            if k in local or r["id"] in seen:continue
            seen.add(r["id"]);clean.append((r["id"],r["title"],r["artist"],r["thumb"],r["duration"],0))
        if clean:self.render_stream_rows(clean,title)

    def _render_hybrid_cards(self,rows,title,artist_mode=False):
        if not hasattr(self,"cards"):return
        seen=set()
        for r in rows:
            name=r["artist"] if artist_mode else r["title"]
            if not name or name in seen:continue
            seen.add(name)
            px=gradient_pixmap(150,THEMES.get(self.theme,THEMES["noche"])["accent"],THEMES.get(self.theme,THEMES["noche"])["accent2"])
            item=QListWidgetItem(QIcon(px),f"{name}\n{'YouTube · artista' if artist_mode else 'YouTube · descubrir'}")
            item.setData(Qt.ItemDataRole.UserRole,("online_search",name))
            self.cards.addItem(item)
            if len(seen)>=6:break
        if seen:
            self.section.setText("Tu colección + "+title)

    def show_stats(self):
        self.list.clear();self.rows=[];total,top=self.d.stats();plays,seconds=total
        h=QListWidgetItem(f"Tu biblioteca en números\n{plays} reproducciones • {seconds//3600} horas registradas");h.setFlags(Qt.ItemFlag.NoItemFlags);self.list.addItem(h)
        mp={r[0]:r for r in self.d.songs()}
        for i,(p,n) in enumerate(top,1):
            if p in mp:
                r=mp[p];it=QListWidgetItem(f"{i:02d}  {r[1]}\n     {r[2]} • {n} reproducciones");it.setData(Qt.ItemDataRole.UserRole,p);self.list.addItem(it)

    def _remove_search_headers(self):
        for i in range(self.list.count()-1,-1,-1):
            it=self.list.item(i)
            if it.data(Qt.ItemDataRole.UserRole)=="search-header":self.list.takeItem(i)
    def _render_unified_local_header(self):
        q=self.search.text().strip()
        if len(q)<2:return
        # refresh() already rendered local rows; add a clear source heading at the top.
        it=QListWidgetItem("En tu biblioteca");it.setFlags(Qt.ItemFlag.NoItemFlags);it.setData(Qt.ItemDataRole.UserRole,"search-header")
        f=it.font();f.setBold(True);it.setFont(f);self.list.insertItem(0,it)
    def _add_search_header(self,text):
        it=QListWidgetItem(text);it.setFlags(Qt.ItemFlag.NoItemFlags);it.setData(Qt.ItemDataRole.UserRole,"search-header");f=it.font();f.setBold(True);it.setFont(f);self.list.addItem(it)

    def search_changed(self):
        self.refresh()
        q=self.search.text().strip()
        if len(q)>=2:
            self.stream_search_timer.start();self.deezer_timer.start()
        else:
            self.stream_search_timer.stop();self.deezer_timer.stop()


    def _valid_video_id(self,vid):
        return bool(YT_ID_RE.fullmatch(str(vid or "")))

    def search_deezer(self):
        q=self.search.text().strip()[:100]
        if len(q)<2:return
        # Deezer is a metadata/catalog enrichment provider here; playback remains
        # local or YouTube. No private app code, tokens, DRM or media URLs are used.
        from urllib.parse import quote
        url=QUrl("https://api.deezer.com/search?q="+quote(q))
        rep=self.net.get(QNetworkRequest(url))
        rep.finished.connect(lambda:self._deezer_results(rep,q))

    def _deezer_results(self,rep,q):
        if q!=self.search.text().strip()[:100]:rep.deleteLater();return
        try:data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
        except Exception:data={}
        rep.deleteLater()
        rows=(data.get("data") or [])[:6]
        if not rows:return
        self._add_search_header("Deezer · catálogo")
        for x in rows:
            title=str(x.get("title") or "");artist=str((x.get("artist") or {}).get("name") or "")
            album=str((x.get("album") or {}).get("title") or "");cover=str((x.get("album") or {}).get("cover_medium") or "")
            it=QListWidgetItem(f"◇  {title}\n    {artist}  •  {album}")
            it.setToolTip("Metadatos de Deezer · doble clic para buscar esta canción en las fuentes reproducibles")
            it.setData(Qt.ItemDataRole.UserRole,("deezer_search",(title+" "+artist).strip(),cover))
            self.list.addItem(it)

    def search_youtube(self):
        q=self.search.text().strip()[:120]
        self.stream_rows=[]
        if self.view=="Streaming":self.list.clear()
        if len(q)<2:
            it=QListWidgetItem("Escribe al menos 2 caracteres para buscar en YouTube"); it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it); return
        if self.view=="Streaming":
            self.heading.setText("Buscando en YouTube…")
            it=QListWidgetItem("Buscando canciones…"); it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it)
        else:
            self._add_search_header("YouTube · buscando…")
        self.youtube_searcher.search(q,limit=12)

    def _on_youtube_results(self,rows):
        if self.view=="Streaming":
            self.list.clear(); self.heading.setText("Resultados de YouTube")
        else:
            # Conserva la sección local y añade la fuente online debajo.
            for i in range(self.list.count()-1,-1,-1):
                it=self.list.item(i)
                if it.data(Qt.ItemDataRole.UserRole)=="youtube-header":self.list.takeItem(i)
            it=QListWidgetItem("YouTube");it.setFlags(Qt.ItemFlag.NoItemFlags);it.setData(Qt.ItemDataRole.UserRole,"youtube-header");f=it.font();f.setBold(True);it.setFont(f);self.list.addItem(it)
        for row in rows:
            self.d.upsert_stream(row)
            self.stream_rows.append(row)
            dur=row["duration"];mm,ss=divmod(dur,60)
            it=QListWidgetItem(f'▶  {row["title"]}\n     {row["artist"]}  •  {mm}:{ss:02d}' if dur else f'▶  {row["title"]}\n     {row["artist"]}')
            it.setData(Qt.ItemDataRole.UserRole,("stream",len(self.stream_rows)-1)); self.list.addItem(it)
        if not self.stream_rows:
            it=QListWidgetItem("No encontré resultados reproducibles");it.setFlags(Qt.ItemFlag.NoItemFlags);self.list.addItem(it)

    def _on_youtube_search_failed(self,msg):
        if self.view=="Streaming":
            self.list.clear(); self.heading.setText("Resultados de YouTube")
        it=QListWidgetItem("No se pudo consultar YouTube. Comprueba tu conexión e inténtalo otra vez."+("\n"+msg[:180] if msg else ""))
        it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it)

    def play_stream(self,index):
        if not (0<=index<len(self.stream_rows)):return
        self.play_stream_dict(self.stream_rows[index])

    def play_stream_dict(self,row):
        if not self._valid_video_id(row.get("id")):return
        self.local_current=None; self.stream_current=row; self.now.setText(f'{row["title"]}\n{row["artist"]} • YouTube')
        self.statusBar().showMessage("Preparando streaming…",3000)
        self.youtube_resolver.resolve(row)

    def _on_stream_resolved(self,row,url):
        if not self.stream_current or str(self.stream_current.get("id"))!=str(row.get("id")):return
        self.fadeTimer.stop();self.crossfade_started=False;self._apply_output_volume()
        self.p.stop()
        if not url or not (url.startswith("http://") or url.startswith("https://")):
            self.statusBar().showMessage("Fuente de streaming no válida para este vídeo.",4000)
            return
        self.p.setSource(QUrl(url));self.p.play();self.d.add_stream_history(row["id"]);self.update_playing_indicator()
        self.now.setText(f'{row["title"]}\n{row["artist"]} • YouTube')
        self.set_cover(None,"◉")
        self._load_stream_thumb(row)
        self.statusBar().showMessage("Reproduciendo desde YouTube",2500)
        QTimer.singleShot(2000, self._prefetch_next_stream)

    def _prefetch_next_stream(self):
        """Precarga la URL del siguiente vídeo de streaming en segundo plano para inicio instantáneo."""
        try:
            next_row=None
            if self.queue:
                entry=self.queue[0]
                if isinstance(entry,tuple) and entry[0]=="stream":
                    next_row=self.d.stream(entry[1])
            elif self.stream_current and self.stream_rows:
                cur=next((i for i,r in enumerate(self.stream_rows) if r.get("id")==self.stream_current.get("id")),-1)
                if cur>=0 and cur+1<len(self.stream_rows):
                    next_row=self.stream_rows[cur+1]
            if next_row and self._valid_video_id(next_row.get("id")):
                vid=next_row["id"]
                from sakukelly.streaming.resolver import _STREAM_URL_CACHE, CACHE_TTL
                import time
                if vid not in _STREAM_URL_CACHE or (time.time()-_STREAM_URL_CACHE[vid][1]>CACHE_TTL):
                    if not getattr(self,"_prefetch_resolver",None):
                        from sakukelly.streaming.resolver import YouTubeStreamResolver
                        self._prefetch_resolver=YouTubeStreamResolver(self)
                    self._prefetch_resolver.resolve(next_row)
        except Exception:pass

    def _on_stream_resolve_failed(self,row,msg):
        if not self.stream_current or str(self.stream_current.get("id"))!=str(row.get("id")):return
        self.statusBar().showMessage(msg,5000)

    def _cover_request(self,url):
        """Crea una petición de carátula tolerante a CDN/redirects."""
        req=QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent",f"Mozilla/5.0 Sakukelly/{APP_VERSION}".encode())
        req.setRawHeader(b"Accept",b"image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8")
        try:req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,QNetworkRequest.RedirectPolicy.NoLessSafeRedirectPolicy)
        except Exception:pass
        return req

    def _set_stream_cover(self,px,vid,cache=None):
        """Muestra la portada solo si sigue sonando el mismo vídeo."""
        if px is None or px.isNull():return False
        if cache:
            try:px.save(str(cache),"PNG")
            except Exception:pass
        if self.stream_current and str(self.stream_current.get("id") or "")==str(vid):
            self.set_cover(px)
        return True

    def _load_stream_thumb(self,row):
        # 5.10.3: prioridad solicitada: YouTube primero; Deezer solo como respaldo.
        # Usamos una clave nueva para no reutilizar portadas antiguas de Deezer
        # guardadas por versiones 5.10.1/5.10.2 bajo el mismo id de YouTube.
        vid=str(row.get("id") or "").strip()
        key=hashlib.sha1(("ytfirst-v2:"+vid).encode("utf-8","ignore")).hexdigest()
        cache=COVER_CACHE/(key+".png")
        if cache.exists():
            px=QPixmap(str(cache))
            if self._set_stream_cover(px,vid):return
        self._load_youtube_cover(row,cache)

    def _load_youtube_cover(self,row,cache):
        """Intenta varias miniaturas oficiales de YouTube antes de usar Deezer."""
        vid=str(row.get("id") or "").strip()
        urls=[]
        thumb=str(row.get("thumb") or "").strip()
        if thumb.startswith("https://"):urls.append(thumb)
        if self._valid_video_id(vid):
            # maxres puede no existir; hqdefault es el respaldo más compatible.
            urls.extend([
                f"https://i.ytimg.com/vi/{vid}/maxresdefault.jpg",
                f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
                f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            ])
        # elimina duplicados conservando el orden
        urls=list(dict.fromkeys(u for u in urls if u.startswith("https://")))
        if not urls:return self._load_stream_deezer_cover(row,cache)

        def attempt(pos):
            if pos>=len(urls):return self._load_stream_deezer_cover(row,cache)
            rep=self.net.get(self._cover_request(urls[pos]))
            def done():
                ok=False
                try:
                    if rep.error()==QNetworkReply.NetworkError.NoError:
                        raw=bytes(rep.readAll());px=QPixmap()
                        if px.loadFromData(raw):ok=self._set_stream_cover(px,vid,cache)
                except Exception:pass
                finally:rep.deleteLater()
                if not ok:attempt(pos+1)
            rep.finished.connect(done)
        attempt(0)

    def _load_stream_deezer_cover(self,row,cache):
        """Respaldo: busca una portada de álbum fiable en Deezer."""
        from urllib.parse import quote
        from difflib import SequenceMatcher
        vid=str(row.get("id") or "");title=str(row.get("title") or "").strip();artist=str(row.get("artist") or "").strip()
        def norm(s):
            s=str(s or "").lower()
            s=re.sub(r"(?i)\b(official|music|video|audio|lyrics?|visualizer|hd|4k|remaster(?:ed)?|live)\b"," ",s)
            s=re.sub(r"[^a-z0-9áéíóúüñ ]+"," ",s)
            return " ".join(s.split())
        clean_title=norm(title);clean_artist=norm(artist)
        q=(artist+" "+clean_title).strip()[:150]
        if not q:return
        rep=self.net.get(self._cover_request("https://api.deezer.com/search?q="+quote(q)))
        def meta_done():
            url="";best_score=0.0
            try:
                data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"));items=(data.get("data") or [])[:12]
                target_duration=int(row.get("duration") or 0)
                for item in items:
                    dz_title=norm(item.get("title_short") or item.get("title"))
                    dz_artist=norm((item.get("artist") or {}).get("name"))
                    title_score=SequenceMatcher(None,clean_title,dz_title).ratio() if clean_title and dz_title else 0
                    artist_score=SequenceMatcher(None,clean_artist,dz_artist).ratio() if clean_artist and dz_artist else (0.72 if not clean_artist else 0)
                    dur=int(item.get("duration") or 0)
                    duration_score=1.0 if not target_duration or not dur else max(0.0,1.0-abs(target_duration-dur)/max(18.0,target_duration*0.18))
                    score=(title_score*0.58)+(artist_score*0.30)+(duration_score*0.12)
                    if score>best_score:
                        album=item.get("album") or {};candidate=str(album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or "")
                        if candidate.startswith("https://"):best_score=score;url=candidate
                if best_score<0.72:url=""
            except Exception:pass
            rep.deleteLater()
            if not url:return
            img=self.net.get(self._cover_request(url))
            def image_done():
                try:
                    if img.error()==QNetworkReply.NetworkError.NoError:
                        raw=bytes(img.readAll());px=QPixmap()
                        if px.loadFromData(raw):self._set_stream_cover(px,vid,cache)
                except Exception:pass
                finally:img.deleteLater()
            img.finished.connect(image_done)
        rep.finished.connect(meta_done)

    def local_video_query(self):
        r=self.local_current
        if not r:return ""
        artist=(r.get("artist") or "").strip();title=(r.get("title") or "").strip()
        return (artist+" "+title+" official video").strip()[:160]

    def find_local_video(self,force=False,callback=None):
        r=self.local_current
        if not r:
            if callback:callback(None)
            return
        cached=self.d.local_video(r["path"])
        if cached and not force:
            if callback:callback(cached)
            return
        q=self.local_video_query()
        if not q:
            if callback:callback(None)
            return
        if getattr(self,"local_video_search",None) and self.local_video_search.state()!=QProcess.ProcessState.NotRunning:self.local_video_search.kill()
        p=QProcess(self);self.local_video_search=p;p.setProgram(YTDLP)
        p.setArguments(["--flat-playlist","--dump-single-json","--no-warnings","--no-playlist",f"ytsearch5:{q}"])
        def done(code,status):
            if p is not self.local_video_search or code!=0:
                if callback:callback(None)
                return
            try:entries=(json.loads(bytes(p.readAllStandardOutput()).decode("utf-8","ignore")).get("entries") or [])
            except Exception:entries=[]
            best=None
            for e in entries:
                vid=str(e.get("id") or "")
                if not self._valid_video_id(vid):continue
                best={"id":vid,"title":str(e.get("title") or ""),"artist":str(e.get("channel") or e.get("uploader") or "YouTube"),"thumb":resolve_thumb(e,vid),"offset_ms":0};break
            if best:self.d.set_local_video(r["path"],best,0)
            if callback:callback(best)
        p.finished.connect(done);p.start();self.statusBar().showMessage("Buscando videoclip para tu canción local…",2500)

    def choose_local_video(self):
        if not self.local_current:return
        q,ok=QInputDialog.getText(self,"Elegir vídeo de YouTube","Buscar vídeo:",text=self.local_video_query())
        if not ok or not q.strip():return
        # Temporarily search with the user query and store the first result.
        old_title=self.local_current["title"];old_artist=self.local_current["artist"]
        self.local_current["title"]=q.strip();self.local_current["artist"]=""
        def done(r):
            self.local_current["title"]=old_title;self.local_current["artist"]=old_artist
            if r:self.statusBar().showMessage("Vídeo asociado a la canción",2500)
        self.find_local_video(True,done)

    def open_video_player(self):
        if getattr(self,"video_player",None) is None:
            self.video_player=VideoPlayer(self)
        self.video_player.show();self.video_player.raise_();self.video_player.activateWindow()
        self.video_player.load_current()

    def download_current_stream(self):
        row=self.stream_current
        if not row:
            QMessageBox.information(self,"Descargas","Reproduce primero una canción de la sección Streaming.");return
        if not self._valid_video_id(row.get("id")):return
        answer=QMessageBox.question(self,"Descargar","Descarga únicamente contenido que tengas derecho o autorización para guardar.\n\n¿Continuar?")
        if answer!=QMessageBox.StandardButton.Yes:return
        folder=QFileDialog.getExistingDirectory(self,"Guardar descarga",str(Path.home()/"Music"))
        if not folder:return
        if self.youtube_downloader.busy:
            QMessageBox.information(self,"Descargas","Ya hay una descarga en curso.");return
        self._download_row=dict(row)
        self.youtube_downloader.download(row["id"],folder)
        self.statusBar().showMessage("Descarga iniciada…",3000)

    def _on_download_finished(self,folder,path):
        row=getattr(self,"_download_row",None)
        if row and path:self.d.add_download(row.get("id",""),row.get("title",""),row.get("artist",""),path)
        self.statusBar().showMessage(f"Descarga terminada en {folder}",7000)
        if self.view in ("Descargas","Offline"):self.render_downloads()

    def refresh(self):
        if getattr(self,"lyricsPanel",None) and self.lyricsPanel.isVisible():
            self.lyricsPanel.hide();self.section.show();self.list.show();self.lyricsBtn.setChecked(False)
        q=self.search.text().strip(); self.list.clear(); self.stream_rows=[]
        if not q and self.view=="Inicio":
            self.section.setText("Descubre")
        elif not q and self.view=="Artistas":
            self.section.setText("Tus artistas y nuevos descubrimientos")
        elif not q and self.view=="Álbumes":
            self.section.setText("Álbumes de tu colección y para descubrir")
        elif not q and self.view=="Top Picks":
            self.section.setText("Selección para ti")
        if q:
            self.rows=self.d.songs(q,False); self.heading.setText("Búsqueda unificada"); self.cards.hide()
            self._add_search_header("En tu biblioteca")
            self.render_rows(self.rows)
            if not self.rows:
                it=QListWidgetItem("No encontré coincidencias locales"); it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it)
            return
        if self.view=="Carpetas": self.render_folders(); return
        if self.view=="Playlists" and not self.filter:
            self.rows=[]
            for n in self.d.pls():
                it=QListWidgetItem("▣  "+n); it.setData(Qt.ItemDataRole.UserRole,("playlist",n)); self.list.addItem(it)
            return
        if self.view=="Playlists" and self.filter: self.rows=self.d.plsongs(self.filter[1])
        else: self.rows=self.d.songs("",self.view=="Favoritos")
        if self.view=="Top Picks": self.rows=sorted(self.rows,key=lambda r:(r[8],r[7]),reverse=True)[:50]
        if self.filter and self.view!="Playlists":
            idx={"artist":2,"album":3,"genre":4}.get(self.filter[0])
            if idx is not None:self.rows=[r for r in self.rows if r[idx]==self.filter[1]]
        if self.view=="Géneros" and not self.filter:
            self.rows=[]
            for name,count in self.d.groups("genre"):
                it=QListWidgetItem(f"≡  {name}\n    {count} canciones"); it.setData(Qt.ItemDataRole.UserRole,("group","genre",name)); self.list.addItem(it)
            return
        if self.view=="Inicio":
            recent=self.d.recent(10)
            if recent:
                self.render_rows(recent)
            elif self.rows:
                self.render_rows(self.rows[:10])
            return
        elif self.view=="Top Picks" and self.rows:self._add_search_header("En tu biblioteca")
        self.render_rows(self.rows)
        if self.view=="Favoritos":
            sf=self.d.stream_favs()
            if sf:self.render_stream_rows(sf,"Favoritos de YouTube")
        elif self.view=="Playlists" and self.filter:
            sp=self.d.stream_plsongs(self.filter[1])
            if sp:self.render_stream_rows(sp,"Streaming")

    def render_rows(self,rows):
        for no,x in enumerate(rows,1):
            p,t,a,al,g,y,d,f,rate=x; mm,ss=divmod(int(d),60); stars="★"*rate+"☆"*(5-rate)
            it=QListWidgetItem(f"{no:02d}    {'♥' if f else '♡'}   {t}\n        {a}  •  {al}     {mm}:{ss:02d}     {stars}")
            it.setData(Qt.ItemDataRole.UserRole,p)
            if self.local_current and self.local_current.get("path")==p:
                it.setText("▮▮  REPRODUCIENDO   "+it.text())
                f=it.font();f.setBold(True);it.setFont(f);it.setBackground(self._now_playing_brush())
            self.list.addItem(it)

    def render_stream_rows(self,rows,title=None):
        if title:self._add_search_header(title)
        for x in rows:
            r={"id":x[0],"title":x[1],"artist":x[2],"thumb":x[3],"duration":x[4],"fav":x[5]}
            self.stream_rows.append(r);mm,ss=divmod(int(r["duration"] or 0),60)
            it=QListWidgetItem(f"◉    {'♥' if r.get('fav') else '♡'}   {r['title']}\n        {r['artist']}  •  YouTube     {mm}:{ss:02d}")
            it.setData(Qt.ItemDataRole.UserRole,("stream",len(self.stream_rows)-1))
            if self.stream_current and self.stream_current.get("id")==r.get("id"):
                it.setText("▮▮  REPRODUCIENDO   "+it.text())
                f=it.font();f.setBold(True);it.setFont(f);it.setBackground(self._now_playing_brush())
            self.list.addItem(it)

    def render_folders(self):
        self.list.clear(); self.rows=[]; roots=[x[0] for x in self.d.c.execute("SELECT path FROM folders ORDER BY path")]
        if self.currentFolder is None:
            self.heading.setText("Tus carpetas")
            if not roots:
                it=QListWidgetItem("＋ Añade una carpeta de música para empezar"); it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it); return
            for f in roots:
                count=sum(1 for r in self.d.songs() if str(r[0]).startswith(str(Path(f))+"/"))
                it=QListWidgetItem(f"▤  {Path(f).name or f}\n    {f}  •  {count} canciones"); it.setData(Qt.ItemDataRole.UserRole,("folder",f)); self.list.addItem(it)
            return
        folder=Path(self.currentFolder); self.heading.setText(folder.name or str(folder))
        up=QListWidgetItem("←  Volver"); up.setData(Qt.ItemDataRole.UserRole,("folder_up",str(folder.parent))); self.list.addItem(up)
        for f in child_folders(self.d,str(folder)):
            it=QListWidgetItem("▤  "+Path(f).name); it.setData(Qt.ItemDataRole.UserRole,("folder",f)); self.list.addItem(it)
        self.rows=folder_rows(self.d,str(folder)); self.render_rows(self.rows)

    def player_drop(self,payload):
        """Play immediately when a library item or audio file is dropped on the player."""
        kind,data=payload
        if kind=="files":
            path=next((x for x in data if Path(x).suffix.lower() in EXT and Path(x).exists()),None)
            if not path:return
            row=next((r for r in self.d.songs() if r[0]==path),None)
            if row:
                self.rows=[row];self.i=0;self.playrow(0)
            else:
                title=Path(path).stem;artist="";album="Archivo"
                try:
                    a=MF(path,easy=True) if MF else None
                    if a:
                        title=(a.get("title") or [title])[0];artist=(a.get("artist") or [""])[0];album=(a.get("album") or ["Archivo"])[0]
                except Exception:pass
                self.stream_current=None;self.local_current={"path":path,"title":title,"artist":artist,"album":album}
                self.p.stop();self.p.setSource(QUrl.fromLocalFile(path));self.p.play();self.now.setText(f"{title}\\n{artist or album}")
                px=embedded_or_folder_cover(path,300);self.set_cover(px)
            self.statusBar().showMessage("Reproduciendo archivo arrastrado",2200);return
        d=data
        if isinstance(d,list):d=tuple(d)
        if isinstance(d,tuple) and d:
            if d[0]=="stream":self.play_stream(int(d[1]));return
            if d[0]=="download":
                path=d[2]
                if Path(path).exists():
                    self.stream_current=None;self.local_current={"path":path,"title":Path(path).stem,"artist":"","album":"Offline"};self.p.setSource(QUrl.fromLocalFile(path));self.p.play();self.now.setText(Path(path).stem+"\\nOffline")
                return
        if isinstance(d,str):
            idx=next((j for j,r in enumerate(self.rows) if r[0]==d),-1)
            if idx>=0:self.i=idx;self.playrow(idx)

    def activate(self):
        it=self.list.currentItem()
        if not it:return
        d=it.data(Qt.ItemDataRole.UserRole)
        if isinstance(d,tuple) and d and d[0]=="download":
            path=d[2]
            if Path(path).exists():
                self.stream_current=None;self.local_current={"path":path,"title":self.list.currentItem().text().split("\n")[0].replace("⇩  ",""),"artist":"","album":"Descargas"}
                self.p.stop();self.p.setSource(QUrl.fromLocalFile(path));self.p.play();self.now.setText(self.local_current["title"]+"\nDisponible sin conexión")
            return
        if isinstance(d,tuple) and d and d[0]=="deezer_search":
            self.search.setText(d[1]);self.search_youtube();return
        if isinstance(d,tuple) and d and d[0]=="stream":
            self.play_stream(d[1]); return
        if isinstance(d,tuple) and d and d[0]=="queue_item":
            idx=d[1]
            if 0<=idx<len(self.queue):
                entry=self.queue[idx]; del self.queue[:idx+1]
                if isinstance(entry,tuple) and entry[0]=="stream":
                    r=self.d.stream(entry[1])
                    if r:self.play_stream_dict(r)
                else:
                    path=entry[1] if isinstance(entry,tuple) else entry
                    r=next((x for x in self.d.songs() if x[0]==path),None)
                    if r:self.rows=[r];self.i=0;self.playrow(0)
            if self.view=="Cola":self.render_queue()
            return
        if isinstance(d,tuple):
            if d[0]=="smart":
                self.rows=self.d.smart(d[1]); self.heading.setText(d[1]); self.list.clear(); self.render_rows(self.rows); return
            if d[0]=="folder": self.currentFolder=d[1]; self.render_folders(); return
            if d[0]=="folder_up":
                roots=[Path(x[0]) for x in self.d.c.execute("SELECT path FROM folders")]; parent=Path(d[1])
                self.currentFolder=None if any(parent==r.parent or parent==r for r in roots) else str(parent); self.render_folders(); return
            if d[0]=="playlist": self.filter=("playlist",d[1]); self.heading.setText(d[1]); self.refresh(); return
            if d[0]=="group": self.filter=(d[1],d[2]); self.heading.setText(d[2]); self.refresh(); return
        idx=next((j for j,r in enumerate(self.rows) if r[0]==d),-1)
        if idx>=0:self.i=idx; self.playrow(idx)

    def playrow(self,i):
        if 0<=i<len(self.rows):
            self.fadeTimer.stop(); self.crossfade_started=False; self._pending_next=None; self._apply_output_volume(); self.p2.stop(); self.au2.setVolume(0.0)
            x=self.rows[i]; self.stream_current=None; self.local_current={"path":x[0],"title":x[1],"artist":x[2],"album":x[3]}; self.p.stop(); self.p.setSource(QUrl.fromLocalFile(x[0])); self.p.play(); self.update_playing_indicator(); self.d.played(x[0]); self.now.setText(f"{x[1]}\n{x[2]} • {x[3]}"); self.art(x[0])
        if self.video_player:
            self.video_player.load_current()

    def play_file_external(self, path):
        if not path or not Path(path).exists(): return
        r = next((x for x in self.d.songs() if x[0] == path), None)
        if not r:
            try:
                title = Path(path).stem
                r = (path, title, "Desconocido", "Desconocido", 0, 0, 0, 0, 0, 0, "")
            except Exception: return
        self.rows = [r]; self.i = 0; self.playrow(0)

    def _now_playing_brush(self):
        c=QColor(THEMES.get(self.theme,THEMES["noche"]).get("accent","#7c3aed"));c.setAlpha(70);return c

    def update_playing_indicator(self):
        for n in range(self.list.count()):
            it=self.list.item(n);d=it.data(Qt.ItemDataRole.UserRole)
            txt=it.text().replace("▮▮  REPRODUCIENDO   ","")
            active=False
            if isinstance(d,str) and self.local_current:active=(d==self.local_current.get("path"))
            elif isinstance(d,tuple) and d and d[0]=="stream" and 0<=d[1]<len(self.stream_rows) and self.stream_current:
                active=(self.stream_rows[d[1]].get("id")==self.stream_current.get("id"))
            it.setText(("▮▮  REPRODUCIENDO   " if active else "")+txt)
            f=it.font();f.setBold(active);it.setFont(f)
            it.setBackground(self._now_playing_brush() if active else QColor(0,0,0,0))
        if self.view=="Cola":self.render_queue()

    def queue_reordered(self,*_):
        if self.view!="Cola":return
        ordered=[]
        for n in range(self.list.count()):
            d=self.list.item(n).data(Qt.ItemDataRole.UserRole)
            if isinstance(d,tuple) and d and d[0]=="queue_item":
                old=d[1]
                if 0<=old<len(self.queue):ordered.append(self.queue[old])
        if len(ordered)==len(self.queue):
            self.queue=ordered
            QTimer.singleShot(0,self.render_queue)

    def render_downloads(self):
        self.list.clear();rows=self.d.downloads()
        if not rows:
            it=QListWidgetItem("No hay descargas disponibles sin conexión.");it.setFlags(Qt.ItemFlag.NoItemFlags);self.list.addItem(it);return
        for i,title,artist,path,ts in rows:
            it=QListWidgetItem(f"⇩  {title}\n    {artist}  •  Disponible sin conexión")
            it.setData(Qt.ItemDataRole.UserRole,("download",i,path));self.list.addItem(it)

    def render_queue(self):
        self.list.clear()
        if self.local_current or self.stream_current:
            title=(self.local_current or self.stream_current)["title"]; artist=(self.local_current or self.stream_current)["artist"]
            source="Biblioteca local" if self.local_current else "YouTube"
            it=QListWidgetItem(f"▮▮  REPRODUCIENDO AHORA   {title}\n        {artist}  •  {source}")
            it.setFlags(Qt.ItemFlag.NoItemFlags); f=it.font(); f.setBold(True); it.setFont(f)
            it.setBackground(self._now_playing_brush()); self.list.addItem(it)
        if not self.queue:
            it=QListWidgetItem("La cola está vacía.\nAñade canciones con clic derecho > Añadir a la cola.")
            it.setFlags(Qt.ItemFlag.NoItemFlags); self.list.addItem(it)
            return
        header=QListWidgetItem("A CONTINUACIÓN"); header.setFlags(Qt.ItemFlag.NoItemFlags)
        f=header.font(); f.setBold(True); header.setFont(f); self.list.addItem(header)
        for idx,entry in enumerate(self.queue):
            kind=entry[0] if isinstance(entry,tuple) else "local"
            payload=entry[1] if isinstance(entry,tuple) else entry
            if kind=="stream":
                row=self.d.stream(payload); title=row["title"] if row else str(payload); artist=row["artist"] if row else "YouTube"; icon="◉"
            else:
                r=next((x for x in self.d.songs() if x[0]==payload),None)
                title=r[1] if r else Path(str(payload)).name; artist=r[2] if r else ""; icon="♫"
            it=QListWidgetItem(f"{idx+1:02d}   {icon}  {title}\n        {artist}")
            it.setData(Qt.ItemDataRole.UserRole,("queue_item",idx))
            self.list.addItem(it)

    def art(self,p):
        self.set_cover(None)
        px=embedded_or_folder_cover(p,288)
        if px is not None:
            self.set_cover(px)
        elif self.local_current:
            # Mientras se intenta bajar la carátula real, mostramos de una
            # vez una portada genérica bonita (no un hueco en blanco).
            title=self.local_current.get("title") or Path(p).stem
            artist=self.local_current.get("artist") or ""
            self.set_cover(generic_cover_pixmap(f"{artist} {title}".strip(),288))
            self.fetch_deezer_local_cover(self.local_current)

    def fetch_deezer_local_cover(self,row,on_done=None):
        """Descarga la carátula de un álbum vía Deezer y la guarda en la
        misma caché que usa embedded_or_folder_cover. Si no se puede (sin
        red, sin resultados, título/artista vacíos...), guarda en su lugar
        una portada genérica bonita para no dejar la canción sin carátula
        y no reintentar la búsqueda en cada sesión. `on_done(found_bool)` se
        llama siempre al terminar (usado por el barrido en segundo plano)."""
        path=str(row.get("path") or "");title=str(row.get("title") or "").strip();artist=str(row.get("artist") or "").strip()
        seed=(artist+" "+title).strip() or Path(path).stem
        if not path:
            if on_done:on_done(False)
            return
        key=hashlib.sha1(path.encode("utf-8","ignore")).hexdigest();cache=COVER_CACHE/(key+".png")
        if cache.exists():
            px=QPixmap(str(cache))
            if not px.isNull():
                if self.local_current and self.local_current.get("path")==path:self.set_cover(px)
                if on_done:on_done(True)
                return
        if not title:
            save_generic_cover_to_cache(path,seed)
            if on_done:on_done(False)
            return
        token=(path,title,artist)
        if getattr(self,"_deezer_cover_pending",None)==token:
            if on_done:on_done(False)
            return
        self._deezer_cover_pending=token
        from urllib.parse import quote
        q=(artist+" "+title).strip()[:140]
        rep=self.net.get(QNetworkRequest(QUrl("https://api.deezer.com/search?q="+quote(q))))
        def meta_done():
            try:
                data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"));items=data.get("data") or []
                best=items[0] if items else {};album=best.get("album") or {}
                url=str(album.get("cover_xl") or album.get("cover_big") or album.get("cover_medium") or "")
            except Exception:url=""
            rep.deleteLater()
            if not url.startswith("https://"):
                save_generic_cover_to_cache(path,seed)
                if on_done:on_done(False)
                return
            img=self.net.get(QNetworkRequest(QUrl(url)))
            def image_done():
                found=False
                try:
                    raw=bytes(img.readAll());px=QPixmap()
                    if raw and px.loadFromData(raw):
                        px.save(str(cache),"PNG");found=True
                        if self.local_current and self.local_current.get("path")==path:
                            self.set_cover(px)
                    else:
                        save_generic_cover_to_cache(path,seed)
                finally:
                    img.deleteLater()
                    if on_done:on_done(found)
            img.finished.connect(image_done)
        rep.finished.connect(meta_done)

    # ---- Barrido en segundo plano: portadas locales faltantes ------------
    def start_cover_backfill(self,force=False):
        """Recorre la biblioteca local buscando canciones sin carátula (ni
        incrustada, ni en su carpeta, ni ya cacheada) y para cada una intenta
        bajarla automáticamente; si no se puede, le deja una portada
        genérica bonita. Corre de a una, con una pequeña pausa entre
        canciones, para no saturar la red ni bloquear la interfaz."""
        if getattr(self,"_cover_backfill_active",False) and not force:return
        pending=[r[0] for r in self.d.songs() if not has_cached_cover(r[0])]
        if not pending:
            if force:self.statusBar().showMessage("Todas tus canciones ya tienen carátula.",3000)
            return
        self._cover_backfill_queue=pending
        self._cover_backfill_active=True
        self._cover_backfill_total=len(pending); self._cover_backfill_done=0
        self._cover_backfill_found=0
        self._scan_next_cover()

    def stop_cover_backfill(self):
        self._cover_backfill_active=False

    def _scan_next_cover(self):
        if not getattr(self,"_cover_backfill_active",False):return
        if not self._cover_backfill_queue:
            self._cover_backfill_active=False
            if self._cover_backfill_total:
                self.statusBar().showMessage(
                    f"Carátulas completadas: {self._cover_backfill_found} descargadas de {self._cover_backfill_total} canciones "
                    f"(el resto recibió una portada genérica).",5000)
            return
        path=self._cover_backfill_queue.pop(0)
        if has_cached_cover(path) or embedded_or_folder_cover(path,150) is not None:
            self._on_cover_backfill_step(True);return
        r=next((x for x in self.d.songs() if x[0]==path),None)
        row={"path":path,"title":(r[1] if r else Path(path).stem),"artist":(r[2] if r else "")}
        self.fetch_deezer_local_cover(row,on_done=self._on_cover_backfill_step)

    def _on_cover_backfill_step(self,found):
        self._cover_backfill_done+=1
        if found:self._cover_backfill_found+=1
        if self._cover_backfill_done%10==0 or self._cover_backfill_done==self._cover_backfill_total:
            self.statusBar().showMessage(f"Buscando carátulas: {self._cover_backfill_done}/{self._cover_backfill_total}",2000)
        # Pequeña pausa entre canciones: evita disparar decenas de peticiones
        # de red simultáneas y deja la interfaz completamente fluida.
        QTimer.singleShot(180,self._scan_next_cover)

    def open_current_on_youtube(self):
        from urllib.parse import quote_plus
        if self.stream_current:
            vid=str(self.stream_current.get("id") or "")
            if self._valid_video_id(vid):
                QDesktopServices.openUrl(QUrl("https://www.youtube.com/watch?v="+vid));return
        if self.local_current:
            title=str(self.local_current.get("title") or "");artist=str(self.local_current.get("artist") or "")
            q=(artist+" "+title+" official music video").strip()
            if q:QDesktopServices.openUrl(QUrl("https://www.youtube.com/results?search_query="+quote_plus(q)));return
        self.statusBar().showMessage("No hay una canción seleccionada para abrir en YouTube.",3000)

    def toggle(self):
        if self.p.playbackState()==QMediaPlayer.PlaybackState.PlayingState:self.p.pause()
        elif self.p.source().isEmpty():
            if self.rows:self.i=max(0,self.i); self.playrow(self.i)
        else:self.p.play()

    def set_volume(self,x):
        self.base_volume=x/100; self._apply_output_volume()

    def _peek_next_local(self):
        """Determina qué sonará después sin avanzar el estado, para poder precargarlo
        y solapar su audio con el de la canción actual (crossfade real)."""
        if self.queue:
            entry=self.queue[0]
            if isinstance(entry,tuple) and entry[0]=="stream":return None
            path=entry[1] if isinstance(entry,tuple) else entry
            return ("queue_path",path)
        if not self.rows:return None
        ni=next_index(self.i,len(self.rows),self.shuffle,self.repeat)
        return ("index",ni)

    def _begin_crossfade(self,duration_ms=None):
        if self.crossfade_started or not self.rows: return
        self._pending_next=self._peek_next_local()
        if self._pending_next:
            kind,payload=self._pending_next
            path=payload if kind=="queue_path" else (self.rows[payload][0] if 0<=payload<len(self.rows) else None)
            if path:
                self._gain_mult2=self._gain_for_path(path)
                self.au2.setVolume(0.0); self.p2.setSource(QUrl.fromLocalFile(path)); self.p2.play()
            else:
                self._pending_next=None
        self._active_fade_ms=duration_ms if duration_ms else self.crossfade_ms
        self.crossfade_started=True; self.fadeStart=int(time.time()*1000); self.fadeTimer.start()

    def _fade_step(self):
        elapsed=int(time.time()*1000)-self.fadeStart; dur=max(60,getattr(self,"_active_fade_ms",None) or self.crossfade_ms)
        ratio=min(1.0,elapsed/dur)
        self.au.setVolume(max(0.0,min(1.0,self.base_volume*getattr(self,"_gain_mult",1.0)*(1.0-ratio))))
        if self._pending_next:self.au2.setVolume(max(0.0,min(1.0,self.base_volume*getattr(self,"_gain_mult2",1.0)*ratio)))
        if ratio>=1.0:
            self.fadeTimer.stop(); self.crossfade_started=False; self._apply_output_volume()
            if self._pending_next:self._complete_crossfade()
            else:self.next()

    def _complete_crossfade(self):
        kind,payload=self._pending_next; self._pending_next=None
        carry_pos=self.p2.position()
        self.p2.stop(); self.au2.setVolume(0.0)
        if kind=="queue_path":
            path=payload
            if self.queue and (self.queue[0][1] if isinstance(self.queue[0],tuple) else self.queue[0])==path:self.queue.pop(0)
            r=next((x for x in self.d.songs() if x[0]==path),None)
            if not r:self.next();return
            self.rows=[r]; self.i=0; x=r
        else:
            ni=payload
            if not (0<=ni<len(self.rows)):self.next();return
            self.i=ni; x=self.rows[ni]
        self.stream_current=None; self.local_current={"path":x[0],"title":x[1],"artist":x[2],"album":x[3]}
        self.p.stop(); self.p.setSource(QUrl.fromLocalFile(x[0])); self.p.play()
        QTimer.singleShot(60,lambda pos=carry_pos:self.p.setPosition(pos))
        self._apply_output_volume()
        self.update_playing_indicator(); self.d.played(x[0]); self.now.setText(f"{x[1]}\n{x[2]} • {x[3]}"); self.art(x[0])
        if self.video_player:
            self.video_player.load_current()

    def next(self):
        # 1) Si la pista actual de streaming pertenece a la lista de
        #    resultados/streaming visible, avanzamos dentro de ella (con
        #    vuelta al principio). Antes, si stream_current no aparecía en
        #    stream_rows (p. ej. venía de Favoritos, de la cola, o de una
        #    búsqueda ya reemplazada), esta condición fallaba por completo
        #    y "Siguiente" no hacía nada.
        if self.stream_current and self.stream_rows:
            cur=next((i for i,r in enumerate(self.stream_rows) if r.get("id")==self.stream_current.get("id")),-1)
            if cur>=0:
                self.play_stream((cur+1)%len(self.stream_rows)); return
        # 2) La cola "a continuación" tiene prioridad si hay algo pendiente,
        #    sea local o de streaming.
        if self.queue:
            entry=self.queue.pop(0)
            if isinstance(entry,tuple) and entry[0]=="stream":
                r=self.d.stream(entry[1])
                if r:self.stream_current=r;self.play_stream_dict(r);return
            path=entry[1] if isinstance(entry,tuple) else entry
            r=next((x for x in self.d.songs() if x[0]==path),None)
            if r:self.rows=[r];self.i=0;self.playrow(0);return
        # 3) Biblioteca local: avanza (o da la vuelta) en la lista actual.
        if not self.stream_current:
            if 0<=self.i<len(self.rows) and self.p.duration()>0 and self.p.position()<self.p.duration()*.5:
                self.d.skip(self.rows[self.i][0])
            if self.rows:
                self.i=next_index(self.i,len(self.rows),self.shuffle,self.repeat,respect_repeat=False)
                self.playrow(self.i); return
        # 4) No queda nada más en cola/biblioteca/resultados (por ejemplo,
        #    reproducías un solo archivo arrastrado, una descarga offline, o
        #    una pista de streaming fuera de cualquier lista). En vez de
        #    dejar la reproducción muerta en silencio, repetimos la pista
        #    actual para que la cola nunca se detenga sola, ni en streaming
        #    ni en local.
        if self.stream_current:
            self.play_stream_dict(self.stream_current); return
        if self.local_current and self.local_current.get("path"):
            path=self.local_current["path"]
            self.p.setSource(QUrl.fromLocalFile(path)); self.p.play()
            self.update_playing_indicator()

    def prev(self):
        if self.stream_current and self.stream_rows:
            cur=next((i for i,r in enumerate(self.stream_rows) if r.get("id")==self.stream_current.get("id")),0)
            self.play_stream((cur-1)%len(self.stream_rows)); return
        if self.rows:self.i=prev_index(self.i,len(self.rows)); self.playrow(self.i)

    def _list_item_clicked(self,item):
        # Ctrl/Shift-click está extendiendo la selección para una acción en
        # lote (cola/playlist/favoritos), no pidiendo reproducir ese ítem.
        if QApplication.keyboardModifiers() & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.ShiftModifier):
            return
        self.activate()

    def selected(self):
        it=self.list.currentItem(); d=it.data(Qt.ItemDataRole.UserRole) if it else None
        return d if isinstance(d,str) else (self.rows[self.i][0] if 0<=self.i<len(self.rows) else None)

    def _set_shuffle(self,on):
        self.shuffle=bool(on)
        b=getattr(self,"shuffleBtn",None)
        if b and b.isChecked()!=self.shuffle:
            b.blockSignals(True);b.setChecked(self.shuffle);b.blockSignals(False)

    def _set_repeat(self,on):
        self.repeat=bool(on)
        b=getattr(self,"repeatBtn",None)
        if b and b.isChecked()!=self.repeat:
            b.blockSignals(True);b.setChecked(self.repeat);b.blockSignals(False)

    def favorite(self):
        if self.stream_current and self.p.playbackState()!=QMediaPlayer.PlaybackState.StoppedState:
            self.d.upsert_stream(self.stream_current);self.d.stream_fav(self.stream_current["id"])
            self.update_fav_btn()
            self.statusBar().showMessage("Favorito de streaming actualizado",2200);return
        # Prioriza la canción que REALMENTE está sonando (self.local_current).
        # Antes se usaba solo self.selected() (lo resaltado en la lista visible),
        # así que si navegabas a otra vista mientras reproducías algo, el botón
        # de favorito guardaba la fila equivocada o no encontraba nada y no
        # pasaba nada en absoluto. self.selected() queda como respaldo para
        # poder marcar favorito una canción de la lista sin tenerla sonando.
        p=(self.local_current.get("path") if self.local_current else None) or self.selected()
        if p:
            self.d.fav(p); self.refresh()
            self.update_fav_btn()
            self.statusBar().showMessage("Favorito actualizado",2200)
        else:
            self.statusBar().showMessage("Reproduce o selecciona una canción para marcarla como favorita.",3000)

    def menu(self,pos):
        it=self.list.itemAt(pos)
        if not it:return
        sel_before=self.list.selectedItems()
        if it not in sel_before:
            self.list.selectionModel().setCurrentIndex(self.list.indexFromItem(it),QItemSelectionModel.SelectionFlag.ClearAndSelect)  # clic fuera de la selección: actuar solo sobre este ítem
        else:
            self.list.selectionModel().setCurrentIndex(self.list.indexFromItem(it),QItemSelectionModel.SelectionFlag.NoUpdate)
        d=it.data(Qt.ItemDataRole.UserRole)
        if isinstance(d,tuple) and d and d[0]=="folder":
            folder=d[1]
            count=sum(1 for r in self.d.songs() if str(r[0]).startswith(str(Path(folder))+os.sep))
            m=QMenu(self)
            opena=m.addAction("Abrir carpeta")
            remove=None
            if count==0:remove=m.addAction("Eliminar carpeta vacía de la colección")
            x=m.exec(self.list.mapToGlobal(pos))
            if x==opena:self.activate();return
            if remove is not None and x==remove:
                ans=QMessageBox.question(self,"Eliminar carpeta vacía",
                    f"¿Quitar esta carpeta de la colección?\n\n{folder}\n\nNo se eliminará ninguna carpeta ni archivo del disco.")
                if ans==QMessageBox.StandardButton.Yes:
                    self.d.remove_folder(folder);self.currentFolder=None;self.render_folders()
                    self.statusBar().showMessage("Carpeta vacía eliminada de la colección",3000)
                return
            return
        if isinstance(d,tuple) and d and d[0]=="queue_item":
            idx=d[1]; m=QMenu(self); playnow=m.addAction("Reproducir ahora"); up=m.addAction("Mover arriba");down=m.addAction("Mover abajo");remove=m.addAction("Quitar de la cola")
            x=m.exec(self.list.mapToGlobal(pos))
            if x==playnow:self.activate()
            elif x==up and idx>0:self.queue[idx-1],self.queue[idx]=self.queue[idx],self.queue[idx-1];self.render_queue()
            elif x==down and idx<len(self.queue)-1:self.queue[idx+1],self.queue[idx]=self.queue[idx],self.queue[idx+1];self.render_queue()
            elif x==remove and 0<=idx<len(self.queue):
                self.queue.pop(idx); self.render_queue(); self.statusBar().showMessage("Canción quitada de la cola",2000)
            return
        is_stream=isinstance(d,tuple) and d and d[0]=="stream"
        p=self.selected() if not is_stream else None
        if not p and not is_stream:return
        # Selección múltiple homogénea (mismo tipo que el ítem clicado): las
        # acciones de cola/playlist/favorito pasan a operar en lote.
        sel_items=self.list.selectedItems()
        if is_stream:
            batch_rows=[si.data(Qt.ItemDataRole.UserRole) for si in sel_items]
            batch_rows=[t for t in batch_rows if isinstance(t,tuple) and len(t)>1 and t[0]=="stream"]
            n=max(1,len(batch_rows))
        else:
            batch_paths=[si.data(Qt.ItemDataRole.UserRole) for si in sel_items]
            batch_paths=[bp for bp in batch_paths if isinstance(bp,str)]
            n=max(1,len(batch_paths))
        m=QMenu(self);play=m.addAction("Reproducir");playnext=m.addAction("Reproducir siguiente")
        queue=m.addAction(f"Añadir {n} canciones a la cola" if n>1 else "Añadir al final de la cola")
        fav=m.addAction(f"Añadir/quitar favorito ({n})" if n>1 else "Añadir/quitar favorito")
        pl=m.addAction(f"Añadir {n} canciones a playlist" if n>1 else "Añadir a playlist")
        lyrics=m.addAction("Ver letra");info=m.addAction("Información");similar=m.addAction("Artistas similares")
        rm=None;acts=[];fixmeta=None
        vmenu=None;vauto=vchoose=vclear=None
        if not is_stream:
            fixmeta=m.addAction("Corregir metadatos (MusicBrainz)")
            rm=m.addMenu("Calificación");acts=[rm.addAction("Sin calificación")]+[rm.addAction("★"*i) for i in range(1,6)]
            vmenu=m.addMenu("Vídeo de YouTube");vauto=vmenu.addAction("Buscar automáticamente");vchoose=vmenu.addAction("Elegir otro vídeo");vclear=vmenu.addAction("Quitar asociación")
        x=m.exec(self.list.mapToGlobal(pos))
        if x==play:self.activate()
        elif x==fixmeta:self.show_metadata_fix(p)
        elif x==similar:
            artist=self.stream_rows[d[1]].get("artist","") if is_stream else next((r[2] for r in self.d.songs() if r[0]==p),"")
            if artist:self.show_similar_artists(artist)
        elif is_stream:
            row=self.stream_rows[d[1]]
            self.d.upsert_stream(row)
            if x==fav:
                for t in (batch_rows if n>1 else [d]):
                    r=self.stream_rows[t[1]];self.d.upsert_stream(r);self.d.stream_fav(r["id"])
                self.statusBar().showMessage("Favorito actualizado" if n<=1 else f"{n} favoritos actualizados",2200)
            elif x==queue:
                for t in (batch_rows if n>1 else [d]):
                    r=self.stream_rows[t[1]];self.d.upsert_stream(r);self.queue.append(("stream",r["id"]))
                self.statusBar().showMessage(f"Cola: {len(self.queue)} canciones",2500)
                if self.view=="Cola":self.render_queue()
            elif x==playnext:
                items=[]
                for t in (batch_rows if n>1 else [d]):
                    r=self.stream_rows[t[1]];self.d.upsert_stream(r);items.append(("stream",r["id"]))
                self.queue[0:0]=items
                self.statusBar().showMessage("Sonará a continuación" if n<=1 else f"{n} canciones sonarán a continuación",2500)
                if self.view=="Cola":self.render_queue()
            elif x==pl:
                self.addpl_stream_multi([self.stream_rows[t[1]] for t in batch_rows]) if n>1 else self.addpl_stream(row)
            elif x==lyrics:self.show_lyrics(row.get("artist",""),row.get("title",""))
            elif x==info:self.show_track_info(row,stream=True)
        else:
            if x==fav:
                for bp in (batch_paths if n>1 else [p]):self.d.fav(bp)
                self.refresh()
            elif x==queue:
                for bp in (batch_paths if n>1 else [p]):self.queue.append(("local",bp))
                self.statusBar().showMessage(f"Cola: {len(self.queue)} canciones",2500)
                if self.view=="Cola":self.render_queue()
            elif x==playnext:
                items=[("local",bp) for bp in (batch_paths if n>1 else [p])]
                self.queue[0:0]=items
                self.statusBar().showMessage("Sonará a continuación" if n<=1 else f"{n} canciones sonarán a continuación",2500)
                if self.view=="Cola":self.render_queue()
            elif x==pl:
                self.addpl_multi(batch_paths) if n>1 else self.addpl(p)
            elif x==lyrics:
                r=next((r for r in self.d.songs() if r[0]==p),None)
                if r:self.show_lyrics(r[2],r[1])
            elif x==info:
                r=next((r for r in self.d.songs() if r[0]==p),None)
                if r:self.show_track_info(r)
            elif x==vauto:
                r=next((r for r in self.d.songs() if r[0]==p),None)
                if r:self.local_current={"path":r[0],"title":r[1],"artist":r[2],"album":r[3]};self.find_local_video(True,lambda z:self.statusBar().showMessage("Vídeo asociado" if z else "No encontré un vídeo adecuado",3000))
            elif x==vchoose:
                r=next((r for r in self.d.songs() if r[0]==p),None)
                if r:self.local_current={"path":r[0],"title":r[1],"artist":r[2],"album":r[3]};self.choose_local_video()
            elif x==vclear:self.d.clear_local_video(p);self.statusBar().showMessage("Asociación de vídeo eliminada",2200)
            elif x in acts:self.d.rate(p,acts.index(x));self.refresh()


    def start_radio(self,artist,title=""):
        q=(artist+" "+title+" canciones similares").strip()
        self.nav("Streaming");self.search.setText(q);self.search_youtube()
        self.statusBar().showMessage("Radio iniciada · preparando canciones relacionadas",3000)

    def show_lyrics(self,artist,title):
        if not artist or not title:
            QMessageBox.information(self,"Letra","No hay suficientes metadatos para buscar la letra.");return
        from urllib.parse import quote
        rep=self.net.get(QNetworkRequest(QUrl(f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}")))
        self.statusBar().showMessage("Buscando letra…",2000)
        def done():
            try:data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"));ly=data.get("lyrics","").strip()
            except Exception:ly=""
            rep.deleteLater()
            dlg=QDialog(self);dlg.setWindowTitle(f"Letra · {title}");dlg.resize(650,720);v=QVBoxLayout(dlg)
            h=QLabel(f"{title}\\n{artist}");h.setObjectName("heading");v.addWidget(h)
            box=QTextEdit();box.setReadOnly(True);box.setPlainText(ly or "No encontré una letra disponible para esta canción.");v.addWidget(box,1)
            dlg.exec()
        rep.finished.connect(done)

    def show_track_info(self,row,stream=False):
        if stream:
            text=f"Título: {row.get('title','')}\\nArtista: {row.get('artist','')}\\nFuente: YouTube\\nDuración: {int(row.get('duration',0))//60}:{int(row.get('duration',0))%60:02d}\\nID: {row.get('id','')}"
        else:
            path,title,artist,album,genre,year,duration,fav,rating=row
            try:size=Path(path).stat().st_size/1024/1024
            except Exception:size=0
            text=f"Título: {title}\\nArtista: {artist}\\nÁlbum: {album}\\nAño: {year}\\nGénero: {genre}\\nDuración: {int(duration)//60}:{int(duration)%60:02d}\\nValoración: {rating}/5\\nTamaño: {size:.1f} MB\\nRuta: {path}"
        QMessageBox.information(self,"Información de la canción",text)

    # ---- Descubrimiento de artistas similares -----------------------------
    # ---- Limpieza de metadatos (MusicBrainz) -------------------------------
    def show_metadata_fix(self,path):
        r=next((r for r in self.d.songs() if r[0]==path),None)
        if not r:return
        cur_title,cur_artist,cur_album,cur_year=r[1],r[2],r[3],r[5]
        dlg=QDialog(self);dlg.setWindowTitle("Corregir metadatos");dlg.resize(460,380)
        v=QVBoxLayout(dlg)
        head=QLabel(cur_title);head.setObjectName("dialogTitle");head.setWordWrap(True);v.addWidget(head)
        status=QLabel("Buscando en MusicBrainz…");status.setObjectName("eyebrow");v.addWidget(status)
        rows_container=QVBoxLayout();v.addLayout(rows_container)
        v.addStretch(1)
        btnRow=QHBoxLayout()
        applyBtn=QPushButton("Aplicar seleccionados");applyBtn.setEnabled(False)
        closeBtn=QPushButton("Cerrar");closeBtn.clicked.connect(dlg.reject)
        btnRow.addWidget(closeBtn);btnRow.addWidget(applyBtn);v.addLayout(btnRow)

        state={"checks":{},"mbid":None}

        def populate(sugg):
            if not sugg:
                status.setText("No se encontró una coincidencia confiable en MusicBrainz.");return
            state["mbid"]=sugg.get("mbid")
            status.setText(f"Coincidencia con {sugg.get('score',0)}% de confianza:")
            fields=[("title","Título",cur_title,sugg.get("title")),("artist","Artista",cur_artist,sugg.get("artist")),
                    ("album","Álbum",cur_album,sugg.get("album")),("year","Año",cur_year,sugg.get("year"))]
            for key,label,cur,new in fields:
                if not new or str(new)==str(cur):continue
                cb=QCheckBox(f'{label}: "{cur or "(vacío)"}" → "{new}"');cb.setChecked(True)
                rows_container.addWidget(cb);state["checks"][key]=(cb,new)
            if state["checks"]:applyBtn.setEnabled(True)
            else:status.setText("MusicBrainz no aportó nada nuevo para esta canción.")

        def apply():
            updates={k:v[1] for k,v in state["checks"].items() if v[0].isChecked()}
            if updates:
                self.d.update_metadata(path,mbid=state["mbid"],**updates)
                self._write_file_tags(path,updates)
                self.refresh();self.populate_cards()
                self.statusBar().showMessage("Metadatos actualizados",2500)
            dlg.accept()
        applyBtn.clicked.connect(apply)

        self._mb_search_recording(cur_title,cur_artist,populate)
        dlg.exec()

    def start_metadata_cleanup_scan(self):
        if getattr(self,"_mbclean_active",False):
            self.statusBar().showMessage("Ya hay una limpieza de metadatos en curso",2500);return
        rows=self.d.needs_metadata_cleanup()
        if not rows:
            self.statusBar().showMessage("No encontré canciones con metadatos incompletos",3000);return
        self._mbclean_queue=list(rows);self._mbclean_total=len(rows);self._mbclean_done=0
        self._mbclean_suggestions=[];self._mbclean_active=True
        self.statusBar().showMessage(f"Analizando metadatos: 0/{self._mbclean_total} (respeta 1 consulta/seg. a MusicBrainz)",2500)
        self._mbcleanTimer=QTimer(self);self._mbcleanTimer.setInterval(1100);self._mbcleanTimer.timeout.connect(self._mbclean_step);self._mbcleanTimer.start()

    def stop_metadata_cleanup_scan(self):
        self._mbclean_active=False
        if getattr(self,"_mbcleanTimer",None):self._mbcleanTimer.stop()
        self.statusBar().showMessage("Limpieza de metadatos detenida",2200)

    def _mbclean_step(self):
        if not getattr(self,"_mbclean_active",False) or not self._mbclean_queue:
            if getattr(self,"_mbcleanTimer",None):self._mbcleanTimer.stop()
            self._mbclean_active=False
            self._show_metadata_review()
            return
        path,title,artist,album,genre,year=self._mbclean_queue.pop(0)
        def on_result(sugg,path=path,title=title,artist=artist,album=album,year=year):
            self._mbclean_done+=1
            self.statusBar().showMessage(f"Analizando metadatos: {self._mbclean_done}/{self._mbclean_total}",1500)
            if sugg:
                changes={}
                if sugg.get("artist") and artist in ("Artista desconocido",""," ") and sugg["artist"]!=artist:changes["artist"]=sugg["artist"]
                if sugg.get("album") and album in ("Álbum desconocido",""," ") and sugg["album"]!=album:changes["album"]=sugg["album"]
                if sugg.get("year") and not year:changes["year"]=sugg["year"]
                if changes:
                    self._mbclean_suggestions.append((path,title,artist,album,year,changes,sugg.get("mbid")))
        lookup_title=title if title else Path(path).stem
        lookup_artist=artist if artist!="Artista desconocido" else ""
        self._mb_search_recording(lookup_title,lookup_artist,on_result)

    def _show_metadata_review(self):
        if not self._mbclean_suggestions:
            self.statusBar().showMessage("No encontré sugerencias confiables para completar tu biblioteca",3800);return
        FIELD_LABELS={"artist":"Artista","album":"Álbum","year":"Año"}
        dlg=QDialog(self);dlg.setWindowTitle("Revisar metadatos sugeridos");dlg.resize(560,600)
        v=QVBoxLayout(dlg)
        head=QLabel(f"{len(self._mbclean_suggestions)} canciones con sugerencias");head.setObjectName("dialogTitle");v.addWidget(head)
        info=QLabel("Solo se completan campos vacíos o genéricos; nada que ya tengas se sobreescribe sin tu confirmación.")
        info.setWordWrap(True);info.setObjectName("eyebrow");v.addWidget(info)
        scroll=QScrollArea();scroll.setObjectName("lyricsScroll");scroll.setWidgetResizable(True);scroll.setFrameShape(QFrame.Shape.NoFrame)
        inner=QWidget();inner.setObjectName("lyricsInner");innerV=QVBoxLayout(inner)
        row_checks=[]
        for path,title_,artist,album,year,changes,mbid in self._mbclean_suggestions:
            cur_map={"artist":artist,"album":album,"year":year}
            desc=" · ".join(f'{FIELD_LABELS.get(k,k)}: "{cur_map.get(k) or "(vacío)"}" → "{v}"' for k,v in changes.items())
            box=QCheckBox(f"{title_ or Path(path).stem}\n{desc}");box.setChecked(True)
            innerV.addWidget(box);row_checks.append((box,path,changes,mbid))
        scroll.setWidget(inner);v.addWidget(scroll,1)
        btnRow=QHBoxLayout()
        cancelBtn=QPushButton("Cancelar");cancelBtn.clicked.connect(dlg.reject)
        applyBtn=QPushButton("Aplicar seleccionados");applyBtn.clicked.connect(lambda:self._apply_metadata_review(row_checks,dlg))
        btnRow.addWidget(cancelBtn);btnRow.addWidget(applyBtn);v.addLayout(btnRow)
        dlg.exec()

    def _apply_metadata_review(self,row_checks,dlg):
        n=0
        for box,path,changes,mbid in row_checks:
            if box.isChecked():
                self.d.update_metadata(path,mbid=mbid,**changes)
                self._write_file_tags(path,changes)
                n+=1
        self.refresh();self.populate_cards()
        self.statusBar().showMessage(f"{n} canciones actualizadas",3000)
        dlg.accept()

    def show_similar_artists(self,artist_name):
        dlg=QDialog(self);dlg.setWindowTitle("Artistas similares");dlg.resize(440,540)
        v=QVBoxLayout(dlg)
        title=QLabel(f"Parecido a {artist_name}");title.setObjectName("dialogTitle");title.setWordWrap(True);v.addWidget(title)
        status=QLabel("Buscando artistas similares…");status.setObjectName("eyebrow");v.addWidget(status)
        listw=QListWidget();listw.setObjectName("miniList");v.addWidget(listw,1)
        hint=QLabel("Toca un artista para buscarlo.");hint.setObjectName("eyebrow");v.addWidget(hint)
        close=QPushButton("Cerrar");close.clicked.connect(dlg.accept);v.addWidget(close)

        def populate(results,source):
            listw.clear()
            if not results:
                status.setText("No se encontraron artistas similares.");return
            status.setText(f"{len(results)} artistas similares · fuente: {source}")
            for name,match,_img in results:
                label=name if match is None else f"{name}   ·   {int(round(match*100))}%"
                it=QListWidgetItem(label);it.setData(Qt.ItemDataRole.UserRole,name);listw.addItem(it)

        def on_click(it):
            name=it.data(Qt.ItemDataRole.UserRole); dlg.accept()
            self.search.setText(name); self.refresh()

        listw.itemClicked.connect(on_click)
        self.fetch_similar_artists(artist_name,populate)
        dlg.exec()

    def fetch_similar_artists(self,artist_name,callback):
        if getattr(self,"lastfm_key",""):
            self._similar_via_lastfm(artist_name,callback)
        else:
            self._similar_via_listenbrainz(artist_name,callback)

    def _similar_via_lastfm(self,artist_name,callback):
        url=QUrl("https://ws.audioscrobbler.com/2.0/");q=QUrlQuery()
        for k,v in {"method":"artist.getsimilar","artist":artist_name,"api_key":self.lastfm_key,"format":"json","limit":"25","autocorrect":"1"}.items():
            q.addQueryItem(k,v)
        url.setQuery(q)
        req=QNetworkRequest(url);req.setRawHeader(b"User-Agent",f"Mozilla/5.0 Sakukelly/{APP_VERSION}".encode())
        rep=self.net.get(req)
        def handle(rep=rep):
            results=[]
            try:
                data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
                for a in data.get("similarartists",{}).get("artist",[]):
                    name=a.get("name")
                    try:match=float(a.get("match"))
                    except Exception:match=None
                    if name:results.append((name,match,None))
            except Exception:pass
            rep.deleteLater()
            if results:callback(results,"Last.fm")
            else:self._similar_via_listenbrainz(artist_name,callback)  # respaldo si Last.fm no encontró nada
        rep.finished.connect(handle)

    def _similar_via_listenbrainz(self,artist_name,callback):
        self._resolve_artist_mbid(artist_name,lambda mbid:self._similar_lb_step2(mbid,callback))

    def _similar_lb_step2(self,mbid,callback):
        if not mbid:
            callback([],"ListenBrainz");return
        url=QUrl("https://labs.api.listenbrainz.org/similar-artists/json");q=QUrlQuery()
        q.addQueryItem("artist_mbids",mbid)
        q.addQueryItem("algorithm","session_based_days_7500_session_300_contribution_5_threshold_10_limit_100_filter_True_skip_30")
        url.setQuery(q)
        req=QNetworkRequest(url);req.setRawHeader(b"User-Agent",f"Sakukelly-MusicPlayer/{APP_VERSION}".encode())
        rep=self.net.get(req)
        def handle(rep=rep):
            results=[]
            try:
                data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
                results=self._parse_lb_similar(data)
            except Exception:pass
            rep.deleteLater()
            callback(results,"ListenBrainz")
        rep.finished.connect(handle)

    def _parse_lb_similar(self,data):
        """Analiza la respuesta de ListenBrainz Labs de forma flexible."""
        candidates=[]
        if isinstance(data,list):candidates=data
        elif isinstance(data,dict):
            for key in ("similar_artists","artists","data","results"):
                if isinstance(data.get(key),list):candidates=data[key];break
        out=[]
        for item in candidates:
            if not isinstance(item,dict):continue
            name=item.get("name") or item.get("artist_name")
            if name:out.append((name,None,None))
        return out

    def _mb_search_recording(self,title,artist,callback):
        """Busca una grabación en MusicBrainz por título/artista. Solo llama
        al callback con una sugerencia si la coincidencia es de alta
        confianza (score>=88), para no arriesgar corromper datos correctos."""
        from urllib.parse import quote
        parts=[]
        if title:parts.append(f'recording:"{title}"')
        if artist and artist!="Artista desconocido":parts.append(f'artist:"{artist}"')
        if not parts:
            callback(None);return
        query=" AND ".join(parts)
        req=QNetworkRequest(QUrl("https://musicbrainz.org/ws/2/recording/?query="+quote(query)+"&fmt=json&limit=5"))
        req.setRawHeader(b"User-Agent",f"Sakukelly-MusicPlayer/{APP_VERSION}".encode())
        rep=self.net.get(req)
        def handle(rep=rep,callback=callback):
            suggestion=None
            try:
                data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
                recs=data.get("recordings",[])
                if recs:
                    best=max(recs,key=lambda r:r.get("score",0))
                    if best.get("score",0)>=88:
                        credits=best.get("artist-credit",[])
                        s_artist=credits[0].get("name") if credits else None
                        s_album=None;s_year=None
                        releases=best.get("releases",[])
                        if releases:
                            s_album=releases[0].get("title")
                            date=releases[0].get("date","") or ""
                            if date:s_year=date.split("-")[0]
                        suggestion={"title":best.get("title"),"artist":s_artist,"album":s_album,"year":s_year,
                            "mbid":best.get("id"),"score":best.get("score",0)}
            except Exception:pass
            rep.deleteLater()
            callback(suggestion)
        rep.finished.connect(handle)

    def _write_file_tags(self,path,updates):
        """Escribe los campos corregidos también en el archivo (no solo en
        la base de datos interna), para que la corrección sea duradera."""
        if not MF or not updates:return
        try:
            f=MF(path,easy=True)
            if not f:return
            key_map={"title":"title","artist":"artist","album":"album","year":"date","genre":"genre"}
            for k,v in updates.items():
                tagkey=key_map.get(k)
                if tagkey and v:
                    try:f[tagkey]=str(v)
                    except Exception:pass
            f.save()
        except Exception:pass

    def _resolve_artist_mbid(self,artist_name,callback):
        if not artist_name:callback(None);return
        if self.d.artist_mbid_known(artist_name):
            callback(self.d.get_artist_mbid(artist_name));return
        from urllib.parse import quote
        req=QNetworkRequest(QUrl("https://musicbrainz.org/ws/2/artist/?query="+quote(f'artist:"{artist_name}"')+"&fmt=json&limit=1"))
        req.setRawHeader(b"User-Agent",f"Sakukelly-MusicPlayer/{APP_VERSION}".encode())
        rep=self.net.get(req)
        def handle(rep=rep,artist_name=artist_name,callback=callback):
            mbid=None
            try:
                data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
                artists=data.get("artists",[])
                if artists:mbid=artists[0].get("id")
            except Exception:pass
            self.d.set_artist_mbid(artist_name,mbid)
            rep.deleteLater()
            callback(mbid)
        rep.finished.connect(handle)

    def addpl(self,p):
        opts=self.d.pls()+["+ Nueva playlist"]; n,ok=QInputDialog.getItem(self,"Playlist","Selecciona:",opts,0,False)
        if not ok:return
        if n=="+ Nueva playlist":
            n,ok=QInputDialog.getText(self,"Nueva playlist","Nombre:")
            if not ok or not n.strip():return
            n=n.strip(); self.d.newpl(n)
        self.d.addpl(n,p); self.reload_playlists()

    def addpl_multi(self,paths):
        if not paths:return
        opts=self.d.pls()+["+ Nueva playlist"]
        n,ok=QInputDialog.getItem(self,"Playlist",f"Selecciona (se añadirán {len(paths)} canciones):",opts,0,False)
        if not ok:return
        if n=="+ Nueva playlist":
            n,ok=QInputDialog.getText(self,"Nueva playlist","Nombre:")
            if not ok or not n.strip():return
            n=n.strip(); self.d.newpl(n)
        for p in paths:self.d.addpl(n,p)
        self.reload_playlists(); self.statusBar().showMessage(f"{len(paths)} canciones añadidas a {n}",2800)

    def addpl_stream(self,row):
        opts=self.d.pls()+["+ Nueva playlist"];n,ok=QInputDialog.getItem(self,"Playlist","Selecciona:",opts,0,False)
        if not ok:return
        if n=="+ Nueva playlist":
            n,ok=QInputDialog.getText(self,"Nueva playlist","Nombre:")
            if not ok or not n.strip():return
            n=n.strip();self.d.newpl(n)
        self.d.upsert_stream(row);self.d.add_stream_pl(n,row["id"]);self.reload_playlists()
        self.statusBar().showMessage(f"Añadida a {n}",2200)

    def addpl_stream_multi(self,rows):
        if not rows:return
        opts=self.d.pls()+["+ Nueva playlist"]
        n,ok=QInputDialog.getItem(self,"Playlist",f"Selecciona (se añadirán {len(rows)} canciones):",opts,0,False)
        if not ok:return
        if n=="+ Nueva playlist":
            n,ok=QInputDialog.getText(self,"Nueva playlist","Nombre:")
            if not ok or not n.strip():return
            n=n.strip(); self.d.newpl(n)
        for row in rows:
            self.d.upsert_stream(row);self.d.add_stream_pl(n,row["id"])
        self.reload_playlists(); self.statusBar().showMessage(f"{len(rows)} canciones añadidas a {n}",2800)

    def pos(self,p):
        self._last_pos_ms=p; self._last_pos_time=time.time()
        self.sl.setValue(p); d=self.p.duration(); f=lambda x:f"{x//60000}:{(x//1000)%60:02d}"; self.tm.setText(f(p)); self.tt.setText(f(d))
        if not self.stream_current and d>0 and not self.crossfade_started:
            if self.crossfade and p>=max(0,d-self.crossfade_ms): self._begin_crossfade()
            elif self.gapless and p>=max(0,d-GAPLESS_MS): self._begin_crossfade(GAPLESS_MS)
        self._update_lyrics_highlight(p)
        if not getattr(self,"_scrobble_done",True) and getattr(self,"_scrobble_threshold_ms",None) and p>=self._scrobble_threshold_ms:
            self._scrobble_done=True; self._queue_scrobble()

    # ---- Letras sincronizadas (estilo Apple Music) ----------------------
    def toggle_lyrics(self,checked):
        if checked:
            self._pre_lyrics_hero=self.hero.isVisible();self._pre_lyrics_cards=self.cards.isVisible()
            self.hero.hide();self.cards.hide();self.section.hide();self.list.hide();self.lyricsPanel.show()
            # El panel acaba de hacerse visible: su geometría todavía no está
            # asentada por Qt en este mismo tick (viewport().width() daría un
            # valor viejo/por defecto). Diferimos la carga un ciclo de evento
            # para que el layout ya esté resuelto y las líneas no salgan
            # amontonadas la primera vez que se abre.
            QTimer.singleShot(0,self.load_lyrics_for_current)
        else:
            self.lyricsPanel.hide();self.section.show();self.list.show()
            self.hero.setVisible(getattr(self,"_pre_lyrics_hero",self.view=="Inicio"))
            self.cards.setVisible(getattr(self,"_pre_lyrics_cards",self.view=="Inicio"))

    def _clear_lyrics_layout(self):
        while self.lyricsLayout.count():
            it=self.lyricsLayout.takeAt(0);w=it.widget()
            if w:w.deleteLater()
        self._lyrics_labels=[]

    def _make_lyric_label(self,text):
        lbl=KaraokeLabel(text)
        lbl.setObjectName("lyricLine");lbl.setWordWrap(True);lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # El ancho máximo se fija en _fit_lyric_label (tras el layout real),
        # no aquí: fijarlo en el momento de crear la etiqueta usaba un ancho
        # de viewport obsoleto y producía líneas amontonadas/recortadas.
        return lbl

    def _adjust_lyrics_offset(self,delta):
        self.lyrics_offset=round(getattr(self,"lyrics_offset",0.0)+delta,2)
        sign="+" if self.lyrics_offset>0 else ""
        txt=f"Sync: {sign}{self.lyrics_offset:.1f}s"
        if hasattr(self,"offset_label"):self.offset_label.setText(txt)
        self.save_settings()
        self._lyrics_current_idx=-1

    def _reset_lyrics_offset(self):
        self.lyrics_offset=0.0
        txt="Sync: 0.0s"
        if hasattr(self,"offset_label"):self.offset_label.setText(txt)
        self.save_settings()
        self._lyrics_current_idx=-1

    def _fit_lyric_label(self,lb):
        """Fija el ancho máximo con la geometría YA asentada del panel y
        recalcula la altura según ese ancho. Se hace aquí (no al crear la
        etiqueta) porque justo al abrir el panel de letras Qt todavía no le
        había dado su tamaño final; calcularlo en ese momento usaba un ancho
        de viewport obsoleto y las líneas salían amontonadas/recortadas
        hasta que algo más disparaba un nuevo layout (p. ej. cambiar de
        canción). También corre en cada resize para que el ajuste de línea
        siga siendo correcto si la ventana cambia de tamaño."""
        vw=self.lyricsScroll.viewport().width()
        lb.setMaximumWidth(max(320,vw-64) if vw>0 else 860)
        w=lb.width()
        if w>0:lb.setFixedHeight(lb.heightForWidth(w))

    def _fit_all_lyric_labels(self):
        for lb in self._lyrics_labels:self._fit_lyric_label(lb)

    def _show_lyrics_loading(self):
        self._clear_lyrics_layout();self.lyricsScroll.hide()
        self.lyricsEmpty.setText("Buscando letras…");self.lyricsEmpty.show()

    def _show_lyrics_empty(self,msg):
        self._clear_lyrics_layout();self.lyricsScroll.hide()
        self.lyricsEmpty.setText(msg);self.lyricsEmpty.show()

    def _gain_for_path(self,path):
        """Multiplicador lineal de volumen (ReplayGain) a partir de la sonoridad
        medida (LUFS) guardada para esa pista. 1.0 si está desactivado, la
        pista es de streaming, o todavía no se ha analizado."""
        if not getattr(self,"replaygain",False) or not path:return 1.0
        lufs=self.d.get_loudness(path)
        if lufs is None:return 1.0
        gain_db=REPLAYGAIN_TARGET_LUFS-lufs
        return max(0.15,min(3.0,10**(gain_db/20)))

    def _apply_output_volume(self):
        self.au.setVolume(max(0.0,min(1.0,self.base_volume*getattr(self,"_gain_mult",1.0))))

    def _on_player_error(self,error,error_string):
        if error==QMediaPlayer.Error.NoError:return
        try:self.p.stop()
        except Exception:pass
        if self.stream_current:
            self.statusBar().showMessage("No se pudo reproducir este vídeo de YouTube (enlace caducado o formato no compatible). Pasando al siguiente...",4000)
            QTimer.singleShot(1500, self.next)
        else:
            self.statusBar().showMessage(f"Error de reproducción: {error_string or error}",5000)

    def _on_track_settled(self):
        path=self.local_current.get("path") if self.local_current else None
        self._gain_mult=self._gain_for_path(path)
        self._apply_output_volume()
        self.load_lyrics_for_current()
        self.update_fav_btn()
        self._mpris_update()
        self._scrobble_now_playing()

    def _setup_mpris(self):
        self._mpris_service=None
        if not DBUS_AVAILABLE or not getattr(self,"mpris_enabled",True):return
        try:
            bus=dbus.SessionBus()
            name=dbus.service.BusName(MPRIS_BUS_NAME,bus)
            self._mpris_bus_name_obj=name
            self._mpris_service=MPRISService(self,bus)
        except Exception:
            self._mpris_service=None  # sin bus de sesión disponible: seguimos sin MPRIS

    def _mpris_metadata(self):
        src=self.local_current or self.stream_current
        if not src:
            return {"mpris:trackid":dbus.ObjectPath("/org/mpris/MediaPlayer2/sakukelly/NoTrack")}
        title=str(src.get("title") or "");artist=str(src.get("artist") or "");album=str(src.get("album") or "")
        key=str(src.get("path") or src.get("id") or title or "x")
        trackid="/org/mpris/MediaPlayer2/sakukelly/track/"+hashlib.md5(key.encode("utf-8","ignore")).hexdigest()[:16]
        meta={
            "mpris:trackid":dbus.ObjectPath(trackid),
            "mpris:length":dbus.Int64(int(self.p.duration())*1000),
            "xesam:title":title,
            "xesam:artist":dbus.Array([artist] if artist else [],signature="s"),
            "xesam:album":album,
        }
        if MPRIS_ART_CACHE.exists():meta["mpris:artUrl"]="file://"+str(MPRIS_ART_CACHE)
        return meta

    def _mpris_update(self):
        svc=getattr(self,"_mpris_service",None)
        if not svc:return
        try:
            st=self.p.playbackState()
            status="Playing" if st==QMediaPlayer.PlaybackState.PlayingState else ("Paused" if st==QMediaPlayer.PlaybackState.PausedState else "Stopped")
            changed=dbus.Dictionary({"PlaybackStatus":status,"Metadata":dbus.Dictionary(self._mpris_metadata(),signature="sv")},signature="sv")
            svc.PropertiesChanged(MPRIS_PLAYER_IFACE,changed,dbus.Array([],signature="s"))
        except Exception:pass

    def _mpris_shutdown(self):
        try:
            if getattr(self,"_mpris_bus_name_obj",None):
                del self._mpris_bus_name_obj
        except Exception:pass

    def _setup_tray(self):
        self.tray=None

    def _tray_show(self):
        self.showNormal();self.raise_();self.activateWindow()

    def _tray_quit(self):
        self.close()

    def _on_tray_activated(self,reason):
        pass

    # ---- Scrobbling (ListenBrainz + Last.fm) ------------------------------
    def _scrobble_now_playing(self):
        src=self.local_current or self.stream_current
        self._scrobble_threshold_ms=None; self._scrobble_done=True
        if not src:return
        dur_ms=self.p.duration()
        dur_s=(dur_ms/1000) if dur_ms else float(src.get("duration") or 0)
        artist=str(src.get("artist") or "");title=str(src.get("title") or "")
        if not artist or not title:return
        self._scrobble_meta={"artist":artist,"title":title,"album":str(src.get("album") or ""),
            "duration_s":int(dur_s),"started_at":int(time.time())}
        if dur_s>=30:
            self._scrobble_threshold_ms=int(min(240000,(dur_ms/2) if dur_ms else dur_s*500))
            self._scrobble_done=False
        if getattr(self,"lb_enabled",False) and self.lb_token:
            self.lb_service.now_playing(self.lb_token,artist,title,self._scrobble_meta["album"],dur_s)
        if getattr(self,"lastfm_enabled",False) and self.lastfm_session:
            self.lastfm_service.now_playing(self.lastfm_key,self.lastfm_secret,self.lastfm_session,self._scrobble_meta)

    def _queue_scrobble(self):
        m=getattr(self,"_scrobble_meta",None)
        if not m:return
        if getattr(self,"lb_enabled",False) and self.lb_token:
            self.d.queue_scrobble("listenbrainz",m["artist"],m["title"],m["album"],m["duration_s"],m["started_at"])
        if getattr(self,"lastfm_enabled",False) and self.lastfm_session:
            self.d.queue_scrobble("lastfm",m["artist"],m["title"],m["album"],m["duration_s"],m["started_at"])
        self.flush_scrobble_queue()

    def _on_scrobble_result(self,sid,ok):
        # callback compartido por ListenBrainz y Last.fm: si el envio tuvo
        # exito se descarta de la cola local, si no se reintenta mas tarde.
        if sid is None:return
        self.d.drop_scrobble(sid) if ok else self.d.bump_scrobble_attempts(sid)

    def flush_scrobble_queue(self):
        if getattr(self,"lb_enabled",False) and self.lb_token:
            for sid,artist,title,album,dur,ts,attempts in self.d.pending_scrobbles("listenbrainz"):
                self.lb_service.submit_scrobble(self.lb_token,sid,artist,title,album,dur,ts,self._on_scrobble_result)
        if getattr(self,"lastfm_enabled",False) and self.lastfm_session:
            for sid,artist,title,album,dur,ts,attempts in self.d.pending_scrobbles("lastfm"):
                self.lastfm_service.submit_scrobble(self.lastfm_key,self.lastfm_secret,self.lastfm_session,sid,artist,title,album,dur,ts,self._on_scrobble_result)

    # ---- Last.fm / ListenBrainz: autenticación -----------------------------
    # La logica de protocolo (firma, peticiones HTTP, parseo de respuesta)
    # vive en sakukelly/services/{lastfm,listenbrainz}.py; aqui solo se
    # coordinan las credenciales (que son configuracion de esta ventana) y
    # la interfaz de usuario (statusBar, guardado de ajustes).
    def lastfm_start_auth(self):
        self.lastfm_service.start_auth(
            self.lastfm_key,self.lastfm_secret,
            on_token=lambda token:(setattr(self,"_lastfm_pending_token",token),
                self.statusBar().showMessage("Autoriza Sakukelly en la página que se abrió y vuelve a pulsar 'Confirmar conexión'",7000)),
            on_error=lambda msg:self.statusBar().showMessage(msg,4000))

    def lastfm_finish_auth(self):
        token=getattr(self,"_lastfm_pending_token",None)
        if not token:
            self.statusBar().showMessage("Primero pulsa 'Conectar con Last.fm'",3000);return
        def on_session(key):
            self.lastfm_session=key; self.lastfm_enabled=True; self.save_settings()
            self.statusBar().showMessage("Conectado a Last.fm correctamente",3000)
        self.lastfm_service.finish_auth(self.lastfm_key,self.lastfm_secret,token,
            on_session=on_session,
            on_error=lambda msg:self.statusBar().showMessage(msg,4000))

    # ---- Análisis de volumen (ReplayGain real, EBU R128 vía ffmpeg) ------
    def start_loudness_scan(self):
        if getattr(self,"_loudness_scan_active",False):
            self.statusBar().showMessage("Ya hay un análisis de volumen en curso",2500);return
        self._loudness_queue=self.d.unanalyzed_paths()
        if not self._loudness_queue:
            self.statusBar().showMessage("Toda tu biblioteca ya tiene el volumen analizado",3000);return
        self._loudness_scan_active=True; self._loudness_total=len(self._loudness_queue); self._loudness_done=0
        self.statusBar().showMessage(f"Analizando volumen: 0/{self._loudness_total}",2000)
        self._scan_next_loudness()

    def stop_loudness_scan(self):
        self._loudness_scan_active=False
        proc=getattr(self,"_loudness_proc",None)
        if proc and proc.state()!=QProcess.ProcessState.NotRunning:proc.kill()
        self.statusBar().showMessage("Análisis de volumen detenido",2500)

    def _scan_next_loudness(self):
        if not getattr(self,"_loudness_scan_active",False):return
        if not self._loudness_queue:
            self._loudness_scan_active=False
            self.statusBar().showMessage(f"Análisis de volumen completo: {self._loudness_done} canciones",4000)
            return
        path=self._loudness_queue.pop(0)
        proc=QProcess(self); proc.setProgram(FFMPEG)
        proc.setArguments(["-hide_banner","-i",path,"-af","loudnorm=print_format=json","-f","null","-"])
        proc.finished.connect(lambda code,status,pa=path:self._on_loudness_finished(pa))
        self._loudness_proc=proc
        try:proc.start()
        except Exception:self._on_loudness_finished(path)

    def _on_loudness_finished(self,path):
        try:
            out=bytes(self._loudness_proc.readAllStandardError()).decode("utf-8","ignore")
            m=re.search(r"\{[^{}]*\"input_i\"[^{}]*\}",out)
            if m:
                data=json.loads(m.group(0)); lufs=float(data.get("input_i","0"))
                if -70<lufs<0:self.d.set_loudness(path,lufs)
        except Exception:pass
        self._loudness_done+=1
        if self._loudness_done%3==0 or self._loudness_done==self._loudness_total:
            self.statusBar().showMessage(f"Analizando volumen: {self._loudness_done}/{self._loudness_total}",2000)
        self._scan_next_loudness()

    def load_lyrics_for_current(self):
        if not getattr(self,"lyricsPanel",None) or not self.lyricsPanel.isVisible():return
        if not self.local_current and not self.stream_current:
            self._show_lyrics_empty("Reproduce una canción para ver sus letras.");return
        self._lyrics_token+=1;token=self._lyrics_token
        src=self.local_current or self.stream_current
        title=src.get("title","");artist=src.get("artist","")
        path=self.local_current.get("path") if self.local_current else None
        self._show_lyrics_loading()
        if path:
            lrc=Path(path).with_suffix(".lrc")
            if lrc.exists():
                try:
                    lines=parse_lrc(lrc.read_text(encoding="utf-8",errors="ignore"))
                    if lines:self._apply_lyrics(lines,True,token);return
                except Exception:pass
            emb=embedded_synced_lyrics(path)
            if emb:
                lines=parse_lrc(emb)
                if lines:self._apply_lyrics(lines,True,token);return
        cache=LYRICS_CACHE/f"{lyrics_cache_key(artist,title)}.lrc"
        if cache.exists():
            try:
                cached=json.loads(cache.read_text(encoding="utf-8"))
                lines=parse_lrc(cached.get("synced","")) if cached.get("synced") else []
                if lines:self._apply_lyrics(lines,True,token);return
                if cached.get("plain"):self._apply_plain_lyrics(cached["plain"],token);return
                # En streaming no usamos caché negativo viejo para permitir encontrar letras con nuevos patrones
                if cached.get("none") and not self.stream_current:
                    self._show_lyrics_empty("No se encontraron letras para esta canción.");return
            except Exception:pass
        if title or artist:
            cache_key=lyrics_cache_key(artist,title)
            queries=clean_lyrics_query(title,artist) or [(artist,title)]
            # Para streaming construimos una lista enriquecida de queries (strict, full-text q= y title-only)
            search_requests=[]
            for a,t in queries:
                if a and t:
                    search_requests.append(("strict",a,t))
                    search_requests.append(("query",a,f"{a} {t}"))
                elif t:
                    search_requests.append(("query","",t))
            if not search_requests:search_requests=[("query",artist or "",title or artist)]
            self._fetch_lrclib_sequence(search_requests,0,token,cache_key,artist,title)
        else:
            self._show_lyrics_empty("Faltan datos de título/artista para buscar la letra.")

    def _fetch_lrclib(self,title,artist,token,cache_key=None):
        cache_key=cache_key or lyrics_cache_key(artist,title)
        queries=clean_lyrics_query(title,artist) or [(artist,title)]
        search_requests=[("strict",a,t) for a,t in queries]
        self._fetch_lrclib_sequence(search_requests,0,token,cache_key,artist,title)

    def _fetch_lrclib_sequence(self,requests,idx,token,cache_key,orig_artist="",orig_title=""):
        if token!=self._lyrics_token:return
        if idx>=len(requests):
            # Fallback final a lyrics.ovh si LRCLIB no devolvió resultados
            self._fetch_ovh_fallback(orig_artist,orig_title,token,cache_key)
            return
        kind,art,tit=requests[idx]
        url=QUrl("https://lrclib.net/api/search");q=QUrlQuery()
        if kind=="strict":
            q.addQueryItem("track_name",tit)
            if art:q.addQueryItem("artist_name",art)
        else:
            q.addQueryItem("q",tit)
        url.setQuery(q)
        req=QNetworkRequest(url);req.setRawHeader(b"User-Agent",f"Mozilla/5.0 Sakukelly/{APP_VERSION} (+lyrics; https://lrclib.net)".encode())
        rep=self.net.get(req)
        rep.finished.connect(lambda r=rep,tok=token,reqs=requests,i=idx,ck=cache_key,oa=orig_artist,ot=orig_title:self._on_lrclib_reply_seq(r,tok,reqs,i,ck,oa,ot))

    def _on_lrclib_reply_seq(self,rep,token,requests,idx,cache_key,orig_artist="",orig_title=""):
        try:data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
        except Exception:data=None
        rep.deleteLater()
        if token!=self._lyrics_token:return
        synced=None;plain=None
        if isinstance(data,list):
            for cand in data:
                if not synced and cand.get("syncedLyrics"):synced=cand["syncedLyrics"]
                if not plain and cand.get("plainLyrics"):plain=cand["plainLyrics"]
                if synced:break
        if synced or plain:
            cache=LYRICS_CACHE/f"{cache_key}.lrc"
            try:cache.write_text(json.dumps({"synced":synced or "","plain":plain or "","none":False}),encoding="utf-8")
            except Exception:pass
            if synced:
                lines=parse_lrc(synced)
                if lines:self._apply_lyrics(lines,True,token);return
            if plain:
                self._apply_plain_lyrics(plain,token);return
        self._fetch_lrclib_sequence(requests,idx+1,token,cache_key,orig_artist,orig_title)

    def _fetch_ovh_fallback(self,artist,title,token,cache_key):
        if token!=self._lyrics_token:return
        art=quote(artist or ""); tit=quote(title or "")
        if not art or not tit:
            cache=LYRICS_CACHE/f"{cache_key}.lrc"
            try:cache.write_text(json.dumps({"synced":"","plain":"","none":True}),encoding="utf-8")
            except Exception:pass
            if token==self._lyrics_token:self._show_lyrics_empty("No se encontraron letras para esta canción.")
            return
        url=QUrl(f"https://api.lyrics.ovh/v1/{art}/{tit}")
        req=QNetworkRequest(url)
        rep=self.net.get(req)
        rep.finished.connect(lambda r=rep,tok=token,ck=cache_key:self._on_ovh_reply(r,tok,ck))

    def _on_ovh_reply(self,rep,token,cache_key):
        try:
            data=json.loads(bytes(rep.readAll()).decode("utf-8","ignore"))
            ly=data.get("lyrics","").strip()
        except Exception:ly=""
        rep.deleteLater()
        if token!=self._lyrics_token:return
        if ly:
            cache=LYRICS_CACHE/f"{cache_key}.lrc"
            try:cache.write_text(json.dumps({"synced":"","plain":ly,"none":False}),encoding="utf-8")
            except Exception:pass
            self._apply_plain_lyrics(ly,token)
        else:
            cache=LYRICS_CACHE/f"{cache_key}.lrc"
            try:cache.write_text(json.dumps({"synced":"","plain":"","none":True}),encoding="utf-8")
            except Exception:pass
            if token==self._lyrics_token:self._show_lyrics_empty("No se encontraron letras para esta canción.")

    def _apply_plain_lyrics(self,text,token):
        if token!=self._lyrics_token:return
        self._clear_lyrics_layout();self.lyricsEmpty.hide();self.lyricsScroll.show()
        note=QLabel("Letra sin sincronización disponible");note.setObjectName("lyricsBadge");self.lyricsLayout.addWidget(note)
        for line in text.splitlines():
            line=line.strip()
            if not line:continue
            lbl=self._make_lyric_label(line)
            self.lyricsLayout.addWidget(lbl)
        self._lyrics_lines=[];self._lyrics_synced=False;self._lyrics_current_idx=-1

    def _apply_lyrics(self,lines,synced,token):
        if token!=self._lyrics_token:return
        self._clear_lyrics_layout();self.lyricsEmpty.hide();self.lyricsScroll.show()
        for _,text in lines:
            lbl=self._make_lyric_label(text)
            lbl.setProperty("current",False);self.lyricsLayout.addWidget(lbl);self._lyrics_labels.append(lbl)
        self._lyrics_lines=lines;self._lyrics_synced=synced;self._lyrics_current_idx=-1
        self._lyrics_scroll_idx=-2;self._lyr_tick=0
        QTimer.singleShot(0,self._fit_all_lyric_labels)

    def _tick_lyrics_smooth(self):
        if not getattr(self, "lyricsPanel", None) or not self.lyricsPanel.isVisible():
            return
        if self.p.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            elapsed = (time.time() - getattr(self, "_last_pos_time", time.time())) * 1000.0
            pos_ms = getattr(self, "_last_pos_ms", 0) + elapsed
        else:
            pos_ms = getattr(self, "_last_pos_ms", 0)
        self._update_lyrics_highlight(pos_ms)

    def _update_lyrics_highlight(self,ms):
        if not self._lyrics_synced or not self._lyrics_lines:return
        panel_visible=bool(getattr(self,"lyricsPanel",None) and self.lyricsPanel.isVisible())
        if not panel_visible:return
        offset=getattr(self,"lyrics_offset",0.0)
        t=(ms/1000.0)+offset
        idx=-1
        for i,(ts,_) in enumerate(self._lyrics_lines):
            if ts<=t:idx=i
            else:break
        progress=0.0
        if 0<=idx<len(self._lyrics_lines):
            t_start=self._lyrics_lines[idx][0]
            t_end=self._lyrics_lines[idx+1][0] if idx+1<len(self._lyrics_lines) else (t_start+4.0)
            dur=max(0.15,t_end-t_start)
            progress=max(0.0,min(1.0,(t-t_start)/dur))

        _t=THEMES.get(self.theme, THEMES["noche"])
        acc1=_t.get("accent","#7c3aed"); acc2=_t.get("accent2","#a78bfa")
        dim_c=_t.get("dim","rgba(255,255,255,0.45)")

        if idx!=self._lyrics_current_idx:
            old=self._lyrics_current_idx;self._lyrics_current_idx=idx
            if 0<=old<len(self._lyrics_labels):
                lb=self._lyrics_labels[old]
                if isinstance(lb, KaraokeLabel):
                    lb.set_active_progress(False,0.0,accent1=acc1,accent2=acc2,dim_color=dim_c)
                else:
                    lb.setProperty("current",False);lb.update()
                self._fit_lyric_label(lb)

        if 0<=idx<len(self._lyrics_labels):
            lb=self._lyrics_labels[idx]
            if isinstance(lb, KaraokeLabel):
                lb.set_active_progress(True,progress,accent1=acc1,accent2=acc2,dim_color=dim_c)
            else:
                lb.setProperty("current",True);lb.update()
            if idx!=getattr(self,"_lyrics_scroll_idx",-2):
                self._lyrics_scroll_idx=idx;self._scroll_to_lyric(lb)

    def _scroll_to_lyric(self,label):
        bar=self.lyricsScroll.verticalScrollBar()
        target=label.pos().y()-max(0,(self.lyricsScroll.viewport().height()//2)-label.height()//2)
        target=max(bar.minimum(),min(bar.maximum(),target))
        if getattr(self,"_lyrics_anim",None) and self._lyrics_anim.state()==QPropertyAnimation.State.Running:
            self._lyrics_anim.stop()
        anim=QPropertyAnimation(bar,b"value",self);anim.setDuration(320);anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.setStartValue(bar.value());anim.setEndValue(target);anim.start()
        self._lyrics_anim=anim

    def save_session(self):
        try:
            data=json.loads(SETTINGS_FILE.read_text()) if SETTINGS_FILE.exists() else {}
            current=None
            if self.stream_current:current={"kind":"stream","id":self.stream_current.get("id")}
            elif self.local_current:current={"kind":"local","path":self.local_current.get("path")}
            data["session"]={"queue":self.queue,"current":current,"position":self.p.position(),"volume":self.base_volume,"view":self.view}
            SETTINGS_FILE.write_text(json.dumps(data))
        except Exception:pass

    def restore_session(self):
        try:data=json.loads(SETTINGS_FILE.read_text()).get("session",{})
        except Exception:return
        q=[]
        for e in data.get("queue",[]):
            if isinstance(e,list) and len(e)>=2:q.append(tuple(e))
            else:q.append(e)
        self.queue=q
        self.base_volume=float(data.get("volume",self.base_volume));self._apply_output_volume()
        cur=data.get("current") or {};pos=int(data.get("position",0))
        if cur.get("kind")=="local" and Path(cur.get("path","")).exists():
            r=next((x for x in self.d.songs() if x[0]==cur["path"]),None)
            if r:
                self.rows=[r];self.i=0;self.playrow(0);self.p.pause();QTimer.singleShot(250,lambda:self.p.setPosition(pos))
        elif cur.get("kind")=="stream":
            r=self.d.stream(cur.get("id",""))
            if r:
                self.play_stream_dict(r);QTimer.singleShot(1500,lambda:self.p.pause());QTimer.singleShot(1700,lambda:self.p.setPosition(pos))
        self.statusBar().showMessage("Sesión anterior recuperada",2200)

    def resizeEvent(self,e):
        super().resizeEvent(e)
        # Si el panel de letras está abierto, su ancho disponible cambió:
        # recalculamos el ajuste de línea de cada etiqueta para que no
        # queden amontonadas/recortadas con el nuevo tamaño de ventana.
        if getattr(self,"lyricsPanel",None) and self.lyricsPanel.isVisible() and self._lyrics_labels:
            self._fit_all_lyric_labels()

    def closeEvent(self,e):
        try:self.p.stop()
        except Exception:pass
        self.save_session()
        self.youtube_searcher.cancel(); self.youtube_resolver.cancel(); self.youtube_downloader.cancel()
        for p in (self.hybrid_process,getattr(self,"_home_trending_process",None),getattr(self,"local_video_search",None)):
            try:
                if p and p.state()!=QProcess.ProcessState.NotRunning:p.kill()
            except Exception:pass
        try:self.dsp.unload()
        except Exception:pass
        self._mpris_shutdown()
        if getattr(self,"tray",None):
            try:
                self.tray.hide()
                self.tray.deleteLater()
            except Exception:pass
            self.tray=None
        e.accept()
        QApplication.instance().quit()

    def end(self,s):
        if s==QMediaPlayer.MediaStatus.EndOfMedia:
            if self.crossfade_started:return
            if self.repeat:self.p.setPosition(0); self.p.play()
            else:self.next()


