# TODO: Integração do Defuddle no Web Jornal

## Prioridade: Média
## Status: Aguardando integração

### O que fazer
Integrar o defuddle como fallback na coleta de notícias do web jornal.

### Contexto
- Defuddle já está instalado em `/home/osmar/defuddle/`
- CLI disponível: `defuddle parse URL --markdown`
- Scripts wrapper criados: `~/.local/bin/defuddle-fetch`, `~/.local/bin/web-clean`
- Skill criada: `defuddle-web-cleanup`

### Benefícios
- removing menus, ads, footers automaticamente
- Melhor qualidade de conteúdo extraído
- Fallback para quando RSS/BeautifulSoup falham

### Onde integrar
1. `scripts/news_collector.py` → função `fetch_article()` como fallback
2. `scripts/source_discovery_search.py` → busca de URLs candidatas
3. `scripts/generate_script.py` → pré-processamento de raw URLs

### Como implementar
```python
import subprocess

def fetch_with_defuddle(url: str) -> str:
    """Fetch URL and clean with defuddle."""
    try:
        # Fetch HTML
        resp = requests.get(url, headers=HEADERS, timeout=30)
        html = resp.text
        
        # Clean with defuddle
        result = subprocess.run(
            ["defuddle", "parse", "--markdown"],
            input=html,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and len(result.stdout) > 100:
            return result.stdout
    except Exception as e:
        log.warning(f"Defuddle failed for {url}: {e}")
    
    # Fallback to BeautifulSoup
    return fetch_with_beautifulsoup(url)
```

### Checklist
- [ ] Adicionar import `subprocess` ao `news_collector.py`
- [ ] Criar função `fetch_with_defuddle()`
- [ ] Integrar como fallback em `fetch_article()`
- [ ] Adicionar log de métricas (defuddle vs BeautifulSoup)
- [ ] Testar com URLs reais do web jornal
- [ ] Atualizar documentação

### Notas
- Defuddle funciona melhor com server-rendered HTML
- Sites com muito JavaScript podem precisar de browser automation primeiro
- Timeout de 30s já é suficiente para a maioria das páginas

---
Criado em: 2026-07-31
Atualizado: 2026-07-31
