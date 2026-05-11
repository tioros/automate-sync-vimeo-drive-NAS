# plan-api.md — Plano de Implementação da API (Backend)

## 1. Estrutura de Pastas do Projeto

```
drive-vimeo-sync/
├── app/
│   ├── main.py               # FastAPI app, routers, startup
│   ├── config.py             # Configurações via pydantic-settings
│   ├── database.py           # Conexão PostgreSQL (SQLAlchemy async)
│   ├── auth.py               # JWT, get_current_user, RequireRole
│   ├── models/
│   │   ├── video.py          # ORM: Video, VideoStatus
│   │   ├── config.py         # ORM: SystemConfig
│   │   └── user.py           # ORM: User, UserRole
│   ├── schemas/
│   │   ├── video.py          # Pydantic schemas request/response
│   │   ├── config.py
│   │   └── user.py
│   ├── routers/
│   │   ├── videos.py         # GET /videos, GET /videos/{id}
│   │   ├── config.py         # GET/PUT /config
│   │   ├── reports.py        # GET /reports/*
│   │   └── admin.py          # POST /admin/* (somente Admin)
│   └── services/
│       ├── drive.py          # Google Drive API
│       └── vimeo.py          # Vimeo API
├── worker/
│   ├── celery_app.py         # Configuração do Celery + Beat
│   └── tasks/
│       ├── scanner.py        # Task: scan_drive
│       ├── integrity.py      # Task: check_integrity
│       ├── uploader.py       # Task: upload_to_vimeo
│       └── monitor.py        # Task: monitor_vimeo
├── migrations/               # Alembic
├── tests/
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

---

## 2. Endpoints da API REST

### 2.1 Configuração do Sistema

#### `GET /api/v1/config`
Retorna a configuração atual. Acessível por Admin e Auditor.

**Response 200:**
```json
{
  "drive_root_folder_id": "1A2B3C4D5E6F",
  "vimeo_root_folder_uri": "/folders/987654",
  "updated_at": "2025-01-15T10:00:00Z"
}
```

#### `PUT /api/v1/config`
Atualiza a configuração. Somente Admin.

**Request:**
```json
{
  "drive_root_folder_id": "1A2B3C4D5E6F",
  "vimeo_root_folder_uri": "/folders/987654"
}
```

**Response 200:** configuração atualizada.

---

### 2.2 Vídeos

#### `GET /api/v1/videos`
Lista vídeos com filtros. Admin e Auditor.

**Query params:**
- `status` — filtra por status (ex: `ERROR`, `SUCCESS`)
- `relative_path` — filtra por pasta (ex: `/Python/Modulo_01/`)
- `page` — padrão: 1
- `page_size` — padrão: 50

**Response 200:**
```json
{
  "total": 142,
  "page": 1,
  "page_size": 50,
  "items": [
    {
      "id": "uuid",
      "filename": "aula_01.mp4",
      "relative_path": "/Python/Modulo_01/",
      "drive_file_id": "1A2B3C",
      "vimeo_uri": "/videos/987654321",
      "vimeo_folder_uri": "/folders/111222",
      "status": "SUCCESS",
      "checksum": "d41d8cd98f00b204e9800998ecf8427e",
      "file_size": 1073741824,
      "retry_count": 0,
      "last_error": null,
      "updated_at": "2025-01-15T12:30:00Z"
    }
  ]
}
```

#### `GET /api/v1/videos/{id}`
Detalhe com histórico de estados. Admin e Auditor.

**Response 200:**
```json
{
  "id": "uuid",
  "filename": "aula_01.mp4",
  "status": "ERROR",
  "retry_count": 2,
  "last_error": "Vimeo pull failed: 401 Unauthorized",
  "history": [
    { "from": null,              "to": "DISCOVERED",       "at": "2025-01-15T09:00:00Z", "message": null },
    { "from": "DISCOVERED",      "to": "DRIVE_READY",      "at": "2025-01-15T09:05:00Z", "message": "MD5 estável" },
    { "from": "DRIVE_READY",     "to": "VIMEO_UPLOADING",  "at": "2025-01-15T09:06:00Z", "message": null },
    { "from": "VIMEO_UPLOADING", "to": "ERROR",            "at": "2025-01-15T10:10:00Z", "message": "Token expirado" }
  ]
}
```

---

### 2.3 Ações Administrativas (somente Admin)

#### `POST /api/v1/admin/videos/{id}/retry`
Força retry de vídeo em `ERROR`. Zera `retry_count`.

**Response 200:**
```json
{ "message": "Retry enqueued", "video_id": "uuid" }
```

#### `POST /api/v1/admin/scan`
Dispara scan manual imediato.

**Response 202:**
```json
{ "message": "Scan started", "task_id": "celery-task-uuid" }
```

---

### 2.4 Relatórios (Admin e Auditor)

#### `GET /api/v1/reports/summary`
```json
{
  "total_files": 200,
  "by_status": {
    "SUCCESS": 185,
    "ERROR": 3,
    "VIMEO_UPLOADING": 2,
    "VIMEO_TRANSCODING": 5,
    "DRIVE_READY": 4,
    "DRIVE_SYNC_PENDING": 1,
    "DISCOVERED": 0
  }
}
```

#### `GET /api/v1/reports/by-folder`
Agrupa contagem por `relative_path`.

```json
[
  {
    "relative_path": "/Python/Modulo_01/",
    "counts": { "SUCCESS": 14, "ERROR": 0, "VIMEO_UPLOADING": 1 }
  }
]
```

#### `GET /api/v1/reports/export`
Exporta CSV com filtros opcionais.
**Response:** `text/csv`
Colunas: `id, filename, relative_path, status, vimeo_uri, retry_count, last_error, updated_at`

---

## 3. Tasks Celery

### Task: `scan_drive`

```python
@celery_app.task(name="tasks.scan_drive")
def scan_drive():
    config = SystemConfig.get()
    if not config:
        return

    drive_files = drive_service.list_all_mp4(config.drive_root_folder_id)

    for file in drive_files:
        if not Video.exists_by_drive_id(file["id"]):
            relative_path = drive_service.resolve_relative_path(
                file_path=file["path"],
                root_folder_id=config.drive_root_folder_id
            )
            Video.create(
                filename=file["name"],
                drive_file_id=file["id"],
                relative_path=relative_path,
                file_size=int(file.get("size", 0)),
                status="DISCOVERED"
            )
            StatusLog.create(video_id=..., from_status=None, to_status="DISCOVERED")
```

---

### Task: `check_integrity`

```python
@celery_app.task(name="tasks.check_integrity")
def check_integrity():
    videos = Video.get_by_statuses(["DISCOVERED", "DRIVE_SYNC_PENDING"])

    for video in videos:
        verifications, interval = get_verification_window(video.file_size)
        checksums = []

        for _ in range(verifications):
            data = drive_service.get_file_meta(video.drive_file_id)
            md5 = data.get("md5Checksum")

            if not md5:
                # Arquivo ainda sendo enviado para o Drive
                video.update(status="DRIVE_SYNC_PENDING")
                break

            checksums.append(md5)
            if _ < verifications - 1:
                time.sleep(interval)

        if len(checksums) == verifications and len(set(checksums)) == 1:
            # MD5 estável em todas as verificações
            video.update(
                status="DRIVE_READY",
                checksum=checksums[0],
                file_size=int(data.get("size", video.file_size))
            )
            StatusLog.create(video.id, "DRIVE_SYNC_PENDING", "DRIVE_READY", "MD5 estável")
```

---

### Task: `upload_to_vimeo`

```python
@celery_app.task(name="tasks.upload_to_vimeo")
def upload_to_vimeo(video_id: str):
    video = Video.get(video_id)
    config = SystemConfig.get()

    # Resolve pasta destino no Vimeo pelo relative_path
    # A estrutura deve espelhar o NAS/Drive (ver docs/vimeo_folder_structure.md)
    vimeo_folder_uri = vimeo_service.resolve_folder(
        root_uri=config.vimeo_root_folder_uri,
        relative_path=video.relative_path
    )

    # Token gerado imediatamente antes do POST — nunca antes
    download_url = drive_service.generate_download_url(video.drive_file_id)

    try:
        vimeo_uri = vimeo_service.pull_upload(
            link=download_url,
            name=video.filename,
            folder_uri=vimeo_folder_uri,
            size=video.file_size
        )
        video.update(
            status="VIMEO_UPLOADING",
            vimeo_uri=vimeo_uri,
            vimeo_folder_uri=vimeo_folder_uri
        )
        StatusLog.create(video.id, "DRIVE_READY", "VIMEO_UPLOADING")

    except Exception as e:
        video.update(
            retry_count=video.retry_count + 1,
            last_error=str(e)
        )
        if video.retry_count < 3:
            upload_to_vimeo.apply_async(args=[video_id], countdown=60)
        else:
            video.update(status="ERROR")
            StatusLog.create(video.id, "VIMEO_UPLOADING", "ERROR", str(e))
```

---

### Task: `monitor_vimeo`

```python
@celery_app.task(name="tasks.monitor_vimeo")
def monitor_vimeo():
    videos = Video.get_by_statuses(["VIMEO_UPLOADING", "VIMEO_TRANSCODING"])

    for video in videos:
        data = vimeo_service.get_status(video.vimeo_uri)
        upload_status = data["upload"]["status"]
        transcode_status = data["transcode"]["status"]

        if transcode_status == "complete":
            video.update(status="SUCCESS")
            StatusLog.create(video.id, "VIMEO_TRANSCODING", "SUCCESS")

        elif upload_status == "complete" and video.status == "VIMEO_UPLOADING":
            video.update(status="VIMEO_TRANSCODING")
            StatusLog.create(video.id, "VIMEO_UPLOADING", "VIMEO_TRANSCODING")

        elif "error" in [upload_status, transcode_status]:
            msg = f"upload={upload_status}, transcode={transcode_status}"
            video.update(retry_count=video.retry_count + 1, last_error=msg)

            if video.retry_count >= 3:
                video.update(status="ERROR")
                StatusLog.create(video.id, video.status, "ERROR", msg)
            else:
                upload_to_vimeo.apply_async(args=[str(video.id)], countdown=60)
```

---

## 4. Configuração Docker

### `requirements.txt`
```
fastapi==0.111.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.30
asyncpg==0.29.0
alembic==1.13.1
pydantic-settings==2.2.1
celery[redis]==5.4.0
redis==5.0.4
google-auth==2.29.0
google-api-python-client==2.131.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
httpx==0.27.0
python-dotenv==1.0.1
```

### `docker-compose.yml`
```yaml
version: "3.9"

services:
  api:
    build: .
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    env_file: .env
    ports:
      - "8000:8000"
    depends_on:
      - postgres
      - redis

  worker:
    build: .
    command: celery -A worker.celery_app worker --concurrency=2 --loglevel=info
    env_file: .env
    depends_on:
      - postgres
      - redis

  beat:
    build: .
    command: celery -A worker.celery_app beat --loglevel=info
    env_file: .env
    depends_on:
      - redis

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: drive_vimeo
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "127.0.0.1:5432:5432"

  redis:
    image: redis:7-alpine
    ports:
      - "127.0.0.1:6379:6379"

volumes:
  pgdata:
```

> Em produção via **Dokploy**: o mesmo `docker-compose.yml` é usado. As variáveis de ambiente são configuradas na interface do Dokploy, sem `.env` no repositório.
