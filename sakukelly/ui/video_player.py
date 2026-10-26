"""Mini-player flotante basado en carátula: ventana pequeña, siempre
disponible, que comparte el audio de la ventana principal.

Extraída de ui/main_window.py sin cambios de comportamiento: sigue
comunicándose con la ventana principal a través de `self.main`.
"""
from PyQt6.QtCore import Qt, QUrl, QTimer
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSlider, QCheckBox

from sakukelly.config import APP_ICON, THEMES
from sakukelly.streaming.youtube import youtube_thumb_url
from sakukelly.ui.widgets import mini_player_qss


class VideoPlayer(QWidget):
    """Player flotante estable basado en carátula; comparte el audio principal."""
    def __init__(self,main):
        super().__init__();self.main=main
        self.setObjectName("miniPlayer")
        self.setWindowTitle("Sakukelly · Player");self.setWindowIcon(QIcon(APP_ICON))
        self.setWindowFlags(Qt.WindowType.Tool);self.resize(420,150);self.setMinimumSize(260,110)
        self.setStyleSheet(mini_player_qss(THEMES.get(getattr(main,"theme","noche"),THEMES["noche"])))
        v=QVBoxLayout(self);v.setContentsMargins(10,8,10,8);v.setSpacing(5)
        self.art=QLabel();self.art.hide()
        self.title=QLabel("Nada reproduciéndose");self.title.setAlignment(Qt.AlignmentFlag.AlignCenter);self.title.setWordWrap(True);v.addWidget(self.title)
        c=QHBoxLayout();self.prevb=QPushButton("◀");self.playb=QPushButton("▶ / Ⅱ");self.nextb=QPushButton("▶")
        self.prevb.clicked.connect(main.prev);self.playb.clicked.connect(main.toggle);self.nextb.clicked.connect(main.next)
        c.addStretch();c.addWidget(self.prevb);c.addWidget(self.playb);c.addWidget(self.nextb);c.addStretch();v.addLayout(c)
        self.seek=QSlider(Qt.Orientation.Horizontal);self.seek.setRange(0,1000);self.seek.sliderMoved.connect(self.seek_to);v.addWidget(self.seek)
        self.status=QLabel("Mini-player");self.status.setAlignment(Qt.AlignmentFlag.AlignCenter);v.addWidget(self.status)
        self.pin=QCheckBox("Siempre visible");self.pin.toggled.connect(self.set_always_on_top);v.addWidget(self.pin,0,Qt.AlignmentFlag.AlignCenter)
        self.net=QNetworkAccessManager(self);self.last_key=None
        self.timer=QTimer(self);self.timer.timeout.connect(self.sync);self.timer.start(350);self.sync()

    def set_always_on_top(self,on):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,on);self.show()

    def load_current(self):self.sync(force=True)

    def sync(self,force=False):
        p=self.main.p;d=p.duration()
        if d>0 and not self.seek.isSliderDown():self.seek.setValue(int(p.position()*1000/d))
        if self.main.stream_current:
            r=self.main.stream_current;key="yt:"+str(r.get("id"))
            self.title.setText(f'{r.get("title","")}\n{r.get("artist","")} · YouTube')
            if force or key!=self.last_key:self.last_key=key
        elif self.main.local_current:
            r=self.main.local_current;key="local:"+str(r.get("path"))
            self.title.setText(f'{r.get("title","")}\n{r.get("artist","")} · Local')
            if force or key!=self.last_key:self.last_key=key
        else:self.title.setText("Nada reproduciéndose")

    def set_art(self,px):
        if px is None or px.isNull():
            self.art.setPixmap(QPixmap());self.art.setText("♪");return
        self.art.setText("")
        target=max(72,min(self.art.width(),self.art.height()))
        self.art.setPixmap(px.scaled(target,target,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def load_remote_art(self,url,_retry=True):
        if not str(url).startswith("https://"):self.set_art(None);return
        rep=self.net.get(QNetworkRequest(QUrl(url)))
        def done():
            px=QPixmap()
            if px.loadFromData(bytes(rep.readAll())):
                self.set_art(px)
            elif _retry and self.main.stream_current:
                fallback=youtube_thumb_url(self.main.stream_current.get("id"))
                if fallback and fallback!=url:self.load_remote_art(fallback,_retry=False)
                else:self.set_art(None)
            else:self.set_art(None)
            rep.deleteLater()
        rep.finished.connect(done)

    def seek_to(self,x):
        d=self.main.p.duration()
        if d>0:self.main.p.setPosition(int(d*x/1000))
