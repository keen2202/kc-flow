"""风险分析器技能入口"""

from datetime import datetime, timezone
from typing import List
from pydantic import BaseModel, Field


class AnalyzeInput(BaseModel):
    document_content: str
    document_type: str = "PPM"
    language: str = "zh-CN"
    risk_threshold: float = 0.7


class RiskItem(BaseModel):
    clause_ref: str
    risk_type: str
    severity: str
    description: str
    recommendation: str


class AnalyzeOutput(BaseModel):
    risk_score: float
    risk_level: str
    risk_items: List[RiskItem]
    summary: str
    analyzed_at: str


async def analyze(input: AnalyzeInput, context: "SkillContext") -> AnalyzeOutput:
    """
    文档风险分析技能入口。

    使用LLM进行智能风险识别，结合规则引擎进行合规检查。
    """
    context.logger.info(f"Starting risk analysis for {input.document_type} document")

    prompt_template = context.load_template("extract_prompt.jinja2")

    llm = context.get_llm_client(model="gpt-4o")

    response = await llm.chat(
        messages=[
            {
                "role": "system",
                "content": prompt_template.render(
                    document_type=input.document_type,
                    language=input.language,
                ),
            },
            {"role": "user", "content": input.document_content},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    result = AnalyzeOutput.model_validate_json(response.content)
    result.analyzed_at = datetime.now(timezone.utc).isoformat()

    if result.risk_score >= input.risk_threshold:
        context.logger.warning(
            f"High risk detected: score={result.risk_score}, level={result.risk_level}"
        )

    context.record_metric("risk_score", result.risk_score, {"document_type": input.document_type})

    return result
