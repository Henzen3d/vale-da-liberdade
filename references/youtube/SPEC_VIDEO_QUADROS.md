# SPEC: Pipeline de Vídeo por Quadros — Vale da Liberdade (YouTube)

**Status:** Proposta para implementação — produção começa pelo **Brasil e Mundo** (§1.1.1)
**Depende de:** segmentação por quadro (followup_tracker.py no diário; mapeamento do `especial-{video_id}.json` no BM), script TTS estruturado, DashScope (geração de imagem), HyperFrames (camada de composição/render — seção 12), screenshot da matéria via Playwright (seção 8)
**Substitui:** thumbnail estática + waveform cobrindo o corpo inteiro do episódio
**Mantém:** vídeo de abertura fixo, vídeo de fechamento fixo (produzidos manualmente por Osmar)

---

## 0. Ideia central

Hoje o corpo do episódio é 1 imagem estática (thumbnail) + `showwaves`. A proposta é trocar por
um **slideshow editorial com Ken Burns effect (zoompan)**: 1 imagem por quadro/notícia, com pan/zoom
lento, crossfade entre quadros, e — opcionalmente — uma **faixa fina de waveform sobreposta na parte
inferior** para manter o feedback visual de "isso é áudio tocando". Isso é mais leve para a Intel HD
630 do que renderizar showwaves em tela cheia, porque a imagem estática não precisa ser recalculada
frame a frame — só o zoompan (barato) e a faixa de waveform (pequena).

Estrutura final do vídeo:

```
[intro fixo] → [quadro 1: zoompan + legenda + lower-third] → crossfade →
[quadro 2] → crossfade → ... → [quadro N] → [outro fixo]
```

> **Dois tipos de quadro** (ver §1 "campos opcionais" e §8):
> - **Quadro de notícia/slideshow** — 1 imagem editorial gerada (DashScope) + zoompan + lower-third.
>   É o formato desta seção 0.
> - **Quadro de comentário de matéria** — screenshot real da matéria + avatar do apresentador em
>   split 50/50 + citação da fonte. É o formato da seção 8 (e o mais comum no Brasil e Mundo).
> Ambos seguem a mesma timeline/funcionamento de quadros; mudam os assets por quadro.

---

## 1. Formato de segmentação — `quadros.json`

A segmentação em quadros vem do roteiro estruturado. No **diário**, o `followup_tracker.py` já
separa o roteiro por tópico/bloco. No **Brasil e Mundo**, o `especial-{video_id}.json` já nasce
dividido em `abertura`/`desenvolvimento`/`fechamento` (§1.1.1) — um mapeamento simples, sem o tracker.
Em ambos os casos o output precisa ser exportado neste schema, que vira o contrato entre o gerador
de roteiro/TTS e o gerador de vídeo:

```json
{
  "episode_id": "2026-08-07-vdl",
  "total_duration_ms": 1080000,
  "intro_video": "assets/intro_fixo.mp4",
  "outro_video": "assets/outro_fixo.mp4",
  "quadros": [
    {
      "id": "q01",
      "order": 1,
      "section": "blumenau",
      "chapter_label": "Blumenau",
      "start_ms": 0,
      "end_ms": 145000,
      "duration_ms": 145000,
      "script_text": "texto do trecho falado neste quadro...",
      "image_prompt": "prompt para o gerador de imagem",
      "image_path": "generated/q01.png",
      "quotable_score": 0.0
    }
  ]
}
```

`start_ms`/`end_ms` são relativos ao **corpo do episódio** (depois do intro), não ao arquivo final —
o gerador de vídeo soma a duração do intro na hora de montar a timeline.

**Campos opcionais por tipo de quadro** (o schema acima é a base comum; cada tipo de quadro soma os
seus):

- **Quadro de notícia/slideshow (padrão):** `image_path` + `image_prompt` (DashScope) — seção 2/3.
- **Quadro de comentário de matéria (§8):** `screenshot_materia` (PNG real da matéria), `fonte_nome`/
  `fonte_url` (citação, obrigatórios), `avatar_loop` (vídeo do apresentador em loop), `audio_narracao`
  (áudio do trecho) e `script_words_json` (timestamps por palavra). Alternativo a `image_path`: pode
  existir `video_path` quando o quadro for um vídeo gravado (ex.: leitor simulado, seção 9.3).
- **Qualquer quadro com dois apresentadores (§11):** `speaker_segments` — lista de `{speaker,
  start_ms, end_ms}` relativos ao início do quadro, para acender/apagar o indicador de fala ativa.

Os campos de fonte (`fonte_nome`/`fonte_url`) de um quadro de comentário vêm de
`fonte_referencias`/`fonte_veiculo` já gravados no roteiro pelo `bm_condensador.py`.

---

## 1.1 Dois formatos, dois papéis no funil — não confundir

Depois do piloto que o Hermes gerou usando o template padrão do HyperFrames ("faceless-explainer",
8 beats fixos, ~3min), ficou claro que existem **dois formatos de vídeo distintos**, cada um
respondendo a um objetivo diferente do funil. Não são a mesma coisa em durações diferentes — são
produtos com propósito diferente, e é importante não deixar que um vire "versão simplificada" do
outro por acidente de implementação.

### Formato A — Digest curto (aquisição)

- **Papel no funil:** descoberta. É pra quem nunca ouviu falar do Vale da Liberdade — precisa
prender atenção rápido e converter em inscrito/ouvinte novo.
- **Estrutura:** sequência fixa de beats editoriais (contexto → dados → desafios → fechamento →
CTA), ~3min, curadoria do dia — não é o episódio inteiro.
- **Produção:** roteiro **próprio**, curado especificamente pra esse formato — não é reaproveitamento
automático do script do TTS diário. Isso é trabalho editorial recorrente, não só técnico.
- **Métrica de sucesso:** CTR, impressões, retenção nos primeiros segundos — mede se está trazendo
gente nova.
- **Status:** piloto já existe (estrutura gerada pelo Hermes via template do HyperFrames). Caminho
mais rápido de validar primeiro, porque já está com scaffold pronto.

### Formato B — Episódio completo em vídeo (retenção)

- **Papel no funil:** retenção de quem já descobriu o canal (via Formato A, busca, ou já é ouvinte
do podcast e quer assistir). É o "episódio completo" pra quem já converteu o interesse inicial.
- **Estrutura:** quadros variáveis por editoria (seção 1 desta spec), duração igual ao áudio
(15-20min), intro/outro fixos, Peter e Ricardo.
- **Produção:** zero roteiro novo — reaproveita 100% o que o pipeline TTS diário já gera. É o mesmo
conteúdo do podcast em outra mídia, não um produto editorial paralelo.
- **Métrica de sucesso:** watch time / retenção ao longo do vídeo — mede se quem já era ouvinte
migra pro consumo em vídeo.
- **Status:** desenhado nas seções 1-11 desta spec, ainda não implementado.

### Por que separar isso agora, antes de implementar mais

Os dois formatos vão competir pela mesma capacidade de produção do Hermes. Sem decidir a ordem, o
risco é os dois avançarem pela metade ao mesmo tempo. **Recomendação: validar o Formato A primeiro**
— já tem scaffold pronto, é rápido de testar, e resolve o objetivo original de aquisição que motivou
essa frente toda. O Formato B entra depois, quando o canal já tiver alguma base de inscritos que
justifique pedir 15-20min de atenção de quem ainda não conhece o Vale da Liberdade.

Enquanto o Formato A estiver em teste, o Hermes não deveria misturar as duas lógicas no mesmo
projeto (`~/vale-da-liberdade-videos/vale-noticias/`) sem deixar explícito no `BRIEF.md` qual dos
dois formatos aquele projeto representa — evita que alguém tente "encaixar" a estrutura de quadros
dentro do template de 8 beats fixos, ou vice-versa, sem perceber que são propósitos diferentes.

### 1.1.1 Onde o Brasil e Mundo se encaixa

O **Brasil e Mundo (BM)** — a seção que está sendo implementada primeiro — é um **Formato B
reduzido**: episódio completo em vídeo (reaproveita 100% o roteiro/áudio que o `bm_pipeline.py`
já gera, zero roteiro novo), mas curto (~5 min, ~750-900 palavras, narração solo do Peter via
`bm_pipeline.py`), em vez dos 15-20 min do diário Peter+Ricardo.

Consequências práticas para esta spec quando aplicada ao BM:

- **Um só apresentador** → a seção 11 (indicador de fala de DOIS apresentadores) **não se aplica**
  ao BM; vale apenas o avatar único (seção 10 / §8). O `speaker_segments` não é necessário no BM
  (tudo é `peter`).
- **Os quadros do BM mapeiam direto do roteiro JSON** — o `especial-{video_id}.json` já tem
  `abertura` / `desenvolvimento` / `fechamento`, cada um uma lista de blocos `{speaker, texto}`.
  Regra de mapeamento: **1 quadro = 1 abertura; 1 quadro por bloco de `desenvolvimento` (ou 1 por
  grupo de 2-3 blocos se ficar curto demais para um quadro); 1 quadro de fechamento**. O
  `chapter_label` = tag temática do roteiro (ex.: "corrupção", "impostos").
- **Duração dos quadros** = soma das durações de fala dos blocos que agrupa (via `script_words_json`,
  seção 4), não um tempo fixo.
- **Quadros de comentário de matéria (seção 8)** são o caso mais comum aqui: cada notícia comentada
  mostra a screenshot real da matéria (do `fonte_url`/`fonte_referencias`) + avatar do Peter em split.

O BM é o **campo de prova ideal** para o pipeline por quadros: mais curto (render rápido), estrutura
já separada em quadros no JSON, e exercita de ponta a ponta o fluxo do HyperFrames (seção 12) antes
do diário completo.

> **Implementação do mapeamento (2026-08-10):** `scripts/bm_quadros_mapper.py` já materializa este
> mapeamento — lê `output/brasil_e_mundo/episodes/especial-{video_id}.json` e gera o `quadros.json`
> (1 abertura, 1 quadro por bloco de `desenvolvimento`, 1 fechamento; durações estimadas por
> proporção de palavras, com o áudio como fonte de duração total via ffprobe). Protótipo de
> validação: `references/youtube/prototype/quadros-PlBbhW6dR_Q.json` (episódio do enxofre).
> As durações por quadro passam a ser EXATAS quando o `script_words_json` (WordBoundary) existir (§4)
> — o mapper deve então sobrescrever os ms pelos timestamps reais em vez de estimar por palavras.

---

## 2. Formato do prompt de imagem por quadro

Regra prática: 1 chamada DashScope por quadro em vez de 1 por episódio. Para manter consistência
visual entre quadros (senão vira colcha de retalhos), fixem um **sufixo de estilo constante** que
entra em toda chamada, por exemplo:

```
"{tema do quadro}, editorial illustration style, muted amber and off-white palette,
minimalist, no text, no readable signage, 16:9"
```

Pontos de atenção:
- **Não gerar rostos de figuras públicas identificáveis** (políticos, autoridades) — além de ser
prática arriscada de imagem/IP, a maioria dos geradores recusa ou distorce. Prefiram simbolismo:
prédio público vazio para burocracia, gráfico caindo para inflação, cadeado/grade para regulação,
mercado de rua movimentado para mercado livre. Isso conversa naturalmente com a leitura ancap sem
precisar narrar.
- Guardem o `image_prompt` no `quadros.json` mesmo depois de gerada a imagem — vocês vão querer
regenerar ou fazer variações sem reconstruir o prompt do zero.

---

## 3. FFmpeg — zoompan + crossfade por quadro

> **Nota de implementação (2026-08-10):** com o HyperFrames escolhido (seção 12), esta seção
> descreve a abordagem de **referência** (ffmpeg puro via `filter_complex`). Nos quadros de
> **comentário de matéria**, a composição (zoompan + split + citação) é declarada em HTML no
> HyperFrames — mais fácil de manter. No corpo de notícias/slideshow, o teste de bancada (§12.2)
> decide entre ffmpeg puro ou HyperFrames conforme o custo de render. As receitas desta seção
> seguem válidas como baseline/fallback e para a concatenação final do assembly.

Cada quadro vira um clipe de vídeo próprio (imagem estática → zoompan), depois todos são concatenados
com `xfade`. Exemplo de filtro para 1 quadro (adaptem duração/fps):

```bash
ffmpeg -loop 1 -i q01.png -t 5 -vf \
"scale=1920:1080,zoompan=z='min(zoom+0.0008,1.15)':d=125:s=1920x1080:fps=25" \
-c:v libx264 -pix_fmt yuv420p q01_clip.mp4
```

Concatenação com crossfade entre pares consecutivos usa `xfade` (fade suave de ~0.5s), encadeado
via `filter_complex` — como o pipeline já usa `filter_complex` para overlay/drawtext, é extensão
natural do que existe, não tecnologia nova.

**Overlay animado com canal alfa (opcional, recomendado — substitui o waveform):** em vez de
`showwaves` em tempo real, sobrepor um loop de vídeo curto (partícula, textura, linha de luz sutil)
por cima do clipe já com zoompan aplicado. Mais barato pra CPU que `showwaves` (que recalcula a
forma de onda a cada frame) porque é só decodificação de um clipe curto repetido em loop:

```bash
ffmpeg -i q01_zoompan.mp4 -stream_loop -1 -i overlay_anim.webm \
-filter_complex "[0:v][1:v]overlay=0:0:shortest=1" \
-c:v libx264 -pix_fmt yuv420p q01_final.mp4
```

`-stream_loop -1` repete a animação em loop até acabar a duração do clipe principal, então funciona
independente da duração do quadro. Formato do asset de overlay:
- **WebM com alfa (VP9)** — preferido: leve, decodifica rápido, transparência com anti-aliasing
suave. É o formato que packs de overlay (partículas, poeira, luz) costumam já disponibilizar.
- **PNG sequence/APNG** — alternativa se for gerado internamente, mais pesado em disco.
- Evitar GIF puro: transparência binária (sem anti-aliasing) fica serrilhada em cima do movimento
do zoompan. Se só existir em GIF, tratar com `colorkey` (chroma key) — funciona, mas borda menos fina.

Se quiserem manter também o sinal "isso é áudio ao vivo", dá pra reservar o `showwaves` fino só para
momentos específicos (ex: trecho de citação direta) em vez de rodar o episódio inteiro — combina as
duas camadas sem pagar o custo do waveform full-time.

**Lower-third:** `drawtext` com o `chapter_label` do quadro (ex: "BLUMENAU"), usando a fonte da
marca assim que Osmar mandar o arquivo `.ttf`. Até lá, DejaVu Sans Bold serve de placeholder.

---

## 4. Legendas — SRT sincronizado

> **Consumo no HyperFrames (2026-08-10):** o `script_words_json` (timestamps por palavra) alimenta
> direto o **caption skin** do HyperFrames, que faz a legenda estilo karaoke por palavra (§12). A
> origem do dado é a mesma desta seção (WordBoundary do Edge TTS, sem Whisper) — muda só o consumo:
> em vez de (ou além de) gerar `.srt`, os timestamps vão para o caption do frame.

Edge TTS (biblioteca `edge-tts`) já emite eventos `WordBoundary` com offset em unidades de 100ns
durante a síntese — ou seja, dá pra gerar o SRT **sem** rodar Whisper, aproveitando o timestamp que
o TTS já calcula nativamente. Fluxo:

1. Capturar os eventos `WordBoundary` durante a chamada de síntese (já em uso no pipeline)
2. Agrupar palavras em blocos de ~8-12 palavras (padrão de legenda legível)
3. Exportar `.srt` com os timestamps agrupados
4. Anexar como legenda embutida (soft sub, `-c:s mov_text` para mp4) ou upload separado via
YouTube Data API — soft sub é mais simples e já cobre o objetivo de SEO/indexação

Isso é praticamente gratuito computacionalmente porque reaproveita dado que o TTS já produz.

---

## 5. Capítulos no description do YouTube

Gerado direto do `quadros.json`, somando a duração do intro a cada `start_ms`:

```
00:00 Abertura
02:15 Blumenau
08:40 Brasil e Mundo
14:20 Economia
17:50 Encerramento
```

Trivial de automatizar — é só formatar `intro_duration_ms + quadro.start_ms` como `mm:ss` e
concatenar com o `chapter_label`.

---

## 6. Seleção de trechos para Shorts

Cada quadro já tem `script_text`. Proposta de heurística simples para `quotable_score` (0 a 1), sem
precisar de outro modelo caro — pode rodar como pós-processamento do roteiro já gerado:

- Sentença isolada de 15-35s de fala (bate com o formato Shorts)
- Presença de marcadores de opinião forte (afirmação categórica, contraste "não é X, é Y",
pergunta retórica) — dá pra manter uma lista pequena de padrões linguísticos e pontuar por presença
- Preferência por trechos do Peter (perfil mais incisivo) quando empatar, já que tende a gerar mais
engajamento em corte curto

O quadro com maior `quotable_score` do episódio vira candidato automático a Short: reaproveita a
mesma imagem do quadro (zoompan em formato 9:16) + legenda burned-in (agora que existe SRT, é só
recortar a fatia correspondente).

---

## 7. Thumbnail do episódio (a estática, para o card do vídeo)

Mantém DashScope como está, mas soma uma camada `drawtext` com a manchete do dia (2-4 palavras,
fonte da marca, alto contraste) por cima da imagem gerada. Thumbnail sem texto compete mal contra
canais de notícia — o texto é o que garante leitura em 1 segundo de scroll.

---

## 8. Quadro "comentário de matéria" — abordagem adotada: screenshot real + avatar em split

> **Decisão (2026-08-10):** depois de ver referências reais do formato (Tim Pool, ancapsu), a
> abordagem que entra em produção é a mais simples e comprovada pelo mercado: **screenshot
> estática real da matéria do portal** (com o trecho-chave da manchete pré-selecionado via
> Playwright, **uma única captura** — não gravação contínua), exibida com **avatar em loop**,
> com citação da fonte sempre visível. É mais leve (sem navegador renderizando ao vivo
> durante o quadro inteiro), e mostrar a matéria real com a marca do portal, citando a fonte, é
> prática comum e aceita de comentário jornalístico.
>
> **REVISÃO DE DESIGN (2026-08-11, teste de bancada q02 v2):** o usuário reprovou o split
> 50/50 do v1 (avatar ocupando metade da tela, legenda quebrada no topo com sombra sobre o
> conteúdo, zero efeitos). A composição validada em produção passa a ser: **sem split** —
> navegador (browser chrome em HTML/CSS: abas + barra de endereço + URL) com a screenshot
> dentro e zoompan, avatar em **PiP circular ≤ 15% da largura** sobreposto ao canto inferior
> esquerdo do navegador, legenda **karaoke palavra a palavra** em lower third (timestamps do
> `script_words_json`), camadas de fundo animadas (glow/grid/anéis), selo de dado (ex. 50%),
> entradas/saídas em camadas. Detalhes no `prompt_hyperframes_comentario_materia.txt` e na
> composição `bancada-render/project/index.html` (gerada por `bancada-render/build_q02_composition.py`).
>
> **Implementação:** renderizado pelo HyperFrames (escolhido como camada de composição — seção 12),
> seguindo o prompt de referência `prompt_hyperframes_comentario_materia.txt` (placeholders
> `{{...}}` preenchidos pelo pipeline a partir do `quadros.json`).

**Captura da screenshot (implementada 2026-08-10):** `scripts/bm_screenshot_materia.py` (via
Playwright + playwright-stealth) abre a `fonte_url`, seleciona o trecho-chave da manchete (destaque de
texto) e captura a região editorial do artigo (`article`/`main`) em 1920x1080. Protótipo validado num
episódio real: `references/youtube/prototype/generated/q02_screenshot.png`.

> **PITFALL (2026-08-10):** captura do site do portal pode esbarrar em **anti-bot/403** mesmo com
> stealth — o `nationalinterest.org` (fonte principal deste episódio) retornou 403 bloqueando o
> headless; a **CNBC** (também referência do roteiro, `fonte_referencias`) carregou normalmente. Regra
> de fallback: quando a fonte principal está bloqueada, usar como `screenshot_materia` uma das
> referências ACESSÍVEIS (`fonte_referencias`) do mesmo episódio; a citação na tela passa a exibir a
> fonte da captura real. Se nenhuma referência for acessível, cair para o leitor simulado próprio (§9).
> É exatamente o risco que a §9 antecipa — a screenshot real é o caminho preferido, mas **não é um
> requisito rígido de qualidade de produção** se o portal não cooperar.

O que o pipeline disponibiliza por quadro de comentário (novos campos no `quadros.json`, seção 1):

- `screenshot_materia` — PNG da captura real da matéria (gerada 1× via Playwright ANTES do render, não ao vivo). O trecho-chave da manchete vem já selecionado (texto destacado) na captura.
- `avatar_loop` — vídeo curto (5-10s) do apresentador em pose "lendo/concentrado", para loop de fundo. **Não é talking-head**: não há sincronização de boca com o áudio. Cenário: o avatar pode ser o próprio apresentador (Peter/Ricardo) ou um avatar sintético, conforme o asset que Osmar entregar.
- `fonte_nome` / `fonte_url` — metadado do portal citado, SEMPRE exibido como citação na tela (nunca omitir).
- `audio_narracao` + `script_words_json` — áudio do trecho + timestamps por palavra (WordBoundary do Edge TTS).

### 8.1 (descartado) — leitor simulado com scroll contínuo (Playwright)

> **Descartado como método primário de produção do quadro.** Fica como alternativa SOMENTE
> quando/onde o objetivo for a página do leitor servir também como conteúdo vivo do portal
> (seção 10.2) — os dois não são mutuamente exclusivos, são casos de uso diferentes:
> produção de vídeo usa a screenshot estática (§8); página viva do portal usa o mockup (§9).

O raciocínio que motivou o mockup segue válido como princípio: em vez de navegar e gravar o site
real do portal (frágil: cookie banner, paywall, ads intersticiais quebram a automação; e arriscado:
exibir layout/marca de terceiro em vídeo monetizado é terreno cinzento de direito autoral), recriar
um **leitor próprio em HTML** com a identidade visual de vocês, alimentado pelo texto que o pipeline
já extrai da matéria. A automação (mouse, seleção, scroll) roda em cima desse HTML controlado por
vocês, não do site do portal — detalhado na seção 9.

## 9. Variante: leitor simulado e suíte de gráficos broadcast (Mockup Browser V2)

> **DIRETRIZ DE DESIGN & IDENTIDADE (SET/2026):**
> O ambiente visual do mockup browser e dos componentes broadcast adota formalmente o **Light Editorial Studio Standard** (design claro / estúdio diurno prime, inspirado em CNN, Bloomberg e BBC).
> É **obrigatório** manter fundos claros/brancos com tipografia em preto editorial para assegurar máxima legibilidade em telas de TV e mobile, além de perfeita separação com o apresentador Peter Albuquerque e integração com o Lower Third.
> Documentação técnica e tokens completos: [`mockup-browser/LIGHT_BROADCAST_DESIGN_SYSTEM.md`](file:///references/youtube/mockup-browser/LIGHT_BROADCAST_DESIGN_SYSTEM.md).

Em vez de navegar e gravar o site real do portal, recriar um **leitor próprio em HTML** com a
identidade visual de vocês, alimentado pelo texto que o pipeline já extrai da matéria.

### 9.1 Mockup HTML do leitor

Página estática simples — título da matéria, fonte/link do portal citado no rodapé (prática normal
de comentário jornalístico), corpo do texto extraído, tipografia e cor da marca:

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<style>
  body { font-family: 'MarcaFont', Georgia, serif; background: #0D1B2A; color: #f2f2f2;
         max-width: 760px; margin: 0 auto; padding: 60px 40px; line-height: 1.7; font-size: 22px; }
  h1 { font-size: 34px; color: #e8a23d; margin-bottom: 8px; }
  .fonte { color: #999; font-size: 15px; margin-bottom: 40px; }
  ::selection { background: #e8a23d; color: #0D1B2A; }
</style>
</head>
<body>
  <h1 id="titulo">{{titulo_materia}}</h1>
  <div class="fonte">Fonte: {{nome_portal}} — {{url_original}}</div>
  <div id="corpo">{{texto_extraido}}</div>
</body>
</html>
```

O `{{texto_extraido}}` já existe no pipeline (é o mesmo texto usado para gerar o roteiro/TTS da
matéria), então não é extração nova — é reaproveitamento do dado.

### 9.2 Script de leitura simulada (Playwright)

```python
from playwright.sync_api import sync_playwright
import time, random

def gravar_leitura(html_path: str, output_video_dir: str, duracao_s: int):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=output_video_dir,
            record_video_size={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        page.goto(f"file://{html_path}")
        page.wait_for_timeout(800)

        corpo = page.locator("#corpo")
        box = corpo.bounding_box()

        # scroll gradual simulando leitura, com pausas variáveis
        passos = int(duracao_s / 1.2)
        for i in range(passos):
            delta = random.randint(35, 70)
            page.mouse.wheel(0, delta)
            page.wait_for_timeout(random.randint(900, 1500))

            # a cada ~3 passos, seleciona um trecho pra dar ênfase visual
            if i % 3 == 0:
                x = box["x"] + random.randint(40, 200)
                y = box["y"] + random.randint(20, 400)
                page.mouse.move(x, y, steps=15)
                page.mouse.down()
                page.mouse.move(x + random.randint(200, 400), y, steps=10)
                page.mouse.up()
                page.wait_for_timeout(600)

        context.close()
        browser.close()
```

Pontos de ajuste fino:
- `steps=` nos `mouse.move` controla a suavidade — mais steps, movimento mais fluido
- A pausa aleatória entre scrolls (`900-1500ms`) é o que evita parecer "robótico" — scroll constante
sem variação é o principal tell de automação
- `duracao_s` deve casar com a duração daquele quadro no `quadros.json`, pra sincronizar com o áudio

### 9.3 Onde isso entra na timeline do episódio

O `.webm` gerado pelo Playwright vira um clipe de vídeo como outro qualquer — entra no lugar de um
quadro com `image_path`/`screenshot_materia` no schema da seção 1 (campo alternativo `video_path`),
seguindo o mesmo crossfade com os quadros vizinhos. No fluxo padrão de hoje (§8) ele é **opcional**:
a screenshot estática já cobre o quadro de comentário sem precisar desta gravação.

### 9.4 Observação sobre atribuição

Mesmo usando o mockup próprio (que já resolve o risco de exibir o layout do portal), mantenham a
citação clara da fonte visível na tela (nome do portal + link) durante todo o quadro — é prática
padrão de comentário jornalístico e reforça que o conteúdo é comentário autoral sobre a matéria, não
reprodução dela.

---

## 10. Avatar em PiP circular + conteúdo único (HTML vivo)

> **Dois empregos do avatar (não confundir):**
> - **Split 50/50 / tela cheia** — usado no quadro de **comentário de matéria** (§8): o avatar
>   ocupa uma metade (ou a tela toda na abertura do quadro), é reenquadrado e centralizado, em loop
>   contínuo. É o caso dirigido pelo prompt `prompt_hyperframes_comentario_materia.txt`.
> - **PiP circular no canto** (esta seção) — usado como "sugestão de alguém presente" durante
>   quadros que NÃO são de comentário (ex.: corpo editorial de um Formato B), e onde o avatar deve
>   ficar discreto no canto. Pequeno e de canto, pequenas dessincronias boca/áudio passam
>   despercebidas — não resolve lipsync.

Para dar a sensação de "alguém no quadro" sem depender de lipsync real, um avatar em vídeo curto
(5-10s, gravado uma vez) roda em loop dentro de um círculo pequeno no canto do quadro.

### 10.1 Composição — máscara circular estática (barata)

Mais barato que recalcular uma expressão de máscara por pixel (`geq`) é usar uma **PNG de máscara
pré-gerada uma única vez** (círculo branco sobre preto) combinada via `alphamerge`:

```bash
ffmpeg -stream_loop -1 -i avatar_loop.mp4 -i mask_circle.png -i base_video.mp4 \
-filter_complex "
[0:v]scale=220:220,format=yuva420p[av];
[1:v]scale=220:220,format=gray[mask];
[av][mask]alphamerge[circle];
[2:v][circle]overlay=W-240:H-240:shortest=1
" -c:v libx264 -pix_fmt yuv420p out.mp4
```

- `mask_circle.png` (220x220, gerado uma vez via Pillow) é asset reutilizável para sempre
- `-stream_loop -1` faz o avatar rodar em loop independente da duração do quadro
- Um anel fino na cor da marca (outro PNG estático com furo transparente) pode ser somado por cima
para acabamento de "moldura de podcast"
- Uma pequena biblioteca de 3-5 loops diferentes, escolhidos por rotação entre episódios, evita
repetição visual sem precisar gravar um vídeo novo a cada episódio

### 10.2 Conteúdo único, dois consumidores (evita divergência e trava de deploy)

Como o HTML do leitor (seção 9) também vai servir como página real do portal, o fluxo correto **não**
é gerar o HTML só pro Playwright gravar — é gerar um **payload de conteúdo único** que alimenta os
dois destinos:

```
payload de conteúdo (título, fonte, corpo, slug)
        │
        ├──► template local → gravação Playwright (rápida, sem depender de rede/deploy)
        └──► mesma página publicada no portal (Astro/Cloudflare) com URL própria
```

Por que gravar do HTML local em vez da URL de produção: gravar direto da URL publicada tornaria o
cron noturno dependente do deploy já estar no ar e de latência de rede — ponto de falha desnecessário
numa pipeline que roda desassistida de madrugada. Gerar local primeiro, publicar em paralelo, resolve.

Ganho estratégico: cada matéria comentada vira uma página indexável do portal — funciona como landing
page de aquisição (busca orgânica ou link na descrição do YouTube → leitura no portal → app), fechando
o funil de "novos ouvintes no app" que motivou essa frente toda.

---

## 11. Dois apresentadores — destaque de fala ativa

Hoje a maioria dos canais do gênero usa 1 avatar fixo. Com Peter e Ricardo Souto (já com vozes
diferenciadas no pipeline de TTS), dá pra ir além do avatar único e fazer o PiP se comportar como
**indicador de quem está falando**, no estilo "chamada de vídeo" — isso é diferencial visual real
frente à concorrência de host único, e o dado que aciona isso **já existe**: o pipeline de
diferenciação de voz já marca cada linha do roteiro com o apresentador correspondente.

### 11.1 Layout

Dois círculos lado a lado no canto (em vez de um), cada um com o loop do respectivo avatar, com um
rótulo curto abaixo (mesmo padrão visual do lower-third da seção 3 — nome em caps, barra de cor):

```
                                    ┌────┐┌────┐
                                    │ 🗣️ ││ 👤 │
                                    └────┘└────┘
                                    PETER  RICARDO
```

Quem está falando ganha um leve destaque (anel âmbar mais forte + leve escala/glow); quem está em
silêncio fica com o anel apagado e levemente escurecido — igual ao indicador de "falando agora" de
chamada de vídeo, só que automático, dirigido pelo roteiro.

### 11.2 Dado necessário — reaproveitamento do que já existe

Não é dado novo: é exportar o mesmo marcador de apresentador que já decide qual voz o Edge TTS usa
por linha, como uma lista de segmentos por quadro:

```json
{
  "id": "q03",
  "speaker_segments": [
    { "speaker": "peter", "start_ms": 0, "end_ms": 4200 },
    { "speaker": "ricardo", "start_ms": 4200, "end_ms": 9800 },
    { "speaker": "peter", "start_ms": 9800, "end_ms": 14000 }
  ]
}
```

`start_ms`/`end_ms` aqui são relativos ao início do quadro (mesma referência da seção 1).

### 11.3 FFmpeg — alternando o destaque por segmento

O truque é usar a expressão `enable=` do `overlay`, que aceita soma de condições `between()` como OR
(qualquer valor diferente de zero conta como verdadeiro). Cada apresentador tem seu próprio overlay de
"anel aceso", visível só nos trechos em que é a vez dele:

```bash
ffmpeg -i base.mp4 -i peter_circle.mp4 -i ricardo_circle.mp4 \
-i peter_ring_lit.png -i ricardo_ring_lit.png \
-filter_complex "
[0:v][1:v]overlay=W-460:H-240[base1];
[base1][2:v]overlay=W-240:H-240[base2];
[base2][3:v]overlay=W-460:H-240:enable='between(t,0,4.2)+between(t,9.8,14)'[base3];
[base3][4:v]overlay=W-240:H-240:enable='between(t,4.2,9.8)'
" -c:v libx264 -pix_fmt yuv420p out.mp4
```

Os dois primeiros overlays desenham os círculos sempre visíveis (base). Os dois últimos desenham só
o anel aceso, aparecendo e sumindo nos intervalos certos — gerados automaticamente a partir do
`speaker_segments`, sem precisar editar isso na mão por episódio.

### 11.4 Nível mais simples, se quiserem começar por aí

Se topar começar simples antes de ir pro indicador dinâmico: **um círculo só, que troca de avatar por
segmento** (em vez de dois círculos com anel dinâmico) — mesma lógica de `enable=between()`, só que
trocando qual vídeo de avatar aparece em vez de acender/apagar anel. Menos impressionante visualmente,
mas mais rápido de implementar e já resolve "dois apresentadores" sem a complexidade dos dois círculos
simultâneos.

---

## 12. HyperFrames (HeyGen) — camada de composição/render escolhida

**Decisão (2026-08-10):** o HyperFrames é a **ferramenta escolhida** como camada de composição/render
para os quadros de vídeo — em particular o quadro de **comentário de matéria** (§8), cujo prompt de
referência (`prompt_hyperframes_comentario_materia.txt`) já o usa. NÃO é mais "avaliar". O que
permanece em aberto são apenas os **testes de bancada de custo (tempo/RAM)** na máquina de vocês
(§12.2), não a decisão de adoção.

Ferramenta feita para agentes: composição em HTML/CSS (animações via GSAP/Lottie), preview com hot
reload, e render por captura frame a frame em Chrome headless (`frame = floor(time * fps)`) piped
para ffmpeg. Para os casos previstos nesta spec, ele cobre de forma nativa o que planejamos
construir do zero em `filter_complex`:

| Caso previsto nesta spec | Como o HyperFrames atende |
|---|---|
| Zoompan + lower-third + crossfade (seção 3) | Composição declarativa em HTML/CSS + animação GSAP — mais fácil de manter que `filter_complex` cru |
| Split 50/50 avatar + screenshot + citação da fonte (seção 8) | Layout declarativo (flex/grid) com o avatar em `<video>` em loop e a screenshot em `<img>` + zoompan do quadro |
| SRT / legenda palavra a palavra (seção 4) | `caption skin` nativo com transição karaoke (estilo por palavra), consumindo os timestamps do WordBoundary |
| Trilha de fundo (pendência do Hermes) | Geração de BGM multi-provider (Google Lyria / MusicGen local) |
| Máscara circular do avatar (seção 10) | Remoção de fundo nativa no pipeline de pré-processamento de asset |

### 12.1 Instalação

```bash
npx skills add heygen-com/hyperframes --full-depth
```

`--full-depth` é obrigatório para instalar a versão atual do repositório — sem essa flag, o comando
busca o blob do registro `skills.sh`, que atrasa horas em relação ao `main`. Para ambiente não
interativo (cron, agente sem terminal), preferir:

```bash
npx hyperframes skills update
```

que instala exatamente o conjunto "core" sem abrir o seletor interativo.

### 12.2 Teste de bancada — resultados reais (2026-08-10)

**Custo medido de 1 quadro de comentário (32s, 1920×1080, 30fps, quality high), render local
software (llvmpipe, sem GPU):**

| Métrica | Medido | Nota |
|---|---|---|
| Tempo de render | **~95s** (1:34) para 960 frames | ~1s de wall-clock por 10 frames |
| Pico de RAM | **~552 MB** (564.944 KB RSS) | Chrome headless + ffmpeg |
| CPU | 91,4s user + 12,3s system | proporcional aos frames |
| Output | `q02_bancada.mp4` · 8,56 MB · H.264+AAC · 32.0s | válido, passou `check` |

**Leitura do resultado para o escopo:**

- **Custo escala com a DURAÇÃO (frames), não com o nº de quadros.** 32s → ~95s de render. Um
  episódio BM completo tem ~300s de áudio → ~9.000 frames → **~15 min de render só do HyperFrames**.
  É aceitável para o cron da madrugada (o diário de 18min renderiza em poucos min via ffmpeg puro,
  mas o vídeo por quadros do BM é a jornada; cabe testar se 15 min por episódio BM comporta a fila).
- **RAM ~552 MB cabe** nos 7,6 GB da máquina, mesmo somado ao resto do pipeline.
- **Render headless desassistido confirmado** — rodou sem interação, com `npx hyperframes render
  --quality high --output ...` (documentação para agente/CI procede na prática).
- **Decisão de escopo:** o HyperFrames entra onde o ganho visual justifica o custo — os **quadros de
  comentário de matéria** (§8). Para o **corpo de notícias/slideshow** (imagem + zoompan + lower-third,
  §5 da tabela), o **ffmpeg puro continua preferível** (custo menor e sem Chrome), reservando o
  HyperFrames para os quadros que realmente precisam de composição declarativa (split, avatar,
  karaoke).

> Regra mantida: a decisão de adoção (HyperFrames SIM para quadros de comentário) está fechada.
> O teste de bancada definiu o **escopo**: HyperFrames nos quadros de comentário; ffmpeg puro no
> corpo de slideshow de notícia.

---

## 13. Prioridade de implementação sugerida

**Sequência de produção:** o **Brasil e Mundo** (seção 1.1.1) é o primeiro caso de produção do
pipeline por quadros. Fluxo recomendado de implementação, com o HyperFrames já escolhido (seção 12):

| Ordem | Item | Depende de |
|---|---|---|
| 0 | Teste de bancada do HyperFrames (tempo/RAM vs. ffmpeg puro) — decide só o escopo, não a adoção (§12.2) | Nada — roda isolado |
| 1 | `quadros.json` schema + export para o BM (mapear `especial-{id}.json` → quadros, seção 1.1.1) | Ajuste no `bm_condensador.py` / novo script de mapeamento |
| 2 | Screenshot da matéria via Playwright (1 captura por quadro de comentário, trecho pré-selecionado) | Campo `screenshot_materia` no quadros.json |
| 3 | Prompt `prompt_hyperframes_comentario_materia.txt` operacional: quadro de comentário (split avatar + screenshot + citação) no HyperFrames | Itens 1 e 2 + loop de avatar (gravação do Osmar) |
| 4 | SRT/legenda karaoke via WordBoundary (consumido pelo caption skin do HyperFrames) | Nada novo — só capturar evento já emitido |
| 5 | Slideshow zoompan + crossfade para quadros DE NOTÍCIA (não-comentário) | DashScope por quadro |
| 6 | Capítulos no description do YouTube | quadros.json pronto |
| 7 | Shorts automáticos (recorte 9:16 do quadro de maior `quotable_score`) | SRT + quadros.json prontos |
| 8 | Faixa de waveform fina sobreposta (sinal de áudio ao vivo, opcional) | Item 5 pronto |
| 9 | Payload de conteúdo único (página viva do portal via leitor simulado, seção 9) | Caso de uso de portal, separado do vídeo |
| 10 | Avatar PiP circular para o corpo dos Formatos A/B (single, sem indicador de fala) | Gravação do loop de avatar (Osmar) |
| 11 | Indicador de fala ativa (dois apresentadores) — diário Peter+Ricardo, NÃO aplicável ao BM | Item 10 pronto + export de `speaker_segments` |

O BM não espera os itens 10/11 (são do diário). Para o BM, o caminho crítico é: **1 → 2 → 3** (um
quadro de comentário inteiro renderizado no HyperFrames), depois 4 e 6 para fechar o episódio publicável.
Itens 1, 2, 4 e 6 não dependem de nenhum asset visual novo — dá pra o Hermes prototipar já no próximo
episódio em paralelo com você produzindo fonte/logo/cores/trilha e o loop de avatar.
