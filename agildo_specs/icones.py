"""Icone da aplicacao (SVG instalado ou fallback desenhado)."""
import os

from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor
from PyQt6.QtCore import Qt


def caminhos_icone_specs() -> list[str]:
    raiz_pkg = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return [
        "/usr/share/icons/hicolor/scalable/apps/agildospecs.svg",
        os.path.join(raiz_pkg, "data", "icons", "hicolor", "scalable", "apps", "agildospecs.svg"),
    ]


def icone_specs() -> QIcon:
    for caminho in caminhos_icone_specs():
        if os.path.isfile(caminho):
            return QIcon(caminho)
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#1a1028"))
    p.setPen(QColor("#bd00ff"))
    p.drawRoundedRect(4, 4, 56, 56, 10, 10)
    p.setPen(QColor("#00e5ff"))
    p.drawRoundedRect(18, 18, 28, 28, 4, 4)
    p.end()
    return QIcon(pix)
