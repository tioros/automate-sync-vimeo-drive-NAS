# Índice da Documentação — Drive → Vimeo Sync

Este índice serve como guia de navegação para toda a documentação técnica e funcional do sistema. Para entender o projeto, recomenda-se a leitura na ordem sugerida abaixo.

---

## 1. Documentação de Negócio e Funcional
- **[Especificação Funcional (spec.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/spec.md):** Visão geral, atores, casos de uso e regras de negócio.
- **[Estrutura de Pastas (vimeo_folder_structure.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/vimeo_folder_structure.md):** Detalhamento da hierarquia NAS espelhada no Vimeo.

---

## 2. Documentação Técnica e Arquitetura
- **[Arquitetura do Sistema (architecture.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/architecture.md):** Diagramas de componentes, fluxos de dados e infraestrutura.
- **[Padrões de Design (design_patterns.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/design_patterns.md):** Princípios de DDD, CQRS, Clean Code e estratégias de escalabilidade.
- **[Contratos e Schemas (contracts.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/contracts.md):** Modelagem do banco de dados e especificações das APIs Google/Vimeo.

---

## 3. Planos de Implementação
- **[Plano de Backend/API (plan-api.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/plan-api.md):** Detalhes das tarefas Celery, endpoints e estrutura de arquivos.
- **[Plano de Frontend/Dashboard (plan-web.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/plan-web.md):** Protótipos de UI e estados da interface.
- **[Plano de Execução (plan.md)](file:///c:/Users/joao.borges/Downloads/drive-vimeo-sync/docs/plan.md):** Cronograma de fases, critérios de conclusão e análise de riscos.

---

## 4. Glossário Rápido de Conceitos
- **relative_path:** O caminho de um vídeo a partir da raiz configurada (ex: `/01 - Janeiro/01/EJA/INTEGRAL/`).
- **Pull Approach:** Método onde o Vimeo baixa o vídeo diretamente do Google via URL autenticada.
- **Janela de Integridade:** Validação múltipla de MD5 para garantir que o upload do arquivo para o Drive foi concluído.
