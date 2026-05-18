"""Janela principal do Agildo Specs."""
from __future__ import annotations

import json
import os

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QMessageBox, QFormLayout,
    QScrollArea, QFrame, QHeaderView, QAbstractItemView, QCheckBox,
    QFileDialog, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QTimer
from PyQt6.QtGui import QFont, QGuiApplication

from agildo_specs import VERSAO_APP
from agildo_specs.coletor import (
    DadosHardware, coletar_hardware, coletar_sensores, total_ram_texto, ModuloRam,
    gpu_resumo_texto,
)
from agildo_specs.relatorio import para_texto, para_json, comparar
from agildo_specs.widgets import CartaoResumo, WidgetDualChannel, PainelBenchmarkCpuZ

FONTE_UI = "Noto Sans"

ESTILO_ESCURO = """
    QMainWindow, QWidget { background-color: #141414; color: #e8e8e8; font-size: 13px; }
    QTabWidget::pane { border: 1px solid #444; border-radius: 6px; background: #1a1a1a; }
    QTabBar::tab { background: #252525; color: #bbb; padding: 8px 14px; margin-right: 2px;
        border-top-left-radius: 6px; border-top-right-radius: 6px; }
    QTabBar::tab:selected { background: #bd00ff; color: white; font-weight: bold; }
    QLabel#destaque { font-size: 20px; font-weight: bold; color: #00e5ff; }
    QLabel#aviso { color: #f39c12; }
    QTableWidget { background: #1e1e1e; gridline-color: #333; border: 1px solid #444; }
    QHeaderView::section { background: #2a2a2a; color: #bd00ff; padding: 6px; font-weight: bold; }
    QPushButton { background: #bd00ff; color: white; font-weight: bold; padding: 8px 14px;
        border: none; border-radius: 6px; }
    QPushButton:hover { background: #d040ff; }
    QPushButton#secundario { background: #333; }
    QPushButton#secundario:hover { background: #444; }
    QLabel#form_rotulo { color: #888; min-width: 170px; max-width: 170px; font-weight: bold; }
    QLabel#form_valor { color: #f0f0f0; padding-left: 4px; }
    QCheckBox { spacing: 6px; }
"""

ESTILO_CLARO = """
    QMainWindow, QWidget { background-color: #f4f4f4; color: #222; font-size: 13px; }
    QTabWidget::pane { border: 1px solid #ccc; background: #fff; }
    QTabBar::tab { background: #e0e0e0; padding: 8px 14px; }
    QTabBar::tab:selected { background: #7b2cbf; color: white; font-weight: bold; }
    QLabel#destaque { font-size: 20px; font-weight: bold; color: #0066aa; }
    QTableWidget { background: #fff; }
    QPushButton { background: #7b2cbf; color: white; font-weight: bold; padding: 8px 14px; border-radius: 6px; }
    QPushButton#secundario { background: #ccc; color: #222; }
"""


class WorkerColeta(QThread):
    pronto = pyqtSignal(object)

    def __init__(self, smbios: bool, benchmark: bool):
        super().__init__()
        self.smbios = smbios
        self.benchmark = benchmark

    def run(self):
        self.pronto.emit(coletar_hardware(self.smbios, self.benchmark))


class WorkerBenchmark(QThread):
    progresso = pyqtSignal(str, int)
    pronto = pyqtSignal(object)

    def run(self):
        from agildo_specs.benchmark import executar_benchmark

        def _cb(msg: str, pct: int) -> None:
            self.progresso.emit(msg, pct)

        self.pronto.emit(executar_benchmark(progresso=_cb))


class JanelaPrincipal(QMainWindow):
    def __init__(self, settings: QSettings):
        super().__init__()
        self.settings = settings
        self._dados: DadosHardware | None = None
        self._worker: WorkerColeta | None = None
        self._worker_bench: WorkerBenchmark | None = None
        self._idx_aba_sensores = 6
        self._idx_aba_benchmark = 8
        self._timer_sensores = QTimer(self)
        self._timer_sensores.setInterval(1500)
        self._timer_sensores.timeout.connect(self._tick_sensores)
        self.setWindowTitle(f"Agildo Specs v{VERSAO_APP}")
        self.resize(900, 700)
        self._montar_ui()
        self._aplicar_tema(self.settings.value("tema_escuro", True, type=bool))
        aba = int(self.settings.value("ultima_aba", 0))
        if 0 <= aba < self.abas.count():
            self.abas.setCurrentIndex(aba)
        if self.settings.value("atualizar_ao_abrir", True, type=bool):
            self.atualizar(smbios=True)

    def _montar_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        raiz = QVBoxLayout(central)
        raiz.setContentsMargins(12, 12, 12, 12)

        topo = QHBoxLayout()
        titulo = QLabel("Agildo Specs")
        titulo.setFont(QFont(FONTE_UI, 17, QFont.Weight.Bold))
        titulo.setStyleSheet("color: #bd00ff;")
        topo.addWidget(titulo)
        topo.addStretch()

        for texto, slot, sec in (
            ("Atualizar", lambda: self.atualizar(False), False),
            ("SMBIOS", lambda: self.atualizar(True), True),
            ("Benchmark", self._iniciar_benchmark, True),
            ("Copiar", self._copiar, True),
            ("JSON", self._exportar_json, True),
            ("Comparar", self._comparar, True),
        ):
            b = QPushButton(texto)
            if sec:
                b.setObjectName("secundario")
            b.clicked.connect(slot)
            topo.addWidget(b)
        raiz.addLayout(topo)

        self.lbl_aviso = QLabel()
        self.lbl_aviso.setObjectName("aviso")
        self.lbl_aviso.setWordWrap(True)
        self.lbl_aviso.hide()
        raiz.addWidget(self.lbl_aviso)

        cartoes = QHBoxLayout()
        self.card_cpu = CartaoResumo("CPU", "#00e5ff")
        self.card_ram = CartaoResumo("RAM", "#e0af68")
        self.card_gpu = CartaoResumo("GPU", "#ff6b6b")
        self.card_canal = CartaoResumo("DUAL CH.", "#2ecc71")
        self.card_placa = CartaoResumo("PLACA", "#bb9af7")
        for c in (self.card_cpu, self.card_ram, self.card_gpu, self.card_canal, self.card_placa):
            cartoes.addWidget(c)
        raiz.addLayout(cartoes)

        opts = QHBoxLayout()
        self.chk_tema = QCheckBox("Tema escuro")
        self.chk_tema.setChecked(self.settings.value("tema_escuro", True, type=bool))
        self.chk_tema.toggled.connect(self._toggle_tema)
        self.chk_auto = QCheckBox("Atualizar ao abrir")
        self.chk_auto.setChecked(self.settings.value("atualizar_ao_abrir", True, type=bool))
        self.chk_auto.toggled.connect(lambda v: self.settings.setValue("atualizar_ao_abrir", v))
        self.chk_bandeja = QCheckBox("Minimizar para bandeja")
        self.chk_bandeja.setChecked(self.settings.value("minimizar_bandeja", True, type=bool))
        self.chk_bandeja.toggled.connect(lambda v: self.settings.setValue("minimizar_bandeja", v))
        opts.addWidget(self.chk_tema)
        opts.addWidget(self.chk_auto)
        opts.addWidget(self.chk_bandeja)
        opts.addStretch()
        raiz.addLayout(opts)

        self.abas = QTabWidget()
        self.abas.currentChanged.connect(self._ao_mudar_aba)
        self.aba_resumo = QWidget()
        self.aba_cpu = QWidget()
        self.aba_mem = QWidget()
        self.aba_gpu = QWidget()
        self.aba_disco = QWidget()
        self.aba_rede = QWidget()
        self.aba_sens = QWidget()
        self.aba_sis = QWidget()
        self.aba_bench = QWidget()
        for nome, aba in (
            ("Resumo", self.aba_resumo), ("CPU", self.aba_cpu), ("Memória", self.aba_mem),
            ("GPU", self.aba_gpu), ("Discos", self.aba_disco), ("Rede", self.aba_rede),
            ("Sensores", self.aba_sens), ("Sistema", self.aba_sis), ("Benchmark", self.aba_bench),
        ):
            self.abas.addTab(aba, nome)
        raiz.addWidget(self.abas, stretch=1)

        self.form_resumo = self._criar_form(self.aba_resumo)
        self.form_cpu = self._criar_form(self.aba_cpu)
        self.form_sis = self._criar_form(self.aba_sis)

        lay_bench = QVBoxLayout(self.aba_bench)
        lay_bench.setContentsMargins(12, 12, 12, 12)
        self.lbl_bench_info = QLabel(
            "Benchmark sintético (single/multi core, memória, disco). "
            "Escala calibrada p/ Ryzen 5 5500 (~3000 single / ~14000 multi). Compare no mesmo PC."
        )
        self.lbl_bench_info.setWordWrap(True)
        self.lbl_bench_info.setStyleSheet("color: #aaa; padding-bottom: 6px;")
        self.painel_bench = PainelBenchmarkCpuZ()
        self.btn_executar_bench = QPushButton("Executar benchmark novamente")
        self.btn_executar_bench.clicked.connect(self._rodar_benchmark)
        lay_bench.addWidget(self.lbl_bench_info)
        lay_bench.addWidget(self.painel_bench)
        lay_bench.addWidget(self.btn_executar_bench)
        lay_bench.addStretch()

        lay_mem = QVBoxLayout(self.aba_mem)
        self.widget_dual = WidgetDualChannel()
        self.lbl_dual = QLabel()
        self.lbl_dual.setWordWrap(True)
        self.tabela_ram = self._criar_tabela(
            ["Slot", "Canal", "Tamanho", "Tipo", "MHz", "Fabricante", "Part Number"],
        )
        lay_mem.addWidget(self.widget_dual)
        lay_mem.addWidget(self.lbl_dual)
        lay_mem.addWidget(self.tabela_ram)

        self.tabela_gpu = self._criar_tabela(["GPU", "Driver", "VRAM", "PCI"])
        QVBoxLayout(self.aba_gpu).addWidget(self.tabela_gpu)
        self.tabela_disco = self._criar_tabela(["Dispositivo", "Tamanho", "Modelo", "Bus", "Tipo", "SMART"])
        QVBoxLayout(self.aba_disco).addWidget(self.tabela_disco)
        self.tabela_rede = self._criar_tabela(["Interface", "IPv4", "MAC", "Link", "Ativa"])
        QVBoxLayout(self.aba_rede).addWidget(self.tabela_rede)
        lay_sens = QVBoxLayout(self.aba_sens)
        self.lbl_sens_tempo = QLabel("Atualização automática a cada 1,5 s enquanto esta aba estiver aberta.")
        self.lbl_sens_tempo.setStyleSheet("color: #888; padding: 4px 2px;")
        self.tabela_sens = self._criar_tabela(["Sensor", "Valor"])
        lay_sens.addWidget(self.lbl_sens_tempo)
        lay_sens.addWidget(self.tabela_sens)

    def _criar_form(self, aba: QWidget) -> QFormLayout:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(14, 10, 14, 10)
        form.setSpacing(8)
        scroll.setWidget(w)
        QVBoxLayout(aba).addWidget(scroll)
        return form

    def _criar_tabela(self, colunas: list[str]) -> QTableWidget:
        t = QTableWidget(0, len(colunas))
        t.setHorizontalHeaderLabels(colunas)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.setAlternatingRowColors(True)
        return t

    def _preencher_form(self, form: QFormLayout, pares: dict):
        while form.rowCount():
            form.removeRow(0)
        for k, v in pares.items():
            if v is None or v == "":
                continue
            rotulo = QLabel(k)
            rotulo.setObjectName("form_rotulo")
            valor = QLabel(str(v))
            valor.setObjectName("form_valor")
            valor.setWordWrap(True)
            valor.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            form.addRow(rotulo, valor)

    def _preencher_tabela(self, tabela: QTableWidget, linhas: list[list]):
        tabela.setRowCount(0)
        for vals in linhas:
            r = tabela.rowCount()
            tabela.insertRow(r)
            for c, v in enumerate(vals):
                tabela.setItem(r, c, QTableWidgetItem(str(v)))

    def _atualizar_tabela_sensores(self, sensores: list[dict]):
        """Atualiza valores sem reconstruir a tabela (tempo real)."""
        t = self.tabela_sens
        for r, s in enumerate(sensores):
            if r >= t.rowCount():
                t.insertRow(r)
            nome = str(s.get("nome", ""))
            valor = str(s.get("valor", ""))
            item_nome = t.item(r, 0)
            if item_nome is None:
                t.setItem(r, 0, QTableWidgetItem(nome))
            elif item_nome.text() != nome:
                item_nome.setText(nome)
            item_val = t.item(r, 1)
            if item_val is None:
                t.setItem(r, 1, QTableWidgetItem(valor))
            elif item_val.text() != valor:
                item_val.setText(valor)
        while t.rowCount() > len(sensores):
            t.removeRow(t.rowCount() - 1)

    def _tick_sensores(self):
        if not self.isVisible():
            return
        sensores = coletar_sensores()
        if self._dados is not None:
            self._dados.sensores = sensores
        self._atualizar_tabela_sensores(sensores)

    def _gerir_timer_sensores(self, activo: bool):
        if activo and self.isVisible():
            self._tick_sensores()
            self._timer_sensores.start()
        else:
            self._timer_sensores.stop()

    def _aplicar_tema(self, escuro: bool):
        self.setStyleSheet(ESTILO_ESCURO if escuro else ESTILO_CLARO)

    def _toggle_tema(self, escuro: bool):
        self.settings.setValue("tema_escuro", escuro)
        self._aplicar_tema(escuro)

    def _aplicar_dados(self, dados: DadosHardware):
        self._dados = dados
        modelo = dados.cpu.get("Modelo") or dados.cpu.get("Version", "—")
        total = total_ram_texto(dados.modulos_ram, dados.memoria_array)
        self.card_cpu.definir(modelo)
        self.card_ram.definir(total or "SMBIOS?")
        self.card_canal.definir(dados.dual_channel)
        self.card_gpu.definir(gpu_resumo_texto(dados.gpu_detalhe))
        self.card_placa.definir(dados.placa.get("Modelo", "—"))

        if dados.erro_smbios:
            self.lbl_aviso.setText(dados.erro_smbios)
            self.lbl_aviso.show()
        else:
            self.lbl_aviso.hide()

        # Memoria: detalhe sem repetir o titulo do cartao "DUAL CH."
        linhas_mem = []
        if dados.dual_channel_detalhe:
            linhas_mem.append(dados.dual_channel_detalhe)
        if dados.validacao_ram:
            linhas_mem.append(dados.validacao_ram)
        self.lbl_dual.setText("<br>".join(linhas_mem) if linhas_mem else "")
        if linhas_mem:
            self.lbl_dual.setStyleSheet("color: #ccc; padding: 6px 4px;")
            self.lbl_dual.show()
        else:
            self.lbl_dual.hide()
        self.widget_dual.atualizar(dados.modulos_ram)

        # Resumo: sem linha "Dual channel" (ja esta no cartao verde)
        self._preencher_form(self.form_resumo, {
            "Processador": modelo,
            "Núcleos / Threads": f"{dados.cpu.get('Nucleos', '?')} / {dados.cpu.get('Threads', '?')}",
            "Placa de vídeo": gpu_resumo_texto(dados.gpu_detalhe),
            "Memória instalada": total or "—",
            "Detalhe memória": dados.dual_channel_detalhe or "—",
            "Capacidade máx. placa": dados.memoria_array.get("uso_maximo", "—"),
            "Placa-mãe": f"{dados.placa.get('Fabricante', '')} {dados.placa.get('Modelo', '')}".strip(),
            "BIOS": f"{dados.bios.get('Versao', '')} ({dados.bios.get('Data', '')})".strip(" ()"),
        })
        self._preencher_form(self.form_cpu, dados.cpu)
        self._preencher_benchmark(dados.benchmark)

        ram_rows = []
        for m in dados.modulos_ram:
            if m.preenchido or "no module" not in m.tamanho.lower():
                ram_rows.append([m.slot, m.canal or "—", m.tamanho, m.tipo, m.velocidade, m.fabricante, m.part_number])
        self._preencher_tabela(self.tabela_ram, ram_rows)

        gpu_rows = [[g.get("nome", ""), g.get("driver", ""), g.get("vram", ""), g.get("pci", "")] for g in dados.gpu_detalhe]
        self._preencher_tabela(self.tabela_gpu, gpu_rows or [[g.get("linha", "")] for g in dados.gpus])

        self._preencher_tabela(self.tabela_disco, [
            [d.get("nome"), d.get("tamanho"), d.get("modelo"), d.get("bus"), d.get("rotacao"), d.get("smart", "—")]
            for d in dados.discos
        ])
        self._preencher_tabela(self.tabela_rede, [
            [r.get("interface"), r.get("ipv4"), r.get("mac"), r.get("link"), r.get("up")] for r in dados.rede
        ])
        self._atualizar_tabela_sensores(dados.sensores)
        if self.abas.currentIndex() == self._idx_aba_sensores:
            self._gerir_timer_sensores(True)

        sis = {}
        sis.update({f"Sistema — {k}": v for k, v in dados.sistema.items()})
        sis.update({f"Placa — {k}": v for k, v in dados.placa.items()})
        sis.update({f"BIOS — {k}": v for k, v in dados.bios.items()})
        for i, s in enumerate(dados.pcie[:8], 1):
            sis[f"PCIe {i}"] = f"{s.get('slot')} ({s.get('uso')})"
        self._preencher_form(self.form_sis, sis)

    def _preencher_benchmark(self, benchmark: dict):
        if benchmark and ("_meta" in benchmark or benchmark.get("cpu_single_pontos")):
            self.painel_bench.atualizar(benchmark)
            self.lbl_bench_info.setText(
                "Concluído. Compare single vs multi e execute de novo após mudar RAM/clock."
            )
        else:
            self.lbl_bench_info.setText(
                "Sem resultados. A executar benchmark… ou clique no botao abaixo."
            )

    def _ao_mudar_aba(self, indice: int):
        self.settings.setValue("ultima_aba", indice)
        self._gerir_timer_sensores(indice == self._idx_aba_sensores)
        if indice == self._idx_aba_benchmark:
            if not (self._dados and self._dados.benchmark):
                self._rodar_benchmark()
            else:
                self._preencher_benchmark(self._dados.benchmark)

    def _iniciar_benchmark(self):
        """Abre a aba Benchmark e corre o teste com animacao."""
        self.abas.setCurrentIndex(self._idx_aba_benchmark)
        self._rodar_benchmark()

    def _rodar_benchmark(self):
        if self._worker_bench and self._worker_bench.isRunning():
            return
        self.lbl_bench_info.setText(
            "Teste em curso — single-core, multi-core, memoria e disco (~10–25 s)."
        )
        self.lbl_bench_info.setStyleSheet("color: #e0af68; font-weight: bold; padding-bottom: 6px;")
        self.painel_bench.iniciar_teste()
        self.btn_executar_bench.setEnabled(False)
        self.btn_executar_bench.setText("A testar… aguarde")
        self._worker_bench = WorkerBenchmark()
        self._worker_bench.progresso.connect(self._ao_benchmark_progresso)
        self._worker_bench.pronto.connect(self._ao_benchmark_pronto)
        self._worker_bench.finished.connect(self._ao_benchmark_terminado)
        self._worker_bench.start()

    def _ao_benchmark_progresso(self, mensagem: str, percentual: int):
        self.painel_bench.atualizar_progresso(mensagem, percentual)

    def _ao_benchmark_pronto(self, resultados: dict):
        if self._dados is None:
            self._dados = DadosHardware()
        self._dados.benchmark = resultados
        self._preencher_benchmark(resultados)

    def _ao_benchmark_terminado(self):
        self.btn_executar_bench.setEnabled(True)
        self.btn_executar_bench.setText("Executar benchmark novamente")
        self.lbl_bench_info.setStyleSheet("color: #aaa; padding-bottom: 6px;")

    def atualizar(self, smbios: bool, benchmark: bool = False):
        if self._worker and self._worker.isRunning():
            return
        self.lbl_aviso.setText("A recolher dados...")
        self.lbl_aviso.show()
        self._worker = WorkerColeta(smbios, benchmark)
        self._worker.pronto.connect(self._ao_coletar)
        self._worker.start()

    def _ao_coletar(self, dados: DadosHardware):
        self._aplicar_dados(dados)
        self.lbl_aviso.hide()

    def _copiar(self):
        if not self._dados:
            QMessageBox.information(self, "Agildo Specs", "Atualize os dados primeiro.")
            return
        QGuiApplication.clipboard().setText(para_texto(self._dados))
        self.lbl_aviso.setText("Relatório copiado para a área de transferência.")
        self.lbl_aviso.show()

    def _exportar_json(self):
        if not self._dados:
            return
        caminho, _ = QFileDialog.getSaveFileName(self, "Guardar JSON", "agildo-specs.json", "JSON (*.json)")
        if caminho:
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(para_json(self._dados))
            QMessageBox.information(self, "Agildo Specs", f"Guardado: {caminho}")

    def _comparar(self):
        if not self._dados:
            return
        caminho, _ = QFileDialog.getOpenFileName(self, "Abrir relatorio JSON", "", "JSON (*.json)")
        if not caminho:
            return
        with open(caminho, encoding="utf-8") as f:
            outro = json.load(f)
        QMessageBox.information(self, "Comparar", comparar(self._dados, outro))

    def showEvent(self, event):
        super().showEvent(event)
        if self.abas.currentIndex() == self._idx_aba_sensores:
            self._gerir_timer_sensores(True)

    def hideEvent(self, event):
        self._timer_sensores.stop()
        super().hideEvent(event)

    def closeEvent(self, event):
        self._timer_sensores.stop()
        if self.settings.value("minimizar_bandeja", True, type=bool):
            app = QApplication.instance()
            if hasattr(app, "esconder_na_bandeja"):
                app.esconder_na_bandeja()
                event.ignore()
                return
        self.settings.setValue("ultima_aba", self.abas.currentIndex())
        super().closeEvent(event)
