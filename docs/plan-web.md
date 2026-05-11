# plan-web.md — Plano de Implementação do Dashboard (Frontend)

## 1. Visão Geral

Interface web para **Admin** e **Auditor** monitorarem a sincronização Drive → Vimeo. O Admin tem acesso a ações (retry, scan, configuração). O Auditor tem somente leitura.

**Stack (MVP):** Jinja2 + Tailwind CSS via CDN + JS inline com `fetch`
Servido diretamente pelo FastAPI — sem Node.js, sem build step, deploy imediato.

---

## 2. Controle de Acesso por Papel

| Elemento de UI | Admin | Auditor |
|----------------|-------|---------|
| Dashboard (leitura) | ✅ | ✅ |
| Listagem de vídeos | ✅ | ✅ |
| Detalhe do vídeo + histórico | ✅ | ✅ |
| Relatórios + exportar CSV | ✅ | ✅ |
| Botão "Retry" | ✅ | ❌ (oculto) |
| Botão "Scan manual" | ✅ | ❌ (oculto) |
| Tela de configuração (pasta raiz) | ✅ | ❌ (rota bloqueada) |

---

## 3. Páginas

### 3.1 Dashboard Principal — `/`

Visão geral da sincronização em tempo real.

```
┌─────────────────────────────────────────────────────────────┐
│  Drive → Vimeo Sync                    [Admin] [Scan Manual]│
├─────────────────────────────────────────────────────────────┤
│  RESUMO GERAL                                               │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │
│  │  200     │ │  185     │ │    3     │ │    7     │       │
│  │  Total   │ │ ✅ OK    │ │ ❌ Erro  │ │ ⏳ Fila  │       │
│  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │
├─────────────────────────────────────────────────────────────┤
│  POR PASTA                                                  │
│  /Python/Modulo_01/   [████████░░] 14/20 arquivos   70%    │
│  /Python/Modulo_02/   [████████  ]  8/10 arquivos   80%    │
│  /React/Modulo_01/    [██████████] 20/20 arquivos  100% ✅ │
├─────────────────────────────────────────────────────────────┤
│  ARQUIVOS COM ERRO                                          │
│  aula_05.mp4  /Python/Modulo_01/  tentativas: 3  [Retry]   │
│  aula_09.mp4  /Python/Modulo_01/  tentativas: 2  [Retry]   │
└─────────────────────────────────────────────────────────────┘
```

**Dados:** `GET /api/v1/reports/summary`, `GET /api/v1/reports/by-folder`, `GET /api/v1/videos?status=ERROR`
**Atualização:** polling a cada 30 segundos via `fetch`.
**Botão "Retry":** visível apenas para Admin.
**Botão "Scan Manual":** visível apenas para Admin.

---

### 3.2 Listagem de Vídeos — `/videos`

Tabela filtrável com todos os arquivos.

**Filtros disponíveis:**
- Status (dropdown: todos / SUCCESS / ERROR / em andamento)
- Pasta (`relative_path`)

**Tabela:**

| Arquivo | Pasta | Status | Vimeo | Tentativas | Atualizado | Ações |
|---------|-------|--------|-------|-----------|------------|-------|
| aula_01.mp4 | /Python/M01/ | ✅ SUCCESS | [Link] | 0 | 15/01 12:30 | [Ver] |
| aula_05.mp4 | /Python/M01/ | ❌ ERROR | — | 3 | 15/01 10:10 | [Ver] [Retry*] |

*Retry visível apenas para Admin.

**Badges de status:**

| Status | Cor | Ícone |
|--------|-----|-------|
| DISCOVERED | Cinza | 🔍 |
| DRIVE_SYNC_PENDING | Amarelo | ⏳ |
| DRIVE_READY | Azul | 📁 |
| VIMEO_UPLOADING | Laranja | ⬆️ |
| VIMEO_TRANSCODING | Roxo | 🎬 |
| SUCCESS | Verde | ✅ |
| ERROR | Vermelho | ❌ |

---

### 3.3 Detalhe do Vídeo — `/videos/{id}`

Histórico completo de estados e informações técnicas.

```
aula_01.mp4
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Pasta        /Python/Modulo_01/
Drive ID     1A2B3C4D5E6F
Vimeo        /videos/987654321 [Abrir ↗]
Tamanho      1.0 GB
Checksum     d41d8cd98f00b2...
Tentativas   0
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HISTÓRICO DE ESTADOS

09:00  DISCOVERED
09:02  DRIVE_SYNC_PENDING   (MD5 ausente, aguardando)
09:05  DRIVE_READY          (MD5 estável após 3 verificações)
09:06  VIMEO_UPLOADING      (pull iniciado)
09:45  VIMEO_TRANSCODING    (upload concluído)
11:02  SUCCESS ✅
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Para vídeos em `ERROR`, exibe o box de log:
```
ÚLTIMO ERRO
┌─────────────────────────────────┐
│ Vimeo pull failed: 401          │
│ Unauthorized. Token may have    │
│ expired before pull started.    │
└─────────────────────────────────┘
                        [Retry Manual*]
```
*Visível apenas para Admin.

---

### 3.4 Configuração — `/config` (somente Admin)

Formulário único de configuração do sistema. Preenchido **uma única vez**.

```
CONFIGURAÇÃO DO SISTEMA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ID da pasta raiz no Google Drive:
[ 1A2B3C4D5E6F                                ]
(ID visível na URL do Drive ao abrir a pasta)

URI da pasta raiz no Vimeo:
[ /folders/987654                             ]
(URI retornada pela API do Vimeo)

                                      [Salvar]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  O sistema monitorará apenas esta pasta e suas subpastas.
    A estrutura de subpastas no Vimeo deve ser idêntica ao Drive.
```

---

### 3.5 Relatórios — `/reports` (Admin e Auditor)

```
RELATÓRIO DE SINCRONIZAÇÃO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Filtros: [Todas as pastas ▼]  [Todos os status ▼]
         De: [__/__/____]     Até: [__/__/____]
                                    [Exportar CSV]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Gráfico de barras: vídeos por status
Tabela: por pasta com contagem por status
```

---

## 4. Estados de UI

| Situação | Comportamento |
|----------|---------------|
| API offline | Banner vermelho: "Não foi possível conectar à API" |
| Scan em andamento | Spinner: "Varredura em andamento..." |
| Retry enviado | Toast verde: "Retry agendado com sucesso" |
| Nenhum resultado | "Nenhum vídeo encontrado para os filtros aplicados" |
| Configuração ausente | Banner amarelo: "Configure a pasta raiz para iniciar o monitoramento" |

---

## 5. Implementação (MVP — Jinja2)

```
app/
└── templates/
    ├── base.html          # Layout, nav, CSS Tailwind CDN
    ├── dashboard.html     # Página principal
    ├── videos.html        # Listagem com filtros
    ├── video_detail.html  # Detalhe + histórico
    ├── config.html        # Configuração (Admin only)
    └── reports.html       # Relatórios + exportação
```

**Polling de atualização (JS inline):**
```javascript
setInterval(async () => {
  const res = await fetch('/api/v1/reports/summary');
  const data = await res.json();
  document.getElementById('total-success').textContent = data.by_status.SUCCESS;
  // atualiza demais contadores...
}, 30000);
```
