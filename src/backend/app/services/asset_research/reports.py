"""Deterministic report rendering for public multi-asset research decisions."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from app.schemas.asset_research import (
    InstrumentIdentity,
    RawAssetSnapshot,
    ReportSection,
    ResearchDecision,
)

# These chapter contracts come directly from the six asset requirement
# documents.  IDs are stable export/evidence keys, rather than translated
# headings, so report revisions can remain comparable across locales.
_ASSET_REPORT_OUTLINES: dict[str, tuple[tuple[str, str], ...]] = {
    "bond": (
        ("identity_terms", "债券身份、市场和关键条款"),
        ("public_decision", "公开建议"),
        ("source_quality", "数据日期、来源和完整性"),
        ("valuation", "净价/全价、YTM/YTW 和相对估值"),
        ("curve_carry", "曲线、carry 和 roll-down"),
        ("rates_risk", "久期、凸性、DV01 和利率情景"),
        ("credit", "信用、偿债、契约和评级变化"),
        ("liquidity", "流动性、bid-ask、成交与估值可执行性"),
        ("embedded_options", "含权和提前偿还风险"),
        ("macro_events", "宏观与近期事件"),
        ("scenarios", "牛/基准/熊总回报情景"),
        ("thesis", "正方、反方证据和失效条件"),
        ("history", "历史预测、成熟样本和质量"),
        ("risk_method", "风险提示与方法版本"),
    ),
    "fund": (
        ("identity_mechanism", "基金身份、份额类别、类型和交易机制"),
        ("public_decision", "公开建议"),
        ("mandate_benchmark", "投资目标、合同约束和正式基准"),
        ("nav_market", "NAV、累计 NAV、分红和场内价格"),
        ("relative_return", "历史总回报与基准净超额"),
        ("risk", "波动、回撤、下行和风险调整表现"),
        ("holdings", "持仓、配置、集中、风格和漂移"),
        ("management", "基金经理、团队、任期和组织变化"),
        ("fees", "费用、税务和份额类别差异"),
        ("flows_liquidity", "规模、资金流、申赎和流动性"),
        ("etf_quality", "ETF 溢折价、PCF、IOPV 和跟踪质量"),
        ("scenarios", "情景、催化剂、风险和失效条件"),
        ("source_quality", "数据质量、披露滞后和来源"),
        ("history", "历史预测和分层统计"),
        ("compliance", "合规风险提示"),
    ),
    "futures": (
        ("public_decision", "观点、动作、置信度和资格"),
        ("contract_mapping", "真实合约、连续序列、映射和换月"),
        ("market_state", "趋势、波动、成交和持仓"),
        ("curve_basis", "期限结构、基差和 carry"),
        ("supply_demand", "现货、库存、仓单、供需和季节"),
        ("cot", "会员持仓/COT 及局限"),
        ("fundamentals", "品种专属基本面"),
        ("margin_risk", "保证金、涨跌停、杠杆和压力情景"),
        ("expiry_liquidity", "到期、交割、换月和流动性"),
        ("catalysts", "催化剂和新闻证据"),
        ("position_matrix", "结论和持仓条件动作矩阵"),
        ("history", "历史预测、样本和成本后表现"),
        ("source_version", "数据、时点、策略和模型版本"),
    ),
    "option": (
        ("identity_underlying", "精确合约身份和标的"),
        ("public_decision", "公开建议"),
        ("terms", "条款、行权和结算"),
        ("underlying_market", "标的行情和催化剂"),
        ("chain_liquidity", "期权链流动性"),
        ("iv_surface", "IV 期限、微笑/偏度和曲面质量"),
        ("valuation", "理论价、市场价和模型误差"),
        ("greeks", "Greeks 风险"),
        ("payoff", "到期盈亏、盈亏平衡、最大损失和压力"),
        ("suitability", "策略适用性与有限风险替代"),
        ("expiry_risk", "到期、行权、指派、流动性和保证金风险"),
        ("history", "历史预测和三个 head 的独立准确率及四类经济结果"),
        ("source_version", "来源、估值时点、模型和策略版本"),
    ),
    "fx": (
        ("identity_settlement", "产品身份、报价方向和结算"),
        ("public_decision", "公开建议"),
        ("market_state", "趋势、波动和技术状态"),
        ("macro", "两国宏观与货币政策差异"),
        ("carry", "carry、远期曲线和基差"),
        ("positioning", "机构头寸、事件和新闻"),
        ("liquidity", "流动性、spread、融资和可执行成本"),
        ("scenarios", "多头/基准/空头情景、催化剂和失效"),
        ("risk_compliance", "杠杆、对手方、结算和地区合规"),
        ("source_quality", "数据质量、来源和截止时间"),
        ("history", "历史预测、期限质量和样本"),
    ),
    "crypto": (
        ("identity_product", "资产、链、合约地址、场所和产品"),
        ("public_decision", "公开建议"),
        ("market", "跨场所价格、趋势和流动性"),
        ("microstructure", "波动、深度和微观结构"),
        ("derivatives", "funding、basis、OI、清算和期权状态"),
        ("onchain", "链上活动、供给和持币结构"),
        ("tokenomics", "tokenomics、收入、治理、升级和解锁"),
        ("events", "新闻、监管、攻击和生态事件"),
        ("custody_risk", "托管、场所、稳定币、oracle、bridge 和合约风险"),
        ("scenarios", "情景、催化剂、失效和风险预算"),
        ("source_quality", "数据质量、来源、cutoff 和资产解析"),
        ("history", "历史信号、分产品/期限质量和样本"),
    ),
}


def asset_report_outline(asset_type: str) -> tuple[tuple[str, str], ...]:
    """Return the frozen public chapter outline for one supported asset type."""
    try:
        return _ASSET_REPORT_OUTLINES[asset_type]
    except KeyError as exc:
        raise ValueError("ASSET_REPORT_OUTLINE_UNKNOWN") from exc


def build_asset_report_sections(
    *, snapshot: RawAssetSnapshot, published_decision: ResearchDecision
) -> list[ReportSection]:
    """Build public-only asset chapters without exposing candidate signal data.

    The deterministic skeleton gives every consumer a stable section order.
    Asset adapters may enrich the public ``asset_details`` and evidence IDs;
    missing data is rendered as missing rather than being converted into zero
    or an invented narrative.
    """
    details = (
        published_decision.asset_details.model_dump(mode="json")
        if published_decision.asset_details is not None
        else {}
    )
    source = snapshot.source_manifest
    source_id = str(source.get("source_id") or source.get("provider") or "未登记来源")
    source_snapshot_evidence_id = _content_addressed_evidence_id(
        "source_snapshot",
        snapshot.content_hash,
        {"source_id": source_id},
    )
    decision_evidence_id = _content_addressed_evidence_id(
        "published_decision",
        snapshot.content_hash,
        published_decision.model_dump(mode="json"),
    )
    quality_evidence_id = _content_addressed_evidence_id(
        "quality",
        snapshot.content_hash,
        {"reason_codes": published_decision.reason_codes},
    )
    detail_evidence_ids = _detail_evidence_ids(snapshot.content_hash, details)
    facts = _safe_detail_facts(details, detail_evidence_ids)
    quality_text = "；".join(published_decision.reason_codes) or "当前未记录额外质量否决"
    decision_text = (
        f"公开建议：{published_decision.recommendation}；可行动性："
        f"{published_decision.actionability}；期限：{published_decision.horizon_code}；"
        f"研究动作：{published_decision.trade_intent}。"
        f"（证据 ID：{decision_evidence_id}）"
    )
    source_text = (
        f"分析截止：{snapshot.cutoff_at.isoformat()}；来源：{source_id}；"
        f"许可状态：{source.get('license_status') or 'UNKNOWN'}；质量说明：{quality_text}。"
        f"（来源证据 ID：{source_snapshot_evidence_id}；"
        f"质量证据 ID：{quality_evidence_id}）"
    )
    standard_text = (
        "本章节仅基于截止前冻结且允许公开的结构化事实生成。"
        f"当前公开字段：{facts or '无可公开的资产专属字段'}；"
        "缺失信息保持缺失，不以 0、候选方向或未验证叙述补齐。"
    )
    sections: list[ReportSection] = []
    for section_id, title in asset_report_outline(snapshot.identity.asset_type):
        if section_id == "public_decision":
            markdown = decision_text
            evidence_ids = [decision_evidence_id]
        elif section_id == "source_quality":
            markdown = source_text
            evidence_ids = [source_snapshot_evidence_id, quality_evidence_id]
        else:
            markdown = standard_text
            evidence_ids = [source_snapshot_evidence_id, *detail_evidence_ids.values()]
        sections.append(
            ReportSection(
                section_id=section_id, title=title, markdown=markdown, evidence_ids=evidence_ids
            )
        )
    return sections


def _detail_evidence_ids(snapshot_content_hash: str, details: dict[str, Any]) -> dict[str, str]:
    """Create immutable field-level evidence IDs for public scalar report facts.

    A report can safely show public derived values, but an auditor must be able
    to bind each value to the exact frozen source snapshot that produced it.
    The ID therefore covers the source snapshot hash, field name and rendered
    value.  It does not reveal any raw provider payload.
    """
    evidence_ids: dict[str, str] = {}
    for key, value in sorted(details.items()):
        if key == "kind" or value is None or isinstance(value, (dict, list)):
            continue
        if isinstance(value, (str, int, float, bool)):
            evidence_ids[key] = _content_addressed_evidence_id(
                "detail", snapshot_content_hash, {"field": key, "value": value}
            )
    return evidence_ids


def _safe_detail_facts(details: dict[str, Any], evidence_ids: dict[str, str]) -> str:
    """Serialize public scalar details with their immutable evidence IDs."""
    values: list[str] = []
    for key in sorted(evidence_ids):
        values.append(f"{key}={details[key]}（证据 ID：{evidence_ids[key]}）")
    return "；".join(values)


def _content_addressed_evidence_id(
    evidence_kind: str, snapshot_content_hash: str, payload: dict[str, Any]
) -> str:
    """Return a stable public evidence key without exposing raw source fields."""
    canonical_payload = json.dumps(
        {
            "evidence_kind": evidence_kind,
            "snapshot_content_hash": snapshot_content_hash,
            "payload": payload,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return f"{evidence_kind}:{sha256(canonical_payload.encode('utf-8')).hexdigest()}"


def build_report_payload(
    *,
    identity: InstrumentIdentity,
    published_decision: ResearchDecision,
    sections: list[ReportSection],
) -> dict[str, Any]:
    """Build the public report payload without exposing a candidate decision."""
    return {
        "meta": {
            "asset_type": identity.asset_type,
            "canonical_id": identity.canonical_id,
            "display_symbol": identity.display_symbol,
            "name": identity.name,
            "metadata_version": identity.metadata_version,
        },
        "published_decision": published_decision.model_dump(mode="json"),
        "sections": [section.model_dump(mode="json") for section in sections],
        "disclaimer": "本报告仅供研究参考，不构成投资建议；系统不连接账户或创建订单。",
    }


def render_markdown(payload: dict[str, Any]) -> str:
    """Render a stable, export-ready Markdown view from the public payload."""
    meta = payload["meta"]
    decision = payload["published_decision"]
    lines = [
        f"# {meta['name']}（{meta['display_symbol']}）研究报告",
        "",
        f"- 资产类型：{meta['asset_type']}",
        f"- 规范标识：{meta['canonical_id']}",
        f"- 公开建议：{decision['recommendation']}",
        f"- 可行动性：{decision['actionability']}",
        "",
    ]
    for section in payload["sections"]:
        lines.extend((f"## {section['title']}", "", section["markdown"], ""))
    lines.extend(("## 免责声明", "", payload["disclaimer"], ""))
    return "\n".join(lines)
