# AI工作流编排系统 — 技术规格文档

> 基于Dify与Coze深度调研，融合两者优势设计。Dify的集成化架构与Variable Pool数据流转模型、Coze的模块化微服务与多Agent协同，形成本系统的设计基础。

---

## 一、系统架构设计

### 1.1 总体架构

```
┌─────────────────────────────────────────────────────────────────┐
│                         前端表现层                                │
│  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌───────────┐     │
│  │ 工作流画布 │  │ 节点市场   │  │ 监控仪表盘 │  │ 系统管理   │     │
│  │ (ReactFlow)│  │ (Plugin)  │  │ (Grafana) │  │ (Admin)   │     │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘     │
└────────┼───────────────┼───────────────┼───────────────┼─────────┘
         │               │               │               │
┌────────┼───────────────┼───────────────┼───────────────┼─────────┐
│        │           API 网关层                                    │
│  ┌─────┴──────────────────────────┴──────────────────────────┐  │
│  │              Nginx/Envoy (TLS + 限流 + 路由)               │  │
│  │  RESTful API (FastAPI)  │  WebSocket (实时推送)            │  │
│  │  SSE (流式响应)          │  gRPC (服务间通信)               │  │
│  └─────┬──────────────────────────┬──────────────────────────┘  │
│  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐    │
│  │ 工作流API  │  │ 节点管理API│  │ 模型调用API│  │ 认证鉴权API│    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │
└────────┼───────────────┼───────────────┼───────────────┼─────────┘
         │               │               │               │
┌────────┼───────────────┼───────────────┼───────────────┼─────────┐
│        │             核心服务层 (Python 3.11+ / FastAPI)          │
│  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐    │
│  │ 工作流引擎 │  │ DSL解析器  │  │ 节点运行时  │  │ 变量池管理 │    │
│  │ (Graph    │  │ (Parser)  │  │ (Node     │  │ (Variable │    │
│  │  Engine)  │  │           │  │  Runtime) │  │  Pool)    │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │
│  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐    │
│  │ Skill调度器│  │ 模型路由层 │  │ 插件管理器 │  │ 事件总线   │    │
│  │ (Skill    │  │ (Model    │  │ (Plugin   │  │ (Event    │    │
│  │  Scheduler)│  │  Router)  │  │  Manager) │  │  Bus)     │    │
│  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘    │
│  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐    │
│  │ 版本管理器 │  │ Agent协调器│  │ 错误恢复器 │  │ 审计日志   │    │
│  │ (Version  │  │ (Agent    │  │ (Error    │  │ (Audit    │    │
│  │  Manager) │  │  Orch.)   │  │  Recovery)│  │  Logger)  │    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │
└────────┬───────────────┬───────────────┬───────────────┬─────────┘
         │               │               │               │
┌────────┼───────────────┼───────────────┼───────────────┼─────────┐
│        │             基础设施层                                    │
│  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐  ┌─────┴─────┐    │
│  │ PostgreSQL│  │ Redis     │  │ 向量数据库 │  │ 对象存储   │    │
│  │ (主数据库) │  │ (缓存/队列)│  │ (Milvus等)│  │ (MinIO)   │    │
│  └───────────┘  └───────────┘  └───────────┘  └───────────┘    │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Celery      │  │ Prometheus  │  │ Docker/K8s              │  │
│  │ (异步任务)  │  │ + Grafana   │  │ (容器编排)              │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 架构设计原则

系统架构借鉴Dify的集成化优势与Coze的模块化理念，采用"统一平台、模块化核心、插件化扩展"的设计策略：

| 原则 | 说明 | 来源 |
|------|------|------|
| **分层解耦** | API网关层、核心服务层、基础设施层各自独立，通过标准化接口通信 | 通用架构原则 |
| **图引擎为心** | 以基于DAG的工作流图引擎为核心，统一调度所有节点执行 | Dify |
| **变量池通信** | 采用发布-订阅模式的Variable Pool实现节点间数据解耦 | Dify |
| **多Agent协同** | 支持主从Agent模式，Master Agent负责任务拆解与结果归并 | Coze |
| **插件化扩展** | 节点、模型和工具均通过插件注册机制实现热扩展 | Dify + Coze |
| **定义与执行分离** | DSL定义层与Runtime执行层解耦，便于版本管理和回滚 | Dify |
| **协议标准化** | 原生支持MCP协议，拥抱行业标准 | Coze |
| **技能SDK独立** | Skills SDK作为独立组件，可单独使用或集成到工作流引擎 | 本项目创新 |

### 1.3 组件交互序列图

```
用户          前端画布        API网关      工作流引擎     VariablePool    LLM节点       EventBus
 │              │              │              │              │            │            │
 │  拖拽连线    │              │              │              │            │            │
 │─────────────>│              │              │              │            │            │
 │              │  POST /workflows          │              │            │            │
 │              │─────────────>│             │              │            │            │
 │              │              │ parse DSL   │              │            │            │
 │              │              │────────────>│              │            │            │
 │              │              │             │ validate DAG │            │            │
 │              │              │             │──────────────│            │            │
 │              │              │  {workflow_id, version}    │            │            │
 │              │              │<────────────│              │            │            │
 │              │  {id, version}            │              │            │            │
 │              │<─────────────│             │              │            │            │
 │              │              │             │              │            │            │
 │  点击执行    │              │             │              │            │            │
 │─────────────>│              │             │              │            │            │
 │              │  POST /run   │             │              │            │            │
 │              │─────────────>│             │              │            │            │
 │              │              │ execute()   │              │            │            │
 │              │              │────────────>│              │            │            │
 │              │              │             │ node_started │            │            │
 │              │              │             │─────────────────────────────────────>│
 │              │              │             │              │            │            │
 │              │              │             │              │ execute()  │            │
 │              │              │             │──────────────────────────>│            │
 │              │              │             │              │            │            │
 │              │              │             │              │   output   │            │
 │              │              │             │<──────────────────────────│            │
 │              │              │             │ set(node_llm.output)      │            │
 │              │              │             │─────────────>│            │            │
 │              │              │             │              │            │            │
 │              │              │             │ node_completed            │            │
 │              │              │             │─────────────────────────────────────>│
 │              │              │             │              │            │            │
 │              │  SSE: node_completed      │              │            │            │
 │              │<─────────────│<────────────│              │            │            │
```

### 1.4 技术选型理由

| 组件 | 技术选型 | 理由 |
|------|---------|------|
| API框架 | FastAPI (Python) | 原生异步支持、自动OpenAPI文档、类型安全 |
| 工作流引擎 | 自研 (Python asyncio) | 深度定制需求，借鉴Dify图引擎设计 |
| 前端画布 | ReactFlow v11+ | 成熟的节点编辑器，支持自定义节点和边 |
| 异步任务 | Celery + Redis | 业界标准，Dify已验证的方案 |
| 数据库 | PostgreSQL 15+ | JSONB支持DSL灵活存储，成熟稳定 |
| 向量数据库 | Milvus (主) + PGVector (轻量) | 分层方案，兼顾性能与简易部署 |
| 对象存储 | MinIO (S3兼容) | 开源、S3兼容、易于迁移 |
| 容器编排 | Docker Compose (开发) + K8s (生产) | 开发到生产的平滑过渡 |

---

## 二、工作流执行引擎设计

### 2.1 核心数据结构

**Workflow DSL（JSON格式）：**

```json
{
    "workflow": {
        "id": "wf_a1b2c3d4",
        "name": "文档智能审阅工作流",
        "version": "1.2.0",
        "description": "自动化金融文档审核流程",
        "environment": "production",
        "config": {
            "timeout_seconds": 1800,
            "max_retries": 3,
            "error_strategy": "fail_fast",
            "checkpoint_enabled": true
        },
        "nodes": [
            {
                "id": "node_start",
                "type": "start",
                "data": {
                    "variables": [
                        {"name": "document_url", "type": "string", "required": true, "description": "待审阅文档的URL"},
                        {"name": "review_type", "type": "select", "options": ["PPM", "LPA", "SLA"], "default": "PPM"},
                        {"name": "language", "type": "string", "default": "zh-CN"}
                    ]
                },
                "position": {"x": 100, "y": 200}
            },
            {
                "id": "node_llm_extract",
                "type": "llm",
                "data": {
                    "model": "gpt-4o",
                    "prompt_template": "从以下文档中提取关键条款信息：\n\n文档内容：{{node_doc_parser.output.content}}\n\n请提取：\n1. 合同主体信息\n2. 关键条款列表\n3. 风险评估",
                    "temperature": 0.1,
                    "max_tokens": 4096,
                    "output_schema": {
                        "type": "object",
                        "properties": {
                            "parties": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "role": {"type": "string"}}}},
                            "clauses": {"type": "array", "items": {"type": "object", "properties": {"title": {"type": "string"}, "content": {"type": "string"}, "risk_level": {"type": "string", "enum": ["low", "medium", "high"]}}}},
                            "overall_risk": {"type": "string", "enum": ["low", "medium", "high"]}
                        },
                        "required": ["clauses", "overall_risk"]
                    },
                    "fallback_model": "claude-opus-4-7",
                    "retry_config": {"max_retries": 3, "backoff_factor": 2.0}
                },
                "position": {"x": 400, "y": 200}
            },
            {
                "id": "node_condition",
                "type": "condition",
                "data": {
                    "conditions": [
                        {
                            "expression": "{{node_llm_extract.output.overall_risk}} == 'high'",
                            "target_node": "node_alert"
                        },
                        {
                            "expression": "{{node_llm_extract.output.overall_risk}} in ['low', 'medium']",
                            "target_node": "node_report"
                        }
                    ],
                    "default_target": "node_report"
                },
                "position": {"x": 700, "y": 200}
            },
            {
                "id": "node_alert",
                "type": "skill",
                "data": {
                    "skill_name": "risk_alert",
                    "skill_params": {
                        "risk_level": "{{node_llm_extract.output.overall_risk}}",
                        "clauses": "{{node_llm_extract.output.clauses}}",
                        "notify_channels": ["email", "slack"]
                    }
                },
                "position": {"x": 1000, "y": 100}
            },
            {
                "id": "node_report",
                "type": "template",
                "data": {
                    "template": "templates/review_report.jinja2",
                    "inputs": {
                        "clauses": "{{node_llm_extract.output.clauses}}",
                        "risk": "{{node_llm_extract.output.overall_risk}}",
                        "review_type": "{{node_start.output.review_type}}"
                    },
                    "output_format": "markdown"
                },
                "position": {"x": 1000, "y": 300}
            },
            {
                "id": "node_aggregator",
                "type": "variable_aggregator",
                "data": {
                    "groups": [
                        {"name": "final_output", "variables": ["node_alert.output", "node_report.output"]}
                    ],
                    "strategy": "first_non_null"
                },
                "position": {"x": 1300, "y": 200}
            },
            {
                "id": "node_end",
                "type": "end",
                "data": {
                    "outputs": [
                        {"name": "result", "from": "node_aggregator.output.final_output"},
                        {"name": "risk_level", "from": "node_llm_extract.output.overall_risk"},
                        {"name": "execution_summary", "from": "sys.execution_metadata"}
                    ]
                },
                "position": {"x": 1600, "y": 200}
            }
        ],
        "edges": [
            {"id": "e1", "source": "node_start", "target": "node_llm_extract", "source_handle": "output", "target_handle": "input"},
            {"id": "e2", "source": "node_llm_extract", "target": "node_condition"},
            {"id": "e3", "source": "node_condition", "target": "node_alert", "condition_index": 0},
            {"id": "e4", "source": "node_condition", "target": "node_report", "condition_index": 1},
            {"id": "e5", "source": "node_alert", "target": "node_aggregator"},
            {"id": "e6", "source": "node_report", "target": "node_aggregator"},
            {"id": "e7", "source": "node_aggregator", "target": "node_end"}
        ],
        "view_data": {"viewport": {"x": 0, "y": 0, "zoom": 1}}
    }
}
```

### 2.2 执行引擎核心组件

| 组件 | 职责 | 关键方法 |
|------|------|---------|
| **GraphParser** | 将DSL JSON解析为可执行的图结构 | `parse()`, `validate()`, `optimize()`, `detect_cycles()` |
| **ExecutionScheduler** | 基于拓扑排序的执行调度器 | `schedule()`, `enqueue_node()`, `resolve_dependencies()`, `get_next_batch()` |
| **VariablePool** | 运行时内存空间，存储所有节点输入输出 | `get()`, `set()`, `resolve_template()`, `snapshot()`, `merge()` |
| **NodeRuntime** | 节点抽象基类，定义统一的执行接口 | `execute()`, `validate_inputs()`, `pre_execute()`, `post_execute()` |
| **ParallelExecutor** | 并行分支执行器 | `execute_parallel()`, `wait_all()`, `handle_branch_failure()` |
| **EventEmitter** | 事件系统，推送执行状态到前端 | `emit()`, `subscribe()`, `unsubscribe()` |
| **CheckpointManager** | 执行检查点，支持断点恢复 | `save_checkpoint()`, `restore_checkpoint()`, `cleanup()` |

### 2.3 执行流程详解

```
阶段一：解析 (Parsing Phase)
┌──────────────────────────────────────────────────────┐
│ 1. GraphParser.parse(dsl_json)                       │
│    ├── JSON Schema验证 (基于workflow-schema.json)     │
│    ├── 节点ID唯一性检查                                │
│    ├── 边连接有效性验证 (source/target必须存在)         │
│    ├── 必需节点检查 (至少包含Start和End)                │
│    └── 构建邻接表 (adjacency list)                     │
│                                                      │
│ 2. GraphParser.validate(graph)                       │
│    ├── 环路检测 (DFS cycle detection)                  │
│    ├── 变量引用解析 (所有 {{...}} 必须有效)             │
│    ├── 类型兼容性检查 (上游输出类型匹配下游输入类型)     │
│    ├── 条件表达式语法验证                                │
│    └── 不可达节点检测                                    │
│                                                      │
│ 3. GraphParser.optimize(graph)                       │
│    ├── 死代码消除 (不可达节点移除)                      │
│    ├── 常量折叠 (编译期可确定的表达式)                  │
│    └── 并行分支检测 (标记可并行执行的分支)               │
└──────────────────────────────────────────────────────┘

阶段二：初始化 (Initialization Phase)
┌──────────────────────────────────────────────────────┐
│ 1. 创建 VariablePool 实例                              │
│    ├── 注入系统变量:                                   │
│    │   ├── sys.execution_id: "exec_uuid"              │
│    │   ├── sys.workflow_id: "wf_uuid"                │
│    │   ├── sys.workflow_version: "1.2.0"             │
│    │   ├── sys.user_id: "user_abc123"                │
│    │   ├── sys.timestamp: "2026-05-02T10:30:00Z"    │
│    │   ├── sys.environment: "production"              │
│    │   └── sys.trigger: "api"                        │
│    └── 注入用户输入变量 (来自API请求)                    │
│                                                      │
│ 2. 创建 ExecutionContext                              │
│    ├── execution_id: UUID                             │
│    ├── workflow_version_id: UUID                      │
│    ├── trace_enabled: boolean                         │
│    └── metadata: Dict                                 │
│                                                      │
│ 3. 初始化 EventEmitter                                 │
│    └── 注册 WebSocket/SSE 推送通道                     │
└──────────────────────────────────────────────────────┘

阶段三：调度执行 (Scheduling & Execution Phase)
┌──────────────────────────────────────────────────────┐
│ ExecutionScheduler 主循环:                            │
│                                                      │
│ ready_queue = [StartNode]  # 初始化就绪队列            │
│ while ready_queue is not empty:                      │
│                                                      │
│   batch = get_next_batch(ready_queue)                 │
│   # batch包含所有依赖已满足的节点                      │
│                                                      │
│   for node in batch:                                 │
│     ├── 标记节点状态: RUNNING                          │
│     ├── EventEmitter.emit("node_started")            │
│     │                                                 │
│     ├── try:                                         │
│     │   ├── inputs = VariablePool.resolve(node.id)   │
│     │   ├── result = await node.execute(inputs)      │
│     │   ├── VariablePool.set(node.id + ".output", result)│
│     │   ├── 标记节点状态: SUCCEEDED                    │
│     │   └── EventEmitter.emit("node_completed")      │
│     │                                                 │
│     ├── catch TimeoutError:                          │
│     │   ├── 标记节点状态: TIMEOUT                      │
│     │   └── 执行超时处理策略                            │
│     │                                                 │
│     ├── catch RetryableError:                        │
│     │   ├── 如果未超过最大重试次数:                      │
│     │   │   ├── 等待 backoff_delay                    │
│     │   │   └── 重新入队                               │
│     │   └── 否则: 标记节点状态: FAILED                  │
│     │                                                 │
│     └── catch NonRetryableError:                     │
│         ├── 标记节点状态: FAILED                       │
│         └── 执行错误处理策略                            │
│                                                      │
│   # 依赖解析                                           │
│   for succeeded_node in batch_succeeded:             │
│     for successor in graph.get_successors(node.id):  │
│       if all_predecessors_completed(successor):      │
│         ready_queue.enqueue(successor)                │
│                                                      │
│   # 检查工作流是否应终止                               │
│   if should_terminate():                             │
│     break                                            │
└──────────────────────────────────────────────────────┘

阶段四：完成 (Completion Phase)
┌──────────────────────────────────────────────────────┐
│ 1. 收集 End 节点的输出                                 │
│ 2. 生成执行摘要:                                       │
│    ├── total_duration_ms                             │
│    ├── node_executions: [{node_id, status, duration}]│
│    ├── total_tokens_consumed                         │
│    ├── total_api_calls                               │
│    └── error_count                                   │
│ 3. EventEmitter.emit("workflow_completed")           │
│ 4. 保存执行记录到数据库                                  │
│ 5. 清理 VariablePool                                  │
│ 6. 返回最终结果                                        │
└──────────────────────────────────────────────────────┘
```

### 2.4 分支处理策略

**条件分支：**
```
If/Else节点执行逻辑:
1. 按顺序评估 conditions 数组中的每个条件
2. 第一个匹配的条件激活对应的 target_node
3. 如果所有条件都不匹配，使用 default_target
4. 条件支持的操作符:
   - 比较: ==, !=, >, <, >=, <=
   - 包含: in, not_in, contains, not_contains
   - 逻辑: and, or, not
   - 存在性: exists, not_exists
   - 类型: is_empty, not_empty, is_type
5. 未激活的分支节点标记为 SKIPPED
```

**并行分支：**
```
Parallel节点执行逻辑:
1. 识别所有并行分支 (从Parallel节点的出边)
2. 创建 asyncio.Task 或 ThreadPoolExecutor 提交每个分支
3. 各分支独立运行，写入各自的 VariablePool 命名空间
4. 等待所有分支完成 (asyncio.gather / concurrent.futures.wait)
5. 错误处理策略可配置:
   - fail_fast: 任一分支失败立即终止其他分支
   - continue_on_error: 失败分支记录错误，其他分支继续
   - aggregate: 收集所有错误，最后统一报告
6. 分支汇聚处使用 VariableAggregator 统一输出
```

### 2.5 检查点与断点恢复

```
Checkpoint 数据结构:
{
    "checkpoint_id": "ckpt_uuid",
    "execution_id": "exec_uuid",
    "workflow_id": "wf_uuid",
    "created_at": "2026-05-02T10:30:15Z",
    "graph_state": {
        "node_states": {
            "node_start": "SUCCEEDED",
            "node_llm_extract": "SUCCEEDED",
            "node_condition": "RUNNING",
            "node_alert": "PENDING",
            "node_report": "PENDING"
        },
        "ready_queue": ["node_alert"],
        "blocked_nodes": ["node_report"]
    },
    "variable_pool_snapshot": {
        "node_start.output": {...},
        "node_llm_extract.output": {...}
    },
    "resume_point": "node_condition"
}

恢复流程:
1. 从数据库加载最近的checkpoint
2. 恢复 VariablePool 状态
3. 恢复 ready_queue 和 blocked_nodes
4. 从 resume_point 继续执行
5. 如果是幂等节点(LLM调用)，可选择跳过已执行节点
```

---

## 三、节点类型体系与注册管理

### 3.1 完整节点类型层次

**第一层：基础控制节点**

| 节点类型 | 说明 | 输入 | 输出 | 典型配置 |
|---------|------|------|------|---------|
| Start | 工作流启动入口 | 用户输入变量 | 变量集合 | `variables: [{name, type, required, default}]` |
| End | 工作流终止出口 | 上游输出 | 最终结果 | `outputs: [{name, from}]` |
| Condition | if-else分支判断 | 评估变量 | 分支路由 | `conditions: [{expression, target}]` |
| Loop | 循环执行 | 循环变量 | 循环结果 | `loop_type: for/while, max_iterations` |
| Parallel | 并行分支 | 分支输入 | 汇聚结果 | `branches: [{name, nodes}]` |
| VariableAssigner | 变量赋值 | 赋值规则 | 新变量 | `assignments: [{var, value}]` |
| VariableAggregator | 多分支聚合 | 多个变量组 | 聚合变量 | `groups: [{name, variables, strategy}]` |

**第二层：AI核心节点**

| 节点类型 | 说明 | 关键配置 |
|---------|------|---------|
| LLM | 大模型推理 | `model`, `prompt_template`, `temperature`, `max_tokens`, `output_schema`, `fallback_model`, `retry_config` |
| KnowledgeRetrieval | 知识库检索 | `knowledge_base_id`, `retrieval_strategy`(vector/hybrid/fulltext), `top_k`, `score_threshold`, `rerank_model` |
| QuestionClassifier | 意图识别 | `classes: [{name, description, examples, target_node}]` |
| ParameterExtractor | 结构化提取 | `parameters: [{name, type, description, required}]` |
| Agent | 自主Agent | `agent_config: {max_iterations, tools, memory_type}` |
| MultiAgent | 多Agent协同 | `agents: [{name, role, tools}], coordination: sequential/broadcast/debate` |

**第三层：数据处理与集成节点**

| 节点类型 | 说明 | 关键配置 |
|---------|------|---------|
| Code | 沙箱代码执行 | `language: python/javascript`, `code`, `dependencies`, `timeout` |
| HTTPRequest | HTTP API调用 | `url`, `method`, `headers`, `body_template`, `timeout`, `retry_config` |
| Template | Jinja2模板转换 | `template/text`, `inputs`, `output_format` |
| DataTransform | 数据格式转换 | `input_format`, `output_format`, `mapping_rules` |
| DocumentParser | 文档解析 | `file_source`, `file_type`(pdf/docx/xlsx), `extraction_mode` |
| Webhook | 外部回调触发 | `webhook_url`, `secret`, `events` |
| MCPTool | MCP协议工具调用 | `mcp_server`, `tool_name`, `tool_params` |
| Skill | 技能调用 | `skill_name`, `skill_params` (详见第四章) |
| Wait | 定时等待 | `wait_type: fixed/dynamic`, `duration_seconds`, `until_condition` |

### 3.2 节点注册机制

```python
# === 节点基类定义 ===
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Type
from pydantic import BaseModel, Field
from enum import Enum

class NodeCategory(str, Enum):
    CONTROL = "control"      # 控制流
    AI = "ai"                # AI核心
    DATA = "data"            # 数据处理
    INTEGRATION = "integration"  # 集成

class VariableDef(BaseModel):
    """变量定义"""
    name: str
    type: str  # string / number / boolean / object / array / any
    required: bool = False
    default: Any = None
    description: str = ""

class NodeConfig(BaseModel):
    """节点配置Schema"""
    node_type: str = Field(..., description="节点类型唯一标识")
    display_name: str = Field(..., description="显示名称 (支持i18n key)")
    description: str = Field("", description="节点功能描述")
    icon: str = Field("default", description="节点图标")
    category: NodeCategory = Field(..., description="节点分类")
    inputs: List[VariableDef] = Field(default_factory=list)
    outputs: List[VariableDef] = Field(default_factory=list)
    config_schema: Dict[str, Any] = Field(default_factory=dict, description="节点配置参数的JSON Schema")
    version: str = Field("1.0.0")
    author: str = Field("")
    tags: List[str] = Field(default_factory=list)

class NodeStatus(str, Enum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"
    TIMEOUT = "timeout"

class NodeResult(BaseModel):
    """节点执行结果"""
    status: NodeStatus
    outputs: Dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: int = 0
    token_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)

class BaseNode(ABC):
    """所有节点的抽象基类"""
    config: NodeConfig

    def __init__(self, node_id: str, node_config: Dict[str, Any]):
        self.node_id = node_id
        self.node_config = node_config

    @abstractmethod
    async def execute(self, variable_pool: "VariablePool") -> NodeResult:
        """节点执行入口 - 子类必须实现"""
        ...

    async def pre_execute(self, variable_pool: "VariablePool") -> Dict[str, Any]:
        """执行前钩子：输入验证、资源准备"""
        return {}

    async def post_execute(self, variable_pool: "VariablePool", result: NodeResult) -> NodeResult:
        """执行后钩子：输出验证、清理"""
        return result

    def validate_inputs(self, inputs: Dict[str, Any]) -> List[str]:
        """输入参数校验，返回错误列表"""
        errors = []
        for var_def in self.config.inputs:
            if var_def.required and var_def.name not in inputs:
                errors.append(f"Missing required input: {var_def.name}")
        return errors

    @property
    def supported_retry_exceptions(self) -> List[Type[Exception]]:
        """定义哪些异常可重试"""
        return [TimeoutError, ConnectionError]

# === 节点注册中心 ===
class NodeRegistry:
    """全局节点注册中心（单例模式）"""
    _instance: Optional["NodeRegistry"] = None
    _registry: Dict[str, Type[BaseNode]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._registry = {}
        return cls._instance

    def register(self, node_class: Type[BaseNode]) -> Type[BaseNode]:
        """注册节点类型"""
        instance = node_class.__new__(node_class)
        # 获取config而不执行完整__init__
        config = getattr(node_class, "config", None)
        if config is None:
            raise ValueError(f"Node class {node_class.__name__} must define 'config'")
        self._registry[config.node_type] = node_class
        return node_class

    def unregister(self, node_type: str) -> None:
        """注销节点类型"""
        self._registry.pop(node_type, None)

    def create_node(self, node_type: str, node_id: str, node_config: Dict[str, Any]) -> BaseNode:
        """工厂方法：根据类型创建节点实例"""
        node_class = self._registry.get(node_type)
        if not node_class:
            raise ValueError(f"Unknown node type: {node_type}")
        return node_class(node_id=node_id, node_config=node_config)

    def list_nodes(self, category: Optional[NodeCategory] = None) -> List[NodeConfig]:
        """列出所有已注册节点配置"""
        configs = []
        for node_cls in self._registry.values():
            instance = node_cls.__new__(node_cls)
            config = getattr(instance, "config", None)
            if config and (category is None or config.category == category):
                configs.append(config)
        return configs

    def get_node_config(self, node_type: str) -> Optional[NodeConfig]:
        """获取指定节点类型的配置"""
        node_class = self._registry.get(node_type)
        if node_class:
            instance = node_class.__new__(node_class)
            return getattr(instance, "config", None)
        return None

# 全局注册中心实例
node_registry = NodeRegistry()

# === 装饰器注册方式 ===
def register_node(
    node_type: str,
    display_name: str,
    category: NodeCategory,
    icon: str = "default",
    description: str = "",
    version: str = "1.0.0",
    author: str = "",
    tags: List[str] = [],
    inputs: List[VariableDef] = [],
    outputs: List[VariableDef] = [],
    config_schema: Dict[str, Any] = {},
):
    """节点注册装饰器"""
    def decorator(cls):
        cls.config = NodeConfig(
            node_type=node_type,
            display_name=display_name,
            description=description,
            icon=icon,
            category=category,
            inputs=inputs,
            outputs=outputs,
            config_schema=config_schema,
            version=version,
            author=author,
            tags=tags,
        )
        node_registry.register(cls)
        return cls
    return decorator

# === 使用示例 ===
@register_node(
    node_type="llm",
    display_name="大模型推理",
    category=NodeCategory.AI,
    icon="brain",
    description="调用大语言模型进行推理和文本生成",
    inputs=[
        VariableDef(name="prompt", type="string", required=True),
        VariableDef(name="model", type="string", required=False, default="gpt-4o"),
    ],
    outputs=[
        VariableDef(name="text", type="string"),
        VariableDef(name="token_count", type="number"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "模型名称"},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2.0},
            "max_tokens": {"type": "integer", "minimum": 1, "maximum": 128000},
            "output_schema": {"type": "object", "description": "结构化输出schema"}
        }
    }
)
class LLMNode(BaseNode):
    async def execute(self, variable_pool):
        # 1. 从variable pool读取prompt和配置
        prompt = variable_pool.resolve_template(
            self.node_config.get("prompt_template", ""),
            context={"node_id": self.node_id}
        )
        model = self.node_config.get("model", "gpt-4o")

        # 2. 通过模型路由层调用
        router = get_model_router()
        result = await router.call_llm(
            model=model,
            prompt=prompt,
            temperature=self.node_config.get("temperature", 0.7),
            max_tokens=self.node_config.get("max_tokens", 4096),
            output_schema=self.node_config.get("output_schema"),
        )

        # 3. 返回结构化结果
        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={"text": result.text, "token_count": result.token_count},
            duration_ms=result.duration_ms,
            token_count=result.token_count,
            metadata={"model": model, "finish_reason": result.finish_reason}
        )
```

### 3.3 插件系统设计

```
插件生命周期:
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  [开发] → [打包] → [上传] → [安装] → [激活] → [运行]          │
│                                    │                         │
│                                    ├── [停用] → [激活]       │
│                                    ├── [更新] → [激活]       │
│                                    └── [卸载] → [清理]       │
│                                                              │
│  每个阶段的验证:                                              │
│  - 开发: CLI工具验证 manifest.yaml 格式                       │
│  - 打包: 依赖完整性检查、代码签名                             │
│  - 上传: 病毒扫描、版本冲突检查                              │
│  - 安装: 依赖安装、沙箱测试                                  │
│  - 激活: 运行时兼容性验证、资源配置                          │
│  - 停止: 优雅退出、资源释放                                  │
└──────────────────────────────────────────────────────────────┘
```

**插件包结构：**

```
my-custom-plugin/
├── manifest.yaml              # 插件描述文件 (必需)
├── README.md                  # 插件文档
├── icon.png                   # 插件图标 (可选)
├── requirements.txt           # Python依赖 (可选)
├── main.py                    # 插件入口 (必需)
├── nodes/                     # 自定义节点
│   ├── __init__.py
│   └── custom_llm_node.py
├── tools/                     # 自定义工具
│   ├── __init__.py
│   └── api_client.py
├── models/                    # 模型提供者 (可选)
│   └── custom_model.py
├── templates/                 # 提示词模板 (可选)
│   └── prompts/
├── tests/                     # 测试文件
│   ├── __init__.py
│   └── test_nodes.py
└── examples/                  # 使用示例
    └── workflow_example.json
```

**manifest.yaml 规范：**

```yaml
# manifest.yaml - 插件描述文件
api_version: v1
kind: Plugin
metadata:
  name: my-custom-plugin
  version: 1.0.0
  display_name: 我的自定义插件
  description: 提供自定义LLM节点和API工具
  author: author-name
  license: MIT
  homepage: https://github.com/author/my-plugin
  repository: https://github.com/author/my-plugin
  tags: [llm, custom, api]

nodes:
  - type: custom_structured_llm
    display_name: 结构化LLM
    category: ai
    description: 支持严格结构化输出的LLM节点
    entry: nodes.custom_llm_node.StructuredLLMNode
    config_schema:
      type: object
      properties:
        model:
          type: string
          default: gpt-4o
        output_schema:
          type: object
          description: JSON Schema for structured output

tools:
  - name: custom_api_client
    display_name: 自定义API客户端
    description: 调用自定义外部API
    entry: tools.api_client.CustomAPIClient
    config_schema:
      type: object
      properties:
        base_url:
          type: string
          format: uri
        api_key:
          type: string
          format: password

runtime:
  language: python
  version: ">=3.11"
  sandbox: docker  # docker / process / none
  memory_limit_mb: 512
  timeout_seconds: 300
  dependencies:
    - requests>=2.28.0
    - pydantic>=2.0.0

permissions:
  network:
    - "api.example.com"  # 允许访问的域名
  filesystem:
    - "/tmp"  # 可读写的文件路径
```

---

## 四、Skills SDK — 独立技能开发框架

Skills SDK是本系统的核心创新，设计为独立于工作流引擎的、可单独使用的技能开发与执行框架。

### 4.1 设计原则

| 原则 | 说明 |
|------|------|
| **独立性** | SDK可脱离工作流引擎独立安装使用 (`pip install skills-sdk`) |
| **声明式** | 通过 manifest.yaml 声明式定义技能的接口、依赖和运行时需求 |
| **类型安全** | 输入/输出通过Pydantic schema严格验证 |
| **沙箱隔离** | 技能在Docker沙箱或进程隔离环境中执行 |
| **可组合** | 技能可以作为工作流节点、CLI命令或HTTP API三种方式调用 |

### 4.2 Skills目录结构

```
skills/                           # 技能根目录
├── skill_manifest.yaml           # 全局技能清单（自动生成）
├── document_processor/           # 技能: 文档处理
│   ├── manifest.yaml             #   技能描述文件
│   ├── handler.py                #   技能入口函数
│   ├── config.json               #   技能默认参数配置
│   ├── requirements.txt          #   技能专属依赖
│   ├── templates/                #   模板文件
│   │   └── extract_prompt.jinja2
│   ├── tests/                    #   技能测试
│   │   ├── __init__.py
│   │   ├── test_handler.py
│   │   └── fixtures/             #   测试数据
│   │       └── sample_doc.pdf
│   └── README.md                 #   技能文档
│
├── risk_analyzer/                # 技能: 风险分析
│   ├── manifest.yaml
│   ├── handler.py
│   ├── models/                   #   技能专属模型
│   │   └── risk_classifier.pkl
│   └── tests/
│       └── test_risk_analyzer.py
│
├── compliance_checker/           # 技能: 合规检查
│   ├── manifest.yaml
│   ├── handler.py
│   └── rules/                    #   合规规则库
│       ├── gdpr_rules.yaml
│       └── hipaa_rules.yaml
│
├── data_transformer/             # 技能: 数据转换
│   ├── manifest.yaml
│   └── handler.py
│
└── notification_sender/          # 技能: 通知发送
    ├── manifest.yaml
    ├── handler.py
    └── channels/                 #   通知渠道适配器
        ├── email.py
        ├── slack.py
        └── wechat.py
```

### 4.3 Skill Manifest 规范 v2

```yaml
# manifest.yaml - 技能描述文件 v2
api_version: v2
kind: Skill
metadata:
  name: document_risk_analyzer
  version: 1.2.0
  display_name: 文档风险分析
  description: >
    分析金融文档中的风险条款，支持PPM、LPA等多种文档类型。
    基于LLM+规则引擎的混合分析方案，输出结构化风险评估报告。
  author: kc-flow-team
  license: MIT
  tags: [document, risk, finance, llm]
  category: risk_analysis

# 输入定义 (JSON Schema)
inputs:
  type: object
  properties:
    document_content:
      type: string
      description: 待分析的文档文本内容
    document_type:
      type: string
      enum: [PPM, LPA, SLA, NDA]
      default: PPM
      description: 文档类型
    language:
      type: string
      enum: [zh-CN, en-US]
      default: zh-CN
    risk_threshold:
      type: number
      minimum: 0
      maximum: 1
      default: 0.7
      description: 风险告警阈值
  required: [document_content]

# 输出定义 (JSON Schema)
outputs:
  type: object
  properties:
    risk_score:
      type: number
      minimum: 0
      maximum: 1
      description: 综合风险评分
    risk_level:
      type: string
      enum: [low, medium, high, critical]
      description: 风险等级
    risk_items:
      type: array
      items:
        type: object
        properties:
          clause_ref:
            type: string
            description: 条款引用
          risk_type:
            type: string
            enum: [legal, financial, operational, compliance]
          severity:
            type: string
            enum: [low, medium, high]
          description:
            type: string
          recommendation:
            type: string
      description: 风险项列表
    summary:
      type: string
      description: 风险摘要
    analyzed_at:
      type: string
      format: date-time

# 运行时配置
runtime:
  entry_point: handler.py::analyze
  language: python
  version: ">=3.11"
  sandbox:
    type: docker
    image: python:3.11-slim
    memory_limit: 512MB
    cpu_limit: 2
    timeout_seconds: 300
    network: restricted  # none / restricted / full
    allowed_domains:
      - "api.openai.com"
      - "api.anthropic.com"
  dependencies:
    - pydantic>=2.0.0
    - httpx>=0.27.0
    - jinja2>=3.1.0

# 触发配置 (可选)
triggers:
  - event: document.uploaded
    condition: "file_type in ['pdf', 'docx'] and file_size < 50MB"
  - event: workflow.node_completed
    condition: "node_type == 'document_parser'"

# 版本兼容性
compatibility:
  sdk_version: ">=1.0.0"
  workflow_engine_version: ">=2.0.0"

# 使用示例
examples:
  - name: 基本使用
    description: 分析PPM文档的风险条款
    input:
      document_content: "{{ sample_document }}"
      document_type: PPM
    expected_output:
      risk_level: medium
```

### 4.4 Skill Handler 标准接口

```python
# handler.py - 技能入口函数标准接口
from typing import Dict, Any, Optional
from pydantic import BaseModel, Field

# === 输入输出模型 (由manifest.yaml自动生成) ===
class AnalyzeInput(BaseModel):
    document_content: str = Field(..., description="待分析的文档文本内容")
    document_type: str = Field(default="PPM", description="文档类型")
    language: str = Field(default="zh-CN", description="语言")
    risk_threshold: float = Field(default=0.7, description="风险告警阈值")

class RiskItem(BaseModel):
    clause_ref: str
    risk_type: str
    severity: str
    description: str
    recommendation: str

class AnalyzeOutput(BaseModel):
    risk_score: float
    risk_level: str
    risk_items: list
    summary: str
    analyzed_at: str

# === 技能入口函数 ===
async def analyze(
    input: AnalyzeInput,
    context: "SkillContext",  # SDK提供的执行上下文
) -> AnalyzeOutput:
    """
    文档风险分析技能入口。

    Args:
        input: 经过Pydantic验证的输入参数
        context: SDK执行上下文，提供日志、缓存、模型调用等能力

    Returns:
        结构化风险分析结果
    """
    # 1. 从context获取LLM客户端
    llm = context.get_llm_client(model="gpt-4o")

    # 2. 使用context加载模板
    prompt_template = context.load_template("extract_prompt.jinja2")

    # 3. 调用LLM进行分析
    response = await llm.chat(
        messages=[
            {"role": "system", "content": prompt_template.render(document_type=input.document_type)},
            {"role": "user", "content": input.document_content}
        ],
        temperature=0.1,
        response_format={"type": "json_object"}
    )

    # 4. 解析和验证结果
    result = AnalyzeOutput.model_validate_json(response.content)

    # 5. 使用context记录日志
    context.logger.info(f"Risk analysis completed: {result.risk_level}")

    return result

# === 技能也可以定义多个入口函数 ===
async def batch_analyze(
    input: "BatchAnalyzeInput",
    context: "SkillContext",
) -> "BatchAnalyzeOutput":
    """批量文档分析入口"""
    results = []
    for doc in input.documents:
        single_input = AnalyzeInput(
            document_content=doc.content,
            document_type=input.document_type,
        )
        result = await analyze(single_input, context)
        results.append(result)
    return BatchAnalyzeOutput(results=results)
```

### 4.5 SkillContext — SDK运行时API

```python
# Skill SDK 提供的执行上下文
class SkillContext:
    """
    技能执行上下文 - SDK提供的运行时能力。

    每个技能执行时都会获得一个SkillContext实例，
    通过它可以访问日志、缓存、LLM客户端、外部API等能力。
    """

    # === 日志 ===
    logger: logging.Logger
    """结构化日志记录器，自动关联execution_id"""

    # === LLM调用 ===
    def get_llm_client(self, model: Optional[str] = None) -> "LLMClient":
        """获取LLM客户端，自动使用上下文中配置的模型和凭证"""
        ...

    # === 模板加载 ===
    def load_template(self, template_path: str) -> "jinja2.Template":
        """加载技能目录下的Jinja2模板"""
        ...

    # === 缓存 ===
    async def cache_get(self, key: str) -> Optional[Any]:
        """从缓存中获取值 (Redis-backed)"""
        ...

    async def cache_set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """设置缓存值"""
        ...

    # === 外部HTTP调用 (受沙箱网络策略约束) ===
    async def http_request(
        self, method: str, url: str, headers: Dict = None, body: Any = None
    ) -> "HTTPResponse":
        """发起HTTP请求，受沙箱网络白名单约束"""
        ...

    # === 文件操作 (受沙箱文件系统策略约束) ===
    async def read_file(self, path: str) -> bytes:
        """读取文件 (仅限沙箱允许的路径)"""
        ...

    async def write_file(self, path: str, content: bytes) -> None:
        """写入文件 (仅限沙箱允许的路径)"""
        ...

    # === 度量上报 ===
    def record_metric(self, name: str, value: float, tags: Dict[str, str] = None) -> None:
        """上报自定义指标"""
        ...

    # === 执行信息 ===
    execution_id: str
    skill_name: str
    skill_version: str
    workflow_run_id: Optional[str]
```

### 4.6 Skill调度器

```python
class SkillScheduler:
    """
    技能调度器 - 工作流引擎与Skills SDK的桥梁。

    职责:
    1. 扫描skills/目录，加载所有技能定义
    2. 验证manifest.yaml的合法性
    3. 在工作流中调用技能
    4. 管理技能执行的沙箱环境
    5. 收集技能执行指标
    """

    def __init__(self, skills_dir: str = "skills/"):
        self.skills_dir = Path(skills_dir)
        self.skill_registry: Dict[str, SkillDefinition] = {}
        self._load_skills()

    def _load_skills(self) -> Dict[str, SkillDefinition]:
        """扫描skills目录，加载所有技能定义"""
        skills = {}
        for manifest_path in self.skills_dir.rglob("manifest.yaml"):
            try:
                skill_def = SkillDefinition.from_yaml(manifest_path)
                skills[skill_def.metadata.name] = skill_def
                logger.info(f"Loaded skill: {skill_def.metadata.name} v{skill_def.metadata.version}")
            except Exception as e:
                logger.error(f"Failed to load skill from {manifest_path}: {e}")
        return skills

    def reload(self) -> Dict[str, SkillDefinition]:
        """重新扫描并加载所有技能（热加载）"""
        self.skill_registry.clear()
        self.skill_registry = self._load_skills()
        self._generate_global_manifest()
        return self.skill_registry

    def _validate_inputs(self, skill: SkillDefinition, inputs: Dict[str, Any]) -> List[str]:
        """根据manifest中的input schema验证输入参数"""
        try:
            jsonschema.validate(inputs, skill.inputs)
            return []
        except jsonschema.ValidationError as e:
            return [str(e)]

    async def execute_skill(
        self,
        skill_name: str,
        inputs: Dict[str, Any],
        context: ExecutionContext,
        entry_point: str = "default",
    ) -> Dict[str, Any]:
        """
        在工作流中调用Skill。

        Args:
            skill_name: 技能名称 (manifest.yaml中定义的name)
            inputs: 输入参数
            context: 工作流执行上下文
            entry_point: 入口函数名 (默认使用manifest中定义的entry_point)

        Returns:
            技能执行结果
        """
        skill = self.skill_registry.get(skill_name)
        if not skill:
            raise SkillNotFoundError(f"Skill '{skill_name}' not found. Available: {list(self.skill_registry.keys())}")

        # 验证输入
        validation_errors = self._validate_inputs(skill, inputs)
        if validation_errors:
            raise SkillValidationError(f"Input validation failed: {validation_errors}")

        # 创建Skill执行上下文
        skill_context = SkillContext(
            execution_id=context.execution_id,
            skill_name=skill_name,
            skill_version=skill.metadata.version,
            workflow_run_id=context.workflow_run_id,
            sandbox_config=skill.runtime.sandbox,
        )

        # 在沙箱中执行
        try:
            result = await self._run_in_sandbox(
                skill=skill,
                entry_point=entry_point,
                inputs=inputs,
                context=skill_context,
            )
        except SkillTimeoutError:
            return {
                "status": "timeout",
                "error": f"Skill execution timed out after {skill.runtime.sandbox.timeout_seconds}s"
            }
        except SkillExecutionError as e:
            return {
                "status": "failed",
                "error": str(e),
                "traceback": e.traceback,
            }

        return {
            "status": "completed",
            "output": result,
            "metadata": {
                "skill_name": skill_name,
                "skill_version": skill.metadata.version,
                "duration_ms": skill_context._duration_ms,
                "memory_used_mb": skill_context._memory_used_mb,
            }
        }

    async def _run_in_sandbox(
        self,
        skill: SkillDefinition,
        entry_point: str,
        inputs: Dict[str, Any],
        context: SkillContext,
    ) -> Any:
        """在沙箱环境中执行技能"""
        sandbox_type = skill.runtime.sandbox.type

        if sandbox_type == "docker":
            return await self._run_in_docker_sandbox(skill, entry_point, inputs, context)
        elif sandbox_type == "process":
            return await self._run_in_process_sandbox(skill, entry_point, inputs, context)
        else:
            # 直接执行 (仅限受信任的技能)
            return await self._run_direct(skill, entry_point, inputs, context)

    def _generate_global_manifest(self) -> None:
        """生成全局 skill_manifest.yaml"""
        manifest = {
            "skills": [
                {
                    "name": s.metadata.name,
                    "version": s.metadata.version,
                    "display_name": s.metadata.display_name,
                    "category": s.metadata.category,
                    "triggers": s.triggers,
                }
                for s in self.skill_registry.values()
            ]
        }
        manifest_path = self.skills_dir / "skill_manifest.yaml"
        with open(manifest_path, "w") as f:
            yaml.dump(manifest, f)
```

### 4.7 Skill节点类型

```python
@register_node(
    node_type="skill",
    display_name="技能调用",
    category=NodeCategory.INTEGRATION,
    icon="puzzle",
    description="调用skills/目录中的技能作为工作流节点",
    inputs=[
        VariableDef(name="skill_name", type="string", required=True),
        VariableDef(name="skill_params", type="object", required=True),
    ],
    outputs=[
        VariableDef(name="output", type="object"),
        VariableDef(name="status", type="string"),
    ],
)
class SkillNode(BaseNode):
    """将skills/目录中的技能作为工作流节点直接拖拽使用"""

    async def execute(self, variable_pool: VariablePool) -> NodeResult:
        skill_name = self.node_config["skill_name"]
        skill_params = variable_pool.resolve_template(self.node_config.get("skill_params", {}))

        scheduler = get_skill_scheduler()
        result = await scheduler.execute_skill(
            skill_name=skill_name,
            inputs=skill_params,
            context=ExecutionContext(
                execution_id=variable_pool.get("sys.execution_id"),
                workflow_run_id=variable_pool.get("sys.workflow_run_id"),
            ),
        )

        if result["status"] == "completed":
            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={"output": result["output"], "status": "completed"},
                metadata=result.get("metadata", {}),
            )
        else:
            return NodeResult(
                status=NodeStatus.FAILED,
                outputs={"output": None, "status": result["status"]},
                error=result.get("error"),
            )
```

### 4.8 Skills CLI工具

```bash
# Skills CLI - 独立的命令行工具
pip install skills-sdk[cli]

# 创建新技能
skills-cli init my-custom-skill --template llm

# 验证技能完整性
skills-cli validate ./my-custom-skill

# 打包技能
skills-cli package ./my-custom-skill --output my-custom-skill-1.0.0.skill

# 本地运行技能
skills-cli run document_risk_analyzer \
    --input '{"document_content": "...", "document_type": "PPM"}' \
    --skills-dir ./skills

# 运行技能测试
skills-cli test ./my-custom-skill

# 发布技能到注册中心
skills-cli publish ./my-custom-skill-1.0.0.skill \
    --registry https://skills-registry.example.com

# 列出已安装技能
skills-cli list --skills-dir ./skills

# 查看技能详情
skills-cli info document_risk_analyzer --skills-dir ./skills
```

---

## 五、安全性设计

### 5.1 多层次安全防护体系

```
安全防护层次:

┌─────────────────────────────────────────────────────────────┐
│ Layer 1: 网络边界安全                                        │
│  - TLS 1.3 端到端加密                                        │
│  - WAF (Web应用防火墙)                                       │
│  - DDoS防护 (速率限制 + IP黑名单)                             │
│  - API强制HTTPS, HTTP自动重定向                              │
├─────────────────────────────────────────────────────────────┤
│ Layer 2: 认证层                                              │
│  - OAuth 2.0 + OIDC                                         │
│  - API-Key (Bearer Token)                                   │
│  - SSO/SAML 集成 (企业版)                                    │
│  - MFA 多因素认证 (TOTP/FIDO2)                               │
│  - 会话管理 (JWT + 刷新令牌)                                  │
├─────────────────────────────────────────────────────────────┤
│ Layer 3: 授权层                                              │
│  - RBAC 角色权限                                             │
│  - ABAC 属性权限 (Workspace级隔离)                           │
│  - 资源级 ACL                                               │
│  - API端点级权限控制                                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 4: 应用安全层                                          │
│  - 输入验证与净化 (防XSS/SQL注入/命令注入)                    │
│  - Prompt注入检测与防护                                       │
│  - 参数化查询 (SQLAlchemy ORM)                               │
│  - CORS策略白名单                                           │
│  - CSP (内容安全策略)                                        │
├─────────────────────────────────────────────────────────────┤
│ Layer 5: 代码执行安全                                        │
│  - Docker沙箱隔离 (gVisor/kata可选)                          │
│  - 系统调用白名单 (seccomp profile)                          │
│  - 网络访问控制 (仅允许白名单域名)                            │
│  - 资源配额限制 (CPU/内存/磁盘/IO)                            │
│  - 进程隔离 (每个代码执行在独立容器中)                         │
├─────────────────────────────────────────────────────────────┤
│ Layer 6: 数据安全层                                          │
│  - 静态加密: AES-256-GCM                                     │
│  - 传输加密: TLS 1.3                                         │
│  - 敏感凭证托管: HashiCorp Vault / KMS                        │
│  - API-Key 哈希存储 (bcrypt)                                 │
│  - PII数据脱敏 (可配置脱敏规则)                                │
│  - 审计日志全记录 (不可篡改)                                   │
├─────────────────────────────────────────────────────────────┤
│ Layer 7: 限流与防护                                          │
│  - 用户级: 每分钟/每小时请求限制                              │
│  - 应用级: 每工作流/每模型的调用限制                          │
│  - API级: 每个端点的独立限流                                  │
│  - 模型调用: Token消耗配额                                    │
│  - 指数退避重试, 令牌桶算法                                   │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 权限模型

```
权限模型 (RBAC + ABAC 混合)

系统级权限 (System Role):
├── super_admin: 全局管理权限
│   ├── 管理所有工作空间
│   ├── 管理所有用户
│   ├── 系统配置管理
│   └── 查看全局审计日志
├── admin: 工作空间管理权限
│   ├── 管理工作空间成员
│   ├── 管理计费和使用配额
│   └── 查看工作空间审计日志
└── auditor: 审计日志查看权限
    └── 只读访问审计日志

工作空间级权限 (Workspace Role):
├── workspace_owner: 空间所有者
│   ├── 管理工作空间设置
│   ├── 管理成员和权限
│   └── 删除工作空间
├── developer: 开发者
│   ├── 创建/编辑/删除工作流
│   ├── 发布工作流到各环境
│   ├── 安装/配置插件
│   ├── 管理知识库
│   └── 执行工作流
└── viewer: 查看者
    ├── 查看工作流定义
    ├── 查看执行历史
    └── 查看监控仪表盘

资源级权限 (Resource ACL):
├── workflow: {create, read, update, delete, publish, execute}
├── node_plugin: {install, configure, execute, uninstall}
├── knowledge_base: {upload, query, manage, delete}
├── api_key: {create, revoke, rotate}
├── skill: {register, execute, configure}
└── model: {configure, use}
```

### 5.3 API-Key管理

```
API-Key生命周期:
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  [创建] → [激活] → [使用] → [轮换] → [撤销]                  │
│    │                  │         │         │                  │
│    │                  │         │         └── 永久删除       │
│    │                  │         └── 旧Key保留宽限期后失效     │
│    │                  └── 速率限制 + 使用审计                 │
│    └── 生成后仅显示一次完整Key                                │
│                                                             │
│ API-Key属性:                                                 │
│ - key_id: 唯一标识 (公开)                                     │
│ - key_prefix: Key前缀 (用于识别，如 sk-abc...xyz)            │
│ - key_hash: bcrypt哈希值 (存储)                              │
│ - permissions: 关联的权限范围                                 │
│ - rate_limit: 独立的速率限制配置                              │
│ - expires_at: 过期时间 (可选)                                 │
│ - last_used_at: 最后使用时间                                  │
│ - created_by: 创建者                                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、工作流版本管理

### 6.1 版本控制方案

```
Git式版本控制模型:

版本号规则: MAJOR.MINOR.PATCH (语义化版本)
  - MAJOR: 不兼容的节点或API变更
  - MINOR: 向后兼容的新功能 (新增节点、分支)
  - PATCH: 向后兼容的修复 (参数调整、Prompt优化)

版本生命周期:
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│  [Draft] ──→ [Published] ──→ [Deprecated] ──→ [Archived]    │
│     │            │               │                           │
│     │            │               └── 不再推荐使用              │
│     │            └── 不可修改，生成版本快照                    │
│     └── 可自由编辑，不计入版本历史                            │
│                                                              │
│  环境提升流程:                                                │
│  development ──→ staging ──→ production                      │
│       │              │            │                           │
│       └── 自动测试   └── 人工审批 └── 灰度发布                │
└──────────────────────────────────────────────────────────────┘
```

### 6.2 数据模型

```sql
-- 工作流主表
CREATE TABLE workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE,
    current_version_id UUID,
    status VARCHAR(20) DEFAULT 'draft',  -- draft / active / archived
    tags TEXT[],                          -- PostgreSQL数组类型
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    deleted_at TIMESTAMP WITH TIME ZONE  -- 软删除
);

-- 工作流版本表
CREATE TABLE workflow_versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL REFERENCES workflows(id) ON DELETE CASCADE,
    version VARCHAR(20) NOT NULL,         -- 语义化版本号 1.0.0
    status VARCHAR(20) NOT NULL DEFAULT 'draft',  -- draft / published / deprecated / archived
    dsl_definition JSONB NOT NULL,        -- 完整DSL定义
    dsl_hash VARCHAR(64),                 -- DSL内容的SHA-256哈希，用于快速比较
    changelog TEXT,                       -- 变更说明
    environment VARCHAR(20),              -- development / staging / production
    published_at TIMESTAMP WITH TIME ZONE,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(workflow_id, version)
);

-- 版本差异表
CREATE TABLE workflow_version_diffs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    from_version_id UUID NOT NULL REFERENCES workflow_versions(id),
    to_version_id UUID NOT NULL REFERENCES workflow_versions(id),
    diff_type VARCHAR(20) NOT NULL,       -- nodes_added / nodes_removed / nodes_modified / edges_changed / config_changed
    diff_detail JSONB NOT NULL,           -- 具体差异内容
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 执行记录表
CREATE TABLE workflow_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_version_id UUID NOT NULL REFERENCES workflow_versions(id),
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    status VARCHAR(20) NOT NULL,          -- queued / running / success / failed / timeout / cancelled
    trigger_type VARCHAR(20),             -- api / schedule / webhook / manual
    inputs JSONB,
    outputs JSONB,
    node_executions JSONB,                -- 各节点执行详情
    variable_pool_snapshot JSONB,         -- Variable Pool的最终快照
    error_message TEXT,
    error_node_id VARCHAR(100),
    total_tokens INTEGER DEFAULT 0,
    total_api_calls INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    created_by UUID REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 节点执行详情表 (用于复杂查询和分析)
CREATE TABLE node_executions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    node_id VARCHAR(100) NOT NULL,
    node_type VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,          -- pending / running / succeeded / failed / skipped / timeout
    inputs JSONB,
    outputs JSONB,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE,
    duration_ms INTEGER,
    token_count INTEGER DEFAULT 0,
    model_name VARCHAR(100),              -- 仅LLM节点
    prompt_text TEXT,                     -- 仅LLM节点 (可配置是否存储)
    response_text TEXT                    -- 仅LLM节点 (可配置是否存储)
);

-- 检查点表
CREATE TABLE workflow_checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id UUID NOT NULL REFERENCES workflow_executions(id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,     -- 检查点序号
    graph_state JSONB NOT NULL,           -- 节点状态 + 就绪队列
    variable_pool_snapshot JSONB NOT NULL, -- Variable Pool快照
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 索引设计
CREATE INDEX idx_workflows_workspace ON workflows(workspace_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_workflow_versions_workflow ON workflow_versions(workflow_id, version);
CREATE INDEX idx_workflow_versions_env ON workflow_versions(workflow_id, environment);
CREATE INDEX idx_workflow_executions_workflow ON workflow_executions(workflow_id, created_at DESC);
CREATE INDEX idx_workflow_executions_status ON workflow_executions(status) WHERE status IN ('running', 'queued');
CREATE INDEX idx_node_executions_execution ON node_executions(execution_id, node_id);
CREATE INDEX idx_workflow_checkpoints_execution ON workflow_checkpoints(execution_id, sequence_number DESC);
```

### 6.3 版本管理操作

```
版本回滚流程:
1. 用户选择目标版本
2. 系统验证目标版本存在且状态为 published
3. 创建新版本 (基于目标版本的DSL，递增PATCH版本号)
4. DSL复制目标版本的完整定义
5. 自动生成changelog: "Rollback to version X.Y.Z"
6. 新版本状态设为 draft，需重新发布

环境提升流程:
1. 在development环境测试通过
2. 发布到staging: POST /workflows/{id}/promote (target_env=staging)
3. staging环境运行集成测试
4. 审批通过: POST /workflows/{id}/promote (target_env=production)
5. production环境自动灰度发布 (10% → 50% → 100%)
```

---

## 七、监控与可观测性

### 7.1 监控指标体系

| 监控维度 | 核心指标 | 采集方式 | 告警阈值 |
|---------|---------|---------|---------|
| **执行性能** | 工作流总耗时、节点耗时分布、P50/P95/P99延迟 | Prometheus Histogram | P99 > 10s |
| **吞吐量** | QPS、并发执行数、任务队列深度、Worker利用率 | Prometheus Gauge | 队列深度 > 100 |
| **成功率** | 工作流成功率、节点成功率、模型调用成功率 | Prometheus Counter | 成功率 < 95% |
| **资源消耗** | CPU/内存使用率、Token消耗量、API调用次数 | Prometheus + cAdvisor | CPU > 80% |
| **模型调用** | 各模型QPS、Token消耗分布、模型错误率 | Custom Metrics | 模型错误率 > 5% |
| **业务指标** | 用户数、工作流数、执行次数、技能调用次数 | Application Metrics | 按业务需求 |

### 7.2 执行追踪

```python
# 每个工作流执行记录包含完整的节点级追踪信息
execution_trace = {
    "execution_id": "exec_uuid",
    "workflow_id": "wf_uuid",
    "workflow_version": "1.2.0",
    "status": "success",
    "total_duration_ms": 5200,
    "total_tokens": 3456,
    "total_api_calls": 3,

    "nodes": [
        {
            "node_id": "node_start",
            "node_type": "start",
            "status": "succeeded",
            "duration_ms": 5,
            "inputs": {"query": "分析这份合同的风险条款"},
            "outputs": {"query": "分析这份合同的风险条款"},
        },
        {
            "node_id": "node_llm_extract",
            "node_type": "llm",
            "status": "succeeded",
            "duration_ms": 2300,
            "inputs": {
                "prompt": "从以下文档中提取关键条款...",
                "model": "gpt-4o",
                "temperature": 0.1,
            },
            "outputs": {
                "text": "根据分析，该合同存在...",
                "clauses": [...],
                "overall_risk": "high",
            },
            "token_count": 1234,
            "model_name": "gpt-4o",
            "prompt_hash": "sha256:abc123...",  # Prompt内容哈希，便于去重和审计
            "retry_count": 0,
        },
        {
            "node_id": "node_condition",
            "node_type": "condition",
            "status": "succeeded",
            "duration_ms": 2,
            "matched_condition": 0,
            "matched_target": "node_alert",
        },
        {
            "node_id": "node_alert",
            "node_type": "skill",
            "status": "succeeded",
            "duration_ms": 800,
            "skill_name": "risk_alert",
            "skill_version": "1.0.0",
        },
        {
            "node_id": "node_report",
            "node_type": "template",
            "status": "skipped",
            "skip_reason": "Condition branch not taken",
        },
        {
            "node_id": "node_end",
            "node_type": "end",
            "status": "succeeded",
            "duration_ms": 3,
        },
    ],

    # LLM调用的完整记录 (可用于审计和优化)
    "llm_calls": [
        {
            "node_id": "node_llm_extract",
            "model": "gpt-4o",
            "prompt_text": "从以下文档中提取关键条款信息：\n\n...(完整Prompt)",
            "response_text": "根据分析，该合同存在以下风险：\n\n...(完整Response)",
            "input_tokens": 856,
            "output_tokens": 378,
            "duration_ms": 2300,
            "finish_reason": "stop",
        }
    ],

    # 检查点记录
    "checkpoints": [
        {"sequence": 1, "after_node": "node_start", "timestamp": "..."},
        {"sequence": 2, "after_node": "node_llm_extract", "timestamp": "..."},
    ],
}
```

### 7.3 分布式追踪（OpenTelemetry集成）

```
追踪上下文传播:
┌─────────────────────────────────────────────────────────────┐
│                      Trace: workflow-execution               │
│                                                             │
│  Span: workflow.total (5200ms)                              │
│  ├── Span: node_start (5ms)                                 │
│  │   └── Event: variables_injected                          │
│  ├── Span: node_llm_extract (2300ms)                        │
│  │   ├── Span: prompt_resolution (15ms)                     │
│  │   ├── Span: llm_api_call (2250ms)                        │
│  │   │   ├── Attribute: model = "gpt-4o"                    │
│  │   │   ├── Attribute: input_tokens = 856                  │
│  │   │   ├── Attribute: output_tokens = 378                 │
│  │   │   └── Event: first_token_received_at (450ms)         │
│  │   └── Span: output_validation (10ms)                     │
│  ├── Span: node_condition (2ms)                             │
│  │   └── Event: condition_0_matched                        │
│  ├── Span: node_alert (800ms)                               │
│  │   ├── Span: skill_loading (50ms)                         │
│  │   ├── Span: skill_execution (700ms)                      │
│  │   └── Span: channel_notification (45ms)                  │
│  └── Span: node_end (3ms)                                   │
│      └── Event: result_compiled                             │
└─────────────────────────────────────────────────────────────┘
```

### 7.4 告警规则

```yaml
# Prometheus告警规则
groups:
  - name: workflow_alerts
    rules:
      - alert: WorkflowFailureRateHigh
        expr: |
          rate(workflow_executions_failed_total[5m]) /
          rate(workflow_executions_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "工作流失败率超过5%"
          description: "过去5分钟内工作流失败率为 {{ $value | humanizePercentage }}"

      - alert: WorkflowP99LatencyHigh
        expr: |
          histogram_quantile(0.99,
            rate(workflow_execution_duration_seconds_bucket[5m])
          ) > 10
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "工作流P99延迟超过10秒"

      - alert: LLMCallErrorRateHigh
        expr: |
          rate(llm_call_errors_total[5m]) /
          rate(llm_call_total[5m]) > 0.03
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "LLM调用错误率超过3%"
```

---

## 八、API接口规范

### 8.1 统一API设计约定

**基础URL:** `https://{host}/api/v1`

**鉴权方式:**
```
Authorization: Bearer {API_KEY}
X-Request-ID: {UUID}  # 请求追踪ID (可选，未提供时自动生成)
```

**统一响应格式:**
```json
{
    "code": 0,
    "message": "success",
    "data": {},
    "request_id": "req_a1b2c3d4",
    "timestamp": "2026-05-02T10:30:00Z"
}
```

**统一错误响应:**
```json
{
    "code": 40001,
    "message": "节点配置校验失败：缺少必需参数 'document_url'",
    "errors": [
        {
            "field": "nodes.0.data.variables.document_url",
            "reason": "required_field_missing",
            "detail": "Start节点的 'document_url' 参数为必需项"
        }
    ],
    "request_id": "req_a1b2c3d4",
    "timestamp": "2026-05-02T10:30:00Z"
}
```

**分页响应:**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "items": [...],
        "pagination": {
            "page": 1,
            "page_size": 20,
            "total": 156,
            "total_pages": 8,
            "has_next": true,
            "has_prev": false
        }
    },
    "request_id": "req_a1b2c3d4",
    "timestamp": "2026-05-02T10:30:00Z"
}
```

### 8.2 工作流管理API

| 方法 | 路径 | 说明 | 请求体/参数 |
|------|------|------|-----------|
| POST | `/workflows` | 创建工作流 | `{name, description, workspace_id}` |
| GET | `/workflows/{id}` | 获取工作流详情 | `?include_versions=true` |
| PUT | `/workflows/{id}` | 更新工作流 | `{name, description, dsl_definition, changelog}` |
| DELETE | `/workflows/{id}` | 删除工作流 (软删除) | - |
| GET | `/workflows` | 列出工作流 | `?workspace_id=&status=&page=&page_size=&sort_by=&order=` |
| POST | `/workflows/{id}/publish` | 发布工作流 | `{version, environment, changelog}` |
| POST | `/workflows/{id}/rollback` | 回滚到指定版本 | `{target_version, reason}` |
| POST | `/workflows/{id}/promote` | 提升到目标环境 | `{target_environment, approval_id?}` |
| POST | `/workflows/{id}/clone` | 克隆工作流 | `{new_name, workspace_id?}` |
| GET | `/workflows/{id}/versions` | 获取版本列表 | `?status=&environment=&page=&page_size=` |
| GET | `/workflows/{id}/versions/{version_id}` | 获取版本详情 | - |
| GET | `/workflows/{id}/versions/{v1}/diff/{v2}` | 比较两个版本 | - |

**创建工作流请求示例:**
```json
POST /api/v1/workflows
{
    "name": "文档智能审阅",
    "description": "自动化金融文档审核流程",
    "workspace_id": "ws_a1b2c3d4",
    "dsl_definition": { /* 完整的Workflow DSL */ },
    "tags": ["document", "finance", "review"]
}
```

**创建工作流响应示例:**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "id": "wf_a1b2c3d4",
        "name": "文档智能审阅",
        "version": "0.0.1",
        "status": "draft",
        "created_at": "2026-05-02T10:30:00Z"
    },
    "request_id": "req_a1b2c3d4",
    "timestamp": "2026-05-02T10:30:00Z"
}
```

### 8.3 工作流执行API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/workflows/{id}/run` | 同步执行工作流 |
| POST | `/workflows/{id}/run-async` | 异步执行工作流 |
| POST | `/workflows/{id}/run-stream` | 流式执行 (SSE) |
| GET | `/workflows/{id}/executions` | 获取执行历史 |
| GET | `/workflows/{id}/executions/{exec_id}` | 获取执行详情 |
| GET | `/workflows/{id}/executions/{exec_id}/status` | 获取执行状态 (轻量) |
| POST | `/workflows/{id}/executions/{exec_id}/cancel` | 取消执行 |
| POST | `/workflows/{id}/executions/{exec_id}/retry` | 重试失败执行 |
| GET | `/workflows/{id}/executions/{exec_id}/trace` | 获取执行追踪 |
| GET | `/workflows/{id}/executions/{exec_id}/checkpoints` | 获取检查点列表 |

**同步执行请求:**
```json
POST /api/v1/workflows/wf_a1b2c3d4/run
{
    "inputs": {
        "document_url": "https://storage.example.com/docs/contract_2024.pdf",
        "review_type": "PPM",
        "language": "zh-CN"
    },
    "version": "1.2.0",
    "timeout": 600
}
```

**同步执行响应:**
```json
{
    "code": 0,
    "message": "success",
    "data": {
        "execution_id": "exec_xyz789",
        "status": "success",
        "outputs": {
            "result": "# 文档审阅报告\n\n...",
            "risk_level": "high",
            "execution_summary": {
                "total_duration_ms": 5200,
                "nodes_executed": 5,
                "nodes_skipped": 1,
                "total_tokens": 3456,
                "total_api_calls": 3
            }
        },
        "started_at": "2026-05-02T10:30:00Z",
        "completed_at": "2026-05-02T10:30:05Z",
        "duration_ms": 5200
    },
    "request_id": "req_a1b2c3d4",
    "timestamp": "2026-05-02T10:30:05Z"
}
```

### 8.4 流式响应 (SSE)

```
请求:
POST /api/v1/workflows/wf_a1b2c3d4/run-stream
Content-Type: application/json
Accept: text/event-stream

{
    "inputs": {"document_url": "...", "review_type": "PPM"},
    "version": "1.2.0"
}

SSE响应流:
event: workflow_started
data: {"execution_id": "exec_xyz789", "workflow_id": "wf_a1b2c3d4", "version": "1.2.0", "timestamp": "2026-05-02T10:30:00Z"}

event: node_started
data: {"node_id": "node_start", "node_type": "start", "display_name": "开始", "index": 0, "timestamp": "2026-05-02T10:30:00.100Z"}

event: node_completed
data: {"node_id": "node_start", "node_type": "start", "status": "succeeded", "duration_ms": 5, "timestamp": "2026-05-02T10:30:00.105Z"}

event: node_started
data: {"node_id": "node_llm_extract", "node_type": "llm", "display_name": "大模型提取", "index": 1, "timestamp": "2026-05-02T10:30:00.150Z"}

event: node_streaming
data: {"node_id": "node_llm_extract", "text_chunk": "根据分析，该合同存在以下风险条款...", "token_count": 150, "timestamp": "2026-05-02T10:30:01.500Z"}

event: node_streaming
data: {"node_id": "node_llm_extract", "text_chunk": "\n1. 违约责任条款不明确...", "token_count": 300, "timestamp": "2026-05-02T10:30:02.200Z"}

event: node_completed
data: {"node_id": "node_llm_extract", "node_type": "llm", "status": "succeeded", "duration_ms": 2300, "token_count": 1234, "timestamp": "2026-05-02T10:30:02.450Z"}

event: node_started
data: {"node_id": "node_condition", "node_type": "condition", "display_name": "风险判断", "index": 2, "timestamp": "2026-05-02T10:30:02.500Z"}

event: node_completed
data: {"node_id": "node_condition", "node_type": "condition", "status": "succeeded", "matched_condition": 0, "duration_ms": 2, "timestamp": "2026-05-02T10:30:02.502Z"}

event: node_started
data: {"node_id": "node_alert", "node_type": "skill", "display_name": "风险告警", "index": 3, "timestamp": "2026-05-02T10:30:02.550Z"}

event: node_completed
data: {"node_id": "node_alert", "node_type": "skill", "status": "succeeded", "duration_ms": 800, "timestamp": "2026-05-02T10:30:03.350Z"}

event: node_skipped
data: {"node_id": "node_report", "node_type": "template", "status": "skipped", "reason": "Condition branch not taken", "timestamp": "2026-05-02T10:30:03.360Z"}

event: workflow_completed
data: {"execution_id": "exec_xyz789", "status": "success", "total_duration_ms": 5200, "total_tokens": 3456, "outputs": {...}, "timestamp": "2026-05-02T10:30:05.200Z"}

event: ping
data: {"timestamp": "2026-05-02T10:30:30.000Z"}
```

### 8.5 节点管理API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/nodes` | 获取可用节点列表 |
| GET | `/nodes/categories` | 获取节点分类体系 |
| GET | `/nodes/{node_type}` | 获取节点类型详情 |
| POST | `/nodes/plugins` | 注册/安装自定义节点插件 |
| DELETE | `/nodes/plugins/{plugin_id}` | 卸载节点插件 |
| PUT | `/nodes/plugins/{plugin_id}` | 更新插件配置 |
| POST | `/nodes/plugins/{plugin_id}/toggle` | 启用/停用插件 |

### 8.6 模型管理API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/models` | 获取可用模型列表 |
| POST | `/models` | 注册自定义模型提供者 |
| PUT | `/models/{provider_id}/credentials` | 更新模型凭证 |
| DELETE | `/models/{provider_id}` | 删除模型提供者 |
| GET | `/models/{provider_id}/usage` | 获取模型使用统计 |

### 8.7 Skill集成API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/skills` | 获取已注册技能列表 |
| POST | `/skills/reload` | 重新扫描skills/目录加载技能 |
| GET | `/skills/{skill_name}` | 获取技能详情 |
| POST | `/skills/{skill_name}/test` | 测试技能执行 |
| POST | `/skills/validate` | 验证技能manifest合法性 |
| POST | `/skills/package` | 打包技能为可分发包 |
| POST | `/skills/install` | 从分发包安装技能 |

### 8.8 WebSocket事件

```
连接: wss://{host}/ws/workflows/{workflow_id}/executions/{execution_id}

客户端 → 服务端:
{
    "type": "subscribe",
    "events": ["node_started", "node_completed", "node_streaming", "workflow_completed", "error"]
}

{
    "type": "cancel",
    "execution_id": "exec_xyz789"
}

服务端 → 客户端:
# 与SSE事件格式相同，使用JSON消息传递
{
    "type": "node_completed",
    "data": {
        "node_id": "node_llm_extract",
        "node_type": "llm",
        "status": "succeeded",
        "duration_ms": 2300,
        "token_count": 1234
    }
}
```

### 8.9 错误码目录

| 错误码 | HTTP状态码 | 说明 |
|--------|-----------|------|
| 0 | 200 | 成功 |
| 40001 | 400 | 参数校验失败 |
| 40002 | 400 | DSL格式验证失败 |
| 40003 | 400 | 图结构验证失败 (环路/不可达节点) |
| 40004 | 400 | 变量引用无效 |
| 40005 | 400 | 节点配置不合法 |
| 40101 | 401 | 未提供认证凭证 |
| 40102 | 401 | API-Key无效或已过期 |
| 40301 | 403 | 无权限访问该资源 |
| 40302 | 403 | 超过使用配额限制 |
| 40401 | 404 | 工作流不存在 |
| 40402 | 404 | 执行记录不存在 |
| 40403 | 404 | 节点类型不存在 |
| 40404 | 404 | 技能不存在 |
| 40801 | 408 | 工作流执行超时 |
| 40901 | 409 | 版本冲突 (同时编辑) |
| 42201 | 422 | 工作流状态不允许此操作 |
| 42901 | 429 | 请求频率超限 |
| 42902 | 429 | Token消耗超限 |
| 50001 | 500 | 内部服务错误 |
| 50002 | 500 | 模型调用失败 |
| 50003 | 500 | 技能执行失败 |
| 50201 | 502 | 模型提供者不可用 |
| 50301 | 503 | 服务暂时不可用 |
| 50302 | 503 | Worker队列已满 |

---

## 九、错误处理与恢复机制

### 9.1 错误分类体系

```
错误分类层次:

ErrorCategory (顶层分类)
├── ValidationError (验证错误 - 400)
│   ├── DSLValidationError: DSL格式/结构验证失败
│   ├── GraphValidationError: 图结构验证失败 (环路/不可达)
│   ├── VariableValidationError: 变量引用/类型验证失败
│   └── InputValidationError: 用户输入参数验证失败
│
├── ExecutionError (执行错误 - 500)
│   ├── NodeExecutionError: 节点执行失败
│   │   ├── LLMCallError: 模型调用失败 (可重试)
│   │   ├── SkillExecutionError: 技能执行失败
│   │   └── CodeExecutionError: 代码执行失败
│   ├── WorkflowTimeoutError: 工作流超时
│   ├── ResourceExhaustedError: 资源不足
│   └── ExternalServiceError: 外部服务故障 (可重试)
│
├── SystemError (系统错误 - 500)
│   ├── DatabaseError: 数据库错误
│   ├── QueueError: 消息队列错误
│   └── ConfigurationError: 配置错误
│
└── AuthError (认证授权错误 - 401/403)
    ├── AuthenticationError: 认证失败
    ├── AuthorizationError: 授权失败
    └── QuotaExceededError: 配额超限
```

### 9.2 重试与降级策略

```python
from enum import Enum
from dataclasses import dataclass
from typing import List, Type, Optional
import asyncio

class FallbackStrategy(str, Enum):
    SKIP_NODE = "skip_node"           # 跳过失败节点，继续执行
    USE_DEFAULT = "use_default"       # 使用默认值
    CALL_BACKUP = "call_backup"       # 调用备用模型/服务
    MANUAL = "manual"                 # 转人工处理
    RETRY_WITH_BACKOFF = "retry"      # 指数退避重试

@dataclass
class RetryPolicy:
    """重试策略配置"""
    max_retries: int = 3
    backoff_factor: float = 2.0         # 指数退避倍数
    initial_delay_ms: int = 1000        # 初始延迟
    max_delay_ms: int = 30000           # 最大延迟
    jitter: bool = True                 # 是否添加随机抖动
    retryable_exceptions: List[Type[Exception]] = None  # 可重试的异常类型

    def get_delay(self, attempt: int) -> int:
        """计算第N次重试的延迟时间"""
        delay = self.initial_delay_ms * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay_ms)
        if self.jitter:
            delay = delay * (0.75 + random.random() * 0.5)  # 75%-125%
        return int(delay)

@dataclass
class ErrorHandlingConfig:
    """节点级错误处理配置"""
    retry_policy: RetryPolicy = RetryPolicy()
    fallback_strategy: FallbackStrategy = FallbackStrategy.RETRY_WITH_BACKOFF
    fallback_model: Optional[str] = None     # 备用模型名称
    fallback_default_value: Any = None       # 默认值
    alert_on_failure: bool = True            # 失败时是否告警

# === 执行引擎中的重试逻辑 ===
async def execute_node_with_retry(
    node: BaseNode,
    variable_pool: VariablePool,
    error_config: ErrorHandlingConfig,
) -> NodeResult:
    """带重试和降级的节点执行包装器"""
    last_error = None

    for attempt in range(error_config.retry_policy.max_retries + 1):
        try:
            result = await node.execute(variable_pool)
            if result.status == NodeStatus.SUCCEEDED:
                return result
            last_error = Exception(result.error)
        except tuple(error_config.retry_policy.retryable_exceptions or [Exception]) as e:
            last_error = e

            if attempt < error_config.retry_policy.max_retries:
                delay = error_config.retry_policy.get_delay(attempt)
                logger.warning(
                    f"Node {node.node_id} failed (attempt {attempt+1}/{error_config.retry_policy.max_retries+1}), "
                    f"retrying in {delay}ms: {e}"
                )
                await asyncio.sleep(delay / 1000)
                continue
        except Exception as e:
            # 不可重试的异常，直接进入降级处理
            last_error = e
            break

    # 所有重试均失败，执行降级策略
    return await apply_fallback(node, variable_pool, error_config, last_error)

async def apply_fallback(
    node: BaseNode,
    variable_pool: VariablePool,
    error_config: ErrorHandlingConfig,
    error: Exception,
) -> NodeResult:
    """执行降级策略"""
    strategy = error_config.fallback_strategy

    if strategy == FallbackStrategy.SKIP_NODE:
        return NodeResult(
            status=NodeStatus.SKIPPED,
            error=f"Node skipped due to: {error}",
        )

    elif strategy == FallbackStrategy.USE_DEFAULT:
        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={"text": error_config.fallback_default_value},
            error=f"Used default value due to: {error}",
        )

    elif strategy == FallbackStrategy.CALL_BACKUP:
        if error_config.fallback_model:
            backup_config = {**node.node_config, "model": error_config.fallback_model}
            # 使用备用模型重新执行
            try:
                return await node.__class__(
                    node_id=node.node_id,
                    node_config=backup_config,
                ).execute(variable_pool)
            except Exception as backup_error:
                return NodeResult(
                    status=NodeStatus.FAILED,
                    error=f"Both primary and backup failed. Primary: {error}, Backup: {backup_error}",
                )

    # 默认: 报告失败
    return NodeResult(
        status=NodeStatus.FAILED,
        error=str(error),
    )
```

### 9.3 熔断器模式

```python
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum

class CircuitState(str, Enum):
    CLOSED = "closed"           # 正常状态，请求通过
    OPEN = "open"               # 熔断状态，直接拒绝
    HALF_OPEN = "half_open"     # 半开状态，试探性放行

@dataclass
class CircuitBreaker:
    """
    熔断器 - 保护工作流免于级联故障。

    针对LLM调用、HTTP请求等外部依赖使用。
    """
    name: str                           # 熔断器名称 (如 "llm:gpt-4o")
    failure_threshold: int = 5          # 连续失败次数阈值
    recovery_timeout_seconds: int = 60  # 恢复超时 (熔断后多久进入半开)
    half_open_max_requests: int = 3     # 半开状态允许的试探请求数

    _state: CircuitState = CircuitState.CLOSED
    _failure_count: int = 0
    _last_failure_time: Optional[datetime] = None
    _half_open_requests: int = 0

    async def call(self, coro) -> Any:
        """通过熔断器执行异步调用"""
        if self._state == CircuitState.OPEN:
            if self._should_attempt_recovery():
                self._state = CircuitState.HALF_OPEN
                self._half_open_requests = 0
                logger.info(f"Circuit breaker '{self.name}' entering HALF_OPEN state")
            else:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is OPEN. "
                    f"Retry after {self._recovery_seconds_remaining()}s"
                )

        if self._state == CircuitState.HALF_OPEN:
            if self._half_open_requests >= self.half_open_max_requests:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' HALF_OPEN limit reached"
                )
            self._half_open_requests += 1

        try:
            result = await coro
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e

    def _on_success(self):
        self._state = CircuitState.CLOSED
        self._failure_count = 0

    def _on_failure(self):
        self._failure_count += 1
        self._last_failure_time = datetime.now()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                f"Circuit breaker '{self.name}' OPEN after "
                f"{self._failure_count} consecutive failures"
            )

    def _should_attempt_recovery(self) -> bool:
        if self._last_failure_time is None:
            return True
        elapsed = (datetime.now() - self._last_failure_time).total_seconds()
        return elapsed >= self.recovery_timeout_seconds
```

### 9.4 死信队列

```
死信队列处理流程:

执行失败后的处理路径:
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  节点执行失败                                            │
│      │                                                  │
│      ├── 重试策略: 可重试? ──是──→ 指数退避重试 (最多3次)  │
│      │        │                        │                │
│      │       否                        ├── 成功 → 继续   │
│      │        │                        └── 失败 ↓        │
│      │        ↓                                         │
│      ├── 降级策略:                                       │
│      │   ├── SKIP_NODE → 跳过, 使用默认值                │
│      │   ├── CALL_BACKUP → 切换到备用模型/服务           │
│      │   └── MANUAL → 进入死信队列                       │
│      │                                                  │
│      └── 死信队列 ──→ 人工审查 ──→ 决策:                  │
│           │                ├── 修复后重试                  │
│           │                ├── 修改配置后重新执行            │
│           │                └── 确认失败, 通知用户           │
│                                                         │
│  死信队列记录格式:                                        │
│  {                                                      │
│    "id": "dlq_uuid",                                    │
│    "execution_id": "exec_uuid",                         │
│    "node_id": "node_llm_extract",                       │
│    "error": "LLM call failed after 3 retries",          │
│    "inputs": {...},                                     │
│    "context": {...},                                    │
│    "created_at": "...",                                 │
│    "status": "pending_review"                           │
│  }                                                      │
└─────────────────────────────────────────────────────────┘
```

---

## 十、部署架构

### 10.1 Docker Compose部署（开发/小规模生产）

```yaml
# docker-compose.yaml
version: "3.8"

services:
  # API服务
  api:
    build: .
    ports: ["8080:8080"]
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/workflow
      - REDIS_URL=redis://redis:6379/0
      - SKILLS_DIR=/app/skills
    volumes:
      - ./skills:/app/skills
    depends_on: [postgres, redis]
    deploy:
      replicas: 2

  # Celery Worker
  worker:
    build: .
    command: celery -A workflow.worker worker -Q workflow --concurrency=8
    environment:
      - DATABASE_URL=postgresql://user:pass@postgres:5432/workflow
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - ./skills:/app/skills
    depends_on: [postgres, redis]
    deploy:
      replicas: 4

  # WebSocket服务
  websocket:
    build: .
    command: python -m workflow.websocket_server
    ports: ["8081:8081"]
    depends_on: [redis]

  # 数据库
  postgres:
    image: postgres:15
    environment:
      POSTGRES_DB: workflow
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - postgres_data:/var/lib/postgresql/data

  # 缓存/队列
  redis:
    image: redis:7-alpine
    volumes:
      - redis_data:/data

  # 向量数据库 (可选，需要RAG功能时启用)
  milvus:
    image: milvusdb/milvus:latest
    ports: ["19530:19530"]
    profiles: [rag]

  # 对象存储
  minio:
    image: minio/minio:latest
    ports: ["9000:9000", "9001:9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    volumes:
      - minio_data:/data
    command: server /data --console-address ":9001"

volumes:
  postgres_data:
  redis_data:
  minio_data:
```

### 10.2 Kubernetes生产部署

```
Kubernetes部署拓扑:

┌─────────────────────────────────────────────────────────────┐
│                      Ingress Controller                       │
│                    (Nginx Ingress + cert-manager)              │
│                    TLS Termination + Rate Limiting             │
└──────────────────────┬──────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────┐
│  api-service         │  websocket-service                    │
│  ┌───────────────────┴──────────────────────────────────┐  │
│  │              API Server Deployment                     │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                 │  │
│  │  │ Pod 1   │ │ Pod 2   │ │ Pod N   │ (HPA: 2-10)     │  │
│  │  │ CPU:2   │ │ CPU:2   │ │ CPU:2   │                 │  │
│  │  │ Mem:4Gi │ │ Mem:4Gi │ │ Mem:4Gi │                 │  │
│  │  └─────────┘ └─────────┘ └─────────┘                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Worker Deployment (Celery)                │  │
│  │  ┌─────────┐ ┌─────────┐ ┌─────────┐                 │  │
│  │  │Worker 1 │ │Worker 2 │ │Worker N │ (HPA: 2-20)    │  │
│  │  │CPU:4   │ │CPU:4   │ │CPU:4   │                    │  │
│  │  │Mem:8Gi │ │Mem:8Gi │ │Mem:8Gi │                    │  │
│  │  └─────────┘ └─────────┘ └─────────┘                 │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │         WebSocket Server Deployment                    │  │
│  │  ┌─────────┐ ┌─────────┐                             │  │
│  │  │ Pod 1   │ │ Pod 2   │ (HPA: 2-5)                  │  │
│  │  └─────────┘ └─────────┘                             │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────┐
│                  Data Services (StatefulSets)                 │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ PostgreSQL   │ │ Redis        │ │ Milvus (向量数据库)  │ │
│  │ Primary +    │ │ Cluster      │ │ Coordinator +        │ │
│  │ Read Replica │ │ (Sentinel)   │ │ Proxy + Data Nodes   │ │
│  └──────────────┘ └──────────────┘ └──────────────────────┘ │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              MinIO (对象存储, Distributed Mode)       │  │
│  │  4 Nodes × 1 Disk each                               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘

水平扩展策略:
- API Server: 基于CPU (>70%) 和 请求QPS (>1000/s)
- Worker: 基于队列深度 (>100) 和 CPU (>60%)
- WebSocket: 基于连接数 (>5000/实例)
```

### 10.3 CI/CD流水线

```yaml
# .github/workflows/deploy.yaml
stages:
  - test:
      - unit-tests (pytest)
      - integration-tests (docker-compose)
      - lint (ruff, mypy)
      - security-scan (bandit, trivy)

  - build:
      - docker-build (multi-arch: amd64, arm64)
      - push-to-registry
      - helm-package

  - deploy-dev:
      - helm-upgrade (namespace: dev)
      - smoke-tests
      - auto-rollback-on-failure

  - deploy-staging:
      - approval-gate (manual)
      - helm-upgrade (namespace: staging)
      - integration-tests
      - performance-tests (k6)

  - deploy-production:
      - approval-gate (manual, 2 reviewers)
      - helm-upgrade (namespace: production)
      - canary-deploy (10% → 50% → 100%)
      - health-check (5min monitoring window)
      - auto-rollback-on-alert
```

---

## 十一、测试策略

### 11.1 测试金字塔

```
测试层次:

           ┌──────┐
           │ E2E  │  (全链路测试: 10-20个场景)
           │      │   验证: 用户操作 → API → 工作流执行 → 数据库
           └──┬───┘
        ┌─────┴─────┐
        │ Integration│ (集成测试: 50-100个场景)
        │            │  验证: API端点 + 数据库交互 + 外部Mock
        └─────┬──────┘
     ┌───────┴────────┐
     │  Unit Tests    │ (单元测试: 500+ 测试用例)
     │                │  验证: 引擎逻辑、节点执行、DSL解析、变量池
     └────────────────┘
```

### 11.2 测试框架与工具

| 测试类型 | 工具 | 覆盖目标 |
|---------|------|---------|
| 单元测试 | pytest + pytest-asyncio + pytest-cov | 核心引擎 >90%, 节点 >85% |
| 集成测试 | pytest + testcontainers (PostgreSQL, Redis) | API >80% |
| E2E测试 | Playwright (前端) + pytest (API) | 核心用户流程 100% |
| 性能测试 | k6 + locust | 关键API的QPS和延迟 |
| 混沌测试 | chaos-mesh (K8s) | 故障恢复能力 |

### 11.3 节点测试框架

```python
# 节点测试工具
class NodeTestHarness:
    """节点单元测试工具 - 提供隔离的测试环境"""

    def __init__(self, node_class: Type[BaseNode]):
        self.node_class = node_class
        self.variable_pool = VariablePool()
        self.node_config = {}

    def with_config(self, **kwargs) -> "NodeTestHarness":
        """配置节点参数"""
        self.node_config.update(kwargs)
        return self

    def with_input(self, variable_name: str, value: Any) -> "NodeTestHarness":
        """设置Variable Pool中的输入值"""
        self.variable_pool.set(variable_name, value)
        return self

    async def execute(self) -> NodeResult:
        """执行节点并返回结果"""
        node = self.node_class(node_id="test_node", node_config=self.node_config)
        return await node.execute(self.variable_pool)

    def assert_succeeded(self, result: NodeResult):
        """断言执行成功"""
        assert result.status == NodeStatus.SUCCEEDED, \
            f"Expected SUCCEEDED, got {result.status}: {result.error}"

    def assert_output(self, result: NodeResult, key: str, expected: Any):
        """断言输出值"""
        assert key in result.outputs, f"Output key '{key}' not found"
        assert result.outputs[key] == expected, \
            f"Expected {expected}, got {result.outputs[key]}"

# 使用示例
async def test_llm_node_basic():
    harness = NodeTestHarness(LLMNode)
    result = await harness \
        .with_config(model="gpt-4o", prompt_template="Hello, {{sys.user_id}}") \
        .with_input("sys.user_id", "test_user") \
        .execute()

    harness.assert_succeeded(result)
    harness.assert_output_exists(result, "text")
```

### 11.4 工作流模拟测试

```python
async def test_workflow_branch_execution():
    """测试条件分支工作流 - 所有分支路径"""
    workflow_dsl = {
        "nodes": [
            {"id": "start", "type": "start", "data": {"variables": [{"name": "score", "type": "number"}]}},
            {"id": "condition", "type": "condition", "data": {"conditions": [
                {"expression": "{{start.output.score}} >= 0.7", "target_node": "high"},
                {"expression": "{{start.output.score}} < 0.7", "target_node": "low"}
            ]}},
            {"id": "high", "type": "variable_assigner", "data": {"assignments": [{"var": "result", "value": "high_risk"}]}},
            {"id": "low", "type": "variable_assigner", "data": {"assignments": [{"var": "result", "value": "low_risk"}]}},
            {"id": "end", "type": "end"}
        ],
        "edges": [
            {"source": "start", "target": "condition"},
            {"source": "condition", "target": "high", "condition_index": 0},
            {"source": "condition", "target": "low", "condition_index": 1},
            {"source": "high", "target": "end"},
            {"source": "low", "target": "end"},
        ]
    }

    # 测试高分支
    result_high = await execute_workflow(workflow_dsl, {"score": 0.9})
    assert result_high.outputs["result"] == "high_risk"

    # 测试低分支
    result_low = await execute_workflow(workflow_dsl, {"score": 0.3})
    assert result_low.outputs["result"] == "low_risk"
```

---

## 十二、性能指标与容量规划

### 12.1 性能指标目标

| 指标 | Phase 1 目标 | Phase 2 目标 | Phase 3 目标 |
|------|-------------|-------------|-------------|
| DSL解析延迟 | < 100ms (100节点) | < 50ms (100节点) | < 20ms (500节点) |
| 节点调度延迟 | < 20ms | < 10ms | < 5ms |
| LLM节点P50延迟 | < 5s | < 3s | < 2s |
| 并发工作流执行 | 50 | 100 | 500+ |
| 单工作流最大节点 | 200 | 500 | 1000+ |
| API QPS | 1000/s | 5000/s | 20000/s |
| 系统可用性 | 99.5% | 99.9% | 99.95% |
| 部署支持工作流数 | 1,000 | 10,000 | 50,000+ |

### 12.2 缓存策略

```
缓存层次:

L1: 进程内缓存 (Python dict / lru_cache)
├── NodeRegistry: 已注册节点类型配置
├── SkillRegistry: skill清单和manifest
└── ModelConfigCache: 模型配置 (TTL: 5min)

L2: Redis缓存
├── WorkflowDSL: 热工作流的DSL定义 (TTL: 30min)
├── ExecutionState: 正在执行的工作流状态 (TTL: execution_timeout)
├── SessionCache: 用户会话 (TTL: session_timeout)
├── RateLimitCounter: 限流计数器
└── ModelResponseCache: 相同Prompt的LLM响应 (TTL: 1h, 可选)

L3: 数据库 (PostgreSQL)
├── WorkflowDefinitions: 工作流定义 (持久存储)
├── ExecutionHistory: 执行历史 (7天热数据 + 归档)
└── AuditLogs: 审计日志 (保留1年)

缓存失效策略:
- WorkflowDSL: 发布新版本时主动失效
- ModelConfig: TTL自动过期 + 配置变更事件推送
- ExecutionState: 执行完成后删除
```

### 12.3 数据库查询优化

```sql
-- 关键查询的性能优化

-- 1. 工作流列表查询 (最常见的查询)
-- 使用覆盖索引避免回表
CREATE INDEX idx_workflows_list ON workflows(workspace_id, status, updated_at DESC)
    INCLUDE (name, description, current_version_id)
    WHERE deleted_at IS NULL;

-- 2. 版本列表查询
CREATE INDEX idx_versions_list ON workflow_versions(workflow_id, environment, status, created_at DESC);

-- 3. 执行历史查询 (大表优化)
-- 分区表: 按月分区
CREATE TABLE workflow_executions_partitioned (
    id UUID,
    workflow_id UUID NOT NULL,
    status VARCHAR(20) NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    -- ... 其他列
) PARTITION BY RANGE (started_at);

-- 创建月度分区
CREATE TABLE workflow_executions_2026_05 PARTITION OF workflow_executions_partitioned
    FOR VALUES FROM ('2026-05-01') TO ('2026-06-01');
```

---

## 十三、分阶段实施路线图

### Phase 1: MVP (8-10周)
**目标：** 核心工作流引擎 + 基础节点 + 可视化画布 + API

| 周 | 任务 |
|----|------|
| 1-2 | 项目脚手架搭建, 数据库schema, 基础认证 |
| 3-4 | DSL解析器 + 图验证, Variable Pool实现 |
| 5-6 | 工作流执行引擎 (调度/并行/分支) |
| 7-8 | 前端工作流画布 (ReactFlow), 10个基础节点 |
| 9-10 | API层, SSE流式, 测试, 文档 |

### Phase 2: 增强 (6-8周)
**目标：** Skills SDK + 自定义插件 + 版本管理 + 监控

| 周 | 任务 |
|----|------|
| 1-2 | Skills SDK设计实现, 5个预置技能 |
| 3-4 | 插件系统 + 插件注册中心 |
| 5-6 | 版本管理系统, 环境发布流程 |
| 7-8 | Prometheus+Grafana监控, 告警规则 |

### Phase 3: 企业级 (6-8周)
**目标：** RBAC权限 + 审计日志 + 多环境 + 高可用

| 周 | 任务 |
|----|------|
| 1-2 | RBAC + ABAC权限模型实现 |
| 3-4 | 审计日志 + K8s Helm部署 |
| 5-6 | 多租户Workspace隔离, 配额管理 |
| 7-8 | 高可用, 灾难恢复, 性能压测 |

### Phase 4: 生态 (持续迭代)
**目标：** 节点市场 + 社区协作 + 多Agent协同 + MCP协议

| 任务 |
|------|
| 节点/技能市场 (发布/发现/安装) |
| 多Agent协同架构 (Master-SubAgent) |
| MCP协议原生支持 |
| 联邦部署支持 |
| 社区治理体系 |

---

## 附录A: 错误码完整目录

| 错误码 | HTTP | 错误码标识 | 说明 |
|--------|------|-----------|------|
| 0 | 200 | success | 成功 |
| 40001 | 400 | invalid_param | 参数校验失败 |
| 40002 | 400 | dsl_parse_error | DSL JSON解析失败 |
| 40003 | 400 | graph_cycle_detected | 工作流图中检测到环路 |
| 40004 | 400 | unreachable_node | 存在不可达节点 |
| 40005 | 400 | invalid_variable_ref | 变量引用无效 |
| 40006 | 400 | type_mismatch | 节点输入/输出类型不匹配 |
| 40007 | 400 | missing_required_node | 缺少必需的Start/End节点 |
| 40008 | 400 | node_config_invalid | 节点配置不合法 |
| 40009 | 400 | skill_manifest_invalid | 技能manifest验证失败 |
| 40101 | 401 | missing_auth | 缺少认证凭证 |
| 40102 | 401 | invalid_api_key | API-Key无效 |
| 40103 | 401 | expired_api_key | API-Key已过期 |
| 40104 | 401 | invalid_token | 访问令牌无效 |
| 40301 | 403 | access_denied | 无权限访问该资源 |
| 40302 | 403 | quota_exceeded | 配额超限 |
| 40303 | 403 | workspace_access_denied | 无该工作空间访问权限 |
| 40304 | 403 | sandbox_restriction | 沙箱安全策略限制 |
| 40401 | 404 | workflow_not_found | 工作流不存在 |
| 40402 | 404 | execution_not_found | 执行记录不存在 |
| 40403 | 404 | node_type_not_found | 节点类型不存在 |
| 40404 | 404 | skill_not_found | 技能不存在 |
| 40405 | 404 | version_not_found | 版本不存在 |
| 40801 | 408 | workflow_timeout | 工作流执行超时 |
| 40802 | 408 | node_timeout | 节点执行超时 |
| 40901 | 409 | version_conflict | 版本冲突 |
| 40902 | 409 | workflow_locked | 工作流正在编辑中 |
| 42201 | 422 | invalid_status_transition | 状态不允许此操作 |
| 42202 | 422 | workflow_not_published | 工作流未发布 |
| 42901 | 429 | rate_limit_exceeded | API请求频率超限 |
| 42902 | 429 | token_quota_exceeded | Token消耗超限 |
| 50001 | 500 | internal_error | 内部服务器错误 |
| 50002 | 500 | llm_call_failed | LLM模型调用失败 |
| 50003 | 500 | skill_execution_failed | 技能执行失败 |
| 50004 | 500 | code_execution_failed | 代码执行失败 |
| 50005 | 500 | db_error | 数据库错误 |
| 50201 | 502 | model_provider_unavailable | 模型提供者不可用 |
| 50301 | 503 | service_unavailable | 服务暂时不可用 |
| 50302 | 503 | worker_queue_full | Worker队列已满 |

## 附录B: 术语表

| 术语 | 英文 | 说明 |
|------|------|------|
| 工作流 | Workflow | 由节点和边组成的DAG，定义了AI应用的执行流程 |
| DSL | Domain Specific Language | 基于JSON的工作流定义语言 |
| 节点 | Node | 工作流中的基本执行单元 |
| 边 | Edge | 节点之间的连接，定义数据流和控制流 |
| 变量池 | Variable Pool | 运行时内存KV存储，节点间通过它间接通信 |
| 技能 | Skill | 独立的、可复用的功能单元，有标准化的接口 |
| 插件 | Plugin | 扩展节点类型的第三方组件 |
| 检查点 | Checkpoint | 执行状态的快照，用于断点恢复 |
| 熔断器 | Circuit Breaker | 自动故障隔离机制 |
| 死信队列 | Dead Letter Queue | 无法处理的消息/任务的存储队列 |
| 沙箱 | Sandbox | 隔离的代码执行环境 |
| Agent | 智能体 | 具有自主决策能力的AI程序 |
| MCP | Model Context Protocol | AI模型与外部工具通信的开放协议 |
