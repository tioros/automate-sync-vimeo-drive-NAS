# vimeo_folder_structure.md — Estrutura de Pastas do Vimeo (Espelhamento NAS)

Este documento descreve a hierarquia de pastas utilizada no Vimeo para organizar os vídeos sincronizados do Google Drive. Esta estrutura é idêntica à utilizada no NAS da instituição e deve ser mantida manualmente no Vimeo para que o sistema de sincronização funcione corretamente.

---

## 1. Visão Geral

O sistema **Drive → Vimeo Sync** opera sob a premissa de que a estrutura de pastas no Vimeo já existe e espelha exatamente a organização do Google Drive. O sistema utiliza o `relative_path` do arquivo no Drive para localizar a pasta correspondente no Vimeo.

---

## 2. Hierarquia de Pastas

A estrutura segue uma lógica temporal descendente, seguida por segmentação pedagógica e de período:

### Nível 1: Mês
As pastas raiz de primeiro nível são organizadas pelos 12 meses do ano, seguindo o padrão `[MM] - [Nome do Mês]`.
- `01 - Janeiro`
- `02 - Fevereiro`
- ...
- `12 - Dezembro`

### Nível 2: Dia
Dentro de cada mês, existem subpastas para cada dia do mês (01 a 31).
- `01`
- `02`
- ...
- `31`

### Nível 3: Nível de Ensino (Pedagógico)
Dentro de cada dia, os arquivos são segregados por nível de ensino:
- `EJA`
- `ENSINO MÉDIO`

### Nível 4: Período / Modalidade
Dentro do nível de ensino, a última subdivisão refere-se ao período da aula:
- `INTEGRAL`
- `PARCIAL MANHÃ`
- `PARCIAL TARDE`
- `PARCIAL NOITE`

---

## 3. Exemplo de Caminho Completo

Um vídeo de uma aula do Ensino Médio Integral ocorrida em 15 de Janeiro seria organizado no seguinte caminho:
`01 - Janeiro / 15 / ENSINO MÉDIO / INTEGRAL / aula_exemplo.mp4`

---

## 4. Regras de Sincronização

1.  **Existência Prévia:** O sistema **não cria pastas no Vimeo**. Se um caminho de subpasta não existir no Vimeo no momento da sincronização, o processo resultará em erro até que o Admin crie a pasta manualmente.
2.  **Case Sensitivity:** A comparação de nomes de pastas é sensível a maiúsculas/minúsculas e acentuação. O nome no Vimeo deve ser idêntico ao nome no Google Drive.
3.  **Mapeamento Determinístico:** O `relative_path` calculado pelo Scanner (ex: `/01 - Janeiro/15/ENSINO MÉDIO/INTEGRAL/`) é concatenado à `vimeo_root_folder_uri` para realizar o lookup via API.

---

## 5. Manutenção

Como a estrutura é baseada no calendário e na grade pedagógica, recomenda-se que a estrutura do ano letivo seja criada em lote (bulk) no início de cada período para evitar erros de "Pasta não encontrada" durante a operação diária do Scanner.
