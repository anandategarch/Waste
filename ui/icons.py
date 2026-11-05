"""icons.py — sistem ikon vektor monokrom (v2.17.0 rombak P0).

Mengganti sup-emoji (≈215 emoji warna sebelumnya) dengan ikon vektor
profesional: digambar via QPainter, konsisten stroke, skala bebas,
warna mengikuti palet tema (monokrom = profesional).

TANPA dependensi baru: QPainter/QPixmap/QIcon inti Qt. TANPA file SVG
eksternal (self-contained — ikon = fungsi draw).

API:
- ``Icon(name, size=16, color=None)`` → QWidget u/ ditempatkan di layout.
- ``make_qicon(name, size=16, color=None)`` → QIcon u/ QAction/QPushButton.
- ``icon_pixmap(name, size=16, color=None)`` → QPixmap u/ QLabel.setPixmap.

Set ikon (18): chart_bar, receipt, store, package, sparkle, trending_down,
coins, calendar, flask, link, trending_up, shuffle, save, help, play,
calculator, eye, building.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QPainter,
    QPainterPath,
    QPalette,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QWidget


def _pen(color: QColor, rect: QRectF, w_ratio: float = 0.10) -> QPen:
    """Pen monokrom: stroke proporsional ukuran, ujung membulat."""
    pen = QPen(color)
    pen.setWidthF(max(1.0, rect.width() * w_ratio))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    return pen


# ------------------------------------------------------------
# FUNGSI DRAW — masing-masing (painter, rect, color)
# ------------------------------------------------------------
def _chart_bar(p: QPainter, r: QRectF, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    w = r.width() * 0.18
    gap = r.width() * 0.08
    x0 = r.left() + gap
    heights = [0.45, 0.7, 0.55, 0.9]
    for i, h in enumerate(heights):
        bh = r.height() * h
        p.drawRect(QRectF(x0 + i * (w + gap), r.bottom() - bh, w, bh))


def _receipt(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.08)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Body dengan tepi bawah zigzag.
    path = QPainterPath()
    top = r.top()
    bot = r.bottom()
    path.moveTo(r.left(), top)
    path.lineTo(r.right(), top)
    path.lineTo(r.right(), bot - r.height() * 0.06)
    n = 3
    step = r.width() / n
    for i in range(n):
        path.lineTo(r.right() - step * (i + 0.5), bot)
        path.lineTo(r.right() - step * (i + 1), bot - r.height() * 0.06)
    path.lineTo(r.left(), top)
    p.drawPath(path)
    # Garis isi (3 baris teks).
    p.setPen(_pen(c, r, 0.06))
    for i, y in enumerate((0.3, 0.5, 0.7)):
        p.drawLine(QRectF(r.left() + r.width() * 0.18,
                          r.top() + r.height() * y,
                          r.width() * 0.64, 0).topLeft(),
                   QRectF(r.left() + r.width() * 0.82,
                          r.top() + r.height() * y, 0, 0).topLeft())


def _store(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Atap trapesium.
    aw = r.width() * 0.12
    roof = QPainterPath()
    roof.moveTo(r.left(), r.top() + aw)
    roof.lineTo(r.left() + aw, r.top())
    roof.lineTo(r.right() - aw, r.top())
    roof.lineTo(r.right(), r.top() + aw)
    roof.closeSubpath()
    p.drawPath(roof)
    # Badan.
    body = QRectF(r.left(), r.top() + aw, r.width(), r.height() - aw)
    p.drawRect(body)
    # Pintu.
    door = QRectF(r.center().x() - r.width() * 0.12,
                  body.bottom() - r.height() * 0.32,
                  r.width() * 0.24, r.height() * 0.32)
    p.drawRect(door)


def _package(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r)
    # Lid atas + garis tengah vertikal ke lid.
    mid_y = r.top() + r.height() * 0.3
    p.drawLine(QPointF(r.center().x(), r.top()),
               QPointF(r.center().x(), mid_y))
    p.drawLine(QPointF(r.left(), mid_y), QPointF(r.right(), mid_y))


def _sparkle(p: QPainter, r: QRectF, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    cx, cy = r.center().x(), r.center().y()
    rad = r.width() * 0.5
    # Bintang 4-tajuk (diamond memanjang + 2 sisi pendek).
    path = QPainterPath()
    path.moveTo(cx, cy - rad)
    path.quadTo(cx, cy, cx + rad, cy)
    path.quadTo(cx, cy, cx, cy + rad)
    path.quadTo(cx, cy, cx - rad, cy)
    path.quadTo(cx, cy, cx, cy - rad)
    p.drawPath(path)
    # Spark kecil.
    p.setBrush(c)
    sr = r.width() * 0.12
    for (sx, sy) in ((r.right() - sr, r.top() + sr * 2),
                     (r.left() + sr * 2, r.bottom() - sr)):
        p.drawEllipse(QRectF(sx - sr / 2, sy - sr / 2, sr, sr))


def _trending_down(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.11)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Polyline turun.
    p.drawLine(QRectF(r.left(), r.top() + r.height() * 0.25, 0, 0).topLeft(),
               QRectF(r.center().x(), r.top() + r.height() * 0.5, 0, 0).topLeft())
    p.drawLine(QRectF(r.center().x(), r.top() + r.height() * 0.5, 0, 0).topLeft(),
               QRectF(r.right(), r.bottom() - r.height() * 0.1, 0, 0).topLeft())
    # Anak panah.
    ah = r.width() * 0.3
    p.drawLine(QRectF(r.right() - ah, r.bottom() - r.height() * 0.35, 0, 0).topLeft(),
               QRectF(r.right(), r.bottom() - r.height() * 0.1, 0, 0).topLeft())
    p.drawLine(QRectF(r.right() - ah * 0.4, r.bottom(), 0, 0).topLeft(),
               QRectF(r.right(), r.bottom() - r.height() * 0.1, 0, 0).topLeft())


def _coins(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.08)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Dua koin elips bertumpuk.
    ew, eh = r.width() * 0.8, r.height() * 0.28
    p.drawEllipse(QRectF(r.left() + r.width() * 0.1,
                         r.top() + r.height() * 0.2, ew, eh))
    p.drawEllipse(QRectF(r.left() + r.width() * 0.1,
                         r.top() + r.height() * 0.52, ew, eh))


def _calendar(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    body = QRectF(r.left(), r.top() + r.height() * 0.22,
                  r.width(), r.height() * 0.78)
    p.drawRect(body)
    # Binding atas (2 kaki).
    for fx in (0.28, 0.72):
        p.drawLine(QRectF(r.left() + r.width() * fx,
                          r.top(), 0, r.height() * 0.3).topLeft(),
                   QRectF(r.left() + r.width() * fx,
                          r.top() + r.height() * 0.3, 0, 0).bottomLeft())
    # Garis pemisah header.
    p.drawLine(QRectF(r.left(), r.top() + r.height() * 0.42,
                      r.width(), 0).topLeft(),
               QRectF(r.right(), r.top() + r.height() * 0.42, 0, 0).topLeft())
    # Titik grid 2x2.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    dot = r.width() * 0.08
    for gx in (0.3, 0.7):
        for gy in (0.62, 0.82):
            p.drawRect(QRectF(r.left() + r.width() * gx - dot / 2,
                              r.top() + r.height() * gy - dot / 2, dot, dot))


def _flask(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Leher + labu Erlenmeyer.
    path = QPainterPath()
    nx = r.center().x()
    nw = r.width() * 0.2
    path.moveTo(nx - nw / 2, r.top())
    path.lineTo(nx + nw / 2, r.top())
    path.lineTo(nx + nw / 2, r.top() + r.height() * 0.35)
    path.lineTo(r.right(), r.bottom())
    path.lineTo(r.left(), r.bottom())
    path.lineTo(nx - nw / 2, r.top() + r.height() * 0.35)
    path.closeSubpath()
    p.drawPath(path)
    # Garis cairan.
    p.drawLine(QRectF(r.left() + r.width() * 0.2,
                      r.bottom() - r.height() * 0.3, 0, 0).topLeft(),
               QRectF(r.right() - r.width() * 0.2,
                      r.bottom() - r.height() * 0.3, 0, 0).topLeft())


def _link(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.1)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Dua elips miring saling kait.
    import math
    ang = math.radians(35)
    p.save()
    p.translate(r.center().x(), r.center().y())
    p.rotate(ang)
    p.drawEllipse(QRectF(-r.width() * 0.45, -r.height() * 0.2,
                         r.width() * 0.4, r.height() * 0.4))
    p.drawEllipse(QRectF(r.width() * 0.05, -r.height() * 0.2,
                         r.width() * 0.4, r.height() * 0.4))
    p.restore()


def _trending_up(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.11)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QRectF(r.left(), r.bottom() - r.height() * 0.15, 0, 0).topLeft(),
               QRectF(r.center().x(), r.top() + r.height() * 0.5, 0, 0).topLeft())
    p.drawLine(QRectF(r.center().x(), r.top() + r.height() * 0.5, 0, 0).topLeft(),
               QRectF(r.right(), r.top() + r.height() * 0.1, 0, 0).topLeft())
    ah = r.width() * 0.3
    p.drawLine(QRectF(r.right() - ah, r.top() + r.height() * 0.35, 0, 0).topLeft(),
               QRectF(r.right(), r.top() + r.height() * 0.1, 0, 0).topLeft())
    p.drawLine(QRectF(r.right() - ah * 0.4, r.top(), 0, 0).topLeft(),
               QRectF(r.right(), r.top() + r.height() * 0.1, 0, 0).topLeft())


def _shuffle(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.1)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Dua panah bersilang.
    p.drawLine(QRectF(r.left(), r.top() + r.height() * 0.3, 0, 0).topLeft(),
               QRectF(r.right() - r.width() * 0.2,
                      r.top() + r.height() * 0.3, 0, 0).topLeft())
    p.drawLine(QRectF(r.left(), r.bottom() - r.height() * 0.3, 0, 0).topLeft(),
               QRectF(r.right() - r.width() * 0.2,
                      r.bottom() - r.height() * 0.3, 0, 0).topLeft())
    # Ujung panah kanan-atas & kanan-bawah.
    ah = r.width() * 0.22
    p.drawLine(QRectF(r.right() - ah,
                      r.top() + r.height() * 0.1, 0, 0).topLeft(),
               QRectF(r.right(),
                      r.top() + r.height() * 0.3, 0, 0).topLeft())
    p.drawLine(QRectF(r.right() - ah,
                      r.top() + r.height() * 0.5, 0, 0).topLeft(),
               QRectF(r.right(),
                      r.top() + r.height() * 0.3, 0, 0).topLeft())
    p.drawLine(QRectF(r.right() - ah,
                      r.bottom() - r.height() * 0.1, 0, 0).topLeft(),
               QRectF(r.right(),
                      r.bottom() - r.height() * 0.3, 0, 0).topLeft())
    p.drawLine(QRectF(r.right() - ah,
                      r.bottom() - r.height() * 0.5, 0, 0).topLeft(),
               QRectF(r.right(),
                      r.bottom() - r.height() * 0.3, 0, 0).topLeft())


def _save(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r)
    # Slot disket atas (label).
    p.setBrush(c)
    p.drawRect(QRectF(r.left() + r.width() * 0.2,
                      r.top() + r.height() * 0.1,
                      r.width() * 0.6, r.height() * 0.3))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Lubang disk (lingkaran) bawah.
    p.drawEllipse(QRectF(r.center().x() - r.width() * 0.18,
                         r.top() + r.height() * 0.52,
                         r.width() * 0.36, r.height() * 0.36))


def _help(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawEllipse(r)
    f = QFont()
    f.setBold(True)
    f.setPointSizeF(r.width() * 0.55)
    p.setFont(f)
    p.setPen(QPen(c))
    p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), "?")


def _play(p: QPainter, r: QRectF, c: QColor) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    path = QPainterPath()
    path.moveTo(r.left() + r.width() * 0.2, r.top() + r.height() * 0.12)
    path.lineTo(r.right() - r.width() * 0.12, r.center().y())
    path.lineTo(r.left() + r.width() * 0.2, r.bottom() - r.height() * 0.12)
    path.closeSubpath()
    p.drawPath(path)


def _calculator(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.08)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r)
    # Layar atas.
    p.setBrush(c)
    p.drawRect(QRectF(r.left() + r.width() * 0.12,
                      r.top() + r.height() * 0.12,
                      r.width() * 0.76, r.height() * 0.22))
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Tombol 2x3.
    bw, bh = r.width() * 0.22, r.height() * 0.16
    for row in range(3):
        for col in range(2):
            x = r.left() + r.width() * (0.18 + col * 0.34) - bw / 2
            y = r.top() + r.height() * (0.45 + row * 0.18) - bh / 2
            p.drawRect(QRectF(x, y, bw, bh))


def _eye(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.1)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Bentuk mata (lens almond).
    path = QPainterPath()
    path.moveTo(r.left(), r.center().y())
    path.quadTo(r.center().x(), r.top() + r.height() * 0.05,
                r.right(), r.center().y())
    path.quadTo(r.center().x(), r.bottom() - r.height() * 0.05,
                r.left(), r.center().y())
    p.drawPath(path)
    # Pupil.
    p.setBrush(c)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(QRectF(r.center().x() - r.width() * 0.12,
                         r.center().y() - r.height() * 0.12,
                         r.width() * 0.24, r.height() * 0.24))


def _building(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.08)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRect(r)
    # Grid jendela 3x3.
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    w = r.width() * 0.16
    for row in range(3):
        for col in range(3):
            x = r.left() + r.width() * (0.18 + col * 0.27) - w / 2
            y = r.top() + r.height() * (0.18 + row * 0.27) - w / 2
            p.drawRect(QRectF(x, y, w, w))


def _folder(p: QPainter, r: QRectF, c: QColor) -> None:
    pen = _pen(c, r, 0.09)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    # Tab atas (kiri) + body bawah (kanan, lebih tinggi).
    body = QRectF(r.left(), r.top() + r.height() * 0.25,
                  r.width(), r.height() * 0.75)
    p.drawRect(body)
    # Tab: dari pojok kiri-atas body → naik → ke kanan (sepertiga) → turun.
    tab = QPainterPath()
    tw = r.width() * 0.4
    th = r.height() * 0.25
    tab.moveTo(r.left(), r.top() + th)
    tab.lineTo(r.left() + tw, r.top() + th)
    tab.lineTo(r.left() + tw + r.width() * 0.08, r.top())
    tab.lineTo(r.left() + r.width(), r.top())
    tab.lineTo(r.left() + r.width(), r.top() + th)
    p.drawPath(tab)


# Registry nama → fungsi draw.
_ICONS: dict[str, callable] = {
    "chart_bar": _chart_bar,
    "receipt": _receipt,
    "store": _store,
    "package": _package,
    "sparkle": _sparkle,
    "trending_down": _trending_down,
    "coins": _coins,
    "calendar": _calendar,
    "flask": _flask,
    "link": _link,
    "trending_up": _trending_up,
    "shuffle": _shuffle,
    "save": _save,
    "help": _help,
    "play": _play,
    "calculator": _calculator,
    "eye": _eye,
    "building": _building,
    "folder": _folder,
}

# Alias emoji → nama ikon (pemetaan migrasi cepat).
EMOJI_TO_ICON: dict[str, str] = {
    "📊": "chart_bar", "🧾": "receipt", "🏬": "store", "📦": "package",
    "🆕": "sparkle", "📉": "trending_down", "💰": "coins", "📅": "calendar",
    "🧪": "flask", "🔗": "link", "📈": "trending_up", "🔀": "shuffle",
    "💾": "save", "❓": "help", "▶": "play", "🧮": "calculator",
    "👀": "eye", "🏢": "building",
}


def icon_names() -> list[str]:
    return list(_ICONS)


def has_icon(name: str) -> bool:
    return name in _ICONS


def icon_pixmap(name: str, size: int = 16,
                color: QColor | None = None) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    draw = _ICONS.get(name)
    if draw is None:
        return pm
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    c = color if color is not None else QColor("#0f172a")
    draw(p, QRectF(0, 0, size, size).adjusted(1, 1, -1, -1), c)
    p.end()
    return pm


def make_qicon(name: str, size: int = 16,
               color: QColor | None = None) -> QIcon:
    return QIcon(icon_pixmap(name, size, color))


class Icon(QWidget):
    """Widget ikon vektor monokrom — ditempatkan di layout.

    Warna default = WindowText palet (mengikuti teks tema, terang/gelap).
    """

    def __init__(self, name: str, size: int = 16,
                 color: QColor | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name = name
        self._size = size
        self._color = color
        self.setFixedSize(size, size)

    def set_name(self, name: str) -> None:
        self._name = name
        self.update()

    def set_color(self, color: QColor | None) -> None:
        self._color = color
        self.update()

    def paintEvent(self, _event) -> None:
        draw = _ICONS.get(self._name)
        if draw is None:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = self._color if self._color is not None else \
            self.palette().color(QPalette.ColorRole.WindowText)
        draw(p, QRectF(0, 0, self._size, self._size).adjusted(1, 1, -1, -1), c)
        p.end()
