"""AI core nodes: LLM, KnowledgeRetrieval, QuestionClassifier, ParameterExtractor, Agent, MultiAgent."""

from typing import Any

import structlog

from src.engine.abstractions import (
    BaseNode,
    ExecutionContext,
    NodeCategory,
    NodeResult,
    NodeStatus,
    VariableDef,
    register_node,
)
from src.services.model_router import ModelRouter

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# LLM Node
# ──────────────────────────────────────────────


@register_node(
    node_type="llm",
    display_name="大模型推理",
    category=NodeCategory.AI,
    icon="brain",
    description="调用大语言模型进行推理，支持多种模型和流式输出",
    inputs=[
        VariableDef(name="prompt", type="string", required=True, description="用户提示词"),
        VariableDef(name="system_prompt", type="string", description="系统提示词"),
        VariableDef(name="context", type="string", description="上下文信息"),
    ],
    outputs=[
        VariableDef(name="text", type="string", description="模型输出文本"),
        VariableDef(name="usage", type="object", description="Token 使用量"),
        VariableDef(name="finish_reason", type="string", description="完成原因"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "model": {"type": "string", "description": "模型标识，如 gpt-4o, claude-opus-4-7"},
            "prompt_template": {"type": "string", "description": "提示词模板，支持 {{variable}} 引用"},
            "system_prompt": {"type": "string", "description": "系统提示词"},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2, "default": 0.7},
            "max_tokens": {"type": "integer", "minimum": 1, "maximum": 128000, "default": 4096},
            "top_p": {"type": "number", "minimum": 0, "maximum": 1, "default": 1.0},
            "output_schema": {"type": "object", "description": "JSON Schema for structured output"},
            "fallback_model": {"type": "string", "description": "备用模型标识"},
            "retry_config": {
                "type": "object",
                "properties": {
                    "max_retries": {"type": "integer", "default": 3},
                    "backoff_factor": {"type": "number", "default": 2.0},
                },
            },
        },
        "required": ["model"],
    },
)
class LLMNode(BaseNode):
    """Calls a large language model for inference."""

    @property
    def supported_retry_exceptions(self) -> tuple[type[Exception], ...]:
        return (TimeoutError, ConnectionError, OSError)

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        model = self.node_config.get("model", "gpt-4o")
        prompt_template = self.node_config.get("prompt_template", "")
        system_prompt = self.node_config.get("system_prompt", "")
        temperature = self.node_config.get("temperature", 0.7)
        max_tokens = self.node_config.get("max_tokens", 4096)
        fallback_model = self.node_config.get("fallback_model")
        stream = self.node_config.get("stream", True)

        # Resolve prompt template
        if prompt_template:
            prompt = variable_pool.resolve_template(prompt_template)
        else:
            prompt = variable_pool.get(f"{self.node_id}.input.prompt", "")

        # Resolve system prompt
        if system_prompt and "{{" in system_prompt:
            system_prompt = variable_pool.resolve_template(system_prompt)

        if not prompt:
            return NodeResult(status=NodeStatus.FAILED, error="No prompt provided")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        router = ModelRouter()

        # Use streaming if an event emitter is available and streaming is enabled
        emitter = getattr(context, "event_emitter", None) if context else None
        if stream and emitter is not None:
            return await self._execute_stream(router, model, messages, temperature, max_tokens, emitter, context)

        return await self._execute_sync(router, model, messages, temperature, max_tokens, fallback_model)

    async def _execute_stream(
        self,
        router: ModelRouter,
        model: str,
        messages: list,
        temperature: float,
        max_tokens: int,
        emitter: Any,
        context: ExecutionContext | None,
    ) -> NodeResult:
        """Stream LLM response, emitting NODE_STREAMING events for each chunk."""
        from src.engine.scheduler import WorkflowEvent, WorkflowEventType

        accumulated_text = ""
        chunk_count = 0
        try:
            async for chunk in router.call_llm_stream(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            ):
                if chunk.text:
                    accumulated_text += chunk.text
                    chunk_count += 1
                    event = WorkflowEvent(
                        event_type=WorkflowEventType.NODE_STREAMING,
                        data={
                            "node_id": self.node_id,
                            "chunk": chunk.text,
                            "accumulated_text": accumulated_text,
                            "chunk_index": chunk_count,
                            "is_final": chunk.is_final,
                        },
                    )
                    await emitter.emit(event)

            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={
                    "text": accumulated_text,
                    "finish_reason": "stop",
                },
            )
        except Exception as e:
            logger.error("LLM streaming failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))

    async def _execute_sync(
        self,
        router: ModelRouter,
        model: str,
        messages: list,
        temperature: float,
        max_tokens: int,
        fallback_model: str | None,
    ) -> NodeResult:
        """Non-streaming LLM call (legacy path)."""
        try:
            result = await router.call_llm(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                fallback_model=fallback_model,
            )
            usage = result.get("usage", {})
            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={
                    "text": result.get("content", ""),
                    "usage": usage,
                    "finish_reason": result.get("finish_reason", "stop"),
                },
                token_count=usage.get("total_tokens", 0),
            )
        except Exception as e:
            logger.error("LLM node execution failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))


# ──────────────────────────────────────────────
# Knowledge Retrieval Node
# ──────────────────────────────────────────────


@register_node(
    node_type="knowledge_retrieval",
    display_name="知识库检索",
    category=NodeCategory.AI,
    icon="database",
    description="从知识库中检索相关文档片段，支持向量、全文和混合检索",
    inputs=[
        VariableDef(name="query", type="string", required=True, description="检索查询文本"),
    ],
    outputs=[
        VariableDef(name="documents", type="array", description="检索到的文档片段列表"),
        VariableDef(name="scores", type="array", description="相关性分数列表"),
        VariableDef(name="context", type="string", description="拼接后的上下文文本"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "knowledge_base_id": {"type": "string", "description": "知识库ID"},
            "retrieval_strategy": {
                "type": "string",
                "enum": ["vector", "fulltext", "hybrid"],
                "default": "hybrid",
            },
            "top_k": {"type": "integer", "minimum": 1, "maximum": 100, "default": 5},
            "score_threshold": {"type": "number", "minimum": 0, "maximum": 1, "default": 0.5},
            "rerank_model": {"type": "string", "description": "重排序模型"},
            "query_template": {"type": "string", "description": "查询模板"},
        },
        "required": ["knowledge_base_id"],
    },
)
class KnowledgeRetrievalNode(BaseNode):
    """Retrieves relevant document chunks from a knowledge base."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        knowledge_base_id = self.node_config.get("knowledge_base_id", "")
        retrieval_strategy = self.node_config.get("retrieval_strategy", "hybrid")
        top_k = self.node_config.get("top_k", 5)
        score_threshold = self.node_config.get("score_threshold", 0.5)
        query_template = self.node_config.get("query_template", "")

        # Get query
        if query_template:
            query = variable_pool.resolve_template(query_template)
        else:
            query = variable_pool.get(f"{self.node_id}.input.query", "")

        if not query:
            return NodeResult(status=NodeStatus.FAILED, error="No query provided")

        try:
            from src.services.rag.pipeline import RAGPipeline

            pipeline = RAGPipeline()
            results = await pipeline.retrieve(
                knowledge_base_id=knowledge_base_id,
                query=query,
                strategy=retrieval_strategy,
                top_k=top_k,
                score_threshold=score_threshold,
            )

            documents = results.get("documents", [])
            scores = results.get("scores", [])
            context_text = "\n\n---\n\n".join(
                doc.get("content", "") for doc in documents
            )

            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={
                    "documents": documents,
                    "scores": scores,
                    "context": context_text,
                },
            )
        except ImportError:
            logger.warning("RAG pipeline not available, returning empty results")
            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={"documents": [], "scores": [], "context": ""},
            )
        except Exception as e:
            logger.error("Knowledge retrieval failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))


# ──────────────────────────────────────────────
# Question Classifier Node
# ──────────────────────────────────────────────


@register_node(
    node_type="question_classifier",
    display_name="意图分类",
    category=NodeCategory.AI,
    icon="tags",
    description="使用 LLM 对用户问题进行意图分类，路由到对应的处理分支",
    inputs=[
        VariableDef(name="query", type="string", required=True, description="用户问题"),
        VariableDef(name="context", type="string", description="对话上下文"),
    ],
    outputs=[
        VariableDef(name="class_name", type="string", description="分类结果名称"),
        VariableDef(name="class_index", type="number", description="分类结果索引"),
        VariableDef(name="confidence", type="number", description="分类置信度"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "classes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                        "examples": {"type": "array", "items": {"type": "string"}},
                        "target_node": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
            "model": {"type": "string", "default": "gpt-4o-mini"},
            "instruction": {"type": "string", "description": "分类指令"},
        },
        "required": ["classes"],
    },
)
class QuestionClassifierNode(BaseNode):
    """Classifies user intent using LLM and routes to appropriate branch."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        classes = self.node_config.get("classes", [])
        model = self.node_config.get("model", "gpt-4o-mini")
        instruction = self.node_config.get("instruction", "")

        query = variable_pool.get(f"{self.node_id}.input.query", "")
        ctx = variable_pool.get(f"{self.node_id}.input.context", "")

        if not query:
            return NodeResult(status=NodeStatus.FAILED, error="No query provided")

        # Build classification prompt
        class_descriptions = []
        for i, cls in enumerate(classes):
            desc = f"{i}. {cls['name']}"
            if cls.get("description"):
                desc += f": {cls['description']}"
            if cls.get("examples"):
                desc += f"\n   Examples: {', '.join(cls['examples'][:3])}"
            class_descriptions.append(desc)

        prompt = f"""Classify the following question into one of the provided categories.

Categories:
{chr(10).join(class_descriptions)}

{f"Context: {ctx}" if ctx else ""}

Question: {query}

Respond with ONLY the category number (0-{len(classes) - 1})."""

        if instruction:
            prompt = f"{instruction}\n\n{prompt}"

        router = ModelRouter()
        try:
            result = await router.call_llm(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=10,
            )

            response_text = result.get("content", "").strip()
            # Extract class index
            try:
                class_index = int(response_text[0]) if response_text else 0
                class_index = max(0, min(class_index, len(classes) - 1))
            except (ValueError, IndexError):
                class_index = 0

            class_name = classes[class_index]["name"] if classes else "unknown"

            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={
                    "class_name": class_name,
                    "class_index": class_index,
                    "confidence": 1.0,  # LLM doesn't provide confidence natively
                },
            )
        except Exception as e:
            logger.error("Question classification failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))


# ──────────────────────────────────────────────
# Parameter Extractor Node
# ──────────────────────────────────────────────


@register_node(
    node_type="parameter_extractor",
    display_name="参数提取",
    category=NodeCategory.AI,
    icon="filter",
    description="从非结构化文本中提取结构化参数",
    inputs=[
        VariableDef(name="text", type="string", required=True, description="待提取的文本"),
    ],
    outputs=[
        VariableDef(name="parameters", type="object", description="提取的参数字典"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "parameters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["string", "number", "boolean", "array", "object"]},
                        "description": {"type": "string"},
                        "required": {"type": "boolean", "default": False},
                    },
                    "required": ["name", "type"],
                },
            },
            "model": {"type": "string", "default": "gpt-4o-mini"},
            "instruction": {"type": "string"},
        },
        "required": ["parameters"],
    },
)
class ParameterExtractorNode(BaseNode):
    """Extracts structured parameters from unstructured text using LLM."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        param_defs = self.node_config.get("parameters", [])
        model = self.node_config.get("model", "gpt-4o-mini")
        instruction = self.node_config.get("instruction", "")

        text = variable_pool.get(f"{self.node_id}.input.text", "")
        if not text:
            return NodeResult(status=NodeStatus.FAILED, error="No text provided")

        # Build extraction prompt
        param_descriptions = []
        for p in param_defs:
            desc = f"- {p['name']} ({p['type']})"
            if p.get("description"):
                desc += f": {p['description']}"
            if p.get("required"):
                desc += " [REQUIRED]"
            param_descriptions.append(desc)

        prompt = f"""Extract the following parameters from the text below.

Parameters:
{chr(10).join(param_descriptions)}

{text}

Respond with a JSON object containing the extracted parameters. Use null for missing optional parameters."""

        if instruction:
            prompt = f"{instruction}\n\n{prompt}"

        router = ModelRouter()
        try:
            result = await router.call_llm(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0,
                max_tokens=1024,
            )

            response_text = result.get("content", "").strip()

            # Parse JSON from response
            import json
            # Try to extract JSON from markdown code block or raw text
            if "```json" in response_text:
                json_str = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                json_str = response_text.split("```")[1].split("```")[0].strip()
            else:
                json_str = response_text

            try:
                parameters = json.loads(json_str)
            except json.JSONDecodeError:
                parameters = {}

            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={"parameters": parameters},
            )
        except Exception as e:
            logger.error("Parameter extraction failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))


# ──────────────────────────────────────────────
# Agent Node
# ──────────────────────────────────────────────


@register_node(
    node_type="agent",
    display_name="自主Agent",
    category=NodeCategory.AI,
    icon="robot",
    description="自主决策的AI Agent，支持工具调用和多步推理",
    inputs=[
        VariableDef(name="task", type="string", required=True, description="Agent任务描述"),
        VariableDef(name="context", type="string", description="上下文信息"),
    ],
    outputs=[
        VariableDef(name="result", type="string", description="Agent执行结果"),
        VariableDef(name="steps", type="array", description="执行步骤记录"),
        VariableDef(name="tool_calls", type="array", description="工具调用记录"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "model": {"type": "string", "default": "gpt-4o"},
            "agent_config": {
                "type": "object",
                "properties": {
                    "max_iterations": {"type": "integer", "default": 10},
                    "tools": {"type": "array", "items": {"type": "string"}},
                    "memory_type": {"type": "string", "enum": ["none", "buffer", "summary"], "default": "buffer"},
                    "system_prompt": {"type": "string"},
                },
            },
        },
    },
)
class AgentNode(BaseNode):
    """Autonomous AI Agent with tool use and multi-step reasoning."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        agent_config = self.node_config.get("agent_config", {})
        model = self.node_config.get("model", "gpt-4o")
        max_iterations = agent_config.get("max_iterations", 10)
        system_prompt = agent_config.get("system_prompt", "")

        task = variable_pool.get(f"{self.node_id}.input.task", "")
        ctx = variable_pool.get(f"{self.node_id}.input.context", "")

        if not task:
            return NodeResult(status=NodeStatus.FAILED, error="No task provided")

        # Build agent prompt with ReAct pattern
        agent_prompt = f"""You are an autonomous AI agent. Complete the following task using multi-step reasoning.

Task: {task}
{f"Context: {ctx}" if ctx else ""}

Think step by step. For each step:
1. Thought: What you need to do next
2. Action: The action to take
3. Observation: The result of the action

When you have enough information, provide your Final Answer."""

        router = ModelRouter()
        steps: list[dict[str, Any]] = []

        try:
            for iteration in range(max_iterations):
                result = await router.call_llm(
                    model=model,
                    messages=[{"role": "user", "content": agent_prompt}],
                    system=system_prompt or None,
                    temperature=0.7,
                    max_tokens=2048,
                )

                response = result.get("content", "")
                steps.append({"iteration": iteration, "response": response})

                # Check if agent has reached a final answer
                if "Final Answer:" in response or "final answer:" in response.lower():
                    final_answer = response
                    if "Final Answer:" in response:
                        final_answer = response.split("Final Answer:")[-1].strip()
                    elif "final answer:" in response.lower():
                        final_answer = response.lower().split("final answer:")[-1].strip()

                    return NodeResult(
                        status=NodeStatus.SUCCEEDED,
                        outputs={
                            "result": final_answer,
                            "steps": steps,
                            "tool_calls": [],
                        },
                    )

                # Continue reasoning
                agent_prompt += f"\n\n{response}\n\nContinue your reasoning..."

            # Max iterations reached
            return NodeResult(
                status=NodeStatus.SUCCEEDED,
                outputs={
                    "result": steps[-1]["response"] if steps else "",
                    "steps": steps,
                    "tool_calls": [],
                },
            )
        except Exception as e:
            logger.error("Agent execution failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))


# ──────────────────────────────────────────────
# Multi-Agent Node
# ──────────────────────────────────────────────


@register_node(
    node_type="multi_agent",
    display_name="多Agent协同",
    category=NodeCategory.AI,
    icon="users",
    description="多个Agent协同工作，支持顺序、广播和辩论模式",
    inputs=[
        VariableDef(name="task", type="string", required=True, description="协同任务"),
        VariableDef(name="context", type="string", description="共享上下文"),
    ],
    outputs=[
        VariableDef(name="result", type="string", description="最终协同结果"),
        VariableDef(name="agent_outputs", type="array", description="各Agent输出"),
        VariableDef(name="consensus", type="string", description="共识结论"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "agents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "role": {"type": "string"},
                        "model": {"type": "string", "default": "gpt-4o"},
                        "system_prompt": {"type": "string"},
                        "tools": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["name", "role"],
                },
            },
            "coordination": {
                "type": "string",
                "enum": ["sequential", "broadcast", "debate"],
                "default": "sequential",
            },
            "max_rounds": {"type": "integer", "default": 3},
        },
        "required": ["agents"],
    },
)
class MultiAgentNode(BaseNode):
    """Multi-agent collaboration with sequential, broadcast, or debate coordination."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        agents = self.node_config.get("agents", [])
        coordination = self.node_config.get("coordination", "sequential")
        max_rounds = self.node_config.get("max_rounds", 3)

        task = variable_pool.get(f"{self.node_id}.input.task", "")
        ctx = variable_pool.get(f"{self.node_id}.input.context", "")

        if not task:
            return NodeResult(status=NodeStatus.FAILED, error="No task provided")
        if not agents:
            return NodeResult(status=NodeStatus.FAILED, error="No agents defined")

        router = ModelRouter()

        try:
            if coordination == "sequential":
                return await self._sequential(router, agents, task, ctx)
            elif coordination == "broadcast":
                return await self._broadcast(router, agents, task, ctx)
            elif coordination == "debate":
                return await self._debate(router, agents, task, ctx, max_rounds)
            else:
                return NodeResult(status=NodeStatus.FAILED, error=f"Unknown coordination: {coordination}")
        except Exception as e:
            logger.error("Multi-agent execution failed", node_id=self.node_id, error=str(e))
            return NodeResult(status=NodeStatus.FAILED, error=str(e))

    async def _sequential(self, router: ModelRouter, agents: list, task: str, ctx: str) -> NodeResult:
        """Sequential: each agent processes the output of the previous one."""
        current_input = task
        agent_outputs: list[dict[str, Any]] = []

        for agent in agents:
            prompt = f"""You are {agent['name']}, role: {agent['role']}.
Task: {current_input}
{f"Context: {ctx}" if ctx else ""}
Provide your analysis and output."""

            result = await router.call_llm(
                model=agent.get("model", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                system=agent.get("system_prompt"),
                temperature=0.7,
                max_tokens=2048,
            )
            output = result.get("content", "")
            agent_outputs.append({"name": agent["name"], "role": agent["role"], "output": output})
            current_input = output

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "result": current_input,
                "agent_outputs": agent_outputs,
                "consensus": current_input,
            },
        )

    async def _broadcast(self, router: ModelRouter, agents: list, task: str, ctx: str) -> NodeResult:
        """Broadcast: all agents work on the same task independently."""
        import asyncio

        async def run_agent(agent: dict) -> dict[str, Any]:
            prompt = f"""You are {agent['name']}, role: {agent['role']}.
Task: {task}
{f"Context: {ctx}" if ctx else ""}
Provide your analysis."""

            result = await router.call_llm(
                model=agent.get("model", "gpt-4o"),
                messages=[{"role": "user", "content": prompt}],
                system=agent.get("system_prompt"),
                temperature=0.7,
                max_tokens=2048,
            )
            return {"name": agent["name"], "role": agent["role"], "output": result.get("content", "")}

        agent_outputs = await asyncio.gather(*[run_agent(a) for a in agents])

        # Synthesize results
        synthesis_prompt = "Synthesize the following agent outputs into a unified conclusion:\n\n"
        for ao in agent_outputs:
            synthesis_prompt += f"--- {ao['name']} ({ao['role']}) ---\n{ao['output']}\n\n"

        synthesis = await router.call_llm(
            model=agents[0].get("model", "gpt-4o"),
            messages=[{"role": "user", "content": synthesis_prompt}],
            temperature=0.3,
            max_tokens=2048,
        )

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "result": synthesis.get("content", ""),
                "agent_outputs": list(agent_outputs),
                "consensus": synthesis.get("content", ""),
            },
        )

    async def _debate(self, router: ModelRouter, agents: list, task: str, ctx: str, max_rounds: int) -> NodeResult:
        """Debate: agents discuss and refine through multiple rounds."""
        current_positions: list[dict[str, Any]] = []
        all_outputs: list[dict[str, Any]] = []

        for round_num in range(max_rounds):
            round_outputs: list[dict[str, Any]] = []

            for agent in agents:
                if round_num == 0:
                    prompt = f"""You are {agent['name']}, role: {agent['role']}.
Topic: {task}
{f"Context: {ctx}" if ctx else ""}
State your position and reasoning."""
                else:
                    others = "\n".join(
                        f"- {p['name']} ({p['role']}): {p['position'][:200]}..."
                        for p in current_positions if p["name"] != agent["name"]
                    )
                    prompt = f"""You are {agent['name']}, role: {agent['role']}.
Topic: {task}

Other agents' positions:
{others}

Refine your position considering the others' arguments. State your updated position."""

                result = await router.call_llm(
                    model=agent.get("model", "gpt-4o"),
                    messages=[{"role": "user", "content": prompt}],
                    system=agent.get("system_prompt"),
                    temperature=0.7,
                    max_tokens=1024,
                )
                output = result.get("content", "")
                round_outputs.append({"name": agent["name"], "role": agent["role"], "output": output, "round": round_num})

            current_positions = [{"name": o["name"], "role": o["role"], "position": o["output"]} for o in round_outputs]
            all_outputs.extend(round_outputs)

        # Final consensus
        consensus_prompt = "Based on the multi-round debate, provide a final consensus:\n\n"
        for pos in current_positions:
            consensus_prompt += f"- {pos['name']} ({pos['role']}): {pos['position'][:300]}\n\n"

        consensus = await router.call_llm(
            model=agents[0].get("model", "gpt-4o"),
            messages=[{"role": "user", "content": consensus_prompt}],
            temperature=0.3,
            max_tokens=2048,
        )

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "result": consensus.get("content", ""),
                "agent_outputs": all_outputs,
                "consensus": consensus.get("content", ""),
            },
        )
