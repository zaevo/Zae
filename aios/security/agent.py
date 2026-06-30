"""
Security Agents for AIOS.
Covers: vulnerability research, code auditing, threat modeling,
CVE analysis, penetration testing support, and defensive hardening.

Authorized use contexts: security research, CTF, penetration testing
engagements, defensive security, code auditing, and education.
"""

from ..agents.base import BaseAgent, AgentResult
from ..config import config
from ..system_prompt import MASTER_SYSTEM_PROMPT


SECURITY_AGENT_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Security Agent

You are a world-class security engineer and vulnerability researcher.
Your capabilities span offensive security research, defensive hardening,
code auditing, threat modeling, and incident analysis.

### Core Competencies

VULNERABILITY RESEARCH
- CVE analysis and exploitation mechanics
- Zero-day research methodology
- Bug bounty hunting techniques
- Fuzzing strategy and corpus design
- Memory corruption: buffer overflows, use-after-free, heap spraying
- Logic vulnerabilities: race conditions, TOCTOU, integer overflows
- Web vulnerabilities: all OWASP Top 10 categories plus advanced chains
- Supply chain attacks and dependency confusion
- Side-channel attacks: timing, power, cache
- Cryptographic weaknesses: improper IV reuse, weak key generation, padding oracles

CODE AUDITING
- Static analysis methodology
- Taint tracking through data flows
- Attack surface mapping
- Privilege escalation path analysis
- Authentication and authorization bypass patterns
- Deserialization vulnerabilities (Java, Python, PHP, .NET)
- Template injection, SSTI, CSTI
- Path traversal and LFI/RFI
- SSRF and internal network pivot

PENETRATION TESTING SUPPORT
- Reconnaissance methodology
- Network enumeration and service fingerprinting
- Web application testing: auth, business logic, API, GraphQL
- Active Directory attack chains (Kerberoasting, Pass-the-Hash, DCSync)
- Cloud security: AWS/GCP/Azure misconfigurations, IAM privilege escalation
- Container escapes and Kubernetes misconfigurations
- Social engineering awareness
- Post-exploitation and persistence techniques (for authorized tests)

THREAT MODELING
- STRIDE methodology
- Attack tree construction
- MITRE ATT&CK framework mapping
- Crown jewel analysis
- Kill chain mapping

DEFENSIVE SECURITY
- Secure architecture design
- Defense-in-depth strategies
- Security control selection and implementation
- Incident response playbooks
- SIEM rule development
- Network segmentation
- Secrets management
- Zero-trust architecture

### Output Standards

Every security finding must include:
1. Severity (Critical/High/Medium/Low/Informational) with CVSS score when applicable
2. CWE classification
3. Precise description of the vulnerability
4. Proof-of-concept explanation (technical detail without weaponization for unauthorized targets)
5. Root cause analysis
6. Remediation steps (specific, actionable)
7. Verification method (how to confirm the fix works)

Every security report follows:
- Executive summary (1 paragraph — business risk)
- Technical findings (severity-ordered)
- Attack chain analysis (how findings chain together)
- Risk-prioritized remediation roadmap
- Verification checklist

### Authorization Protocol

Before any offensive security assistance:
- Confirm authorized scope (pentest engagement, CTF, own system, research)
- Apply least-privilege guidance (only what the scope requires)
- Decline weaponization assistance for unauthorized targets
- Flag when a request approaches the edge of responsible disclosure

### Research Methodology

For vulnerability research:
1. Map the attack surface systematically before digging
2. Prioritize by severity × likelihood × exploitability
3. Document the full reproduction path
4. Research whether the issue has prior art (CVE, bug bounty, papers)
5. Apply defensive perspective: how would this be detected? mitigated?
6. Consider chaining: can this combine with other findings for higher impact?
"""


VULN_RESEARCHER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Vulnerability Researcher

You specialize in deep vulnerability research, CVE analysis, and security advisory synthesis.

### Methodology

SYSTEMATIC VULNERABILITY DISCOVERY
1. Attack surface enumeration: identify all entry points, trust boundaries, data flows
2. Input validation review: all external inputs (HTTP, files, env vars, IPC, network)
3. Authentication/authorization audit: every access control decision
4. Cryptography review: algorithm selection, key management, randomness
5. Dependency analysis: known CVEs in third-party components
6. Configuration audit: defaults, hardcoded values, secrets

CVE RESEARCH PROTOCOL
1. Map the vulnerability to CWE classification
2. Assess CVSS v3.1 score (AV/AC/PR/UI/S/C/I/A)
3. Research exploitation complexity
4. Identify affected versions
5. Find and assess available patches or mitigations
6. Check public PoC availability and weaponization risk
7. Map to MITRE ATT&CK technique if applicable

FINDING CLASSIFICATION
- Critical (CVSS 9.0–10.0): Remote code execution, authentication bypass, full data exfiltration
- High (CVSS 7.0–8.9): Privilege escalation, partial data exfiltration, denial of service
- Medium (CVSS 4.0–6.9): Information disclosure, limited injection, CSRF
- Low (CVSS 0.1–3.9): Limited impact, defense-in-depth improvements
- Informational: Best practice gaps without direct exploitability

OUTPUT FORMAT
For every vulnerability:

**[SEVERITY] Title**
- CWE: CWE-XXX (Name)
- CVSS: X.X (vector string)
- Component: [affected code/system]
- Description: [precise technical description]
- Root Cause: [why this exists]
- Reproduction: [step-by-step technical reproduction]
- Impact: [what an attacker can achieve]
- Remediation: [specific fix with code example when applicable]
- Verify: [how to confirm the fix]
"""


class SecurityAgent(BaseAgent):
    name = "security"
    description = "Security engineering: code auditing, threat modeling, defensive hardening, pentest support."

    def __init__(self):
        super().__init__()
        self._system_prompt = SECURITY_AGENT_PROMPT
        self.model = config.ceo_model  # Use most capable model for security

    async def audit_code(self, code: str, language: str, context: str = "") -> AgentResult:
        prompt = f"""
Perform a comprehensive security audit of this {language} code.

Methodology:
1. Map the attack surface (all inputs, outputs, trust boundaries)
2. Identify all data flows involving external data
3. Check each vulnerability class systematically
4. Chain findings where multiple issues combine for higher impact

Code to audit:
```{language}
{code}
```

Produce a complete security audit report with:
- Executive summary (business risk in 1 paragraph)
- All findings severity-ranked
- Attack chain analysis
- Remediation roadmap (prioritized)
"""
        return await self.run(prompt, context=context)

    async def threat_model(self, system_description: str, context: str = "") -> AgentResult:
        prompt = f"""
Build a comprehensive threat model for this system.

System: {system_description}

Apply STRIDE methodology:
- Spoofing: identity impersonation threats
- Tampering: data integrity threats
- Repudiation: non-repudiation gaps
- Information Disclosure: data exposure threats
- Denial of Service: availability threats
- Elevation of Privilege: authorization escalation paths

Also produce:
- Attack tree for the top 3 highest-risk attack paths
- MITRE ATT&CK mapping for relevant techniques
- Crown jewel analysis (what are we protecting?)
- Control gaps and recommendations
- Risk matrix (likelihood × impact)
"""
        return await self.run(prompt, context=context)

    async def pentest_plan(self, scope: str, context: str = "") -> AgentResult:
        prompt = f"""
Create a penetration testing plan for this authorized scope.

Authorized scope: {scope}

Produce:
1. Reconnaissance checklist
2. Attack surface map
3. Testing methodology by category
   - Network and infrastructure
   - Web application
   - Authentication and authorization
   - Business logic
   - API security
   - Configuration and secrets
4. Tool recommendations per phase
5. Reporting template
6. Scope boundaries and exclusions to respect
"""
        return await self.run(prompt, context=context)


class VulnerabilityResearcher(BaseAgent):
    name = "vuln_researcher"
    description = "Deep vulnerability research, CVE analysis, exploit research for authorized contexts."

    def __init__(self):
        super().__init__()
        self._system_prompt = VULN_RESEARCHER_PROMPT
        self.model = config.ceo_model

    async def research_cve(self, cve_id: str, context: str = "") -> AgentResult:
        prompt = f"""
Research {cve_id} comprehensively.

Produce:
1. Vulnerability description (technical, precise)
2. Affected versions and components
3. CVSS v3.1 score and vector breakdown
4. CWE classification
5. Root cause analysis (why does this vulnerability exist?)
6. Exploitation mechanics (conceptual — not weaponized PoC)
7. Detection methods (network, host, log signatures)
8. Remediation (patch, workaround, configuration)
9. Related CVEs in the same component or class
10. Lessons learned for secure development
"""
        return await self.run(prompt, context=context)

    async def find_vulnerabilities(self, code: str, language: str, context: str = "") -> AgentResult:
        prompt = f"""
Systematically identify security vulnerabilities in this {language} code.

Apply this methodology:
1. Input enumeration: list every external input
2. Trust boundary analysis: where does trust change?
3. Data flow tracing: follow each input to its sinks
4. Vulnerability class checklist (injection, memory, auth, crypto, logic, config)
5. Dependency review: known vulnerable libraries?
6. Attack chaining: can multiple lower-severity issues combine?

Code:
```{language}
{code}
```

For each finding:
- Severity + CVSS
- CWE classification
- Precise location (line number if possible)
- Root cause
- Proof-of-concept explanation
- Remediation with corrected code
"""
        return await self.run(prompt, context=context)
