# 🎙️ Studio Humanizer — Humanização do Estúdio Virtual

> **Projeto:** Web Jornal Vale da Liberdade  
> **Objetivo:** Eliminar a "esterilidade digital" das vozes IA adicionando camadas sonoras orgânicas  
> **Data:** 2026-09-07  
> **Status:** 📋 Planejamento

---

## Problema

Vozes geradas por IA possuem uma característica inconfundível: **silêncio absoluto e perfeição acústica**. O cérebro humano estranha essa "limpeza digital" — a ausência total de textura sonora, ruído de fundo e imperfeições acústicas que existem em qualquer gravação real.

Quando um ouvinte percebe (conscientemente ou não) que o áudio é "limpo demais", a suspensão de descrença é quebrada e a voz passa a ser analisada como sintética em vez de contextualizada em um ambiente físico.

## Solução

Adicionar **3 camadas de áudio orgânico** ao pipeline de produção existente:

1. **Room Tone** — ruído contínuo de ambiente (sopro de ar, zumbido elétrico, ventoinha)
2. **Foley Sutil** — eventos incidentais esparsos (teclado, clique de mouse, cadeira)
3. **Cola Acústica** — reverb de convolução para integrar a voz ao espaço

## Modelo Híbrido (Custo Mínimo por Episódio)

O sistema opera em **duas fases** para minimizar o tempo de processamento:

```
  PREPARE (uma vez, offline)              POR EPISÓDIO (~2-3 segundos)
  ══════════════════════════              ════════════════════════════
  Baixar sons → raw/                      Ler prepared/ (já pronto)
  EQ + normalizar + trim                  Loop room tone na duração
  Salvar em prepared/                     Posicionar foley (aleatório)
  Gerar _manifest.json                    Convoluir reverb + mix
  Tempo: ~30-60s (uma vez)                Tempo: ~2-3s ⚡
```

**Custo adicional por episódio: <1% do tempo total do pipeline TTS.**

### Quick Start

```bash
# 1. Baixar sons CC0 e colocar em audio/ambience/raw/
# 2. Pré-processar (executar UMA VEZ):
python scripts/studio_humanizer.py prepare

# 3. A partir daí, cada episódio é humanizado automaticamente!
#    (basta enabled: true no config/studio_humanizer.yaml)
```

## Documentos deste Plano

| Documento | Descrição |
|---|---|
| [`PLANO_HUMANIZACAO.md`](./PLANO_HUMANIZACAO.md) | Plano mestre com arquitetura, fases e cronograma |
| [`AUDIO_LAYERS_SPEC.md`](./AUDIO_LAYERS_SPEC.md) | Especificação técnica das 3 camadas de áudio |
| [`MIXING_RULES.md`](./MIXING_RULES.md) | Regras de mixagem, EQ, volume e reverb |
| [`FOLEY_CATALOG.md`](./FOLEY_CATALOG.md) | Catálogo de sons ambientes e eventos Foley |
| [`INTEGRATION_MAP.md`](./INTEGRATION_MAP.md) | Mapa de integração com o pipeline existente |
| [`CONFIG_SPEC.md`](./CONFIG_SPEC.md) | Especificação do arquivo YAML de configuração |
| [`TESTES_E_VALIDACAO.md`](./TESTES_E_VALIDACAO.md) | Plano de testes A/B e métricas de validação |

## Princípio Fundamental

> **"Você só deve notar que o som de fundo existia se mutar a faixa de repente."**

A ambiência deve ser imperceptível durante a audição normal. O objetivo não é que o ouvinte ouça os sons — é que o cérebro pare de classificar a voz como artificial.

