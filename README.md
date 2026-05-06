# KC-Flow — AI 工作流编排引擎

基于 Dify 与 Coze 深度调研，融合两者优势设计的 AI 工作流编排系统。支持可视化 DAG 编排、21 种内置节点、多模型路由、RAG 知识检索、插件市场等能力。

## 快速开始

```bash
# 启动依赖服务
docker compose up -d postgres redis minio

# 安装依赖
pip install -e ".[dev]"

# 启动 API 服务
uvicorn src.api.main:app --host 0.0.0.0 --port 8080 --reload

# 启动前端 (另一个终端)
cd frontend && npm install && npm run dev
```

API 文档: http://localhost:8080/docs (debug 模式)

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                     前端画布 (React + ReactFlow)              │
├─────────────────────────────────────────────────────────────┤
│  REST API (FastAPI)  │  SSE 流式  │  WebSocket 实时通信       │
├─────────────────────────────────────────────────────────────┤
│                      执行引擎 (ExecutionScheduler)            │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ 图解析器  │  │ 变量池    │  │ 检查点    │  │ 事件发射  │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
├─────────────────────────────────────────────────────────────┤
│  控制流节点 (7)  │  AI 节点 (6)  │  数据/集成节点 (8)          │
├─────────────────────────────────────────────────────────────┤
│  模型路由 (OpenAI / Anthropic / Local)                       │
│  RAG 管道 (向量检索 + BM25 + 重排序)                          │
│  Skills SDK  │  插件系统  │  Docker 沙箱                      │
├─────────────────────────────────────────────────────────────┤
│  PostgreSQL  │  Redis  │  Milvus/PGVector  │  MinIO          │
└─────────────────────────────────────────────────────────────┘
```

## 目录结构

```
kc-flow/
├── src/
│   ├── api/                    # FastAPI 应用
│   │   ├── main.py             #   应用工厂、中间件注册
│   │   ├── middleware.py       #   RequestID、日志、限流
│   │   ├── dependencies.py     #   分页、认证、响应格式
│   │   ├── schemas.py          #   统一响应模型
│   │   └── routes/             #   API 路由
│   │       ├── workflows.py    #     工作流 CRUD + 执行
│   │       ├── nodes.py        #     节点管理
│   │       ├── models.py       #     模型管理
│   │       ├── skills.py       #     技能管理
│   │       ├── auth.py         #     认证 (JWT + API-Key)
│   │       ├── streaming.py    #     SSE / WebSocket
│   │       └── marketplace.py  #     节点市场
│   ├── engine/                 # 执行引擎核心
│   │   ├── abstractions.py     #   BaseNode、NodeRegistry、ExecutionContext
│   │   ├── scheduler.py        #   ExecutionScheduler (拓扑排序调度)
│   │   ├── graph_parser.py     #   DSL 解析 + 图验证
│   │   ├── variable_pool.py    #   VariablePool (Jinja2 模板解析)
│   │   ├── checkpoint.py       #   检查点管理
│   │   ├── circuit_breaker.py  #   熔断器
│   │   ├── retry.py            #   重试策略 (指数退避)
│   │   └── dead_letter_queue.py#   死信队列
│   ├── nodes/                  # 内置节点实现
│   │   ├── control/            #   控制流: Start, End, Condition, Loop, Parallel, Variable*
│   │   ├── ai/                 #   AI: LLM, KnowledgeRetrieval, QuestionClassifier, Agent, MultiAgent
│   │   └── data/               #   数据: Code, HTTPRequest, Template, DataTransform, DocumentParser, Webhook, MCPTool, Wait
│   ├── services/               # 业务服务
│   │   ├── model_router.py     #   多模型统一路由 (OpenAI / Anthropic / Local)
│   │   ├── rag/                #   RAG 管道
│   │   │   ├── vector_store.py #     向量存储 (InMemory / PGVector / Milvus)
│   │   │   ├── embedding.py    #     嵌入服务 (OpenAI / Cohere / Local)
│   │   │   ├── chunker.py      #     文档分块 (FixedSize / Sentence / Recursive)
│   │   │   ├── hybrid_searcher.py # 混合检索 (向量 + BM25 RRF)
│   │   │   ├── reranker.py     #     重排序 (Cohere / CrossEncoder BGE)
│   │   │   └── pipeline.py     #     端到端管道编排
│   │   ├── auth.py             #   认证服务 (JWT + API-Key)
│   │   ├── rbac.py             #   RBAC 权限
│   │   ├── security.py         #   安全加固 (加密、注入检测、输入净化)
│   │   ├── sandbox.py          #   Docker 代码沙箱
│   │   ├── plugin_manager.py   #   插件生命周期管理
│   │   ├── version_manager.py  #   工作流版本管理
│   │   ├── marketplace.py      #   节点市场
│   │   └── monitoring.py       #   Prometheus 指标
│   ├── skills_sdk/             # Skills SDK (独立 pip 包)
│   │   ├── manifest.py         #   manifest.yaml 解析
│   │   ├── context.py          #   SkillContext 运行时 API
│   │   ├── scheduler.py        #   SkillScheduler 加载/执行
│   │   └── node.py             #   SkillNode 节点集成
│   ├── models/                 # SQLAlchemy 数据模型
│   └── config/                 # 配置管理 (pydantic-settings)
├── skills/                     # 内置技能示例
│   ├── document_processor/     #   文档处理
│   ├── risk_analyzer/          #   风险分析
│   └── compliance_checker/     #   合规检查
├── frontend/                   # React 前端 (Vite + TypeScript + ReactFlow)
├── tests/
│   ├── unit/                   #   单元测试
│   ├── integration/            #   集成测试 (API + Streaming)
│   └── e2e/                    #   端到端测试
├── deploy/k8s/                 # Kubernetes 部署 manifests
├── docker-compose.yaml         # 本地开发环境
├── Dockerfile                  # 多阶段构建
├── Makefile                    # 常用命令
└── pyproject.toml              # Python 项目配置
```

## 内置节点 (21 种)

| 类别 | 节点 | 说明 |
|------|------|------|
| 控制流 | Start, End, Condition, Loop, Parallel, VariableAssigner, VariableAggregator | 流程控制、分支、循环、变量操作 |
| AI | LLM, KnowledgeRetrieval, QuestionClassifier, ParameterExtractor, Agent, MultiAgent | 大模型推理、RAG 检索、意图分类、Agent 协同 |
| 数据/集成 | Code, HTTPRequest, Template, DataTransform, DocumentParser, Webhook, MCPTool, Wait | 代码执行、HTTP 调用、数据转换、文档解析 |

## 技术栈

- **后端**: Python 3.11+, FastAPI, SQLAlchemy, Celery, Redis
- **前端**: React 18, TypeScript, Vite, ReactFlow, Zustand, Tailwind CSS
- **向量存储**: Milvus, PGVector, InMemory (开发)
- **模型**: OpenAI GPT-4o/4.1, Anthropic Claude Opus/Sonnet, 本地模型 (vLLM/Ollama)
- **基础设施**: PostgreSQL 15, Redis 7, MinIO, Docker, Kubernetes

## 开发命令

```bash
make lint          # 代码检查 (ruff)
make format        # 代码格式化
make typecheck     # 类型检查 (mypy)
make test          # 运行全部测试
make test-unit     # 单元测试
make test-integration  # 集成测试
make test-cov      # 测试覆盖率
make build         # 构建 Docker 镜像
make migrate       # 数据库迁移
```
