"""Teste do regex de entidades após correção."""
import sys
import re
sys.path.insert(0, '/home/osmar/web-jornal-vale-da-liberdade')
from scripts.followup_tracker import FollowupTracker, ENTITY_PATTERNS

tracker = FollowupTracker()

textos = [
    "Prefeitura de Blumenau investe R$ 6,9 milhões em novos parques",
    "Blumenau gasta R$ 6,9 milhões em brinquedos escolares",
    "Grave colisão na BR-470 em Rodeio mobiliza helicóptero Arcanjo 03",
    "Tragédia na BR-470 mata motociclista no quilômetro 34 em Gaspar",
    "Incêndio destrói estufa de fumo e causa prejuízo de R$ 200 mil em Taió",
    "Distrito de Inovação de Blumenau começa a sair do papel com R$ 60 mil",
]

print("Padrões de entidade:")
for p in ENTITY_PATTERNS:
    print(f"  {p}")

print("\nExtração de entidades:")
for t in textos:
    entidades = tracker._extract_entities(t)
    print(f"  '{t[:65]}...'")
    print(f"    → {entidades}")

# Testar overlap para os pares reais
print("\n" + "=" * 60)
print("OVERLAP DE ENTIDADES NOS PARES REAIS:")
print("=" * 60)

pares = [
    (textos[0], textos[1], "R$ 6,9M"),
    (textos[2], textos[3], "BR-470"),
]

for t1, t2, label in pares:
    e1 = tracker._extract_entities(t1)
    e2 = tracker._extract_entities(t2)
    overlap = e1 & e2
    print(f"\n  {label}:")
    print(f"    Entidades 1: {e1}")
    print(f"    Entidades 2: {e2}")
    print(f"    Overlap: {overlap}")
