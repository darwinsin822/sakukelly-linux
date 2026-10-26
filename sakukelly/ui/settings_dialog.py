"""Diálogo de configuración de Sakukelly (temas, ecualizador, wallpaper,
crossfade/gapless, MPRIS, bandeja, carátulas, Last.fm/ListenBrainz).

Rediseñado con una barra lateral de categorías + panel de contenido por
páginas, look oscuro y acentos verdes, al estilo de la ventana de
Configuración de Spotify. Toda la lógica sigue delegando en la ventana
principal a través de `self.parent`, sin cambios de comportamiento respecto
a la versión anterior: solo cambia cómo se organiza y se ve.
"""
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSlider, QCheckBox, QFileDialog, QLineEdit, QListWidget, QListWidgetItem,
    QStackedWidget, QWidget, QFrame, QScrollArea, QSizePolicy)

try:
    import dbus
    DBUS_AVAILABLE = True
except Exception:
    DBUS_AVAILABLE = False


SPOTIFY_GREEN = "#1db954"
SPOTIFY_GREEN_HOVER = "#1ed760"

SETTINGS_QSS = f"""
QDialog#settings{{background:#121212;color:#ffffff;font-family:'Inter','SF Pro Display','Segoe UI','Ubuntu','Noto Sans',sans-serif;font-size:13px}}
QWidget#settingsSidebar{{background:#000000}}
QLabel#settingsBrand{{color:#ffffff;font-size:15px;font-weight:800;padding:2px 22px 16px 22px}}
QListWidget#settingsNav{{background:transparent;border:none;outline:0;padding:0 10px}}
QListWidget#settingsNav::item{{color:#b3b3b3;font-size:13px;font-weight:700;padding:11px 12px;border-radius:6px;margin:1px 0}}
QListWidget#settingsNav::item:hover{{color:#ffffff;background:rgba(255,255,255,.06)}}
QListWidget#settingsNav::item:selected{{color:#ffffff;background:rgba(255,255,255,.10)}}
QScrollArea#settingsScroll{{background:transparent;border:none}}
QWidget#settingsPage{{background:transparent}}
QLabel#pageTitle{{color:#ffffff;font-size:22px;font-weight:800;letter-spacing:-.2px;padding-bottom:2px}}
QLabel#pageSubtitle{{color:#b3b3b3;font-size:12.5px;padding-bottom:6px}}
QLabel#sectionLabel{{color:#ffffff;font-size:13px;font-weight:800;letter-spacing:.4px;padding-top:14px}}
QLabel#hint{{color:#b3b3b3;font-size:12px}}
QLabel#value{{color:#b3b3b3;font-size:12px;font-weight:700}}
QWidget#card{{background:#181818;border-radius:10px}}
QDialog#settings QPushButton{{background:rgba(255,255,255,.08);color:#ffffff;border:none;border-radius:18px;padding:9px 18px;font-weight:700;font-size:12.5px}}
QDialog#settings QPushButton:hover{{background:rgba(255,255,255,.16)}}
QDialog#settings QPushButton#navBtn{{background:transparent;border:1px solid #7a7a7a;border-radius:18px;padding:8px 22px}}
QDialog#settings QPushButton#navBtn:hover{{border-color:#ffffff}}
QDialog#settings QPushButton#primary{{background:{SPOTIFY_GREEN};color:#000000;border-radius:22px;padding:11px 30px;font-weight:800}}
QDialog#settings QPushButton#primary:hover{{background:{SPOTIFY_GREEN_HOVER}}}
QDialog#settings QPushButton#themeSwatch{{border-radius:10px;padding:14px 10px;font-weight:800;color:#ffffff}}
QDialog#settings QLineEdit{{background:#2a2a2a;border:1px solid #3a3a3a;border-radius:6px;padding:9px 10px;color:#ffffff}}
QDialog#settings QLineEdit:focus{{border:1px solid {SPOTIFY_GREEN}}}
QDialog#settings QSlider::groove:horizontal{{height:4px;background:#4d4d4d;border-radius:2px}}
QDialog#settings QSlider::sub-page:horizontal{{background:{SPOTIFY_GREEN};border-radius:2px}}
QDialog#settings QSlider::handle:horizontal{{background:#ffffff;width:14px;height:14px;margin:-5px 0;border-radius:7px}}
QDialog#settings QSlider::groove:vertical{{width:4px;background:#4d4d4d;border-radius:2px}}
QDialog#settings QSlider::add-page:vertical{{background:{SPOTIFY_GREEN};border-radius:2px}}
QDialog#settings QSlider::handle:vertical{{background:#ffffff;height:14px;width:14px;margin:0 -5px;border-radius:7px}}
QDialog#settings QCheckBox{{color:#ffffff;font-size:13px;spacing:12px;padding:2px 0}}
QDialog#settings QCheckBox::indicator{{width:36px;height:20px;border-radius:10px;background:#4d4d4d}}
QDialog#settings QCheckBox::indicator:checked{{background:{SPOTIFY_GREEN}}}
QFrame#hr{{background:#2a2a2a;max-height:1px;min-height:1px;border:none}}
"""


class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent); self.parent=parent
        self.setWindowTitle("Configuración"); self.resize(940,660); self.setObjectName("settings")
        self.setStyleSheet(SETTINGS_QSS)

        root=QVBoxLayout(self); root.setContentsMargins(0,0,0,0); root.setSpacing(0)
        body=QHBoxLayout(); body.setContentsMargins(0,0,0,0); body.setSpacing(0)

        sidebar=QWidget(); sidebar.setObjectName("settingsSidebar"); sidebar.setFixedWidth(230)
        sv=QVBoxLayout(sidebar); sv.setContentsMargins(0,22,0,22); sv.setSpacing(0)
        brand=QLabel("Configuración"); brand.setObjectName("settingsBrand"); sv.addWidget(brand)
        self.navList=QListWidget(); self.navList.setObjectName("settingsNav")
        self.navList.setFrameShape(QFrame.Shape.NoFrame)
        self.navList.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navList.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navList.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        sv.addWidget(self.navList,1)
        body.addWidget(sidebar)

        self.stack=QStackedWidget(); self.stack.setObjectName("settingsStack")
        body.addWidget(self.stack,1)
        root.addLayout(body,1)

        footer=QHBoxLayout(); footer.setContentsMargins(28,14,28,18)
        footer.addStretch()
        close=QPushButton("Cerrar"); close.setObjectName("primary"); close.clicked.connect(self.accept)
        footer.addWidget(close)
        root.addLayout(footer)

        pages=[
            ("Reproducción", self._page_playback),
            ("Apariencia", self._page_appearance),
            ("Carátulas y metadatos", self._page_covers),
            ("Sistema", self._page_system),
            ("Cuentas conectadas", self._page_accounts),
        ]
        for name,_ in pages:
            self.navList.addItem(QListWidgetItem(name))
        for _,builder in pages:
            self.stack.addWidget(self._wrap_scroll(builder()))
        self.navList.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.navList.setCurrentRow(0)

        self.coverTimer=QTimer(self); self.coverTimer.setInterval(900)
        self.coverTimer.timeout.connect(self._refresh_covers_label); self.coverTimer.start()

    # ---- helpers de layout -------------------------------------------------
    def _wrap_scroll(self,inner):
        scroll=QScrollArea(); scroll.setObjectName("settingsScroll"); scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame); scroll.setWidget(inner)
        return scroll

    def _page(self,title,subtitle=None):
        page=QWidget(); page.setObjectName("settingsPage")
        v=QVBoxLayout(page); v.setContentsMargins(36,30,36,30); v.setSpacing(10)
        t=QLabel(title); t.setObjectName("pageTitle"); v.addWidget(t)
        if subtitle:
            s=QLabel(subtitle); s.setObjectName("pageSubtitle"); s.setWordWrap(True); v.addWidget(s)
        return page,v

    def label(self,t):
        x=QLabel(t); x.setObjectName("sectionLabel"); return x

    def _hr(self,v):
        line=QFrame(); line.setObjectName("hr"); line.setFrameShape(QFrame.Shape.HLine); v.addWidget(line)

    def _card(self):
        card=QWidget(); card.setObjectName("card")
        cv=QVBoxLayout(card); cv.setContentsMargins(18,16,18,16); cv.setSpacing(10)
        return card,cv

    # ---- página: Reproducción ----------------------------------------------
    def _page_playback(self):
        page,v=self._page("Reproducción","Ecualizador, transiciones entre canciones y normalización de volumen.")

        v.addWidget(self.label("ECUALIZADOR"))
        presets=QHBoxLayout()
        for n in ["Plano","Graves","Voces","Agudos","Rock"]:
            b=QPushButton(n); b.clicked.connect(lambda _,x=n:self.preset(x)); presets.addWidget(b)
        v.addLayout(presets)
        bands=QHBoxLayout(); self.eq=[]
        for hz in ["60","150","400","1K","2.4K","6K","12K","16K"]:
            col=QVBoxLayout(); sl=QSlider(Qt.Orientation.Vertical); sl.setRange(-12,12); sl.setValue(0); sl.setMinimumHeight(150)
            self.eq.append(sl); sl.valueChanged.connect(self.eq_changed); col.addWidget(sl,0,Qt.AlignmentFlag.AlignHCenter)
            lab=QLabel(hz); lab.setObjectName("value"); lab.setAlignment(Qt.AlignmentFlag.AlignCenter); col.addWidget(lab)
            bands.addLayout(col)
        v.addLayout(bands)
        saved=self.parent.eq_values
        for sl,val in zip(self.eq,saved): sl.blockSignals(True); sl.setValue(int(val)); sl.blockSignals(False)
        self.dspStatus=QLabel("DSP: comprobando…"); self.dspStatus.setObjectName("hint"); v.addWidget(self.dspStatus)
        self.eqTimer=QTimer(self); self.eqTimer.setSingleShot(True); self.eqTimer.setInterval(180); self.eqTimer.timeout.connect(self.commit_eq)

        self._hr(v)
        v.addWidget(self.label("TRANSICIONES"))
        self.crossfade=QCheckBox("Crossfade entre canciones"); self.crossfade.setChecked(self.parent.crossfade); self.crossfade.toggled.connect(self.crossfade_changed); v.addWidget(self.crossfade)
        cfrow=QHBoxLayout(); cfrow.addWidget(QLabel("Duración del crossfade"))
        self.crossfadeSlider=QSlider(Qt.Orientation.Horizontal); self.crossfadeSlider.setRange(1,10); self.crossfadeSlider.setValue(max(1,min(10,self.parent.crossfade_ms//1000))); self.crossfadeSlider.valueChanged.connect(self.crossfade_duration_changed)
        cfrow.addWidget(self.crossfadeSlider,1)
        self.crossfadeValue=QLabel(f"{self.crossfadeSlider.value()} s"); self.crossfadeValue.setObjectName("value"); cfrow.addWidget(self.crossfadeValue)
        v.addLayout(cfrow)
        self.gapless=QCheckBox("Reproducción gapless (pistas sin corte, ideal para álbumes en vivo o conceptuales)"); self.gapless.setChecked(self.parent.gapless); self.gapless.toggled.connect(self.gapless_changed); v.addWidget(self.gapless)

        self._hr(v)
        v.addWidget(self.label("VOLUMEN"))
        self.normalize=QCheckBox("Normalizar volumen (ReplayGain, EBU R128)"); self.normalize.setChecked(self.parent.replaygain); self.normalize.toggled.connect(self.replaygain_changed); v.addWidget(self.normalize)
        rgrow=QHBoxLayout()
        done,total=self.parent.d.loudness_progress()
        self.rgLabel=QLabel(f"{done}/{total} canciones analizadas" if total else "Sin canciones en la biblioteca")
        self.rgLabel.setObjectName("hint"); rgrow.addWidget(self.rgLabel,1)
        rgscan=QPushButton("Analizar biblioteca"); rgscan.clicked.connect(self.start_rg_scan); rgrow.addWidget(rgscan)
        v.addLayout(rgrow)

        v.addStretch()
        self.commit_eq()
        return page

    # ---- página: Apariencia -------------------------------------------------
    def _page_appearance(self):
        page,v=self._page("Apariencia","Colores de la interfaz y fondo personalizado.")

        v.addWidget(self.label("TEMAS DE COLOR"))
        themes=QHBoxLayout()
        theme_colors={"noche":"#7c5cff","sunset":"#ff6b6b","forest":"#3ddc97","mono":"#8a8a8a","candy":"#ff4fd8"}
        for key,label in [("noche","Noche estrellada"),("sunset","Atardecer"),("forest","Bosque"),("mono","Monocromo"),("candy","Candy")]:
            b=QPushButton(label); b.setObjectName("themeSwatch"); b.setMinimumHeight(64)
            b.setStyleSheet(f"QPushButton#themeSwatch{{background:{theme_colors[key]}}} QPushButton#themeSwatch:hover{{background:{theme_colors[key]}}}")
            b.clicked.connect(lambda _,k=key:self.parent.apply_theme(k)); themes.addWidget(b)
        v.addLayout(themes)

        self._hr(v)
        v.addWidget(self.label("FONDO PERSONALIZADO"))
        wallrow=QHBoxLayout()
        wb=QPushButton("Elegir imagen o wallpaper"); wb.clicked.connect(self.choose_wallpaper); wallrow.addWidget(wb)
        wr=QPushButton("Quitar wallpaper"); wr.clicked.connect(self.clear_wallpaper); wallrow.addWidget(wr)
        wallrow.addStretch()
        v.addLayout(wallrow)
        self.wallLabel=QLabel(self.parent.wallpaper if self.parent.wallpaper else "Fondo del tema actual")
        self.wallLabel.setObjectName("hint"); self.wallLabel.setWordWrap(True); v.addWidget(self.wallLabel)

        self._hr(v)
        mini=QPushButton("Abrir Player"); mini.setToolTip("Muestra la carátula y controles de la canción actual"); mini.clicked.connect(self.open_mini)
        v.addWidget(mini,0,Qt.AlignmentFlag.AlignLeft)

        v.addStretch()
        return page

    # ---- página: Carátulas y metadatos --------------------------------------
    def _page_covers(self):
        page,v=self._page("Carátulas y metadatos","Portadas automáticas para tu biblioteca local y limpieza de etiquetas incompletas.")

        v.addWidget(self.label("CARÁTULAS FALTANTES"))
        info=QLabel("Sakukelly ya baja automáticamente las carátulas de tu música local en segundo plano; a la que no se le encuentre una, se le asigna una portada genérica bonita para que nunca quede en blanco.")
        info.setWordWrap(True); info.setObjectName("hint"); v.addWidget(info)
        coversRow=QHBoxLayout()
        self.coversLabel=QLabel(""); self.coversLabel.setObjectName("hint"); coversRow.addWidget(self.coversLabel,1)
        coversBtn=QPushButton("Buscar carátulas ahora"); coversBtn.clicked.connect(self.start_cover_scan); coversRow.addWidget(coversBtn)
        v.addLayout(coversRow)
        self._refresh_covers_label()

        self._hr(v)
        v.addWidget(self.label("METADATOS"))
        mbInfo=QLabel("Completa artista, álbum o año que falten, buscando coincidencias confiables en MusicBrainz. Nunca sobreescribe datos existentes sin que los revises primero.")
        mbInfo.setWordWrap(True); mbInfo.setObjectName("hint"); v.addWidget(mbInfo)
        mbBtn=QPushButton("Buscar y revisar metadatos incompletos"); mbBtn.clicked.connect(self.parent.start_metadata_cleanup_scan); v.addWidget(mbBtn,0,Qt.AlignmentFlag.AlignLeft)

        v.addStretch()
        return page

    # ---- página: Sistema -----------------------------------------------------
    def _page_system(self):
        page,v=self._page("Sistema","Integración con el sistema operativo.")

        v.addWidget(self.label("PREFERENCIAS GENERALES"))
        self.mprisBox=QCheckBox("Integración con el sistema (teclas multimedia, applet de sonido, bloqueo de pantalla)")
        self.mprisBox.setChecked(self.parent.mpris_enabled); self.mprisBox.toggled.connect(self.mpris_toggled); v.addWidget(self.mprisBox)
        if not DBUS_AVAILABLE:
            self.mprisBox.setEnabled(False)
            note=QLabel("No se encontró python3-dbus en el sistema; instálalo para activar esta opción.")
            note.setObjectName("hint"); v.addWidget(note)

        v.addStretch()
        return page

    # ---- página: Cuentas conectadas ------------------------------------------
    def _page_accounts(self):
        page,v=self._page("Cuentas conectadas","Escrobbleo e historial de escucha.")

        v.addWidget(self.label("LISTENBRAINZ"))
        lbRow=QHBoxLayout()
        self.lbBox=QCheckBox("Activar"); self.lbBox.setChecked(self.parent.lb_enabled); self.lbBox.toggled.connect(self.lb_toggled); lbRow.addWidget(self.lbBox)
        v.addLayout(lbRow)
        self.lbToken=QLineEdit(); self.lbToken.setPlaceholderText("Token personal de listenbrainz.org/settings"); self.lbToken.setText(self.parent.lb_token); self.lbToken.editingFinished.connect(self.lb_token_changed)
        v.addWidget(self.lbToken)
        lbHelp=QLabel('Consigue tu token gratis en <a href="https://listenbrainz.org/settings/">listenbrainz.org/settings</a> (no hace falta crear una app).')
        lbHelp.setOpenExternalLinks(True); lbHelp.setObjectName("hint"); v.addWidget(lbHelp)

        self._hr(v)
        v.addWidget(self.label("LAST.FM"))
        lfKeyRow=QHBoxLayout(); lfKeyRow.addWidget(QLabel("API key"))
        self.lfKey=QLineEdit(); self.lfKey.setText(self.parent.lastfm_key); self.lfKey.editingFinished.connect(self.lastfm_creds_changed)
        lfKeyRow.addWidget(self.lfKey,1); v.addLayout(lfKeyRow)
        lfSecRow=QHBoxLayout(); lfSecRow.addWidget(QLabel("Secret"))
        self.lfSecret=QLineEdit(); self.lfSecret.setEchoMode(QLineEdit.EchoMode.Password); self.lfSecret.setText(self.parent.lastfm_secret); self.lfSecret.editingFinished.connect(self.lastfm_creds_changed)
        lfSecRow.addWidget(self.lfSecret,1); v.addLayout(lfSecRow)
        lfHelp=QLabel('Regístralas gratis en <a href="https://www.last.fm/api/account/create">last.fm/api/account/create</a> — es un registro tuyo, no lo puede hacer la app por ti.')
        lfHelp.setOpenExternalLinks(True); lfHelp.setWordWrap(True); lfHelp.setObjectName("hint"); v.addWidget(lfHelp)
        lfBtnRow=QHBoxLayout()
        lfConnect=QPushButton("Conectar con Last.fm"); lfConnect.clicked.connect(self.parent.lastfm_start_auth); lfBtnRow.addWidget(lfConnect)
        lfConfirm=QPushButton("Confirmar conexión"); lfConfirm.clicked.connect(self.lastfm_confirm); lfBtnRow.addWidget(lfConfirm)
        lfBtnRow.addStretch()
        v.addLayout(lfBtnRow)
        self.lfStatus=QLabel("Last.fm: conectado" if self.parent.lastfm_session else "Last.fm: no conectado")
        self.lfStatus.setObjectName("hint"); v.addWidget(self.lfStatus)

        v.addStretch()
        return page

    # ---- lógica (idéntica a la versión anterior del diálogo) ---------------
    def choose_wallpaper(self):
        f,_=QFileDialog.getOpenFileName(self,"Seleccionar wallpaper","","Imágenes (*.jpg *.jpeg *.png *.webp *.bmp)")
        if f:
            self.parent.wallpaper=f
            self.parent.save_settings()
            self.parent.apply_wallpaper()
            self.wallLabel.setText(f)
    def clear_wallpaper(self):
        self.parent.wallpaper=""
        self.parent.save_settings()
        self.parent.apply_wallpaper()
        self.wallLabel.setText("Fondo del tema actual")
    def crossfade_changed(self,on):
        self.parent.crossfade=bool(on); self.parent.save_settings()
        if on and self.gapless.isChecked():self.gapless.setChecked(False)
    def crossfade_duration_changed(self,value):
        self.parent.crossfade_ms=int(value)*1000; self.crossfadeValue.setText(f"{value} s"); self.parent.save_settings()
    def gapless_changed(self,on):
        self.parent.gapless=bool(on); self.parent.save_settings()
        if on and self.crossfade.isChecked():self.crossfade.setChecked(False)
    def replaygain_changed(self,on):
        self.parent.replaygain=bool(on); self.parent.save_settings()
        self.parent._gain_mult=self.parent._gain_for_path(self.parent.local_current.get("path") if self.parent.local_current else None)
        self.parent._apply_output_volume()
    def start_rg_scan(self):
        self.parent.start_loudness_scan()
        done,total=self.parent.d.loudness_progress()
        self.rgLabel.setText(f"Analizando… ({done}/{total} hasta ahora, sigue en segundo plano)" if total else "Sin canciones en la biblioteca")
    def start_cover_scan(self):
        self.parent.start_cover_backfill(force=True)
        self._refresh_covers_label()
    def _refresh_covers_label(self):
        if not hasattr(self,"coversLabel"):return
        if getattr(self.parent,"_cover_backfill_active",False):
            done=getattr(self.parent,"_cover_backfill_done",0); total=getattr(self.parent,"_cover_backfill_total",0)
            self.coversLabel.setText(f"Buscando carátulas… {done}/{total} (sigue en segundo plano)")
        else:
            try:
                from sakukelly.metadata.artwork import has_cached_cover
                paths=[r[0] for r in self.parent.d.songs()]
                total=len(paths)
                missing=sum(1 for p in paths if not has_cached_cover(p))
                self.coversLabel.setText(f"{total-missing}/{total} canciones con carátula" if total else "Sin canciones en la biblioteca")
            except Exception:
                self.coversLabel.setText("")
    def mpris_toggled(self,on):
        self.parent.mpris_enabled=bool(on); self.parent.save_settings()
        if on and not getattr(self.parent,"_mpris_service",None):self.parent._setup_mpris()
        elif not on and getattr(self.parent,"_mpris_service",None):
            self.parent._mpris_shutdown(); self.parent._mpris_service=None
    def tray_toggled(self,on):
        pass
    def lb_toggled(self,on):
        self.parent.lb_enabled=bool(on); self.parent.save_settings()
    def lb_token_changed(self):
        self.parent.lb_token=self.lbToken.text().strip(); self.parent.save_settings()
    def lastfm_creds_changed(self):
        self.parent.lastfm_key=self.lfKey.text().strip(); self.parent.lastfm_secret=self.lfSecret.text().strip(); self.parent.save_settings()
    def lastfm_confirm(self):
        self.parent.lastfm_finish_auth()
        QTimer.singleShot(1200,self._refresh_lastfm_status)
    def _refresh_lastfm_status(self):
        self.lfStatus.setText("Last.fm: conectado" if self.parent.lastfm_session else "Last.fm: no conectado")
    def open_mini(self):
        self.parent.open_video_player()
    def preset(self,n):
        values={"Plano":[0]*8,"Graves":[8,6,4,1,0,-1,-2,-2],"Voces":[-2,-1,2,5,5,3,1,0],"Agudos":[-3,-2,-1,0,2,5,7,8],"Rock":[5,3,-2,-3,1,3,5,6]}[n]
        for sl,v in zip(self.eq,values): sl.setValue(v)
        self.commit_eq()
    def eq_changed(self,_=None):
        self.eqTimer.start()
    def commit_eq(self):
        vals=[sl.value() for sl in self.eq]
        ok,msg=self.parent.set_equalizer(vals)
        self.dspStatus.setText("DSP activo · ecualización aplicada en tiempo real" if ok else "DSP no activo · instala swh-plugins y asegúrate de tener pactl")
