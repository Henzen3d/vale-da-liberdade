# Troubleshooting OAuth e RPCs — Sessão 2026-08-04

## Problema: OAuth sempre volta para a página principal

### Sintomas
- Usuário clica em "Entrar com Google" na dashboard admin
- Google autentica com sucesso
- Mas o callback volta para `https://news.mob.tec.br/` (página principal)
- Na página principal, o usuário já está logado mas a dashboard não detecta a sessão

### Diagnóstico
```bash
# Verificar logs do Supabase
docker logs supabase-auth | grep -E "(authorize|callback|admin)" | tail -20
```

**Resultado esperado:**
```
path="/authorize" referer="https://news.mob.tec.br/admin/"
path="/callback" referer="https://news.mob.tec.br"  # ← PROBLEMA: deveria ser /admin/
```

### Causa Raiz
O Supabase self-hosted só redireciona para URLs configuradas em `ADDITIONAL_REDIRECT_URLS` no `.env`. O callback do OAuth SEMPRE volta para a URL base (`/`) porque é a única configurada.

### Solução Implementada

#### 1. Adicionar `/admin/` às URLs permitidas no `.env`
```bash
# No arquivo /home/osmar/supabase/docker/.env
ADDITIONAL_REDIRECT_URLS=https://news.mob.tec.br,https://news.mob.tec.br/**,https://news.mob.tec.br/admin/**,http://news.mob.tec.br,http://192.168.31.22:8090,http://192.168.31.22:8080,http://127.0.0.1:8090
```

#### 2. Reiniciar o container de auth
```bash
docker restart supabase-auth
```

#### 3. Código JavaScript (admin_auth.js)
```javascript
async function signInWithGoogle() {
  if (!supabase) {
    console.error('[admin_auth] supabase não inicializado');
    return;
  }

  // Usar URL absoluta com domínio completo
  const redirectUrl = 'https://news.mob.tec.br/admin/';
  console.log('[admin_auth] Redirect URL:', redirectUrl);
  
  const { error } = await supabase.auth.signInWithOAuth({
    provider: 'google',
    options: {
      redirectTo: redirectUrl,
      queryParams: { access_type: 'offline', prompt: 'consent' },
    },
  });
  
  if (error) {
    console.error('[admin_auth] Erro no OAuth:', error);
    alert('Falha ao iniciar login: ' + error.message);
  }
}
```

## Problema: Múltiplas instâncias do GoTrueClient

### Sintomas
```
Multiple GoTrueClient instances detected in the same browser context.
It is not an error, but this should be avoided...
```

### Causa
O Supabase SDK é carregado tanto na página principal quanto na página admin.

### Solução
Usar `storageKey` único para a instância do admin:
```javascript
supabase = window.supabase.createClient(url, key, {
  auth: {
    storageKey: 'admin-supabase-auth-token',  // Storage único
    // ...
  }
});
```

## Problema: RPC is_admin_user() retorna false

### Sintomas
```
[admin_auth] Resultado RPC is_admin_user: {data: false, error: null}
```

### Diagnóstico
```sql
-- Verificar se a tabela user_profiles tem a coluna role
SELECT column_name FROM information_schema.columns 
WHERE table_name = 'user_profiles' AND column_name = 'role';

-- Verificar se o usuário tem role='admin'
SELECT id, email, role FROM public.user_profiles WHERE email = 'henzen3d@gmail.com';

-- Se não tiver, atualizar:
UPDATE public.user_profiles SET role = 'admin' WHERE email = 'henzen3d@gmail.com';
```

### Solução
Executar o script SQL completo:
```bash
docker exec -i supabase-db psql -U postgres -d postgres -f scripts/05_admin_dashboard_backend.sql
```

## Problema: Erro "Cannot read properties of undefined (reading 'oneOfType')"

### Sintomas
```
Animate.js:330 Uncaught TypeError: Cannot read properties of undefined (reading 'oneOfType')
```

### Causa
Biblioteca de animação (Animate.js) tentando usar PropTypes do React que não foi carregado.

### Solução
Garantir que React e ReactDOM sejam carregados antes do Recharts:
```html
<script src="https://cdn.jsdelivr.net/npm/react@18/umd/react.production.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/react-dom@18/umd/react-dom.production.min.js" defer></script>
<script src="https://cdn.jsdelivr.net/npm/recharts@2.12.7/umd/Recharts.js" defer></script>
```

## Logs Importantes para Debug

### Supabase Auth
```bash
# Verificar solicitações de OAuth
docker logs supabase-auth | grep -E "(authorize|callback|google)" | tail -20

# Verificar erros
docker logs supabase-auth | grep -i error | tail -10
```

### Browser Console
```javascript
// Logs esperados na dashboard admin:
[admin_auth] Iniciando inicialização...
[admin_auth] window.supabase: true
[admin_auth] Instância isolada criada com storageKey único
[admin_auth] Verificando sessão existente...
[admin_auth] getSession: { hasSession: false, ... }
[admin_auth] Nenhuma sessão ativa — mostrando tela de login
[admin_auth] Iniciando login com Google...
[admin_auth] Redirect URL: https://news.mob.tec.br/admin/
[admin_auth] Redirecionando para Google...
[admin_auth] Auth state change: SIGNED_IN
[admin_auth] Usuário logado: henzen3d@gmail.com
[admin_auth] Verificando permissão de admin para: henzen3d@gmail.com
[admin_auth] Resultado RPC is_admin_user: {data: true, error: null}
[admin_auth] É admin? true
[admin_auth] Acesso permitido!
```
