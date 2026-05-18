"""Aplicacao PyQt6 com bandeja do sistema."""
import os
import sys

from PyQt6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PyQt6.QtGui import QIcon, QAction, QPixmap, QPainter, QColor
from PyQt6.QtCore import QSettings, Qt

from agildo_specs import VERSAO_APP
from agildo_specs.ui import JanelaPrincipal


def _icone_specs() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(QColor(0, 0, 0, 0))
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor("#bd00ff"))
    p.setPen(QColor("#00e5ff"))
    p.drawRoundedRect(8, 8, 48, 48, 8, 8)
    p.setPen(QColor("white"))
    p.drawText(pix.rect(), int(Qt.AlignmentFlag.AlignCenter), "S")
    p.end()
    return QIcon(pix)


class AgildoSpecsApp(QApplication):
    def __init__(self, argv):
        super().__init__(argv)
        self.setApplicationName("AgildoSpecs")
        self.setApplicationVersion(VERSAO_APP)
        self.setQuitOnLastWindowClosed(False)
        self.settings = QSettings("AgildoSoft", "SpecsV1")
        self.janela = JanelaPrincipal(self.settings)
        self._montar_bandeja()

    def _montar_bandeja(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(_icone_specs(), self)
        menu = QMenu()
        menu.addAction("Abrir Agildo Specs", self.mostrar_janela)
        menu.addAction("Atualizar (SMBIOS)", lambda: self.janela.atualizar(True))
        menu.addSeparator()
        menu.addAction("Sair", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._clique_bandeja)
        self.tray.setToolTip(f"Agildo Specs v{VERSAO_APP}")
        self.tray.show()

    def _clique_bandeja(self, razao):
        if razao == QSystemTrayIcon.ActivationReason.Trigger:
            self.mostrar_janela()

    def mostrar_janela(self):
        self.janela.show()
        self.janela.raise_()
        self.janela.activateWindow()

    def esconder_na_bandeja(self):
        self.janela.hide()
        if hasattr(self, "tray"):
            self.tray.showMessage(
                "Agildo Specs",
                "A correr na bandeja. Clique no ícone para abrir.",
                QSystemTrayIcon.MessageIcon.Information,
                2500,
            )


def main():
    if "--help" in sys.argv:
        print("Uso: agildospecs [--mostrar]")
        return 0
    app = AgildoSpecsApp(sys.argv)
    if "--mostrar" in sys.argv or not QSystemTrayIcon.isSystemTrayAvailable():
        app.mostrar_janela()
    elif app.settings.value("mostrar_ao_iniciar", False, type=bool):
        app.mostrar_janela()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
