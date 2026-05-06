# AI工作流编排系统 — 任务分解

> 关联规范文档: [flow-1.md](flow-1.md) | [research-report.md](research-report.md)

---

## 依赖关系图

```
Phase 1: MVP
════════════════════════════════════════════════════════════════════

  #8 [done] 项目脚手架
    ├─→ #13 [done] 核心抽象 (BaseNode, NodeRegistry)
    ├─→ #10 [done] 数据库Schema
    ├─→ #30 [done] 模型路由
    ├─→ #32 [done] Docker 沙箱
    └─→ #20 [done] 认证系统

  #13 ──→ #9  [done] Variable Pool
  #13 ──→ #11 [done] DSL 解析器

  #9 + #11 + #13 ──→ #12 [done] 执行引擎 ← 核心里程碑

  #13 ──→ #14 [done] 控制流节点 (7个)
  #13 + #9 + #30 ──→ #15 [done] AI核心节点 (6个)
  #13 + #9 + #32 ──→ #17 [done] 数据/集成节点 (8个)
  #8 + #10 ──→ #33 [done] RAG 管道

  #10 + #12 + #14 + #15 + #17 ──→ #19 [done] REST API 层
  #12 + #19 ──→ #16 [done] SSE/WebSocket
  #19 ──→ #18 [in_progress] 前端画布

Phase 2: 增强
════════════════════════════════════════════════════════════════════

  #8 + #13 ──→ #21 [done] Skills SDK
  #13 + #19 ──→ #22 [done] 插件系统
  #10 + #19 ──→ #23 [done] 版本管理
  #12 + #13 ──→ #24 [done] 错误处理/熔断器
  #12 + #19 ──→ #25 [done] 监控告警

Phase 3: 企业级
════════════════════════════════════════════════════════════════════

  #20 + #19 + #10 ──→ #26 [done] RBAC 权限
  #17 + #20 ──→ #29 [done] 安全加固
  #19 + #16 ──→ #27 [in_progress] K8s 部署
  #12..19 ──→ #28 [in_progress] 测试套件

Phase 4: 生态
════════════════════════════════════════════════════════════════════

  #19 + #21 + #22 ──→ #31 [in_progress] 文档
  #22 + #21 + #18 ──→ #34 [done] 节点市场
```

---

## 任务清单

---

### #8 [done] 项目脚手架与开发环境搭建

**Phase:** 1 · **Status:** done · **Estimate:** 1-2 weeks

**Dependencies:**
- blockedBy: (none)
- blocks: #9, #10, #11, #12, #13, #14, #15, #17, #20, #21, #30, #32, #33

**Spec Reference:** docs/flow-1.md — Section 1.4 (技术选型), Section 10.1 (Docker Compose), Section 10.3 (CI/CD)

**Active Form:** Setting up project scaffolding and development environment

**Description:**
Initialize the Python project structure with FastAPI, configure Docker Compose for local development, set up linting (ruff, mypy), testing (pytest), and CI pipeline skeleton.

**Checklist:**
- [x] Create project directory structure (`api/`, `engine/`, `nodes/`, `models/`, `services/`, `skills_sdk/`, `frontend/`)
- [x] Set up `pyproject.toml` with all dependencies (fastapi, pydantic, sqlalchemy, celery, redis, httpx, jinja2, structlog)
- [x] Configure Docker Compose with PostgreSQL 15, Redis 7, MinIO services
- [x] Set up ruff for linting (rules: E, F, I, N, W, UP, B, SIM)
- [x] Set up mypy for type checking (strict mode)
- [x] Set up pytest with pytest-asyncio, pytest-cov, pytest-xdist
- [x] Create configuration management via pydantic-settings (`config.py` for dev/staging/prod)
- [x] Set up structlog for structured logging with execution_id correlation
- [x] Create GitHub Actions CI workflow (`.github/workflows/ci.yaml`: lint, typecheck, test, build-docker)
- [x] Create `Dockerfile` with multi-stage build (builder + runtime)
- [x] Create `Makefile` with common commands (lint, test, dev, build, migrate)
- [ ] Verify all services start via `docker compose up`

---

### #10 [done] 数据库Schema设计与迁移

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8
- blocks: #12, #19, #20, #23, #26, #33

**Spec Reference:** docs/flow-1.md — Section 6.2 (数据模型), Section 9 (数据模型定义), Section 12.3 (查询优化)

**Active Form:** Designing and implementing database schema and migrations

**Description:**
Implement all PostgreSQL tables: workflows, workflow_versions, workflow_executions, node_executions, node_definitions, plugins, skill_registry, workflow_checkpoints, workflow_version_diffs, users, workspaces. Set up Alembic for migrations.

**Checklist:**
- [x] Create SQLAlchemy `Base` and engine configuration with connection pooling
- [x] Implement `User` model (id, email, password_hash, name, role, created_at, updated_at)
- [x] Implement `Workspace` model (id, name, owner_id, plan, created_at)
- [x] Implement `Workflow` model (id, name, description, workspace_id, current_version_id, status, tags, created_by, deleted_at)
- [x] Implement `WorkflowVersion` model (id, workflow_id, version, status, dsl_definition JSONB, dsl_hash, changelog, environment, published_at, created_by)
- [x] Implement `WorkflowExecution` model (id, workflow_version_id, workflow_id, status, trigger_type, inputs/outputs JSONB, node_executions JSONB, error_message, total_tokens, started_at, completed_at, duration_ms)
- [x] Implement `NodeExecution` model (id, execution_id, node_id, node_type, status, inputs/outputs JSONB, error_message, retry_count, duration_ms, token_count, model_name, prompt_text, response_text)
- [x] Implement `NodeDefinition` model (id, node_type, display_name, category, is_builtin, plugin_id, input_schema/output_schema/config_schema JSONB, version)
- [x] Implement `Plugin` model (id, name, version, node_type, entry_point, runtime, dependencies JSONB, config JSONB, status)
- [x] Implement `SkillRegistry` model (id, name, version, display_name, category, manifest_path, input_schema/output_schema JSONB, status)
- [x] Implement `WorkflowCheckpoint` model (id, execution_id, sequence_number, graph_state JSONB, variable_pool_snapshot JSONB)
- [x] Implement `WorkflowVersionDiff` model (id, from_version_id, to_version_id, diff_type, diff_detail JSONB)
- [x] Implement `AuditLog` model (id, user_id, workspace_id, action, resource_type, resource_id, details JSONB, ip_address, created_at)
- [ ] Create Alembic initial migration with all tables
- [x] Create optimized indexes per Section 12.3
- [ ] Implement table partitioning for `workflow_executions` (monthly RANGE)
- [ ] Create seed data migration for 15 built-in node types
- [ ] Write model relationship tests (FK constraints, cascading deletes)

---

### #13 [done] 核心抽象实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8
- blocks: #9, #11, #12, #14, #15, #17, #21, #22, #24

**Spec Reference:** docs/flow-1.md — Section 3.2 (节点注册机制, 完整代码列表)

**Active Form:** Implementing core abstractions (BaseNode, NodeConfig, NodeRegistry)

**Description:**
Implement the foundational node system: BaseNode abstract class, NodeConfig/NodeResult Pydantic models, NodeRegistry singleton with full CRUD, and the @register_node decorator.

**Checklist:**
- [x] Implement `NodeCategory` enum (CONTROL, AI, DATA, INTEGRATION)
- [x] Implement `NodeStatus` enum (PENDING, QUEUED, RUNNING, SUCCEEDED, FAILED, SKIPPED, TIMEOUT)
- [x] Implement `VariableDef` model (name, type, required, default, description)
- [x] Implement `NodeConfig` model (node_type, display_name, description, icon, category, inputs, outputs, config_schema, version, author, tags)
- [x] Implement `NodeResult` model (status, outputs, error, duration_ms, token_count, metadata)
- [x] Implement `BaseNode` abstract class with `execute()`, `pre_execute()`, `post_execute()`, `validate_inputs()`, `supported_retry_exceptions`
- [x] Implement `NodeRegistry` singleton (`_registry`, `register()`, `unregister()`, `create_node()`, `list_nodes()`, `get_node_config()`)
- [x] Implement `@register_node` decorator with all metadata parameters
- [x] Implement `ExecutionContext` model (execution_id, workflow_version_id, trace_enabled, metadata)
- [x] Write comprehensive unit tests: registry operations, duplicate registration, unknown type error, decorator config extraction

---

### #30 [done] 模型路由实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8
- blocks: #15

**Spec Reference:** docs/flow-1.md — Section 1.1 (模型路由层), Section 3.2 (LLMNode), Section 8.6 (模型管理API)

**Active Form:** Implementing model router with provider adapters

**Description:**
Build the unified Model Router that abstracts LLM provider differences. Implement provider adapters for OpenAI, Anthropic, and local models, with credential management, fallback routing, and usage tracking.

**Checklist:**
- [x] Implement `ModelRouter` class with unified `call_llm(model, messages, **params)` async interface
- [x] Implement `OpenAIProvider` adapter (GPT-4o, GPT-4.1, O3, O4 — chat completions + streaming)
- [x] Implement `AnthropicProvider` adapter (Claude Opus 4, Sonnet 4, Haiku 4 — messages API + streaming)
- [ ] Implement `LocalProvider` adapter (vLLM/Ollama OpenAI-compatible endpoints)
- [x] Implement `ModelConfig` registry (model_name, provider, capabilities, pricing_per_1k_tokens, context_window, supports_vision, supports_streaming)
- [x] Implement fallback chain logic (primary → fallback_model on connection error / timeout / rate limit)
- [ ] Implement model-level circuit breaker integration (via CircuitBreaker from #24)
- [x] Implement token usage tracking (input_tokens, output_tokens per call, aggregated to execution)
- [ ] Implement model credential encryption (`ModelCredential` model, KMS/Vault integration)
- [x] Implement streaming iterator wrapper (unified SSE chunk interface across providers)
- [ ] Write adapter unit tests with mocked HTTP responses for each provider

---

### #32 [done] Docker代码沙箱实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8
- blocks: #17

**Spec Reference:** docs/flow-1.md — Section 5.1 (Layer 5: 代码执行安全), Section 3.1 (Code节点), Section 3.3 (沙箱配置)

**Active Form:** Implementing Docker-based code execution sandbox

**Description:**
Build secure Docker-based execution sandbox for Code nodes and Skill execution. Container lifecycle, resource limits, network policies, seccomp profiles, and output capture.

**Checklist:**
- [x] Implement `DockerSandbox` class with async context manager interface
- [x] Implement container lifecycle: `create_container(image, command)`, `start()`, `wait(timeout)`, `cleanup()`
- [x] Implement resource limits per execution (memory_limit, cpu_limit, disk_quota) via Docker API
- [x] Implement network policies: `none` (no network), `restricted` (domain whitelist via iptables), `full`
- [ ] Implement seccomp profile generation (system call whitelist per runtime)
- [ ] Implement input injection (write stdin, mount input files read-only)
- [x] Implement output capture (read stdout/stderr streams, enforce output size limit)
- [ ] Implement dependency caching layer (pre-built base images, pip cache volumes, layer reuse)
- [x] Implement timeout enforcement (Docker `stop` + `kill` after grace period)
- [x] Support Python 3.11+ runtime (base image: `python:3.11-slim`)
- [x] Support Node.js 20+ runtime (base image: `node:20-slim`)
- [x] Implement `SandboxResult` model (stdout, stderr, exit_code, duration_ms, memory_used_mb)
- [ ] Write sandbox escape prevention tests (network breakout attempt, filesystem escape, resource exhaustion)

---

### #9 [done] Variable Pool实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8, #13
- blocks: #12, #15, #17

**Spec Reference:** docs/flow-1.md — Section 2.2 (VariablePool), Section 3.1 (数据流转模型), research-report.md — Section 3.1

**Active Form:** Implementing Variable Pool with template resolution

**Description:**
Build the VariablePool runtime memory space enabling publish-subscribe data flow between nodes. Namespaced get/set, Jinja2 template resolution, system variable injection, type-safe access, and snapshot/merge.

**Checklist:**
- [x] Implement `VariablePool` class with thread-safe internal `_data: dict`
- [x] Implement namespaced `get(path)` — supports dot notation: `node_llm.output.text`, `node_start.output.variables.query`
- [x] Implement namespaced `set(path, value)` — auto-creates intermediate namespaces
- [x] Implement system variable injection on pool creation: `sys.execution_id`, `sys.workflow_id`, `sys.workflow_version`, `sys.user_id`, `sys.timestamp`, `sys.environment`, `sys.trigger`, `sys.conversation_id`
- [x] Implement `resolve_template(template_string, context)` — Jinja2 rendering with VariablePool as variable source, supports `{{node_id.output.field}}`, nested access `{{node_id.output.items[0].name}}`, filters `{{value | default('N/A')}}`
- [ ] Implement type-safe `set_typed(path, value, expected_type)` with Pydantic validation
- [x] Implement `snapshot()` — returns deep copy of entire pool state for checkpointing
- [x] Implement `restore(snapshot)` — replaces pool state from snapshot
- [x] Implement `merge(other_pool, strategy)` — merges another pool's data (strategies: `first_wins`, `last_wins`, `merge_lists`)
- [x] Implement `get_namespace(prefix)` — returns all keys under a namespace
- [x] Implement `delete_namespace(prefix)` — cleanup after node execution
- [x] Write unit tests: set/get basic types, nested access, template resolution with Jinja2 syntax, type safety violations, snapshot/restore roundtrip, merge strategies

---

### #11 [done] DSL解析器与图验证器实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8, #13
- blocks: #12

**Spec Reference:** docs/flow-1.md — Section 2.1 (Workflow DSL JSON), Section 2.2 (GraphParser), Section 2.3 (阶段一), Section 3.4 (DSL编译与优化)

**Active Form:** Implementing DSL parser and graph validator

**Description:**
Build GraphParser that converts Workflow DSL JSON into executable DAG structures. JSON Schema validation, adjacency list construction, cycle detection, variable reference validation, type compatibility, and dead code elimination.

**Checklist:**
- [x] Implement `GraphParser` class with `parse(dsl_json) → ExecutionGraph` method
- [ ] Implement JSON Schema validation for Workflow DSL (create `workflow-schema.json` with all constraints)
- [x] Implement Phase 1 — Lexical/Syntax: node ID uniqueness, edge source/target existence, required nodes (Start + End)
- [x] Implement Phase 2 — Semantic: variable reference resolution (validate all `{{...}}` references), type compatibility (upstream output type matches downstream input type), condition expression syntax
- [x] Implement Phase 3 — Optimization: dead code elimination (BFS from Start, mark unreachable nodes), constant folding, parallel branch detection
- [x] Implement adjacency list construction from edges array
- [x] Implement cycle detection using DFS with recursion stack (whitelist Loop node back-edges)
- [x] Implement `ExecutionGraph` model (adjacency list, topo-sorted order, node_configs, parallel_groups, metadata)
- [x] Implement `GraphValidationError` with field-level error reporting (node_id, field, reason)
- [x] Write tests: valid DSLs (linear, parallel, conditional), invalid DSLs (missing Start, cycle, undefined variable ref, type mismatch, unreachable node)

---

### #12 [done] 工作流执行引擎实现

**Phase:** 1 · **Status:** done · **核心里程碑**

**Dependencies:**
- blockedBy: #8, #9, #11, #13
- blocks: #16, #19, #24, #25, #28

**Spec Reference:** docs/flow-1.md — Section 2.2-2.5 (完整执行引擎规范)

**Active Form:** Implementing workflow execution engine (ExecutionScheduler)

**Description:**
Build the core execution engine: topological scheduling, node execution loop, dependency resolution, parallel branches, condition handling, checkpoint management, and event emission.

**Checklist:**
- [x] Implement `ExecutionScheduler` class with `schedule(graph, variable_pool) → ExecutionResult`
- [x] Implement Kahn's algorithm for topological sort and ready queue initialization
- [x] Implement main execution loop: dequeue ready nodes → resolve inputs from VariablePool → execute node → write outputs → check successors → enqueue ready successors
- [x] Implement `DependencyResolver`: check all predecessors of a node are in SUCCEEDED/SKIPPED state before enqueueing
- [x] Implement `ParallelExecutor`: identify parallel groups, submit to `asyncio.gather`, wait for barrier
- [x] Implement parallel error strategies: `fail_fast` (cancel all on first error), `continue_on_error` (record error, continue others), `aggregate` (collect all errors, report at end)
- [x] Implement condition branch handling: evaluate If/Else expression, activate matching branch (status=RUNNING), deactivate non-matching (status=SKIPPED)
- [ ] Implement Loop node handling: track iteration count, evaluate break_condition, inject loop_variable
- [x] Implement `CheckpointManager`: `save_checkpoint(graph_state, variable_pool_snapshot)`, `restore_checkpoint(checkpoint_id)`, `cleanup_old_checkpoints(max_age)`
- [x] Implement `EventEmitter`: `emit(event_type, data)`, subscribe/unsubscribe pattern for SSE/WebSocket
- [x] Implement global workflow timeout (configurable, default 1800s) and per-node timeout
- [x] Implement `ExecutionResult` model (status, outputs, node_results, total_duration_ms, total_tokens, total_api_calls, error_summary)
- [ ] Write tests: linear 3-node workflow, parallel 3-branch workflow, conditional branch (both paths), loop workflow (for + while), checkpoint save/restore, timeout handling

---

### #14 [done] 控制流节点实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #13
- blocks: #19, #28

**Spec Reference:** docs/flow-1.md — Section 3.1 (第一层节点), Section 3.2 (register_node示例), Section 2.4 (分支处理策略)

**Active Form:** Implementing control flow nodes

**Description:**
Implement 7 control flow node types: Start, End, Condition, Loop, Parallel, VariableAssigner, VariableAggregator. Each extends BaseNode with @register_node decorator and complete config schemas.

**Checklist:**
- [x] Implement `StartNode`: inject user-provided inputs into VariablePool under `node_start.output.variables.*`, validate required inputs
- [x] Implement `EndNode`: collect final outputs from specified upstream nodes, compile into structured result
- [x] Implement `ConditionNode`: evaluate conditions sequentially (first-match-wins), support operators (==, !=, >, <, >=, <=, in, not_in, contains, not_contains, and, or, not, exists, is_empty), default_target fallback
- [x] Implement `LoopNode`: for mode (iterate over list), while mode (evaluate condition each iteration), break_condition, max_iterations safety limit, loop_variable tracking
- [x] Implement `ParallelNode`: identify branches from outgoing edges, submit each branch as independent sub-scheduler, barrier wait, configurable error strategy
- [x] Implement `VariableAssignerNode`: assign values/expressions to variable pool, support literal values, template expressions, upstream references
- [x] Implement `VariableAggregatorNode`: merge multiple branch outputs, strategies (first_non_null, merge_objects, concat_arrays, pick_by_priority)
- [ ] Write unit test per node type including edge cases (empty inputs, missing condition match, max_iterations exceeded, parallel branch failure)

---

### #15 [done] AI核心节点实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #13, #9, #30
- blocks: #19, #28

**Spec Reference:** docs/flow-1.md — Section 3.1 (第二层节点), Section 3.2 (LLMNode完整代码), research-report.md — Section 九

**Active Form:** Implementing AI core nodes

**Description:**
Implement 6 AI core node types: LLM, KnowledgeRetrieval, QuestionClassifier, ParameterExtractor, Agent, MultiAgent. Model routing, prompt templating, structured output, RAG pipeline, and Agent loops.

**Checklist:**
- [x] Implement `LLMNode`: resolve prompt_template via VariablePool, call ModelRouter, handle streaming, handle structured output (JSON Schema → Pydantic), fallback model, retry config, token tracking
- [x] Implement `KnowledgeRetrievalNode`: connect to RAG pipeline (#33), vector/hybrid/fulltext retrieval strategies, top_k, score_threshold filtering, rerank support
- [x] Implement `QuestionClassifierNode`: LLM-based intent classification with predefined classes (name, description, examples), match confidence threshold, target_node routing
- [x] Implement `ParameterExtractorNode`: extract structured parameters from unstructured text, Pydantic model generation from config, LLM prompt with few-shot examples
- [x] Implement `AgentNode`: ReAct/Function Calling loop, tool registry (list available tools, call tool, parse result), max_iterations guard, conversation memory (short-term context window), final answer synthesis
- [x] Implement `MultiAgentNode`: Master-SubAgent coordination, 4 modes (sequential pipeline, broadcast, debate, hierarchy), shared long-term memory via vector store, task decomposition prompt, result aggregation
- [ ] Write integration tests with mocked LLM responses for each node type

---

### #17 [done] 数据处理与集成节点实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #13, #9, #32
- blocks: #19, #28, #29

**Spec Reference:** docs/flow-1.md — Section 3.1 (第三层节点), Section 3.3 (插件系统设计)

**Active Form:** Implementing data processing and integration nodes

**Description:**
Implement 8 data/integration node types: Code, HTTPRequest, Template, DataTransform, DocumentParser, Webhook, MCPTool, Wait.

**Checklist:**
- [x] Implement `CodeNode`: submit to DockerSandbox, inject VariablePool inputs as environment/args, capture stdout/stderr, parse output, enforce timeout
- [x] Implement `HTTPRequestNode`: Jinja2 body template rendering, configurable method/URL/headers, TLS verification, timeout, retry with backoff, response parsing (JSON/XML/text)
- [x] Implement `TemplateNode`: Jinja2 rendering with full VariablePool access, output format options (plain text, markdown, HTML, JSON), template from string or file reference
- [x] Implement `DataTransformNode`: JSON ↔ XML ↔ CSV conversion, jq-style field mapping rules, input/output schema validation
- [x] Implement `DocumentParserNode`: PDF (pypdf2), DOCX (python-docx), XLSX (openpyxl), TXT/Markdown, text extraction, metadata extraction
- [x] Implement `WebhookNode`: webhook URL registration, HMAC-SHA256 signature verification, event-based trigger, retry on delivery failure
- [x] Implement `MCPToolNode`: MCP client (STDIO/SSE transport), tool discovery via `list_tools`, parameter mapping from VariablePool, result parsing
- [x] Implement `WaitNode`: fixed duration (sleep), dynamic wait (poll `until_condition` expression), max_wait timeout
- [ ] Write unit tests with mocked external dependencies for each node type

---

### #33 [done] RAG管道实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #8, #10
- blocks: (none - consumed by #15 KnowledgeRetrievalNode)

**Spec Reference:** docs/flow-1.md — Section 3.1 (KnowledgeRetrieval节点), research-report.md — Section 1.2

**Active Form:** Implementing RAG pipeline for Knowledge Retrieval

**Description:**
Implement end-to-end RAG pipeline: vector search (Milvus/PGVector), hybrid search, result reranking, document chunking, and embedding generation.

**Checklist:**
- [x] Implement `VectorStore` abstraction with pluggable backends
- [x] Implement `MilvusBackend`: collection management, IVF_FLAT/HNSW index, metadata filtering, batch insert
- [x] Implement `PGVectorBackend`: pgvector extension, cosine/L2 distance, lightweight alternative
- [x] Implement `EmbeddingService`: OpenAI text-embedding-3, Cohere embed, local sentence-transformers
- [x] Implement document chunking strategies: `FixedSizeChunker` (by token count), `SemanticChunker` (by sentence + overlap), `RecursiveChunker` (by section hierarchy)
- [x] Implement `HybridSearcher`: combine vector similarity + BM25 keyword scores (weighted sum)
- [x] Implement `Reranker`: cross-encoder model (Cohere Rerank / BGE-Reranker) for result refinement
- [x] Implement `KnowledgeBaseManager`: create/delete collection, upload documents, query, delete documents
- [x] Write integration tests with embedded Milvus and PGVector

---

### #19 [done] REST API层实现

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #12, #14, #15, #17, #10
- blocks: #16, #18, #22, #23, #25, #26, #27, #28, #31

**Spec Reference:** docs/flow-1.md — Section 8 (完整API接口规范)

**Active Form:** Implementing REST API layer with FastAPI

**Description:**
Implement complete REST API: FastAPI app with middleware stack, unified response/error format, pagination, all endpoint groups, OpenAPI docs.

**Checklist:**
- [x] Set up FastAPI application with lifespan events (startup DB connect, shutdown cleanup)
- [x] Implement middleware stack: RequestID, Logging (structlog), ErrorHandling, CORS, RateLimiting
- [x] Implement unified response helper: `success_response(data)`, `error_response(code, message, errors)`
- [x] Implement pagination helper: `paginate(query, page, page_size) → {items, pagination}`
- [x] Implement Workflow Management endpoints: POST/GET/PUT/DELETE `/workflows`, POST publish/rollback/promote/clone, GET versions/diff
- [x] Implement Workflow Execution endpoints: POST `/run`, `/run-async`, `/run-stream`, GET executions/status/trace/checkpoints, POST cancel/retry
- [x] Implement Node Management endpoints: GET `/nodes`, `/nodes/categories`, `/nodes/{type}`, POST/DELETE `/nodes/plugins`
- [x] Implement Model Management endpoints: GET `/models`, POST `/models`, PUT/DELETE credentials
- [x] Implement Skill Integration endpoints: GET `/skills`, POST `/skills/reload`, GET `/{name}`, POST `/test`, `/validate`, `/package`, `/install`
- [x] Implement Authentication endpoints: POST `/auth/login`, `/auth/refresh`, `/auth/api-keys`
- [x] Implement request/response model validation with Pydantic v2 for all endpoints
- [x] Auto-generate OpenAPI 3.1 documentation with full examples
- [x] Write API integration tests for all endpoint groups

---

### #16 [done] SSE流式与WebSocket实时通信

**Phase:** 1 · **Status:** done

**Dependencies:**
- blockedBy: #12, #19
- blocks: #18, #27

**Spec Reference:** docs/flow-1.md — Section 8.4 (SSE), Section 8.8 (WebSocket), research-report.md — Section 6.2

**Active Form:** Implementing SSE streaming and WebSocket real-time communication

**Description:**
SSE for streaming workflow execution, WebSocket for bidirectional real-time communication. All event types per spec.

**Checklist:**
- [x] Implement SSE endpoint `POST /workflows/{id}/run-stream` with proper headers (`Content-Type: text/event-stream`, `Cache-Control: no-cache`)
- [x] Implement all SSE event types: `workflow_started`, `node_started`, `node_streaming` (LLM text chunks), `node_completed`, `node_skipped`, `workflow_completed`, `ping`, `error`
- [x] Implement LLM streaming: relay provider SSE chunks as `text_chunk` events with incremental token_count
- [x] Implement WebSocket endpoint `ws://host/ws/workflows/{id}/executions/{exec_id}`
- [x] Implement WebSocket message protocol: client→server (`subscribe`, `cancel`), server→client (same events as SSE + `pong`)
- [x] Implement connection manager: track active connections per user, heartbeat (30s ping), auto-reconnect guidance, max connections limit
- [x] Implement EventEmitter pub/sub: decouple execution engine from transport, support multiple subscribers per execution
- [x] Write integration tests: SSE event ordering, WebSocket subscribe/cancel flow, reconnection handling

---

### #18 [in_progress] 前端工作流画布

**Phase:** 1 · **Status:** in_progress

**Dependencies:**
- blockedBy: #19
- blocks: #34

**Spec Reference:** docs/flow-1.md — Section 1.1 (前端表现层), Section 1.3 (组件交互序列图)

**Active Form:** Building frontend workflow canvas with ReactFlow

**Description:**
Visual workflow designer using ReactFlow v11+. Drag-and-drop palette, canvas with zoom/pan, edge connections, node configuration panel, real-time execution visualization.

**Checklist:**
- [x] Set up React project (Vite + TypeScript + React 18) with Zustand for state management
- [x] Implement drag-and-drop node palette with category grouping (control/ai/data/integration tabs)
- [x] Implement ReactFlow canvas: zoom/pan/minimap/background grid/snap-to-grid
- [x] Implement custom node components per type (icon, color, input/output handles, status indicator)
- [x] Implement edge creation: handle type validation (output→input), animated edges during execution, edge labels
- [x] Implement node configuration side panel: dynamic form rendered from node's `config_schema` (JSON Schema → React Hook Form)
- [ ] Implement global workflow settings panel: name, description, timeout, error_strategy, environment
- [x] Implement execution visualization: node status overlay (running pulse, success green, failed red, skipped gray), progress bar, token count badges
- [ ] Implement real-time SSE consumption: update node statuses, display LLM streaming text, show timing
- [x] Implement keyboard shortcuts: Delete (remove selected), Ctrl+Z/Ctrl+Y (undo/redo), Ctrl+C/Ctrl+V (copy/paste), Ctrl+S (save)
- [x] Implement Dagre auto-layout algorithm
- [x] Implement workflow JSON import/export (download/upload .json files)
- [ ] Write E2E tests with Playwright: create workflow, connect nodes, configure LLM node, run and verify streaming

---

### #20 [done] 认证系统实现

**Phase:** 2 · **Status:** done

**Dependencies:**
- blockedBy: #8, #10
- blocks: #26, #29

**Spec Reference:** docs/flow-1.md — Section 5.1 (认证层), Section 5.3 (API-Key管理), Section 8.1 (鉴权方式)

**Active Form:** Implementing authentication system (API-Key + JWT)

**Description:**
API-Key (Bearer Token) and JWT-based authentication. Key lifecycle management, bcrypt hashing, rate limiting integration.

**Checklist:**
- [x] Implement API-Key generation: `sk-` prefix + 48 chars of secure random (secrets.token_urlsafe)
- [x] Implement bcrypt hashing: store `key_hash` only (never plaintext), `key_prefix` for display (first 8 chars)
- [x] Implement FastAPI `Depends(get_current_user)` for Bearer token extraction and validation
- [x] Implement JWT access token (15min TTL) + refresh token (7 day TTL) flow
- [x] Implement API-Key CRUD endpoints: POST create (returns full key once), GET list (prefix only), POST rotate, DELETE revoke
- [ ] Implement `last_used_at` auto-update on each authenticated request
- [ ] Implement optional `expires_at` for time-limited keys
- [ ] Implement per-key rate limit configuration
- [ ] Write tests: valid key, invalid key, expired key, revoked key, rate limit enforcement

---

### #21 [done] Skills SDK框架实现

**Phase:** 2 · **Status:** done

**Dependencies:**
- blockedBy: #8, #13
- blocks: #22, #31, #34

**Spec Reference:** docs/flow-1.md — Section 4 (完整Skills SDK规范), skills/目录示例

**Active Form:** Implementing Skills SDK framework (standalone package)

**Description:**
Standalone pip-installable Skills SDK. Manifest v2 parsing, SkillContext runtime API, sandbox execution, SkillScheduler, CLI tooling, and 5 preset skills.

**Checklist:**
- [x] Design `skills-sdk` Python package structure (`skills_sdk/` with `__init__`, `manifest.py`, `context.py`, `scheduler.py`, `sandbox.py`, `cli.py`)
- [x] Implement `SkillDefinition` model: parse manifest.yaml v2 with full validation (metadata, inputs JSON Schema, outputs JSON Schema, runtime config, triggers, compatibility)
- [x] Implement `SkillContext` class: `logger` (structlog), `get_llm_client(model)`, `load_template(path) → jinja2.Template`, `cache_get/set(key, value, ttl)`, `http_request(method, url, ...)`, `read_file/write_file(path)`, `record_metric(name, value, tags)`, execution metadata fields
- [ ] Implement Docker sandbox executor: reuse DockerSandbox from #32, map manifest sandbox config to container params
- [ ] Implement process sandbox executor: `asyncio.create_subprocess_exec`, stdin pipe, stdout/stderr capture
- [x] Implement `SkillScheduler`: `_load_skills()` (scan skills/ dir), `reload()`, `_validate_inputs()` (jsonschema), `execute_skill(name, inputs, context)`, `_generate_global_manifest()`
- [x] Implement `SkillNode`: `@register_node(node_type="skill")` integration — looks up skill by name, resolves params from VariablePool, calls SkillScheduler
- [ ] Implement `skills-cli` (Click/Typer): `init <name> --template`, `validate <path>`, `package <path> --output`, `run <name> --input '<json>' --skills-dir`, `test <path>`, `publish <file> --registry`, `list --skills-dir`, `info <name>`
- [x] Create preset skill: `document_processor` (PDF/Word/Excel parsing via pypdf2/python-docx/openpyxl)
- [x] Create preset skill: `risk_analyzer` (LLM-based document risk analysis with structured output)
- [x] Create preset skill: `compliance_checker` (rule engine + LLM, GDPR/HIPAA rule YAML files)
- [ ] Create preset skill: `data_transformer` (JSON/XML/CSV inter-conversion, jq-style mapping)
- [ ] Create preset skill: `notification_sender` (email/Slack/WeChat channel adapters)
- [x] Write SDK unit tests: manifest parsing, validation, skill execution, CLI commands

---

### #22 [done] 插件管理系统实现

**Phase:** 2 · **Status:** done

**Dependencies:**
- blockedBy: #13, #19
- blocks: #31, #34

**Spec Reference:** docs/flow-1.md — Section 3.3 (插件系统设计), Section 8.5 (节点管理API), manifest.yaml规范

**Active Form:** Implementing plugin management system

**Description:**
Plugin system with manifest-based registration, full lifecycle management, Plugin Manager API, and sandbox verification.

**Checklist:**
- [x] Implement `PluginManager` class: `install(file)`, `activate(plugin_id)`, `deactivate(plugin_id)`, `update(plugin_id, file)`, `uninstall(plugin_id)`
- [x] Implement plugin manifest.yaml validation (nodes, tools, runtime, permissions sections)
- [ ] Implement plugin dependency resolution (check requirements.txt compatibility, install via pip)
- [ ] Implement plugin sandbox verification: compatibility check (API version), security scan (bandit), isolated test run
- [x] Implement plugin API endpoints: `POST /nodes/plugins` (upload .plugin archive), `DELETE /nodes/plugins/{id}`, `PUT /nodes/plugins/{id}` (update config), `POST /nodes/plugins/{id}/toggle` (enable/disable)
- [x] Implement plugin packaging format: `.plugin` = tar.gz with manifest.yaml + code + assets
- [ ] Implement `plugins-cli` tool: `init`, `validate`, `package`, `publish`
- [ ] Implement plugin store client: discover plugins from registry, search by category/tag, install with one command
- [ ] Write tests: install→activate→deactivate→uninstall lifecycle, invalid manifest rejection, dependency conflict handling

---

### #23 [done] 版本管理系统实现

**Phase:** 2 · **Status:** done

**Dependencies:**
- blockedBy: #10, #19
- blocks: (none)

**Spec Reference:** docs/flow-1.md — Section 6 (完整版本管理规范)

**Active Form:** Implementing workflow version management system

**Description:**
Git-style version control: semantic versioning, draft/published lifecycle, version diff, rollback, and dev→staging→production environment promotion.

**Checklist:**
- [x] Implement version creation on publish: snapshot full DSL as JSONB, compute SHA-256 hash, assign semantic version
- [x] Implement semantic version parser: MAJOR.MINOR.PATCH validation and auto-increment logic
- [x] Implement version lifecycle state machine: `draft → published → deprecated → archived`
- [x] Implement version diff computation: compare two DSL JSONs, produce structured diff (nodes_added/removed/modified, edges_changed, config_changed with field-level detail)
- [x] Implement rollback operation: load target version DSL, create new version with incremented PATCH, auto-fill changelog
- [ ] Implement environment promotion: `POST /workflows/{id}/promote {target_environment}` with optional approval_id
- [ ] Implement canary deployment: traffic splitting by execution percentage (10→50→100), auto-rollback on elevated error rate
- [x] Implement version comparison API: `GET /workflows/{id}/versions/{v1}/diff/{v2}`
- [x] Implement version listing with filtering (status, environment, date_range, created_by)
- [ ] Write tests: publish version, semantic version conflict, diff computation, rollback, promotion flow, canary rollback trigger

---

### #24 [done] 错误处理与恢复框架

**Phase:** 2 · **Status:** done

**Dependencies:**
- blockedBy: #12, #13
- blocks: (none - consumed by #12 execution engine)

**Spec Reference:** docs/flow-1.md — Section 9 (完整错误处理规范), Section 9.1-9.4

**Active Form:** Implementing error handling, retry, and circuit breaker framework

**Description:**
Error classification hierarchy, RetryPolicy with exponential backoff, FallbackStrategy, CircuitBreaker, Dead Letter Queue.

**Checklist:**
- [x] Implement `ErrorCategory` hierarchy: `ValidationError` (DSL/Graph/Variable/Input), `ExecutionError` (Node/LLM/Skill/Code/Timeout/Resource/External), `SystemError` (DB/Queue/Config), `AuthError` (Authentication/Authorization/Quota)
- [x] Implement `RetryPolicy` dataclass: max_retries, backoff_factor, initial_delay_ms, max_delay_ms, jitter, retryable_exceptions list
- [x] Implement `get_delay(attempt)` with exponential backoff + optional jitter
- [ ] Implement `FallbackStrategy` enum and `apply_fallback()`: `SKIP_NODE` (mark skipped, continue), `USE_DEFAULT` (inject default_value), `CALL_BACKUP` (switch to fallback_model/service), `MANUAL` (route to DLQ)
- [x] Implement `CircuitBreaker` class: CLOSED/OPEN/HALF_OPEN states, failure_threshold, recovery_timeout_seconds, half_open_max_requests
- [x] Implement `circuit_breaker.call(coro)` wrapper: state transitions on success/failure, auto half-open after timeout
- [ ] Implement `execute_node_with_retry(node, variable_pool, error_config)` wrapper used by ExecutionScheduler
- [ ] Implement `ErrorHandlingConfig` per-node configuration (retry_policy, fallback_strategy, fallback_model, fallback_default_value, alert_on_failure)
- [x] Implement Dead Letter Queue: `DeadLetterEntry` model (execution_id, node_id, error, inputs, context, status: pending_review/retrying/resolved/confirmed_failure), DLQ query API, retry/resolve actions
- [x] Write tests: retry exhaustion, circuit breaker CLOSED→OPEN→HALF_OPEN→CLOSED cycle, fallback to backup model, DLQ flow

---

### #25 [done] 监控与可观测性系统

**Phase:** 2 · **Status:** done

**Dependencies:**
- blockedBy: #12, #19
- blocks: (none)

**Spec Reference:** docs/flow-1.md — Section 7 (完整监控规范), Section 7.1-7.4

**Active Form:** Implementing monitoring, metrics, and alerting system

**Description:**
Prometheus metrics, Grafana dashboards, OpenTelemetry tracing, structured logging, alert rules, and execution trace recording.

**Checklist:**
- [x] Implement Prometheus metrics endpoint (`/metrics` on a separate port)
- [x] Implement Counter metrics: `workflow_executions_total{status}`, `node_executions_total{node_type,status}`, `llm_call_total{model,status}`, `llm_call_errors_total{model,error_type}`
- [x] Implement Histogram metrics: `workflow_execution_duration_seconds`, `node_execution_duration_seconds{node_type}`, `llm_call_duration_seconds{model}`
- [x] Implement Gauge metrics: `active_executions`, `worker_queue_depth`, `circuit_breaker_state{name}`
- [ ] Implement execution trace recording: complete node-level trace JSON per Section 7.2 (stored in `node_executions` outputs column)
- [ ] Implement OpenTelemetry integration: auto-instrument FastAPI, manual spans for execution engine, trace context propagation in SSE events (traceparent header)
- [ ] Create Grafana dashboard JSON: "Workflow Overview" (execution rate, success rate, P50/P95/P99 latency), "Node Performance" (per-type latency heatmap), "LLM Usage" (token consumption by model/time), "Worker Status" (queue depth, active workers)
- [ ] Implement Prometheus alert rules YAML: `WorkflowFailureRateHigh` (>5% for 5min), `WorkflowP99LatencyHigh` (>10s for 10min), `LLMCallErrorRateHigh` (>3% for 5min)
- [x] Implement structlog configuration: all logs include `execution_id`, `workflow_id`, `node_id`, `user_id`, structured output to stdout (JSON for Loki)
- [ ] Write tests: metric counter increments, histogram bucket recording, trace context propagation

---

### #26 [done] RBAC权限系统实现

**Phase:** 3 · **Status:** done

**Dependencies:**
- blockedBy: #20, #19, #10
- blocks: (none)

**Spec Reference:** docs/flow-1.md — Section 5.2 (完整权限模型), Section 5.1 (安全体系)

**Active Form:** Implementing RBAC + ABAC permission and authorization system

**Description:**
Hybrid RBAC+ABAC: system roles, workspace roles, resource-level ACLs, permission enforcement middleware, audit logging.

**Checklist:**
- [x] Implement `Role` and `Permission` models with relationship tables
- [x] Implement system roles: `super_admin` (global), `admin` (workspace management), `auditor` (audit log read)
- [x] Implement workspace roles: `workspace_owner` (full workspace control), `developer` (CRUD workflows, publish, install plugins), `viewer` (read-only)
- [x] Implement resource-level ACL: workflow {create,read,update,delete,publish,execute}, node_plugin {install,configure,execute,uninstall}, knowledge_base {upload,query,manage,delete}, api_key {create,revoke,rotate}, skill {register,execute,configure}, model {configure,use}
- [ ] Implement FastAPI dependency `@require_permission(resource, action)`: extract user from token, resolve workspace context, check permission
- [ ] Implement workspace-level query isolation: all CRUD queries auto-filtered by `workspace_id` from token
- [x] Implement `AuditLog` recording: every CRUD operation writes immutable audit entry (user_id, workspace_id, action, resource_type, resource_id, details JSONB, ip_address, timestamp)
- [ ] Implement audit log query API: `GET /audit-logs?user=&action=&resource=&from=&to=&page=`
- [ ] Implement (optional, Phase 3+) SSO/SAML integration skeleton with python-saml
- [ ] Write tests: cross-workspace access denied, developer cannot delete others' workflows, viewer cannot modify, all actions audited

---

### #29 [done] 安全加固实现

**Phase:** 3 · **Status:** done

**Dependencies:**
- blockedBy: #17, #20
- blocks: (none)

**Spec Reference:** docs/flow-1.md — Section 5.1 (7层安全体系), Section 5.3 (API-Key管理)

**Active Form:** Implementing security hardening

**Description:**
7-layer security: Docker sandbox seccomp, AES-256 encryption, KMS credential management, prompt injection detection, input sanitization, security scanning.

**Checklist:**
- [ ] Implement seccomp profiles for Docker sandbox: Python profile (allow ~150 syscalls), Node.js profile, default-deny posture
- [ ] Implement sandbox network egress filtering: iptables rules in container, allow only manifest-declared `allowed_domains`
- [x] Implement AES-256-GCM field-level encryption: `encrypt_field(value)` / `decrypt_field(ciphertext)` for sensitive stored data
- [ ] Implement KMS integration: `KMSProvider` abstraction, HashiCorp Vault adapter, key rotation support
- [x] Implement prompt injection detection: pattern-based (regex for common injection patterns), LLM-based secondary check for high-risk inputs, configurable action (block/warn/log)
- [x] Implement input sanitization middleware: HTML entity encoding for XSS, SQLAlchemy parameterized queries (already in ORM), shell metacharacter escaping for code nodes
- [x] Implement CORS middleware: strict origin whitelist per environment
- [ ] Implement CSP headers: `Content-Security-Policy` with restrictive defaults
- [x] Implement 3-tier rate limiting: user-level (per minute/hour), app-level (per workflow), API-level (per endpoint), using Redis token bucket
- [ ] Integrate security scanning in CI: bandit (Python SAST), trivy (container scanning), safety (dependency CVE check)
- [ ] Write security tests: XSS vector injection, SQL injection attempt, prompt injection pattern, sandbox escape attempt, rate limit enforcement

---

### #27 [in_progress] K8s部署与Helm Charts

**Phase:** 3 · **Status:** in_progress

**Dependencies:**
- blockedBy: #19, #16
- blocks: (none)

**Spec Reference:** docs/flow-1.md — Section 10.2 (K8s部署拓扑), Section 10.3 (CI/CD)

**Active Form:** Implementing Kubernetes deployment with Helm charts

**Description:**
Production K8s deployment: Helm charts, HPA, resource limits, health checks, secrets, multi-environment support, canary strategy.

**Checklist:**
- [ ] Create Helm chart structure: `deploy/helm/workflow-engine/` with `Chart.yaml`, `values.yaml`, `templates/`
- [x] Create Deployment template for API Server: replicas, resource limits, env vars from ConfigMap/Secrets, liveness/readiness probes
- [x] Create Deployment template for Celery Worker: higher CPU/memory, HPA based on queue depth
- [ ] Create Deployment template for WebSocket Server: sticky session support, connection limits
- [x] Create HPA templates: API Server (CPU >70%, memory >80%), Worker (queue depth >100), WebSocket (connections >5000)
- [x] Create Service templates: ClusterIP for API, headless for WebSocket, ClusterIP for Worker monitoring
- [ ] Create Ingress template: TLS via cert-manager, rate limiting annotations, WebSocket upgrade support
- [x] Create ConfigMap template: all non-sensitive configuration
- [x] Create Secret template: DB credentials, Redis password, API encryption keys, model provider keys
- [ ] Create StatefulSet references for external data services (PostgreSQL, Redis, Milvus, MinIO)
- [ ] Create environment values files: `dev.yaml` (single replica, minimal resources), `staging.yaml` (2 replicas, moderate), `production.yaml` (HA, full resources)
- [ ] Create canary deployment Job: traffic split 10→50→100%, health check after each step, auto-rollback on Prometheus alert
- [ ] Create GitHub Actions deploy workflow: `deploy.yaml` with environment gates
- [ ] Write deployment smoke tests: deploy to kind cluster, verify all pods healthy, run basic workflow

---

### #28 [in_progress] 综合测试套件

**Phase:** 3 · **Status:** in_progress

**Dependencies:**
- blockedBy: #12, #14, #15, #17, #19
- blocks: (none — final quality gate)

**Spec Reference:** docs/flow-1.md — Section 11 (完整测试策略), Section 11.1-11.4

**Active Form:** Implementing comprehensive test suite (unit + integration + E2E)

**Description:**
Complete test suite: NodeTestHarness, workflow simulation, API integration with testcontainers, E2E with Playwright, performance with k6.

**Checklist:**
- [ ] Implement unit tests for all 21 node types using `NodeTestHarness` (control flow nodes, AI nodes, data nodes)
- [x] Implement unit tests for `GraphParser`: valid DSLs (5 types), invalid DSLs (6 error categories), optimization (dead code removal)
- [x] Implement unit tests for `VariablePool`: basic CRUD, template resolution (10+ Jinja2 patterns), snapshot/restore, merge strategies, system variables
- [ ] Implement unit tests for `ExecutionScheduler`: linear 3-node, parallel 3-branch, conditional (both paths), loop (for + while with break), checkpoint/resume, timeout, error recovery
- [x] Implement unit tests for error handling: retry exhaustion, circuit breaker state machine, all 4 fallback strategies, dead letter queue enqueue/dequeue
- [x] Implement unit tests for Skills SDK: manifest parsing (valid + invalid), skill execution cycle, sandbox execution (Docker + process)
- [ ] Implement integration tests with `testcontainers-python`: PostgreSQL (schema creation + CRUD), Redis (cache + queue operations)
- [ ] Implement API integration tests (FastAPI `TestClient` + async): all endpoints, auth flows (valid/invalid/expired/revoked tokens), error response formats, pagination
- [ ] Implement E2E tests with Playwright: create workflow → add nodes → connect edges → configure LLM node → run → verify streaming display → check execution history
- [ ] Implement performance tests with k6: `POST /workflows/{id}/run` at 100 RPS for 60s, measure P50/P95/P99, verify <1% error rate
- [ ] Achieve coverage targets: `engine/` >90%, `nodes/` >85%, `api/` >80%
- [ ] Configure `pytest-cov` with coverage thresholds in `pyproject.toml`, fail CI if below thresholds

---

### #31 [in_progress] 开发者文档与API参考

**Phase:** 4 · **Status:** in_progress

**Dependencies:**
- blockedBy: #19, #21, #22
- blocks: (none)

**Spec Reference:** docs/flow-1.md 和 docs/research-report.md (所有章节)

**Active Form:** Writing developer documentation and API reference

**Description:**
Comprehensive developer docs: quickstart, API reference, Skills SDK guide, plugin guide, deployment guide, architecture overview, examples.

**Checklist:**
- [ ] Write Getting Started guide: local setup (prerequisites, clone, `docker compose up`), create first workflow (step-by-step with screenshots), create first skill
- [x] Generate API reference from FastAPI OpenAPI schema: deploy with Scalar/ReDoc theme, include request/response examples
- [ ] Write Skills SDK Developer Guide: project structure, manifest.yaml reference (every field documented), handler patterns (async, error handling, context API), testing skills, packaging and publishing
- [ ] Write Plugin Development Guide: project structure, node registration, tool registration, manifest reference, packaging, publishing to marketplace
- [ ] Write Deployment Guide: Docker Compose (single-node), K8s Helm (multi-node HA), environment configuration reference, secrets management
- [ ] Write Architecture Overview: system layers diagram, data flow (request→execution→response), key design decisions and rationale
- [ ] Write Security Guide: API-Key management best practices, RBAC configuration examples, sandbox security model, audit log usage
- [ ] Create 10 example workflows: document review, customer support triage, data pipeline, content generation, risk analysis, compliance check, multi-agent research, code review automation, notification orchestration, ETL pipeline
- [ ] Create 5 example skills: sentiment analyzer, language translator, image describer, SQL query generator, meeting summarizer
- [ ] Create `CONTRIBUTING.md`: development setup, code style, PR process, testing requirements

---

### #34 [done] 节点与技能市场

**Phase:** 4 · **Status:** done

**Dependencies:**
- blockedBy: #22, #21, #18
- blocks: (none)

**Spec Reference:** docs/flow-1.md — Section 13 (Phase 4 生态), Section 3.3 (插件包结构)

**Active Form:** Building node and skill marketplace

**Description:**
Community marketplace: discover, install, share nodes/plugins/skills. Search, categories, ratings, version compatibility, one-click install.

**Checklist:**
- [x] Implement marketplace registry backend: `PackageRegistry` model (name, type node/skill, versions JSONB, metadata, author, download_count, rating)
- [x] Implement marketplace API: `GET /marketplace/search?q=&type=&category=&sort=`, `GET /marketplace/package/{name}`, `POST /marketplace/publish`, `POST /marketplace/install/{name}`, `POST /marketplace/rate`
- [ ] Implement package storage backend (MinIO/S3): versioned upload, checksum verification, download with CDN
- [ ] Implement package verification pipeline: security scan (bandit + trivy), compatibility check (API version range), digital signature verification (cosign), automated smoke test in sandbox
- [x] Implement frontend marketplace UI: search bar with autocomplete, category browsing, package detail page (description, versions, ratings, install count), one-click install button, author profiles
- [x] Implement community features: star rating (1-5), text reviews, download statistics, "verified publisher" badge, report abuse
- [ ] Implement notification system: new version available for installed packages, security advisory alerts
- [ ] Write marketplace moderation guidelines
- [x] Write tests: publish→approve→search→install flow, rating aggregation, version compatibility check

---

## 阶段概览

| 阶段 | 任务数 | 关键任务 | 预估周期 |
|------|--------|---------|---------|
| Phase 1: MVP | 15 (#8-#19, #30, #32, #33) | #12 执行引擎, #19 API层, #18 前端画布 | 8-10周 |
| Phase 2: 增强 | 5 (#20-#25) | #21 Skills SDK, #22 插件系统, #23 版本管理 | 6-8周 |
| Phase 3: 企业级 | 4 (#26-#29) | #26 RBAC, #27 K8s部署, #29 安全加固 | 6-8周 |
| Phase 4: 生态 | 2 (#31, #34) | #34 节点市场, #31 文档 | 持续迭代 |

---

## 并行度分析

- **Phase 1 最大并行:** 5条独立路径同时推进 (`#10 DB Schema`, `#13 核心抽象`, `#30 模型路由`, `#32 Docker沙箱`, `#20 认证`)
- **关键路径:** `#8 → #13 → #11 → #12 → #19 → #18`, 约6个串行步骤
- **Phase 2-3** 与 Phase 1 后续任务存在并行窗口 (`#21 Skills SDK` 可与 `#14/#15/#17 节点` 并行)
- **测试 (#28)** 应作为持续活动，每个节点/模块完成后立即编写对应测试

---

## 当前状态

- **已完成 (23):** #8 项目脚手架, #10 数据库Schema, #13 核心抽象, #30 模型路由, #32 Docker沙箱, #9 Variable Pool, #11 DSL解析器, #12 执行引擎, #14 控制流节点, #15 AI节点, #17 数据/集成节点, #16 SSE/WebSocket, #19 REST API层, #20 认证系统, #21 Skills SDK, #22 插件管理, #23 版本管理, #24 错误处理, #25 监控, #26 RBAC, #29 安全加固, #33 RAG管道, #34 节点市场
- **进行中 (4):** #18 前端画布, #27 K8s部署, #28 测试套件, #31 文档
- **待开始 (0):** (无)

**关键缺口:**
1. 所有服务使用内存存储，未接入数据库 (尽管模型已定义)
2. 无 Alembic 迁移文件
3. 各服务未集成 (熔断器、监控、RBAC、安全均独立实现)
4. 测试覆盖薄弱 — 仅6个单元测试文件，无集成/E2E测试
5. K8s部署仅有原始manifests，无Helm Charts
