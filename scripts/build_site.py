#!/usr/bin/env python3
"""
Gerador Estático do Portal Web Dinâmico
Web Jornal Vale da Liberdade

Reconstrói automaticamente public/index.html e public/styles.css
integrando o Player de Áudio, Transcrição por Persona, Supabase Auth e Fontes do Dia.
"""

import os
import sys
import json
import re
from pathlib import Path
from dotenv import load_dotenv

# Carregar variáveis de ambiente
env_path = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=env_path)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ARCHIVE_INDEX = PROJECT_ROOT / 'archive' / 'index.md'
EPISODES_DIR = PROJECT_ROOT / 'episodes'
AUDIO_DIR = PROJECT_ROOT / 'audio'
PUBLIC_DIR = PROJECT_ROOT / 'public'

SUPABASE_URL = os.getenv("SUPABASE_URL", "http://192.168.31.22:8080")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", "")


def load_episodes():
    """Carrega todas as edições listadas no archive/index.md."""
    if not ARCHIVE_INDEX.exists():
        return []

    with open(ARCHIVE_INDEX, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    episodes = []
    for line in lines:
        match = re.search(r'(\d{4}-\d{2}-\d{2})', line)
        if match:
            date_str = match.group(1)
            meta_path = EPISODES_DIR / f"{date_str}-metadata.json"
            script_path = EPISODES_DIR / f"{date_str}.md"
            audio_local = AUDIO_DIR / f"{date_str}-vale-da-liberdade.mp3"

            metadata = {}
            if meta_path.exists():
                try:
                    with open(meta_path, 'r', encoding='utf-8') as mf:
                        metadata = json.load(mf)
                except Exception:
                    pass

            script_text = ""
            if script_path.exists():
                with open(script_path, 'r', encoding='utf-8') as sf:
                    script_text = sf.read()

            audio_url = f"/audio/{date_str}-vale-da-liberdade.mp3"
            if not audio_local.exists():
                # Tentar fallback ou URL pública
                audio_url = f"https://audio.mob.tec.br/audio/{date_str}-vale-da-liberdade.mp3"

            # Verificar sidecar R2 e usar URL pública se disponível
            r2_path = EPISODES_DIR / f"{date_str}-r2.json"
            if r2_path.exists():
                try:
                    with open(r2_path, 'r', encoding='utf-8') as rf:
                        r2_meta = json.load(rf)
                    if r2_meta.get("r2_uploaded") and r2_meta.get("catalog_url"):
                        audio_url = r2_meta["catalog_url"]
                except Exception:
                    pass

            episodes.append({
                "date": date_str,
                "metadata": metadata,
                "script": script_text,
                "audio_url": audio_url
            })

    # Ordenar edições da mais recente para a mais antiga
    episodes.sort(key=lambda x: x['date'], reverse=True)
    return episodes


def parse_script_to_html(script_text):
    """Converte o roteiro markdown em componentes HTML estilizados por persona."""
    if not script_text:
        return "<p class='no-script'>Roteiro indisponível para esta edição.</p>"

    lines = script_text.splitlines()
    html_out = []
    
    in_dialogue = False

    for line in lines:
        line_str = line.strip()
        if not line_str:
            continue

        if line_str.startswith('#'):
            # Título de Quadro
            title = line_str.lstrip('#').strip()
            html_out.append(f'<h3 class="section-title">{title}</h3>')
        elif line_str.startswith('Peter:') or line_str.startswith('Peter Albuquerque:'):
            text = re.sub(r'^Peter(\s+Albuquerque)?:', '', line_str).strip()
            html_out.append(f'''
                <div class="speech-bubble peter-bubble">
                    <div class="speaker-header">
                        <span class="speaker-avatar peter-avatar">🎙️</span>
                        <strong class="speaker-name peter-name">Peter Albuquerque</strong>
                        <span class="speaker-tag">Ancap / Crítico</span>
                    </div>
                    <p class="speech-text">{text}</p>
                </div>
            ''')
        elif line_str.startswith('Ricardo:') or line_str.startswith('Ricardo Souto:'):
            text = re.sub(r'^Ricardo(\s+Souto)?:', '', line_str).strip()
            html_out.append(f'''
                <div class="speech-bubble ricardo-bubble">
                    <div class="speaker-header">
                        <span class="speaker-avatar ricardo-avatar">📊</span>
                        <strong class="speaker-name ricardo-name">Ricardo Souto</strong>
                        <span class="speaker-tag">Economista / Pragmático</span>
                    </div>
                    <p class="speech-text">{text}</p>
                </div>
            ''')
        else:
            html_out.append(f'<p class="general-text">{line_str}</p>')

    return '\n'.join(html_out)


def build_site():
    """Atualiza o catálogo do site via publish_site.py, preservando o layout PWA dinâmico com Brasil & Mundo."""
    print("[BUILD SITE] Redirecionando para publish_site.py para preservar a UX PWA (abas Jornal Diário + Brasil & Mundo)...")
    pub_script = PROJECT_ROOT / "scripts" / "publish_site.py"
    if pub_script.exists():
        import subprocess
        subprocess.run([sys.executable, str(pub_script)], cwd=str(PROJECT_ROOT))
    else:
        print("[BUILD SITE] ERRO: publish_site.py não foi encontrado!")


if __name__ == "__main__":
    build_site()
