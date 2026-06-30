"""
Coding Engine
Repository-aware software engineering with architecture planning,
multi-file reasoning, security auditing, and test generation.
"""

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..agents.specializations import CoderAgent, CriticAgent
from ..intelligence.reasoning import build_coding_protocol, extract_confidence


@dataclass
class FileContext:
    path: str
    content: str
    language: str
    size_bytes: int


@dataclass
class RepoContext:
    root: str
    files: list[FileContext]
    languages: list[str]
    entry_points: list[str]
    dependencies: dict[str, str]   # package -> version
    architecture_notes: str = ""


@dataclass
class SecurityFinding:
    severity: str          # "critical", "high", "medium", "low"
    category: str          # OWASP category
    file: str
    line: int | None
    description: str
    recommendation: str


@dataclass
class CodeResult:
    task: str
    plan: str
    implementation: str
    tests: str
    security_findings: list[SecurityFinding]
    confidence: float
    files_modified: list[str]
    raw_output: str


SECURITY_PATTERNS = {
    "sql_injection": [
        r'f".*SELECT.*{',
        r"execute\(.*%.*\)",
        r'query\s*=\s*["\'].*\+',
    ],
    "hardcoded_secret": [
        r'(password|secret|token|key)\s*=\s*["\'][^"\']{8,}',
        r'api_key\s*=\s*["\'][^"\']+',
    ],
    "command_injection": [
        r'os\.system\(',
        r'subprocess\.call\(.*shell=True',
        r'eval\(',
    ],
    "path_traversal": [
        r'open\(.*\+.*\)',
        r'\.\./',
    ],
}


class CodingEngine:
    """
    Full-cycle software engineering: plan → implement → test → audit → deliver.
    """

    def __init__(self):
        self._coder = CoderAgent()
        self._critic = CriticAgent()

    async def implement(
        self,
        task: str,
        repo_root: str | None = None,
        context: str = "",
    ) -> CodeResult:
        # Build repo context
        repo_context = ""
        if repo_root:
            repo_ctx = self._build_repo_context(repo_root)
            repo_context = self._format_repo_context(repo_ctx)

        protocol = build_coding_protocol(task, repo_context)
        result = await self._coder.run(protocol, context=context)

        if not result.succeeded:
            return CodeResult(
                task=task, plan="", implementation=result.error or "Failed",
                tests="", security_findings=[], confidence=0.0,
                files_modified=[], raw_output="",
            )

        output = result.content
        plan = self._extract_section(output, "Phase 1", "Phase 2") or \
               self._extract_section(output, "Plan", "Implementation")
        implementation = self._extract_code_blocks(output)
        tests = self._extract_section(output, "test", "security", case_insensitive=True)

        # Static security scan
        security_findings = self._static_security_scan(implementation)

        # Quality critique
        critique = await self._critic.review(
            output[:5000],
            [
                "Code is correct and handles edge cases",
                "Security vulnerabilities addressed",
                "Tests generated for non-trivial logic",
                "Architecture planned before implementation",
            ]
        )

        confidence = extract_confidence(output)
        files_modified = self._extract_file_references(output)

        return CodeResult(
            task=task,
            plan=plan,
            implementation=implementation,
            tests=tests,
            security_findings=security_findings,
            confidence=confidence,
            files_modified=files_modified,
            raw_output=output,
        )

    def _build_repo_context(self, root: str, max_files: int = 20) -> RepoContext:
        root_path = Path(root)
        files = []
        languages: set[str] = set()
        dependencies = {}

        # Read key files
        for path in sorted(root_path.rglob("*"))[:max_files * 3]:
            if path.is_file() and not any(
                part in str(path) for part in [".git", "__pycache__", "node_modules", ".venv"]
            ):
                ext = path.suffix.lower()
                lang = {
                    ".py": "python", ".ts": "typescript", ".tsx": "typescript",
                    ".js": "javascript", ".jsx": "javascript", ".go": "go",
                    ".rs": "rust", ".java": "java", ".rb": "ruby",
                }.get(ext, "")
                if lang and len(files) < max_files:
                    try:
                        content = path.read_text(encoding="utf-8", errors="ignore")
                        files.append(FileContext(
                            path=str(path.relative_to(root_path)),
                            content=content[:3000],
                            language=lang,
                            size_bytes=path.stat().st_size,
                        ))
                        languages.add(lang)
                    except Exception:
                        pass

        # Parse dependencies
        req_file = root_path / "requirements.txt"
        if req_file.exists():
            for line in req_file.read_text().splitlines():
                if ">=" in line or "==" in line:
                    parts = re.split(r"[><=]", line)
                    if parts:
                        dependencies[parts[0].strip()] = line.strip()

        return RepoContext(
            root=root,
            files=files,
            languages=list(languages),
            entry_points=self._find_entry_points(root_path),
            dependencies=dependencies,
        )

    def _find_entry_points(self, root: Path) -> list[str]:
        candidates = ["main.py", "app.py", "index.py", "server.py", "cli.py", "run.py"]
        return [str(p) for c in candidates if (p := root / c).exists()]

    def _format_repo_context(self, ctx: RepoContext) -> str:
        parts = [
            f"## Repository: {ctx.root}",
            f"Languages: {', '.join(ctx.languages)}",
            f"Entry points: {', '.join(ctx.entry_points) or 'none found'}",
        ]
        if ctx.dependencies:
            parts.append("Dependencies: " + ", ".join(list(ctx.dependencies)[:10]))
        for f in ctx.files[:10]:
            parts.append(f"\n### {f.path} ({f.language})\n```\n{f.content[:1000]}\n```")
        return "\n".join(parts)

    def _static_security_scan(self, code: str) -> list[SecurityFinding]:
        findings = []
        lines = code.splitlines()
        for category, patterns in SECURITY_PATTERNS.items():
            for pattern in patterns:
                for i, line in enumerate(lines, 1):
                    if re.search(pattern, line, re.IGNORECASE):
                        findings.append(SecurityFinding(
                            severity="high" if category in ("sql_injection", "command_injection") else "medium",
                            category=category,
                            file="<generated>",
                            line=i,
                            description=f"Potential {category.replace('_', ' ')} detected",
                            recommendation=f"Review line {i} for {category.replace('_', ' ')} vulnerability",
                        ))
        return findings

    def _extract_code_blocks(self, text: str) -> str:
        blocks = re.findall(r"```(?:\w+)?\n(.*?)```", text, re.DOTALL)
        return "\n\n".join(blocks) if blocks else text

    def _extract_section(
        self, text: str, start_marker: str, end_marker: str, case_insensitive: bool = False
    ) -> str:
        flags = re.IGNORECASE if case_insensitive else 0
        pattern = rf"{re.escape(start_marker)}(.*?)(?={re.escape(end_marker)}|$)"
        match = re.search(pattern, text, re.DOTALL | flags)
        return match.group(1).strip() if match else ""

    def _extract_file_references(self, text: str) -> list[str]:
        patterns = [
            r"`([^`]+\.(py|ts|js|go|rs|java|rb|sql|yaml|json))`",
            r"###\s+([^\s]+\.(py|ts|js|go|rs|java|rb))",
        ]
        files = []
        for pattern in patterns:
            files.extend(m.group(1) for m in re.finditer(pattern, text))
        return list(dict.fromkeys(files))  # deduplicate preserving order
