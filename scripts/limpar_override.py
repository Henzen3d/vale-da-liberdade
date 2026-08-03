#!/usr/bin/env python3
"""Limpar override de modelo da sessão do Telegram."""
import json

sessions_file = '/home/osmar/.hermes/sessions/sessions.json'

# Carregar
with open(sessions_file, 'r') as f:
    data = json.load(f)

telegram_key = 'agent:main:telegram:dm:8122386267'

print("Antes:")
print(f"  model_override: {data[telegram_key].get('model_override', 'NENHUM')}")

# Limpar o override
if 'model_override' in data[telegram_key]:
    del data[telegram_key]['model_override']
    print("\nOverride removido!")

# Salvar
with open(sessions_file, 'w') as f:
    json.dump(data, f, indent=2)

print("\nDepois:")
with open(sessions_file, 'r') as f:
    data = json.load(f)
print(f"  model_override: {data[telegram_key].get('model_override', 'NENHUM')}")

print("\n✅ Override limpo com sucesso!")
print("Agora o /model deve funcionar normalmente.")
