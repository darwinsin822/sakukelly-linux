"""Widgets Qt reutilizables sin dependencia de la ventana principal:
letra karaoke animada, forma de onda decorativa, lista con arrastre y
marco con soporte de "soltar" (drag & drop) de pistas."""
import json, re, math
from PyQt6.QtCore import Qt, QRect, QMimeData, pyqtSignal, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen, QBrush, QLinearGradient, QDrag
from PyQt6.QtWidgets import QLabel, QWidget, QListWidget, QFrame, QGraphicsDropShadowEffect
from PyQt6.QtMultimedia import QMediaPlayer
from sakukelly.config import THEMES

def hex_to_rgb(h):
    """Convierte '#rrggbb' a una tupla (r,g,b) para usar en rgba() de QSS."""
    h=str(h).lstrip("#")
    if len(h)!=6:return (124,92,255)
    try:return tuple(int(h[i:i+2],16) for i in (0,2,4))
    except Exception:return (124,92,255)


def glass_shadow(widget,blur=44,dx=0,dy=14,alpha=140):
    """Aplica una sombra suave real (no simulable en QSS) para dar sensación
    de panel de cristal flotando sobre el fondo."""
    eff=QGraphicsDropShadowEffect(widget);eff.setBlurRadius(blur);eff.setOffset(dx,dy);eff.setColor(QColor(0,0,0,alpha))
    widget.setGraphicsEffect(eff)


def mini_player_qss(t):
    """Hoja de estilos Liquid Glass para el mini-player: es una ventana de
    nivel superior aparte, así que no hereda el stylesheet de la ventana
    principal y necesita la suya propia."""
    ar,ag,ab=hex_to_rgb(t['accent']); a2r,a2g,a2b=hex_to_rgb(t['accent2'])
    return f"""
    #miniPlayer{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 {t['mid']},stop:1 {t['deep']});color:{t['text']};font-family:'Inter','SF Pro Display','Segoe UI','Ubuntu','Noto Sans',sans-serif;font-size:13px}}
    #miniPlayer QLabel{{color:{t['text']}}}
    #miniPlayer QPushButton{{background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,.12),stop:1 rgba(255,255,255,.04));border:1px solid rgba(255,255,255,.18);border-radius:15px;padding:6px 12px;color:{t['text']}}}
    #miniPlayer QPushButton:hover{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba({ar},{ag},{ab},.32),stop:1 rgba({a2r},{a2g},{a2b},.20))}}
    #miniPlayer QSlider::groove:horizontal{{height:6px;background:rgba(255,255,255,.16);border-radius:3px}}
    #miniPlayer QSlider::sub-page:horizontal{{background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {t['accent']},stop:1 {t['accent2']});border-radius:3px}}
    #miniPlayer QSlider::handle:horizontal{{background:qradialgradient(cx:.35,cy:.35,radius:1,fx:.35,fy:.35,stop:0 #ffffff,stop:.5 {t['accent2']},stop:1 {t['accent']});width:14px;height:14px;margin:-4px 0;border-radius:7px;border:1px solid rgba(255,255,255,.6)}}
    #miniPlayer QCheckBox{{color:{t['dim']};spacing:8px}}
    #miniPlayer QCheckBox::indicator{{width:16px;height:16px;border-radius:5px;background:rgba(255,255,255,.07);border:1px solid rgba(255,255,255,.22)}}
    #miniPlayer QCheckBox::indicator:checked{{background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['accent']},stop:1 {t['accent2']});border:1px solid rgba(255,255,255,.5)}}
    """


class KaraokeLabel(QLabel):
    """Etiqueta de letra estilo Karaoke real.
    Dibuja el texto con un degradado animado que se llena progresivamente
    a lo largo de la línea según el tiempo transcurrido de la canción."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setObjectName("lyricLine")
        self.setWordWrap(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._progress = 0.0
        self._is_active = False
        self._accent1 = "#00f2fe"
        self._accent2 = "#4facfe"
        self._dim_color = QColor(255, 255, 255, 100)

    def set_active_progress(self, is_active, progress=0.0, accent1="#00f2fe", accent2="#4facfe", dim_color="rgba(255,255,255,0.4)"):
        changed = (self._is_active != is_active or abs(self._progress - progress) > 0.012)
        self._is_active = is_active
        self._progress = max(0.0, min(1.0, progress)) if is_active else 0.0
        self._accent1 = accent1
        self._accent2 = accent2
        # dim_color may be a CSS rgba() string or a QColor — always store as QColor
        if isinstance(dim_color, QColor):
            self._dim_color = dim_color
        elif isinstance(dim_color, str):
            m = re.search(r"rgba\((\d+),(\d+),(\d+),([\d.]+)\)", dim_color.replace(" ",""))
            if m:
                self._dim_color = QColor(int(m.group(1)),int(m.group(2)),int(m.group(3)),int(float(m.group(4))*255))
            else:
                self._dim_color = QColor(255,255,255,100)
        else:
            self._dim_color = QColor(255,255,255,100)
        if changed:
            self.update()

    def paintEvent(self, event):
        if not self._is_active:
            super().paintEvent(event)
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        text_flags = int(Qt.AlignmentFlag.AlignCenter) | int(Qt.AlignmentFlag.AlignVCenter) | int(Qt.TextFlag.TextWordWrap)

        # ---- 1) Capa base: texto inactivo estilo Apple Music ----
        painter.setFont(self.font())
        painter.setPen(getattr(self, "_dim_color", QColor(255, 255, 255, 110)))
        painter.drawText(rect, text_flags, self.text())

        # ---- 2) Capa de relleno karaoke: degradado progresivo de acento ----
        if self._progress > 0.0:
            fill_w = max(1, int(rect.width() * self._progress))
            clip_rect = QRect(rect.x(), rect.y(), fill_w, rect.height())
            painter.setClipRect(clip_rect)

            grad = QLinearGradient(float(rect.x()), 0.0, float(rect.x() + rect.width()), 0.0)
            try: c1 = QColor(getattr(self, "_accent1", "#00f2fe"))
            except Exception: c1 = QColor(0, 242, 254)
            try: c2 = QColor(getattr(self, "_accent2", "#4facfe"))
            except Exception: c2 = QColor(79, 172, 254)
            grad.setColorAt(0.0, c1)
            grad.setColorAt(1.0, c2)

            painter.setPen(QPen(QBrush(grad), 1.0))
            painter.drawText(rect, text_flags, self.text())

        painter.end()


class WaveformWidget(QWidget):
    """Decorative live-looking waveform for the main player."""
    def __init__(self,parent=None):
        super().__init__(parent);self.setObjectName("waveform");self.setFixedHeight(58);self.phase=0
        self.timer=QTimer(self);self.timer.setInterval(120);self.timer.timeout.connect(self.tick);self.timer.start()
    def tick(self):
        self.phase=(self.phase+1)%1000;self.update()
    def paintEvent(self,event):
        pa=QPainter(self);pa.setRenderHint(QPainter.RenderHint.Antialiasing)
        w,h=self.width(),self.height();cy=h/2;bars=43;gap=3.0;bw=max(2.0,(w-gap*(bars-1))/bars)
        playing=False;theme_key="noche"
        win=self.window()
        try:
            playing=win.p.playbackState()==QMediaPlayer.PlaybackState.PlayingState
            theme_key=getattr(win,"theme","noche")
        except Exception: pass
        tk=THEMES.get(theme_key,THEMES["noche"])
        accent=QColor(tk["accent2"]);white=QColor(255,255,255,235)
        ph=self.phase*0.12
        half=(bars-1)/2
        for i in range(bars):
            x=i*(bw+gap);d=abs(i-half)/half
            env=max(.14,1-d*.88)
            wave=(.48+.52*abs(math.sin(i*.67+ph))) if playing else (.38+.34*abs(math.sin(i*.55)))
            bh=max(4,h*env*wave);c=white if i<bars*.42 else accent
            pa.setPen(QPen(c,bw,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap));pa.drawLine(int(x+bw/2),int(cy-bh/2),int(x+bw/2),int(cy+bh/2))


class TrackListWidget(QListWidget):
    """List optimized for mouse and touch drag-to-player."""
    def startDrag(self,supportedActions):
        it=self.currentItem()
        if not it:return
        data=it.data(Qt.ItemDataRole.UserRole)
        mime=QMimeData();mime.setText("sakukelly:"+json.dumps(data,ensure_ascii=False))
        drag=QDrag(self);drag.setMimeData(mime);drag.exec(Qt.DropAction.CopyAction)


class DropPlayerFrame(QFrame):
    dropped=pyqtSignal(object)
    def __init__(self,parent=None):
        super().__init__(parent);self.setAcceptDrops(True)
    def dragEnterEvent(self,e):
        md=e.mimeData()
        if md.hasUrls() or (md.hasText() and md.text().startswith("sakukelly:")):e.acceptProposedAction()
        else:e.ignore()
    def dropEvent(self,e):
        md=e.mimeData()
        if md.hasUrls():
            files=[u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            if files:self.dropped.emit(("files",files));e.acceptProposedAction();return
        if md.hasText() and md.text().startswith("sakukelly:"):
            try:self.dropped.emit(("item",json.loads(md.text()[11:])));e.acceptProposedAction();return
            except Exception:pass
        e.ignore()


from PyQt6.QtWidgets import QPushButton
from PyQt6.QtGui import QRadialGradient, QPainterPath
from PyQt6.QtCore import QPointF, QRectF

class PowerampPlayButton(QPushButton):
    """Botón Play/Pause táctil estilo Poweramp:
    - Doble bisel metálico oscuro con relieve cenital.
    - Núcleo cóncavo con gradiente dopamínico.
    - Halo de luz circular neón persistente mientras está en reproducción.
    - Renderizado vectorial de alta fidelidad sin aliasing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(68, 68)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._is_playing = False
        self._accent = "#7c5cff"
        self._accent2 = "#33e0ff"
        self._halo_phase = 0.0
        self._pulse_dir = 1

        # Timer para sutil pulsación viva del halo neón
        self._pulse_timer = QTimer(self)
        self._pulse_timer.setInterval(40)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

    def set_theme_colors(self, accent_hex, accent2_hex):
        self._accent = accent_hex
        self._accent2 = accent2_hex
        self.update()

    def set_playing_state(self, playing: bool):
        if self._is_playing != playing:
            self._is_playing = playing
            if playing:
                self._pulse_timer.start()
            else:
                self._pulse_timer.stop()
                self._halo_phase = 0.0
            self.update()

    def _on_pulse_tick(self):
        # Pulsación orgánica sutil entre 0.70 y 1.0
        self._halo_phase += 0.035 * self._pulse_dir
        if self._halo_phase >= 1.0:
            self._halo_phase = 1.0
            self._pulse_dir = -1
        elif self._halo_phase <= 0.0:
            self._halo_phase = 0.0
            self._pulse_dir = 1
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w = self.width()
        h = self.height()
        center = QPointF(w / 2.0, h / 2.0)
        btn_radius = 25.5

        ar, ag, ab = hex_to_rgb(self._accent)
        a2r, a2g, a2b = hex_to_rgb(self._accent2)

        # 1. Halo Neón Circular Persistente (solo cuando está reproduciendo)
        if self._is_playing:
            glow_intensity = 0.75 + 0.25 * self._halo_phase
            halo_grad = QRadialGradient(center, 33.5)
            halo_grad.setColorAt(0.70, QColor(ar, ag, ab, 0))
            halo_grad.setColorAt(0.80, QColor(ar, ag, ab, int(150 * glow_intensity)))
            halo_grad.setColorAt(0.92, QColor(a2r, a2g, a2b, int(190 * glow_intensity)))
            halo_grad.setColorAt(1.0, QColor(a2r, a2g, a2b, 0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(halo_grad))
            p.drawEllipse(center, 33.5, 33.5)

        # 2. Sombra de profundidad de botón (Drop shadow)
        shadow_grad = QRadialGradient(QPointF(center.x(), center.y() + 2), btn_radius + 3)
        shadow_grad.setColorAt(0.80, QColor(0, 0, 0, 160))
        shadow_grad.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(shadow_grad))
        p.drawEllipse(QPointF(center.x(), center.y() + 2), btn_radius + 2, btn_radius + 2)

        # 3. Anillo metálico exterior (Bisel de hardware con relieve de luz)
        outer_grad = QLinearGradient(center.x(), center.y() - btn_radius, center.x(), center.y() + btn_radius)
        if self.isDown():
            outer_grad.setColorAt(0.0, QColor(25, 24, 35))
            outer_grad.setColorAt(1.0, QColor(50, 48, 65))
        elif self.underMouse():
            outer_grad.setColorAt(0.0, QColor(80, 78, 105))
            outer_grad.setColorAt(0.5, QColor(40, 38, 55))
            outer_grad.setColorAt(1.0, QColor(20, 18, 28))
        else:
            outer_grad.setColorAt(0.0, QColor(65, 62, 85))
            outer_grad.setColorAt(0.5, QColor(32, 30, 44))
            outer_grad.setColorAt(1.0, QColor(14, 12, 20))

        p.setBrush(QBrush(outer_grad))
        # Borde exterior fino con brillo superior
        border_pen = QPen(QColor(255, 255, 255, 75 if not self.isDown() else 25), 1.2)
        p.setPen(border_pen)
        p.drawEllipse(center, btn_radius, btn_radius)

        # 4. Núcleo cóncavo dopamínico interior (Radio 21px)
        core_radius = 21.0
        core_grad = QRadialGradient(QPointF(center.x(), center.y() - (1.5 if not self.isDown() else -1.5)), core_radius)
        if self.isDown():
            core_grad.setColorAt(0.0, QColor(int(ar * 0.7), int(ag * 0.7), int(ab * 0.7)))
            core_grad.setColorAt(0.85, QColor(int(ar * 0.9), int(ag * 0.9), int(ab * 0.9)))
            core_grad.setColorAt(1.0, QColor(int(a2r * 0.8), int(a2g * 0.8), int(a2b * 0.8)))
        elif self._is_playing:
            # Estado sonando: núcleo vibrante
            core_grad.setColorAt(0.0, QColor(255, 255, 255, 230))
            core_grad.setColorAt(0.35, QColor(a2r, a2g, a2b, 245))
            core_grad.setColorAt(1.0, QColor(ar, ag, ab, 255))
        else:
            # Estado pausado: cóncavo metálico dopamínico elegante
            core_grad.setColorAt(0.0, QColor(a2r, a2g, a2b, 220))
            core_grad.setColorAt(0.70, QColor(ar, ag, ab, 230))
            core_grad.setColorAt(1.0, QColor(int(ar * 0.75), int(ag * 0.75), int(ab * 0.75), 245))

        p.setPen(QPen(QColor(0, 0, 0, 70), 1.0))
        p.setBrush(QBrush(core_grad))
        p.drawEllipse(center, core_radius, core_radius)

        # 5. Icono Vectorial Centrado (Play o Pause) con relieve
        ico_color = QColor(15, 14, 25) if self._is_playing else QColor(255, 255, 255)
        # Sombra del icono
        shadow_ico_color = QColor(0, 0, 0, 90) if not self._is_playing else QColor(255, 255, 255, 110)

        if self._is_playing:
            # Dos barras de pausa estilizadas
            bar_w = 4.2
            bar_h = 15.0
            r_bar = 2.0
            y_bar = center.y() - bar_h / 2.0
            # Sombra
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(shadow_ico_color))
            p.drawRoundedRect(QRectF(center.x() - 6.5, y_bar + 1.0, bar_w, bar_h), r_bar, r_bar)
            p.drawRoundedRect(QRectF(center.x() + 2.3, y_bar + 1.0, bar_w, bar_h), r_bar, r_bar)
            # Frente
            p.setBrush(QBrush(ico_color))
            p.drawRoundedRect(QRectF(center.x() - 6.5, y_bar, bar_w, bar_h), r_bar, r_bar)
            p.drawRoundedRect(QRectF(center.x() + 2.3, y_bar, bar_w, bar_h), r_bar, r_bar)
        else:
            # Triángulo de reproducción apuntando a la derecha
            path = QPainterPath()
            offset_x = 1.5
            x_left = center.x() - 5.5 + offset_x
            x_right = center.x() + 7.5 + offset_x
            y_top = center.y() - 8.5
            y_mid = center.y()
            y_bot = center.y() + 8.5

            path.moveTo(x_left, y_top)
            path.lineTo(x_right, y_mid)
            path.lineTo(x_left, y_bot)
            path.closeSubpath()

            # Sombra de icono
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(shadow_ico_color))
            shadow_path = QPainterPath()
            shadow_path.moveTo(x_left, y_top + 1.2)
            shadow_path.lineTo(x_right, y_mid + 1.2)
            shadow_path.lineTo(x_left, y_bot + 1.2)
            shadow_path.closeSubpath()
            p.fillPath(shadow_path, shadow_ico_color)

            # Frente del triángulo con redondeo visual
            p.fillPath(path, ico_color)


