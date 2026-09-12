# 09 — Infraestrutura compartilhada (DRY)

**Impacto**: Baixo. Opt-in.
**Ganho**: menos boilerplate; startup irrelevante no cron.
**Não** na mesma noite que 02/06 (mexe no topo de muitos scripts).

---

## Alinhamento

- Paths: `SCRIPT_DIR = Path(__file__).resolve().parent` — `_bootstrap.py` **dentro de `scripts/`** faz `PROJECT_ROOT = SCRIPT_DIR.parent`. Correto.
- Dotenv: projeto `.env` **primeiro**; `~/.hermes/.env` com `override=False`. Cron diário já dá `source` no `.env` do projeto — não duplicar chaves.
- **Não** Pydantic Settings nesta onda. `pydantic_settings` existe no HERMES_PY e **falta** no PROJECT_PY. Um `ProjectConfig()` no import de `bm_mockup_video` quebraria o vídeo. stdlib + dotenv basta.
- Logging JSON do thumbnail: não unificar com `basicConfig` do collector (formato diferente é proposital).
- Nome `_bootstrap.py`: ok (privado). Evitar `scripts/bootstrap.py` solto no PATH.
- UTF-8 `reconfigure`: no cron Linux o locale já é UTF-8; manter o helper não faz mal.
- `sys.path.insert(0, SCRIPT_DIR)`: o diário às vezes roda com `PYTHONPATH=PROJECT_ROOT`. Não quebrar imports `from scripts.x` vs `from x`.

---

## Checklist

- [ ] `_bootstrap.py` importável nos **dois** Pythons
- [ ] Nenhum script BM passou a exigir `pydantic_settings`
- [ ] `pipeline.py full --help` e `bm_mockup_video.py --help` ok
- [ ] Sem migração em massa na mesma noite (2–3 scripts piloto)
