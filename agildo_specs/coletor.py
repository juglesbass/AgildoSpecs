"""Coleta de dados de hardware (SMBIOS, sysfs, ferramentas CLI)."""
from __future__ import annotations

import glob
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field, asdict

try:
    import psutil
except ImportError:
    psutil = None


@dataclass
class ModuloRam:
    slot: str = ""
    banco: str = ""
    tamanho: str = ""
    tipo: str = ""
    velocidade: str = ""
    fabricante: str = ""
    part_number: str = ""
    canal: str = ""
    preenchido: bool = False
    rank: str = ""
    voltagem: str = ""


@dataclass
class DadosHardware:
    cpu: dict = field(default_factory=dict)
    sistema: dict = field(default_factory=dict)
    placa: dict = field(default_factory=dict)
    bios: dict = field(default_factory=dict)
    modulos_ram: list = field(default_factory=list)
    memoria_array: dict = field(default_factory=dict)
    dual_channel: str = "Indeterminado"
    dual_channel_detalhe: str = ""
    validacao_ram: str = ""
    gpus: list = field(default_factory=list)
    gpu_detalhe: list = field(default_factory=list)
    discos: list = field(default_factory=list)
    rede: list = field(default_factory=list)
    sensores: list = field(default_factory=list)
    pcie: list = field(default_factory=list)
    benchmark: dict = field(default_factory=dict)
    erro_smbios: str = ""

    def para_dict(self) -> dict:
        d = asdict(self)
        return d


_CAMPOS_DMI = {
    "size": ("Size", "Tamanho"),
    "locator": ("Locator", "Localizador"),
    "bank": ("Bank Locator", "Localizador de banco", "Banco"),
    "type": ("Type", "Tipo"),
    "speed": ("Speed", "Velocidade"),
    "configured_speed": (
        "Configured Memory Speed",
        "Velocidade de memoria configurada",
        "Velocidade configurada da memória",
    ),
    "manufacturer": ("Manufacturer", "Fabricante"),
    "part": ("Part Number", "Numero da peca", "Número de peça"),
    "max_capacity": ("Maximum Capacity", "Capacidade maxima", "Capacidade máxima"),
    "devices": ("Number Of Devices", "Numero de dispositivos", "Número de dispositivos"),
    "range_size": ("Range Size", "Tamanho do intervalo"),
    "partition_width": ("Partition Width", "Largura da particao", "Largura da partição"),
    "rank": ("Rank", "Classificacao", "Classificação"),
    "voltage": ("Configured Voltage", "Minimum Voltage", "Voltage"),
}


def _executar(cmd: list[str], timeout: int = 45) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, errors="replace",
        )
        return proc.returncode, proc.stdout, proc.stderr
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return -1, "", str(e)


def _ler_sysfs_dmi(campo: str) -> str:
    try:
        with open(f"/sys/devices/virtual/dmi/id/{campo}", encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _ler_arquivo(caminho: str) -> str:
    try:
        with open(caminho, encoding="utf-8", errors="replace") as f:
            return f.read().strip()
    except OSError:
        return ""


def _extrair_campo_bloco(bloco: str, *nomes: str) -> str:
    for nome in nomes:
        m = re.search(rf"^\s*{re.escape(nome)}:\s*(.*)$", bloco, re.MULTILINE | re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


def _campo(bloco: str, chave: str) -> str:
    return _extrair_campo_bloco(bloco, *_CAMPOS_DMI[chave])


def _canal_de_texto(*textos: str) -> str:
    junto = " ".join(t for t in textos if t).upper()
    if not junto:
        return ""
    for padrao, rotulo in (
        (r"P0\s+CHANNEL\s+([AB])\b", "Canal {}"),
        (r"\bCHANNEL\s+([AB])\b", "Canal {}"),
        (r"CHANNEL\s*([AB])\b", "Canal {}"),
    ):
        m = re.search(padrao, junto)
        if m:
            return rotulo.format(m.group(1))
    if re.search(r"\bCHANNEL\s*0\b", junto):
        return "Canal 0"
    if re.search(r"\bCHANNEL\s*1\b", junto):
        return "Canal 1"
    return ""


def _modulo_preenchido(tamanho: str, bloco: str = "") -> bool:
    t = tamanho.lower()
    if t and ("no module" in t or ("nenhum" in t and "modul" in t)):
        return False
    if re.search(r"\d+\s*(mb|gb|tb|gib|mib)", t, re.I):
        return True
    if bloco:
        fab = _campo(bloco, "manufacturer").lower()
        parte = _campo(bloco, "part").lower()
        if fab and fab not in ("unknown", "desconhecido", "not specified", "to be filled"):
            return True
        if parte and parte not in ("unknown", "desconhecido", "not specified", "--", "n/a"):
            return True
    return False


def _parse_lscpu() -> dict:
    cod, saida, _ = _executar(["lscpu"])
    if cod != 0:
        return {}
    dados = {}
    for linha in saida.splitlines():
        if ":" in linha:
            c, v = linha.split(":", 1)
            dados[c.strip()] = v.strip()
    return dados


def _parse_cpu_extra() -> dict:
    extra: dict[str, str] = {}
    flags_path = "/proc/cpuinfo"
    try:
        with open(flags_path, encoding="utf-8", errors="replace") as f:
            for linha in f:
                if linha.lower().startswith("flags"):
                    flags = linha.split(":", 1)[-1].upper()
                    for nome in ("AVX", "AVX2", "AVX512F", "SSE4_2", "AES"):
                        extra[f"Instrucao {nome}"] = "Sim" if nome in flags else "Nao"
                    break
    except OSError:
        pass
    if os.path.isdir("/sys/devices/system/cpu/cpu0/cache"):
        for idx in sorted(glob.glob("/sys/devices/system/cpu/cpu0/cache/index*")):
            nivel = _ler_arquivo(os.path.join(idx, "level"))
            tamanho = _ler_arquivo(os.path.join(idx, "size"))
            if nivel and tamanho:
                extra[f"Cache L{nivel}"] = tamanho
    for i in range(os.cpu_count() or 0):
        freq = _ler_arquivo(f"/sys/devices/system/cpu/cpu{i}/cpufreq/scaling_cur_freq")
        if freq.isdigit():
            extra[f"CPU{i} MHz"] = f"{int(freq) / 1000:.0f}"
            if i >= 3:
                extra["..."] = f"+ {max(0, (os.cpu_count() or 0) - 3)} nucleos"
                break
    return extra


def _parse_dmidecode_memoria(texto: str) -> tuple[list[ModuloRam], dict]:
    modulos: list[ModuloRam] = []
    array_info: dict[str, str] = {}
    m = re.search(r"Physical Memory Array\n(.*?)(?=\nHandle|\Z)", texto, re.DOTALL | re.I)
    if m:
        bloco = m.group(1)
        array_info["uso_maximo"] = _campo(bloco, "max_capacity")
        array_info["dispositivos"] = _campo(bloco, "devices")
    for m in re.finditer(r"Memory Array Mapped Address\n(.*?)(?=\nHandle|\Z)", texto, re.DOTALL | re.I):
        bloco = m.group(1)
        rs, pw = _campo(bloco, "range_size"), _campo(bloco, "partition_width")
        if rs:
            array_info["range_size"] = rs
        if pw and pw.lower() not in ("unknown", "desconhecido"):
            array_info["partition_width"] = pw
    for m in re.finditer(
        r"(?:Memory Device|Dispositivo de [Mm]em[oó]ria)\n(.*?)(?=\nHandle|\Z)", texto, re.DOTALL,
    ):
        bloco = m.group(1)
        locator, banco = _campo(bloco, "locator"), _campo(bloco, "bank")
        canal = _canal_de_texto(locator, banco)
        slot = f"{locator} — {banco}" if locator and banco else (locator or banco or f"Slot {len(modulos)+1}")
        modulos.append(
            ModuloRam(
                slot=slot,
                banco=banco,
                tamanho=_campo(bloco, "size"),
                tipo=_campo(bloco, "type"),
                velocidade=_campo(bloco, "configured_speed") or _campo(bloco, "speed"),
                fabricante=_campo(bloco, "manufacturer"),
                part_number=_campo(bloco, "part"),
                canal=canal,
                rank=_campo(bloco, "rank"),
                voltagem=_campo(bloco, "voltage"),
                preenchido=_modulo_preenchido(_campo(bloco, "size"), bloco),
            )
        )
    return modulos, array_info


def _parse_dmidecode_processador(texto: str) -> dict:
    cpu = {}
    m = re.search(r"Processor Information\n(.*?)(?=\nHandle|\n\n[A-Z]|\Z)", texto, re.DOTALL)
    if not m:
        return cpu
    bloco = m.group(1)
    for campo in (
        "Socket Designation", "Manufacturer", "Version", "Family", "Signature",
        "Max Speed", "Current Speed", "Core Count", "Thread Count", "Voltage", "External Clock",
    ):
        v = _extrair_campo_bloco(bloco, campo)
        if v:
            cpu[campo] = v
    return cpu


def _parse_dmidecode_pcie(texto: str) -> list[dict]:
    slots = []
    for m in re.finditer(r"System Slot Information\n(.*?)(?=\nHandle|\Z)", texto, re.DOTALL):
        bloco = m.group(1)
        des = _extrair_campo_bloco(bloco, "Designation")
        tipo = _extrair_campo_bloco(bloco, "Type")
        uso = _extrair_campo_bloco(bloco, "Current Usage")
        if des:
            slots.append({"slot": des, "tipo": tipo, "uso": uso})
    return slots[:20]


def _inferir_dual_channel(modulos: list[ModuloRam], array_info: dict | None = None) -> tuple[str, str]:
    array_info = array_info or {}
    ativos = [m for m in modulos if m.preenchido]
    pw = array_info.get("partition_width", "")
    if pw.isdigit() and int(pw) >= 2:
        return "Dual channel (SMBIOS)", f"Partition Width = {pw}."
    if not ativos:
        return "Indeterminado", "Use Ler SMBIOS (root) para modulos RAM."
    if len(ativos) == 1:
        return "Single channel (provavel)", "Apenas 1 modulo instalado."
    canais = {m.canal for m in ativos if m.canal}
    if len(canais) >= 2:
        return "Dual channel (SMBIOS)", f"Canais: {', '.join(sorted(canais))}."
    letras = set()
    for m in ativos:
        t = f"{m.slot} {m.banco}".upper()
        if re.search(r"CHANNEL\s+A|P0\s+CHANNEL\s+A", t):
            letras.add("A")
        if re.search(r"CHANNEL\s+B|P0\s+CHANNEL\s+B", t):
            letras.add("B")
    if len(letras) >= 2:
        return "Dual channel (SMBIOS)", "Canais A e B ocupados."
    if len(ativos) >= 2:
        return "Provavel dual channel", f"{len(ativos)} modulos — confira slots A2+B2 no manual."
    return "Indeterminado", ""


def _validar_slots_ram(modulos: list[ModuloRam], modelo_placa: str) -> str:
    ativos = [m for m in modulos if m.preenchido]
    if len(ativos) < 2:
        return ""
    canais = set()
    for m in ativos:
        t = f"{m.banco} {m.canal}".upper()
        if "CHANNEL A" in t or "CANAL A" in t or re.search(r"\bA\b", m.canal or ""):
            canais.add("A")
        if "CHANNEL B" in t or "CANAL B" in t or re.search(r"\bB\b", m.canal or ""):
            canais.add("B")
    if len(canais) == 1 and len(ativos) >= 2:
        return (
            "Atencao: os modulos parecem estar no mesmo canal. "
            "Para dual channel, use normalmente DIMM A2 + DIMM B2 (ver manual da placa)."
        )
    if "A520" in modelo_placa.upper() and len(ativos) == 2:
        return "A520: 2 pentes em canais A e B — configuracao tipica correta para dual channel."
    return ""


def _ler_dmidecode_com_privilegio() -> tuple[str, str]:
    cod, saida, err = _executar(["dmidecode"])
    if cod == 0 and saida.strip():
        return saida, ""
    for elevador in (
        ["pkexec", "dmidecode"] if shutil.which("pkexec") else None,
        ["kdesu", "-c", "dmidecode"] if shutil.which("kdesu") else None,
        ["sudo", "-n", "dmidecode"] if shutil.which("sudo") else None,
    ):
        if elevador:
            cod, saida, err = _executar(elevador)
            if cod == 0 and saida.strip():
                return saida, ""
    return "", err.strip() or "dmidecode requer privilegios (pkexec)."


# iGPU AMD (APU) — preferir placa dedicada na lista
_IGPU_HINTS = (
    "raphael", "cezanne", "rembrandt", "picasso", "renoir", "barcelo",
    "lucienne", "mendocino", "phoenix", "hawk point", "vega ", "granville",
)


def _extrair_nome_gpu_lspci(linha: str) -> str:
    """Extrai nome comercial (ex.: Radeon RX 6600) da linha do lspci."""
    m = re.search(
        r"\[((?:Radeon|GeForce|RTX|GTX|Arc|Quadro|Tesla|Intel)[^\]]+)\]",
        linha,
        re.I,
    )
    if m:
        return m.group(1).split("/")[0].strip()

    if ":" not in linha:
        return linha.strip()
    desc = linha.split(":", 1)[-1].strip()
    desc = re.sub(r"\s*\[[0-9a-f]{4}:[0-9a-f]{4}\].*$", "", desc, flags=re.I)
    desc = re.sub(r"\s*\(rev [^)]+\)\s*", "", desc, flags=re.I)
    desc = re.sub(
        r"^(VGA compatible controller|Display controller|3D controller)\s*",
        "",
        desc,
        flags=re.I,
    )
    desc = re.sub(r"Advanced Micro Devices, Inc\.\s*\[AMD/ATI\]\s*", "", desc, flags=re.I)
    desc = re.sub(r"NVIDIA Corporation\s*", "", desc, flags=re.I)
    desc = re.sub(r"Intel Corporation\s*", "", desc, flags=re.I)
    # Navi 23 [Radeon RX ...] sem colchetes externos
    m2 = re.search(r"\[([^\]]*Radeon[^\]]*)\]", desc, re.I)
    if m2:
        return m2.group(1).split("/")[0].strip()
    return desc.strip() or linha.strip()


def _prioridade_gpu(nome: str, pci_id: str) -> int:
    """Maior = placa dedicada (mostrar primeiro)."""
    baixo = nome.lower()
    if any(h in baixo for h in _IGPU_HINTS):
        return 10
    if any(x in baixo for x in ("radeon rx", "geforce", "rtx ", "gtx ", "arc a", "quadro")):
        return 100
    if "nvidia" in baixo or "radeon" in baixo:
        return 80
    return 50


def _vram_sysfs_drm(pci_slot: str) -> str:
    """VRAM total via sysfs (amdgpu). pci_slot ex.: 0000:12:00.0"""
    slot = pci_slot.replace(":", r"\:").replace(".", r"\.")
    for pasta in glob.glob("/sys/bus/pci/devices/*"):
        uevent = os.path.join(pasta, "uevent")
        if not os.path.isfile(uevent):
            continue
        try:
            with open(uevent, encoding="utf-8", errors="replace") as f:
                txt = f.read()
            if pci_slot not in txt and slot not in txt:
                continue
            for nome_arq in ("mem_info_vram_total", "mem_info_vis_vram_total"):
                raw = _ler_arquivo(os.path.join(pasta, nome_arq))
                if raw.isdigit():
                    gb = int(raw) / (1024**3)
                    return f"{gb:.0f} GB"
        except OSError:
            continue
    return ""


def _normalizar_slot_pci(pci: str) -> str:
    """Forma canónica 0000:bb:dd.f para cruzar nvidia-smi com lspci."""
    if not pci or pci == "—":
        return ""
    p = pci.strip().lower().replace("00000000:", "0000:")
    if re.match(r"^[0-9a-f]{2}:[0-9a-f]{2}\.[0-9a-f]$", p):
        return f"0000:{p}"
    return p


def _normalizar_chave_gpu(nome: str) -> str:
    """Chave para deduplicar nomes equivalentes (lspci vs glxinfo vs hwinfo)."""
    n = nome.lower().split("(")[0].strip()
    n = re.sub(r"^(amd|nvidia|intel)\s+", "", n)
    n = re.sub(r"\s+", " ", n)
    m = re.search(r"\b((?:rx|rtx|gtx)\s*\d{3,4}[a-z0-9]*)\b", n, re.I)
    if m:
        return re.sub(r"\s+", "", m.group(1).lower())
    m = re.search(r"\b(arc\s*a?\s*\d{3,4}[a-z0-9]*)\b", n, re.I)
    if m:
        return re.sub(r"\s+", "", m.group(1).lower())
    return n


def gpu_resumo_texto(gpu_detalhe: list) -> str:
    """Texto curto da GPU principal para o cartão Resumo."""
    if not gpu_detalhe:
        return "—"
    g = gpu_detalhe[0]
    nome = g.get("nome", "") or "—"
    vram = g.get("vram", "")
    if vram and vram != "—":
        return f"{nome} · {vram}"
    return nome


def _gpu_glxinfo() -> str:
    """Nome curto via glxinfo — só fallback quando lspci não encontrou placa."""
    cod, out, _ = _executar(["glxinfo", "-B"], timeout=8)
    if cod != 0:
        return ""
    for ln in out.splitlines():
        if "OpenGL renderer" in ln or "Device:" in ln:
            bruto = ln.split(":", 1)[-1].strip()
            # "AMD Radeon RX 6600 (radeonsi, ...)" -> "Radeon RX 6600"
            curto = bruto.split("(")[0].strip()
            curto = re.sub(r"^AMD\s+", "", curto, flags=re.I)
            curto = re.sub(r"^NVIDIA\s+", "", curto, flags=re.I)
            m = re.search(
                r"\[((?:Radeon|GeForce|RTX|GTX|Arc)[^\]]+)\]",
                bruto,
                re.I,
            )
            if m:
                return m.group(1).split("/")[0].strip()
            return curto or bruto
    return ""


def _gpu_hwinfo() -> list[dict]:
    cod, out, _ = _executar(["hwinfo", "--gfxcard"], timeout=15)
    if cod != 0:
        return []
    placas = []
    bloco_atual: dict = {}
    for ln in out.splitlines():
        if ln.startswith("Graphics Card:"):
            if bloco_atual.get("nome"):
                placas.append(bloco_atual)
            bloco_atual = {}
        elif ":" in ln and bloco_atual is not None:
            ch, val = ln.split(":", 1)
            ch = ch.strip().lower()
            val = val.strip()
            if ch == "model":
                bloco_atual["nome"] = val
            elif ch in ("vendor", "driver"):
                bloco_atual.setdefault("driver", val)
            elif "memory" in ch and "size" in ch:
                bloco_atual["vram"] = val
    if bloco_atual.get("nome"):
        placas.append(bloco_atual)
    return placas


def _nvidia_gpus() -> list[dict]:
    cod, out, _ = _executar(
        ["nvidia-smi", "--query-gpu=pci.bus_id,name,memory.total,driver_version", "--format=csv,noheader"],
    )
    if cod != 0 or not out.strip():
        return []
    lista = []
    for linha in out.strip().splitlines():
        partes = [p.strip() for p in linha.split(",")]
        if len(partes) < 4:
            continue
        pci = _normalizar_slot_pci(partes[0])
        nome, vram, driver = partes[1], partes[2], partes[3]
        lista.append({"nome": nome, "vram": vram, "driver": driver, "pci": pci})
    return lista


def _parse_lspci_gpus() -> tuple[list[dict], list[dict]]:
    simples, detalhe = [], []
    vistos: set[str] = set()
    pci_vistos: set[str] = set()

    # NVIDIA primeiro (nome exacto)
    for ng in _nvidia_gpus():
        chave = _normalizar_chave_gpu(ng["nome"])
        pci_norm = _normalizar_slot_pci(ng.get("pci", ""))
        if chave in vistos or (pci_norm and pci_norm in pci_vistos):
            continue
        vistos.add(chave)
        if pci_norm:
            pci_vistos.add(pci_norm)
        detalhe.append(ng)
        simples.append({"linha": ng["nome"]})

    cod, saida, _ = _executar(["lspci", "-nn"])
    if cod == 0:
        entradas_pci = []
        for linha in saida.splitlines():
            baixo = linha.lower()
            if not any(x in baixo for x in ("vga", "3d", "display")):
                continue
            pci_id = linha.split()[0]
            nome = _extrair_nome_gpu_lspci(linha)
            entradas_pci.append((pci_id, nome, linha.strip()))

        entradas_pci.sort(key=lambda e: _prioridade_gpu(e[1], e[0]), reverse=True)

        for pci_id, nome, linha_completa in entradas_pci:
            chave = _normalizar_chave_gpu(nome)
            pci_norm = _normalizar_slot_pci(pci_id)
            if chave in vistos or (pci_norm and pci_norm in pci_vistos):
                continue
            driver, vram = "", _vram_sysfs_drm(pci_id)
            c2, out, _ = _executar(["lspci", "-v", "-s", pci_id])
            if c2 == 0:
                for ln in out.splitlines():
                    if "Kernel driver in use" in ln or "Kernel driver:" in ln:
                        driver = ln.split(":", 1)[-1].strip()
                    elif "Kernel modules" in ln and not driver:
                        driver = ln.split(":", 1)[-1].strip().split()[0]
            if not vram and c2 == 0:
                m = re.search(r"prefetchable\).*size=([0-9]+[MG])", out.replace("\n", " "), re.I)
                if m:
                    vram = m.group(1)
            detalhe.append({
                "nome": nome,
                "driver": driver or "—",
                "vram": vram or "—",
                "pci": pci_id,
            })
            simples.append({"linha": nome})
            vistos.add(chave)
            if pci_norm:
                pci_vistos.add(pci_norm)

    # hwinfo como reforco se lspci falhou
    if not detalhe:
        for h in _gpu_hwinfo():
            nome = h.get("nome", "")
            chave = _normalizar_chave_gpu(nome)
            if nome and chave not in vistos:
                detalhe.append({
                    "nome": nome,
                    "driver": h.get("driver", "—"),
                    "vram": h.get("vram", "—"),
                    "pci": "—",
                })
                simples.append({"linha": nome})
                vistos.add(chave)

    # glxinfo só se nada foi detectado (evita "Radeon RX 6600 (AMD Radeon RX 6600 ...)")
    if not detalhe:
        glx = _gpu_glxinfo()
        if glx:
            detalhe.append({"nome": glx, "driver": "—", "vram": "—", "pci": "—"})
            simples.append({"linha": glx})

    return simples, detalhe


def _parse_discos() -> list[dict]:
    discos = []
    cod, saida, _ = _executar(["lsblk", "-J", "-o", "NAME,SIZE,TYPE,MODEL,ROTA,TRAN,MOUNTPOINT"])
    if cod == 0:
        try:
            blocos = json.loads(saida).get("blockdevices", [])
            for dev in blocos:
                if dev.get("type") in ("disk", "nvme"):
                    discos.append({
                        "nome": dev.get("name", ""),
                        "tamanho": dev.get("size", ""),
                        "modelo": dev.get("model", "") or "—",
                        "bus": dev.get("tran", "") or "—",
                        "rotacao": "SSD" if dev.get("rota") is False else ("HDD" if dev.get("rota") else "—"),
                    })
        except json.JSONDecodeError:
            pass
    if shutil.which("smartctl"):
        for d in discos[:4]:
            nome = d.get("nome", "")
            if not nome:
                continue
            dev = f"/dev/{nome}"
            c, out, _ = _executar(["smartctl", "-H", dev], timeout=10)
            if c == 0 and "SMART overall-health" in out:
                m = re.search(r"overall-health self-assessment test result:\s*(\w+)", out, re.I)
                d["smart"] = m.group(1) if m else "OK"
    return discos


def _parse_rede() -> list[dict]:
    if not psutil:
        return []
    linhas = []
    try:
        addrs = psutil.net_if_addrs()
        stats = psutil.net_if_stats()
        for iface, lista in addrs.items():
            if iface == "lo":
                continue
            mac, ipv4 = "", ""
            for a in lista:
                addr = getattr(a, "address", "") or ""
                fam = str(getattr(a, "family", ""))
                if "AF_INET" in fam or (("." in addr) and (":" not in addr[:8])):
                    ipv4 = addr
                elif ":" in addr and len(addr) >= 11:
                    mac = addr
            st = stats.get(iface)
            linhas.append({
                "interface": iface,
                "mac": mac,
                "ipv4": ipv4,
                "link": f"{st.speed} Mbps" if st and st.speed else "—",
                "up": "Sim" if st and st.isup else "Não",
            })
    except Exception:
        pass
    return linhas


def _chave_sensor(nome: str) -> str:
    """Chave para evitar duplicar o mesmo sensor (psutil + sysfs)."""
    n = nome.lower()
    n = re.sub(r"\s+", " ", n)
    for prefixo in ("k10temp ", "coretemp ", "amdgpu ", "nvidia ", "zenpower "):
        if n.startswith(prefixo):
            n = n[len(prefixo):]
    return n.strip()


def coletar_sensores() -> list[dict]:
    """Temperaturas em tempo real (psutil, hwmon, thermal, GPU DRM)."""
    por_chave: dict[str, dict] = {}

    def _registar(nome: str, celsius: float, origem: str, prioridade: int) -> None:
        if celsius <= 0 or celsius > 150:
            return
        chave = _chave_sensor(nome)
        if not chave:
            return
        entrada = {
            "nome": nome,
            "valor": f"{celsius:.1f} °C",
            "tipo": origem,
            "_prioridade": prioridade,
        }
        antiga = por_chave.get(chave)
        if antiga is None or prioridade >= antiga.get("_prioridade", 0):
            por_chave[chave] = entrada

    if psutil:
        try:
            for chip, leituras in (psutil.sensors_temperatures() or {}).items():
                for i, leitura in enumerate(leituras):
                    atual = leitura.current
                    if atual is None:
                        continue
                    rotulo = leitura.label or f"T{i}"
                    nome = f"{chip} {rotulo}".strip()
                    _registar(nome, float(atual), "psutil", 30)
        except Exception:
            pass

    for inp in sorted(glob.glob("/sys/class/drm/card*/device/hwmon/hwmon*/temp*_input")):
        raw = _ler_arquivo(inp)
        if not raw.isdigit():
            continue
        pasta = os.path.dirname(inp)
        chip = _ler_arquivo(os.path.join(pasta, "name")) or "gpu"
        label = _ler_arquivo(inp.replace("_input", "_label")) or os.path.basename(inp)
        _registar(f"{chip} {label}".strip(), int(raw) / 1000, "gpu", 40)

    for hw in sorted(glob.glob("/sys/class/hwmon/hwmon*")):
        chip = _ler_arquivo(os.path.join(hw, "name")) or os.path.basename(hw)
        for inp in sorted(glob.glob(os.path.join(hw, "temp*_input"))):
            raw = _ler_arquivo(inp)
            if not raw.isdigit():
                continue
            label = _ler_arquivo(inp.replace("_input", "_label")) or os.path.basename(inp)
            _registar(f"{chip} {label}".strip(), int(raw) / 1000, "hwmon", 20)

    for zona in sorted(glob.glob("/sys/class/thermal/thermal_zone*")):
        temp = _ler_arquivo(os.path.join(zona, "temp"))
        tipo = _ler_arquivo(os.path.join(zona, "type")) or os.path.basename(zona)
        if temp.isdigit():
            _registar(tipo, int(temp) / 1000, "thermal", 10)

    lista = sorted(por_chave.values(), key=lambda s: s["nome"].lower())
    for s in lista:
        s.pop("_prioridade", None)
    return lista[:40]


def _parse_sensores() -> list[dict]:
    return coletar_sensores()


def coletar_hardware(usar_smbios: bool = True, rodar_benchmark: bool = False) -> DadosHardware:
    from agildo_specs.benchmark import executar_benchmark

    dados = DadosHardware()
    lscpu = _parse_lscpu()
    dados.cpu = {
        "Modelo": lscpu.get("Model name", lscpu.get("Nome do modelo", "")),
        "Arquitetura": lscpu.get("Architecture", lscpu.get("Arquitetura", "")),
        "Nucleos": lscpu.get("Core(s) per socket", lscpu.get("Núcleo(s) por soquete", "")),
        "Threads": lscpu.get("CPU(s)", ""),
        "Soquetes": lscpu.get("Socket(s)", lscpu.get("Soquete(s)", "")),
        "Frequencia max": lscpu.get("CPU max MHz", lscpu.get("CPU MHz máx.", "")),
        "Virtualizacao": lscpu.get("Virtualization", lscpu.get("Virtualização", "")),
        "Cache L3": lscpu.get("L3 cache", lscpu.get("cache de L3", "")),
        "Microcode": lscpu.get("Microcode version", ""),
    }
    dados.cpu.update(_parse_cpu_extra())
    dados.gpus, dados.gpu_detalhe = _parse_lspci_gpus()
    dados.discos = _parse_discos()
    dados.rede = _parse_rede()
    dados.sensores = _parse_sensores()
    dados.sistema = {
        "Fabricante": _ler_sysfs_dmi("sys_vendor"),
        "Produto": _ler_sysfs_dmi("product_name"),
        "Versao": _ler_sysfs_dmi("product_version"),
    }
    dados.placa = {
        "Fabricante": _ler_sysfs_dmi("board_vendor"),
        "Modelo": _ler_sysfs_dmi("board_name"),
        "Versao": _ler_sysfs_dmi("board_version"),
        "Chipset": _ler_sysfs_dmi("product_name"),
    }
    dados.bios = {
        "Fornecedor": _ler_sysfs_dmi("bios_vendor"),
        "Versao": _ler_sysfs_dmi("bios_version"),
        "Data": _ler_sysfs_dmi("bios_date"),
    }
    if usar_smbios:
        smbios, erro = _ler_dmidecode_com_privilegio()
        if erro:
            dados.erro_smbios = erro
        if smbios:
            dados.modulos_ram, dados.memoria_array = _parse_dmidecode_memoria(smbios)
            dados.cpu.update(_parse_dmidecode_processador(smbios))
            dados.pcie = _parse_dmidecode_pcie(smbios)
            dados.dual_channel, dados.dual_channel_detalhe = _inferir_dual_channel(
                dados.modulos_ram, dados.memoria_array,
            )
            dados.validacao_ram = _validar_slots_ram(
                dados.modulos_ram, dados.placa.get("Modelo", ""),
            )
    if rodar_benchmark:
        dados.benchmark = executar_benchmark()
    return dados


def total_ram_texto(modulos: list[ModuloRam], array_info: dict | None = None) -> str:
    array_info = array_info or {}
    total_mb, ativos = 0, 0
    for m in modulos:
        if not m.preenchido:
            continue
        ativos += 1
        g = re.search(r"(\d+)\s*G[iB]?B", m.tamanho, re.I)
        if g:
            total_mb += int(g.group(1)) * 1024
            continue
        g = re.search(r"(\d+)\s*M[iB]?B", m.tamanho, re.I)
        if g:
            total_mb += int(g.group(1))
    if total_mb >= 1024:
        return f"{total_mb / 1024:.0f} GB ({ativos} modulo(s))"
    rs = array_info.get("range_size", "")
    if rs:
        return f"{rs}"
    return ""
