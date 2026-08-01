"""Render stock analysis reports to multiple export formats."""

from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from typing import Any

from markdown_it import MarkdownIt

from app.services.stock_analysis.report_builder import COMPAT_REPORT_KEY


class StockAnalysisExporter:
    """Export reports as Markdown, HTML, DOCX, and PDF."""

    STAGE_TITLES = {
        "market_report": "技术与市场分析",
        "news_report": "新闻与情绪",
        "fundamentals_report": "基本面分析",
        "sentiment_report": "社媒情绪",
        "investment_plan": "多空研究与投资计划",
        "trader_investment_plan": "交易员计划",
        "final_trade_decision": "风险评估与终审",
        "bull_researcher": "多头研究观点",
        "bear_researcher": "空头研究观点",
        "research_team_decision": "研究团队裁决",
        "risky_analyst": "激进风险分析",
        "safe_analyst": "稳健风险分析",
        "neutral_analyst": "中性风险分析",
        "risk_management_decision": "风险经理裁决",
    }

    CONTENT_TYPES = {
        "markdown": "text/markdown; charset=utf-8",
        "html": "text/html; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }

    EXTENSIONS = {
        "markdown": "md",
        "html": "html",
        "docx": "docx",
        "pdf": "pdf",
    }

    def render(self, report: dict[str, Any], export_format: str) -> bytes:
        if export_format == "markdown":
            return self.render_markdown(report).encode("utf-8")
        if export_format == "html":
            return self.render_html(report).encode("utf-8")
        if export_format == "docx":
            return self.render_docx(report)
        if export_format == "pdf":
            return self.render_pdf(report)
        raise ValueError(f"Unsupported export format: {export_format}")

    def render_markdown(self, report: dict[str, Any]) -> str:
        meta = report.get("meta") or {}
        decision = report.get("decision") or {}
        symbol = self._display_symbol(str(meta.get("symbol") or ""))
        compat = report.get(COMPAT_REPORT_KEY) or {}
        stage_order = list(self.STAGE_TITLES)
        lines = [
            f"# {symbol} 股票分析报告",
            "",
            f"分析日期: {meta.get('analysis_date', '')}",
            "分析师: market, fundamentals, news",
            f"研究深度: {meta.get('research_depth', '')}",
            "",
            "## 执行摘要",
            "",
            self._nest_markdown_headings(report.get("executive_summary") or "", level=3),
            "",
            "## 结构化决策摘要",
            "",
            f"最终建议: {decision.get('label', '观望')}",
            f"目标价位: {decision.get('target_price', 'N/A')}",
            f"置信度: {decision.get('confidence_score', 0.5)}",
            f"风险等级: {decision.get('risk_level', '中等')}",
            f"风险评分: {decision.get('risk_score', 0.5)}",
            "",
            self._nest_markdown_headings(decision.get("reasoning") or "", level=3),
            "",
        ]
        rendered = set()
        for key in stage_order:
            value = compat.get(key)
            if not value:
                continue
            rendered.add(key)
            lines.extend(
                [
                    f"## {self.STAGE_TITLES[key]}",
                    "",
                    self._nest_markdown_headings(value, level=3),
                    "",
                ]
            )
        for key, value in compat.items():
            if key in rendered or not value:
                continue
            lines.extend(
                [
                    f"## {key.replace('_', ' ').title()}",
                    "",
                    self._nest_markdown_headings(value, level=3),
                    "",
                ]
            )
        lines.extend(
            [
                "## 数据质量、限制与免责声明",
                "",
                *(f"- {item}" for item in report.get("limitations") or []),
                "",
                str(report.get("disclaimer") or "本报告仅供研究参考，不构成投资建议。"),
                "",
            ]
        )
        return "\n".join(lines)

    def render_html(self, report: dict[str, Any]) -> str:
        body = self._markdown_renderer().render(self.render_markdown(report))
        return (
            """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>股票分析报告</title>
  <style>
    @page { size: A4; margin: 18mm 15mm; }
    body { font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", "Noto Sans CJK SC", "Source Han Sans SC", sans-serif; font-size: 11pt; line-height: 1.75; margin: 0; color: #1f2937; word-break: break-word; }
    h1, h2, h3, h4, h5, h6 { color: #111827; page-break-after: avoid; }
    h1 { font-size: 24pt; border-bottom: 2px solid #2563eb; padding-bottom: 0.35rem; }
    h2 { font-size: 17pt; margin-top: 1.8rem; border-left: 4px solid #2563eb; padding-left: 0.6rem; }
    h3 { font-size: 14pt; margin-top: 1.4rem; }
    p { margin: 0.55rem 0; }
    ul, ol { padding-left: 1.6rem; }
    li { margin: 0.25rem 0; }
    table { width: 100%; border-collapse: collapse; margin: 1rem 0; page-break-inside: avoid; }
    th, td { border: 1px solid #d1d5db; padding: 0.45rem 0.6rem; text-align: left; vertical-align: top; }
    th { background: #eff6ff; font-weight: 600; }
    pre { background: #f3f4f6; border-radius: 6px; padding: 0.9rem; overflow-wrap: anywhere; white-space: pre-wrap; }
    code { font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace; }
    blockquote { border-left: 4px solid #93c5fd; color: #4b5563; margin: 1rem 0; padding-left: 1rem; }
    a { color: #2563eb; }
  </style>
</head>
<body>
"""
            + body
            + "\n</body>\n</html>\n"
        )

    def render_docx(self, report: dict[str, Any]) -> bytes:
        document_xml = self._docx_document_xml(self.render_markdown(report))
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
            )
            zf.writestr(
                "_rels/.rels",
                """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>""",
            )
            zf.writestr("word/document.xml", document_xml)
        return output.getvalue()

    def render_pdf(self, report: dict[str, Any]) -> bytes:
        try:
            from weasyprint import HTML
        except ImportError as exc:
            raise RuntimeError("PDF export requires the weasyprint dependency") from exc
        return HTML(string=self.render_html(report)).write_pdf()

    def build_file_name(self, report: dict[str, Any], export_format: str) -> str:
        meta = report.get("meta") or {}
        symbol = self._safe_file_part(
            self._display_symbol(str(meta.get("symbol") or "stock")),
            fallback="stock",
        )
        analysis_date = self._safe_file_part(
            str(meta.get("analysis_date") or "analysis"),
            fallback="analysis",
        )
        return f"{symbol}_分析报告_{analysis_date}.{self.EXTENSIONS[export_format]}"

    def save(self, content: bytes, *, user_id: str, report_id: str, file_name: str) -> Path:
        output_dir = Path("data") / "exports" / "stock-analysis" / user_id / report_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / file_name
        output_path.write_bytes(content)
        return output_path

    def _docx_document_xml(self, markdown_text: str) -> str:
        paragraphs = []
        for line in markdown_text.splitlines():
            text = html.escape(line.strip())
            if not text:
                continue
            paragraphs.append(f"<w:p><w:r><w:t>{text}</w:t></w:r></w:p>")
        return (
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
"""
            + "\n".join(paragraphs)
            + """
  </w:body>
</w:document>"""
        )

    @staticmethod
    def _safe_file_part(value: str, *, fallback: str) -> str:
        sanitized = re.sub(r"[^A-Za-z0-9._-]+", "_", value).strip("._-")
        return sanitized[:80] or fallback

    @staticmethod
    def _display_symbol(value: str) -> str:
        normalized = str(value or "").strip().upper()
        match = re.fullmatch(r"(\d{6})\.(?:SZ|SH)", normalized)
        if match:
            return match.group(1)
        return normalized or "stock"

    @staticmethod
    def _nest_markdown_headings(value: Any, *, level: int) -> str:
        """Nest an AI Markdown fragment under a report section without losing its structure."""
        text = str(value or "").replace("\r\n", "\n").strip()
        if not text:
            return ""
        heading_pattern = re.compile(r"^(#{1,6})(\s+)", re.MULTILINE)
        source_levels = [len(match.group(1)) for match in heading_pattern.finditer(text)]
        if not source_levels:
            return text
        source_base = min(source_levels)

        def replace_heading(match: re.Match[str]) -> str:
            source_level = len(match.group(1))
            nested_level = min(6, level + source_level - source_base)
            return f"{'#' * nested_level}{match.group(2)}"

        return heading_pattern.sub(replace_heading, text)

    @staticmethod
    def _markdown_renderer() -> MarkdownIt:
        """Return the safe CommonMark renderer used for HTML and PDF exports."""
        return MarkdownIt("commonmark", {"html": False}).enable("table").enable("strikethrough")
