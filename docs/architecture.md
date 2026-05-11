# architecture.md — Arquitetura Técnica do Sistema Drive → Vimeo

## 1. Visão Geral

Este sistema utiliza princípios de **DDD**, **CQRS** e **Clean Architecture**. Para detalhes sobre os padrões aplicados, consulte [design_patterns.md](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/design_patterns.md).

```
┌─────────────────────────────────────────────────────────┐
│                   CAMADA DE INTERFACE                    │
│             FastAPI  (Dashboard + REST API)              │
│         Admin: leitura + escrita + ações                 │
│         Auditor: somente leitura                         │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│                  CAMADA DE ORQUESTRAÇÃO                  │
│             Celery Beat (agendador periódico)            │
│      Scanner · Verificador de Integridade · Monitor      │
└──────────────────────────┬──────────────────────────────┘
                           │ enfileira jobs
┌──────────────────────────▼──────────────────────────────┐
│                     CAMADA DE FILA                       │
│                         Redis                            │
└──────────────────────────┬──────────────────────────────┘
                           │ consome jobs
┌──────────────────────────▼──────────────────────────────┐
│                   CAMADA DE WORKERS                      │
│             Celery Workers  (concurrency=2)              │
│   Gera token SA · Resolve pasta Vimeo · POST pull upload │
└──────────┬──────────────────────────────┬───────────────┘
           │                              │
┌──────────▼──────────┐      ┌────────────▼──────────────┐
│  Google Drive API   │      │        Vimeo API           │
│  Lista arquivos     │      │  Recebe link, faz pull     │
│  Valida MD5+size    │      │  Transcoda e aloca         │
│  Gera token SA      │      │  na pasta correta          │
└─────────────────────┘      └───────────────────────────┘
           │                              │
           └──────────────┬──────────────┘
                          │
               ┌──────────▼──────────┐
               │     PostgreSQL      │
               │  Máquina de estados │
               │  Auditoria e logs   │
               └─────────────────────┘
```

---

## 2. Componentes

### 2.1 FastAPI

**Responsabilidades:** Dashboard web, endpoints REST, RBAC (Admin/Auditor), configuração do sistema.

**RBAC via FastAPI Dependency:**
```python
class RequireRole:
    def __init__(self, *roles: str):
        self.roles = roles

    def __call__(self, user=Depends(get_current_user)):
        if user.role not in self.roles:
            raise HTTPException(status_code=403, detail="Acesso negado")
        return user

# Uso:
@router.post("/folders",           dependencies=[Depends(RequireRole("admin"))])
@router.post("/admin/scan",        dependencies=[Depends(RequireRole("admin"))])
@router.post("/admin/{id}/retry",  dependencies=[Depends(RequireRole("admin"))])
@router.get("/videos")             # admin + auditor
@router.get("/reports/summary")    # admin + auditor
```

**Tecnologia:** Python 3.11+, FastAPI, Uvicorn, Nginx (TLS)

---

### 2.2 Celery Beat

Agendador de tarefas periódicas:

```python
CELERYBEAT_SCHEDULE = {
    "scanner": {
        "task": "tasks.scan_drive",
        "schedule": crontab(minute="*/5"),    # a cada 5 minutos
    },
    "integrity_check": {
        "task": "tasks.check_integrity",
        "schedule": crontab(minute="*/2"),    # a cada 2 minutos
    },
    "vimeo_monitor": {
        "task": "tasks.monitor_vimeo",
        "schedule": crontab(minute="*/1"),    # a cada 1 minuto
    },
}
```

---

### 2.3 Redis

Broker de mensagens entre Beat e Workers. Single node para MVP.
`redis://localhost:6379/0`

---

### 2.4 Celery Workers

`concurrency=2` — dois uploads simultâneos no máximo para não estourar o rate limit do Vimeo.

---

### 2.5 PostgreSQL 15+

Fonte de verdade do estado de cada arquivo. Armazena configuração global, histórico de transições e logs de erro.

---

## 3. Fluxo de Dados Detalhado

### Fase 1 — Descoberta

```
[Celery Beat] → scan_drive()
    ↓
Lê drive_root_folder_id de system_config
    ↓
[Drive API] lista recursivamente todos os .mp4 na pasta raiz
    ↓
Para cada arquivo novo (não existe no DB):
    relative_path = caminho do arquivo menos a raiz configurada
    INSERT INTO videos (filename, drive_file_id, relative_path, status='DISCOVERED')
```

---

### Fase 2 — Verificação de Integridade

```
[Celery Beat] → check_integrity()
    ↓
Seleciona status IN ('DISCOVERED', 'DRIVE_SYNC_PENDING')
    ↓
[Drive API] GET files/{id}?fields=md5Checksum,size
    ↓
md5Checksum ausente? → UPDATE status='DRIVE_SYNC_PENDING' → fim
    ↓
Aplica janela proporcional ao size:
    < 100MB  → 2x com 30s de intervalo
    100-500MB → 2x com 60s de intervalo
    > 500MB  → 3x com 90s de intervalo
    ↓
MD5 estável em todas as verificações?
    SIM → UPDATE status='DRIVE_READY', checksum=md5, file_size=size
    NÃO → UPDATE status='DRIVE_SYNC_PENDING'
```

---

### Fase 3 — Upload para o Vimeo (pull)

```
[Celery Beat] → enfileira upload_to_vimeo() para cada DRIVE_READY
    ↓
[Redis] job enfileirado
    ↓
[Worker] consome job
    ↓
Resolve vimeo_folder_uri:
    Consulta Vimeo API pela subpasta = vimeo_root_uri + relative_path
    (pasta já existe, nunca é criada pelo sistema)
    ↓
[Google Auth] gera access_token via Service Account (~1h validade)
    ↓
Monta URL:
    https://www.googleapis.com/drive/v3/files/{ID}?alt=media&access_token={TOKEN}
    ↓
POST https://api.vimeo.com/me/videos
    {
      "upload": { "approach": "pull", "link": "<URL>" },
      "name": filename,
      "folder_uri": vimeo_folder_uri
    }
    ↓
Resposta: { "uri": "/videos/123456" }
    ↓
UPDATE status='VIMEO_UPLOADING', vimeo_uri='/videos/123456'
```

> O arquivo nunca passa pela VPS. O Vimeo faz GET na URL acima diretamente nos servidores do Google.

---

### Fase 4 — Monitoramento de Transcodificação

```
[Celery Beat] → monitor_vimeo()
    ↓
Seleciona status IN ('VIMEO_UPLOADING', 'VIMEO_TRANSCODING')
    ↓
GET https://api.vimeo.com/videos/{ID}
    ↓
transcode.status == 'complete'      → UPDATE status='SUCCESS'
upload.status == 'complete'         → UPDATE status='VIMEO_TRANSCODING'
upload|transcode status == 'error'  → retry_count++
    retry_count < 3  → gera novo token → reenfileira (Fase 3)
    retry_count >= 3 → UPDATE status='ERROR', last_error=<msg>
```

---

## 4. Máquina de Estados

```
                    DISCOVERED
                        │
                        ▼
            DRIVE_SYNC_PENDING ◄─── (MD5 instável ou ausente)
                        │
                        ▼ (MD5 estável N vezes consecutivas)
                   DRIVE_READY
                        │
                        ▼ (Worker enfileira job)
                 VIMEO_UPLOADING
                        │
                        ▼ (upload.status == complete)
               VIMEO_TRANSCODING
                        │
             ┌──────────┴──────────┐
             ▼                     ▼
           SUCCESS               ERROR
                                   │
                        (retry_count < 3)
                                   │
                                   └──► novo token → VIMEO_UPLOADING
```

---

## 5. Infraestrutura

### Ambientes

| Ambiente | Ferramenta | Observação |
|----------|-----------|------------|
| Local (desenvolvimento) | Docker Desktop | `docker-compose up -d` |
| Produção (VPS) | Dokploy | Lê o mesmo `docker-compose.yml` via Git |

### Especificação Mínima da VPS

| Recurso | Mínimo |
|---------|--------|
| CPU | 2 vCPU |
| RAM | 2 GB |
| Disco | 20 GB (SO, logs, banco — sem vídeos) |
| SO | Ubuntu 22.04 LTS |

### Serviços no docker-compose

| Serviço | Imagem | Função |
|---------|--------|--------|
| `api` | Python 3.11 | FastAPI + Uvicorn |
| `worker` | Python 3.11 | Celery Worker (concurrency=2) |
| `beat` | Python 3.11 | Celery Beat |
| `postgres` | postgres:15 | Banco de dados |
| `redis` | redis:7-alpine | Fila de mensagens |

---

## 6. Segurança

| Item | Implementação |
|------|--------------|
| Chave SA Google | Variável de ambiente `GOOGLE_SA_KEY_PATH`. Nunca comitada no Git. |
| Token Vimeo | Variável de ambiente `VIMEO_ACCESS_TOKEN`. Nunca comitada no Git. |
| URL com token SA | Gerada sob demanda, nunca armazenada no banco. |
| Redis / PostgreSQL | Bind em `127.0.0.1`. Não expostos externamente. |
| Dashboard | JWT (produção) ou HTTP Basic (MVP). Roles: `admin` e `auditor`. |
| Secrets em produção | Configurados na UI do Dokploy, não no `.env` comitado. |
