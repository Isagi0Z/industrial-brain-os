# Industrial Brain OS Engineering Bible v1.0
## Software Architecture, Engineering Governance, and AI Platform Standards

---

## 1. Engineering Principles
* **Why**: Establishes a shared baseline of engineering discipline, preventing technical debt from accumulating during high-velocity development cycles.
* **Mandatory Rules**:
  * **Keep it Simple**: Prioritize simple, readable code over clever or hyper-abstracted patterns.
  * **Explicit is Better than Implicit**: Configuration, routing, and data transitions must be explicitly declared.
  * **Fail Fast**: Catch errors at the boundary points (interfaces, inputs) and fail immediately with structured error definitions.
* **Prohibited**:
  * Implementing speculative features not defined in active task schemas.
  * Hiding exceptions behind empty `except:` or `try-catch` blocks.
* **Checklist**:
  - [ ] Code has no dead references or unused variables.
  - [ ] Complexity metrics (cyclomatic complexity) do not exceed 10.

## 2. Clean Architecture Rules
* **Why**: Decouples application logic from databases, UI, and external frameworks, enabling easy maintenance and testability.
* **Mandatory Rules**:
  * Dependency direction must point inwards: Core/Domain ← Application ← Infrastructure/Presentation.
  * Domain layers must not import any modules from Infrastructure (e.g., ORM models, API frameworks).
* **Prohibited**:
  * Importing FastAPI routes or SQLAlchemy session models directly inside the Domain entities.
* **Checklist**:
  - [ ] Core business entities are completely agnostic of database engines or web frameworks.
  - [ ] Data Transfer Objects (DTOs) decouple presentation requests from internal entities.

## 3. SOLID Rules
* **Why**: Minimizes coupling and increases structural robustness to adjustments.
* **Mandatory Rules**:
  * **Single Responsibility**: Each class/module must solve exactly one functional requirement.
  * **Open/Closed**: Code must be open for extension but closed for modification (e.g., using interfaces for storage providers).
  * **Dependency Inversion**: Rely on abstractions (interfaces), never on concrete classes.
* **Prohibited**:
  * Hardcoding API clients or concrete database clients within service layer constructors.
* **Checklist**:
  - [ ] No class handles both database persistence and business calculations.
  - [ ] Subclasses can replace their base classes without breaking execution tests.

## 4. Domain Driven Design (DDD) Rules
* **Why**: Aligns code semantics directly with industrial operations, preventing misalignments between technical logic and business domain models.
* **Mandatory Rules**:
  * Maintain a strict Ubiquitous Language (e.g., use `AssetTag`, `Criticality`, `WorkOrder` matching plant standards).
  * Isolate domain operations inside clear Aggregates, Entities, and Value Objects.
* **Prohibited**:
  * Exposing raw internal entity states for external modification without utilizing domain validation methods.
* **Checklist**:
  - [ ] Entities possess unique identifiers; Value Objects are immutable.
  - [ ] Bounded contexts are separated by strict namespaces.

## 5. Repository Standards
* **Why**: Assures consistency in how files, scripts, and documentation are organized, preventing dependency leaks across submodules.
* **Mandatory Rules**:
  * Commit only clean, linted code.
  * Every repository must possess a clear `README.md` and standard setup instructions.
* **Prohibited**:
  * Committing local files, environment credentials, `.env` configurations, or binary assets.
* **Checklist**:
  - [ ] `.gitignore` is up-to-date and prevents build directory leaks.
  - [ ] Sub-modules or dependencies are version-pinned in configuration descriptors.

## 6. Folder Standards
* **Why**: Establishes predictable paths for navigation across backend, frontend, and AI configurations.
* **Mandatory Rules**:
  * Follow the standard Clean Architecture layout defined in V2: `presentation`, `application`, `domain`, `infrastructure`, `ai`.
* **Prohibited**:
  * Creating generic `utils` or `helpers` folders at the root. Group utility files by domain context.
* **Checklist**:
  - [ ] Folders utilize uniform casing rules (snake_case for Python, kebab-case for directories/frontend).
  - [ ] Test files reside in directories matching their target module structures.

## 7. Naming Conventions
* **Why**: Code readability and self-documentation.
* **Mandatory Rules**:
  * **Python Backend**: Classes use `PascalCase`; functions and variables use `snake_case`; constants use `UPPER_SNAKE_CASE`.
  * **Frontend**: Components use `PascalCase`; source files, styles, and hooks use `kebab-case` or `camelCase`.
* **Prohibited**:
  * Single-character variable naming (e.g., `x`, `y`, `d`) except in simple mathematical iterations.
* **Checklist**:
  - [ ] Boolean variables are prefixed with helper tokens (e.g., `is_active`, `has_criticality`).
  - [ ] Abstract class interfaces are prefixed or suffixed logically (e.g., `AssetRepositoryInterface`).

## 8. Coding Standards
* **Why**: Guarantees code uniformity, simplifies refactoring, and reduces lint error loops.
* **Mandatory Rules**:
  * Enforce strict formatting guidelines: `black` and `ruff` for Python, `prettier` and `eslint` for TypeScript/React.
  * Use explicit type annotations on all function signatures.
* **Prohibited**:
  * Using Python `Any` typing or TypeScript `any` declarations.
* **Checklist**:
  - [ ] Lint check passes locally without suppression overrides.
  - [ ] Functions do not exceed 50 lines of execution logic.

## 9. Documentation Standards
* **Why**: Keeps design intents clear and helps new developers onboard.
* **Mandatory Rules**:
  * Write clear docstrings for all classes, methods, and interface definitions.
  * Document any deviations from standard ontological structures.
* **Prohibited**:
  * Writing redundant docstrings that simply mirror function names (e.g., `def get_user(id): # gets user`).
* **Checklist**:
  - [ ] All public endpoints have matching OpenAPI parameters described in docs.
  - [ ] Architectural shifts are tracked via Architecture Decision Records (ADRs).

## 10. Git Workflow
* **Why**: Keeps code changes safe and ensures clean commit paths.
* **Mandatory Rules**:
  * Follow a trunk-based development strategy with short-lived branch structures.
  * Rebase main branch updates onto local paths regularly to avoid complex merge conflicts.
* **Prohibited**:
  * Committing directly to protected branches (`main`, `master`, `production`).
* **Checklist**:
  - [ ] All feature merges are fast-forwarded or require clean squash-and-merge pipelines.
  - [ ] Branch histories are cleaned of local fixup cycles before submission.

## 11. Branch Strategy
* **Why**: Identifies the purpose of active developments.
* **Mandatory Rules**:
  * Structure branches with descriptive prefixes: `feature/<desc>`, `bugfix/<desc>`, `hotfix/<desc>`, `docs/<desc>`.
* **Prohibited**:
  * Creating generic, undocumented branches (e.g., `test-code`, `updates`, `fix`).
* **Checklist**:
  - [ ] Branch names match the target ticket identifier.
  - [ ] Stale branches are deleted from remote registries after successful merges.

## 12. Commit Convention
* **Why**: Automated changelog generation and clear version history.
* **Mandatory Rules**:
  * Follow Conventional Commits: `<type>(<scope>): <short description>`.
  * Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`.
* **Prohibited**:
  * Generic messages (e.g., `fixes`, `changes`, `work in progress`).
* **Checklist**:
  - [ ] Commits are squashed to present logical units of work.
  - [ ] Breaking changes contain the exact text `BREAKING CHANGE:` in the footers.

## 13. Pull Request Checklist
* **Why**: Eliminates regression errors and ensures peer-reviewed quality checks.
* **Mandatory Rules**:
  * Pull Requests must have at least one senior architect approval.
  * CI pipeline checks (tests, lints, security audits) must pass successfully.
* **Prohibited**:
  * Merging PRs with failing unit tests or unresolved review requests.
* **Checklist**:
  - [ ] The description lists what was changed, testing steps, and relevant issue links.
  - [ ] All code changes are verified through added tests.

## 14. Security Standards
* **Why**: Safeguards intellectual property and protects operational systems.
* **Mandatory Rules**:
  * Run regular dependency security checks (e.g., using `bandit`, `pip-audit`, or `npm audit`).
  * Enforce strict HTTPS/TLS setups and use secure vault structures for credentials.
* **Prohibited**:
  * Storing API tokens, keys, or database passwords in source code.
* **Checklist**:
  - [ ] Environment configurations are read dynamically from env processes.
  - [ ] Input data is validated at the application boundaries to prevent injection attacks.

## 15. RBAC Standards
* **Why**: Implements multi-tenant and secure data isolation, which is critical for industrial security.
* **Mandatory Rules**:
  * Enforce role-based access controls on every API route and query executor.
  * Context queries must filter by user permissions (e.g., bounding vector lookups to allowed workspaces).
* **Prohibited**:
  * Returning raw database entries without evaluating target user scopes first.
* **Checklist**:
  - [ ] User role verification is handled via decoupled security middleware.
  - [ ] Audit logs capture any unauthorized access attempts.

## 16. Logging Standards
* **Why**: Simplifies debugging in distributed production environments.
* **Mandatory Rules**:
  * Format all application logs in structured JSON format.
  * Tag every log message with a unique request/session `Correlation-ID`.
* **Prohibited**:
  * Logging sensitive user details, access tokens, or plain-text passwords.
* **Checklist**:
  - [ ] Log levels (`INFO`, `WARN`, `ERROR`, `DEBUG`) are used appropriately.
  - [ ] Error messages capture the context arguments alongside stack traces.

## 17. Observability Standards
* **Why**: Minimizes system downtime through real-time alerts.
* **Mandatory Rules**:
  * Instrument all databases, services, and AI calls with OpenTelemetry spans.
  * Monitor vector search latencies and LLM token usage.
* **Prohibited**:
  * Running black-box reasoning agents without active tracing configurations.
* **Checklist**:
  - [ ] Trace IDs are passed across all service calls and backend processes.
  - [ ] Dashboards display metric updates for latency percentiles and error rates.

## 18. Knowledge Graph Standards
* **Why**: Ensures structural reliability when navigating complex relationships.
* **Mandatory Rules**:
  * Node types, properties, and relation edges must match the ontology.
  * Node creation pipelines must verify and merge duplicate records.
* **Prohibited**:
  * Creating ad-hoc relationships or attributes not defined in the system ontology.
* **Checklist**:
  - [ ] Transactions maintain graph consistency.
  - [ ] Graph schemas are defined and validated by active rules.

## 19. Ontology Standards
* **Why**: Prevents semantic conflicts across different systems.
* **Mandatory Rules**:
  * Store all ontology schemas in version-controlled configuration files.
  * Changes to the ontology must be verified by the knowledge engineering team.
* **Prohibited**:
  * Modifying schemas on production graphs without running validation checks.
* **Checklist**:
  - [ ] Ontology structures inherit from standard templates.
  - [ ] Modifications are validated through schema compatibility tests.

## 20. GraphRAG Standards
* **Why**: Combines vector indexing with relational mapping for contextually accurate generation.
* **Mandatory Rules**:
  * Ensure retrieved graphs are filtered by active metadata constraints.
  * Format graph relations in structured formats (e.g., Markdown tables or lists) before sending them to the LLM.
* **Prohibited**:
  * Sending large, unfiltered subgraphs directly into the LLM context window.
* **Checklist**:
  - [ ] Retrieval pipelines search both vector and graph databases.
  - [ ] Token budgets are monitored during the hybrid context assembly stage.

## 21. AI Agent Standards
* **Why**: Ensures reliable agent execution and prevents infinite loops.
* **Mandatory Rules**:
  * Define all agent workflows using explicit states (e.g., using LangGraph).
  * Configure maximum step limits for all loop executions.
* **Prohibited**:
  * Allowing agents to run indefinitely without boundary checks.
* **Checklist**:
  - [ ] Agents log their execution steps.
  - [ ] Fallback methods are defined for failed tool executions.

## 22. Prompt Engineering Standards
* **Why**: Minimizes generation variance and ensures predictable LLM outputs.
* **Mandatory Rules**:
  * Version-control prompts alongside application code.
  * Define explicit output format requirements (e.g., JSON schemas or Markdown templates) in system prompts.
* **Prohibited**:
  * Hardcoding prompt templates directly inside application files.
* **Checklist**:
  - [ ] System instructions are separated from dynamic user inputs.
  - [ ] Prompt templates are verified using evaluation datasets.

## 23. LLM Interaction Rules
* **Why**: Keeps costs manageable and ensures system stability.
* **Mandatory Rules**:
  * Implement retry policies with exponential backoff for all LLM calls.
  * Define max-token constraints for every request.
* **Prohibited**:
  * Calling raw APIs directly without timeout configurations.
* **Checklist**:
  - [ ] Fallback models are configured for API outages.
  - [ ] Token usage metrics are logged per request.

## 24. Context Building Standards
* **Why**: Prevents retrieval pollution and keeps context relevant.
* **Mandatory Rules**:
  * Deduplicate and rank chunks before building the final prompt.
  * Format source materials using markdown schemas.
* **Prohibited**:
  * Appending raw search results without validation checks.
* **Checklist**:
  - [ ] Chunks are ordered by relevance score.
  - [ ] Unused details are stripped to optimize token usage.

## 25. Evaluation Standards
* **Why**: Ensures output quality and catches hallucinations.
* **Mandatory Rules**:
  * Run automated evaluation cycles (e.g., checking faithfulness and relevance) on all release candidates.
  * Use gold standard datasets for quality benchmarking.
* **Prohibited**:
  * Deploying prompt or model changes without verifying baseline metrics.
* **Checklist**:
  - [ ] Test outputs are verified against reference responses.
  - [ ] Evaluation metrics are logged for tracking.

## 26. Testing Standards
* **Why**: Prevents regression errors and keeps the codebase stable.
* **Mandatory Rules**:
  * Maintain at least 80% test coverage across backend modules.
  * Separate tests into unit, integration, and end-to-end suites.
* **Prohibited**:
  * Disabling or skipping tests in main branch builds without fix tasks.
* **Checklist**:
  - [ ] Tests run successfully in local and CI environments.
  - [ ] Mock external API dependencies during unit test runs.

## 27. Performance Standards
* **Why**: Guarantees fast response times for users.
* **Mandatory Rules**:
  * Cache frequent queries using fast, local storage.
  * Optimize database queries to keep execution times under 100ms.
* **Prohibited**:
  * Running unindexed search operations on large database tables.
* **Checklist**:
  - [ ] Performance metrics are monitored during testing cycles.
  - [ ] Heavy analytical jobs run in background processes.

## 28. Scalability Standards
* **Why**: Prepares the platform for high volumes of data and users.
* **Mandatory Rules**:
  * Design all services to be stateless to support horizontal scaling.
  * Use message queues to balance traffic spikes.
* **Prohibited**:
  * Storing session states in local memory.
* **Checklist**:
  - [ ] Services scale horizontally behind load balancers.
  - [ ] Database configurations support replica configurations.

## 29. Error Handling Standards
* **Why**: Provides clear error insights and prevents data leaks.
* **Mandatory Rules**:
  * Use structured error responses at all API interfaces.
  * Catch and log exceptions before returning generic error messages to users.
* **Prohibited**:
  * Returning raw database logs or detailed stack traces in client API responses.
* **Checklist**:
  - [ ] All custom exceptions are categorized.
  - [ ] Boundary endpoints validate payload structures before processing.

## 30. Deployment Standards
* **Why**: Ensures reliable releases across different environments.
* **Mandatory Rules**:
  * Automate deployments using Infrastructure as Code (IaC).
  * Use identical configuration templates for staging and production.
* **Prohibited**:
  * Modifying production server settings manually.
* **Checklist**:
  - [ ] Rollback steps are defined for all deployments.
  - [ ] Service configurations are validated before release.

## 31. Docker Standards
* **Why**: Simplifies local setup and ensures consistent environments.
* **Mandatory Rules**:
  * Build multi-stage, minimal Docker images to keep sizes small.
  * Avoid running containers as the root user.
* **Prohibited**:
  * Committing local files or environment secrets into Docker images.
* **Checklist**:
  - [ ] Image builds are scanned for security vulnerabilities.
  - [ ] Port configurations and storage paths are documented.

## 32. CI/CD Standards
* **Why**: Automates delivery pipelines and ensures quality gates are met.
* **Mandatory Rules**:
  * Configure pipelines to run tests and lints on every push.
  * Store build artifacts securely.
* **Prohibited**:
  * Merging code changes when the CI/CD build fails.
* **Checklist**:
  - [ ] Deployment pipelines run automated test suites.
  - [ ] Build statuses are tracked in team channels.

## 33. API Design Standards
* **Why**: Ensures consistent and predictable integrations.
* **Mandatory Rules**:
  * Follow RESTful API guidelines and include version tags.
  * Define explicit data validation schemas for all inputs.
* **Prohibited**:
  * Changing API schemas without updating version endpoints.
* **Checklist**:
  - [ ] Route structures follow resource patterns.
  - [ ] Interactive APIs include documentation links.

## 34. Database Standards
* **Why**: Keeps operational data organized and fast to access.
* **Mandatory Rules**:
  * Manage all schema updates using migration tools (e.g., Alembic).
  * Define explicit indexes for columns used in filters.
* **Prohibited**:
  * Running schema changes directly on production databases without migrations.
* **Checklist**:
  - [ ] Table relationships are mapped with keys.
  - [ ] Query plans are verified during performance checks.

## 35. Vector Database Standards
* **Why**: Ensures fast similarity search operations.
* **Mandatory Rules**:
  * Match vector configurations with the embedding model dimension size.
  * Apply payload indexing to fields used in metadata filters.
* **Prohibited**:
  * Performing unindexed searches on large vector collections.
  - [ ] Index parameters match expected memory limits.
  - [ ] Validation tests verify search precision.

## 36. Graph Database Standards
* **Why**: Keeps relationships organized and easy to query.
* **Mandatory Rules**:
  * Define indexes on node properties used in start points.
  * Implement constraints to prevent duplicate entries.
* **Prohibited**:
  * Running unconstrained queries that scan the entire graph.
* **Checklist**:
  - [ ] Relationship maps align with the ontology.
  - [ ] Graph performance is monitored for query hotspots.

## 37. Frontend Standards
* **Why**: Ensures a consistent user experience and easy maintenance.
* **Mandatory Rules**:
  * Organize code using component patterns.
  * Use typescript types for all state definitions.
* **Prohibited**:
  * Mixing business logic directly inside component layout blocks.
* **Checklist**:
  - [ ] Build steps complete without errors.
  - [ ] Global states are managed through hooks.

## 38. UI/UX Standards
* **Why**: Provides a premium and responsive design for operators.
* **Mandatory Rules**:
  * Implement responsive design configurations.
  * Use consistent colors, spacing, and layouts.
* **Prohibited**:
  * Using non-standard components that break layout grids.
* **Checklist**:
  - [ ] Layout transitions are smooth.
  - [ ] Design patterns match style guides.

## 39. Accessibility Standards
* **Why**: Ensures usability for all plant operators.
* **Mandatory Rules**:
  * Comply with WCAG 2.1 AA guidelines.
  * Use semantic tag labels and verify contrast ratios.
* **Prohibited**:
  * Relying only on color indicators to show critical states.
  - [ ] Interfaces support keyboard navigation.
  - [ ] Screen readers parse application views.

## 40. Project Quality Gates
* **Why**: Enforces overall platform readiness.
* **Mandatory Rules**:
  * Code modifications must pass quality standards before deployment.
  * Run security audits on all third-party libraries.
* **Prohibited**:
  * Deploying releases with high-severity vulnerabilities.
* **Checklist**:
  - [ ] Static analysis tools show zero high-priority issues.
  - [ ] Documentation updates are completed before the release.
