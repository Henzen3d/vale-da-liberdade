#!/usr/bin/env python3
"""
Pipeline unificado do Web Jornal Vale da Liberdade.

Orquestra o fluxo diário de produção do podcast:
1. Gera template raw para coleta de notícias
2. Processa roteiro finalizado gerando TTS, manchetes e metadados
3. Valida o episódio contra o checklist da SKILL
4. Invoca geração de áudio TTS multi-locutor
5. Atualiza o arquivo de índice

Uso:
    # Criar template para um novo dia
    python pipeline.py init --date 2026-06-16

    # Processar roteiro finalizado (gerar TTS, manchetes, metadados)
    python pipeline.py process --date 2026-06-15

    # Validar um episódio
    python pipeline.py validate --date 2026-06-15

    # Pipeline completo: processar + gerar áudio + atualizar índice
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
from generate_script import generate_script, format_script

try:
    from x_collector import consume_x_tweets_for_pipeline
    _X_COLLECTOR_AVAILABLE = True
except Exception as e:
    # Falha silenciosa para evitar interrupções no pipeline caso dependências do X falhem
    _X_COLLECTOR_AVAILABLE = False

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


def cmd_init(date: str, collect: bool = True, hours: int = 48):
    """Cria templates para um novo dia de produção com coleta automática de notícias opcional."""
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Criar ou preencher o raw
    raw_path = EPISODES_DIR / f"raw-{date}.md"
    if raw_path.exists():
        print(f"⚠️  Arquivo raw já existe: {raw_path}")
    else:
        if collect:
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
        else:
            print("ℹ️  Coleta automática desabilitada. Criando template raw vazio...")
            _create_fallback_raw(raw_path, date)

    # 2. Criar roteiro template
    roteiro_path = EPISODES_DIR / f"{date}.md"
    if roteiro_path.exists():
        print(f"⚠️  Roteiro já existe: {roteiro_path}")
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


def cmd_process(date: str):
    """Processa o roteiro finalizado, gerando TTS, manchetes e metadados."""
    roteiro_path = EPISODES_DIR / f"{date}.md"
    if not roteiro_path.exists():
        print(f"FALHA: roteiro não encontrado: {roteiro_path}")
        print(f"  Dica: execute 'python pipeline.py init --date {date}' primeiro.")
        sys.exit(2)

    # Verifica se o roteiro já está rico (não é mais template)
    current_content = roteiro_path.read_text(encoding="utf-8")
    is_template = (
        "[notícia]" in current_content
        or "[frase de impacto" in current_content
        or "[reação/complemento" in current_content
        or len(current_content.split()) < 500
    )

    if is_template:
        # Gera roteiro com personas a partir do raw usando IA
        try:
            print("🧠 Gerando roteiro com personas Peter/Ricardo via generate_script...")
            roteiro_obj = generate_script(date)
            formatted_roteiro = format_script(date, roteiro_obj)
            roteiro_path.write_text(formatted_roteiro, encoding="utf-8")
            print(f"✅ Roteiro {date} gerado com sucesso por generate_script.")
        except Exception as e:
            # FALHA ALTA: não cair mais para fallback (antes: boilerplate)
            # que produziria roteiro enxuto (430 palavras, 3 quadros) que reprova o
            # checklist de validação (ver LESSONS_LEARNED — regressão 2026-06-20).
            print(f"❌ FALHA CRÍTICA ao gerar roteiro com generate_script: {e}")
            print("   Abortando em vez de emitir roteiro fallback degradado.")
            print("   Ação: execute o Hermes Agent para gerar episodes/roteiro-"
                  f"{date}.json,")
            print(f"   ou corrija a causa da falha e rode novamente.")
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


def cmd_audio(date: str):
    """Gera áudio TTS multi-locutor para o episódio."""
    tts_path = EPISODES_DIR / f"{date}-tts.txt"
    if not tts_path.exists():
        # Tentar processar primeiro
        print(f"⚠️  TTS não encontrado, processando roteiro primeiro...")
        tts_path = cmd_process(date)

    script = SCRIPT_DIR / "generate_gemini_tts_multi.py"
    if not script.exists():
        print(f"FALHA: script TTS não encontrado: {script}")
        sys.exit(2)

    out_path = AUDIO_DIR / f"{date}-completo.wav"
    cmd = [
        sys.executable,
        str(script),
        "--episode", str(tts_path),
        "--out", str(out_path),
    ]

    print(f"\n🎙️  Gerando áudio multi-locutor...")
    print(f"   Input: {tts_path}")
    print(f"   Output: {out_path}")

    # Passar variáveis de ambiente (inclui GEMINI_API_KEY do .env)
    env = os.environ.copy()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        print(f"FALHA na geração de áudio:")
        print(f"  stdout: {result.stdout}")
        print(f"  stderr: {result.stderr}")
        sys.exit(3)

    print(f"  ✅ Áudio gerado: {out_path}")

    # O pós-processamento e conversão MP3 agora são feitos pelo generate_gemini_tts_multi.py
    mp3_path = AUDIO_DIR / f"{date}-vale-da-liberdade.mp3"
    if mp3_path.exists():
        print(f"  ✅ MP3 final com pós-processamento: {mp3_path}")
    else:
        print(f"  ⚠️  MP3 final não encontrado (pós-processamento pode ter falhado). WAV em: {out_path}")

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


def cmd_full(date: str):
    """Pipeline completo: process + validate + audio + archive."""
    print(f"🚀 Pipeline completo para {date}")
    print("=" * 50)

    # 1. Processar roteiro
    print("\n📝 Etapa 1/4 — Processamento do roteiro")
    cmd_process(date)

    # 2. Validar
    print("\n🔍 Etapa 2/4 — Validação")
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

    # 3. Gerar áudio
    print("\n🎙️  Etapa 3/4 — Geração de áudio")
    cmd_audio(date)

    # 4. Atualizar arquivo
    print("\n📁 Etapa 4/4 — Atualização do índice")
    cmd_update_archive(date)

    print("\n" + "=" * 50)
    print(f"✅ Pipeline completo finalizado para {date}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Pipeline Web Jornal Vale da Liberdade")
    parser.add_argument("command", choices=["init", "collect", "process", "validate", "audio", "full", "update-archive"])
    parser.add_argument("--date", help="Data no formato YYYY-MM-DD")
    parser.add_argument("--hours", type=int, default=48, help="Janela de horas para coleta")
    parser.add_argument("--no-collect", action="store_true", help="Desabilita coleta automática no init")
    
    args = parser.parse_args()
    date = get_date_str(args.date) if args.date else datetime.now().strftime("%Y-%m-%d")
    
    if args.command == "init":
        cmd_init(date, collect=not args.no_collect, hours=args.hours)
    elif args.command == "collect":
        cmd_collect(date, hours=args.hours)
    elif args.command == "process":
        cmd_process(date)
    elif args.command == "validate":
        cmd_validate(date)
    elif args.command == "audio":
        cmd_audio(date)
    elif args.command == "full":
        cmd_full(date)
    elif args.command == "update-archive":
        cmd_update_archive(date)