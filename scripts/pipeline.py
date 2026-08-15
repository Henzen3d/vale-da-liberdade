#!/usr/bin/env python3
"""
Pipeline unificado do Web Jornal Vale da Liberdade.

Orquestra o fluxo diário de produção do podcast:
1. init — coleta notícias → raw-{date}.md (+ template md se necessário)
2. roteiro JSON — generate_roteiro_llm.py → roteiro-{date}.json
3. process — renderiza {date}.md + TTS + manchetes + metadados
4. validate — checklist de qualidade
5. audio — TTS multi-locutor
6. archive — atualiza índice

Uso:
    # Criar template / coletar notícias
    python pipeline.py init --date 2026-06-16

    # Processar roteiro finalizado (gerar TTS, manchetes, metadados)
    python pipeline.py process --date 2026-06-15

    # Validar um episódio
    python pipeline.py validate --date 2026-06-15

    # Pipeline completo de ponta a ponta (init → JSON → process → audio)
    python pipeline.py full --date 2026-06-15

    # Gerar apenas o áudio a partir do TTS já processado
    python pipeline.py audio --date 2026-06-15
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Adicionar diretório de scripts ao path para imports
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

# Carregar variáveis de ambiente do .env do projeto
from dotenv import load_dotenv
load_dotenv(dotenv_path=PROJECT_ROOT / ".env")

from tts_preprocessor import (
    extract_manchetes,
    generate_metadata,
    preprocess_for_tts,
    validate_episode,
)

# Imports para automação da coleta de notícias (Fase 2)
from news_collector import collect_all_news, load_cache, save_cache, load_config
from ai_news_filter import filter_and_categorize_news
from generate_script import generate_script, format_script, render_from_json

try:
    from x_collector import consume_x_tweets_for_pipeline
    _X_COLLECTOR_AVAILABLE = True
except Exception as e:
    # Falha silenciosa para evitar interrupções no pipeline caso dependências do X falhem
    _X_COLLECTOR_AVAILABLE = False
    consume_x_tweets_for_pipeline = None  # type: ignore

try:
    from generate_roteiro_llm import generate_roteiro_json, _validate_roteiro
    _ROTEIRO_LLM_AVAILABLE = True
    _ROTEIRO_LLM_IMPORT_ERROR = None
except Exception as e:
    _ROTEIRO_LLM_AVAILABLE = False
    _ROTEIRO_LLM_IMPORT_ERROR = e
    generate_roteiro_json = None  # type: ignore
    _validate_roteiro = None  # type: ignore

def format_raw_markdown(date, sources_used, selected_news):
    categories_map = {
        "seguranca": "SEGURANÇA PÚBLICA",
        "saude": "SAÚDE",
        "educacao": "EDUCAÇÃO",
        "politica": "POLÍTICA E ADMINISTRAÇÃO PÚBLICA",
        "esportes": "ESPORTES E INTERESSE COMUNITÁRIO",
        "brasil": "BRASIL",              # Fase 3.1 — notícia nacional (1 por edição)
        "mundo": "MUNDO",               # Fase 3.1 — notícia internacional (1 por edição)
        "rapidinhas": "RAPIDINHAS DA LOUCURA ESTATAL"
    }

    lines = [
        f"# Web Jornal Vale da Liberdade — RAW — {date}",
        "",
        f"> Coleta automatizada concluída com sucesso.",
        f"> Fontes com notícias: {', '.join(sources_used)}",
        f"> Total de notícias curadas: {len(selected_news)}",
        "",
        "---",
        ""
    ]

    grouped = {cat: [] for cat in categories_map.keys()}
    for item in selected_news:
        cat = item.get("category", "politica")
        if cat in grouped:
            grouped[cat].append(item)
        else:
            grouped.setdefault(cat, []).append(item)

    lines.append("## 📋 NOTÍCIAS CURADAS POR QUADRO")
    lines.append("")

    for cat_id, cat_name in categories_map.items():
        items = grouped.get(cat_id, [])
        if not items:
            continue

        lines.append(f"### QUADRO: {cat_name}")
        lines.append("")

        # Fase 2.3 — notícias breaking primeiro
        items_sorted = sorted(
            items,
            key=lambda x: (x.get("_is_breaking", False), x.get("quality_score", 3), x.get("_relevance", 0)),
            reverse=True,
        )

        for item in items_sorted:
            score_stars = "⭐" * item.get("quality_score", 3)
            title = item.get("title", "")
            if item.get("_is_breaking"):
                title = f"[BREAKING] {title}"
            lines.append(f"#### • {title}")
            lines.append(f"  - **URL**: [{item.get('url')}]({item.get('url')})")
            lines.append(f"  - **Score**: {score_stars} ({item.get('quality_score')}/5)")
            lines.append(f"  - **Resumo**: {item.get('summary')}")
            if item.get("key_points"):
                lines.append(f"  - **Pontos Chave**:")
                for pt in item.get("key_points"):
                    lines.append(f"    1. {pt}")
            lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)


def add_selected_to_cache(selected_news):
    cache = load_cache()
    url_cache = cache.setdefault("url_cache", {})
    now_str = datetime.now().isoformat()
    for item in selected_news:
        url = item.get("url")
        if url:
            url_cache[url] = now_str
    save_cache(cache)

# ---------------------------------------------------------------------------
# Diretórios
# ---------------------------------------------------------------------------

EPISODES_DIR = PROJECT_ROOT / "episodes"
AUDIO_DIR = PROJECT_ROOT / "audio"
ARCHIVE_DIR = PROJECT_ROOT / "archive"
SOURCES_DIR = PROJECT_ROOT / "sources"

# Fontes de notícias para o template raw
NEWS_SOURCES = [
    "https://ndmais.com.br/blumenau/",
    "https://oblumenauense.com.br/",
    "https://altovaleagora.com.br/",
    "https://www.informeblumenau.com/",
    "https://ajnoticias.com.br/",
    "https://www.nsctotal.com.br/",
    "https://altovalenoticias.com.br/",
    "https://www.jatv.com.br/",
    "https://blogdojaime.com.br/",
    "https://mesorregional.com.br/",
    "https://gcd.com.br/",
]


def get_date_str(args_date: str | None = None) -> str:
    """Retorna a data no formato YYYY-MM-DD."""
    if args_date:
        # Validar formato
        try:
            datetime.strptime(args_date, "%Y-%m-%d")
        except ValueError:
            print(f"FALHA: formato de data inválido '{args_date}'. Use YYYY-MM-DD.")
            sys.exit(2)
        return args_date
    return datetime.now().strftime("%Y-%m-%d")


def _raw_needs_collect(raw_path: Path) -> bool:
    """True se o raw não existe ou é placeholder/vazio (ex.: daily-collect.sh legado)."""
    if not raw_path.exists():
        return True
    try:
        text = raw_path.read_text(encoding="utf-8")
    except Exception:
        return True
    markers_empty = (
        "Extração automática indisponível",
        "Cole aqui o conteúdo",
        "template raw vazio",
        "Nenhuma notícia",
    )
    if any(m.lower() in text.lower() for m in markers_empty):
        return True
    # Raw real do collector tem blocos #### • e Resumo
    has_items = ("#### •" in text) or ("**Resumo**:" in text) or ("- **Resumo**:" in text)
    if not has_items:
        return True
    if len(text.split()) < 80:
        return True
    return False


def _is_roteiro_template(content: str) -> bool:
    """Detecta md ainda em template / esqueleto (precisa render a partir do JSON)."""
    return (
        "[notícia]" in content
        or "[frase de impacto" in content
        or "[reação/complemento" in content
        or "Confira agora os destaques do dia" in content
        or len(content.split()) < 500
    )


def _run_news_collection(date: str, hours: int, raw_path: Path) -> None:
    """Executa coleta + filtro e grava raw-{date}.md (ou fallback)."""
    print(f"🚀 Iniciando coleta automática de notícias para {date} (janela: {hours}h)...")
    try:
        raw_articles = collect_all_news(hours=hours)
        if _X_COLLECTOR_AVAILABLE:
            try:
                tweets = consume_x_tweets_for_pipeline()
                if tweets:
                    print(f"📱 Mesclando {len(tweets)} tweets do X na lista de candidatos.")
                    raw_articles.extend(tweets)
            except Exception as ex_err:
                print(f"⚠️  Aviso: Falha ao mesclar tweets do X (o processo continuará): {ex_err}")
        if raw_articles:
            selected_news = filter_and_categorize_news(raw_articles)
            if selected_news:
                config = load_config()
                sources_map = {s["id"]: s["name"] for s in config.get("sources", [])}
                cache = load_cache()
                last_run_sources = cache.get("last_run", {}).get("sources_used", [])
                sources_used_names = [sources_map.get(sid, sid) for sid in last_run_sources]

                raw_content = format_raw_markdown(date, sources_used_names, selected_news)
                raw_path.write_text(raw_content, encoding="utf-8")
                print(f"✅ Raw automatizado criado com {len(selected_news)} notícias em {raw_path}")
                add_selected_to_cache(selected_news)
            else:
                print("⚠️  Nenhuma notícia selecionada pelo filtro de IA. Criando template raw vazio...")
                _create_fallback_raw(raw_path, date)
        else:
            print("⚠️  Nenhuma notícia recente encontrada nas fontes. Criando template raw vazio...")
            _create_fallback_raw(raw_path, date)
    except Exception as e:
        print(f"❌ Erro durante a coleta automática ({e}). Criando template raw vazio...")
        _create_fallback_raw(raw_path, date)


def cmd_init(date: str, collect: bool = True, hours: int = 48):
    """Cria templates para um novo dia de produção com coleta automática de notícias opcional."""
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Criar ou preencher o raw (recoleta se for placeholder legado)
    raw_path = EPISODES_DIR / f"raw-{date}.md"
    if collect and _raw_needs_collect(raw_path):
        if raw_path.exists():
            print(f"⚠️  Raw existe mas está vazio/placeholder — recoleta: {raw_path}")
        _run_news_collection(date, hours, raw_path)
    elif raw_path.exists():
        print(f"✅ Arquivo raw já populado: {raw_path}")
    else:
        print("ℹ️  Coleta automática desabilitada. Criando template raw vazio...")
        _create_fallback_raw(raw_path, date)

    # 2. Criar roteiro template (não sobrescreve conteúdo rico)
    roteiro_path = EPISODES_DIR / f"{date}.md"
    if roteiro_path.exists():
        current = roteiro_path.read_text(encoding="utf-8")
        if _is_roteiro_template(current):
            print(f"ℹ️  Roteiro existe mas ainda é template/esqueleto: {roteiro_path}")
        else:
            print(f"✅ Roteiro já existe com conteúdo rico: {roteiro_path}")
    else:
        template_path = EPISODES_DIR / "TEMPLATE.md"
        if template_path.exists():
            template = template_path.read_text(encoding="utf-8")
            content = template.replace("[DATA]", date).replace("[N]", "?")
        else:
            content = _default_template(date)
        roteiro_path.write_text(content, encoding="utf-8")
        print(f"✅ Roteiro template criado: {roteiro_path}")


def _create_fallback_raw(raw_path, date):
    """Cria o arquivo raw com placeholders caso a coleta falhe ou seja desabilitada."""
    sources_list = "\n".join(f"- {s}" for s in NEWS_SOURCES)
    raw_content = f"""# Web Jornal Vale da Liberdade — RAW — {date}

## Fontes
{sources_list}

## Resumo Fonte A (Manus)
<!-- Cole aqui o resumo consolidado do Manus -->

## Resumo Fonte B (Grok)
<!-- Cole aqui o resumo consolidado do Grok -->

## Notícias brutas
<!-- Cole aqui notícias adicionais não cobertas pelas fontes acima >"""
    raw_path.write_text(raw_content, encoding="utf-8")
    print(f"✅ Template raw vazio criado: {raw_path}")


def cmd_collect(date: str, hours: int = 48):
    """Executa a coleta de notícias avulsa e gera/sobrescreve o arquivo raw."""
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = EPISODES_DIR / f"raw-{date}.md"
    
    print(f"🚀 Executando coleta avulsa para {date} (janela: {hours}h)...")
    raw_articles = collect_all_news(hours=hours)
    if _X_COLLECTOR_AVAILABLE:
        try:
            tweets = consume_x_tweets_for_pipeline()
            if tweets:
                print(f"📱 Mesclando {len(tweets)} tweets do X na lista de candidatos.")
                raw_articles.extend(tweets)
        except Exception as ex_err:
            print(f"⚠️  Aviso: Falha ao mesclar tweets do X (o processo continuará): {ex_err}")
    if raw_articles:
        selected_news = filter_and_categorize_news(raw_articles)
        if selected_news:
            config = load_config()
            sources_map = {s["id"]: s["name"] for s in config.get("sources", [])}
            cache = load_cache()
            last_run_sources = cache.get("last_run", {}).get("sources_used", [])
            sources_used_names = [sources_map.get(sid, sid) for sid in last_run_sources]
           
            raw_content = format_raw_markdown(date, sources_used_names, selected_news)
            raw_path.write_text(raw_content, encoding="utf-8")
            print(f"✅ Arquivo raw atualizado: {raw_path} ({len(selected_news)} notícias)")
            add_selected_to_cache(selected_news)
        else:
            print("⚠️  Nenhuma notícia selecionada pelo filtro de IA.")
    else:
        print("⚠️  Nenhuma notícia coletada.")


def _default_template(date: str) -> str:
    """Template padrão caso TEMPLATE.md não exista."""
    return f"""# WEBJORNAL VALE DA LIBERDADE
## Edição: {date} | Episódio ?

---
## 📋 MANCHETES DO DIA
---
• [Manchete 1]
• [Manchete 2]
• [Manchete 3]
• [Manchete 4]
• [Manchete 5]
---

### INTRODUÇÃO EDITORIAL

Peter: [frase de impacto]
Ricardo: [reação/complemento]
Peter: [gancho para o primeiro quadro]

---
### QUADRO: SEGURANÇA PÚBLICA
---

Ricardo: Vamos agora para o quadro Segurança Pública. [notícia]
Peter: [análise libertária]
Ricardo: [contraponto racional]

---
### QUADRO: SAÚDE
---

Ricardo: Indo agora para o quadro Saúde... [notícia]
Peter: [análise libertária]
Ricardo: [contraponto racional]

---
### QUADRO: EDUCAÇÃO
---

Peter: Vamos para o quadro Educação. [notícia]
Ricardo: [contraponto racional]
Peter: [análise libertária]

---
### QUADRO: POLÍTICA E ADMINISTRAÇÃO PÚBLICA
---

Peter: Agora, política local no foco das atenções. [notícia]
Ricardo: [contraponto racional]
Peter: [análise libertária]

---
### QUADRO: ESPORTES E INTERESSE COMUNITÁRIO
---

Ricardo: No campo e fora dele, vamos ao quadro Esportes e Comunidade. [notícia]
Peter: [análise libertária]
Ricardo: [contraponto racional]

---
### QUADRO: RAPIDINHAS DA LOUCURA ESTATAL (opcional)
---

Peter: E agora, o nosso bloco favorito: Rapidinhas da Loucura Estatal.
Ricardo: [reação]

---
### FECHAMENTO EDITORIAL
---

Peter: [frase provocativa de encerramento]
Ricardo: [reflexão ou chamada à ação]
"""


def get_episode_number(date: str) -> int:
    """Calcula o número sequencial do episódio com base no archive/index.md."""
    index_path = ARCHIVE_DIR / "index.md"
    if not index_path.exists():
        return 1
    try:
        import re
        import bisect
        lines = index_path.read_text(encoding="utf-8").splitlines()
        dates = []
        for line in lines:
            line = line.strip()
            if line.startswith("- "):
                d = line.replace("- ", "").strip()
                if re.match(r"^\d{4}-\d{2}-\d{2}$", d):
                    dates.append(d)
        
        # Ordena as datas de forma única
        dates = sorted(list(set(dates)))
        
        # Se a data já está no index, o número é seu índice (1-based)
        if date in dates:
            return dates.index(date) + 1
        
        # Se a data não está no index, encontra sua posição de inserção
        pos = bisect.bisect_left(dates, date)
        return pos + 1
    except Exception:
        return 1


def ensure_roteiro_json(date: str, force: bool = False) -> Path:
    """Garante episodes/roteiro-{date}.json (gera via LLM se faltar/inválido)."""
    json_path = EPISODES_DIR / f"roteiro-{date}.json"
    if json_path.exists() and not force:
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            # Política C: só estrutura (_validate_roteiro). Naturalidade NÃO
            # dispara LLM — cmd_validate na etapa 4 ainda aborta áudio se houver ❌.
            if _ROTEIRO_LLM_AVAILABLE and _validate_roteiro is not None:
                _validate_roteiro(data)
            elif not (data.get("manchetes") and data.get("introducao") and data.get("quadros") and data.get("fechamento")):
                raise ValueError("JSON incompleto (chaves obrigatórias ausentes)")
            try:
                from naturalize_roteiro import polish_file
                polish_file(date)
            except Exception as exc:
                print(f"⚠️  polish naturalidade: {exc}")
            print(f"✅ roteiro JSON presente e estruturalmente válido: {json_path}")
            return json_path
        except Exception as exc:
            print(f"⚠️  roteiro JSON existente inválido ({exc}) — regenerando: {json_path}")

    if not _ROTEIRO_LLM_AVAILABLE:
        print(f"❌ Módulo generate_roteiro_llm indisponível: {_ROTEIRO_LLM_IMPORT_ERROR}")
        print(f"   Crie manualmente episodes/roteiro-{date}.json e rode process de novo.")
        sys.exit(3)

    try:
        # generate_roteiro_llm já aplica polish + retry 7.1
        return generate_roteiro_json(date, force=force or not json_path.exists())
    except Exception as e:
        print(f"❌ FALHA ao gerar roteiro JSON via LLM: {e}")
        print(f"   Ação: gere episodes/roteiro-{date}.json (Hermes ou "
              f"python3 scripts/generate_roteiro_llm.py --date {date})")
        sys.exit(3)


def cmd_process(date: str, force_render: bool = False):
    """Processa o roteiro finalizado, gerando TTS, manchetes e metadados."""
    roteiro_path = EPISODES_DIR / f"{date}.md"
    json_path = EPISODES_DIR / f"roteiro-{date}.json"

    if not roteiro_path.exists():
        # Se só o JSON existe, renderiza direto
        if json_path.exists():
            print(f"ℹ️  MD ausente; renderizando a partir de {json_path.name}")
            try:
                md = render_from_json(json_path)
                roteiro_path.write_text(md, encoding="utf-8")
            except Exception as e:
                print(f"FALHA ao renderizar JSON→MD: {e}")
                sys.exit(3)
        else:
            print(f"FALHA: roteiro não encontrado: {roteiro_path}")
            print(f"  Dica: execute 'python pipeline.py full --date {date}' (init+JSON).")
            sys.exit(2)

    # Verifica se o roteiro já está rico (não é mais template)
    current_content = roteiro_path.read_text(encoding="utf-8")
    is_template = _is_roteiro_template(current_content)

    if is_template or force_render:
        # Prefere JSON (Hermes/LLM); generate_script só carrega o JSON
        try:
            if not json_path.exists():
                print("🧠 roteiro JSON ausente — tentando gerar via LLM...")
                ensure_roteiro_json(date)
            print("🧠 Renderizando roteiro com personas Peter/Ricardo via generate_script/JSON...")
            if force_render and json_path.exists():
                formatted_roteiro = render_from_json(json_path)
            else:
                roteiro_obj = generate_script(date)
                formatted_roteiro = format_script(date, roteiro_obj)
            roteiro_path.write_text(formatted_roteiro, encoding="utf-8")
            print(f"✅ Roteiro {date} gerado com sucesso.")
        except Exception as e:
            # FALHA ALTA: não cair mais para fallback (antes: boilerplate)
            # que produziria roteiro enxuto (430 palavras, 3 quadros) que reprova o
            # checklist de validação (ver LESSONS_LEARNED — regressão 2026-06-20).
            print(f"❌ FALHA CRÍTICA ao gerar roteiro com generate_script: {e}")
            print("   Abortando em vez de emitir roteiro fallback degradado.")
            print("   Ação: execute o Hermes Agent para gerar episodes/roteiro-"
                  f"{date}.json,")
            print("   ou: python3 scripts/generate_roteiro_llm.py --date "
                  f"{date}")
            sys.exit(3)
    else:
        print("✅ Roteiro já populado com conteúdo rico, mantendo.")

    content = roteiro_path.read_text(encoding="utf-8")
    print(f"📄 Processando roteiro: {roteiro_path} ({len(content.split())} palavras)")

    # 1. Gerar roteiro_tts.txt
    tts_text = preprocess_for_tts(content)
    tts_path = EPISODES_DIR / f"{date}-tts.txt"
    tts_path.write_text(tts_text, encoding="utf-8")
    print(f"  ✅ TTS gerado: {tts_path}")

    # 2. Gerar manchetes.txt
    manchetes = extract_manchetes(content)
    if manchetes:
        manchetes_path = EPISODES_DIR / f"{date}-manchetes.txt"
        manchetes_path.write_text(manchetes, encoding="utf-8")
        print(f"  ✅ Manchetes geradas: {manchetes_path}")
    else:
        print("  ⚠️  Nenhum bloco de manchetes encontrado")

    # 3. Gerar metadados enriquecidos para auditoria
    episode_num = get_episode_number(date)

    # Collect pipeline statistics
    cache = load_cache()
    last_run = cache.get("last_run", {})
    raw_articles_count = last_run.get("items_collected", 0)
    sources_used = last_run.get("sources_used", [])
    url_duplicates = last_run.get("url_duplicates", 0)
    semantic_duplicates = last_run.get("semantic_duplicates", 0)

    # Fase 2.3 — contar notícias breaking sinalizadas no roteiro
    breaking_count = content.count("[BREAKING]")

    # Run validation (returns tuple: ok, errors, warnings)
    ok, errors, warnings = cmd_validate(date)

    metadata = generate_metadata(
        content, date, episode_num,
        sources_used=sources_used,
        raw_articles_count=raw_articles_count,
        url_duplicates=url_duplicates,
        semantic_duplicates=semantic_duplicates,
        validation_errors=errors,
        validation_warnings=warnings,
        breaking_count=breaking_count,
    )
    metadata_path = EPISODES_DIR / f"{date}-metadata.json"
    metadata_path.write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"  ✅ Metadados gerados: {metadata_path}")
    print(f"     📊 {metadata['palavras_total']} palavras, ~{metadata['duracao_estimada_min']} min")
    print(f"     📊 Quadros: {', '.join(metadata['quadros_gerados'])}")

    return tts_path


def cmd_validate(date: str):
    """Valida o episódio contra o checklist de qualidade.
    Returns (ok: bool, errors: list[str], warnings: list[str]).
    Erros bloqueiam o pipeline, warnings são apenas indicados.
    """
    roteiro_path = EPISODES_DIR / f"{date}.md"
    if not roteiro_path.exists():
        print(f"FALHA: roteiro não encontrado: {roteiro_path}")
        sys.exit(2)

    content = roteiro_path.read_text(encoding="utf-8")
    issues = validate_episode(content)

    # Separar erros críticos (❌) de avisos (⚠️)
    errors = []
    warnings = []
    for issue in issues:
        if issue.startswith("❌"):
            errors.append(issue)
        else:
            warnings.append(issue)

    print(f"\n🔍 Validação do episódio {date}:")
    print(f"   Arquivo: {roteiro_path}")
    print(f"   Palavras: {len(content.split())}")
    print()

    if errors:
        print(f"❌ {len(errors)} erro(s) crítico(s) encontrado(s):\n")
        for err in errors:
            print(f"  {err}")
    if warnings:
        print(f"⚠️  {len(warnings)} aviso(s) encontrado(s):\n")
        for warn in warnings:
            print(f"  {warn}")
    if not (errors or warnings):
        print("✅ Episódio passou em todas as verificações!")

    return (len(errors) == 0, errors, warnings)


def cmd_audio(date: str, allow_short: bool = False):
    """Gera áudio TTS multi-locutor para o episódio.

    Cadeia de fallback (2026-08-15):
      1) Gemini multi-TTS (vozes Charon/Schedar)
      2) Edge TTS pt-BR (tts_fallback_edge.sh, pt-BR-AntonioNeural)
      ElevenLabs nunca teve conta — não restaurar tts_fallback_elevenlabs.py;
      se um dia precisar, reescrever. MOSS desabilitado até fine-tune pt-BR.

    Gates:
      - roteiro ≥ 1500 palavras (a menos que allow_short)
      - MP3 final ≥ 1 MB
      - publica audio/{date}.mp3 como alias de entrega
    """
    roteiro_path = EPISODES_DIR / f"{date}.md"
    tts_path = EPISODES_DIR / f"{date}-tts.txt"

    if roteiro_path.exists() and not allow_short:
        words = len(roteiro_path.read_text(encoding="utf-8").split())
        if words < 1500:
            print(
                f"❌ GATE tamanho: roteiro com {words} palavras (< 1500). "
                f"Áudio bloqueado. Melhore o roteiro ou use --allow-short-audio."
            )
            sys.exit(4)

    if not tts_path.exists():
        print(f"⚠️  TTS não encontrado, processando roteiro primeiro...")
        tts_path = cmd_process(date)

    script = SCRIPT_DIR / "generate_gemini_tts_multi.py"
    if not script.exists():
        print(f"FALHA: script TTS não encontrado: {script}")
        sys.exit(2)

    out_path = AUDIO_DIR / f"{date}-completo.wav"
    hermes_py = Path("/home/osmar/.hermes/hermes-agent/venv/bin/python3")
    py = str(hermes_py) if hermes_py.exists() else sys.executable
    env = os.environ.copy()

    def _delivery_ok() -> bool:
        delivery = AUDIO_DIR / f"{date}.mp3"
        named = AUDIO_DIR / f"{date}-vale-da-liberdade.mp3"
        if not delivery.exists() and named.exists():
            delivery.write_bytes(named.read_bytes())
        if delivery.exists() and delivery.stat().st_size >= 1_000_000:
            return True
        if named.exists() and named.stat().st_size >= 1_000_000:
            if not delivery.exists():
                delivery.write_bytes(named.read_bytes())
            return True
        return False

    # ── 1) Gemini multi ──────────────────────────────────────────────
    cmd = [
        py, str(script),
        "--episode", str(tts_path),
        "--out", str(out_path),
        "--skip-preprocess",
    ]
    print(f"\n🎙️  Gerando áudio multi-locutor (Gemini)...")
    print(f"   Python: {py}")
    print(f"   Input: {tts_path}")
    print(f"   Output: {out_path}")

    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode == 0:
        if result.stdout:
            print(result.stdout[-1500:])
        print(f"  ✅ Gemini OK: {out_path}")
    else:
        print(f"⚠️  Gemini multi-TTS falhou (exit {result.returncode})")
        if result.stdout:
            print(result.stdout[-1500:])
        if result.stderr:
            print(result.stderr[-1500:])

        eleven_ok = False
        edge_ok = False

        # ── 2) ElevenLabs pt-BR (se API key) ─────────────────────────
        el = SCRIPT_DIR / "tts_fallback_elevenlabs.py"
        hermes_py = Path("/home/osmar/.hermes/hermes-agent/venv/bin/python3")
        el_py = str(hermes_py) if hermes_py.exists() else sys.executable
        if el.exists():
            print("🔁 Fallback #2: ElevenLabs (Liam/Will pt-BR)...")
            eb = subprocess.run(
                [el_py, str(el), "--date", date],
                capture_output=True,
                text=True,
                env=env,
                cwd=str(PROJECT_ROOT),
            )
            if eb.stdout:
                print(eb.stdout[-2000:])
            if eb.returncode == 0 and _delivery_ok():
                print("  ✅ ElevenLabs fallback OK")
                eleven_ok = True
            else:
                print(f"⚠️  ElevenLabs indisponível/falhou (exit {eb.returncode})")
                if eb.stderr:
                    print(eb.stderr[-1200:])

        # ── 3) Edge TTS pt-BR (voz natural) ─────────────────────────
        if not eleven_ok:
            edge_fallback = SCRIPT_DIR / "tts_fallback_edge.sh"
            if edge_fallback.exists():
                print("🔁 Fallback #3: Edge TTS pt-BR (voz natural)...")
                eb = subprocess.run(
                    ["bash", str(edge_fallback), date],
                    capture_output=True,
                    text=True,
                    env=env,
                    cwd=str(PROJECT_ROOT),
                )
                print(eb.stdout[-2000:] if eb.stdout else "")
                if eb.returncode == 0 and _delivery_ok():
                    print("  ✅ Edge TTS fallback OK")
                    edge_ok = True
                else:
                    print(f"⚠️  Edge TTS falhou (exit {eb.returncode})")
                    if eb.stderr:
                        print(eb.stderr[-1200:])
            else:
                print("⚠️  Script Edge TTS não encontrado")

        # ── 4) MOSS-TTS-Nano — DESABILITADO ───────────────────────
        # Aguarda fine-tune para pt-BR antes de reativar
        # Se necessário, descomente o bloco abaixo:
        # moss_ok = False
        # moss = SCRIPT_DIR / "tts_fallback_moss.py"
        # moss_py_candidates = [
        #     Path("/home/osmar/moss-nano-env/bin/python"),
        #     Path("/home/osmar/moss-tts-env/bin/python"),
        # ]
        # moss_py = next((p for p in moss_py_candidates if p.exists()), None)
        # if (not eleven_ok) and (not edge_ok) and moss.exists() and moss_py is not None:
        #     print("🔁 Fallback #4: MOSS-TTS (pt-PT — último recurso)...")
        #     ...

        # ── 5) Falha total ──────────────────────────────────────────
        if not eleven_ok and not edge_ok:
            print("❌ TODOS os backends TTS falharam")
            print("   (MOSS-TTS desabilitado — aguarda fine-tune pt-BR)")
            sys.exit(3)

    print(f"  ✅ Áudio gerado: {out_path}")

    delivery = AUDIO_DIR / f"{date}.mp3"
    named = AUDIO_DIR / f"{date}-vale-da-liberdade.mp3"
    if not delivery.exists() and named.exists():
        delivery.write_bytes(named.read_bytes())
    if delivery.exists():
        size = delivery.stat().st_size
        print(f"  ✅ MP3 de entrega: {delivery} ({size/1e6:.2f} MB)")
        if size < 1_000_000:
            print(f"❌ GATE áudio: MP3 < 1 MB ({size} bytes)")
            sys.exit(3)
    elif named.exists():
        print(f"  ✅ MP3: {named}")
    else:
        print(f"  ⚠️  MP3 final não encontrado (WAV em: {out_path})")
        sys.exit(3)

    return out_path


def cmd_update_archive(date: str):
    """Atualiza o arquivo de índice do archive."""
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    index_path = ARCHIVE_DIR / "index.md"

    if index_path.exists():
        content = index_path.read_text(encoding="utf-8")
        if date in content:
            print(f"  ℹ️  {date} já está no índice")
            return
    else:
        content = ""

    with index_path.open("a", encoding="utf-8") as f:
        f.write(f"- {date}\n")
    print(f"  ✅ Índice atualizado: {index_path}")


def cmd_full(
    date: str,
    hours: int = 48,
    collect: bool = True,
    skip_audio: bool = False,
    force_roteiro: bool = False,
    allow_short_audio: bool = False,
):
    """Pipeline completo de ponta a ponta:

    init (coleta) → roteiro JSON (LLM) → process (MD+TTS) → validate → audio → archive
    """
    print(f"🚀 Pipeline completo para {date}")
    print("=" * 50)

    # 1. Coleta + templates
    print("\n📥 Etapa 1/7 — Init / coleta de notícias")
    cmd_init(date, collect=collect, hours=hours)

    raw_path = EPISODES_DIR / f"raw-{date}.md"
    if _raw_needs_collect(raw_path):
        print(f"❌ FALHA: raw-{date}.md ficou vazio após init. Abortando full.")
        sys.exit(2)

    # 2. Garantir JSON do roteiro (LLM se necessário)
    print("\n🧠 Etapa 2/7 — Roteiro JSON (LLM se necessário)")
    md_path = EPISODES_DIR / f"{date}.md"
    md_is_thin = (not md_path.exists()) or _is_roteiro_template(
        md_path.read_text(encoding="utf-8")
    )
    # Sempre validar estrutura do JSON (política C). MD "rico" não autoriza skip.
    ensure_roteiro_json(date, force=force_roteiro)

    # 2.5. Título otimizado (skill youtube-journalistic-title-optimizer) — NÃO bloqueia
    print("\n🎯 Etapa 2.5/8 — Título otimizado do episódio")
    try:
        title_script = SCRIPT_DIR / "title_optimizer.py"
        if title_script.exists():
            tr = subprocess.run(
                [sys.executable, str(title_script), "--date", date],
                capture_output=True, text=True,
                env=os.environ.copy(), cwd=str(PROJECT_ROOT),
            )
            if tr.stdout:
                lines = [l for l in tr.stdout.splitlines() if l.strip()]
                print("\n".join(lines[-30:]))
            if tr.returncode != 0:
                print(f"⚠️  title_optimizer exit {tr.returncode} (não bloqueia): {(tr.stderr or '')[-300:]}")
        else:
            print("  (title_optimizer.py não encontrado, pulando)")
    except Exception as e:
        print(f"⚠️  title_optimizer falhou (não bloqueia): {e}")

    # 3. Processar (render MD se template + TTS + metadados)
    print("\n📝 Etapa 3/7 — Processamento do roteiro (MD + TTS)")
    # Se MD é template ou force, re-renderiza a partir do JSON
    cmd_process(date, force_render=force_roteiro or md_is_thin)

    # 4. Validar
    print("\n🔍 Etapa 4/7 — Validação")
    ok, errors, warnings = cmd_validate(date)
    if not ok:
        print("\n❌ Episódio tem problemas críticos. Pipeline abortado.")
        for e in errors:
            print(f"  {e}")
        sys.exit(4)
    if warnings:
        print("\n⚠️  Episódio tem avisos (mas válido):")
        for w in warnings:
            print(f"  {w}")

    # 5. Gerar áudio
    if skip_audio:
        print("\n🎙️  Etapa 5/7 — Áudio IGNORADO (--skip-audio)")
    else:
        print("\n🎙️  Etapa 5/7 — Geração de áudio")
        cmd_audio(date, allow_short=allow_short_audio)

    # 5.5. Inserção de anúncio de patrocinador (Tipo 1 — ads/schedule.json)
    print("\n📢 Etapa 5.5/8 — Inserção de anúncio (patrocínio Tipo 1)")
    try:
        ads_script = SCRIPT_DIR / "ads_insert.py"
        if ads_script.exists():
            r = subprocess.run(
                [sys.executable, str(ads_script), "--date", date, "--no-republish"],
                capture_output=True, text=True, env=os.environ.copy(),
                cwd=str(PROJECT_ROOT),
            )
            if r.stdout:
                print(r.stdout[-1200:])
            if r.returncode != 0:
                print(f"⚠️  ads_insert exit {r.returncode} (não bloqueia): {(r.stderr or '')[-400:]}")
        else:
            print("  (ads_insert.py não encontrado, pulando)")
    except Exception as e:
        print(f"⚠️  ads_insert falhou (não bloqueia): {e}")

    # 5.6. Thumbnail/capa automática (DashScope cascade) — NÃO bloqueia o pipeline
    print("\n🖼️  Etapa 5.6/8 — Thumbnail automática do episódio")
    try:
        from thumbnail_generator import generate_thumbnail_safe
        thumb = generate_thumbnail_safe(date=date, episode_id=f"ep_{date}")
        if thumb.get("path"):
            print(
                f"  ✅ thumbnail: {thumb.get('path')} "
                f"(model={thumb.get('image_model_used')} placeholder={thumb.get('is_placeholder')})"
            )
        else:
            print(f"  ⚠️  thumbnail sem path (não bloqueia): {thumb.get('error', thumb)}")
    except Exception as e:
        print(f"⚠️  thumbnail falhou (não bloqueia): {e}")

    # 6. Atualizar arquivo
    print("\n📁 Etapa 6/8 — Atualização do índice")
    cmd_update_archive(date)

    # 7. Publicar site estático
    print("\n🌐 Etapa 7/8 — Publicar site (public/)")
    cmd_publish_site(date)

    print("\n" + "=" * 50)
    print(f"✅ Pipeline completo finalizado para {date}")


def cmd_publish_site(date: str | None = None):
    """Upload áudio para Cloudflare R2 (espelho local) + rebuild PWA + catálogo/RSS.

    Fluxo:
      1. Upload R2 (espelho do áudio)
      2. Reconstrução da PWA (build_site.py) — gera estrutura HTML + episodes.json
      3. Atualização de feed RSS/JSON (publish_site.py)
    """
    py = sys.executable

    # 1. Upload R2 + espelho public/audio/{date}.mp3
    if date:
        r2_script = SCRIPT_DIR / "upload_r2.py"
        candidates = [
            AUDIO_DIR / f"{date}.mp3",
            AUDIO_DIR / f"{date}-vale-da-liberdade.mp3",
            AUDIO_DIR / f"{date}-completo.mp3",
        ]
        mp3_path = next((p for p in candidates if p.exists() and p.stat().st_size > 1000), None)
        if r2_script.exists() and mp3_path is not None:
            print(f"\n☁️  Enviando áudio para Cloudflare R2 ({mp3_path.name})...")
            try:
                r = subprocess.run(
                    [py, str(r2_script), "--date", date, "--file", str(mp3_path)],
                    cwd=str(PROJECT_ROOT),
                    text=True,
                )
                if r.returncode != 0:
                    print(f"⚠️  upload_r2 exit {r.returncode} — public/ ainda pode servir local")
            except Exception as e:
                print(f"⚠️  Falha no upload R2 (fallback local): {e}")
        else:
            print(f"ℹ️  Sem MP3 para {date} — pulando R2")

    # 2. Reconstrução do Portal Web PWA (build_site.py)
    build_script = SCRIPT_DIR / "build_site.py"
    if build_script.exists():
        print("\n🌐 Reconstruindo Portal Web PWA (build_site.py)...")
        try:
            r = subprocess.run(
                [py, str(build_script)],
                cwd=str(PROJECT_ROOT),
                text=True,
                capture_output=True,
            )
            if r.stdout:
                print(r.stdout[-1500:])
            if r.returncode != 0:
                print(f"⚠️  build_site falhou (exit {r.returncode})")
                if r.stderr:
                    print(r.stderr[-800:])
        except Exception as e:
            print(f"⚠️  Falha ao executar build_site.py: {e}")
    else:
        print("⚠️  scripts/build_site.py não encontrado")

    # 3. Catálogo + feed
    pub = SCRIPT_DIR / "publish_site.py"
    if not pub.exists():
        print("⚠️  scripts/publish_site.py não encontrado")
        return
    cmd = [py, str(pub)]
    if date:
        cmd += ["--date", date]
    print("\n🌐 Atualizando catálogo/RSS (publish_site.py)...")
    print(f"  → {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(PROJECT_ROOT), text=True, capture_output=True)
    if r.stdout:
        print(r.stdout[-2000:])
    if r.returncode != 0:
        print(f"⚠️  publish_site falhou (exit {r.returncode})")
        if r.stderr:
            print(r.stderr[-1000:])
    else:
        print("  ✅ Site atualizado em public/ (UX PWA preservada)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Web Jornal Vale da Liberdade")
    parser.add_argument(
        "command",
        choices=["init", "collect", "process", "validate", "audio", "full", "update-archive", "roteiro", "deliver-check", "publish"],
    )
    parser.add_argument("--date", help="Data no formato YYYY-MM-DD")
    parser.add_argument("--hours", type=int, default=48, help="Janela de horas para coleta")
    parser.add_argument("--no-collect", action="store_true", help="Desabilita coleta automática no init/full")
    parser.add_argument("--skip-audio", action="store_true", help="No full: pula geração de áudio")
    parser.add_argument(
        "--force-roteiro",
        action="store_true",
        help="No full/roteiro: regenera JSON mesmo se já existir",
    )
    parser.add_argument(
        "--allow-short-audio",
        action="store_true",
        help="Permite gerar áudio mesmo com roteiro < 1500 palavras (não recomendado)",
    )

    args = parser.parse_args()
    date = get_date_str(args.date) if args.date else datetime.now().strftime("%Y-%m-%d")

    if args.command == "init":
        cmd_init(date, collect=not args.no_collect, hours=args.hours)
    elif args.command == "collect":
        cmd_collect(date, hours=args.hours)
    elif args.command == "roteiro":
        ensure_roteiro_json(date, force=args.force_roteiro)
    elif args.command == "deliver-check":
        script = SCRIPT_DIR / "delivery_health_check.sh"
        if not script.exists():
            print(f"FALHA: {script} não encontrado")
            sys.exit(2)
        r = subprocess.run(["bash", str(script), "--json"], text=True)
        sys.exit(r.returncode)
    elif args.command == "process":
        cmd_process(date)
    elif args.command == "validate":
        cmd_validate(date)
    elif args.command == "audio":
        cmd_audio(date, allow_short=args.allow_short_audio)
    elif args.command == "full":
        cmd_full(
            date,
            hours=args.hours,
            collect=not args.no_collect,
            skip_audio=args.skip_audio,
            force_roteiro=args.force_roteiro,
            allow_short_audio=args.allow_short_audio,
        )
    elif args.command == "update-archive":
        cmd_update_archive(date)
    elif args.command == "publish":
        cmd_publish_site(date if args.date else None)