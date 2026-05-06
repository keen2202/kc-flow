"""Control flow nodes: Start, End, Condition, Loop, Parallel, VariableAssigner, VariableAggregator."""

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

logger = structlog.get_logger()


# ──────────────────────────────────────────────
# Start Node
# ──────────────────────────────────────────────


@register_node(
    node_type="start",
    display_name="开始",
    category=NodeCategory.CONTROL,
    icon="play-circle",
    description="工作流启动入口，定义用户输入变量",
    outputs=[
        VariableDef(name="variables", type="object", description="用户输入变量集合"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "variables": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "type": {"type": "string", "enum": ["string", "number", "boolean", "object", "array"]},
                        "required": {"type": "boolean"},
                        "default": {},
                        "description": {"type": "string"},
                    },
                    "required": ["name", "type"],
                },
            },
        },
    },
)
class StartNode(BaseNode):
    """Workflow entry point. Validates required inputs and passes them through."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        variables = self.node_config.get("variables", [])
        errors = self.validate_inputs({v["name"]: variable_pool.get(f"node_start.output.{v['name']}") for v in variables})
        if errors:
            return NodeResult(status=NodeStatus.FAILED, error="; ".join(errors))

        # Collect all input variables
        outputs: dict[str, Any] = {}
        for var_def in variables:
            name = var_def["name"]
            value = variable_pool.get(f"node_start.output.{name}", var_def.get("default"))
            outputs[name] = value

        logger.debug("Start node executed", node_id=self.node_id, output_keys=list(outputs.keys()))
        return NodeResult(status=NodeStatus.SUCCEEDED, outputs=outputs)


# ──────────────────────────────────────────────
# End Node
# ──────────────────────────────────────────────


@register_node(
    node_type="end",
    display_name="结束",
    category=NodeCategory.CONTROL,
    icon="stop-circle",
    description="工作流终止出口，收集最终输出结果",
    inputs=[
        VariableDef(name="result", type="any", description="最终输出结果"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "outputs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "from": {"type": "string", "description": "Variable pool path, e.g. node_id.output.field"},
                    },
                    "required": ["name", "from"],
                },
            },
        },
    },
)
class EndNode(BaseNode):
    """Workflow exit point. Collects outputs from upstream nodes."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        output_defs = self.node_config.get("outputs", [])
        outputs: dict[str, Any] = {}

        for output_def in output_defs:
            name = output_def.get("name", "result")
            from_path = output_def.get("from", "")
            if from_path:
                # Resolve template if it contains {{ }}
                if "{{" in from_path:
                    value = variable_pool.resolve_template(from_path)
                else:
                    value = variable_pool.get(from_path, "")
            else:
                value = ""
            outputs[name] = value

        logger.debug("End node executed", node_id=self.node_id, output_keys=list(outputs.keys()))
        return NodeResult(status=NodeStatus.SUCCEEDED, outputs=outputs)


# ──────────────────────────────────────────────
# Condition Node
# ──────────────────────────────────────────────


@register_node(
    node_type="condition",
    display_name="条件分支",
    category=NodeCategory.CONTROL,
    icon="git-branch",
    description="基于条件表达式的 if-else 分支判断",
    inputs=[
        VariableDef(name="expression", type="string", required=True, description="条件表达式"),
    ],
    outputs=[
        VariableDef(name="matched_index", type="number", description="匹配的条件索引"),
        VariableDef(name="matched_target", type="string", description="匹配的目标节点"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "conditions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "expression": {"type": "string", "description": "条件表达式，支持 {{var}} == 'value' 等"},
                        "target_node": {"type": "string"},
                    },
                    "required": ["expression"],
                },
            },
            "default_target": {"type": "string", "description": "无条件匹配时的默认目标节点"},
        },
        "required": ["conditions"],
    },
)
class ConditionNode(BaseNode):
    """Evaluates conditions in order and routes to the first matching branch."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        conditions = self.node_config.get("conditions", [])
        default_target = self.node_config.get("default_target")

        for i, condition in enumerate(conditions):
            expression = condition.get("expression", "")
            try:
                resolved = variable_pool.resolve_template(expression)
                allowed_names = {"True": True, "False": False, "None": None}
                result = eval(resolved, {"__builtins__": {}}, allowed_names)
                if result:
                    target = condition.get("target_node", "")
                    return NodeResult(
                        status=NodeStatus.SUCCEEDED,
                        outputs={"matched_index": i, "matched_target": target},
                    )
            except Exception:
                continue

        # No condition matched — use default
        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={"matched_index": -1, "matched_target": default_target or ""},
        )


# ──────────────────────────────────────────────
# Loop Node
# ──────────────────────────────────────────────


@register_node(
    node_type="loop",
    display_name="循环",
    category=NodeCategory.CONTROL,
    icon="repeat",
    description="循环执行，支持 for 和 while 模式",
    inputs=[
        VariableDef(name="items", type="array", description="for 循环的迭代数据"),
        VariableDef(name="condition", type="string", description="while 循环的条件表达式"),
    ],
    outputs=[
        VariableDef(name="results", type="array", description="每次迭代的结果列表"),
        VariableDef(name="iteration_count", type="number", description="实际迭代次数"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "loop_type": {"type": "string", "enum": ["for", "while"], "default": "for"},
            "max_iterations": {"type": "integer", "default": 100, "description": "最大迭代次数"},
            "items_path": {"type": "string", "description": "for 循环数据源路径，如 node_id.output.items"},
            "condition_expression": {"type": "string", "description": "while 循环条件表达式"},
            "output_aggregation": {"type": "string", "enum": ["collect", "last"], "default": "collect"},
        },
        "required": ["loop_type"],
    },
)
class LoopNode(BaseNode):
    """Loop execution — iterates over items or while a condition holds.

    The actual sub-graph execution is handled by the scheduler. This node
    manages iteration state and aggregation.
    """

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        loop_type = self.node_config.get("loop_type", "for")
        max_iterations = self.node_config.get("max_iterations", 100)
        output_aggregation = self.node_config.get("output_aggregation", "collect")

        if loop_type == "for":
            return await self._execute_for_loop(variable_pool, max_iterations, output_aggregation)
        else:
            return await self._execute_while_loop(variable_pool, max_iterations, output_aggregation)

    async def _execute_for_loop(
        self, variable_pool: Any, max_iterations: int, output_aggregation: str
    ) -> NodeResult:
        items_path = self.node_config.get("items_path", "")
        if items_path:
            items = variable_pool.get(items_path, [])
        else:
            items = variable_pool.get(f"{self.node_id}.input.items", [])

        if not isinstance(items, list):
            return NodeResult(status=NodeStatus.FAILED, error="Loop items must be an array")

        results: list[Any] = []
        iteration_count = min(len(items), max_iterations)

        for i in range(iteration_count):
            variable_pool.set(f"{self.node_id}.current_item", items[i])
            variable_pool.set(f"{self.node_id}.current_index", i)
            # The scheduler handles sub-graph execution for each iteration
            results.append({"index": i, "item": items[i]})

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "results": results if output_aggregation == "collect" else (results[-1:] if results else []),
                "iteration_count": iteration_count,
            },
        )

    async def _execute_while_loop(
        self, variable_pool: Any, max_iterations: int, output_aggregation: str
    ) -> NodeResult:
        condition_expr = self.node_config.get("condition_expression", "")
        results: list[Any] = []
        iteration_count = 0

        for _ in range(max_iterations):
            if condition_expr:
                try:
                    resolved = variable_pool.resolve_template(condition_expr)
                    allowed_names = {"True": True, "False": False, "None": None}
                    should_continue = bool(eval(resolved, {"__builtins__": {}}, allowed_names))
                except Exception:
                    break
                if not should_continue:
                    break

            iteration_count += 1
            variable_pool.set(f"{self.node_id}.current_index", iteration_count - 1)
            results.append({"index": iteration_count - 1})

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "results": results if output_aggregation == "collect" else (results[-1:] if results else []),
                "iteration_count": iteration_count,
            },
        )


# ──────────────────────────────────────────────
# Parallel Node
# ──────────────────────────────────────────────


@register_node(
    node_type="parallel",
    display_name="并行分支",
    category=NodeCategory.CONTROL,
    icon="columns",
    description="创建并行执行分支，所有分支同时执行",
    outputs=[
        VariableDef(name="branch_count", type="number", description="并行分支数量"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "branches": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "description": {"type": "string"},
                    },
                },
            },
            "error_strategy": {
                "type": "string",
                "enum": ["fail_fast", "continue_on_error", "aggregate"],
                "default": "fail_fast",
            },
        },
    },
)
class ParallelNode(BaseNode):
    """Parallel branch fork point. The scheduler activates all outgoing branches."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        branches = self.node_config.get("branches", [])
        error_strategy = self.node_config.get("error_strategy", "fail_fast")

        variable_pool.set(f"{self.node_id}.output.error_strategy", error_strategy)

        return NodeResult(
            status=NodeStatus.SUCCEEDED,
            outputs={
                "branch_count": len(branches),
                "error_strategy": error_strategy,
            },
        )


# ──────────────────────────────────────────────
# Variable Assigner Node
# ──────────────────────────────────────────────


@register_node(
    node_type="variable_assigner",
    display_name="变量赋值",
    category=NodeCategory.CONTROL,
    icon="edit",
    description="在工作流中动态创建或修改变量",
    inputs=[
        VariableDef(name="assignments", type="array", required=True, description="赋值规则列表"),
    ],
    outputs=[
        VariableDef(name="assigned", type="object", description="已赋值的变量集合"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "assignments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "variable": {"type": "string", "description": "目标变量路径，如 my_var"},
                        "value": {"type": "string", "description": "赋值表达式，支持 {{template}}"},
                        "operation": {
                            "type": "string",
                            "enum": ["set", "append", "increment", "toggle"],
                            "default": "set",
                        },
                    },
                    "required": ["variable", "value"],
                },
            },
        },
        "required": ["assignments"],
    },
)
class VariableAssignerNode(BaseNode):
    """Assigns values to variables in the VariablePool."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        assignments = self.node_config.get("assignments", [])
        assigned: dict[str, Any] = {}

        for assignment in assignments:
            var_name = assignment.get("variable", "")
            value_expr = assignment.get("value", "")
            operation = assignment.get("operation", "set")

            # Resolve template in value
            if "{{" in str(value_expr):
                resolved_value = variable_pool.resolve_template(str(value_expr))
            else:
                resolved_value = value_expr

            target_path = f"{self.node_id}.output.{var_name}"

            if operation == "set":
                variable_pool.set(target_path, resolved_value)
            elif operation == "append":
                existing = variable_pool.get(target_path, [])
                if isinstance(existing, list):
                    existing.append(resolved_value)
                    variable_pool.set(target_path, existing)
                else:
                    variable_pool.set(target_path, [resolved_value])
            elif operation == "increment":
                existing = variable_pool.get(target_path, 0)
                try:
                    variable_pool.set(target_path, existing + float(resolved_value))
                except (TypeError, ValueError):
                    variable_pool.set(target_path, resolved_value)
            elif operation == "toggle":
                existing = variable_pool.get(target_path, False)
                variable_pool.set(target_path, not existing)

            assigned[var_name] = variable_pool.get(target_path)

        return NodeResult(status=NodeStatus.SUCCEEDED, outputs={"assigned": assigned})


# ──────────────────────────────────────────────
# Variable Aggregator Node
# ──────────────────────────────────────────────


@register_node(
    node_type="variable_aggregator",
    display_name="变量聚合",
    category=NodeCategory.CONTROL,
    icon="merge",
    description="将多个并行分支的输出聚合为统一输出",
    outputs=[
        VariableDef(name="aggregated", type="object", description="聚合后的变量集合"),
    ],
    config_schema={
        "type": "object",
        "properties": {
            "groups": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "聚合输出的变量名"},
                        "variables": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "要聚合的变量路径列表",
                        },
                        "strategy": {
                            "type": "string",
                            "enum": ["first_non_null", "last_wins", "merge_lists", "concatenate", "average"],
                            "default": "first_non_null",
                        },
                    },
                    "required": ["name", "variables"],
                },
            },
        },
        "required": ["groups"],
    },
)
class VariableAggregatorNode(BaseNode):
    """Aggregates variables from multiple parallel branches into unified outputs."""

    async def execute(self, variable_pool: Any, context: ExecutionContext | None = None) -> NodeResult:
        groups = self.node_config.get("groups", [])
        aggregated: dict[str, Any] = {}

        for group in groups:
            name = group.get("name", "result")
            variables = group.get("variables", [])
            strategy = group.get("strategy", "first_non_null")

            values: list[Any] = []
            for var_path in variables:
                if "{{" in var_path:
                    value = variable_pool.resolve_template(var_path)
                else:
                    value = variable_pool.get(var_path)
                values.append(value)

            aggregated[name] = self._aggregate_values(values, strategy)

        return NodeResult(status=NodeStatus.SUCCEEDED, outputs={"aggregated": aggregated})

    def _aggregate_values(self, values: list[Any], strategy: str) -> Any:
        """Aggregate multiple values according to strategy."""
        if strategy == "first_non_null":
            for v in values:
                if v is not None:
                    return v
            return None
        elif strategy == "last_wins":
            return values[-1] if values else None
        elif strategy == "merge_lists":
            result: list[Any] = []
            for v in values:
                if isinstance(v, list):
                    result.extend(v)
                elif v is not None:
                    result.append(v)
            return result
        elif strategy == "concatenate":
            return "".join(str(v) for v in values if v is not None)
        elif strategy == "average":
            numeric = [v for v in values if isinstance(v, (int, float))]
            return sum(numeric) / len(numeric) if numeric else None
        return values[-1] if values else None
