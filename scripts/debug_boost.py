"""Debug do boost de entidade para o caso BR-470."""
import sys
sys.path.insert(0, '/home/osmar/web-jornal-vale-da-liberdade')
from scripts.followup_tracker import FollowupTracker

# Manchetes reais do teste
manchete_26 = "Grave colisão na BR-470 em Rodeio mobiliza helicóptero Arcanjo 03 e deixa vítima presa em ferragens"
manchete_27 = "Tragédia na BR-470 mata motociclista no quilômetro 34 em Gaspar"

print("=" * 70)
print("DEBUG DO BOOST DE ENTIDADE - CASO BR-470")
print("=" * 70)

# Inicializar tracker
tracker = FollowupTracker()

# Extrair entidades
entidades_26 = tracker._extract_entities(manchete_26)
entidades_27 = tracker._extract_entities(manchete_27)

print(f"\nManchete 26/07: {manchete_26}")
print(f"Entidades extraídas: {entidades_26}")

print(f"\nManchete 27/07: {manchete_27}")
print(f"Entidades extraídas: {entidades_27}")

overlap = entidades_26 & entidades_27
print(f"\nOverlap de entidades: {overlap}")

# Calcular embeddings
emb_26 = tracker.embed_fn(manchete_26)
emb_27 = tracker.embed_fn(manchete_27)

# Similaridade base (sem boost)
sim_base = tracker._cosine_sim(emb_26, emb_27)
print(f"\nSimilaridade base (sem boost): {sim_base:.3f}")

# Similaridade com boost
sim_boost = tracker._similarity_with_entity_boost(emb_26, emb_27, manchete_26, manchete_27)
print(f"Similaridade com boost: {sim_boost:.3f}")

print(f"\nBoost aplicado: {sim_boost - sim_base:.3f}")

# Verificar lógica do boost
if overlap:
    boost_esperado = min(0.20, len(overlap) * 0.10)
    print(f"Boost esperado (cálculo): {boost_esperado:.3f}")
    print(f"Boost real aplicado: {sim_boost - sim_base:.3f}")
    
    if abs((sim_boost - sim_base) - boost_esperado) > 0.01:
        print("\n⚠️ DISCREPÂNCIA DETECTADA!")
        print("O boost não está sendo aplicado corretamente.")
    else:
        print("\n✅ Boost aplicado corretamente.")
else:
    print("\n❌ PROBLEMA: Overlap vazio - boost não será aplicado!")
    print("Verifique os padrões de entidade em ENTITY_PATTERNS")
