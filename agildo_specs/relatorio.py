"""Exportar e comparar relatorios."""
from __future__ import annotations

import json
from datetime import datetime

from agildo_specs.coletor import DadosHardware


def _formatar_gpu(g: dict) -> str:
    partes = [g.get("nome", "")]
    if g.get("driver") and g.get("driver") != "—":
        partes.append(f"driver {g['driver']}")
    if g.get("vram") and g.get("vram") != "—":
        partes.append(g["vram"])
    if g.get("pci") and g.get("pci") != "—":
        partes.append(g["pci"])
    return " | ".join(p for p in partes if p)


def para_texto(dados: DadosHardware) -> str:
    linhas = [
        f"=== Agildo Specs === {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "[ CPU ]",
    ]
    for k, v in dados.cpu.items():
        linhas.append(f"  {k}: {v}")
    linhas += ["", "[ RAM / Dual channel ]", f"  {dados.dual_channel}", f"  {dados.dual_channel_detalhe}"]
    if dados.validacao_ram:
        linhas.append(f"  {dados.validacao_ram}")
    for m in dados.modulos_ram:
        if m.preenchido:
            linhas.append(f"  - {m.slot}: {m.tamanho} {m.velocidade} {m.canal}")
    linhas += ["", "[ Placa / BIOS ]"]
    for k, v in {**dados.placa, **dados.bios}.items():
        linhas.append(f"  {k}: {v}")
    if dados.gpu_detalhe:
        linhas += ["", "[ GPU ]"]
        for g in dados.gpu_detalhe:
            linhas.append(f"  {_formatar_gpu(g)}")
    if dados.discos:
        linhas += ["", "[ Discos ]"]
        for d in dados.discos:
            linhas.append(
                f"  {d.get('nome')} {d.get('tamanho')} {d.get('modelo')} "
                f"({d.get('bus')}) SMART={d.get('smart', '—')}"
            )
    if dados.rede:
        linhas += ["", "[ Rede ]"]
        for r in dados.rede:
            linhas.append(
                f"  {r.get('interface')}: {r.get('ipv4') or '—'} "
                f"MAC {r.get('mac')} {r.get('link')} ativa={r.get('up')}"
            )
    if dados.sensores:
        linhas += ["", "[ Sensores ]"]
        for s in dados.sensores[:15]:
            linhas.append(f"  {s.get('nome')}: {s.get('valor')}")
    if dados.benchmark:
        linhas += ["", "[ Benchmark estilo CPU-Z ]"]
        b = dados.benchmark
        meta = b.get("_meta") or {}
        if meta:
            linhas.append(f"  Single-Core: {meta.get('single', b.get('cpu_single_pontos'))} pts")
            linhas.append(f"  Multi-Core: {meta.get('multi', b.get('cpu_multi_pontos'))} pts")
        for k, v in b.items():
            if not k.startswith("_"):
                linhas.append(f"  {k}: {v}")
    return "\n".join(linhas)


def para_json(dados: DadosHardware) -> str:
    payload = dados.para_dict()
    payload["_exportado_em"] = datetime.now().isoformat()
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _diff_dict(caminho: str, a: dict, b: dict) -> list[str]:
    diffs = []
    for k in set(a) | set(b if isinstance(b, dict) else {}):
        va = a.get(k)
        vb = b.get(k) if isinstance(b, dict) else None
        if va != vb:
            diffs.append(f"{caminho}.{k}: '{vb}' -> '{va}'")
    return diffs


def comparar(atual: DadosHardware, outro: dict) -> str:
    diffs = []
    for chave in ("cpu", "placa", "bios", "dual_channel"):
        a = getattr(atual, chave) if hasattr(atual, chave) else {}
        b = outro.get(chave, {})
        if isinstance(a, str):
            if a != b:
                diffs.append(f"{chave}: '{b}' -> '{a}'")
        elif isinstance(a, dict):
            diffs.extend(_diff_dict(chave, a, b if isinstance(b, dict) else {}))

    ram_a = sum(1 for m in atual.modulos_ram if m.preenchido)
    ram_b = sum(
        1 for m in outro.get("modulos_ram", [])
        if (m.get("preenchido") if isinstance(m, dict) else getattr(m, "preenchido", False))
    )
    if ram_a != ram_b:
        diffs.append(f"modulos RAM: {ram_b} -> {ram_a}")

    gpus_a = [_formatar_gpu(g) for g in atual.gpu_detalhe]
    gpus_b = [
        _formatar_gpu(g) if isinstance(g, dict) else str(g)
        for g in outro.get("gpu_detalhe", [])
    ]
    if gpus_a != gpus_b:
        diffs.append(f"GPU: {gpus_b or ['—']} -> {gpus_a or ['—']}")

    discos_a = [d.get("modelo") or d.get("nome") for d in atual.discos]
    discos_b = [
        (d.get("modelo") or d.get("nome")) if isinstance(d, dict) else str(d)
        for d in outro.get("discos", [])
    ]
    if discos_a != discos_b:
        diffs.append(f"discos: {discos_b} -> {discos_a}")

    bench_a = atual.benchmark.get("_meta") or {}
    bench_b = (outro.get("benchmark") or {}).get("_meta") or {}
    if bench_a or bench_b:
        for campo in ("single", "multi"):
            va, vb = bench_a.get(campo), bench_b.get(campo)
            if va != vb and (va or vb):
                diffs.append(f"benchmark.{campo}: {vb} -> {va} pts")

    if not diffs:
        return "Nenhuma diferença relevante entre os dois relatórios."
    return "Diferenças encontradas:\n" + "\n".join(f"  • {d}" for d in diffs)
