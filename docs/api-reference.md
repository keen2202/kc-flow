# AI Workflow Orchestration Engine — API Reference

> Base URL: `http://localhost:8080/api/v1`

---

## Authentication

All endpoints (except `/health` and `/auth/login`) require authentication via Bearer token:

```
Authorization: Bearer <api_key_or_jwt_token>
```

### API Key format: `sk-` + 48 characters

---

## Endpoints

### Health Check

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | System health check |

**Response:**
```json
{"status": "ok", "version": "0.1.0"}
```

---

### Authentication (`/auth`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/login` | Authenticate and get JWT tokens |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/api-keys` | Create a new API key |
| GET | `/auth/api-keys` | List API keys (prefix only) |
| DELETE | `/auth/api-keys/{key_id}` | Revoke an API key |

---

### Workflows (`/workflows`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/workflows` | Create a new workflow |
| GET | `/workflows` | List all workflows (paginated) |
| GET | `/workflows/{id}` | Get workflow details |
| PUT | `/workflows/{id}` | Update workflow definition |
| DELETE | `/workflows/{id}` | Delete a workflow (soft delete) |
| POST | `/workflows/{id}/publish` | Publish a workflow version |
| POST | `/workflows/{id}/rollback` | Rollback to a previous version |
| POST | `/workflows/{id}/clone` | Clone a workflow |

#### Execution

| Method | Path | Description |
|--------|------|-------------|
| POST | `/workflows/{id}/run` | Execute synchronously |
| POST | `/workflows/{id}/run-async` | Execute asynchronously |
| POST | `/workflows/{id}/run-stream` | Execute with SSE streaming |
| GET | `/workflows/{id}/executions` | List executions |
| GET | `/workflows/{id}/executions/{exec_id}` | Get execution status |
| POST | `/workflows/{id}/executions/{exec_id}/cancel` | Cancel execution |

---

### Nodes (`/nodes`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/nodes` | List all registered node types |
| GET | `/nodes/categories` | List node categories |
| GET | `/nodes/{type}` | Get node type details with config schema |
| POST | `/nodes/plugins` | Install a node plugin |
| DELETE | `/nodes/plugins/{id}` | Uninstall a node plugin |

---

### Skills (`/skills`)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/skills` | List all available skills |
| POST | `/skills/reload` | Reload skills from directory |
| GET | `/skills/{name}` | Get skill details |
| POST | `/skills/{name}/test` | Test execute a skill |

---

### Streaming (`/streaming`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/workflows/{id}/executions/{exec_id}/stream` | SSE event stream |
| WS | `/ws/workflows/{id}/executions/{exec_id}` | WebSocket real-time |

#### SSE Event Types

| Event | Description |
|-------|-------------|
| `workflow_started` | Workflow execution started |
| `node_started` | Node execution started |
| `node_streaming` | LLM streaming text chunk |
| `node_completed` | Node execution completed |
| `node_skipped` | Node was skipped |
| `workflow_completed` | Workflow execution completed |
| `ping` | Heartbeat |
| `error` | Error occurred |

#### WebSocket Protocol

Client → Server:
```json
{"action": "subscribe"}
{"action": "cancel"}
```

Server → Client:
```json
{"event": "node_started", "data": {"node_id": "...", "node_type": "llm"}}
{"event": "node_completed", "data": {"node_id": "...", "status": "succeeded"}}
```

---

## Unified Response Format

### Success
```json
{
    "code": 0,
    "message": "success",
    "data": { ... }
}
```

### Error
```json
{
    "code": 40001,
    "message": "Validation failed",
    "data": null,
    "errors": [
        {"field": "name", "reason": "Name is required"}
    ]
}
```

### Pagination
```json
{
    "items": [ ... ],
    "pagination": {
        "page": 1,
        "page_size": 20,
        "total": 100,
        "total_pages": 5
    }
}
```

---

## Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| 40001 | 400 | DSL validation error |
| 40002 | 400 | Graph validation error |
| 40003 | 400 | Variable reference error |
| 40004 | 400 | Input validation error |
| 40101 | 401 | Authentication required |
| 40102 | 401 | Invalid or expired token |
| 40301 | 403 | Access denied |
| 40401 | 404 | Workflow not found |
| 40402 | 404 | Execution not found |
| 40403 | 404 | Node type not found |
| 40404 | 404 | Skill not found |
| 42901 | 429 | Rate limit exceeded |
| 50001 | 500 | Internal server error |
| 50301 | 503 | Circuit breaker open |

---

## Node Types

### Control Flow
| Type | Display Name | Description |
|------|-------------|-------------|
| `start` | 开始 | Workflow entry point |
| `end` | 结束 | Workflow exit point |
| `condition` | 条件分支 | If-else branching |
| `loop` | 循环 | For/while loops |
| `parallel` | 并行分支 | Parallel execution |
| `variable_assigner` | 变量赋值 | Dynamic variable assignment |
| `variable_aggregator` | 变量聚合 | Multi-branch aggregation |

### AI
| Type | Display Name | Description |
|------|-------------|-------------|
| `llm` | 大模型推理 | LLM inference |
| `knowledge_retrieval` | 知识库检索 | RAG retrieval |
| `question_classifier` | 意图分类 | Intent classification |
| `parameter_extractor` | 参数提取 | Structured extraction |
| `agent` | 自主Agent | Autonomous agent |
| `multi_agent` | 多Agent协同 | Multi-agent collaboration |

### Data/Integration
| Type | Display Name | Description |
|------|-------------|-------------|
| `code` | 代码执行 | Sandbox code execution |
| `http_request` | HTTP请求 | HTTP API calls |
| `template` | 模板转换 | Jinja2 templates |
| `data_transform` | 数据转换 | Data transformation |
| `document_parser` | 文档解析 | PDF/DOCX/XLSX parsing |
| `webhook` | Webhook | External callbacks |
| `mcp_tool` | MCP工具 | MCP protocol tools |
| `wait` | 等待 | Timed delays |
| `skill` | 技能节点 | Skills SDK integration |
