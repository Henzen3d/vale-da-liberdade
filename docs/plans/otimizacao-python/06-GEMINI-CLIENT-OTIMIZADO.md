# 06 — Gemini Client (gemini_client.py)

**Impacto**: Alto **risco**, ganho de latência pequeno neste host
**Scripts**: `gemini_client.py` (688 linhas) + importadores (TTS, roteiro, título, descrição, thumb prompt, BM)
**Persistência viva**: `sources/gemini_usage.json` + `_meta.rr_index`
**Nesta onda: NÃO migrar para SQLite.**

---

## Alinhamento

O retry 30× 0.02–0.1 s é comentário **Windows** (`PermissionError` no `unlink`+`rename`). Este host é Linux: `rename` é atômico no mesmo filesystem. O `unlink` antes do `rename` **é** a race (TOCTOU) — no Linux o padrão é `os.replace(temp, path)` **sem** unlink.

O que o cliente já faz e **não pode regressir** (vale-production-safety):

- Timer por chave `60/RPM` (TTS = 20 s)
- Reserva **antes** da API; rollback se 429 de taxa / 503
- `max_retries` 2; 429 espera janela RPM, não backoff 2 s
- Failover de anel **só** em RPD (`per-day` / `GenerateRequestsPerDay`). 429 RPM **não** varre as 6 chaves
- Não tratar `Quota exceeded for metric` sozinho como RPD (free tier usa a mesma métrica p/ RPM e RPD)
- `Please retry in Xs` ≤180 s = taxa
- `exhausted_until` só vale se o dia local já tem ≥ RPD requests **reais**
- Cursor RR persistido em `_meta.rr_index`

Dois processos (diário 06:00 **e** BM `*/20`) já compartilham o JSON. SQLite WAL ajudaria, mas:

- migração no meio da madrugada + BM a cada 20 min = dois writers em formatos diferentes
- testes `test_gemini_client.py` cobrem JSON
- cache em memória + lazy flush **quebra** o contrato entre processos (cada um vê RPM 0)

---

## Solução desta onda (Linux)

### Fase A — lock POSIX no JSON (substitui SQLite)

**Granularidade (obrigatória):** o `fcntl.flock` cobre **só** leitura → reserva de slot → `os.replace` do JSON (~ms). **Soltar o lock ANTES de qualquer `time.sleep()`** (espera RPM ~20 s, retry 429, backoff 503).

Se o sleep ficar dentro do flock, o outro processo (BM `*/20` vs diário TTS) estoura o timeout de 5 s, falha a reserva e pode pular chave ou corromper o fluxo. Padrão:

```python
import fcntl, os, time

# 1. flock exclusivo (arquivo .lock ao lado, ou o próprio JSON)
# 2. load JSON
# 3. ver RPM / inserir timestamp de reserva / rr_index
# 4. write temp + os.replace(temp, file_path)  # sem unlink
# 5. flock unlock  ← aqui, ainda no mesmo with/try
# 6. SÓ ENTÃO: time.sleep(wait_gap) se o timer 60/RPM exigir
# 7. chamada API (sem lock)
# 8. se 429 taxa / 503: flock de novo só para rollback da reserva; unlock; sleep da janela
```

Timeout flock 5 s. Se timeout: log + **não** zerar o arquivo; não tratar como RPD.

Manter JSON. Lockfile dedicado (`gemini_usage.json.lock`) é preferível a flock no JSON aberto para leitura — evita misturar fd de load com fd de replace.

### Fase B — GC a cada 5 min

Ok **dentro do processo**, desde que o flush continue imediato após cada reserva/commit (o BM precisa ver o RPM). Não cachear RPM só em RAM.

### Fase C — SQLite

Adiada. Reavaliar se flock ainda contender com diário+BM. Fallback JSON “por 1 semana” no plano antigo é pior que um formato só.

---

## Checklist

- [ ] `HERMES_PY -m unittest scripts.test_gemini_client`
- [ ] Dois processos (simular BM + TTS) não corrompem JSON
- [ ] Enquanto um processo dorme os 20 s de RPM, o outro consegue flock (<5 s) e reservar outra chave
- [ ] `time.sleep` **nunca** ocorre com o lock ainda preso (grep / teste)
- [ ] 429 RPM não incrementa RPD / não marca `exhausted_until` falso
- [ ] `_meta.rr_index` sobrevive
- [ ] Sem `gemini_usage.db` nesta onda
- [ ] Windows/PermissionError some do caminho Linux (pode deixar o retry 30× como fallback se flock falhar)
