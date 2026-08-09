# Configuração OAuth — Supabase Self-Hosted

## Configuração de URLs de Redirecionamento

### No arquivo `.env` do Docker
Local: `/home/osmar/supabase/docker/.env`

```bash
# Site URL principal
SITE_URL=https://news.mob.tec.br

# Additional Redirect URLs (IMPORTANTE para OAuth funcionar)
ADDITIONAL_REDIRECT_URLS=https://news.mob.tec.br,https://news.mob.tec.br/**,https://news.mob.tec.br/admin/**,http://news.mob.tec.br,http://192.168.31.22:8090,http://192.168.31.22:8080,http://127.0.0.1:8090
```

### Aplicações
1. **Editar o arquivo** `.env`
2. **Reiniciar o container** de auth:
   ```bash
   docker restart supabase-auth
   ```
3. **Verificar** nos logs:
   ```bash
   docker logs supabase-auth | tail -20
   ```

## URLs Permitidas para OAuth

### Google OAuth
- URL de redirecionamento deve estar em `ADDITIONAL_REDIRECT_URLS`
- O Supabase vai verificar se a URL de callback está permitida
- Se não estiver, o OAuth falha com erro 401

### Configuração no Google Cloud Console
1. Ir em **Credentials** → **OAuth 2.0 Client IDs**
2. Selecionar o client ID do Supabase
3. Em **Authorized redirect URIs**, adicionar:
   - `https://news.mob.tec.br/auth/v1/callback`

## Troubleshooting

### Problema: OAuth retorna 401
**Sintoma:** Erro "Provider could not be found" ou redirect falha

**Solução:**
1. Verificar se a URL está em `ADDITIONAL_REDIRECT_URLS`
2. Verificar se o container foi reiniciado
3. Verificar logs: `docker logs supabase-auth | grep -i error`

### Problema: Callback vai para página errada
**Sintoma:** Após login, usuário volta para página principal

**Causa:** URL de redirecionamento não configurada corretamente

**Solução:**
1. Usar URL absoluta no código: `https://news.mob.tec.br/admin/`
2. Adicionar ao `.env`: `https://news.mob.tec.br/admin/**`
3. Reiniciar container

## Verificação
```bash
# Verificar configuração atual
grep -E "(SITE_URL|REDIRECT)" /home/osmar/supabase/docker/.env

# Verificar se container está usando a configuração
docker inspect supabase-auth | grep -A5 "Env"

# Testar OAuth manualmente
curl -s "https://news.mob.tec.br/auth/v1/authorize?provider=google&redirect_to=https://news.mob.tec.br/admin/" \
  -H "apikey: SUA_ANON_KEY"
```

## Notas Importantes

### Por que usar URL absoluta?
O Supabase pode interpretar mal URLs relativas em alguns contextos. Sempre usar URLs completas:
- ✅ `https://news.mob.tec.br/admin/`
- ❌ `/admin/`

### Ordem dos scripts
Garantir que React e ReactDOM sejam carregados antes do Recharts:
```html
<script src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/react-dom@18/umd/react-dom.production.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/recharts@2.12.7/umd/Recharts.js" defer></script>
```
