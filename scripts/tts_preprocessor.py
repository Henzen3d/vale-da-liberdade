#!/usr/bin/env python3
"""
Módulo de pré-processamento TTS para o Web Jornal Vale da Liberdade.

Implementa as substituições obrigatórias definidas na SKILL.md (Seções 8.2 e 8.3):
- Expansão de siglas para pronúncia soletrada
- Substituição de símbolos por palavras
- Remoção de formatação markdown
- Inserção de marcadores de pausa entre quadros e falas longas
- Normalização dos rótulos de speaker (PETER: / RICARDO:)

[FASE 5.1] Normalização robusta via num2words pt-BR:
- Números por extenso (104 → "cento e quatro")
- Datas (20/06/2026 → "vinte de junho de dois mil e vinte e seis")
- Anos isolados por extenso
- Horas (21h40 → "vinte e uma horas e quarenta")
- Moeda (R$ 70 milhões → "setenta milhões de reais")
- Percentual (104% → "cento e quatro por cento")

[FASE 5.2] Lexicon de pronúncia regional:
- Carrega sources/pronunciation_lexicon.json com aliases para toponímia

Uso standalone:
    python tts_preprocessor.py --input episodes/2026-06-15.md --output episodes/2026-06-15-tts.txt

Uso como módulo:
    from tts_preprocessor import preprocess_for_tts
    tts_text = preprocess_for_tts(roteiro_markdown)
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Configuração de caminho para lexicon
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
LEXICON_PATH = PROJECT_ROOT / "sources" / "pronunciation_lexicon.json"

# Tentar importar num2words; se não instalado, usar fallback
try:
    from num2words import num2words as _num2words
    _NUM2WORDS_AVAILABLE = True
except ImportError:
    _NUM2WORDS_AVAILABLE = False

# ---------------------------------------------------------------------------
# Seção 8.2 — Substituições obrigatórias antes de enviar para TTS
# ---------------------------------------------------------------------------

TTS_SUBSTITUTIONS: dict[str, str] = {
    # Siglas — pronúncia natural/soletrada quando necessário
    "web": "ueb",
    "BR-470": "B-R quatrocentos e setenta",
    "BR-163": "B-R cento e sessenta e três",
    "STF": "S-T-F",
    "STJ": "S-T-J",
    "TSE": "T-S-E",
    "TST": "T-S-T",
    "TRF": "T-R-F",
    "TRE": "T-R-E",
    "TCE": "Tribunal de Contas do Estado",
    "TCU": "Tribunal de Contas da União",
    "CGM": "Controladoria Geral do Município",
    "CGU": "Controladoria Geral da União",
    "SEMED": "Secretaria Municipal de Educação",
    "UPA": "U-P-A",
    "SUS": "SUS",
    "PM": "Polícia Militar",
    "PC": "Polícia Civil",
    "PF": "Polícia Federal",
    "MP": "Ministério Público",
    "MPSC": "M-P-S-C",
    "OAB": "O-A-B",
    "CPI": "C-P-I",
    "PIX": "P-I-X",
    "PIB": "P-I-B",
    "IPVA": "I-P-V-A",
    "ICMS": "I-C-M-S",
    "IPTU": "I-P-T-U",
    "ISS": "I-S-S",
    "PNA": "P-N-A",
    "CASAN": "Casan",
    "CELESC": "Celesc",
    "FIESC": "Fiésc",
    "ACIB": "A-C-I-B",
    "FURB": "Furb",
    "UFSC": "U-F-S-C",
    "ENEM": "Énem",
    "BR": "B-R",
    "SC": "S-C",
    "ALESC": "Alésc",
    "JASC": "jasc",
    "GRAC": "grac",
    "Univali": "UNIVALE",
    "RG": "R-G",
    "CNH": "C-N-H",
    # Pronúncia regional / estrangeirismos
    "Padre João Bachmann": "Padre João Baquemam",
    "RUN": "rãm",
    # Símbolos / unidades
    "R$": "reais",
    "%": " por cento",
    "m²": "metros quadrados",
    "km²": "quilômetros quadrados",
    "km": "quilômetros",
    "nº": "número",
    "Nº": "número",
    "°C": "graus Celsius",
    "§": "parágrafo",
    "Art.": "Artigo",
    "art.": "artigo",
}

# ---------------------------------------------------------------------------
# Normalização robusta via num2words (Fase 5.1)
# ---------------------------------------------------------------------------

# Meses em português para conversão de datas
_MESES = [
    "", "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"
]

# Abreviações de mês
_MESES_ABREV = {
    "jan": 1, "fev": 2, "mar": 3, "abr": 4, "mai": 5, "jun": 6,
    "jul": 7, "ago": 8, "set": 9, "out": 10, "nov": 11, "dez": 12
}


def _number_to_words(n: int | float) -> str:
    """Converte número para extenso em pt-BR usando num2words."""
    if not _NUM2WORDS_AVAILABLE:
        return str(n)
    try:
        if isinstance(n, float) and not n.is_integer():
            return _num2words(n, lang="pt_BR")
        return _num2words(int(n), lang="pt_BR")
    except Exception:
        return str(n)


# Unidades longas primeiro para "mil" não engolir "milhão".
_CURRENCY_UNIT = r"(bilhões|bilhão|milhões|milhão|mil)"
# Símbolos longos primeiro: US$ / R$ antes de $ solto.
_CURRENCY_SPECS: list[tuple[str, str, str]] = [
    (r"US\$|U\$S|U\$|USD\b", "dólares", "de dólares"),
    (r"R\$", "reais", "de reais"),
    (r"€|EUR\b", "euros", "de euros"),
    (r"£|GBP\b", "libras", "de libras"),
    (r"(?<![A-Za-z])\$", "dólares", "de dólares"),
]


def _format_spoken_currency(raw_num: str, unit: str | None, simple: str, de: str) -> str:
    """Monta '{valor} {unidade?} {moeda}' em ordem falada pt-BR."""
    unit_l = (unit or "").strip().lower()
    spoken = raw_num
    if _NUM2WORDS_AVAILABLE:
        if "," in raw_num:
            normalized = raw_num.replace(".", "").replace(",", ".")
        else:
            normalized = raw_num.replace(".", "")
        try:
            val = float(normalized)
            val_int: int | float = int(val) if val == int(val) else val
            words = _number_to_words(val_int)
            if words:
                spoken = words
        except ValueError:
            spoken = raw_num
    if unit_l in {"milhão", "milhões", "bilhão", "bilhões"}:
        return f"{spoken} {unit_l} {de}"
    if unit_l == "mil":
        return f"{spoken} mil {simple}"
    return f"{spoken} {simple}"


def _normalize_currency(text: str) -> str:
    """
    Reescreve símbolo+valor para ordem falada pt-BR.
    R$ 50 mil → "50 mil reais" (ou "cinquenta mil reais" se num2words).
    Nunca "reais 50 mil". Vale para US$, $, €, £.
    """
    for symbol_re, simple, de in _CURRENCY_SPECS:
        def _repl(match, simple=simple, de=de):
            return _format_spoken_currency(match.group(1), match.group(2), simple, de)

        text = re.sub(
            rf"(?:{symbol_re})\s*([\d.,]*\d)(?:\s*{_CURRENCY_UNIT})?",
            _repl,
            text,
            flags=re.IGNORECASE,
        )
    return text


def _normalize_percentage(text: str) -> str:
    """Normaliza percentuais: 104% → 'cento e quatro por cento'."""
    def _replace(match):
        val_str = match.group(1).replace(",", ".")
        try:
            val = float(val_str)
            val_int = int(val) if val == int(val) else val
            return f"{_number_to_words(val_int)} por cento"
        except ValueError:
            return match.group(0)
    return re.sub(r"([\d,]+)\s*%", _replace, text)


def _normalize_dates(text: str) -> str:
    """
    Normaliza datas para extenso em pt-BR.
    Suporta: DD/MM/YYYY, DD/MM/YY, DD de mês de YYYY.
    """
    def _replace_date(match):
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        if year < 100:
            year += 2000
        if not (1 <= month <= 12):
            return match.group(0)
        day_w = _number_to_words(day)
        month_name = _MESES[month]
        year_w = _number_to_words(year)
        return f"{day_w} de {month_name} de {year_w}"

    return re.sub(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", _replace_date, text)


def _normalize_years(text: str) -> str:
    """Normaliza anos isolados de 4 dígitos (1900-2099) para extenso."""
    def _replace_year(match):
        year = int(match.group(1))
        return _number_to_words(year)
    # Apenas anos isolados (não datas, não CPF, não telefone)
    return re.sub(r"(?<![\d/\-])((?:19|20)\d{2})(?![\d/\-])", _replace_year, text)


def _normalize_times(text: str) -> str:
    """
    Normaliza horas: 21h40 → 'vinte e uma horas e quarenta'
                    14h → 'quatorze horas'
                    9h30 → 'nove horas e trinta'
                    22h20min → 'vinte e duas horas e vinte' (consome sufixo 'min')
    """
    def _replace_time(match):
        hour = int(match.group(1))
        minute = match.group(2)
        hour_w = _number_to_words(hour)
        if minute and int(minute) > 0:
            min_w = _number_to_words(int(minute))
            return f"{hour_w} horas e {min_w}"
        return f"{hour_w} horas"

    # Ordem importa: 22h20min (com sufixo min) ANTES de 22h20 simples,
    # para não deixar 'min' colado (ex.: 'vintemin').
    text = re.sub(r"(\d{1,2})h(\d{2})min\b", _replace_time, text, flags=re.IGNORECASE)
    text = re.sub(r"(\d{1,2})h(\d{2})?", _replace_time, text)
    return text


def _normalize_durations(text: str) -> str:
    """
    Normaliza durações curtas em minutos: 28min ou 28m → 'vinte e oito minutos'.
    Usa word boundary em 'm' para não conflitar com 'm²', 'mil', 'metros', etc.
    Não toca em 'km' (quilômetros) nem em 'm' dentro de outras palavras.
    """
    def _replace_min(match):
        val = int(match.group(1))
        return f"{_number_to_words(val)} minutos"

    def _replace_m(match):
        val = int(match.group(1))
        return f"{_number_to_words(val)} minutos"

    # 28min | 28MIN  (sempre minuto)
    text = re.sub(r"(\d+)\s*min\b", _replace_min, text, flags=re.IGNORECASE)
    # 28m (letra m isolada, com word boundary). Protege contra "3m de tubulação"
    # (metro, não minuto): não converte se seguido de " de <substantivo>".
    text = re.sub(r"(\d+)\s*m\b(?!\s+de\b)", _replace_m, text)
    return text


def _normalize_roads(text: str) -> str:
    """
    Normaliza rodovias para extenso em pt-BR: BR-470 → 'BR quatrocentos e setenta'.
    Também aceita prefixos de UF (SC-470, PR-101, etc.) e a palavra 'rodovia'.
    Converte apenas o número após o hífen; preserva o prefixo (BR/SC/PR...).
    """
    def _replace_road(match):
        prefix = match.group(1)  # ex.: 'BR', 'SC', 'rodovia BR'
        num = int(match.group(2))
        return f"{prefix} {_number_to_words(num)}"

    # BR-470 | SC-101 | rodovia BR-470 | Rodovia SC-101
    text = re.sub(
        r"\b((?:rodovia\s+)?[A-Z]{2})-(\d{1,6})\b",
        _replace_road,
        text,
        flags=re.IGNORECASE,
    )
    return text


def _normalize_plain_numbers(text: str):
    """
    Converte números isolados para extenso em pt-BR.
    Evita converter: anos (tratados por _normalize_years), rodovias (preservadas),
    URLs, CEPs, CPFs, telefones.
    Aplica apenas a números ≤ 999.999 para evitar converter IDs longos.
    """
    def _replace_num(match):
        num_str = match.group(0).replace(".", "")
        try:
            n = int(num_str)
            if n > 999_999 or n <= 10:  # Não converter números muito pequenos ou grandes
                return match.group(0)
            return _number_to_words(n)
        except ValueError:
            return match.group(0)

    # Apenas números isolados (não precedidos/seguidos de letras/símbolos especiais)
    return re.sub(r"(?<![\w/\-.])\d{2,6}(?:[.]\d{3})*(?![\w/\-.])", _replace_num, text)


def _apply_num2words_normalization(text: str) -> str:
    """
    Aplica todas as normalizações num2words em ordem segura.
    Ordem: moeda → data → hora → ano → percentual → números simples.
    Moeda roda SEMPRE (não depende de num2words): R$ 50 mil → "50 mil reais".
    """
    text = _normalize_currency(text)
    if not _NUM2WORDS_AVAILABLE:
        return text  # Fallback: sem extenso de data/hora/número
    text = _normalize_dates(text)
    text = _normalize_times(text)
    text = _normalize_durations(text)
    text = _normalize_years(text)
    text = _normalize_percentage(text)
    # Rodovias (BR-470 → BR quatrocentos e setenta) antes dos números simples
    text = _normalize_roads(text)
    # Números simples por último (após moeda/data/hora para não conflitar)
    text = _normalize_plain_numbers(text)  # Habilitado (Fase 5.1)
    return text


# ---------------------------------------------------------------------------
# Lexicon de pronúncia regional (Fase 5.2)
# ---------------------------------------------------------------------------

_PRONUNCIATION_LEXICON: dict[str, str] = {}  # Carregado na primeira chamada
_LEXICON_LOADED = False


def load_pronunciation_lexicon() -> dict[str, str]:
    """Carrega sources/pronunciation_lexicon.json com aliases de pronúncia regional."""
    global _PRONUNCIATION_LEXICON, _LEXICON_LOADED
    if _LEXICON_LOADED:
        return _PRONUNCIATION_LEXICON
    try:
        if LEXICON_PATH.exists():
            with open(LEXICON_PATH, "r", encoding="utf-8") as f:
                _PRONUNCIATION_LEXICON = json.load(f)
    except Exception:
        pass  # Lexicon é opcional — falha silenciosa
    _LEXICON_LOADED = True
    return _PRONUNCIATION_LEXICON


def _apply_pronunciation_lexicon(text: str) -> str:
    """Aplica substituições fonéticas do lexicon regional."""
    lexicon = load_pronunciation_lexicon()
    if not lexicon:
        return text
    for original, phonetic in lexicon.items():
        # Word-boundary match para evitar substituições parciais
        pattern = rf"(?<![\w])({re.escape(original)})(?![\w])"
        text = re.sub(pattern, phonetic, text, flags=re.IGNORECASE)
    return text


# Padrões de markdown a remover na versão TTS (Seção 8.2)
TTS_REMOVE_PATTERNS: list[str] = [
    r"^#{1,6}\s+.*$",          # headers markdown (# ## ### etc.)
    r"\*{1,2}([^*]+)\*{1,2}",  # negrito/itálico → manter texto interno
    r"^---+\s*$",              # separadores horizontais
    r"^\[QUADRO:.*\]$",        # marcadores de quadro
    r"^•\s*",                  # bullets de manchetes
    r"^-\s+",                  # listas com traço
    r"^>\s*",                  # blockquotes
    r"`([^`]+)`",              # código inline → manter texto interno
]

# Palavras-chave de início de quadro (para inserir [PAUSA])
QUADRO_KEYWORDS: list[str] = [
    "SEGURANÇA PÚBLICA",
    "SAÚDE",
    "EDUCAÇÃO",
    "POLÍTICA E ADMINISTRAÇÃO",
    "ESPORTES",
    "RAPIDINHAS",
    "FECHAMENTO",
    "INTRODUÇÃO EDITORIAL",
    "MANCHETES",
    "INFRAESTRUTURA",
    "ECONOMIA",
    "MEIO AMBIENTE",
    "DESPORTOS",
]

# Limiar de comprimento de fala para inserir [PAUSA_CURTA]
MAX_FALA_LENGTH = 400  # caracteres


def _apply_substitutions(text: str) -> str:
    """Aplica todas as substituições de siglas e símbolos."""
    # Moeda em ordem falada pt-BR (R$ 50 mil → 50 mil reais), nunca prefixar.
    text = _normalize_currency(text)
    text = re.sub(r"R\$", "reais", text)

    # Substituir % mantendo o número anterior
    text = re.sub(r"(\d)\s*%", r"\1 por cento", text)

    # Substituir símbolos simples
    for symbol in ["m²", "km²", "°C", "§", "nº", "Nº", "Art.", "art."]:
        if symbol in TTS_SUBSTITUTIONS and symbol in text:
            text = text.replace(symbol, TTS_SUBSTITUTIONS[symbol])

    # Substituir km (cuidado para não substituir dentro de km²)
    text = re.sub(r"(\d)\s*km(?!²|\w)", r"\1 quilômetros", text)

    # PROTEGER códigos de rodovia ANTES da substituição de siglas.
    # A regra \bBR\b → "B-R" corrompia "BR-470" em "B-R-470" (confirmado em
    # episodes/2026-06-20-tts.txt). Placeholders temporários preservam BR/SC + número.
    # Suporta BR-###, SC-###, RR-###, etc. (rodovias federais e estaduais).
    RODOVIA_PLACEHOLDER = "\x00RODOVIA{}\x00"
    rodovias_encontradas = []

    def _guardar_rodovia(match):
        idx = len(rodovias_encontradas)
        rodovias_encontradas.append(match.group(0))
        return RODOVIA_PLACEHOLDER.format(idx)

    text = re.sub(r"\b(BR|SC|RR|ER|RS|PR|SP|RJ|MG|ES|DF)-(\d{2,4})\b", _guardar_rodovia, text)

    # Substituir siglas — usar word boundaries para não substituir dentro de palavras
    sigla_map = {
        k: v for k, v in TTS_SUBSTITUTIONS.items()
        if k not in ["R$", "%", "m²", "km²", "km", "°C", "§", "nº", "Nº",
                      "Art.", "art.", "---"]
    }

    for sigla, expansao in sorted(sigla_map.items(), key=lambda x: -len(x[0])):
        # Usar word boundary para siglas de letras maiúsculas
        pattern = rf"\b{re.escape(sigla)}\b"
        text = re.sub(pattern, expansao, text)

    # RESTAURAR rodovias (após substituição de siglas): BR-470 volta intacto.
    # O TTS pronuncia "BR-470" adequadamente; se necessário, alias fonético pode
    # ser adicionado em sources/pronunciation_lexicon.json (Roadmap Fase 5.2).
    for idx, rodovia in enumerate(rodovias_encontradas):
        text = text.replace(RODOVIA_PLACEHOLDER.format(idx), rodovia)

    return text


def _strip_markdown(text: str) -> str:
    """Remove formatação markdown preservando o conteúdo textual."""
    lines = text.split("\n")
    cleaned = []

    for line in lines:
        stripped = line.strip()

        # Remover headers markdown
        if re.match(r"^#{1,6}\s+", stripped):
            continue

        # Remover separadores
        if re.match(r"^---+\s*$", stripped):
            continue

        # Remover marcadores de quadro
        if re.match(r"^\[QUADRO:.*\]$", stripped):
            continue

        # Remover bullets de manchetes e listas
        stripped = re.sub(r"^[•\-]\s*", "", stripped)

        # Remover blockquotes
        stripped = re.sub(r"^>\s*", "", stripped)

        # Negrito/itálico → manter texto interno
        stripped = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", stripped)

        # Código inline → manter texto
        stripped = re.sub(r"`([^`]+)`", r"\1", stripped)

        # Remover links markdown [texto](url) → manter texto
        stripped = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", stripped)

        # Remover imagens markdown ![alt](url)
        stripped = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", stripped)

        cleaned.append(stripped)

    return "\n".join(cleaned)


def _normalize_speaker_labels(text: str) -> str:
    """Normaliza rótulos de speaker para formato TTS consistente."""
    # Variantes possíveis → formato padrão (deve corresponder exatamente aos nomes em SPEAKERS)
    text = re.sub(r"^(Peter)\s*:", "Peter:", text, flags=re.MULTILINE | re.IGNORECASE)
    text = re.sub(r"^(Ricardo)\s*:", "Ricardo:", text, flags=re.MULTILINE | re.IGNORECASE)
    return text


def _insert_pauses(text: str) -> str:
    """Insere marcadores de pausa entre quadros e falas longas."""
    lines = text.split("\n")
    result = []

    for i, line in enumerate(lines):
        stripped = line.strip()

        # Detectar início de quadro e inserir pausa antes
        is_quadro_start = False
        for keyword in QUADRO_KEYWORDS:
            if keyword.lower() in stripped.lower() and (
                stripped.startswith("Peter:") or stripped.startswith("Ricardo:")
                or "QUADRO" in stripped.upper()
            ):
                is_quadro_start = True
                break

        if is_quadro_start and result and result[-1].strip() != "[PAUSA]":
            result.append("\n[PAUSA]\n")

        # Inserir pausa curta em falas muito longas
        if (stripped.startswith("Peter:") or stripped.startswith("Ricardo:")) and len(stripped) > MAX_FALA_LENGTH:
            result.append(line)
            result.append("[PAUSA_CURTA]")
        else:
            result.append(line)

    return "\n".join(result)


def _extract_speaker_lines(text: str) -> str:
    """Extrai apenas linhas com falas de Peter ou Ricardo."""
    lines = text.split("\n")
    result = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Peter:") or stripped.startswith("Ricardo:"):
            result.append(stripped)
        elif stripped in ("[PAUSA]", "[PAUSA_CURTA]"):
            result.append(stripped)
        elif stripped == "":
            result.append("")

    # Limpar linhas vazias consecutivas
    cleaned = []
    prev_empty = False
    for line in result:
        if line == "":
            if not prev_empty:
                cleaned.append(line)
            prev_empty = True
        else:
            cleaned.append(line)
            prev_empty = False

    return "\n".join(cleaned).strip()


def _fix_peter_pronunciation(text: str) -> str:
    """Peter (nome) → Piter na fala; mantém rótulo 'Peter:' para o multi/turns."""
    # Proteger rótulos de locutor no início da linha
    text = re.sub(
        r"^(Peter)\s*:",
        r"<<<SPK_PETER>>>:",
        text,
        flags=re.MULTILINE | re.IGNORECASE,
    )
    # Nome falado (Ricardo citando, etc.)
    text = re.sub(r"\bPeter\b", "Piter", text)
    text = re.sub(r"\bpeter\b", "Piter", text)
    text = text.replace("<<<SPK_PETER>>>:", "Peter:")
    return text


def preprocess_for_tts(markdown_text: str) -> str:
    """
    Pipeline completo de pré-processamento para TTS.

    Args:
        markdown_text: Roteiro em formato markdown.

    Returns:
        Texto limpo pronto para síntese de voz, contendo apenas
        Peter: / Ricardo: seguidos de texto corrido, com marcadores
        de pausa inseridos.
    """
    text = markdown_text

    # 1. Remover formatação markdown
    text = _strip_markdown(text)

    # 2. Normalizar rótulos de speaker
    text = _normalize_speaker_labels(text)

    # 3. Normalização numérica via num2words (Fase 5.1) — antes das siglas
    #    para evitar conflito (ex: R$ processado aqui, não no dict estático)
    text = _apply_num2words_normalization(text)

    # 4. Aplicar substituições de siglas e símbolos (restantes)
    text = _apply_substitutions(text)

    # 5. Aplicar lexicon de pronúncia regional (Fase 5.2)
    text = _apply_pronunciation_lexicon(text)

    # 5b. Peter → Piter (pronúncia EN) sem quebrar rótulo Peter:
    text = _fix_peter_pronunciation(text)

    # 5c. Vírgula ao redor de nomes de locutor → pausa artificial no TTS
    #     "estado, Peter" → "estado Peter" ; "Peter, você" → "Peter você"
    def _soften_names_line(line: str) -> str:
        if not (line.startswith("Peter:") or line.startswith("Ricardo:")):
            return line
        sp, _, body = line.partition(":")
        body = re.sub(r",\s*(Peter|Ricardo|Piter)\b", r" \1", body)
        body = re.sub(r"\b(Peter|Ricardo|Piter),\s+", r"\1 ", body)
        body = re.sub(r"\s{2,}", " ", body)
        return f"{sp}:{body}"

    text = "\n".join(_soften_names_line(l) for l in text.split("\n"))

    # 6. Extrair apenas linhas de falas
    text = _extract_speaker_lines(text)

    # 7. Inserir marcadores de pausa
    text = _insert_pauses(text)

    # 8. Limpeza final
    text = re.sub(r"\n{3,}", "\n\n", text)  # Máximo 1 linha vazia
    text = text.strip() + "\n"

    return text


def extract_manchetes(markdown_text: str) -> str:
    """
    Extrai o bloco de manchetes do roteiro.

    Procura por padrões como '## 📋 MANCHETES DO DIA' ou '## Manchetes do dia'.
    """
    lines = markdown_text.split("\n")
    manchetes = []
    in_manchetes = False

    for line in lines:
        stripped = line.strip()

        # Detectar início do bloco de manchetes
        if re.match(r"^#{1,3}\s*📋?\s*MANCHETES", stripped, re.IGNORECASE) or \
           re.match(r"^#{1,3}\s*Manchetes\s+do\s+dia", stripped, re.IGNORECASE):
            in_manchetes = True
            continue

        # Detectar fim do bloco (próximo header ou separador seguido de header)
        if in_manchetes:
            if re.match(r"^#{1,3}\s+\w", stripped) and "MANCHETE" not in stripped.upper():
                break
            if stripped.startswith("•") or stripped.startswith("-"):
                manchete = re.sub(r"^[•\-]\s*", "", stripped).strip()
                if manchete:
                    manchetes.append(f"• {manchete}")
            elif stripped == "---":
                continue

    if not manchetes:
        return ""

    return "MANCHETES DO DIA\n\n" + "\n".join(manchetes) + "\n"


def generate_metadata(markdown_text: str, date: str, episode_num: int | None = None,
                      sources_used: list[str] = None,
                      selected_news: list[dict] = None,
                      raw_articles_count: int = 0,
                      url_duplicates: int = 0,
                      semantic_duplicates: int = 0,
                      validation_errors: list[str] = None,
                      validation_warnings: list[str] = None,
                      breaking_count: int = 0) -> dict:
    """
    Gera metadados do episódio conforme SKILL.md Seção 10.
    Envolve estatísticas do pipeline e validação para auditoria.
    """
    lines = markdown_text.split("\n")

    # Contar quadros gerados
    quadros = []
    quadro_map = {
        "segurança": "seguranca",
        "saúde": "saude",
        "educação": "educacao",
        "política": "politica",
        "esportes": "esportes",
        "comunidade": "esportes",
        "rapidinhas": "rapidinhas",
        "infraestrutura": "infraestrutura",
        "economia": "economia",
        "meio ambiente": "meio_ambiente",
        "desportos": "desportos",
        "cultura": "cultura",
        "brasil": "brasil",        # Fase 3.1
        "mundo": "mundo",          # Fase 3.1
    }

    for line in lines:
        stripped = line.strip().lower()
        if "quadro" in stripped or (stripped.startswith("##") and ":" in stripped):
            for keyword, slug in quadro_map.items():
                if keyword in stripped and slug not in quadros:
                    quadros.append(slug)

    # Contar notícias (heurística: contar manchetes)
    manchetes = [l for l in lines if l.strip().startswith("•") or
                 (l.strip().startswith("-") and not l.strip().startswith("- http")
                  and not l.strip().startswith("- Referência"))]

    # Estimar duração (150 palavras por minuto faladas)
    word_count = len(markdown_text.split())
    duracao_min = round(word_count / 150, 1)

    return {
        "edicao": date,
        "episodio": episode_num,
        "duracao_estimada_min": duracao_min,
        "palavras_total": word_count,
        "quadros_gerados": quadros,
        "noticias_total": len(manchetes),
        "noticias_com_continuidade": 0,
        "fontes_utilizadas": sources_used or [],
        "arquivos_gerados": ["roteiro.md", "roteiro_tts.txt", "manchetes.txt"],

        # Estatísticas de pipeline e validação para auditoria.
        "pipeline_stats": {
            "artigos_brutos_coletados": raw_articles_count,
            "duplicatas_url_removidas": url_duplicates,
            "duplicatas_semanticas_removidas": semantic_duplicates,
            "noticias_apos_dedup": len(selected_news) if selected_news else 0,
            "breaking_detectadas": breaking_count,
            "fontes_com_sucesso": sources_used or [],
            "fontes_com_falha": [],
        },
        "validacao": {
            "erros_bloqueantes": validation_errors or [],
            "avisos": validation_warnings or [],
            "passou": len(validation_errors or []) == 0,
        },
    }


def validate_episode(markdown_text: str) -> list[str]:
    """
    Valida o episódio contra o checklist de qualidade (SKILL.md Seção 9).

    Returns:
        Lista de problemas encontrados. Lista vazia = tudo OK.
    """
    issues = []
    text_lower = markdown_text.lower()

    # 1. Bloco de manchetes presente
    if "manchetes" not in text_lower:
        issues.append("❌ Bloco de manchetes ausente (deve estar antes da introdução editorial)")

    # 2. Quadros obrigatórios
    required_quadros = [
        ("segurança", "Segurança Pública"),
        ("saúde", "Saúde"),
        ("educação", "Educação"),
        ("política", "Política e Administração Pública"),
        ("esporte", "Esportes e Interesse Comunitário"),
    ]
    for keyword, name in required_quadros:
        if keyword not in text_lower:
            issues.append(f"❌ Quadro obrigatório ausente: {name}")

    # 2b. Quadros nacionais/internacionais (Fase 3.1) — warnings opcionais
    optional_quadros = [
        ("brasil", "BRASIL (notícia nacional)"),
        ("mundo",  "MUNDO (notícia internacional)"),
    ]
    for keyword, name in optional_quadros:
        if keyword not in text_lower:
            issues.append(f"⚠️ Quadro recomendado ausente: {name} — ver Roadmap Fase 3")

    # 3. Falas muito longas (mais de 6 linhas sem interrupção)
    lines = markdown_text.split("\n")
    current_speaker = None
    consecutive = 0
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Peter:") or stripped.startswith("Ricardo:"):
            speaker = stripped.split(":")[0]
            if speaker == current_speaker:
                consecutive += 1
            else:
                consecutive = 1
                current_speaker = speaker
            if consecutive > 6:
                issues.append(f"⚠️ {speaker} fala por {consecutive} linhas consecutivas sem interrupção")
        elif stripped == "":
            continue

    # 4. Saudações temporais proibidas
    temporal_greetings = ["bom dia", "boa tarde", "boa noite", "bom-dia", "boa-tarde", "boa-noite"]
    for greeting in temporal_greetings:
        if greeting in text_lower:
            issues.append(f"❌ Saudação temporal proibida encontrada: \"{greeting}\"")

    # 5. Tom libertário (heurística)
    libertarian_keywords = [
        "estado", "imposto", "contribuinte", "liberdade", "privado",
        "burocracia", "monopólio", "descentraliz", "voluntári",
    ]
    libertarian_count = sum(1 for kw in libertarian_keywords if kw in text_lower)
    if libertarian_count < 3:
        issues.append("⚠️ Poucas referências ao viés libertário (recomendado: pelo menos 3 menções)")

    # 6. Estimativa de duração — GATE de tamanho (item 4)
    # Meta: 2000–2500 palavras (~15 min). Piso duro antes do áudio: 1500 (~8–10 min).
    word_count = len(markdown_text.split())
    if word_count < 1500:
        issues.append(
            f"❌ Roteiro curto demais para áudio ({word_count} palavras) — "
            f"mínimo 1500 (~8 min); meta 2000-2500 (~15 min)"
        )
    elif word_count < 2000:
        issues.append(
            f"⚠️ Roteiro abaixo da meta ({word_count} palavras) — meta: 2000-2500 palavras (~15 min)"
        )
    elif word_count > 3000:
        issues.append(f"⚠️ Roteiro longo ({word_count} palavras) — meta: 2000-2500 palavras (~15 min)")

    # 7. Naturalidade / dinâmica conversacional (SKILL §7.1)
    try:
        try:
            from validate_naturalidade import validate_naturalidade
        except ImportError:
            _scripts = str(Path(__file__).resolve().parent)
            if _scripts not in sys.path:
                sys.path.insert(0, _scripts)
            from validate_naturalidade import validate_naturalidade

        issues.extend(validate_naturalidade(markdown_text))
    except Exception as exc:
        issues.append(f"⚠️ Naturalidade: validador indisponível ({exc})")

    return issues


# ---------------------------------------------------------------------------
# CLI standalone
# ---------------------------------------------------------------------------

def _run_tests():
    """Testes unitários básicos do pré-processamento."""
    print("🧪 Executando testes do tts_preprocessor...")
    errors = 0

    # Teste 1: Substituição de siglas
    result = _apply_substitutions("O STF decidiu hoje.")
    assert "S-T-F" in result, f"FALHA: sigla STF não expandida: {result}"
    print("  ✅ Substituição de siglas OK")

    # Teste 2: Substituição de R$ — moeda DEPOIS do valor (pt-BR)
    result = _apply_substitutions("Custou R$ 400 milhões.")
    assert "reais" in result, f"FALHA: R$ não substituído: {result}"
    assert "R$" not in result, f"FALHA: R$ ainda presente: {result}"
    assert "reais 400" not in result.lower(), f"FALHA: moeda prefixada: {result}"
    print("  ✅ Substituição de R$ OK")

    # Teste 2b: ordem falada pt-BR (R$ 50 mil → 50 mil reais, nunca "reais 50 mil")
    def _assert_currency_order(src: str, must_contain: str, forbidden: str) -> None:
        for label, out in (
            ("sub", _apply_substitutions(src)),
            ("cur", _normalize_currency(src)),
            ("pre", preprocess_for_tts(src)),
        ):
            low = out.lower()
            assert forbidden not in low, f"FALHA {label}: '{forbidden}' em {out!r} (src={src!r})"
            assert must_contain in low, f"FALHA {label}: falta '{must_contain}' em {out!r} (src={src!r})"

    _assert_currency_order(
        "Peter: O prejuízo chegou a R$ 50 mil.",
        "50 mil reais",
        "reais 50",
    )
    _assert_currency_order(
        "Ricardo: reembolso de R$ 9,8 mil pelo guincho.",
        "9,8 mil reais",
        "reais 9",
    )
    _assert_currency_order(
        "Peter: tarifa de R$ 315.",
        "315 reais",
        "reais 315",
    )
    _assert_currency_order(
        "Ricardo: investimento de R$ 3 milhões.",
        "3 milhões de reais",
        "reais 3",
    )
    _assert_currency_order(
        "Peter: concurso de R$ 1 milhão.",
        "1 milhão de reais",
        "reais 1",
    )
    _assert_currency_order(
        "Ricardo: US$ 350 milhões em subsidiária.",
        "350 milhões de dólares",
        "dólares 350",
    )
    _assert_currency_order(
        "Peter: quase € 20 mil.",
        "20 mil euros",
        "euros 20",
    )
    print("  ✅ Ordem de moeda pt-BR OK")

    # Teste 3: Substituição de %
    result = _apply_substitutions("Aumento de 15%")
    assert "por cento" in result, f"FALHA: % não substituído: {result}"
    print("  ✅ Substituição de % OK")

    # Teste 4: Remoção de markdown
    md = "## Quadro: Segurança\n\n**Peter:** Teste *importante*\n\n---"
    result = _strip_markdown(md)
    assert "##" not in result, f"FALHA: header não removido: {result}"
    assert "**" not in result, f"FALHA: negrito não removido: {result}"
    assert "*" not in result or "importante" in result, f"FALHA: itálico não removido: {result}"
    print("  ✅ Remoção de markdown OK")

    # Teste 5: Normalização de speakers
    result = _normalize_speaker_labels("Peter: Olá\nRicardo: Oi")
    assert "Peter:" in result, f"FALHA: Peter não normalizado: {result}"
    assert "Ricardo:" in result, f"FALHA: Ricardo não normalizado: {result}"
    print("  ✅ Normalização de speakers OK")

    # Teste 6: Pipeline completo
    roteiro = """# WEBJORNAL VALE DA LIBERDADE
## Edição: 15/06/2026

---
## 📋 MANCHETES DO DIA
---
• Corrupção em Blumenau
• Pedágios na BR-470
---

### INTRODUÇÃO EDITORIAL

Peter: O STF decidiu que R$ 400 milhões é pouco.
Ricardo: É, a PM não deu conta.

---
### QUADRO: SEGURANÇA PÚBLICA
---

Peter: A UPA estava lotada com 15% de ocupação a mais.
Ricardo: O SUS precisa de reforma.
"""
    result = preprocess_for_tts(roteiro)
    assert "##" not in result, "FALHA: markdown no TTS"
    assert "Peter:" in result, "FALHA: speaker label ausente"
    assert "S-T-F" in result, "FALHA: sigla não expandida no pipeline"
    assert "reais" in result, "FALHA: R$ não substituído no pipeline"
    assert "por cento" in result, "FALHA: % não substituído no pipeline"
    print("  ✅ Pipeline completo OK")

    # Teste 7: Extração de manchetes
    manchetes = extract_manchetes(roteiro)
    assert "Corrupção" in manchetes, f"FALHA: manchete não extraída: {manchetes}"
    assert "Pedágios" in manchetes, f"FALHA: manchete não extraída: {manchetes}"
    print("  ✅ Extração de manchetes OK")

    # Teste 8: Validação
    issues = validate_episode(roteiro)
    # Este roteiro curto deve ter warnings
    print(f"  ✅ Validação OK ({len(issues)} issues encontrados no roteiro de teste)")

    print(f"\n{'✅ Todos os testes passaram!' if errors == 0 else f'❌ {errors} teste(s) falharam'}")
    return errors


def main():
    parser = argparse.ArgumentParser(
        description="Pré-processamento TTS para Web Jornal Vale da Liberdade"
    )
    parser.add_argument("--input", "-i", help="Caminho do roteiro markdown (.md)")
    parser.add_argument("--output", "-o", help="Caminho de saída do arquivo TTS (.txt)")
    parser.add_argument("--manchetes", help="Caminho de saída do arquivo de manchetes")
    parser.add_argument("--validate", action="store_true", help="Validar episódio contra checklist")
    parser.add_argument("--test", action="store_true", help="Executar testes unitários")
    args = parser.parse_args()

    if args.test:
        sys.exit(_run_tests())

    if not args.input:
        parser.error("--input é obrigatório (exceto com --test)")

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"FALHA: arquivo não encontrado: {input_path}")
        sys.exit(2)

    content = input_path.read_text(encoding="utf-8")

    # Validação
    if args.validate:
        issues = validate_episode(content)
        if issues:
            print(f"⚠️ {len(issues)} problema(s) encontrado(s):")
            for issue in issues:
                print(f"  {issue}")
        else:
            print("✅ Episódio passou em todas as verificações.")
        sys.exit(1 if issues else 0)

    # Gerar TTS
    tts_text = preprocess_for_tts(content)
    output_path = Path(args.output) if args.output else input_path.with_suffix(".tts.txt")
    output_path.write_text(tts_text, encoding="utf-8")
    print(f"OK TTS: {output_path}")

    # Gerar manchetes
    manchetes = extract_manchetes(content)
    if manchetes:
        manchetes_path = Path(args.manchetes) if args.manchetes else input_path.parent / "manchetes.txt"
        manchetes_path.write_text(manchetes, encoding="utf-8")
        print(f"OK Manchetes: {manchetes_path}")
    else:
        print("⚠️ Nenhum bloco de manchetes encontrado no roteiro.")

    # Metadados
    date_str = input_path.stem  # ex: 2026-06-15
    metadata = generate_metadata(content, date_str)
    print(f"📊 Metadados: {metadata['palavras_total']} palavras, ~{metadata['duracao_estimada_min']} min, {len(metadata['quadros_gerados'])} quadros")


if __name__ == "__main__":
    main()
