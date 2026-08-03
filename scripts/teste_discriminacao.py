"""
Teste de discriminação semântica — compara multilingual-MiniLM vs bge-small-en
em pares relacionados (desdobramentos reais) vs não-relacionados (controle negativo).
"""
from sentence_transformers import SentenceTransformer
import numpy as np
import json
import re
from pathlib import Path

# ── Pares de desdobramentos REAIS (controle positivo) ──
pares_reais = [
    (
        "Grave colisão na BR-470 em Rodeio mobiliza helicóptero Arcanjo 03 e deixa vítima presa em ferragens",
        "Tragédia na BR-470 mata motociclista no quilômetro 34 em Gaspar",
    ),
    (
        "Prefeitura de Blumenau investe R$ 6,9 milhões em novos parques para 79 escolas",
        "Blumenau gasta R$ 6,9 milhões em brinquedos escolares enquanto adia reforma de quadra",
    ),
]

# ── Pares NÃO relacionados (controle negativo) ──
pares_nao_relacionados = [
    (
        "Prefeitura de Blumenau investe R$ 6,9 milhões em novos parques para 79 escolas",
        "Grave colisão na BR-470 em Rodeio mobiliza helicóptero Arcanjo 03",
    ),
    (
        "Gian Pitbull nocauteia em Abu Dhabi e aproxima Vale do Itajaí do UFC",
        "Coleta seletiva de lixo reciclável em Rio do Sul salta quase cinquenta por cento",
    ),
    (
        "Oktoberfest Blumenau define as dez finalistas da realeza",
        "Tragédia na BR-470 mata motociclista no quilômetro 34 em Gaspar",
    ),
    (
        "Blumenau vence por WO após Jaraguá desistir da última rodada da Série A",
        "Tarifaço americano ameaça indústria de Santa Catarina e FIESC acende alerta",
    ),
    (
        "Escola centenária de Florianópolis é transferida para o TCE/SC",
        "Metropolitano vence por três a zero no Sesi e garante vice-campeonato",
    ),
    (
        "Distrito de Inovação de Blumenau começa a sair do papel com R$ 60 mil",
        "Defesa Civil de Santa Catarina emite alerta para temporais e chuvas intensas",
    ),
    (
        "Lei autoriza spray de pimenta para defesa pessoal de mulheres em todo o estado",
        "Santa Catarina alcança menor taxa de mortes violentas do Brasil em 2025",
    ),
    (
        "Hospital Santo Antônio detalha avanço das obras em Blumenau",
        "Ituporanga limpa dois quilômetros de rios com empresa terceirizada",
    ),
    (
        "Prefeito Egidio Ferrari de Blumenau critica gestões anteriores",
        "Estudantes da rede municipal são selecionados para programa de imersão",
    ),
    (
        "Incêndio destrói estufa de fumo e causa prejuízo de R$ 200 mil em Taió",
        "Blumenau gasta R$ 6,9 milhões em brinquedos escolares enquanto adia reforma",
    ),
]


def cosine_sim(a, b):
    return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))


def extract_entities(texto):
    patterns = [r'BR-\d+', r'SC-\d+', r'R\$\s*[\d.,]+\s*(milh[oõ]es|bilh[oõ]es|mil)?']
    entities = set()
    for p in patterns:
        entities.update(re.findall(p, texto, re.IGNORECASE))
    return entities


def similarity_with_boost(model, text1, text2):
    emb1 = model.encode(text1)
    emb2 = model.encode(text2)
    sim_base = cosine_sim(emb1, emb2)

    e1 = extract_entities(text1)
    e2 = extract_entities(text2)
    overlap = e1 & e2
    if overlap:
        boost = min(0.20, len(overlap) * 0.10)
        return min(1.0, sim_base + boost), sim_base, overlap
    return sim_base, sim_base, set()


def test_model(model_name, label):
    print("=" * 70)
    print(f"MODELO: {label}")
    print(f"  {model_name}")
    print("=" * 70)

    model = SentenceTransformer(model_name)

    print("\n🎯 PARES RELACIONADOS (desdobramentos reais):")
    sims_reais = []
    for t1, t2 in pares_reais:
        sim_final, sim_base, overlap = similarity_with_boost(model, t1, t2)
        sims_reais.append(sim_final)
        print(f"  Base: {sim_base:.3f} | Com boost: {sim_final:.3f} | Entidades: {overlap}")
        print(f"    '{t1[:65]}...'")
        print(f"    '{t2[:65]}...'")
        print()

    print("\n❌ PARES NÃO RELACIONADOS (controle negativo):")
    sims_nao_rel = []
    for t1, t2 in pares_nao_relacionados:
        sim_final, sim_base, overlap = similarity_with_boost(model, t1, t2)
        sims_nao_rel.append(sim_final)
        marker = " ⚠️ OVERLAP" if overlap else ""
        print(f"  Base: {sim_base:.3f} | Com boost: {sim_final:.3f}{marker}")
        print(f"    '{t1[:65]}...'")
        print(f"    '{t2[:65]}...'")
        print()

    print("=" * 70)
    print("📊 RESUMO ESTATÍSTICO")
    print("=" * 70)
    print(f"\nPares RELACIONADOS (desdobramentos reais):")
    print(f"  Média: {np.mean(sims_reais):.3f} | Mín: {min(sims_reais):.3f} | Máx: {max(sims_reais):.3f}")

    print(f"\nPares NÃO relacionados:")
    print(f"  Média: {np.mean(sims_nao_rel):.3f} | Mín: {min(sims_nao_rel):.3f} | Máx: {max(sims_nao_rel):.3f}")

    gap = min(sims_reais) - max(sims_nao_rel)
    print(f"\n🎯 GAP (mín real - máx não-rel): {gap:.3f}")

    if gap > 0:
        threshold_ideal = (min(sims_reais) + max(sims_nao_rel)) / 2
        print(f"💡 Threshold ideal (ponto médio): {threshold_ideal:.3f}")
        print(f"   → HIGH (automático): ~{threshold_ideal:.2f}")
        print(f"   → LOW (possível):    ~{threshold_ideal - 0.05:.2f}")
    else:
        print("⚠️ NÃO HÁ SEPARAÇÃO LIMPA entre relacionados e não-relacionados!")
        print("   Precisa de mais features além de similaridade semântica.")

    return sims_reais, sims_nao_rel


# ── Testar ambos os modelos ──
print("\n\n")
sims_reais_en, sims_nao_en = test_model("BAAI/bge-small-en-v1.5", "bge-small-en-v1.5 (INGLÊS, 33M params)")
print("\n\n")
sims_reais_multi, sims_nao_multi = test_model("paraphrase-multilingual-MiniLM-L12-v2", "paraphrase-multilingual-MiniLM-L12-v2 (MULTILÍNGUE, 118M params)")

# ── Comparação final ──
print("\n\n")
print("=" * 70)
print("🏆 COMPARAÇÃO FINAL")
print("=" * 70)
print(f"\n{'Modelo':<45} {'Mín Real':<10} {'Máx Não-Rel':<12} {'Gap':<8} {'Discriminação'}")
print("-" * 95)

gap_en = min(sims_reais_en) - max(sims_nao_en)
gap_multi = min(sims_reais_multi) - max(sims_nao_multi)

print(f"{'bge-small-en-v1.5 (inglês)':<45} {min(sims_reais_en):<10.3f} {max(sims_nao_en):<12.3f} {gap_en:<8.3f} {'✅ BOA' if gap_en > 0.1 else '⚠️ RUIM'}")
print(f"{'multilingual-MiniLM-L12-v2 (multilíngue)':<45} {min(sims_reais_multi):<10.3f} {max(sims_nao_multi):<12.3f} {gap_multi:<8.3f} {'✅ BOA' if gap_multi > 0.1 else '⚠️ RUIM'}")

print(f"\n📌 CONCLUSÃO:")
if gap_multi > gap_en:
    print(f"   multilingual-MiniLM tem {gap_multi/gap_en:.1f}x mais poder de discriminação")
    print(f"   → RECOMENDADO para manchetes em português")
else:
    print(f"   bge-small-en tem {gap_en/gap_multi:.1f}x mais poder de discriminação")
    print(f"   → RECOMENDADO (apesar de ser modelo em inglês)")
