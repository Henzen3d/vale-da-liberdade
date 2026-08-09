# Checklist de Deploy — Dashboard Admin

## Pré-Deploy

### 1. Script SQL
- [ ] Executar `scripts/05_admin_dashboard_backend.sql` no Supabase
- [ ] Verificar se todas as tabelas foram criadas:
  ```sql
  SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';
  ```
- [ ] Verificar se todas as RPCs foram criadas:
  ```sql
  SELECT routine_name FROM information_schema.routines WHERE routine_schema = 'public';
  ```

### 2. Configuração do Supabase
- [ ] Adicionar `role` em `user_profiles`:
  ```sql
  ALTER TABLE public.user_profiles ADD COLUMN role TEXT NOT NULL DEFAULT 'reader';
  ```
- [ ] Promover conta para admin:
  ```sql
  UPDATE public.user_profiles SET role = 'admin' WHERE email = 'seu@email.com';
  ```
- [ ] Verificar permissões das RPCs:
  ```sql
  SELECT routine_name, grantee 
  FROM information_schema.routine_privileges 
  WHERE routine_schema = 'public' AND grantee = 'anon';
  ```

### 3. Configuração do Docker
- [ ] Adicionar URLs de redirecionamento no `.env`:
  ```
  ADDITIONAL_REDIRECT_URLS=https://news.mob.tec.br,https://news.mob.tec.br/**,https://news.mob.tec.br/admin/**,http://news.mob.tec.br,http://192.168.31.22:8090,http://192.168.31.22:8080,http://127.0.0.1:8090
  ```
- [ ] Reiniciar container de auth:
  ```bash
  docker restart supabase-auth
  ```

### 4. Arquivos do Frontend
- [ ] `public/admin/index.html` — Shell SPA
- [ ] `public/admin/admin.css` — Design System
- [ ] `public/admin/js/admin_auth.js` — Guard RBAC
- [ ] `public/admin/js/admin_ads.js` — Gestão de Anúncios
- [ ] `public/admin/js/admin_users.js` — Usuários e Assinaturas
- [ ] `public/admin/js/admin_charts.js` — Gráficos
- [ ] `public/admin/js/admin_init.js` — Inicialização

### 5. Testes
- [ ] Acessar `https://news.mob.tec.br/admin/`
- [ ] Verificar se Supabase SDK está carregando
- [ ] Testar login com Google
- [ ] Verificar se RPC `is_admin_user()` retorna `true`
- [ ] Testar Kill-Switch em 1 clique
- [ ] Testar navegação entre abas
- [ ] Testar exportação CSV

## Pós-Deploy

### Verificações
```bash
# Verificar se arquivos estão servidos corretamente
curl -s https://news.mob.tec.br/admin/index.html | head -20
curl -s https://news.mob.tec.br/admin/js/admin_auth.js | head -20

# Verificar logs do Supabase
docker logs supabase-auth | tail -30

# Verificar se usuário tem permissão de admin
docker exec supabase-db psql -U postgres -d postgres -c "SELECT email, role FROM public.user_profiles WHERE email = 'henzen3d@gmail.com';"
```

### Rollback
Caso algo dê errado:
```bash
# Reverter commits
git revert HEAD

# Ou restaurar do backup
git checkout main -- public/admin/
```
