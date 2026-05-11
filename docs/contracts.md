# contracts.md — Contratos de Dados e Interfaces

## 1. Schema do Banco de Dados (PostgreSQL)

### Tabela: `system_config`

Configuração global do sistema. Sempre contém exatamente uma linha.

```sql
CREATE TABLE system_config (
    id                    SERIAL PRIMARY KEY,
    drive_root_folder_id  VARCHAR(256)  NOT NULL,  -- ID da pasta raiz no Google Drive
    vimeo_root_folder_uri VARCHAR(256)  NOT NULL,  -- URI da pasta raiz no Vimeo (ex: /folders/123)
    updated_at            TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
```

---

### Tabela: `videos`

Estado atual de cada arquivo descoberto.

```sql
CREATE TYPE video_status AS ENUM (
    'DISCOVERED',
    'DRIVE_SYNC_PENDING',
    'DRIVE_READY',
    'VIMEO_UPLOADING',
    'VIMEO_TRANSCODING',
    'SUCCESS',
    'ERROR'
);

CREATE TABLE videos (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        VARCHAR(512)   NOT NULL,
    relative_path   VARCHAR(1024)  NOT NULL,   -- ex: /Python/Modulo_01/
    drive_file_id   VARCHAR(256)   NOT NULL UNIQUE,
    vimeo_uri       VARCHAR(256)   NULL,        -- preenchido após POST ao Vimeo
    vimeo_folder_uri VARCHAR(256)  NULL,        -- URI da pasta destino no Vimeo
    status          video_status   NOT NULL DEFAULT 'DISCOVERED',
    checksum        VARCHAR(64)    NULL,        -- md5Checksum confirmado do Drive
    file_size       BIGINT         NULL,        -- tamanho em bytes (usado na janela de verificação)
    retry_count     INTEGER        NOT NULL DEFAULT 0,
    last_error      TEXT           NULL,
    created_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_videos_status        ON videos (status);
CREATE INDEX idx_videos_relative_path ON videos (relative_path);
CREATE INDEX idx_videos_drive_file_id ON videos (drive_file_id);
```

---

### Tabela: `status_logs`

Histórico completo de todas as transições de estado para auditoria.

```sql
CREATE TABLE status_logs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id    UUID          NOT NULL REFERENCES videos(id),
    from_status video_status  NULL,
    to_status   video_status  NOT NULL,
    message     TEXT          NULL,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_status_logs_video_id ON status_logs (video_id);
```

---

### Tabela: `users`

Usuários do sistema com controle de papel (RBAC).

```sql
CREATE TYPE user_role AS ENUM ('admin', 'auditor');

CREATE TABLE users (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email        VARCHAR(256)  NOT NULL UNIQUE,
    password_hash VARCHAR(256) NOT NULL,
    role         user_role     NOT NULL DEFAULT 'auditor',
    created_at   TIMESTAMPTZ   NOT NULL DEFAULT NOW()
);
```

---

## 2. Contratos da Google Drive API

### 2.1 Listar arquivos recursivamente na pasta raiz

**Chamada (por página, seguindo `nextPageToken`):**
```
GET https://www.googleapis.com/drive/v3/files
  ?q='{FOLDER_ID}' in parents and mimeType='video/mp4' and trashed=false
  &fields=files(id,name,parents,md5Checksum,size),nextPageToken
  &pageSize=100
```

**Resposta esperada:**
```json
{
  "files": [
    {
      "id": "1A2B3C4D5E6F",
      "name": "aula_01.mp4",
      "parents": ["PARENT_FOLDER_ID"],
      "md5Checksum": "d41d8cd98f00b204e9800998ecf8427e",
      "size": "1073741824"
    }
  ],
  "nextPageToken": "TOKEN_PROXIMA_PAGINA"
}
```

> O scanner percorre recursivamente subpastas calculando o `relative_path` com base na pasta raiz configurada.

---

### 2.2 Verificar integridade (MD5 + size)

**Chamada:**
```
GET https://www.googleapis.com/drive/v3/files/{FILE_ID}
  ?fields=id,md5Checksum,size
```

**Resposta:**
```json
{
  "id": "1A2B3C4D5E6F",
  "md5Checksum": "d41d8cd98f00b204e9800998ecf8427e",
  "size": "1073741824"
}
```

**Lógica de janela proporcional ao `size`:**

```python
def get_verification_window(file_size_bytes: int) -> tuple[int, int]:
    """Retorna (número de verificações, intervalo em segundos)"""
    mb = file_size_bytes / (1024 * 1024)
    if mb < 100:
        return (2, 30)
    elif mb < 500:
        return (2, 60)
    else:
        return (3, 90)
```

**Campo `md5Checksum` ausente** significa que o Google ainda está calculando — arquivo incompleto. Manter `DRIVE_SYNC_PENDING`.

---

### 2.3 Gerar URL de download autenticada (Service Account)

```python
from google.oauth2 import service_account
import google.auth.transport.requests
import os

def generate_download_url(file_id: str) -> str:
    """
    Gera URL de download direto com access_token embutido.
    Válida por ~1 hora. CHAMAR imediatamente antes do POST ao Vimeo.
    NUNCA armazenar a URL retornada no banco.
    """
    creds = service_account.Credentials.from_service_account_file(
        os.environ["GOOGLE_SA_KEY_PATH"],
        scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    request = google.auth.transport.requests.Request()
    creds.refresh(request)

    return (
        f"https://www.googleapis.com/drive/v3/files/{file_id}"
        f"?alt=media&access_token={creds.token}"
    )
```

---

## 3. Contratos da Vimeo API

### 3.1 Resolver pasta destino pelo relative_path

Antes de fazer o upload, o worker precisa encontrar o `vimeo_folder_uri` correspondente ao `relative_path` do arquivo dentro da pasta raiz Vimeo.

```
GET https://api.vimeo.com{VIMEO_ROOT_FOLDER_URI}/items
  ?type=folder&per_page=100
```

O worker compara os nomes das subpastas com o `relative_path` e obtém o `uri` da pasta correta. Como a estrutura já existe e é idêntica ao Drive, esse lookup é determinístico.

---

### 3.2 Iniciar pull upload

**Endpoint:** `POST https://api.vimeo.com/me/videos`

**Headers:**
```
Authorization: Bearer {VIMEO_ACCESS_TOKEN}
Content-Type: application/json
Accept: application/vnd.vimeo.*+json;version=3.4
```

**Payload:**
```json
{
  "upload": {
    "approach": "pull",
    "link": "https://www.googleapis.com/drive/v3/files/{FILE_ID}?alt=media&access_token={TOKEN}",
    "size": 1073741824
  },
  "name": "aula_01.mp4",
  "folder_uri": "/folders/987654",
  "privacy": {
    "view": "nobody"
  }
}
```

**Resposta de sucesso (HTTP 201):**
```json
{
  "uri": "/videos/123456789",
  "upload": {
    "status": "in_progress",
    "approach": "pull"
  },
  "transcode": {
    "status": "in_progress"
  }
}
```

---

### 3.3 Verificar status (polling)

**Endpoint:** `GET https://api.vimeo.com/videos/{VIDEO_ID}`

**Resposta:**
```json
{
  "uri": "/videos/123456789",
  "upload": { "status": "complete" },
  "transcode": { "status": "in_progress" }
}
```

**Mapeamento de status:**

| `upload.status` | `transcode.status` | Status no DB |
|---|---|---|
| `in_progress` | qualquer | `VIMEO_UPLOADING` |
| `complete` | `in_progress` | `VIMEO_TRANSCODING` |
| `complete` | `complete` | `SUCCESS` |
| `error` (qualquer campo) | | `retry_count++` → retry ou `ERROR` |

---

## 4. Contratos de Autenticação (RBAC)

### Permissões por papel

| Endpoint | Admin | Auditor |
|----------|-------|---------|
| `GET /api/v1/videos` | ✅ | ✅ |
| `GET /api/v1/videos/{id}` | ✅ | ✅ |
| `GET /api/v1/reports/*` | ✅ | ✅ |
| `GET /api/v1/config` | ✅ | ✅ |
| `PUT /api/v1/config` | ✅ | ❌ |
| `POST /api/v1/admin/scan` | ✅ | ❌ |
| `POST /api/v1/admin/videos/{id}/retry` | ✅ | ❌ |

---

## 5. Payload do Job Celery

```python
# Serializado como JSON pelo Celery ao enfileirar
{
    "video_id": "uuid-do-registro",
    "drive_file_id": "1A2B3C4D5E6F",
    "filename": "aula_01.mp4",
    "relative_path": "/Python/Modulo_01/",
    "file_size": 1073741824,
    "retry_count": 0
}
```

---

## 6. Variáveis de Ambiente

```env
# Google
GOOGLE_SA_KEY_PATH=/etc/secrets/google-sa.json

# Vimeo
VIMEO_ACCESS_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx

# Banco de dados
DATABASE_URL=postgresql://user:password@postgres:5432/drive_vimeo

# Redis
REDIS_URL=redis://redis:6379/0

# Celery
CELERY_CONCURRENCY=2
SCANNER_INTERVAL_MINUTES=5
INTEGRITY_CHECK_INTERVAL_MINUTES=2
VIMEO_MONITOR_INTERVAL_SECONDS=30

# Auth
JWT_SECRET=sua_chave_secreta_aqui
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=480
```

> Em produção, todas as variáveis são configuradas diretamente na interface do **Dokploy**, sem `.env` comitado no repositório.
