# design_patterns.md — Princípios de Design e Engenharia

Este documento detalha as escolhas arquiteturais e padrões de design aplicados no sistema **Drive → Vimeo Sync**, com foco em robustez, manutenibilidade e escalabilidade.

---

## 1. Domain-Driven Design (DDD)

O sistema foi modelado seguindo os princípios de DDD para garantir que a lógica de negócio seja o centro da aplicação.

### 1.1 Ubiquitous Language (Linguagem Ubíqua)
Termos definidos entre stakeholders e desenvolvedores que refletem fielmente o domínio:
- **Discovery (Descoberta):** O ato de identificar novos arquivos no Drive.
- **Integrity Window (Janela de Integridade):** O período de validação de MD5 para garantir que o arquivo terminou de sincronizar no Drive.
- **Pull Approach:** A estratégia de fazer o Vimeo baixar do Google, em vez da VPS "empurrar" o arquivo.
- **State Machine (Máquina de Estados):** O ciclo de vida rigoroso de um vídeo (`DISCOVERED` -> `DRIVE_READY` -> `SUCCESS`).

### 1.2 Entidades e Agregados
- **Video (Agregado Raiz):** A entidade central que encapsula todo o estado, metadados e histórico. Todas as ações (retry, status update) orbitam em torno do ID do vídeo.
- **SystemConfig:** Entidade de configuração global que dita os limites do contexto de execução.

### 1.3 Camadas (Layered Architecture)
O projeto segue uma separação clara:
1.  **Interfaces:** FastAPI (REST/Dashboard).
2.  **Aplicação/Orquestração:** Celery Tasks que coordenam o fluxo.
3.  **Domínio/Serviços:** Lógica pura de integração com Google/Vimeo (encapsulada em `services/`).
4.  **Infraestrutura:** Repositórios, modelos SQLAlchemy e conexões externas.

---

## 2. System Design & Resiliência

O design do sistema prioriza a **resiliência passiva** e a **consistência eventual**.

### 2.1 Orquestração Baseada em Estado
Em vez de um script linear longo, o sistema usa uma **Máquina de Estados persistida no PostgreSQL**.
- **Vantagem:** Se o worker cair, o próximo ciclo do `monitor_vimeo` ou `check_integrity` retoma exatamente de onde parou. O sistema é inerentemente *stateless* em sua execução.

### 2.2 Desacoplamento via Filas
O uso de **Celery + Redis** garante que picos de descoberta de arquivos no Drive não sobrecarreguem a API ou o processo de upload.
- O `Celery Beat` atua como o metrônomo do sistema, garantindo que as tarefas de varredura e monitoramento ocorram em intervalos previsíveis.

---

## 3. CQRS (Command Query Responsibility Segregation)

Embora não use bancos de dados separados para leitura e escrita, o sistema aplica o padrão CQRS logicamente:

- **Commands (Escrita):** Executados pelos Workers. Eles alteram o estado do vídeo, incrementam tentativas e registram logs. São operações assíncronas e pesadas.
- **Queries (Leitura):** Executadas pela API FastAPI para alimentar o Dashboard e Relatórios. São otimizadas por índices (ex: `idx_videos_status`) e focadas em fornecer feedback imediato ao Admin, sem interferir na lógica de processamento.

---

## 4. Clean Code & SOLID

A estrutura do código foi planejada para ser legível e fácil de testar.

- **S (Single Responsibility):** Cada Service (`drive.py`, `vimeo.py`) lida apenas com sua respectiva API. Cada Task Celery tem um único propósito (Scan, Integrity, Upload ou Monitor).
- **O (Open/Closed):** A máquina de estados permite adicionar novos status (ex: `VIMEO_OPTIMIZING`) sem alterar a lógica de descoberta de arquivos.
- **D (Dependency Inversion):** O uso de dependências do FastAPI permite injetar sessões de banco de dados e configurações, facilitando mocks em testes unitários.
- **Dry (Don't Repeat Yourself):** A lógica de cálculo de `relative_path` e validação de tokens é centralizada e reutilizada.

---

## 5. Escalabilidade e Performance

O sistema foi desenhado para escalar horizontalmente e verticalmente com baixo custo.

### 5.1 Otimização de Recursos (Pull Approach)
A maior inovação em escalabilidade deste sistema é a **eliminação do trânsito de dados pela VPS**.
- **Escalabilidade de Banda:** A banda de rede da VPS não é o gargalo. O limite de 100 GB/dia (ou mais) é ditado apenas pelas cotas da Google API e Vimeo, não pelo hardware da VPS.
- **Escalabilidade de Disco:** Como o arquivo nunca toca o disco, a VPS pode rodar com apenas 20GB de armazenamento, independente do tamanho dos vídeos processados.

### 5.2 Concorrência Controlada
- O uso de `concurrency=2` no Celery Worker é uma decisão de design para respeitar os limites de *rate limit* do Vimeo, evitando bloqueios de IP e garantindo uma fila de processamento estável.

### 5.3 Banco de Dados
O uso de índices estratégicos no PostgreSQL garante que, mesmo com dezenas de milhares de registros históricos, o dashboard carregue em milissegundos.

---

## 6. Tratamento de Erros e Tolerância a Falhas

O sistema adota uma postura de "falha segura" (fail-safe):

- **Retentativas Exponenciais (Exponential Backoff):** Embora o Celery suporte isso nativamente, o sistema implementa uma lógica customizada onde cada falha incrementa um `retry_count` e registra o `last_error`. Isso permite que o Admin veja exatamente por que algo falhou antes de decidir por um retry manual.
- **Isolamento de Falhas:** Uma falha no upload de um vídeo específico não afeta a fila de outros vídeos, graças ao isolamento provido pelos workers do Celery.
- **Validação de Payload:** O uso de Pydantic garante que dados corrompidos ou malformados das APIs externas (Google/Vimeo) sejam barrados na entrada, evitando estados inconsistentes no banco.

---

## 7. Consistência Eventual e Idempotência

O sistema não garante consistência imediata, mas sim **consistência eventual**:

- **Idempotência das Tasks:** Todas as tarefas (Scanner, Uploader, Monitor) são projetadas para serem idempotentes. Se o `scan_drive` rodar duas vezes simultaneamente, a restrição de `UNIQUE` no `drive_file_id` impede duplicidade.
- **Sincronização de Estado:** O estado de "verdade" é o que está no banco de dados. As APIs externas são consultadas apenas para transicionar esses estados.

---

## 8. Observabilidade (Audit Trail)

Design focado em transparência total para o usuário Admin:

- **Status Logs:** Toda e qualquer mudança de estado é registrada na tabela `status_logs`. Isso não é apenas para auditoria, mas para diagnóstico técnico, permitindo reconstruir a "vida" de um arquivo desde a descoberta até o sucesso.
- **Monitoramento de Saúde:** A separação entre `api`, `worker` e `beat` permite monitorar a saúde de cada componente de forma isolada, facilitando a identificação de gargalos (ex: fila do Redis crescendo muito).
