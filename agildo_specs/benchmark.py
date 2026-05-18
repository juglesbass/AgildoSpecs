"""Benchmark estilo CPU-Z: single/multi core, memoria e disco."""
from __future__ import annotations

import os
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

# Calibrado para Ryzen 5 5500 (6C/12T): ~3000 single / ~14000 multi (escala CPU-Z)
_REF_TEMPO_SINGLE = 3.68
_REF_PONTOS_SINGLE = 3000
_REF_TEMPO_MULTI = 1.15
_REF_PONTOS_MULTI = 14000

_ITER_SINGLE = 10_000_000
# Por processo no multi (ProcessPool — sem GIL entre processos)
_ITER_POR_PROCESSO = 2_000_000


def _carga_cpu(iteracoes: int) -> int:
    """Carga mista inteiro/bit — parecida com testes sinteticos de CPU."""
    x = 123456789
    for i in range(iteracoes):
        x = (x * 1103515245 + 12345) & 0x7FFFFFFF
        x ^= (x << 13) & 0x7FFFFFFF
        x ^= (x >> 17) & 0x7FFFFFFF
        x ^= (x << 5) & 0x7FFFFFFF
        x += i & 255
    return x


def _pontos(tempo: float, ref_tempo: float, ref_pontos: int) -> int:
    if tempo <= 0:
        return 0
    return max(1, int(ref_pontos * (ref_tempo / tempo)))


def _bench_cpu_single() -> tuple[float, int]:
    t0 = time.perf_counter()
    _carga_cpu(_ITER_SINGLE)
    tempo = time.perf_counter() - t0
    return tempo, _pontos(tempo, _REF_TEMPO_SINGLE, _REF_PONTOS_SINGLE)


def _bench_cpu_multi() -> tuple[float, int]:
    """Multi-core com processos (threads Python nao paralelizam CPU por causa do GIL)."""
    nucleos = os.cpu_count() or 4
    cargas = [_ITER_POR_PROCESSO] * nucleos
    t0 = time.perf_counter()
    # fork no Linux: seguro a partir de worker Qt; spawn no Windows exigiria guard no main
    with ProcessPoolExecutor(max_workers=nucleos) as pool:
        list(pool.map(_carga_cpu, cargas, chunksize=1))
    tempo = time.perf_counter() - t0
    return tempo, _pontos(tempo, _REF_TEMPO_MULTI, _REF_PONTOS_MULTI)


def _bench_memoria() -> tuple[float, float]:
    """Latencia media (ns) e largura de banda (MB/s) em copia de 64 MB."""
    tamanho = 64 * 1024 * 1024
    try:
        origem = bytearray(tamanho)
        destino = bytearray(tamanho)
        # Largura de banda
        t0 = time.perf_counter()
        destino[:] = origem[:]
        tempo_bw = time.perf_counter() - t0
        mb_s = (tamanho * 2) / (1024 * 1024) / tempo_bw if tempo_bw > 0 else 0

        # Latencia por acesso em saltos de cache
        saltos = 512_000
        t0 = time.perf_counter()
        acc = 0
        passo = 64
        pos = 0
        for _ in range(saltos):
            acc += origem[pos]
            pos = (pos + passo) % tamanho
        tempo_lat = time.perf_counter() - t0
        ns = (tempo_lat / saltos) * 1e9
        return ns, mb_s
    except MemoryError:
        return 0.0, 0.0


def _bench_disco() -> tuple[float, float]:
    """Tempo total (s) e MB/s na escrita de 64 MB."""
    mb = 64
    try:
        bloco = os.urandom(1024 * 1024)
        with tempfile.NamedTemporaryFile(delete=True) as tmp:
            t0 = time.perf_counter()
            for _ in range(mb):
                tmp.write(bloco)
            tmp.flush()
            os.fsync(tmp.fileno())
            tempo = time.perf_counter() - t0
        velocidade = mb / tempo if tempo > 0 else 0
        return tempo, velocidade
    except OSError:
        return 0.0, 0.0


def executar_benchmark(progresso=None) -> dict:
    """Retorna pontuacoes e detalhes (dict plano + chave _meta para a UI).

    progresso(msg, percentual): callback opcional para animacao na interface.
    """
    def _prog(msg: str, pct: int) -> None:
        if progresso:
            progresso(msg, pct)

    _prog("A preparar teste…", 2)
    _prog("Single-core — a calcular…", 8)
    t_single, pts_single = _bench_cpu_single()
    _prog("Multi-core — a usar todos os nucleos…", 38)
    t_multi, pts_multi = _bench_cpu_multi()
    _prog("Memoria — latencia e banda…", 62)
    lat_ns, bw_mb = _bench_memoria()
    _prog("Disco — escrita temporaria…", 82)
    t_disco, disco_mb_s = _bench_disco()
    _prog("A finalizar…", 98)

    nucleos = os.cpu_count() or 1
    resultado = {
        "cpu_single_pontos": str(pts_single),
        "cpu_single_tempo": f"{t_single:.3f} s",
        "cpu_multi_pontos": str(pts_multi),
        "cpu_multi_tempo": f"{t_multi:.3f} s",
        "cpu_nucleos": str(nucleos),
        "mem_latencia": f"{lat_ns:.1f} ns" if lat_ns else "—",
        "mem_largura_banda": f"{bw_mb:.0f} MB/s" if bw_mb else "—",
        "disco_escrita": f"{disco_mb_s:.0f} MB/s" if disco_mb_s else "—",
        "disco_tempo": f"{t_disco:.2f} s" if t_disco else "—",
        "_meta": {
            "single": pts_single,
            "multi": pts_multi,
            "nucleos": nucleos,
            "mem_lat_ns": lat_ns,
            "mem_bw": bw_mb,
            "disco_mbs": disco_mb_s,
        },
    }
    return resultado
