#!/usr/bin/env python3
"""Metadados obrigatórios do canal Vale no YouTube (upload e atualizar detalhes)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Sao_Paulo")

CATEGORY_NEWS_POLITICS = "25"
CATEGORY_EDUCATION = "27"
CATEGORY_PEOPLE_BLOGS = "22"

TITLE_LANGUAGE = "pt"
AUDIO_LANGUAGE = "pt-BR"

PL_SOCIALISMO = "Socialismo e o Estado que promete"
PL_JUIZES = "Juízes e o gabinete"
PL_ECONOMIA = "Economia no recibo"
PL_BRASILIA = "Brasília no relógio"
PL_MUNDO = "O mundo que cobra o Brasil"

OFFICIAL_PLAYLISTS = (PL_JUIZES, PL_ECONOMIA, PL_BRASILIA, PL_MUNDO, PL_SOCIALISMO)

# IDs ao vivo em 2026-08-29 (canal Vale). Resolver de novo pelo título exato na API.
PLAYLIST_IDS = {
    PL_SOCIALISMO: "PLePrTPmrcBsV5Lef2UhlweTd-WbiU062H",
    PL_JUIZES: "PLePrTPmrcBsUptHe9vzjCfMjhEgEmIz1F",
    PL_ECONOMIA: "PLePrTPmrcBsVKw3OLvLu-Fjn7qSwZu_br",
    PL_BRASILIA: "PLePrTPmrcBsUyuJdVNpX2OwIQXxIgfd6n",
    PL_MUNDO: "PLePrTPmrcBsUPQerDhCru-5CfSEAVnxo-",
}

_EN_STOP = {
    "the", "a", "an", "of", "and", "to", "in", "is", "that", "for", "on", "with",
    "as", "was", "by", "this", "from", "it", "are", "be", "or", "not", "we", "you",
}
_PT_MARK = {
    "de", "da", "do", "que", "em", "no", "na", "os", "as", "para", "com", "uma",
    "um", "nao", "não", "o", "a", "e", "se", "por",
}


def _fold(text: str) -> str:
    raw = unicodedata.normalize("NFD", text or "")
    raw = "".join(c for c in raw if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", raw.lower()).strip()


def _has(blob: str, *needles: str) -> bool:
    for n in needles:
        n = _fold(n)
        if not n:
            continue
        if " " in n:
            if n in blob:
                return True
        elif re.search(rf"(?<!\w){re.escape(n)}(?!\w)", blob):
            return True
    return False


def recording_date_iso(now: datetime | None = None) -> str:
    """Data de envio em America/Sao_Paulo, ISO para a API."""
    d = (now or datetime.now(TZ)).astimezone(TZ).date()
    return f"{d.isoformat()}T00:00:00-03:00"


def choose_category(
    title: str = "",
    description: str = "",
    *,
    kind: str = "news",
    override: str | None = None,
) -> str:
    if override:
        return override
    blob = _fold(f"{title} {description}")
    if kind == "behind" or _has(blob, "bastidor do canal", "bastidores do canal"):
        return CATEGORY_PEOPLE_BLOGS
    if kind == "essay" or _is_historical_essay(title, description):
        return CATEGORY_EDUCATION
    return CATEGORY_NEWS_POLITICS


def _has_year(blob: str) -> bool:
    return bool(re.search(r"\b(19|20)\d{2}\b", blob))


def _is_historical_essay(title: str, description: str) -> bool:
    blob = _fold(f"{title} {description}")
    if not _has(blob, "ensaio"):
        return False
    return not _has_year(blob)


def _is_english_old(title: str, description: str) -> bool:
    words = re.findall(r"[a-zA-Z]+", _fold(f"{title} {description}"))
    if len(words) < 6:
        return False
    en = sum(1 for w in words if w in _EN_STOP)
    pt = sum(1 for w in words if w in _PT_MARK)
    if en >= 4 and en > pt * 2 and not _has_year(_fold(title)):
        return True
    return False


@dataclass(frozen=True)
class PlaylistDecision:
    names: tuple[str, ...]
    reason: str

    @property
    def skipped(self) -> bool:
        return not self.names


def _score_juizes(blob: str) -> int:
    s = 0
    if _has(blob, "stf", "tse", "agu", "moraes", "fachin", "barroso", "toffoli", "gilmar"):
        s += 3
    if _has(blob, "inquerito"):
        s += 3
    if _has(blob, "multa") and _has(blob, "judicial", "tse", "stf", "tribunal"):
        s += 3
    if _has(blob, "recalculo de pena", "recálculo de pena"):
        s += 3
    if _has(blob, "tribunal", "juiz", "ministros", "decisao de tribunal", "habeas"):
        s += 2
    if _has(blob, "proibir", "proibe", "proibiu", "investigar", "multar") and _has(
        blob, "tse", "stf", "tribunal", "juiz", "agu"
    ):
        s += 3
    return s


def _score_economia(blob: str) -> int:
    s = 0
    if _has(
        blob,
        "cnpj",
        "recuperacao judicial",
        "imposto",
        "inflacao",
        "apagao",
        "comparacao de preco",
        "comparar preco",
        "comparar o preco",
    ):
        s += 3
    if _has(blob, "preco", "energia", "empresa", "folha", "divida", "caixa", "tribut"):
        s += 2
    if _has(blob, "quebrar", "quebradeira", "precificar", "tributar"):
        s += 2
    return s


def _score_brasilia(blob: str) -> int:
    s = 0
    if _has(blob, "lula", "lulinha", "planalto", "palanque", "campanha", "flavio bolsonaro"):
        s += 3
    if _has(blob, "pesquisa eleitoral", "jornal nacional") or re.search(r"(?<!\w)jn(?!\w)", blob):
        s += 3
    if _has(blob, "flavio", "eleitoral", "urna", "aliado"):
        s += 1
    return s


def _score_mundo(blob: str) -> int:
    exterior = _has(
        blob,
        "china",
        "tarifa",
        "nepal",
        "washington",
        "espanha",
        "eua",
        "estados unidos",
        "laudo",
        "justica estrangeira",
        "estrangeir",
    )
    custo_aqui = _has(blob, "brasil", "preco", "empresa", "processo", "cnpj", "imposto", "tarifa")
    if exterior and custo_aqui:
        return 4
    if exterior:
        return 1
    return 0


def _score_socialismo(blob: str) -> int:
    s = 0
    if _has(
        blob,
        "socialismo",
        "comunismo",
        "marx",
        "marxista",
        "plano quinquenal",
        "estatizacao",
        "povo no comando",
        "estado engenheiro",
    ):
        s += 4
    return s


STRONG = 3


def choose_playlists(title: str, description: str = "") -> PlaylistDecision:
    """1 playlist; 2 só se os ganchos forem igualmente fortes. Nunca 3+."""
    title_n = _fold(title)
    blob = _fold(f"{title} {description}")

    if _is_english_old(title, description):
        return PlaylistDecision((), "sem playlist — vídeo em inglês / ensaio sem gancho de data")
    if _is_historical_essay(title, description):
        return PlaylistDecision((), "sem playlist — ensaio histórico sem gancho de data")

    scores = {
        PL_JUIZES: _score_juizes(blob),
        PL_ECONOMIA: _score_economia(blob),
        PL_BRASILIA: _score_brasilia(blob),
        PL_MUNDO: _score_mundo(blob),
        PL_SOCIALISMO: _score_socialismo(blob),
    }

    # Empates documentados
    lobista_jn = _has(blob, "lobista") and _has(blob, "lula") and (
        _has(blob, "jornal nacional") or re.search(r"(?<!\w)jn(?!\w)", blob) or _has(blob, "fotos")
    )
    if lobista_jn and not _has(blob, "inquerito"):
        return PlaylistDecision((PL_BRASILIA,), "Brasília no relógio — lobista/Lula/JN")

    lula_preco_tse = _has(blob, "lula") and _has(blob, "preco") and _has(blob, "tse")
    if lula_preco_tse:
        return PlaylistDecision(
            (PL_ECONOMIA, PL_JUIZES),
            "Economia no recibo + Juízes e o gabinete — preço/TSE",
        )

    estatal_rec = _has(blob, "recuperacao judicial") and (
        _has(blob, "estatal", "governo") or _has(blob, "empresa")
    )
    if estatal_rec:
        names = [PL_ECONOMIA]
        if _has(title_n, "lula") or _has(title_n, "presidente"):
            names.append(PL_BRASILIA)
        return PlaylistDecision(tuple(names[:2]), "Economia no recibo — empresa/recuperação")

    imig = _has(blob, "imigracao", "imigrante", "imigrantes") and _has(blob, "sc", "santa catarina")
    if imig:
        if _has(title_n, "fluxo", "fronteira", "mundo") or _score_mundo(title_n) >= STRONG:
            return PlaylistDecision((PL_MUNDO,), "O mundo que cobra o Brasil — fluxo")
        return PlaylistDecision((PL_ECONOMIA,), "Economia no recibo — custo local")

    strong = [(name, scores[name]) for name in OFFICIAL_PLAYLISTS if scores[name] >= STRONG]
    if not strong:
        return PlaylistDecision((), "sem playlist — título fora das cinco")

    strong.sort(key=lambda x: (-x[1], OFFICIAL_PLAYLISTS.index(x[0])))
    top_name, top_score = strong[0]
    if len(strong) >= 2 and strong[1][1] == top_score:
        two = (strong[0][0], strong[1][0])
        return PlaylistDecision(two, f"{two[0]} + {two[1]} — ganchos iguais")
    return PlaylistDecision((top_name,), top_name)


def video_resource_body(
    title: str,
    description: str,
    tags: list[str],
    privacy: str,
    *,
    category_id: str | None = None,
    recording_date: str | None = None,
    kind: str = "news",
) -> dict:
    cat = choose_category(title, description, kind=kind, override=category_id)
    return {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": cat,
            "defaultLanguage": TITLE_LANGUAGE,
            "defaultAudioLanguage": AUDIO_LANGUAGE,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": True,
        },
        "recordingDetails": {
            "recordingDate": recording_date or recording_date_iso(),
        },
    }
