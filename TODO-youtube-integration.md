# TODO: Integração de Vídeos do YouTube no Web Jornal

## Prioridade: Baixa (Futuro)
## Status: Aguardando crescimento do serviço

## O que fazer
Integrar vídeos do YouTube como fonte de conteúdo para o web jornal.
Permite gerar episódios a partir de transcrições de vídeos.

## Contexto
- YouTube Skills instalado em `~/.hermes/skills/youtube-full/`
- Funcionalidades:
  - Extrair transcrições de vídeos
  - Pesquisar vídeos no YouTube
  - Navegar em canais
  - Ler playlists
  - **Sem necessidade de API key do Google**
- Powered by TranscriptAPI (100 credits grátis no signup)

## Casos de Uso Futuros
1. **Reportagens baseadas em vídeos** — encontrar vídeos sobre notícias locais/regionais
2. **Análise de conteúdo** — transformar vídeos de opinião em roteiros de podcast
3. **Fonte alternativa** — quando notícias tradicionais não cobrem um tema
4. **Conteúdo especial** — episódios derivados de documentários, interviews, etc.

## Como funciona
```bash
# Extrair transcrição
transcript video_url

# Pesquisar vídeos
youtube_search "notícias Blumenau"

# Listar vídeos de um canal
channel_videos "UCxxxx"

# Listar playlist
playlist_videos "URL_DA_PLAYLIST"
```

## Integração com o Pipeline
Quando implementado:
1. Scout procura vídeos relevantes sobre temas do Vale do Itajaí
2. Extrai transcrição com youtube-skills
3. Gera roteiro JSON usando `build_script_prompt()`
4. Processa e gera áudio normalmente

## Próximos Passos (quando houver crescimento)
- [ ] Configurar API key do TranscriptAPI (grátis, 100 credits)
- [ ] Criar script de busca de vídeos relevantes
- [ ] Integrar ao pipeline de geração de roteiro
- [ ] Adicionar validação de qualidade da transcrição
- [ ] Testar com vídeos reais do tema

## Dependências
- `youtube-full` skill já instalada
- TranscriptAPI account (signup gratuito)

## Referências
- Repo: https://github.com/ZeroPointRepo/youtube-skills
- API: https://transcriptapi.com
- Docs: https://transcriptapi.com/docs

---
Criado em: 2026-07-31
Atualizado: 2026-07-31
