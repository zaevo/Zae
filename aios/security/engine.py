"""
Security Engine
Full-lifecycle security analysis: static analysis, threat modeling,
CVE research, pentest planning, and defensive hardening recommendations.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from .agent import SecurityAgent, VulnerabilityResearcher
from ..intelligence.reasoning import extract_confidence


CVSS_SEVERITY = {
    (9.0, 10.0): "Critical",
    (7.0, 8.9): "High",
    (4.0, 6.9): "Medium",
    (0.1, 3.9): "Low",
    (0.0, 0.0): "Informational",
}

# OWASP Top 10 2021 with CWE mappings
OWASP_TOP10 = {
    "A01": ("Broken Access Control", ["CWE-200", "CWE-201", "CWE-352"]),
    "A02": ("Cryptographic Failures", ["CWE-261", "CWE-296", "CWE-310"]),
    "A03": ("Injection", ["CWE-20", "CWE-74", "CWE-89", "CWE-77"]),
    "A04": ("Insecure Design", ["CWE-73", "CWE-183", "CWE-209"]),
    "A05": ("Security Misconfiguration", ["CWE-2", "CWE-11", "CWE-13"]),
    "A06": ("Vulnerable and Outdated Components", ["CWE-1035", "CWE-1104"]),
    "A07": ("Identification and Authentication Failures", ["CWE-255", "CWE-259", "CWE-287"]),
    "A08": ("Software and Data Integrity Failures", ["CWE-494", "CWE-502", "CWE-829"]),
    "A09": ("Security Logging and Monitoring Failures", ["CWE-223", "CWE-778"]),
    "A10": ("Server-Side Request Forgery", ["CWE-918"]),
}

# Static patterns for quick pre-scan before LLM analysis
VULNERABILITY_PATTERNS: dict[str, list[tuple[str, str, str]]] = {
    "python": [
        (r"eval\s*\(", "A03", "Command injection via eval()"),
        (r"exec\s*\(", "A03", "Command injection via exec()"),
        (r"os\.system\s*\(", "A03", "OS command injection"),
        (r"subprocess\.\w+\(.*shell\s*=\s*True", "A03", "Shell injection via subprocess"),
        (r"pickle\.loads?\s*\(", "A08", "Insecure deserialization via pickle"),
        (r"yaml\.load\s*\([^)]*\)", "A08", "Unsafe YAML deserialization"),
        (r'(password|secret|token|key|api_key)\s*=\s*["\'][^"\']{4,}["\']', "A02", "Hardcoded credential"),
        (r"MD5|SHA1|DES|RC4", "A02", "Weak cryptographic algorithm"),
        (r"random\.(random|randint|choice)\s*\(", "A02", "Non-cryptographic randomness for security context"),
        (r"f[\"'].*SELECT.*\{", "A03", "SQL injection via f-string"),
        (r'execute\s*\(\s*["\'].*\%[^)]*\)', "A03", "SQL injection via string formatting"),
        (r"open\s*\(.*\+", "A01", "Path traversal via string concatenation"),
        (r"@app\.route.*methods.*POST.*(?!csrf)", "A01", "Potential CSRF — check for token"),
        (r"DEBUG\s*=\s*True", "A05", "Debug mode enabled in code"),
        (r"verify\s*=\s*False", "A05", "TLS verification disabled"),
    ],
    "javascript": [
        (r"eval\s*\(", "A03", "JavaScript eval injection"),
        (r"innerHTML\s*=", "A03", "XSS via innerHTML assignment"),
        (r"document\.write\s*\(", "A03", "XSS via document.write"),
        (r"dangerouslySetInnerHTML", "A03", "XSS risk via React dangerouslySetInnerHTML"),
        (r'(password|secret|token|key)\s*[:=]\s*["\'][^"\']{4,}', "A02", "Hardcoded credential"),
        (r"Math\.random\(\)", "A02", "Non-cryptographic randomness"),
        (r"http://", "A02", "HTTP (unencrypted) URL"),
        (r"localStorage\.(set|get)Item.*token", "A01", "Token stored in localStorage"),
        (r"req\.query\.\w+.*sql", "A03", "Potential SQL injection via query param"),
        (r"require\(['\"]\.\./", "A01", "Path traversal in require()"),
    ],
    "go": [
        (r'fmt\.Sprintf.*SELECT.*%[sv]', "A03", "SQL injection via Sprintf"),
        (r"md5\.|sha1\.", "A02", "Weak cryptographic hash"),
        (r"rand\.Intn|rand\.Float", "A02", "Non-cryptographic randomness"),
        (r"os\.Exec\(|exec\.Command\(.*\+", "A03", "Command injection"),
        (r"ioutil\.ReadFile\(.*\+", "A01", "Path traversal"),
        (r'(password|secret|token)\s*=\s*"[^"]{4,}"', "A02", "Hardcoded credential"),
    ],
}


@dataclass
class VulnerabilityFinding:
    severity: str
    cvss_score: float
    owasp_category: str
    cwe: str
    title: str
    description: str
    location: str
    line: int | None
    root_cause: str
    remediation: str
    proof_of_concept: str = ""
    references: list[str] = field(default_factory=list)


@dataclass
class ThreatModel:
    system: str
    assets: list[str]
    threats: list[dict[str, Any]]
    attack_trees: list[dict[str, Any]]
    mitre_techniques: list[str]
    risk_matrix: list[dict[str, Any]]
    recommendations: list[str]
    overall_risk: str


@dataclass
class VulnerabilityReport:
    target: str
    scan_type: str
    findings: list[VulnerabilityFinding]
    critical_count: int
    high_count: int
    medium_count: int
    low_count: int
    executive_summary: str
    attack_chains: list[str]
    remediation_roadmap: list[dict[str, Any]]
    overall_risk_score: float
    confidence: float
    raw_analysis: str


class SecurityEngine:
    """
    Comprehensive security analysis engine combining static pattern analysis
    with LLM-powered deep vulnerability research.
    """

    def __init__(self):
        self._security_agent = SecurityAgent()
        self._vuln_researcher = VulnerabilityResearcher()

    async def full_security_audit(
        self,
        code: str,
        language: str,
        context: str = "",
        include_threat_model: bool = False,
    ) -> VulnerabilityReport:
        """
        Complete security audit: static scan + LLM deep analysis.
        """
        # Phase 1: Static pattern scan (fast, deterministic)
        static_findings = self._static_scan(code, language)

        # Phase 2: LLM deep audit
        llm_result = await self._security_agent.audit_code(code, language, context)

        # Phase 3: Vulnerability-focused researcher pass
        vuln_result = await self._vuln_researcher.find_vulnerabilities(code, language, context)

        combined_analysis = f"""
## Static Analysis Findings
{self._format_static_findings(static_findings)}

## Deep Security Audit
{llm_result.content if llm_result.succeeded else "Deep audit unavailable"}

## Vulnerability Research
{vuln_result.content if vuln_result.succeeded else "Vulnerability research unavailable"}
"""
        findings = self._parse_findings(combined_analysis, static_findings)
        severity_counts = self._count_severities(findings)

        return VulnerabilityReport(
            target=f"<code ({language})>",
            scan_type="full_audit",
            findings=findings,
            critical_count=severity_counts["Critical"],
            high_count=severity_counts["High"],
            medium_count=severity_counts["Medium"],
            low_count=severity_counts["Low"],
            executive_summary=self._extract_executive_summary(combined_analysis),
            attack_chains=self._extract_attack_chains(combined_analysis),
            remediation_roadmap=self._build_remediation_roadmap(findings),
            overall_risk_score=self._compute_risk_score(findings),
            confidence=extract_confidence(combined_analysis),
            raw_analysis=combined_analysis,
        )

    def _static_scan(self, code: str, language: str) -> list[dict[str, Any]]:
        """Fast deterministic scan using regex patterns before LLM analysis."""
        findings = []
        patterns = VULNERABILITY_PATTERNS.get(language.lower(), [])
        lines = code.splitlines()
        for pattern, owasp_cat, description in patterns:
            for i, line in enumerate(lines, 1):
                if re.search(pattern, line, re.IGNORECASE):
                    owasp_name, cwes = OWASP_TOP10.get(owasp_cat, ("Unknown", []))
                    findings.append({
                        "type": "static",
                        "line": i,
                        "owasp": f"{owasp_cat}: {owasp_name}",
                        "cwe": cwes[0] if cwes else "CWE-0",
                        "description": description,
                        "code_snippet": line.strip()[:120],
                        "severity": self._estimate_severity(owasp_cat),
                    })
        return findings

    def _estimate_severity(self, owasp_cat: str) -> str:
        critical_cats = {"A03", "A01", "A08"}
        high_cats = {"A02", "A07"}
        return "Critical" if owasp_cat in critical_cats else \
               "High" if owasp_cat in high_cats else "Medium"

    def _format_static_findings(self, findings: list[dict]) -> str:
        if not findings:
            return "No static patterns detected."
        lines = []
        for f in findings:
            lines.append(
                f"- **[{f['severity']}]** Line {f['line']}: {f['description']}\n"
                f"  OWASP: {f['owasp']} | CWE: {f['cwe']}\n"
                f"  Code: `{f['code_snippet']}`"
            )
        return "\n".join(lines)

    def _parse_findings(
        self, analysis: str, static_findings: list[dict]
    ) -> list[VulnerabilityFinding]:
        findings = []
        for sf in static_findings:
            findings.append(VulnerabilityFinding(
                severity=sf["severity"],
                cvss_score=8.0 if sf["severity"] == "Critical" else 6.5,
                owasp_category=sf["owasp"],
                cwe=sf["cwe"],
                title=sf["description"],
                description=sf["description"],
                location="<code>",
                line=sf["line"],
                root_cause="Identified via static pattern analysis",
                remediation="See LLM analysis for detailed remediation",
            ))
        return findings

    def _count_severities(self, findings: list[VulnerabilityFinding]) -> dict[str, int]:
        counts: dict[str, int] = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
        for f in findings:
            if f.severity in counts:
                counts[f.severity] += 1
        return counts

    def _extract_executive_summary(self, text: str) -> str:
        for marker in ["executive summary", "summary", "overview"]:
            idx = text.lower().find(marker)
            if idx >= 0:
                start = idx + len(marker)
                segment = text[start:start+500].strip()
                lines = [l.strip() for l in segment.splitlines() if l.strip()][:3]
                if lines:
                    return " ".join(lines)
        return text[:300]

    def _extract_attack_chains(self, text: str) -> list[str]:
        chains = []
        for marker in ["attack chain", "chain", "combined", "chained"]:
            idx = text.lower().find(marker)
            if idx >= 0:
                segment = text[idx:idx+400]
                chains.append(segment[:200])
        return chains[:3]

    def _build_remediation_roadmap(
        self, findings: list[VulnerabilityFinding]
    ) -> list[dict[str, Any]]:
        severity_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
        sorted_findings = sorted(findings, key=lambda f: severity_order.get(f.severity, 4))
        roadmap = []
        for i, f in enumerate(sorted_findings[:10], 1):
            roadmap.append({
                "priority": i,
                "severity": f.severity,
                "title": f.title,
                "remediation": f.remediation,
                "estimated_effort": "low" if f.severity in ("Low",) else
                                    "medium" if f.severity == "Medium" else "high",
            })
        return roadmap

    def _compute_risk_score(self, findings: list[VulnerabilityFinding]) -> float:
        weights = {"Critical": 10.0, "High": 7.0, "Medium": 4.0, "Low": 1.5}
        total = sum(weights.get(f.severity, 0) for f in findings)
        return min(10.0, total / max(1, len(findings) * 0.5))

    async def research_cve(self, cve_id: str, context: str = "") -> AgentResult:
        return await self._vuln_researcher.research_cve(cve_id, context)

    async def threat_model(self, system_description: str, context: str = "") -> ThreatModel:
        result = await self._security_agent.threat_model(system_description, context)
        return ThreatModel(
            system=system_description,
            assets=[],
            threats=[],
            attack_trees=[],
            mitre_techniques=[],
            risk_matrix=[],
            recommendations=[],
            overall_risk=result.content[:100] if result.succeeded else "Unknown",
        )

    async def pentest_plan(self, scope: str, context: str = "") -> AgentResult:
        return await self._security_agent.pentest_plan(scope, context)
