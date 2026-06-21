"""Render stock analysis reports to multiple export formats."""

from __future__ import annotations

import html
import io
import re
import zipfile
from pathlib import Path
from typing import Any

from app.services.stock_analysis.report_builder import COMPAT_REPORT_KEY


class StockAnalysisExporter:
    """Export reports as Markdown, HTML, DOCX, and PDF."""

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
        stage_order = [
            "market_report",
            "news_report",
            "fundamentals_report",
            "sentiment_report",
            "investment_plan",
            "trader_investment_plan",
            "final_trade_decision",
            "bull_researcher",
            "bear_researcher",
            "research_team_decision",
            "risky_analyst",
            "safe_analyst",
            "neutral_analyst",
            "risk_management_decision",
        ]
        lines = [
            f"# {symbol} 股票分析报告",
            "",
            f"分析日期: {meta.get('analysis_date', '')}",
            "分析师: market, fundamentals, news",
            f"研究深度: {meta.get('research_depth', '')}",
            "",
            "## 执行摘要",
            "",
            str(report.get("executive_summary") or ""),
            "",
            "## 结构化决策摘要",
            "",
            f"最终建议: {decision.get('label', '持有')}",
            f"目标价位: {decision.get('target_price', 'N/A')}",
            f"置信度: {decision.get('confidence_score', 0.5)}",
            f"风险等级: {decision.get('risk_level', '中等')}",
            f"风险评分: {decision.get('risk_score', 0.5)}",
            "",
            str(decision.get("reasoning") or ""),
            "",
            "## 兼容阶段输出",
            "",
        ]
        rendered = set()
        for key in stage_order:
            value = compat.get(key)
            if not value:
                continue
            rendered.add(key)
            lines.extend([f"## {key}", "", str(value), ""])
        for key, value in compat.items():
            if key in rendered or not value:
                continue
            lines.extend([f"## {key}", "", str(value), ""])
        lines.extend([
            "## 数据质量、限制与免责声明",
            "",
            *(f"- {item}" for item in report.get("limitations") or []),
            "",
            str(report.get("disclaimer") or "本报告仅供研究参考，不构成投资建议。"),
            "",
        ])
        return "\n".join(lines)

    def render_html(self, report: dict[str, Any]) -> str:
        md = self.render_markdown(report)
        body = []
        for line in md.splitlines():
            escaped = html.escape(line)
            if line.startswith("# "):
                body.append(f"<h1>{escaped[2:]}</h1>")
            elif line.startswith("## "):
                body.append(f"<h2>{escaped[3:]}</h2>")
            elif line.startswith("### "):
                body.append(f"<h3>{escaped[4:]}</h3>")
            elif line.startswith("- "):
                body.append(f"<p>{escaped}</p>")
            elif line.strip():
                body.append(f"<p>{escaped}</p>")
            else:
                body.append("")
        return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>股票分析报告</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height: 1.75; margin: 40px; color: #1f2937; }
    h1, h2, h3 { color: #111827; page-break-after: avoid; }
    p { margin: 0.55rem 0; }
  </style>
</head>
<body>
""" + "\n".join(body) + "\n</body>\n</html>\n"

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

            return HTML(string=self.render_html(report)).write_pdf()
        except Exception:
            return self._render_minimal_pdf(report)

    def _render_minimal_pdf(self, report: dict[str, Any]) -> bytes:
        text = self.render_markdown(report)
        ascii_text = html.escape(text[:3000]).encode("ascii", "ignore").decode("ascii")
        stream = f"BT /F1 10 Tf 40 780 Td ({self._pdf_escape(ascii_text[:1800])}) Tj ET"
        objects = [
            b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
            b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
            b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
            b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
            f"5 0 obj << /Length {len(stream.encode('latin-1'))} >> stream\n{stream}\nendstream endobj".encode(
                "latin-1"
            ),
        ]
        buffer = io.BytesIO()
        buffer.write(b"%PDF-1.4\n")
        offsets = [0]
        for obj in objects:
            offsets.append(buffer.tell())
            buffer.write(obj + b"\n")
        xref = buffer.tell()
        buffer.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode("ascii"))
        for offset in offsets[1:]:
            buffer.write(f"{offset:010d} 00000 n \n".encode("ascii"))
        buffer.write(
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode(
                "ascii"
            )
        )
        return buffer.getvalue()

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
        return """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
""" + "\n".join(paragraphs) + """
  </w:body>
</w:document>"""

    @staticmethod
    def _pdf_escape(text: str) -> str:
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").replace("\n", " ")

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
