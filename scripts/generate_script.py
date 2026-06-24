#!/usr/bin/env python3
"""
Gerador/Renderer de Roteiro — Web Jornal Vale da Liberdade.

Este módulo fornece:
  - Contratos de dados (Pydantic): RoteiroItem, RoteiroCompleto — preservados
  - parse_raw(): extrai notícias estruturadas do raw-{date}.md
  - format_script(): converte RoteiroCompleto (Python obj) em markdown final
  - render_from_json(path): lê roteiro-{date}.json gerado pelo Hermes e emite {date}.md
  - build_script_prompt(): constrói o prompt canônico para o Hermes Agent gerar o JSON

Fluxo:
  Hermes Agent lê raw-{date}.md
      → gera roteiro-{date}.json (seguindo RoteiroCompleto schema)
  pipeline.py cmd_process chama render_from_json(roteiro-{date}.json)
      → emite episodes/{date}.md
  Se roteiro-{date}.json não existir → cmd_process falha alto (exit 3), NÃO usa boilerplate.
"""

import json
import re
import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

EPISODES_DIR = PROJECT_ROOT / "episodes"

# ---------------------------------------------------------------------------
# Personas (conforme SKILL.md) — mantidas para build_script_prompt
# ---------------------------------------------------------------------------

PERSONAS = {
    "Peter": {
        "style": "libertário provocador",
        "voice": "Charon",
        "guidelines": [
            "Anti-estado: rejeita soluções estatais, destaca coerção, questiona burocracia",
            "Nunca elogia eficiência do Estado; expõe custos ocultos e incentivos perversos",
            "Tom irônico, cético, provocador — como quem desafia o status quo",
            "Foca no indivíduo, na liberdade, na responsabilidade pessoal",
            "Usa metáforas libertárias: 'monopólio da violência', 'imposto é roubo', 'burocracia parasitária'",
            "Frases curtas, diretas, às vezes sarcásticas"
        ]
    },
    "Ricardo": {
        "style": "analista pragmático",
        "voice": "Schedar",
        "guidelines": [
            "Contraponto racional, institucional, baseado em dados e evidências",
            "Reconhece problemas mas contextualiza com perspectivas práticas",
            "Não defende o Estado cegamente, mas evita anarquismo ingenuamente",
            "Tom calmo, medido, equilibrado — analista sério",
            "Traz nuances: 'o problema real é X', 'dados mostram Y', 'historicamente Z'",
            "Frases completas, articuladas, ponderadas"
        ]
    }
}

# Quadros fixos (slug, nome, locutor de abertura)
# Fase 3: Brasil e Mundo adicionados após quadros locais
QUADROS = [
    ("seguranca",  "SEGURANÇA PÚBLICA",                  "Ricardo"),
    ("saude",      "SAÚDE",                               "Ricardo"),
    ("educacao",   "EDUCAÇÃO",                            "Peter"),
    ("politica",   "POLÍTICA E ADMINISTRAÇÃO PÚBLICA",    "Peter"),
    ("esportes",   "ESPORTES E INTERESSE COMUNITÁRIO",    "Ricardo"),
    ("brasil",     "BRASIL",                              "Ricardo"),   # Fase 3
    ("mundo",      "MUNDO",                               "Peter"),     # Fase 3
    ("rapidinhas", "RAPIDINHAS DA LOUCURA ESTATAL",       "Peter"),
]


# ---------------------------------------------------------------------------
# Schemas Pydantic — contratos de dados preservados
# ---------------------------------------------------------------------------

class RoteiroItem(BaseModel):
    quadro: str
    speaker: str
    texto: str


class RoteiroCompleto(BaseModel):
    manchetes: List[str]
    introducao: List[RoteiroItem]
    quadros: List[RoteiroItem]
    fechamento: List[RoteiroItem]


# ---------------------------------------------------------------------------
# Parsing do raw-{date}.md
# ---------------------------------------------------------------------------

def load_raw(date: str) -> str:
    raw_path = EPISODES_DIR / f"raw-{date}.md"
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw não encontrado: {raw_path}")
    return raw_path.read_text(encoding="utf-8")


def parse_raw(raw_text: str) -> dict:
    """Extrai notícias por quadro do arquivo raw."""
    quadro_pattern = r"### QUADRO: ([^\n]+)\n(.*?)(?=\n### QUADRO:|\Z)"
    matches = re.findall(quadro_pattern, raw_text, re.S)

    result = {}
    for cat_name, body in matches:
        cat_name = cat_name.strip()
        items = []
        # Cada notícia começa com "#### • "
        news_blocks = re.split(r"\n#### • ", body)
        for block in news_blocks:
            if not block.strip():
                continue
            title_match = re.match(r"([^\n]+)", block)
            title = title_match.group(1).strip() if title_match else ""

            summary_match = re.search(r"- \*\*Resumo\*\*: ([^\n]+)", block)
            summary = summary_match.group(1).strip() if summary_match else ""

            key_points = re.findall(r"    1\. ([^\n]+)", block)

            url_match = re.search(r"- \*\*URL\*\*: \[([^\]]+)\]\([^)]+\)", block)
            url = url_match.group(1).strip() if url_match else ""

            if title:
                items.append({
                    "title": title,
                    "summary": summary,
                    "key_points": key_points,
                    "url": url
                })
        if items:
            result[cat_name] = items
    return result


# ---------------------------------------------------------------------------
# Prompt canônico para o Hermes Agent
# ---------------------------------------------------------------------------

def build_script_prompt(date: str, parsed_news: dict) -> str:
    """
    Constrói o prompt canônico que o Hermes Agent deve usar para gerar
    o roteiro-{date}.json. Este prompt é exposto para uso do Agente e
    não é enviado a nenhuma API externa por este módulo.
    """
    news_json = json.dumps(parsed_news, ensure_ascii=False, indent=2)

    persona_peter = PERSONAS["Peter"]
    persona_ricardo = PERSONAS["Ricardo"]

    return f"""Você é o roteirista-chefe do podcast "Webjornal Vale da Liberdade".
Sua tarefa: escrever o roteiro COMPLETO do episódio de {date} a partir das notícias curadas abaixo.

=== PERSONAGENS (OBRIGATÓRIO SEGUIR) ===

**PETER** — {persona_peter['style'].upper()} (voz: {persona_peter['voice']})
{chr(10).join(f"- {g}" for g in persona_peter['guidelines'])}

**RICARDO** — {persona_ricardo['style'].upper()} (voz: {persona_ricardo['voice']})
{chr(10).join(f"- {g}" for g in persona_ricardo['guidelines'])}

=== ESTRUTURA DO ROTEIRO ===

1. **MANCHETES** (5-6 manchetes curtas de impacto, uma por linha, sem locutor)
2. **INTRODUÇÃO EDITORIAL** — cold open: gancho de impacto ≤30s, NÃO use saudação temporal
   (Peter abre com gancho forte, Ricardo reage, Peter apresenta o roteiro do dia)
3. **QUADROS TEMÁTICOS** (ordem fixa abaixo, cada um com:
   - Transição criativa DO quadro anterior (não genérica)
   - Locutor designado apresenta a notícia principal com dados concretos
   - Outro locutor faz análise/comentário no seu estilo característico
   - Primeiro locutor dá réplica final e fecha o quadro)
4. **FECHAMENTO EDITORIAL** (Peter frase provocativa, Ricardo reflexão/CTA)

ORDEM DOS QUADROS E LOCUTOR DE ABERTURA:
- SEGURANÇA PÚBLICA → Ricardo abre
- SAÚDE → Ricardo abre
- EDUCAÇÃO → Peter abre
- POLÍTICA E ADMINISTRAÇÃO PÚBLICA → Peter abre
- ESPORTES E INTERESSE COMUNITÁRIO → Ricardo abre
- BRASIL (1 notícia nacional concisa) → Ricardo abre
- MUNDO (1 notícia internacional concisa) → Peter abre
- RAPIDINHAS DA LOUCURA ESTATAL → Peter abre

=== REGRAS DE OURO ===
- SEMPRE prefixe falas com "Peter:" ou "Ricardo:" (exato, com dois-pontos)
- NÃO use saudação temporal (bom dia, boa tarde, etc.)
- NÃO invente dados — use apenas o que está nas notícias abaixo
- Especificidade extrema: R$, %, datas, nomes, números exatos
- Voz ativa sempre ("Câmara aprova" não "É aprovado")
- Peter SEMPRE traz ângulo libertário/anti-estado
- Ricardo SEMPRE traz contraponto racional/dados
- Diálogo natural: eles se interrompem, completam, discordam
- Target: ~2000-2500 palavras total (~15 min de áudio)
- NÃO use frases genéricas como "Isso mesmo", "Exatamente", "E para detalhar:"
- Transições entre quadros devem ser variadas — nunca repetir a mesma frase de transição
- Quadros Brasil e Mundo devem ser CONCISOS (máx. 3 falas cada, não ofuscar local)

=== NOTÍCIAS CURADAS POR QUADRO ===
{news_json}

=== FORMATO DE SAÍDA (JSON) ===
Retorne EXATAMENTE este schema:
{{
  "manchetes": ["manchete 1", "manchete 2", "manchete 3", "manchete 4", "manchete 5"],
  "introducao": [
    {{"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter", "texto": "..."}},
    {{"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Ricardo", "texto": "..."}},
    {{"quadro": "INTRODUÇÃO EDITORIAL", "speaker": "Peter", "texto": "..."}}
  ],
  "quadros": [
    {{"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "texto": "..."}},
    {{"quadro": "SEGURANÇA PÚBLICA", "speaker": "Peter", "texto": "..."}},
    {{"quadro": "SEGURANÇA PÚBLICA", "speaker": "Ricardo", "texto": "..."}},
    ...
  ],
  "fechamento": [
    {{"quadro": "FECHAMENTO EDITORIAL", "speaker": "Peter", "texto": "..."}},
    {{"quadro": "FECHAMENTO EDITORIAL", "speaker": "Ricardo", "texto": "..."}}
  ]
}}

IMPORTANTE: No campo "texto", escreva APENAS o que o locutor fala, SEM o prefixo "Peter:" ou "Ricardo:" (o schema já tem o speaker).
O roteiro final será gerado pelo renderer `render_from_json()` e validado pelo `validate_episode()`.
"""


# ---------------------------------------------------------------------------
# Renderer: roteiro-{date}.json → {date}.md
# ---------------------------------------------------------------------------

def render_from_json(json_path: Path) -> str:
    """
    Lê roteiro-{date}.json gerado pelo Hermes Agent e renderiza em markdown.

    O `pipeline.py cmd_process` chama esta função; se o JSON não existir, falha alto (exit 3).

    Args:
        json_path: Caminho para o arquivo roteiro-{date}.json.

    Returns:
        String com o roteiro em markdown, pronto para ser salvo em {date}.md.
    """
    if not json_path.exists():
        raise FileNotFoundError(
            f"roteiro JSON não encontrado: {json_path}\n"
            f"Ação: execute o Hermes Agent para gerar este arquivo antes de 'pipeline.py process'.\n"
            "Contrato documentado em ARCHITECTURE.md: `episodes/roteiro-{date}.json`."
        )

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    roteiro = RoteiroCompleto(**data)
    # Extrair data do nome do arquivo (roteiro-2026-06-20.json)
    date_str = json_path.stem.replace("roteiro-", "")
    return format_script(date_str, roteiro)


def format_script(date: str, roteiro: RoteiroCompleto) -> str:
    """Formata o roteiro para markdown final — preservado como contrato de formatação."""
    lines = [
        "# WEBJORNAL VALE DA LIBERDADE",
        f"## Edição: {date} | Episódio ?",
        "",
        "---",
        "## 📋 MANCHETES DO DIA",
        "---",
    ]

    for m in roteiro.manchetes[:6]:
        lines.append(f"• {m}")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Introdução
    lines.append("### INTRODUÇÃO EDITORIAL")
    lines.append("")
    for item in roteiro.introducao:
        lines.append(f"{item.speaker}: {item.texto}")
    lines.append("")
    lines.append("")

    # Quadros
    previous_quadro = None
    for item in roteiro.quadros:
        current_quadro = item.quadro
        is_quadro_change = current_quadro != previous_quadro
        if is_quadro_change and previous_quadro is not None:
            lines.append("")
            lines.append("")
        if is_quadro_change:
            lines.append("")
            lines.append(f"[QUADRO: {current_quadro}]")
            lines.append("")
        lines.append(f"{item.speaker}: {item.texto}")
        lines.append("")
        previous_quadro = current_quadro

    lines.append("")
    lines.append("")
    # Fechamento
    lines.append("[QUADRO: FECHAMENTO EDITORIAL]")
    lines.append("")
    for item in roteiro.fechamento:
        lines.append(f"{item.speaker}: {item.texto}")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Wrapper de compatibilidade para pipeline.py (usa generate_script como antes)
# ---------------------------------------------------------------------------

def generate_script(date: str) -> RoteiroCompleto:
    """
    Tenta carregar roteiro-{date}.json do Hermes Agent.
    Falha com FileNotFoundError se o JSON não existir (pipeline.py trata com exit 3).

    Este wrapper mantém a assinatura anterior para compatibilidade com pipeline.py.
    """
    json_path = EPISODES_DIR / f"roteiro-{date}.json"
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return RoteiroCompleto(**data)

    # JSON não existe → levantar para que pipeline.py trate com falha alta
    raise FileNotFoundError(
        f"roteiro-{date}.json não encontrado em {EPISODES_DIR}.\n"
        f"Ação necessária: o Hermes Agent deve ler raw-{date}.md e gerar roteiro-{date}.json\n"
        f"antes de executar 'pipeline.py process --date {date}'.\n"
        f"Prompt canônico disponível em: generate_script.build_script_prompt()\n"
        "Contrato documentado em ARCHITECTURE.md: `episodes/roteiro-{date}.json`."
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Renderer de roteiro JSON→MD para Web Jornal Vale da Liberdade"
    )
    parser.add_argument("--date", required=True, help="Data YYYY-MM-DD")
    parser.add_argument("--json", help="Caminho do roteiro JSON (padrão: episodes/roteiro-{date}.json)")
    parser.add_argument("--output", help="Arquivo de saída (padrão: episodes/{date}.md)")
    parser.add_argument("--print-prompt", action="store_true", help="Imprime o prompt canônico para o Hermes Agent")
    args = parser.parse_args()

    if args.print_prompt:
        try:
            raw_text = load_raw(args.date)
            parsed = parse_raw(raw_text)
        except FileNotFoundError:
            parsed = {"[sem raw disponível]": []}
        print(build_script_prompt(args.date, parsed))
        sys.exit(0)

    json_path = Path(args.json) if args.json else EPISODES_DIR / f"roteiro-{args.date}.json"

    print(f"🎙️  Renderizando roteiro de {json_path}...")

    try:
        formatted = render_from_json(json_path)

        out_path = Path(args.output) if args.output else EPISODES_DIR / f"{args.date}.md"
        out_path.write_text(formatted, encoding="utf-8")

        word_count = len(formatted.split())
        print(f"✅ Roteiro renderizado: {out_path} ({word_count} palavras)")

    except FileNotFoundError as e:
        print(f"❌ FALHA: {e}")
        sys.exit(3)
    except Exception as e:
        print(f"❌ Erro ao renderizar roteiro: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()