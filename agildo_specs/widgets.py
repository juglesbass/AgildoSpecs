"""Widgets visuais do Agildo Specs."""
from PyQt6.QtWidgets import (
    QFrame, QVBoxLayout, QLabel, QHBoxLayout, QProgressBar, QWidget, QGridLayout,
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont

from agildo_specs.coletor import ModuloRam

FONTE_UI = "Noto Sans"
# Barras alinhadas a ~3000 / ~14000 no Ryzen 5 5500
_BARRA_SINGLE_MAX = 4500
_BARRA_MULTI_MAX = 18000


class CartaoResumo(QFrame):
    def __init__(self, titulo: str, cor: str):
        super().__init__()
        self.setStyleSheet(
            f"QFrame {{ background: #1e1e1e; border: 1px solid #444; "
            f"border-left: 4px solid {cor}; border-radius: 8px; }}"
        )
        layout = QVBoxLayout(self)
        self.lbl_titulo = QLabel(titulo)
        self.lbl_titulo.setStyleSheet("color: #999; font-size: 11px;")
        self.lbl_valor = QLabel("—")
        self.lbl_valor.setObjectName("destaque")
        self.lbl_valor.setWordWrap(True)
        layout.addWidget(self.lbl_titulo)
        layout.addWidget(self.lbl_valor)

    def definir(self, texto: str):
        self.lbl_valor.setText(texto or "—")


class WidgetDualChannel(QFrame):
    """Visualizacao dos canais A e B."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet("QFrame { background: #1a1a1a; border-radius: 8px; padding: 8px; }")
        raiz = QHBoxLayout(self)
        self.slot_a = self._criar_slot("Canal A")
        self.slot_b = self._criar_slot("Canal B")
        raiz.addWidget(self.slot_a["frame"])
        raiz.addWidget(self.slot_b["frame"])

    def _criar_slot(self, titulo: str) -> dict:
        frame = QFrame()
        frame.setMinimumWidth(150)
        frame.setMinimumHeight(95)
        lay = QVBoxLayout(frame)
        lbl_t = QLabel(titulo)
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_v = QLabel("Vazio")
        lbl_v.setWordWrap(True)
        lbl_v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_v.setStyleSheet("color: #e8e8e8; font-size: 15px; font-weight: bold;")
        lay.addWidget(lbl_t)
        lay.addWidget(lbl_v)
        return {"frame": frame, "titulo": lbl_t, "valor": lbl_v}

    def atualizar(self, modulos: list[ModuloRam]):
        por_canal: dict[str, list[ModuloRam]] = {"A": [], "B": []}
        for m in modulos:
            if not m.preenchido:
                continue
            t = f"{m.canal} {m.banco}".upper()
            if " B" in t or "CANAL B" in t or "CHANNEL B" in t:
                por_canal["B"].append(m)
            elif " A" in t or "CANAL A" in t or "CHANNEL A" in t:
                por_canal["A"].append(m)
            else:
                por_canal["A"].append(m)

        for letra, slot in (("A", self.slot_a), ("B", self.slot_b)):
            mods = por_canal[letra]
            if mods:
                linhas = [f"{m.tamanho}" for m in mods[:2]]
                if mods[0].velocidade:
                    linhas.append(f"{mods[0].velocidade}")
                slot["frame"].setStyleSheet(
                    "QFrame { background: #1a4d3a; border: 2px solid #3ddc84; border-radius: 8px; }"
                )
                slot["titulo"].setStyleSheet(
                    "color: #ffffff; font-weight: bold; font-size: 14px;"
                )
                slot["valor"].setText("\n".join(linhas))
            else:
                slot["frame"].setStyleSheet(
                    "QFrame { background: #252525; border: 2px dashed #555; border-radius: 8px; }"
                )
                slot["titulo"].setStyleSheet(
                    "color: #aaaaaa; font-weight: bold; font-size: 14px;"
                )
                slot["valor"].setText("Vazio")


class PainelBenchmarkCpuZ(QFrame):
    """Painel de pontuacao estilo CPU-Z (single / multi + barras)."""

    def __init__(self):
        super().__init__()
        self.setStyleSheet(
            "QFrame#benchPainel { background: #1c1c1c; border: 1px solid #444; border-radius: 10px; }"
            "QLabel#benchTitulo { color: #bd00ff; font-weight: bold; font-size: 14px; }"
            "QLabel#benchPontos { color: #00e5ff; font-weight: bold; }"
            "QLabel#benchSub { color: #888; font-size: 11px; }"
            "QProgressBar { border: 1px solid #333; border-radius: 4px; text-align: center; "
            "background: #252525; color: #ccc; height: 22px; }"
            "QProgressBar::chunk { background: qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #bd00ff, stop:1 #00e5ff); border-radius: 3px; }"
        )
        self.setObjectName("benchPainel")
        raiz = QVBoxLayout(self)
        raiz.setContentsMargins(20, 16, 20, 16)
        raiz.setSpacing(14)

        tit = QLabel("CPU Benchmark (estilo CPU-Z)")
        tit.setObjectName("benchTitulo")
        raiz.addWidget(tit)

        self.lbl_etapa = QLabel("")
        self.lbl_etapa.setObjectName("benchEtapa")
        self.lbl_etapa.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_etapa.setStyleSheet(
            "color: #e0af68; font-weight: bold; font-size: 13px; padding: 4px;"
        )
        raiz.addWidget(self.lbl_etapa)

        self.bar_total = QProgressBar()
        self.bar_total.setRange(0, 100)
        self.bar_total.setValue(0)
        self.bar_total.setTextVisible(True)
        self.bar_total.setFormat("%p% — progresso geral")
        raiz.addWidget(self.bar_total)

        grelha = QGridLayout()
        grelha.setSpacing(12)
        self.lbl_single = self._bloco_pontos("Single-Core")
        self.lbl_multi = self._bloco_pontos("Multi-Core")
        self.bar_single = QProgressBar()
        self.bar_multi = QProgressBar()
        self.bar_single.setRange(0, _BARRA_SINGLE_MAX)
        self.bar_multi.setRange(0, _BARRA_MULTI_MAX)
        self.bar_single.setFormat("%v pts")
        self.bar_multi.setFormat("%v pts")

        grelha.addWidget(self.lbl_single["wrap"], 0, 0)
        grelha.addWidget(self.bar_single, 1, 0)
        grelha.addWidget(self.lbl_multi["wrap"], 0, 1)
        grelha.addWidget(self.bar_multi, 1, 1)
        raiz.addLayout(grelha)

        self.lbl_extra = QLabel()
        self.lbl_extra.setObjectName("benchSub")
        self.lbl_extra.setWordWrap(True)
        raiz.addWidget(self.lbl_extra)

        self._em_teste = False
        self._msg_etapa = ""
        self._fase_anim = 0
        self._timer_anim = QTimer(self)
        self._timer_anim.timeout.connect(self._tick_animacao)

    def _bloco_pontos(self, nome: str) -> dict:
        wrap = QWidget()
        lay = QVBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lbl_n = QLabel(nome)
        lbl_n.setObjectName("benchSub")
        lbl_p = QLabel("—")
        lbl_p.setObjectName("benchPontos")
        lbl_p.setFont(QFont(FONTE_UI, 28, QFont.Weight.Bold))
        lbl_p.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_t = QLabel("")
        lbl_t.setObjectName("benchSub")
        lbl_t.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(lbl_n)
        lay.addWidget(lbl_p)
        lay.addWidget(lbl_t)
        return {"wrap": wrap, "pontos": lbl_p, "tempo": lbl_t}

    def iniciar_teste(self) -> None:
        """Animacao enquanto o benchmark corre em segundo plano."""
        self._em_teste = True
        self._msg_etapa = "A iniciar"
        self._fase_anim = 0
        self.bar_total.setValue(0)
        self.bar_total.setFormat("%p% — progresso geral")
        self.lbl_etapa.setText("A iniciar teste…")
        self.lbl_single["pontos"].setText("···")
        self.lbl_multi["pontos"].setText("···")
        self.lbl_single["tempo"].setText("A testar")
        self.lbl_multi["tempo"].setText("Aguarde")
        self.lbl_extra.setText("Nao feche a janela — o CPU vai aquecer um pouco.")
        self._barra_indeterminado(self.bar_single, True)
        self._barra_indeterminado(self.bar_multi, True)
        self.lbl_single["pontos"].setStyleSheet("color: #bd00ff;")
        self.lbl_multi["pontos"].setStyleSheet("color: #888;")
        self._timer_anim.start(350)

    def atualizar_progresso(self, mensagem: str, percentual: int) -> None:
        """Atualiza barra global e destaca a fase actual (single / multi / etc.)."""
        self._msg_etapa = mensagem
        self.bar_total.setValue(max(0, min(100, percentual)))
        baixo = mensagem.lower()
        if "single" in baixo:
            self.lbl_single["pontos"].setStyleSheet("color: #00e5ff; font-weight: bold;")
            self.lbl_multi["pontos"].setStyleSheet("color: #555;")
            self.lbl_single["tempo"].setText("A calcular…")
            self._barra_indeterminado(self.bar_single, True)
            self._barra_indeterminado(self.bar_multi, False)
            self.bar_multi.setValue(0)
            self.bar_multi.setFormat("Aguarde…")
        elif "multi" in baixo:
            self.lbl_single["pontos"].setStyleSheet("color: #888;")
            self.lbl_multi["pontos"].setStyleSheet("color: #00e5ff; font-weight: bold;")
            self.lbl_multi["tempo"].setText("A calcular…")
            self._barra_indeterminado(self.bar_single, False)
            self.bar_single.setFormat("Single OK")
            self._barra_indeterminado(self.bar_multi, True)
        elif "memoria" in baixo or "disco" in baixo or "finalizar" in baixo:
            self._barra_indeterminado(self.bar_single, False)
            self._barra_indeterminado(self.bar_multi, False)
            self.bar_single.setFormat("CPU OK")
            self.bar_multi.setFormat("CPU OK")
            self.lbl_single["pontos"].setText("✓")
            self.lbl_multi["pontos"].setText("✓")

    def _barra_indeterminado(self, barra: QProgressBar, activo: bool) -> None:
        if activo:
            barra.setRange(0, 0)
            barra.setFormat("A testar…")
        else:
            barra.setRange(0, _BARRA_SINGLE_MAX if barra is self.bar_single else _BARRA_MULTI_MAX)

    def _tick_animacao(self) -> None:
        if not self._em_teste:
            return
        self._fase_anim = (self._fase_anim + 1) % 4
        pontos = "." * self._fase_anim
        self.lbl_etapa.setText(f"{self._msg_etapa}{pontos}")
        # Pulso suave nas pontuacoes em teste
        cor = "#00e5ff" if self._fase_anim % 2 == 0 else "#bd00ff"
        if "single" in self._msg_etapa.lower():
            self.lbl_single["pontos"].setStyleSheet(f"color: {cor}; font-weight: bold;")
        elif "multi" in self._msg_etapa.lower():
            self.lbl_multi["pontos"].setStyleSheet(f"color: {cor}; font-weight: bold;")

    def parar_teste(self) -> None:
        self._em_teste = False
        self._timer_anim.stop()
        self.lbl_single["pontos"].setStyleSheet("")
        self.lbl_multi["pontos"].setStyleSheet("")
        self.bar_single.setRange(0, _BARRA_SINGLE_MAX)
        self.bar_multi.setRange(0, _BARRA_MULTI_MAX)
        self.bar_single.setFormat("%v pts")
        self.bar_multi.setFormat("%v pts")
        self.bar_total.setFormat("%p% — concluido")
        self.bar_total.setValue(100)
        self.lbl_etapa.setText("Teste concluido!")

    def atualizar(self, dados: dict):
        if self._em_teste:
            self.parar_teste()
        meta = dados.get("_meta") or {}
        single = int(meta.get("single") or dados.get("cpu_single_pontos") or 0)
        multi = int(meta.get("multi") or dados.get("cpu_multi_pontos") or 0)
        nucleos = meta.get("nucleos") or dados.get("cpu_nucleos") or "?"

        self.lbl_single["pontos"].setText(str(single) if single else "—")
        self.lbl_single["tempo"].setText(dados.get("cpu_single_tempo", ""))
        self.lbl_multi["pontos"].setText(str(multi) if multi else "—")
        self.lbl_multi["tempo"].setText(dados.get("cpu_multi_tempo", ""))
        self.bar_single.setValue(min(single, _BARRA_SINGLE_MAX))
        self.bar_multi.setValue(min(multi, _BARRA_MULTI_MAX))

        extras = [
            f"Nucleos logicos: {nucleos}",
            f"Memoria — latencia: {dados.get('mem_latencia', '—')} | banda: {dados.get('mem_largura_banda', '—')}",
            f"Disco (escrita temp.): {dados.get('disco_escrita', '—')} ({dados.get('disco_tempo', '—')})",
        ]
        self.lbl_extra.setText("\n".join(extras))
