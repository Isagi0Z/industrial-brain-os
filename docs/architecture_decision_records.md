# Industrial Brain OS: Architecture Decision Records (ADR)

This document contains the official Architecture Decision Records (ADR) for the Industrial Brain OS project.

---

## ADR-001: Why FastAPI

* **ADR Number**: ADR-001
* **Title**: Selection of FastAPI as the Primary Backend Web Framework
* **Status**: Approved
* **Context**: Industrial Brain OS requires a high-performance, asynchronous web server framework in Python to serve ML pipelines, manage database connections, and handle high concurrent client requests during production runs.
* **Decision**: Adopt FastAPI as the primary backend REST and WebSocket API framework.
* **Alternatives Considered**:
  1. *Django*: Rejected due to its synchronous default nature, heavy ORM overhead, and lack of native async support for microservice architectures.
  2. *Flask*: Rejected because it lacks built-in async execution, type validation, and automatic OpenAPI generation, requiring external packages for validation.
  3. *Tornado*: Rejected because of its smaller modern ecosystem and lack of out-of-the-box integration with OpenAPI, Pydantic, and async database drivers.
* **Pros**:
  - Extremely high performance, matching Node.js and Go speed profiles using Starlette and Uvicorn.
  - Native support for asynchronous programming (`async`/`await`), crucial for non-blocking database and model inference calls.
  - Automatic OpenAPI/Swagger generation from Pydantic models, reducing sync errors between backend APIs and frontend teams.
* **Cons**:
  - Requires developers to understand async event loops and avoid blocking I/O calls.
* **Trade-offs**: Sacrifices Django's rich admin panel and built-in migration suites for runtime speed, async compliance, and API generation simplicity.
* **Risks**: Blocking synchronous libraries (like older DB drivers) can stall the event loop.
* **Mitigation**: Wrap any blocking call inside thread pools using Starlette's `run_in_threadpool`.
* **Consequences**: Fast development cycles, clean API documentation, and low memory footprint under heavy concurrent traffic.
* **Future Revisions**: Re-evaluate if Go-based services are needed for performance-critical pipelines.

---

## ADR-002: Why React + Vite

* **ADR Number**: ADR-002
* **Title**: Selection of React + Vite for the Frontend Platform
* **Status**: Approved
* **Context**: The operators and reliability engineers need a responsive dashboard with complex graph visualizations, document views, and chat tools.
* **Decision**: Adopt React.js combined with Vite as the bundler.
* **Alternatives Considered**:
  1. *Next.js*: Rejected because server-side rendering (SSR) is not required for internal dashboards. This adds deployment complexity in air-gapped environments.
  2. *Angular*: Rejected due to its steep learning curve and heavier runtime footprint.
  3. *Vue.js*: Rejected because React has a larger ecosystem for data visualization (such as Cytoscape.js and D3.js).
* **Pros**:
  - Vite offers fast hot-module replacement (HMR) and optimized build times using esbuild.
  - React's component model simplifies state management for interactive chat features.
* **Cons**:
  - Client-side rendering (CSR) requires downloading the bundle before initialization, which can slow down first-page loads on older client systems.
* **Trade-offs**: We trade server-side optimization features for build simplicity and easier deployment in offline environments.
* **Risks**: Large bundle sizes can impact load times on older terminals in remote environments.
* **Mitigation**: Implement code splitting and route-based lazy loading.
* **Consequences**: A responsive frontend developer environment and reliable client-side rendering.
* **Future Revisions**: None planned unless specific legacy browser support requires custom compilation targets.

---

## ADR-003: Why PostgreSQL

* **ADR Number**: ADR-003
* **Title**: Selection of PostgreSQL as the Core Relational Database
* **Status**: Approved
* **Context**: The platform needs to store configuration settings, transactional records, audit trails, and user roles reliably.
* **Decision**: Deploy PostgreSQL as the primary relational store.
* **Alternatives Considered**:
  1. *MySQL*: Rejected because it has weaker JSON querying capabilities and lacks advanced time-series extensions.
  2. *MongoDB*: Rejected due to the lack of strict relational constraints and transaction safety, which are critical for audit logs.
  3. *SQLite*: Rejected because it cannot handle concurrent write operations and lacks enterprise scalability.
* **Pros**:
  - High compliance with SQL standards and transaction safety.
  - Native JSONB support allows storing semi-structured metadata.
  - Easily extendable with plugins like TimescaleDB for time-series data and pgvector for vector indexes.
* **Cons**:
  - High memory usage when handling large volumes of concurrent connections.
* **Trade-offs**: We choose relational consistency over the flexible schema structures of NoSQL databases.
* **Risks**: Complex joins on unindexed columns can degrade performance as data grows.
* **Mitigation**: Enforce strict query monitoring, add indexes on key search paths, and implement connection pooling.
* **Consequences**: Consistent transactions, simplified audit records, and flexibility to support time-series data.
* **Future Revisions**: Re-evaluate connection limits once concurrent user traffic scales past threshold levels.

---

## ADR-004: Why Neo4j Community

* **ADR Number**: ADR-004
* **Title**: Selection of Neo4j Community Edition for the Knowledge Graph
* **Status**: Approved
* **Context**: We need to query relationships across assets, sensors, failure modes, and procedures using graph queries.
* **Decision**: Adopt Neo4j Community Edition as the primary Graph Database.
* **Alternatives Considered**:
  1. *Apache AGE (Postgres Extension)*: Rejected because its Cypher translation engine is less mature and lacks advanced graph algorithms.
  2. *Amazon Neptune*: Rejected because it requires AWS cloud environments, breaking our requirement for offline/on-premises deployments.
  3. *ArangoDB*: Rejected because Cypher is the standard language for graph querying, whereas ArangoDB uses a custom query language.
* **Pros**:
  - Cypher is the de facto standard for graph queries, with rich library support.
  - High performance for complex multi-hop queries.
  - Strong integration with LLM tools like LangChain and LlamaIndex.
* **Cons**:
  - Neo4j Community Edition is limited to single-node deployments and lacks automatic clustering.
* **Trade-offs**: We accept single-node limitations in the free version to benefit from mature Cypher integrations and rich documentation.
* **Risks**: Single-node setups can become performance bottlenecks as the graph grows.
* **Mitigation**: Optimize queries by setting depth limits and caching frequent traversals in Redis.
* **Consequences**: Fast graph operations and standard integration patterns.
* **Future Revisions**: Migrate to Neo4j Enterprise or Apache AGE if scaling needs exceed single-node limits.

---

## ADR-005: Why Qdrant

* **ADR Number**: ADR-005
* **Title**: Selection of Qdrant as the Vector Database
* **Status**: Approved
* **Context**: The platform needs to perform fast vector similarity searches across millions of document chunks.
* **Decision**: Deploy Qdrant Open Source Edition as our Vector Database.
* **Alternatives Considered**:
  1. *Milvus*: Rejected due to its complex deployment footprint, which requires multiple microservices (MinIO, Pulsar, Etcd).
  2. *Chroma*: Rejected because it lacks clustering support and is not optimized for high-throughput enterprise production workloads.
  3. *PGVector*: Rejected because it suffers from higher latency and lower recall on high-dimensional vectors compared to dedicated vector stores.
* **Pros**:
  - Written in Rust, providing low latency and efficient memory usage.
  - Supports payload filtering, allowing us to enforce RBAC rules directly during vector search.
  - Provides scalar quantization to reduce memory usage at scale.
* **Cons**:
  - Smaller user community compared to older options like Milvus or Pinecone.
* **Trade-offs**: We choose a dedicated, high-performance vector store over the simplicity of using a single database (like PGVector).
* **Risks**: Memory footprint grows quickly as more vector indexes are added.
* **Mitigation**: Configure HNSW index parameters and enable scalar quantization to manage RAM usage.
* **Consequences**: Sub-10ms vector searches with support for metadata filters.
* **Future Revisions**: Evaluate GPU-accelerated index building if ingestion volume scales.

---

## ADR-006: Why MinIO

* **ADR Number**: ADR-006
* **Title**: Selection of MinIO as Object Storage
* **Status**: Approved
* **Context**: We need to store uploaded documents, images, and raw CAD files.
* **Decision**: Deploy MinIO as the primary object storage service.
* **Alternatives Considered**:
  1. *Local Filesystem Storage*: Rejected because it lacks version control, access policies, and is hard to scale horizontally.
  2. *AWS S3*: Rejected because it requires an active internet connection, which violates our air-gapped deployment requirement.
  3. *Ceph*: Rejected because it requires complex management overhead for simple prototype setups.
* **Pros**:
  - Provides an S3-compatible API, allowing us to switch to AWS S3 or other cloud providers without changing code.
  - Highly secure, supporting bucket policies and encryption at rest.
  - Lightweight and easy to run in on-premises container environments.
* **Cons**:
  - Storing metadata alongside files requires external database coordination.
* **Trade-offs**: We trade setup complexity for S3 API compatibility and scalability.
* **Risks**: Local drive failures can result in data loss if replication is not configured.
* **Mitigation**: Deploy MinIO with distributed erasure coding across separate drives.
* **Consequences**: S3-compliant object storage that runs locally in air-gapped environments.
* **Future Revisions**: Switch to cloud storage (like AWS S3) for cloud deployments.

---

## ADR-007: Why LangGraph

* **ADR Number**: ADR-007
* **Title**: Selection of LangGraph for Agent Workflows
* **Status**: Approved
* **Context**: The platform needs to execute complex, multi-step agent actions like Root Cause Analysis and compliance auditing.
* **Decision**: Use LangGraph as the core framework for agent state orchestration.
* **Alternatives Considered**:
  1. *AutoGen*: Rejected because its conversational agent model is hard to configure for strict, predictable workflows.
  2. *CrewAI*: Rejected because it is designed for role-play scenarios and lacks low-level control over state transitions.
  3. *LangChain (Legacy chains)*: Rejected because traditional chains only support sequential steps and cannot handle cyclic loops.
* **Pros**:
  - Provides state-machine configurations with support for loops and branches.
  - Built-in persistence layers support manual human-in-the-loop approvals.
  - Integrates with the LangChain ecosystem.
* **Cons**:
  - Has a steeper learning curve compared to simple sequential chains.
* **Trade-offs**: We choose predictable state control over autonomous agents.
* **Risks**: State structures can become complex and hard to maintain as workflow rules change.
* **Mitigation**: Keep agent graphs modular and enforce strict schema definitions for graph states.
* **Consequences**: Reliable, testable agent workflows with human-in-the-loop approvals.
* **Future Revisions**: Evaluate lighter graph engines if dependency overhead becomes a concern.

---

## ADR-008: Why GraphRAG

* **ADR Number**: ADR-008
* **Title**: Implementation of GraphRAG
* **Status**: Approved
* **Context**: Simple vector search often misses relationship context, such as locating component hierarchies in complex manuals.
* **Decision**: Implement GraphRAG by combining vector indexing with Graph Database traversals.
* **Alternatives Considered**:
  1. *Standard Vector RAG*: Rejected because it cannot resolve multi-hop relationships (e.g., finding failure modes for connected downstream assets).
  2. *Standard Knowledge Graph QA*: Rejected because it fails to answer queries that require analyzing unstructured text.
  3. *Long Context LLM Ingestion*: Rejected due to high token costs and poor recall performance on large documents.
* **Pros**:
  - Combines structured entity relationships with semantic vector search.
  - Provides clear citation paths by linking answers to specific graph nodes and source files.
  - Higher accuracy for complex queries about system dependencies.
* **Cons**:
  - Ingestion is slower and requires more processing power to construct the graph.
* **Trade-offs**: We trade higher ingestion overhead and complexity for improved response accuracy and reliability.
* **Risks**: Parsing errors can introduce incorrect relationships into the graph.
* **Mitigation**: Validate extracted relationships against our ontology schema before updating the database.
* **Consequences**: Accurate answers for complex system queries with clear citation sources.
* **Future Revisions**: Optimize graph construction using faster local models.

---

## ADR-009: Why Hybrid Retrieval

* **ADR Number**: ADR-009
* **Title**: Selection of a Multi-stage Hybrid Retrieval Pipeline
* **Status**: Approved
* **Context**: Industrial users need to search for precise item codes (e.g., "FT-101") as well as general operational concepts (e.g., "thermal stress").
* **Decision**: Implement a retrieval pipeline combining BM25, vector search, graph search, and reranking.
* **Alternatives Considered**:
  1. *Vector Search Only*: Rejected because it fails to retrieve exact technical codes and part numbers.
  2. *Lexical Search (BM25) Only*: Rejected because it cannot capture synonyms or conceptual meaning.
  3. *Parallel Retrieval without Reranking*: Rejected because combining results without a reranking step leads to poor context quality.
* **Pros**:
  - High precision for both exact codes and semantic concepts.
  - Reranking filters out irrelevant results, optimizing the LLM context window.
* **Cons**:
  - Increased query latency due to running multiple search steps and a reranker.
* **Trade-offs**: We trade slight increases in latency for significantly higher search recall and precision.
* **Mitigation**: Run retrieval steps in parallel and optimize the reranker model configuration.
* **Consequences**: High-quality search results with low hallucination rates.
* **Future Revisions**: None planned unless latency requirements require bypassing the reranker for simple queries.

---

## ADR-010: Why Industrial Ontology

* **ADR Number**: ADR-010
* **Title**: Selection of an Ontology-Driven Graph Schema
* **Status**: Approved
* **Context**: Unstructured graph extraction can lead to inconsistent node types, making the graph hard to query.
* **Decision**: Enforce a strict ontology schema aligned with ISO 14224 and ISO 15926 standards.
* **Alternatives Considered**:
  1. *Schema-less Graph (Open Extraction)*: Rejected because it leads to duplicate node types (e.g., "pump" vs. "pumping unit"), which breaks query logic.
  2. *Basic Taxonomy (Only Asset-Child)*: Rejected because it does not support modeling failure modes or safety rules.
  3. *Dynamic Schema Gen*: Rejected because it is unpredictable and hard to test.
* **Pros**:
  - Consistent node types and relationships across the platform.
  - Ensures compliance with international industrial standards.
  - Improves entity resolution during document parsing.
* **Cons**:
  - Requires manual design and updating of ontology files.
* **Trade-offs**: We choose schema consistency and standards compliance over ingestion speed.
* **Risks**: Ingested data that does not fit the ontology may be dropped.
* **Mitigation**: Create fallback classifications and schema update workflows for unmapped entities.
* **Consequences**: Clean, queryable knowledge graph with reliable entity resolution.
* **Future Revisions**: Automate ontology expansion using LLM recommendation models.

---

## ADR-011: Why PaddleOCR

* **ADR Number**: ADR-011
* **Title**: Selection of PaddleOCR as the Core OCR Engine
* **Status**: Approved
* **Context**: Engineering manuals and drawings often contain tabular layouts, small labels, and text orientations that must be parsed accurately.
* **Decision**: Deploy PaddleOCR as the primary text extraction engine.
* **Alternatives Considered**:
  1. *Tesseract OCR*: Rejected because it struggles with multi-column pages, tables, and non-horizontal text.
  2. *EasyOCR*: Rejected due to high memory usage and slower processing speeds on large documents.
  3. *Cloud OCR Services (AWS Textract, Azure Document Intelligence)*: Rejected because they require internet access and cloud dependencies.
* **Pros**:
  - High accuracy for tables, multi-column documents, and vertical text labels.
  - Fast execution speed on GPU instances.
  - Active open-source community.
* **Cons**:
  - Heavy installation footprint with PaddlePaddle library dependencies.
* **Trade-offs**: We accept a larger image size and complex install process to gain high table and layout parsing accuracy.
* **Risks**: Dependency conflicts during installation.
* **Mitigation**: Package PaddleOCR within isolated container environments.
* **Consequences**: High-quality text extraction from complex manuals and scans.
* **Future Revisions**: Evaluate lightweight OCR engines if memory constraints change.

---

## ADR-012: Why Layout-Aware Parsing

* **ADR Number**: ADR-012
* **Title**: Implementation of Layout-Aware Document Parsing
* **Status**: Approved
* **Context**: Standard text parsers ignore document structure, which can split tables or merge unrelated columns.
* **Decision**: Implement layout-aware parsing using LayoutLMv3 and object detection.
* **Alternatives Considered**:
  1. *Standard Text Extraction (PyPDF)*: Rejected because it ignores column boundaries and tables.
  2. *Naïve Chunking*: Rejected because it splits paragraphs and tables at arbitrary token limits, breaking semantic context.
  3. *Recursive Character Chunking*: Rejected because it cannot identify tables or headers.
* **Pros**:
  - Preserves tables, callouts, and lists in single logical blocks.
  - Implements hierarchical chunking based on document structure.
* **Cons**:
  - High CPU/GPU usage during the layout detection phase.
* **Trade-offs**: We trade parsing speed for highly accurate text blocks.
* **Risks**: Low-quality scans can confuse layout detection models.
* **Mitigation**: Fall back to standard extraction if layout detection confidence scores drop below thresholds.
* **Consequences**: Well-structured text chunks that improve vector search accuracy.
* **Future Revisions**: Train custom layout models on engineering drawing templates.

---

## ADR-013: Why Clean Architecture

* **ADR Number**: ADR-013
* **Title**: Adopting Clean Architecture for Backend Services
* **Status**: Approved
* **Context**: AI models and databases evolve rapidly; we need to change databases or APIs without rewriting our core business logic.
* **Decision**: Organize the codebase into layers: Domain, Application, Infrastructure, and Presentation.
* **Alternatives Considered**:
  1. *Monolithic MVC*: Rejected because it couples business logic with the database schema and framework.
  2. *Simple CRUD (FastAPI Routes directly contacting SQL)*: Rejected because it makes testing business logic without a database hard.
  3. *Microservices (from day 1)*: Rejected due to high development and deployment overhead for a prototype.
* **Pros**:
  - Domain logic is independent of databases and web frameworks.
  - High testability; business rules can be verified using simple unit tests.
  - Easy to swap libraries (e.g., switching from Neo4j to AGE).
* **Cons**:
  - Requires writing data transfer objects (DTOs) and interface files, increasing total file count.
* **Trade-offs**: We accept writing boilerplate mapping code to gain long-term codebase flexibility.
* **Risks**: Developers bypassing layers to speed up feature delivery.
* **Mitigation**: Enforce architectural boundaries using code review checks and import lints.
* **Consequences**: Highly testable backend code that can adapt to changing infrastructure.
* **Future Revisions**: None.

---

## ADR-014: Why Domain-Driven Design (DDD)

* **ADR Number**: ADR-014
* **Title**: Implementing Domain-Driven Design (DDD) for System State
* **Status**: Approved
* **Context**: Industrial operations have specific terms and boundaries that must be accurately modeled.
* **Decision**: Apply Domain-Driven Design principles, utilizing Aggregates, Entities, and Value Objects.
* **Alternatives Considered**:
  1. *Anemic Domain Model*: Rejected because it splits data from validation rules, causing inconsistent object states.
  2. *Active Record Pattern*: Rejected because it couples business entities directly with database queries.
  3. *No-Schema JSON Store*: Rejected due to lack of type safety for critical operational data.
* **Pros**:
  - Code uses terminology matching industrial operations.
  - Aggregates protect system data consistency.
  - Business rules are isolated within the domain layer.
* **Cons**:
  - Requires deep domain knowledge to design entities and boundaries correctly.
* **Trade-offs**: We invest time upfront in designing models to avoid database inconsistencies later.
* **Risks**: Designing aggregates that are too large, which can cause transaction conflicts.
* **Mitigation**: Design small aggregates and reference other aggregates by ID only.
* **Consequences**: Business entities match real-world operations and enforce validation rules.
* **Future Revisions**: None.

---

## ADR-015: Why Event-Driven Processing

* **ADR Number**: ADR-015
* **Title**: Adopting Event-Driven Processing for Document Pipelines
* **Status**: Approved
* **Context**: Parsing documents and extracting relationships are slow operations that can block web APIs if run synchronously.
* **Decision**: Implement an event-driven ingestion pipeline using Celery/Redis for background jobs.
* **Alternatives Considered**:
  1. *Synchronous API Execution*: Rejected because parsing large files can cause client requests to time out.
  2. *In-Process Threading*: Rejected because it blocks API worker memory and cannot scale across multiple servers.
  3. *Polled DB Status*: Rejected because polling introduces delays and increases database load.
* **Pros**:
  - Keeps web APIs fast and responsive.
  - Supports scaling worker nodes independently from the API server.
  - Handles temporary failures using automatic task retries.
* **Cons**:
  - Requires running and monitoring a message broker (Redis/RabbitMQ).
* **Trade-offs**: We add message queue infrastructure to guarantee system responsiveness under heavy file loads.
* **Risks**: Broker queues can overflow if ingestion rate exceeds processing capacity.
* **Mitigation**: Set rate limits and configure horizontal pod auto-scaling for worker nodes.
* **Consequences**: Responsive web interfaces with reliable, scalable background processing.
* **Future Revisions**: Migrate to RabbitMQ or Kafka if messaging requirements grow.

---

## ADR-016: Why OpenTelemetry

* **ADR Number**: ADR-016
* **Title**: Selection of OpenTelemetry for Tracing and Observability
* **Status**: Approved
* **Context**: Finding errors in multi-stage agent workflows and hybrid searches is difficult without detailed execution traces.
* **Decision**: Implement OpenTelemetry to capture traces across all services.
* **Alternatives Considered**:
  1. *Custom Logging Middleware*: Rejected because it does not support distributed tracing across separate containers.
  2. *Sentry*: Rejected because it is focus on error collection rather than tracking execution spans.
  3. *Datadog*: Rejected because it is a commercial cloud-based tool, making it unsuitable for offline deployments.
* **Pros**:
  - Open standard supported by major monitoring platforms (Jaeger, Grafana).
  - Captures distributed spans across APIs, databases, and LLM calls.
  - Integrates with Python and React libraries.
* **Cons**:
  - Adds performance overhead for logging and span creation.
* **Trade-offs**: We trade small performance costs for clear execution traces.
* **Risks**: Generating too much trace data can overwhelm storage databases.
* **Mitigation**: Implement trace sampling rules to only save a percentage of successful requests.
* **Consequences**: Clear visibility into agent decisions and database queries.
* **Future Revisions**: None.

---

## ADR-017: Why Prometheus + Grafana

* **ADR Number**: ADR-017
* **Title**: Selection of Prometheus & Grafana for Metrics and Dashboards
* **Status**: Approved
* **Context**: We need to monitor system performance, API error rates, and resource utilization in real-time.
* **Decision**: Deploy Prometheus to collect metrics and Grafana to visualize them.
* **Alternatives Considered**:
  1. *ELK Stack*: Rejected because Elasticsearch is resource-heavy and optimized for text logs rather than metrics.
  2. *Netdata*: Rejected because it lacks historical query tools and customizable alert frameworks.
  3. *CloudWatch*: Rejected because it is tied to AWS and cannot run in air-gapped environments.
* **Pros**:
  - Lightweight metric gathering using pull mechanics.
  - Grafana supports building rich, interactive dashboards.
  - Active community with templates for PostgreSQL, Docker, and Redis.
* **Cons**:
  - Requires configuring exporter agents for each service.
* **Trade-offs**: We add metric collection services to gain unified system monitoring.
* **Risks**: Missing metrics during collector outages.
* **Mitigation**: Configure Prometheus alert rules to warn teams of service outages.
* **Consequences**: Unified dashboards tracking API speeds, database health, and server memory usage.
* **Future Revisions**: None.

---

## ADR-018: Why Docker

* **ADR Number**: ADR-018
* **Title**: Selection of Docker and Docker Compose for Deployment
* **Status**: Approved
* **Context**: The platform consists of multiple databases, queues, and services that must run consistently across local and production setups.
* **Decision**: Standardize packaging using multi-stage Dockerfiles and deploy using Docker Compose.
* **Alternatives Considered**:
  1. *Bare-metal Installation*: Rejected because setting up exact database versions and GPU drivers manually is error-prone.
  2. *Vagrant/VMs*: Rejected due to high memory overhead and slow startup times.
  3. *Kubernetes (Day 1)*: Rejected because managing a full cluster is too complex for initial prototype testing.
* **Pros**:
  - Guarantees identical execution environments across development and production.
  - Simplifies local setup using a single `docker compose up` command.
  - Isolates dependencies, avoiding library version conflicts.
* **Cons**:
  - Containerization adds a layer of abstraction for GPU access (requires NVIDIA Container Toolkit).
* **Trade-offs**: We choose container isolation and configuration simplicity over bare-metal performance.
* **Risks**: Incorrect container volume setups can lead to data loss during updates.
* **Mitigation**: Mount database storage to persistent external directories and automate backups.
* **Consequences**: Standardized image builds and simple local setup steps.
* **Future Revisions**: Create Helm charts for Kubernetes deployments as scale requirements increase.

---

## ADR-019: Why Multi-Brain Architecture

* **ADR Number**: ADR-019
* **Title**: Adopting a Decoupled Multi-Brain Platform Architecture
* **Status**: Approved
* **Context**: A single chat interface can become cluttered with rules for maintenance, compliance, and analysis.
* **Decision**: Build five distinct sub-brains (Knowledge, Maintenance, Compliance, RCA, Lessons Learned) that share data interfaces.
* **Alternatives Considered**:
  1. *Monolithic Assistant*: Rejected because the system prompt becomes too large, leading to hallucinations and poor intent routing.
  2. *Independent Chatbots*: Rejected because they split database storage, preventing brains from sharing knowledge.
  3. *Simple Router with Static Prompts*: Rejected because it does not support specialized data tools for different user roles.
* **Pros**:
  - Specialized agents handle task-specific rules and tools.
  - Smaller system prompts improve response speed and accuracy.
  - Teams can develop and test sub-brains independently.
* **Cons**:
  - Requires maintaining coordinate contracts between sub-brains.
* **Trade-offs**: We choose development modularity and higher response quality over simple monolithic structures.
* **Risks**: Data syncing issues if databases become out of alignment.
* **Mitigation**: Route all data access through shared API schemas and validation logic.
* **Consequences**: Predictable agent behaviors tailored to specific user tasks.
* **Future Revisions**: Add new specialized sub-brains as operational needs expand.

---

## ADR-020: Why PromptOps

* **ADR Number**: ADR-020
* **Title**: Selection of Version-Controlled PromptOps
* **Status**: Approved
* **Context**: Prompts change frequently during optimization; changing them in code files is hard to track and evaluate.
* **Decision**: Decouple prompts from code, storing them in version-controlled configuration files (JSON/YAML) with matching test tests.
* **Alternatives Considered**:
  1. *Hardcoded Prompts*: Rejected because updating prompts requires code releases and is hard to track.
  2. *Database-driven Prompting*: Rejected because it lacks version control history and rollback tools.
  3. *Cloud Prompt Registries*: Rejected because they introduce internet dependencies and external costs.
* **Pros**:
  - Prompts are versioned in git, ensuring clear history and easy rollbacks.
  - Prompt changes can be tested in CI/CD pipelines before deployment.
  - Decouples prompt optimization from backend code changes.
* **Cons**:
  - Requires building configuration loading tools in the backend.
* **Trade-offs**: We invest time building prompt loaders to gain safe, testable prompt deployment.
* **Risks**: Missing configuration variables can cause prompt rendering errors.
* **Mitigation**: Enforce strict schema checks on prompt configuration files during builds.
* **Consequences**: Consistent, version-controlled prompts that can be updated safely.
* **Future Revisions**: None.
