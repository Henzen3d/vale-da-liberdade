# VALIDAÇÃO VISUAL MANUAL — Pós-auditoria 2026-08-08
Local: http://127.0.0.1:8090  ou  https://news.mob.tec.br
Objetivo: confirmar que as 37 correções não quebraram layout nem fluxo do player.

Antes de começar: force recarga SEM cache (Ctrl+Shift+R) 2×, e em aba limpa (ou DevTools > Application > Service Workers > Update + Unregister + reload) para garantir SW novo (vld-v1-202608081535).

---

## BLOCO 1 — Player / Autoplay (fix A1 do duplo autoplay)
- [ ] 1.1 Dar play num episódio (card do feed OU hero) → toca áudio, mini + full player atualizam.
- [ ] 1.2 Deixar o episódio TERMINAR (pular pro fim) → deve avançar para o próximo SEM áudio duplo.
- [ ] 1.3 No fim, verificar se aparece o AD interstitial limpo (sem som do episódio por trás).
- [ ] 1.4 Pular o anúncio (após countdown) → próximo episódio toca normalmente.
- [ ] 1.5 Repetir 1.2–1.4 na TAB Brasil e Mundo (autoplay + ad também funcionam lá).
- [ ] 1.6 Botão "Próximo" (#fullNextEp) no full player → também passa pelo ad (não pula direto).
- [ ] 1.7 Fim da fila da tab → para sozinho (sem loop, sem erro).
- [ ] 1.8 Contador de views: uma transição automática deve contar 1 view (não 2).

---

## BLOCO 2 — Layout / Navegação (não regredir)
- [ ] 2.1 Feed da home renderiza igual (cards, herói, rail "Continuar ouvindo", abas Diário/Brasil e Mundo).
- [ ] 2.2 Abas, busca, drawer lateral, tema claro/escuro — todos funcionando.
- [ ] 2.3 Mini player (barra inferior) e full player (expandir) abrem/fecham sem quebrar.
- [ ] 2.4 Responsivo: testar celular (390px) e desktop (1280px) — sem estouro de layout.
- [ ] 2.5 Botões de ação do feed (play/share/copy/like) continuam agrupados colados ao card.

### Carrossel "Continuar ouvindo" — NOVO (desktop)
- [ ] 2.6 No DESKTOP (≥768px), quando houver mais itens no rail que cabem na tela, devem aparecer **setas ‹ ›** à direita do título "Continuar ouvindo".
- [ ] 2.7 Clique em "›" rola suavemente para o próximo card (e fica desabilitada no fim); clique em "‹" volta (desabilitada no início).
- [ ] 2.8 Com poucos itens (sem overflow), as setas NÃO aparecem.
- [ ] 2.9 No mobile (<768px), as setas ficam ocultas (drag/touch já rola) e nada quebra.

---

## BLOCO 3 — Offline (fix A2 + A3)
- [ ] 3.1 Abrir https://news.mob.tec.br/offline.html direto → DEVE ter estilo (fundo, fontes, botão) — antes era sem CSS.
- [ ] 3.2 DevTools > Network > Offline (ou modo avião) → recarregar o site → mostra o estado offline com banner "Tentar de novo" e conteúdo em cache.
- [ ] 3.3 Imagens que faltam (404) devem dar erro de imagem, NÃO virar HTML de offline.html (A3).

---

## BLOCO 4 — Admin + SEO (não quebrar)
- [ ] 4.1 Abrir /admin/ → login Google funciona; botões com type="button" não disparam submit acidental.
- [ ] 4.2 Modal do admin abre/fecha (aria-label "Fechar modal" aplicado sem quebrar o ×).
- [ ] 4.3 Confirmar no <head> da home: <link rel="canonical"> e favicon 32px presentes.
- [ ] 4.4 PWA: DevTools > Application > Manifest → instalável (ícones 192/512 + maskable 192).

---

## BLOCO 5 — Console / Erros
- [ ] 5.1 Console do browser: 0 erros (warns de ads/SW aceitáveis; erros NÃO).
- [ ] 5.2 Navegar pelas 4 tabs + 1 autoplay + 1 compartilhar → console limpo.

---

## BLOCO 6 — Preview de compartilhamento (WhatsApp/Telegram) — NOVO 2026-08-08
- [ ] 6.1 Compartilhar um episódio (botão share/copy do app) → o link gerado agora é `https://news.mob.tec.br/ep/<id>.html`.
- [ ] 6.2 Colar esse link num chat do WhatsApp (ou usar uma ferramenta de teste de OG) → o card mostra o **título do episódio + resumo + thumbnail do episódio** (não mais o genérico do canal).
- [ ] 6.3 Testar com um episódio diário E um especial B&M (ex.: `ep/2026-08-07.html` e `ep/especial-*.html`).
- [ ] 6.4 Clicar no card/preview → abre o player no episódio certo (redireciona de `/ep/<id>.html` → `/?ep=<id>` e dá play).
- [ ] 6.5 Nota: links `?ep=` já enviados ANTES desta mudança continuam mostrando o preview genérico — só os novos (via `/ep/`) têm preview correto.
- [ ] 6.6 (Opcional, se quiser testar o crawler) abrir `news.mob.tec.br/ep/2026-08-07.html` direto no navegador → deve redirecionar para o player no episódio.

---

## GATE FINAL
- [ ] Layout idêntico ao validado antes da auditoria (sem regressão visual).
- [ ] Autoplay sem áudio duplo (fix A1 OK).
- [ ] Página offline com estilo (fix A2 OK).
- [ ] Console 0 erros.

Se qualquer item falhar: anote a tela/etapa e cole o erro do console aqui.
*Gerado por Hermes Agent | 2026-08-08 | acompanha archive/handoffs/AUDIT-2026-08-08-frontend.md*
