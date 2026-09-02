# Path canônico — Vale da Liberdade

**Único diretório do projeto:**

```
/home/osmar/web-jornal-vale-da-liberdade
```

`liberdade` = **d** antes do **e**. Sempre.

## Alucinações proibidas

Não criar, não ler, não escrever nestes nomes:

- `web-jornal-vale-da-liberdage`
- `web-jornal-vale-da-liberdafe`
- `web-jornal-vale-da-liberdarg`
- qualquer outra variação

Se um comando falhar com “No such file”, o path está errado. Não inventar pasta nova.

## Onde está o quê

| Artefato | Path |
|---|---|
| Player web | `public/assets/js/player.js` |
| App | `public/assets/js/app.js` |
| Site | `public/index.html` |
| Login Google | `public/js/supabase_client.js` (injeta `#auth-container`) |
| Catálogo | `public/data/episodes.json` |
| Teste background (sem OAuth) | `public/player-test.html` |
| Pipeline BM | `scripts/bm_*.py` |
| Composição HyperFrames | `references/youtube/prototype/bancada-render/build_episode_composition.py` |
| Skill de produção | `~/.hermes/skills/content/web-jornal-production/SKILL.md` |
| Índice de docs | `docs/INDEX.md` |
| Mapa VIVO / MORTO | `docs/INDEX.md` (tabelas) e `SYSTEM_MAP.md` |

Não usar como spec de produção: `ARCHITECTURE.md`, `ROADMAP.md`, `docs/PIPELINE_SCRIPTS_INVENTORY.md` (histórico Junho/Agosto 2026).

## Teste local do player

```bash
cd /home/osmar/web-jornal-vale-da-liberdade/public
python3 -m http.server 8077 --bind 0.0.0.0
# http://<LAN>:8077/player-test.html
```

Não usar porta 8080 (Kong). Não servir de pasta com typo.
