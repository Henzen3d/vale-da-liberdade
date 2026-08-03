# Deploy — radio.mob.tec.br (Cloudflare Tunnel + RSS Spotify)

## Visão

```
Internet → Cloudflare (radio.mob.tec.br)
        → cloudflared container
        → nginx (public/)
             ├── index.html (PWA)
             ├── feed.xml   ← Spotify / Apple / Google / Pocket Casts
             ├── feed.json
             └── audio/*.mp3
```

## 1. Variáveis no `.env` do projeto

```bash
SITE_URL=https://radio.mob.tec.br
PODCAST_EMAIL=contato@mob.tec.br
# Token do túnel (Zero Trust → Tunnels → Configure → Install connector)
CLOUDFLARE_TUNNEL_TOKEN=eyJ...
```

## 2. Criar túnel no Cloudflare

1. Acesse [Cloudflare Zero Trust](https://one.dash.cloudflare.com/) → **Networks → Tunnels**
2. **Create a tunnel** → Cloudflared → nome `vale-liberdade`
3. Copie o **token** para `CLOUDFLARE_TUNNEL_TOKEN`
4. **Public Hostname**:
   - Subdomain: `radio`
   - Domain: `mob.tec.br`
   - Type: `HTTP`
   - URL: `web:80`  
     (nome do serviço no `docker-compose.yml`)

> Se o connector rodar **fora** do compose (host), use `http://127.0.0.1:8090` em vez de `web:80`.

## 3. Publicar catálogo + RSS

```bash
cd /home/osmar/web-jornal-vale-da-liberdade
export $(grep -v '^#' .env | xargs -d '\n')   # carrega SITE_URL
python3 scripts/publish_site.py
```

Isso gera:
- `public/data/episodes.json`
- `public/feed.xml`  ← **envie este URL ao Spotify**
- `public/feed.json`
- `public/audio/*.mp3`

## 4. Subir o site

```bash
cd deploy
# garanta CLOUDFLARE_TUNNEL_TOKEN no ../.env ou exporte
set -a; source ../.env; set +a
docker compose up -d
curl -sI http://127.0.0.1:8090/healthz
curl -sI http://127.0.0.1:8090/feed.xml
```

## 5. Enviar para Spotify (e outros)

Quando `https://radio.mob.tec.br/feed.xml` responder 200:

| Plataforma | Onde colar o RSS |
|------------|------------------|
| **Spotify for Podcasters** | https://podcasters.spotify.com/ → Add show → RSS |
| **Apple Podcasts Connect** | https://podcastsconnect.apple.com/ |
| **Amazon Music / Audible** | https://podcasters.amazon.com/ |
| **Pocket Casts** | submit via their directory form |
| **Google Podcasts** | descontinuado; use YouTube/RSS partners |

RSS público:
```
https://radio.mob.tec.br/feed.xml
```

Capa do podcast (1400×1400):
```
https://radio.mob.tec.br/assets/cover.jpg
```

## 6. Automação diária

O `pipeline.py full` já chama `publish_site` na etapa 7.
Depois do áudio do dia, o feed e o site atualizam sozinhos.

## Checklist Spotify

- [ ] `feed.xml` acessível em HTTPS público
- [ ] `<enclosure url="https://...mp3" type="audio/mpeg" length="...">`
- [ ] `<itunes:image href="https://.../assets/cover.jpg">` (mín. 1400px)
- [ ] Idioma `pt-BR`, `itunes:explicit`, `itunes:owner` com e-mail válido
- [ ] Pelo menos 1 episódio com áudio > 1 MB
- [ ] DNS `radio.mob.tec.br` apontando via túnel (proxied)

## Troubleshooting

```bash
docker compose -f deploy/docker-compose.yml logs -f cloudflared
docker compose -f deploy/docker-compose.yml logs -f web
curl -sI https://radio.mob.tec.br/feed.xml
```

Se o túnel estiver UP mas o hostname 404: confira o **Public Hostname** no dashboard (service `http://web:80` na mesma rede Docker).
