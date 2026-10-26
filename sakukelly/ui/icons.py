"""Generador de iconografía vectorial nativa para Sakukelly.

Renderiza iconos nítidos y escalables mediante QPainterPath y QPainter, sin
depender de QtSvg ni paquetes externos, garantizando compatibilidad total
con HiDPI y los temas dinámicos de la aplicación.
"""
from PyQt6.QtGui import (QPainter, QPainterPath, QColor, QPen, QBrush,
                         QPixmap, QIcon)
from PyQt6.QtCore import Qt, QPointF, QRectF


def _draw_play(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    r = 2.2 * sc
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    path = QPainterPath()
    path.moveTo(18 * sc + r, 12 * sc + r * 0.6)
    path.lineTo(34.5 * sc - r, 23 * sc)
    path.quadTo(36 * sc, 24 * sc, 34.5 * sc - r, 25 * sc)
    path.lineTo(18 * sc + r, 36 * sc - r * 0.6)
    path.quadTo(17 * sc, 36.5 * sc, 17 * sc, 35 * sc)
    path.lineTo(17 * sc, 13 * sc)
    path.quadTo(17 * sc, 11.5 * sc, 18 * sc + r, 12 * sc + r * 0.6)
    path.closeSubpath()
    p.fillPath(path, color)


def _draw_pause(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    r = 2.8 * sc
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(14 * sc, 12 * sc, 6.5 * sc, 24 * sc), r, r)
    p.drawRoundedRect(QRectF(27.5 * sc, 12 * sc, 6.5 * sc, 24 * sc), r, r)


def _draw_prev(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    # Barra izquierda redondeada
    p.drawRoundedRect(QRectF(11.5 * sc, 13 * sc, 4.0 * sc, 22 * sc), 1.8 * sc, 1.8 * sc)
    # Triángulo apuntando a la izquierda
    path = QPainterPath()
    r = 1.8 * sc
    path.moveTo(35 * sc - r, 13 * sc + r * 0.6)
    path.lineTo(19 * sc + r, 23 * sc)
    path.quadTo(17.5 * sc, 24 * sc, 19 * sc + r, 25 * sc)
    path.lineTo(35 * sc - r, 35 * sc - r * 0.6)
    path.quadTo(36 * sc, 35.5 * sc, 36 * sc, 34 * sc)
    path.lineTo(36 * sc, 14 * sc)
    path.quadTo(36 * sc, 12.5 * sc, 35 * sc - r, 13 * sc + r * 0.6)
    path.closeSubpath()
    p.fillPath(path, color)


def _draw_next(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    # Triángulo apuntando a la derecha
    path = QPainterPath()
    r = 1.8 * sc
    path.moveTo(13 * sc + r, 13 * sc + r * 0.6)
    path.lineTo(29 * sc - r, 23 * sc)
    path.quadTo(30.5 * sc, 24 * sc, 29 * sc - r, 25 * sc)
    path.lineTo(13 * sc + r, 35 * sc - r * 0.6)
    path.quadTo(12 * sc, 35.5 * sc, 12 * sc, 34 * sc)
    path.lineTo(12 * sc, 14 * sc)
    path.quadTo(12 * sc, 12.5 * sc, 13 * sc + r, 13 * sc + r * 0.6)
    path.closeSubpath()
    p.fillPath(path, color)
    # Barra derecha redondeada
    p.drawRoundedRect(QRectF(32.5 * sc, 13 * sc, 4.0 * sc, 22 * sc), 1.8 * sc, 1.8 * sc)


def _draw_shuffle(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    stroke = max(2.6, 3.2 * sc)
    pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Flecha 1 (inferior a superior)
    p1 = QPainterPath()
    p1.moveTo(10 * sc, 34 * sc)
    p1.cubicTo(19 * sc, 34 * sc, 20 * sc, 14 * sc, 35 * sc, 14 * sc)
    p.drawPath(p1)
    # Punta flecha 1
    p.drawLine(QPointF(29 * sc, 9.5 * sc), QPointF(36 * sc, 14 * sc))
    p.drawLine(QPointF(29 * sc, 18.5 * sc), QPointF(36 * sc, 14 * sc))

    # Flecha 2 con cruce limpio
    p2 = QPainterPath()
    p2.moveTo(10 * sc, 14 * sc)
    p2.cubicTo(18 * sc, 14 * sc, 20 * sc, 22 * sc, 22 * sc, 24.5 * sc)
    p.drawPath(p2)
    p3 = QPainterPath()
    p3.moveTo(25.5 * sc, 27.5 * sc)
    p3.cubicTo(27.5 * sc, 29.5 * sc, 29 * sc, 34 * sc, 35 * sc, 34 * sc)
    p.drawPath(p3)
    # Punta flecha 2
    p.drawLine(QPointF(29 * sc, 29.5 * sc), QPointF(36 * sc, 34 * sc))
    p.drawLine(QPointF(29 * sc, 38.5 * sc), QPointF(36 * sc, 34 * sc))


def _draw_repeat(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    stroke = max(2.6, 3.2 * sc)
    pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Arco superior (hacia la derecha)
    p1 = QPainterPath()
    p1.moveTo(17 * sc, 13 * sc)
    p1.lineTo(33 * sc, 13 * sc)
    p1.cubicTo(38 * sc, 13 * sc, 38 * sc, 18 * sc, 38 * sc, 21 * sc)
    p.drawPath(p1)
    p.drawLine(QPointF(29 * sc, 8.5 * sc), QPointF(35 * sc, 13 * sc))
    p.drawLine(QPointF(29 * sc, 17.5 * sc), QPointF(35 * sc, 13 * sc))

    # Arco inferior (hacia la izquierda)
    p2 = QPainterPath()
    p2.moveTo(31 * sc, 35 * sc)
    p2.lineTo(15 * sc, 35 * sc)
    p2.cubicTo(10 * sc, 35 * sc, 10 * sc, 30 * sc, 10 * sc, 27 * sc)
    p.drawPath(p2)
    p.drawLine(QPointF(19 * sc, 30.5 * sc), QPointF(13 * sc, 35 * sc))
    p.drawLine(QPointF(19 * sc, 39.5 * sc), QPointF(13 * sc, 35 * sc))


def _draw_heart(p: QPainter, color: QColor, s: float, filled: bool = False):
    sc = s / 48.0
    path = QPainterPath()
    path.moveTo(24 * sc, 38 * sc)
    path.cubicTo(10 * sc, 27 * sc, 8 * sc, 15 * sc, 15.5 * sc, 11 * sc)
    path.cubicTo(20 * sc, 8.5 * sc, 23 * sc, 11 * sc, 24 * sc, 14 * sc)
    path.cubicTo(25 * sc, 11 * sc, 28 * sc, 8.5 * sc, 32.5 * sc, 11 * sc)
    path.cubicTo(40 * sc, 15 * sc, 38 * sc, 27 * sc, 24 * sc, 38 * sc)
    path.closeSubpath()
    if filled:
        p.setPen(Qt.PenStyle.NoPen)
        p.fillPath(path, color)
    else:
        stroke = max(2.6, 3.0 * sc)
        p.setPen(QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


def _draw_download(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    stroke = max(2.6, 3.0 * sc)
    pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Flecha vertical
    p.drawLine(QPointF(24 * sc, 11 * sc), QPointF(24 * sc, 27 * sc))
    p.drawLine(QPointF(16 * sc, 20 * sc), QPointF(24 * sc, 28 * sc))
    p.drawLine(QPointF(32 * sc, 20 * sc), QPointF(24 * sc, 28 * sc))
    # Bandeja
    p.drawLine(QPointF(12 * sc, 34 * sc), QPointF(36 * sc, 34 * sc))


def _draw_miniplayer(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    stroke = max(2.6, 3.0 * sc)
    pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Marco de ventana
    p.drawRoundedRect(QRectF(10 * sc, 12 * sc, 28 * sc, 23 * sc), 4 * sc, 4 * sc)
    # Sub-pantalla PiP
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    p.drawRoundedRect(QRectF(23 * sc, 22.5 * sc, 12 * sc, 9.5 * sc), 2 * sc, 2 * sc)


def _draw_youtube(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    stroke = max(2.6, 3.0 * sc)
    pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(9 * sc, 13 * sc, 30 * sc, 22 * sc), 6 * sc, 6 * sc)
    # Triángulo
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QBrush(color))
    path = QPainterPath()
    path.moveTo(21 * sc, 18.5 * sc)
    path.lineTo(29 * sc, 24 * sc)
    path.lineTo(21 * sc, 29.5 * sc)
    path.closeSubpath()
    p.fillPath(path, color)


def _draw_lyrics(p: QPainter, color: QColor, s: float):
    sc = s / 48.0
    stroke = max(2.6, 3.0 * sc)
    pen = QPen(color, stroke, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Cápsula
    p.drawRoundedRect(QRectF(18.5 * sc, 10 * sc, 11 * sc, 17 * sc), 5.5 * sc, 5.5 * sc)
    # Arco receptor
    p.drawArc(QRectF(14.5 * sc, 15 * sc, 19 * sc, 16 * sc), 0, -180 * 16)
    # Soporte y base
    p.drawLine(QPointF(24 * sc, 31 * sc), QPointF(24 * sc, 37 * sc))
    p.drawLine(QPointF(17 * sc, 37 * sc), QPointF(31 * sc, 37 * sc))


_REGISTRY = {
    "play": _draw_play,
    "pause": _draw_pause,
    "prev": _draw_prev,
    "next": _draw_next,
    "shuffle": _draw_shuffle,
    "repeat": _draw_repeat,
    "heart": lambda p, c, s: _draw_heart(p, c, s, False),
    "heart_filled": lambda p, c, s: _draw_heart(p, c, s, True),
    "download": _draw_download,
    "miniplayer": _draw_miniplayer,
    "youtube": _draw_youtube,
    "lyrics": _draw_lyrics,
}


def render_icon_pixmap(name: str, color_hex: str, size: int = 48, scale: float = 2.0) -> QPixmap:
    """Renderiza un icono vectorial como QPixmap con soporte HiDPI."""
    canvas_size = int(size * scale)
    pix = QPixmap(canvas_size, canvas_size)
    pix.fill(Qt.GlobalColor.transparent)
    fn = _REGISTRY.get(name)
    if not fn:
        return pix

    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    color = QColor(color_hex)
    fn(p, color, canvas_size)
    p.end()
    pix.setDevicePixelRatio(scale)
    return pix


def get_icon(name: str, color_hex: str, size: int = 48, active_color_hex: str = None) -> QIcon:
    """Crea un QIcon nítido con el color indicado, con soporte para estado activo."""
    icon = QIcon()
    pix_off = render_icon_pixmap(name, color_hex, size=size)
    icon.addPixmap(pix_off, QIcon.Mode.Normal, QIcon.State.Off)
    if active_color_hex:
        pix_on = render_icon_pixmap(name, active_color_hex, size=size)
        icon.addPixmap(pix_on, QIcon.Mode.Normal, QIcon.State.On)
        icon.addPixmap(pix_on, QIcon.Mode.Active, QIcon.State.On)
    else:
        icon.addPixmap(pix_off, QIcon.Mode.Normal, QIcon.State.On)
    return icon
