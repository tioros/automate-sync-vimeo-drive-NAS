# spec.md — Especificação Funcional do Sistema Drive → Vimeo

## 1. Visão Geral

Sistema de sincronização automática de vídeos do **Google Drive para o Vimeo**, sem que os arquivos transitem pela VPS.

O pipeline monitora uma **pasta raiz única no Google Drive**, valida a integridade dos arquivos e dispara o upload para o Vimeo via **pull approach** — os servidores do Vimeo baixam o arquivo diretamente do Google. A estrutura de subpastas do Drive é espelhada no Vimeo, onde já existe criada manualmente.

---

## 2. Premissas Fixas do Sistema

| Premissa | Detalhe |
|----------|---------|
| **Pasta raiz Drive** | Uma única pasta configurada. O sistema monitora apenas ela e suas subpastas. Nenhuma outra pasta do Drive é tocada. |
| **Pasta raiz Vimeo** | Uma única pasta raiz já existente no Vimeo, com subpastas criadas manualmente espelhando a estrutura do Drive. |
| **Arquivos nunca passam pela VPS** | O Vimeo faz pull direto do Google. A VPS apenas orquestra. |
| **Estrutura de pastas idêntica** | O `relative_path` de um arquivo no Drive é o mesmo no Vimeo. O sistema usa isso para encontrar a pasta destino correta. |
| **Expectativas por módulo/curso** | Será implementado em etapa posterior, após a conexão Drive ↔ Vimeo estar validada em produção. |

---

## 3. Atores

| Ator | Papel |
|------|-------|
| **Admin** | Configura o sistema (pasta raiz Drive, pasta raiz Vimeo). Monitora o dashboard. Executa ações corretivas (retry, scan manual). |
| **Auditor** | Acesso somente leitura ao dashboard e relatórios. Não executa ações. |
| **Scanner** | Processo automatizado que varre a pasta raiz do Drive e sincroniza com o banco. |
| **Worker** | Processo Celery que executa o upload e monitora o status no Vimeo. |
| **Google Drive** | Fonte dos arquivos. Sincronizado pelo cliente local (Google Drive Desktop). |
| **Vimeo API** | Destino final. Realiza o download diretamente do Google via pull. |

---

## 4. Casos de Uso

### UC-01 — Admin configura o sistema

**Ator:** Admin
**Fluxo:**
1. Admin acessa o dashboard.
2. Informa o `drive_root_folder_id` (ID da pasta raiz no Drive).
3. Informa o `vimeo_root_folder_uri` (URI da pasta raiz no Vimeo).
4. Salva. O scanner passa a operar sobre essa configuração.

**Resultado:** `system_config` preenchido. Sistema operacional.

---

### UC-02 — Scanner descobre arquivos novos

**Ator:** Scanner (automatizado, a cada 5 minutos)
**Fluxo:**
1. Percorre recursivamente a pasta raiz do Drive configurada em `system_config`.
2. Para cada arquivo `.mp4` não existente no banco: cria registro com `status = DISCOVERED`.
3. Calcula `relative_path` em relação à pasta raiz.

**Exemplo:**
```
Drive raiz configurada : ID da pasta /Cursos/
Arquivo encontrado     : /Cursos/Python/Modulo_01/aula_01.mp4
relative_path gravado  : /Python/Modulo_01/
filename gravado       : aula_01.mp4
```

---

### UC-03 — Verificador confirma integridade do arquivo

**Ator:** Worker (Celery task periódico)
**Fluxo:**
1. Seleciona registros com `status IN (DISCOVERED, DRIVE_SYNC_PENDING)`.
2. Consulta Drive API: campos `md5Checksum` + `size`.
3. Se `md5Checksum` ausente → arquivo ainda sincronizando → `DRIVE_SYNC_PENDING`.
4. Aplica janela de verificação proporcional ao tamanho:

| Tamanho | Verificações consecutivas | Intervalo entre cada |
|---------|--------------------------|----------------------|
| < 100 MB | 2 | 30 segundos |
| 100 MB – 500 MB | 2 | 60 segundos |
| > 500 MB | 3 | 90 segundos |

5. MD5 estável em todas as verificações → `status = DRIVE_READY`, armazena `checksum` e `file_size`.

**Por que o MD5 pode parecer estável e ainda estar errado:**
O Google Drive calcula o MD5 sobre os chunks já recebidos. Durante um upload lento, o hash pode ficar estável por 60–90 segundos enquanto o arquivo ainda está incompleto. A janela proporcional ao tamanho reduz esse risco: arquivos grandes exigem mais verificações e intervalos maiores antes de serem liberados.

---

### UC-04 — Worker dispara upload para o Vimeo

**Ator:** Worker (Celery task)
**Pré-condição:** `status = DRIVE_READY`
**Fluxo:**
1. Resolve o `vimeo_folder_uri` destino consultando a Vimeo API pela pasta correspondente ao `relative_path` dentro da raiz Vimeo configurada. A pasta já existe — nunca é criada pelo sistema.
2. Gera URL de download autenticada via Service Account (token válido ~1h), imediatamente antes do POST.
3. Envia `POST https://api.vimeo.com/me/videos` com `approach: pull`, a URL gerada e o `folder_uri`.
4. Armazena `vimeo_uri` retornado e atualiza `status = VIMEO_UPLOADING`.

**Crítico:** O token nunca é armazenado no banco. É gerado sob demanda e usado imediatamente.

---

### UC-05 — Monitor acompanha transcodificação

**Ator:** Worker (Celery task periódico)
**Pré-condição:** `status IN (VIMEO_UPLOADING, VIMEO_TRANSCODING)`
**Fluxo:**
Polling `GET https://api.vimeo.com/videos/{ID}` a cada 30 segundos.

| `upload.status` | `transcode.status` | Ação |
|---|---|---|
| `in_progress` | qualquer | Mantém `VIMEO_UPLOADING` |
| `complete` | `in_progress` | Atualiza para `VIMEO_TRANSCODING` |
| `complete` | `complete` | Atualiza para `SUCCESS` |
| `error` (qualquer) | `error` (qualquer) | `retry_count++` → retry ou `ERROR` |

---

### UC-06 — Retry automático em falha

**Ator:** Worker
**Fluxo:**
1. Falha detectada → `retry_count++`, `last_error` preenchido com mensagem.
2. `retry_count < 3`: gera novo token SA, reenfileira job (retorna ao UC-04).
3. `retry_count >= 3`: `status = ERROR`. Admin notificado via dashboard.

---

### UC-07 — Admin força retry manual

**Ator:** Admin
**Fluxo:**
1. Admin localiza vídeo em `ERROR` no dashboard.
2. Clica em "Retry manual".
3. Sistema zera `retry_count`, gera novo token e reenfileira.

---

### UC-08 — Auditor consulta relatórios

**Ator:** Auditor
**Acesso:** Somente leitura. Sem botões de ação.
**Fluxo:**
1. Visualiza vídeos por status e por pasta.
2. Aplica filtros (status, pasta, período).
3. Exporta CSV.

---

## 5. Regras de Negócio

| ID | Regra |
|----|-------|
| RN-01 | O arquivo nunca trafega pelo disco da VPS. |
| RN-02 | Token SA gerado imediatamente antes do POST ao Vimeo. Nunca armazenado. |
| RN-03 | Janela de verificação de MD5 proporcional ao tamanho do arquivo. |
| RN-04 | Máximo de 2 uploads simultâneos ao Vimeo. |
| RN-05 | Máximo de 3 tentativas automáticas por arquivo. |
| RN-06 | `retry_count` nunca zerado automaticamente — apenas por ação do Admin. |
| RN-07 | O sistema monitora **somente** a pasta raiz configurada no Drive. |
| RN-08 | A estrutura de pastas no Vimeo já existe e nunca é criada pelo sistema. Veja [vimeo_folder_structure.md](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/vimeo_folder_structure.md). |
| RN-09 | Admin tem acesso total. Auditor tem somente leitura. |

---

## 6. Requisitos Não-Funcionais

| ID | Requisito |
|----|-----------|
| RNF-01 | Processa até 100 GB/dia sem consumir disco da VPS para os vídeos. |
| RNF-02 | Resiliente a reinicializações — retoma exatamente onde parou. |
| RNF-03 | Dashboard com defasagem máxima de 1 minuto. |
| RNF-04 | Todas as transições de estado registradas com timestamp. |
| RNF-05 | Deploy via Docker Desktop (local) e Dokploy (produção na VPS). |
