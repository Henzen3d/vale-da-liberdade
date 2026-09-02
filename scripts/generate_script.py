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
        "style": "anarcocapitalista provocador",
        "voice": "Charon",
        "guidelines": [
            "Anti-estado: rejeita soluções estatais, destaca coerção, questiona burocracia",
            "Defende mercado livre, liberdade individual, descentralização; imposto é roubo",
            "Nunca elogia eficiência do Estado; expõe custos ocultos e incentivos perversos",
            "Tom irônico, cético, provocador — como quem desafia o status quo",
            "Foca no indivíduo, na liberdade, na responsabilidade pessoal",
            "Usa metáforas libertárias: 'monopólio da violência', 'imposto é roubo', 'burocracia parasitária'",
            "Frases curtas, diretas, às vezes sarcásticas"
        ]
    },
    "Ricardo": {
        "style": "comentarista dinâmico, enérgico e vibrante de rádio ao vivo",
        "voice": "Kore",
        "guidelines": [
            "Extremamente animado, dinâmico, vibrante e caloroso; energia contagiante de rádio ao vivo, com ritmo ágil e presença de estúdio",
            "PROIBIDO terminantemente usar linguagem ou tom de assessoria de imprensa, nota oficial ou diário oficial burocrático",
            "Narrativa quente, no nível da rua e do cidadão comum: foca no impacto real no bolso, no cotidiano e nas consequências práticas",
            "Reações imediatas, espontâneas e expressivas; usa interjeições e ganchos conversacionais vivos ('Peraí!', 'Olha isso!', 'Olha só o absurdo!', 'Presta atenção nisso!')",
            "Usa perguntas retóricas afiadas e humor vivo/indignação lúcida para dar ritmo e dinamismo ('E aí, quem paga a conta?', 'Faz algum sentido isso?', 'Cadê a solução?')",
            "Contraponto inteligente baseado em dados concretos, fatos econômicos e bom senso prático, sem nunca soar apático, monótono ou institucional",
            "Quebra números e fatos em frases curtas e diretas (reação imediata → fato/número concreto → consequência prática no chão da cidade)",
            "Pausas dramáticas curtas antes de números-chave e abertura de cada fala com energia elevada para puxar o diálogo"
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
3. **QUADROS TEMÁTICOS** (ordem fixa abaixo). Se um quadro contiver múltiplas notícias, elas **NUNCA** devem ser aglomeradas em uma única fala ou apresentadas em sequência sem debate. Adote o fluxo de **Bate-Volta Individual por Notícia**:
   - Para **cada** notícia no quadro:
     - O locutor da vez apresenta a notícia com seus fatos e números concretos.
     - Esse mesmo locutor faz um comentário opinativo rápido (estilo característico).
     - O outro locutor responde imediatamente com o contraponto/análise.
     - O primeiro locutor faz uma réplica curta (fechando o minidebate daquela notícia).
     - Passam para a próxima notícia reagindo ao último ponto (eco de número/fato) — SEM muleta forçada.
   - NÃO use "Ainda nessa área..." / "Ainda sobre..." (soa telejornal).
   - NÃO comece toda fala com "Vai daí", "Segura essa", "Pois é e tem mais", "Peraí".
   - Transição entre notícias = reação natural ("Seis acidentes?" / "E o pior:") no máximo 1x a cada 2–3 notícias.
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
- NUNCA escreva Turguniev (nem variantes). O apresentador é Peter Albuquerque; troque essa palavra por Albuquerque. Essa forma nunca vai para o áudio
- Especificidade extrema: R$, %, datas, nomes, números exatos
- Voz ativa sempre ("Câmara aprova" não "É aprovado")
- Peter SEMPRE traz ângulo libertário/anti-estado — mas NÃO em toda fala com a mesma fórmula (ver 7.1)
- Ricardo SEMPRE traz contraponto dinâmico, caloroso e baseado em fatos/dados reais, com reações imediatas, interjeições e linguagem viva de rua (PROIBIDO tom de nota oficial ou leitor de diário oficial)
- Diálogo orgânico e vivo: Peter e Ricardo conversam como radialistas reais no estúdio — reagem com espontaneidade, interrompem com naturalidade, discordam com vivacidade e humor, sem leituras engessadas ou monótonas. Chamar o outro pelo nome COM PARCIMÔNIA (sem vírgula: "estado Peter", não "estado, Peter")
- **DEBATE POR NOTÍCIA (PROIBIDO MONÓLOGOS)**: Se houver mais de uma notícia em um quadro, divida o quadro em ciclos individuais de apresentação-comentário-contraponto-réplica para cada notícia. Não junte tudo no início do quadro nem faça exposições longas sem interrupção. O ouvinte deve perceber um diálogo dinâmico e constante.
- Target: ~2000-2500 palavras total (~15 min de áudio)
- NÃO use frases genéricas como "Isso mesmo", "Exatamente", "E para detalhar:"
- Transições entre quadros devem ser variadas — nunca repetir a mesma frase de transição
- Quadros Brasil e Mundo devem ser CONCISOS (máx. 3 falas cada, não ofuscar local)

=== 7.1 DINÂMICA CONVERSACIONAL (OBRIGATÓRIO — substitui muletas de telejornal) ===
1. Proibido abrir fala com formato de telejornal.
   Nunca começar uma fala com "Na segurança pública...", "Ainda sobre...", "E em [cidade]...", "No quadro X...".
   Também proibido: "Na saúde...", "Na educação...", "Na política...", "Indo para...", "Na mesma segunda-feira...",
   "E fechando o quadro...", "Vamos à segurança...".
   Essas são muletas de apresentador formal. A notícia deve entrar naturalmente dentro da fala, não como manchete lida.

2. Toda fala (exceto a primeira de cada quadro) precisa reagir à fala anterior antes de emendar o próprio ponto.
   Regra prática: pegue uma palavra, número ou ideia específica que o outro acabou de dizer e repita/questione/ironize
   sobre ela antes de introduzir argumento novo. Proibido simplesmente trocar de assunto com uma crítica genérica ao Estado.
   Exemplo ruim: "Estrada pública, manutenção pública, resultado público."
   Exemplo bom: "Setenta metros de fiação, você disse? Sumiu setenta metros e ninguém viu nada?"

3. Limite rígido: 2-3 frases curtas por fala, nunca 4+.
   Se uma fala passar de 3 frases, cortar. Ritmo de podcast é troca rápida, não parágrafo de opinião.

4. Variar a reação do Peter — proibido repetir sempre a fórmula "fato → crítica ao Estado".
   Alternar entre: pergunta retórica, interrupção ("Espera, deixa eu entender..."), ironia seca, incredulidade,
   ou concordância parcial antes de discordar. Nem toda fala do Peter precisa terminar em tese anti-Estado —
   variedade é mais crível que repetição.

5. Trocas por notícia: 3 a 5, mas curtas — nunca infladas pra bater cota.
   Se a notícia é simples, 3 trocas curtas bastam. Não esticar fala pra parecer "completo".
   Densidade de informação por fala deve ser baixa; ritmo de conversa, não de relatório.

6. Transições: RARAS e naturais — proibido spam de muleta.
   - NÃO repetir "Vai daí", "Agora segura essa", "Pois é e tem mais", "Peraí" em falas seguidas.
   - No máximo ~1 expressão dessas por quadro (não por fala).
   - Preferir reação ao conteúdo: ecoar número/fato ("Duzentos mil?" / "Treze anos?") em vez de muleta vazia.
   - PROIBIDO empilhar: "Olha, vai daí…", "Olha, Ricardo: vai daí…", "Pois é, e tem mais: peter,".
   - Lista de reserva (usar no máx. 1x/quadro, se couber): "E o pior:", "Sabe o que mais?", "Espera aí —".

7. Chamar o outro pelo nome — COM PARCIMÔNIA (voz única no áudio).
   - Meta: ~1 chamada a cada 5–6 falas (não em toda fala).
   - SEM vírgula antes/depois do nome (TTS pausa e fica artificial):
     Bom:  "Isso é falha do Estado Peter." / "Peter você viu os números?"
     Ruim: "Isso é falha do Estado, Peter." / "Peter, você viu os números?"
   - Preferir o nome no meio/fim da frase, não só no começo.
   - Não empilhar "Olha Peter" / "Mas Ricardo" em toda réplica.

O validador automático (`validate_naturalidade`) REPROVA aberturas de telejornal, falas com 4+ frases
e EXCESSO de muletas de transição.

=== EXEMPLO BOM (imitate este ritmo — 1 notícia, 4 trocas curtas) ===
Ricardo: Um jovem de 21 anos foi soterrado no Tribess por volta das 8h25.
Peter: Vinte e um anos, Ricardo. Colega puxando gente da terra enquanto a fiscalização olha papel.
Ricardo: Espera, deixa eu entender: a vítima já estava fora quando o bombeiro chegou?
Peter: Exato. Sinal vital estável — e ninguém tinha olhado o talude.
Ricardo: No mesmo dia, seis acidentes com moto em Blumenau.
Peter: Seis? Pista de eleição, não de trânsito.

=== EXEMPLO RUIM (NÃO faça assim) ===
Ricardo: Na segurança pública, um trabalhador foi soterrado e ainda sobre acidentes...
Peter: Vai daí… o Estado falhou. Agora segura essa: o Estado falhou de novo.
Ricardo: Pois é, e tem mais: peter, o Estado...
Peter: Olha, Ricardo: vai daí… justiça feita.

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


def _turn_line(speaker: str, texto: str) -> str:
    """Uma fala no MD, sem prefixo duplicado 'Peter: Peter: ...'."""
    clean = re.sub(rf"^{re.escape(speaker)}:\s*", "", (texto or "").strip(), flags=re.I)
    return f"{speaker}: {clean}"


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
        lines.append(_turn_line(item.speaker, item.texto))
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
        lines.append(_turn_line(item.speaker, item.texto))
        lines.append("")
        previous_quadro = current_quadro

    lines.append("")
    lines.append("")
    # Fechamento
    lines.append("[QUADRO: FECHAMENTO EDITORIAL]")
    lines.append("")
    for item in roteiro.fechamento:
        lines.append(_turn_line(item.speaker, item.texto))
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