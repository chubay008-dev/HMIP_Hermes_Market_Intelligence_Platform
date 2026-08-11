# HMIP Documentation Pack

This repository contains the unified HMIP documentation set for architecture, runtime, domain, engineering, implementation, and appendices.

## Purpose

HMIP is designed as an Enterprise AI Operating System with a single-agent autonomous architecture centered on Hermes Agent.

This documentation pack defines the system vision, runtime model, domain boundaries, API and interface contracts, coding standard, ADRs, testing standard, deployment guide, backlog, data contract, configuration specification, repository mapping, acceptance criteria, ADR details, glossary, traceability matrix, example workflows, and sample schemas.

## Document order

Read and apply the documents in the following order:

1. `01_System_Specification.md`
2. `02_Runtime_Specification.md`
3. `03_Domain_Specification.md`
4. `04_API_Contract.md`
5. `05_Interface_Contract.md`
6. `06_Coding_Standard.md`
7. `07_ADR.md`
8. `08_Testing_Standard.md`
9. `09_Deployment_Guide.md`
10. `10_Project_Backlog.md`
11. `11_Master_Prompt_Claude.md`
12. `12_Data_Contract.md`
13. `13_Configuration_Specification.md`
14. `14_Repository_File_Mapping.md`
15. `15_Acceptance_Criteria.md`
16. `16_ADR_Details.md`
17. `17_Glossary.md`
18. `18_Traceability_Matrix.md`
19. `19_Example_Workflows.md`
20. `20_Sample_Schemas.md`

## Reading policy

If there is any conflict between documents, use this priority order:

1. `07_ADR.md`
2. `16_ADR_Details.md`
3. `01_System_Specification.md`
4. `02_Runtime_Specification.md`
5. `03_Domain_Specification.md`
6. `04_API_Contract.md`
7. `05_Interface_Contract.md`
8. `06_Coding_Standard.md`
9. `08_Testing_Standard.md`
10. `09_Deployment_Guide.md`
11. `10_Project_Backlog.md`
12. `12_Data_Contract.md`
13. `13_Configuration_Specification.md`
14. `14_Repository_File_Mapping.md`
15. `15_Acceptance_Criteria.md`
16. `11_Master_Prompt_Claude.md`
17. `17_Glossary.md`
18. `18_Traceability_Matrix.md`
19. `19_Example_Workflows.md`
20. `20_Sample_Schemas.md`

## How to use

- Use the specification documents to understand architecture and contract.
- Use the engineering documents to implement code and tests.
- Use the appendices to standardize terminology, traceability, example workflows, and sample data.
- Use `11_Master_Prompt_Claude.md` when instructing Claude or another coding agent.

## Repository structure

```text
HMIP-DOCS/
├── README.md
├── 01_System_Specification.md
├── 02_Runtime_Specification.md
├── 03_Domain_Specification.md
├── 04_API_Contract.md
├── 05_Interface_Contract.md
├── 06_Coding_Standard.md
├── 07_ADR.md
├── 08_Testing_Standard.md
├── 09_Deployment_Guide.md
├── 10_Project_Backlog.md
├── 11_Master_Prompt_Claude.md
├── 12_Data_Contract.md
├── 13_Configuration_Specification.md
├── 14_Repository_File_Mapping.md
├── 15_Acceptance_Criteria.md
├── 16_ADR_Details.md
└── appendices/
    ├── 17_Glossary.md
    ├── 18_Traceability_Matrix.md
    ├── 19_Example_Workflows.md
    └── 20_Sample_Schemas.md
```

## Primary implementation target

The first vertical slice is PRC-001 Daily Beer Price Collection.

## Notes

This pack is intended to be the single source of truth for HMIP architecture and implementation guidance.