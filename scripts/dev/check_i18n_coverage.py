#!/usr/bin/env python3
"""Iteration 175 §4 — i18n coverage lint and locale parity check.

Two modes:
  --strict        scan .vue / .ts under src/frontend/src for hard-coded user-
                  visible strings (CJK literals or English text >= 4 chars in
                  template / Element Plus prop / ElMessage* call positions).
  --check-parity  compare the dotted key set between zh-CN and en-US locales.

Both modes exit 0 on success, 1 on detected issues.

Exemption support (Requirement 4.4):
  - "// i18n-ignore-next-line"        on the line immediately preceding the
    offending source line (Vue <script setup> and .ts files).
  - "<!-- i18n-ignore-next-line -->"  on the line immediately preceding the
    offending Vue <template> line.
  - Each exemption MUST be adjacent to a "i18n-reason: <reason>" comment in
    the same block; reason length must be 5..120 characters; otherwise the
    exemption is invalid and the violation is reported regardless.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_SRC = REPO_ROOT / "src" / "frontend" / "src"
LOCALE_FILES = {
    "zh-CN": FRONTEND_SRC / "i18n" / "locales" / "zh-CN.ts",
    "en-US": FRONTEND_SRC / "i18n" / "locales" / "en-US.ts",
}

# Identify CJK-Unified-Ideograph blocks and "user-visible" English text.
CJK = re.compile(r"[\u4e00-\u9fff]+")
# Non-trivial English literal: starts with a letter, total visible chars >= 4.
EN_TEXT = re.compile(r"[A-Za-z][A-Za-z0-9 _\-,.!?'/&%:]{3,}")

IGNORE_LINE_TS = "i18n-ignore-next-line"
REASON_PREFIX = "i18n-reason:"
REASON_MIN = 5
REASON_MAX = 120


@dataclass(frozen=True)
class Violation:
    path: Path
    line: int
    snippet: str
    suggested_key: str
    kind: str  # 'cjk' | 'en'


def _suggested_key(path: Path, line: int, snippet: str) -> str:
    parts = list(path.relative_to(REPO_ROOT).parts)
    # Drop fixed prefix "src" "frontend" "src" if present.
    cleanish = [p for p in parts if p not in {"src", "frontend"}]
    module = cleanish[0] if cleanish else "common"
    page = cleanish[-1].split(".")[0] if cleanish else "page"
    # Element identifier: short slug from snippet's leading word(s).
    snippet_clean = re.sub(r"[^A-Za-z\u4e00-\u9fff0-9]+", "_", snippet).strip("_").lower()
    elem = (snippet_clean[:24] or "text") + f"_l{line}"
    key = f"{module}.{page}.{elem}".replace("-", "_")
    if len(key) > 80:
        key = key[:80]
    return key


def _exemption_ok(prev_lines: list[str]) -> bool:
    """Return True iff the previous line(s) include a valid ignore + reason."""
    saw_ignore = False
    saw_reason = False
    for line in prev_lines:
        if IGNORE_LINE_TS in line:
            saw_ignore = True
        if REASON_PREFIX in line:
            # Extract reason text after prefix
            idx = line.index(REASON_PREFIX) + len(REASON_PREFIX)
            reason = line[idx:].rstrip("-> */}").strip()
            if REASON_MIN <= len(reason) <= REASON_MAX:
                saw_reason = True
    return saw_ignore and saw_reason


def _scan_file(path: Path) -> list[Violation]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    violations: list[Violation] = []

    # Block-level state — only surface findings inside <template>, <script>,
    # ElMessage* call positions, and Element Plus label/placeholder props.
    in_template = path.suffix != ".vue"  # .ts files: always "in code"
    in_script = path.suffix == ".ts"

    for idx, raw in enumerate(lines, start=1):
        if path.suffix == ".vue":
            stripped = raw.lstrip()
            if stripped.startswith("<template"):
                in_template = True
                continue
            if stripped.startswith("</template"):
                in_template = False
                continue
            if stripped.startswith("<script"):
                in_script = True
                continue
            if stripped.startswith("</script"):
                in_script = False
                continue

        # Restrict scan zones.
        applies = False
        if in_template:
            applies = True
        elif in_script:
            # Only ElMessage / ElMessageBox / ElNotification first-arg lines.
            if re.search(r"\bEl(Message|MessageBox|Notification)\s*[(.\u00a0]", raw):
                applies = True
            # Or label="..."/ placeholder="..." in script (programmatic builds).
            if re.search(r"\b(label|placeholder)\s*[:=]\s*['\"`]", raw):
                applies = True

        if not applies:
            continue

        # Skip heavy comment-only lines.
        if raw.strip().startswith("//") or raw.strip().startswith("/*"):
            continue
        if raw.strip().startswith("*") and not raw.strip().startswith("*/"):
            continue

        # Find candidate matches.
        cjk_match = CJK.search(raw)
        en_match = None if cjk_match else EN_TEXT.search(raw)
        if not cjk_match and not en_match:
            continue

        # Skip if the literal is wrapped in a $t/t/i18n.t call already.
        if re.search(r"\b(?:\$t|i18n\.t|t)\(", raw):
            # Heuristic: assume any line with a $t/t() call is internationalised.
            # This drops some false negatives but reduces noise massively.
            continue

        # Skip if the line uses a known a-tag href/src/path-only literal.
        if re.search(r"(?:href|src|path|to|name|id)\s*=\s*['\"`][\w/\-.:]+['\"`]\s*$", raw):
            continue

        # Check exemption against the previous 2 lines (allow comment then
        # ignore directive on the same block).
        prev_window = lines[max(0, idx - 3) : idx - 1]
        if _exemption_ok(prev_window):
            continue

        snippet = (cjk_match.group(0) if cjk_match else en_match.group(0))[:80]
        kind = "cjk" if cjk_match else "en"
        violations.append(
            Violation(
                path=path,
                line=idx,
                snippet=snippet,
                suggested_key=_suggested_key(path, idx, snippet),
                kind=kind,
            )
        )
    return violations


def cmd_strict() -> int:
    candidates = sorted(
        list(FRONTEND_SRC.rglob("*.vue")) + list(FRONTEND_SRC.rglob("*.ts"))
    )
    # Skip locale + test/setup directories.
    skip_dirs = {"i18n", "__tests__", "test", "test-helpers"}
    candidates = [
        p
        for p in candidates
        if not any(part in skip_dirs for part in p.parts)
        and not p.name.endswith(".d.ts")
    ]

    total: list[Violation] = []
    for path in candidates:
        total.extend(_scan_file(path))

    for v in total:
        rel = v.path.relative_to(REPO_ROOT)
        print(
            json.dumps(
                {
                    "file": str(rel),
                    "line": v.line,
                    "kind": v.kind,
                    "snippet": v.snippet,
                    "suggested_key": v.suggested_key,
                }
            )
        )
    print(f"summary: {len(total)} violations", flush=True)
    return 0 if not total else 1


def _load_locale(path: Path) -> dict:
    """Parse a TypeScript `export default { ... }` locale file via Node + JSON.

    We use Node to evaluate the module so we don't have to write a full TS
    parser. Falls back to a regex-based key extraction if Node is unavailable.
    """
    if not path.exists():
        raise FileNotFoundError(path)

    node_script = (
        "const path=require('path');"
        "(async()=>{"
        "  const mod=await import(path.resolve(process.argv[1]));"
        "  process.stdout.write(JSON.stringify(mod.default||mod));"
        "})()"
    )
    try:
        out = subprocess.run(
            [
                "node",
                "--experimental-vm-modules",
                "--input-type=module",
                "-e",
                node_script,
                str(path),
            ],
            capture_output=True,
            check=False,
            timeout=20,
        )
        if out.returncode == 0 and out.stdout.strip():
            return json.loads(out.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    # Fallback: regex-extract dotted keys (less precise, but Parity check
    # only needs the key set).
    return _regex_extract_keys(path)


def _regex_extract_keys(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    # Strip comments.
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)

    # Walk braces to recover nested keys.
    keys: list[str] = []
    stack: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "{":
            stack.append("")
            i += 1
            continue
        if ch == "}":
            if stack:
                stack.pop()
            i += 1
            continue
        m = re.match(r"\s*([A-Za-z_][\w-]*|'[^']+'|\"[^\"]+\")\s*:\s*", text[i:])
        if m:
            raw_key = m.group(1).strip("'\"")
            keys.append(".".join([*[k for k in stack if k], raw_key]))
            # Advance past the key: char.
            i += m.end()
            # If RHS is a string literal, skip it; otherwise leave the
            # walker to descend into nested object on the next iteration.
            if i < len(text) and text[i] in {"'", '"', "`"}:
                quote = text[i]
                j = i + 1
                while j < len(text) and text[j] != quote:
                    if text[j] == "\\":
                        j += 2
                    else:
                        j += 1
                i = j + 1
            continue
        i += 1

    # Fold the flat keys into a dict so the caller can flatten consistently.
    out: dict = {}
    for full in keys:
        cur = out
        parts = full.split(".")
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = ""
    return out


def _flatten(d: dict, prefix: str = "") -> set[str]:
    out: set[str] = set()
    for k, v in d.items():
        full = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out |= _flatten(v, full)
        else:
            out.add(full)
    return out


def cmd_check_parity() -> int:
    zh = _flatten(_load_locale(LOCALE_FILES["zh-CN"]))
    en = _flatten(_load_locale(LOCALE_FILES["en-US"]))
    only_zh = sorted(zh - en)
    only_en = sorted(en - zh)
    if not only_zh and not only_en:
        print("OK: zh-CN and en-US locale key sets identical")
        print(f"summary: 0 parity violations  ({len(zh)} keys each side)")
        return 0
    if only_zh:
        print("only-in-zh:")
        for k in only_zh:
            print(f"  {k}")
    if only_en:
        print("only-in-en:")
        for k in only_en:
            print(f"  {k}")
    print(f"summary: {len(only_zh) + len(only_en)} parity violations")
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description="i18n coverage / parity lint")
    p.add_argument("--strict", action="store_true", help="run scan mode")
    p.add_argument("--check-parity", action="store_true", help="run parity mode")
    args = p.parse_args()

    if not args.strict and not args.check_parity:
        p.print_help(sys.stderr)
        return 2

    rc = 0
    if args.strict:
        rc |= cmd_strict()
    if args.check_parity:
        rc |= cmd_check_parity()
    return rc


if __name__ == "__main__":
    sys.exit(main())
