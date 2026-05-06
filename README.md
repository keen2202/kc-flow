# AI工作流编排系统

基于Dify与Coze深度调研，融合两者优势设计的AI工作流编排系统。

## 文档

- [研究调研报告](docs/research-report.md) — Dify vs Coze 深度技术调研
- [技术规格文档](docs/flow-1.md) — 系统架构、API、数据模型等完整技术规格

## 目录结构

```
kc-flow/
├── docs/
│   ├── research-report.md    # Dify与Coze平台深度调研报告
│   └── flow-1.md             # AI工作流编排系统技术规格文档
├── skills/                   # 技能SDK示例目录
│   ├── skill_manifest.yaml   # 全局技能清单
│   ├── document_processor/   # 文档处理技能
│   ├── risk_analyzer/        # 风险分析技能
│   └── compliance_checker/   # 合规检查技能
└── README.md
```

## 设计理念

- **统一平台、模块化核心**：借鉴Dify的集成化体验 + Coze的模块化架构
- **图引擎为心、变量池为脉**：以Dify的Variable Pool + Queue-based Engine为核心
- **多Agent协同**：吸收Coze的Master-SubAgent模式
- **插件化扩展**：设计更开放的插件SDK，支持社区生态
- **定义与执行分离**：DSL定义层与Runtime执行层解耦

## 分阶段实施

| 阶段 | 目标 | 周期 |
|------|------|------|
| Phase 1: MVP | 核心工作流引擎 + 基础节点 + 可视化画布 + API | 8-10周 |
| Phase 2: 增强 | 技能系统集成 + 自定义插件 + 版本管理 + 监控 | 6-8周 |
| Phase 3: 企业级 | RBAC权限 + 审计日志 + 多环境部署 + 高可用 | 6-8周 |
| Phase 4: 生态 | 节点市场 + 社区协作 + 多Agent协同 + 联邦部署 | 持续迭代 |
