# plan.md — Plano de Execução do Projeto

## Visão Geral

Implementação do sistema de sincronização automática Google Drive → Vimeo em 5 fases sequenciais. As expectativas por módulo/curso são adiadas para uma fase futura, após a conexão Drive ↔ Vimeo estar validada em produção.

---

## Fase 0 — Infraestrutura e Credenciais

**Objetivo:** Ambiente rodando localmente e na VPS. Credenciais configuradas.
**Estimativa:** 0,5 dia

### Tarefas

- [ ] Criar repositório Git com estrutura definida em `plan-api.md`
- [ ] Escrever `Dockerfile` e `docker-compose.yml`
- [ ] Testar `docker-compose up -d` localmente (Docker Desktop)
- [ ] **Google Cloud:**
  - Criar projeto no Google Cloud Console
  - Ativar Google Drive API
  - Criar Service Account
  - Baixar `google-sa.json`
  - Compartilhar a pasta raiz do Drive com o e-mail da Service Account
- [ ] **Vimeo:**
  - Criar app no Vimeo Developer
  - Gerar token com escopos: `upload`, `edit`, `video_files`, `folders`
- [ ] Rodar `alembic upgrade head` — criar tabelas no banco
- [ ] Configurar projeto no **Dokploy** apontando para o repositório Git
- [ ] Configurar variáveis de ambiente no Dokploy (sem `.env` comitado)

### Critério de conclusão
```bash
# Local
docker-compose up -d
curl http://localhost:8000/api/v1/config
# → 200 OK (config vazia)

# Produção
# Dashboard acessível via domínio configurado no Dokploy
```

---

## Fase 1 — Conexão com Google Drive

**Objetivo:** Sistema lista arquivos da pasta raiz do Drive e valida integridade.
**Dependência:** Fase 0 concluída
**Estimativa:** 1,5 dias

### Tarefas

- [ ] Implementar `drive_service.list_all_mp4(root_folder_id)` — percorre recursivamente, resolve `relative_path`
- [ ] Implementar `drive_service.get_file_meta(file_id)` — retorna `md5Checksum` + `size`
- [ ] Implementar `drive_service.generate_download_url(file_id)` — URL autenticada com token SA
- [ ] Implementar task `scan_drive` (Celery)
- [ ] Implementar task `check_integrity` com janela proporcional ao tamanho:
  - < 100 MB: 2 verificações × 30s
  - 100–500 MB: 2 verificações × 60s
  - > 500 MB: 3 verificações × 90s
- [ ] Endpoint `GET /api/v1/config` e `PUT /api/v1/config`
- [ ] Admin configura pasta raiz via dashboard

### Critério de conclusão
1. Admin configura `drive_root_folder_id` via dashboard
2. Coloca um arquivo `.mp4` na pasta raiz do Drive
3. Aguarda até 10 minutos
4. `GET /api/v1/videos` retorna o arquivo com `status = DRIVE_READY`

---

## Fase 2 — Upload para o Vimeo (pull)

**Objetivo:** Arquivos `DRIVE_READY` enviados ao Vimeo sem passar pela VPS.
**Dependência:** Fase 1 concluída
**Estimativa:** 1,5 dias

### Tarefas

- [ ] Implementar `vimeo_service.resolve_folder(root_uri, relative_path)` — encontra pasta destino no Vimeo
- [ ] Implementar `vimeo_service.pull_upload(link, name, folder_uri, size)` — POST à API Vimeo
- [ ] Implementar task `upload_to_vimeo` (Celery)
  - Resolve pasta Vimeo pelo `relative_path`
  - Gera token SA imediatamente antes do POST
  - Armazena `vimeo_uri` e `vimeo_folder_uri`
  - Trata falhas com retry automático (novo token a cada tentativa)
- [ ] Confirmar `concurrency=2` no worker

### Critério de conclusão
1. Arquivo em `DRIVE_READY` é processado
2. `GET /api/v1/videos/{id}` retorna `status = VIMEO_UPLOADING`
3. Vídeo aparece sendo processado no painel do Vimeo, **na pasta correta**
4. VPS não apresenta aumento de uso de disco durante o processo

---

## Fase 3 — Monitor de Transcodificação e Retry

**Objetivo:** Sistema acompanha o Vimeo até `SUCCESS` e trata falhas.
**Dependência:** Fase 2 concluída
**Estimativa:** 1 dia

### Tarefas

- [ ] Implementar `vimeo_service.get_status(vimeo_uri)`
- [ ] Implementar task `monitor_vimeo` (Celery)
  - Polling a cada 30s para `VIMEO_UPLOADING` e `VIMEO_TRANSCODING`
  - Transições: `UPLOADING → TRANSCODING → SUCCESS`
  - Em erro: `retry_count++` → reenfileira ou `ERROR`
- [ ] Registrar todas as transições em `status_logs`
- [ ] Endpoint `POST /api/v1/admin/videos/{id}/retry` — retry manual pelo Admin

### Critério de conclusão
1. Vídeo chega a `SUCCESS` automaticamente
2. `GET /api/v1/videos/{id}` exibe histórico completo de estados
3. Vídeo disponível e na pasta correta no Vimeo
4. Arquivo com falha simulada → `ERROR` após 3 tentativas → retry manual funciona

---

## Fase 4 — Dashboard e RBAC

**Objetivo:** Interface web operacional para Admin e Auditor.
**Dependência:** Fases 1, 2 e 3 concluídas
**Estimativa:** 2 dias

### Tarefas

- [ ] Autenticação JWT: login, `get_current_user`, `RequireRole`
- [ ] Criar usuários Admin e Auditor iniciais via script
- [ ] Dashboard principal: resumo geral + progresso por pasta + erros
- [ ] Listagem de vídeos com filtros, paginação e badges de status
- [ ] Detalhe do vídeo com timeline de estados e log de erro
- [ ] Tela de configuração (Admin only): pasta raiz Drive e Vimeo
- [ ] Relatórios: contagem por status, por pasta, exportação CSV
- [ ] Botão "Retry" (Admin only) — oculto para Auditor
- [ ] Botão "Scan manual" (Admin only) — oculto para Auditor
- [ ] Polling de atualização a cada 30s

### Critério de conclusão
Admin e Auditor conseguem, sem linha de comando:
- Ver status geral e por pasta
- Identificar erros e ler o log de causa
- Admin: forçar retry e disparar scan manual
- Auditor: visualizar tudo, sem ver botões de ação
- Exportar relatório CSV com filtros

---

## Fase 5 — Hardening e Produção

**Objetivo:** Sistema estável para operação contínua.
**Dependência:** Fases 0–4 concluídas
**Estimativa:** 1 dia

### Tarefas

- [ ] Nginx como reverse proxy com TLS (Let's Encrypt via Dokploy)
- [ ] Configurar `logrotate` para logs do Celery e FastAPI
- [ ] Backup diário automático do PostgreSQL
- [ ] Teste de resiliência: reiniciar VPS no meio de um upload e verificar retomada correta
- [ ] Documentar runbook: como reiniciar serviços, ver logs, forçar retry em lote

### Critério de conclusão
- Sistema rodando 48h sem intervenção manual
- Todos os vídeos de teste chegando a `SUCCESS`
- Logs limpos sem erros não tratados

---

## Fase Futura — Expectativas por Módulo/Curso

**Adiada intencionalmente** para após a validação da conexão Drive ↔ Vimeo em produção.

Escopo previsto:
- Formulário para definir X vídeos por semana por módulo/curso
- Cálculo automático de progresso esperado vs realizado
- Alertas quando o ritmo de entrega está abaixo do esperado

---

## Resumo de Estimativas

| Fase | Descrição | Estimativa |
|------|-----------|-----------|
| 0 | Infraestrutura e credenciais | 0,5 dia |
| 1 | Conexão Google Drive | 1,5 dias |
| 2 | Upload Vimeo (pull) | 1,5 dias |
| 3 | Monitor e retry | 1 dia |
| 4 | Dashboard e RBAC | 2 dias |
| 5 | Hardening | 1 dia |
| **Total MVP** | | **~7,5 dias úteis** |

---

## Riscos e Mitigações

| Risco | Probabilidade | Mitigação |
|-------|---------------|-----------|
| MD5 aparenta estabilidade com arquivo incompleto | Média | Janela proporcional ao tamanho com múltiplas verificações |
| Token SA expira antes do Vimeo iniciar o pull | Baixa | Token gerado imediatamente antes do POST; retry com novo token |
| Pasta destino no Vimeo não encontrada pelo `relative_path` | Baixa | Log de erro claro; Admin corrige a estrutura de pastas no Vimeo |
| Rate limit da Vimeo API | Baixa | `concurrency=2`; backoff em caso de `HTTP 429` |
| VPS reinicia durante transcodificação | Baixa | Estado persiste no PostgreSQL; monitor retoma no próximo ciclo |
| Dokploy falha no deploy | Baixa | Rollback via Git; mesmo `docker-compose.yml` roda localmente para teste |
