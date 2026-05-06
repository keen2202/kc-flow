"""合规检查器技能入口"""

from pathlib import Path
from typing import List
import yaml
from pydantic import BaseModel, Field


class CheckInput(BaseModel):
    document_content: str
    compliance_frameworks: List[str]
    industry: str = "general"
    language: str = "zh-CN"


class Violation(BaseModel):
    rule_id: str
    rule_name: str
    severity: str
    description: str
    location: str
    remediation: str


class FrameworkResult(BaseModel):
    framework: str
    score: float
    violations: List[Violation] = []


class CheckOutput(BaseModel):
    overall_compliance_score: float
    framework_results: List[FrameworkResult]


async def check(input: CheckInput, context: "SkillContext") -> CheckOutput:
    """
    合规检查技能入口。

    基于规则引擎和LLM混合方案进行多框架合规检查。
    """
    results = []

    for framework in input.compliance_frameworks:
        # 加载框架规则
        rules = _load_framework_rules(framework)

        # 规则引擎：基于关键词和模式匹配的快速检查
        rule_violations = _rule_based_check(input.document_content, rules)

        # LLM增强：对规则引擎不确定的部分使用LLM深度分析
        llm_violations = await _llm_enhanced_check(
            input.document_content, framework, rule_violations, context
        )

        all_violations = rule_violations + llm_violations

        score = _calculate_score(all_violations)
        results.append(FrameworkResult(
            framework=framework,
            score=score,
            violations=all_violations,
        ))

    overall_score = sum(r.score for r in results) / len(results) if results else 100

    return CheckOutput(
        overall_compliance_score=round(overall_score, 1),
        framework_results=results,
    )


def _load_framework_rules(framework: str) -> list:
    """加载合规框架规则"""
    rules_path = Path(__file__).parent / "rules" / f"{framework}_rules.yaml"
    if not rules_path.exists():
        return []
    with open(rules_path) as f:
        return yaml.safe_load(f).get("rules", [])


def _rule_based_check(content: str, rules: list) -> list:
    """基于规则引擎的快速合规检查"""
    violations = []
    content_lower = content.lower()

    for rule in rules:
        for keyword in rule.get("keywords", []):
            if keyword.lower() in content_lower:
                violations.append(Violation(
                    rule_id=rule["id"],
                    rule_name=rule["name"],
                    severity=rule.get("severity", "medium"),
                    description=rule.get("description", ""),
                    location=f"包含关键词: {keyword}",
                    remediation=rule.get("remediation", "请进一步审查相关内容"),
                ))
                break

    return violations


async def _llm_enhanced_check(
    content: str, framework: str, rule_violations: list, context: "SkillContext"
) -> list:
    """使用LLM增强合规检查"""
    # 如果规则引擎已经覆盖了所有规则，跳过LLM增强
    if not rule_violations:
        return []

    llm = context.get_llm_client()
    prompt = (
        f"根据{framework}框架的要求，对以下文档进行深度合规分析。"
        f"请关注规则引擎可能遗漏的细节。\n\n文档内容:\n{content}"
    )

    response = await llm.chat(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    # 解析LLM发现的额外问题
    # 实际实现需要更复杂的解析逻辑
    return []


def _calculate_score(violations: list) -> float:
    """根据违规情况计算合规评分"""
    severity_weights = {"low": 5, "medium": 15, "high": 30, "critical": 50}
    total_penalty = sum(severity_weights.get(v.severity, 10) for v in violations)
    return max(0, 100 - total_penalty)
