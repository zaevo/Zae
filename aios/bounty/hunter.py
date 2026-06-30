"""
Bug Bounty Hunter Agent — specialized for active bounty hunting.

Capabilities:
- Program scope analysis and attack surface mapping
- Targeted recon planning for a specific scope
- Professional bug report drafting
- Finding triage and prioritization

Authorization: Only assists with programs the user is explicitly
enrolled in. All guidance follows responsible disclosure.
"""

from ..agents.base import BaseAgent, AgentResult
from ..config import config
from ..system_prompt import MASTER_SYSTEM_PROMPT


BOUNTY_HUNTER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Bug Bounty Hunter

You are a professional bug bounty hunter with a track record of critical findings
on HackerOne and Bugcrowd. You approach every target methodically, prioritizing
high-impact vulnerability classes that beginner hunters overlook.

### Your Hunting Philosophy

1. **Attack surface first** — never start testing blind. Map what exists before
   looking for what's broken.
2. **IDOR is gold** — access control issues are everywhere and consistently
   underpaid by the market (meaning: less competition).
3. **Logic over injection** — SQL injection is mostly patched; business logic
   flaws require human insight, not scanners.
4. **Chain findings** — a P4 + P4 + P3 chained correctly is a P1.
5. **Report quality = payout** — the same bug with a bad report gets $0 or $150;
   with an excellent report gets $1,000+.

### Vulnerability Priority for Modern Web Apps

Priority order (highest ROI for time invested):
1. **IDOR / Access Control** — /api/user/{{id}}, object-level auth, horizontal/vertical escalation
2. **SSRF** — any parameter accepting a URL, webhook, callback, fetch, redirect
3. **Auth / JWT flaws** — alg:none, weak secret, improper validation, session fixation
4. **Stored XSS in admin/internal** — much higher impact than reflected
5. **Business logic** — price manipulation, race conditions, limit bypasses
6. **Information disclosure** — debug endpoints, stack traces, leaked keys in JS
7. **CSRF on sensitive actions** — state-changing requests without CSRF token

### Recon Stack (Modern, 2025)

Passive (no active scanning):
```
subfinder -d <target> -o subs.txt
amass enum -passive -d <target>
httpx -l subs.txt -status-code -title -tech-detect -o live.txt
gau <target> | sort -u | grep -E "\\.(js|json|xml|yaml|config)"
waybackurls <target> | sort -u > wayback.txt
trufflehog filesystem <local_clone>   # secrets in JS
```

Active (only after verifying in-scope):
```
ffuf -w /path/to/wordlist -u https://target.com/FUZZ -mc 200,301,302
nuclei -l live.txt -t exposures/ -t misconfiguration/
```

JavaScript analysis (high-value, often skipped):
- Extract all JS files: `cat wayback.txt | grep '\\.js$' | httpx -mc 200`
- Beautify + grep for API endpoints: `grep -E '(api|v[0-9]|/user|/admin|/internal)' *.js`
- Grep for secrets: `grep -E '(api_key|token|password|secret|key)\\s*[=:]' *.js`

### Output Standards

For scope analysis — always produce:
1. Asset inventory (domains, APIs, mobile apps, cloud)
2. Attack surface heat map (ranked by likelihood of vulns)
3. Top 5 specific test cases to start with
4. Out-of-scope guardrails (what NOT to touch)

For recon plans — always produce:
1. Phase 1: Passive reconnaissance (zero server contact)
2. Phase 2: Active enumeration (in-scope targets only)
3. Phase 3: Vulnerability-specific testing
4. Specific tool commands for each phase
5. What to look for and where to log it

For bug reports — always produce:
1. Summary (1 paragraph: what, where, impact)
2. Severity with CVSS justification
3. Step-by-step reproduction (numbered, precise, reproducible)
4. Impact statement (specific, real-world, concrete)
5. Proof-of-concept evidence
6. Remediation suggestion

### Ethical Guardrails

- Never suggest testing targets not explicitly in-scope
- Never suggest accessing, exfiltrating, or retaining real user data
- Never suggest DoS, brute force, or automated scanning beyond scope
- Stop and report immediately at proof-of-concept — no deeper exploitation
- Always remind: read the program policy before testing anything
"""


SCOPE_ANALYZER_PROMPT = f"""
{MASTER_SYSTEM_PROMPT}

## YOUR ROLE: Bug Bounty Scope Analyst

You analyze bug bounty program scope definitions and produce actionable attack surface maps.

Given a program's scope policy text, you:
1. Parse every in-scope and out-of-scope asset
2. Identify the highest-value targets (most complex, most likely to have vulns)
3. Flag any ambiguous scope language that could get a researcher banned
4. Produce a prioritized testing queue
5. Identify what vulnerability classes this program explicitly rewards vs. ignores

You understand that scope violations are the #1 way bug bounty hunters get banned.
Your analysis is conservative — when scope is ambiguous, you flag it and suggest
asking the program before testing.
"""


class BugBountyHunterAgent(BaseAgent):
    name = "bounty_hunter"
    description = "Bug bounty hunting: scope analysis, recon planning, report drafting, finding triage."

    def __init__(self):
        super().__init__()
        self._system_prompt = BOUNTY_HUNTER_PROMPT
        self.model = config.ceo_model

    async def analyze_scope(self, scope_text: str, program_name: str = "") -> AgentResult:
        prog = f" ({program_name})" if program_name else ""
        prompt = f"""
Analyze this bug bounty program scope{prog} and produce a complete attack surface map.

SCOPE POLICY:
{scope_text}

Produce:

## 1. Asset Inventory
List every in-scope asset: domains, subdomains, APIs, mobile apps, cloud services.
Mark each as HIGH/MEDIUM/LOW value for finding bugs.

## 2. Attack Surface Heat Map
For each asset category, rank the most likely vulnerability classes and why.

## 3. Top 5 Testing Priorities
The 5 most specific test cases I should start with immediately. Be concrete:
not "test for IDOR" but "test the /api/v1/user/{{id}} endpoint by swapping user IDs
between two test accounts."

## 4. Out-of-Scope Guardrails
What is explicitly out of scope? What is ambiguous and needs clarification?

## 5. Program Intelligence
- Payout range (if disclosed)
- Response time reputation
- Common duplicate classes to avoid
- Any program-specific quirks
"""
        return await self.run(prompt)

    async def plan_recon(self, target_domain: str, scope_context: str = "") -> AgentResult:
        scope_note = f"\nScope context:\n{scope_context}" if scope_context else ""
        prompt = f"""
Create a complete reconnaissance plan for bug bounty hunting on: {target_domain}
{scope_note}

This is for an authorized bug bounty program. The researcher is enrolled in the program.

Produce a phased recon plan:

## Phase 1: Passive Recon (Zero Server Contact)
Exact commands for:
- Subdomain enumeration (passive only)
- Historical URL collection
- JavaScript file discovery
- Certificate transparency logs
- DNS record collection
Expected output and what to look for in each.

## Phase 2: Active Enumeration (In-Scope Only)
Exact commands for:
- Live host detection
- Technology fingerprinting
- Directory/endpoint discovery
- API endpoint discovery
Expected output and what to look for.

## Phase 3: Vulnerability-Targeted Testing
Based on common vulnerabilities for this type of target:
- IDOR testing methodology
- Auth/JWT testing checklist
- SSRF parameter hunting
- XSS injection points
Specific Burp Suite configurations and test cases.

## Phase 4: Documentation System
How to organize findings, screenshots, and evidence as you work.
What to log and in what format.

## What NOT to Do
Specific actions to avoid that could violate scope or ToS.
"""
        return await self.run(prompt)

    async def draft_report(
        self,
        vulnerability_description: str,
        program_name: str = "",
        severity: str = "",
    ) -> AgentResult:
        prog = f"\nProgram: {program_name}" if program_name else ""
        sev = f"\nResearcher's severity estimate: {severity}" if severity else ""
        prompt = f"""
Write a professional bug bounty report for this finding.
{prog}{sev}

Finding description from researcher:
{vulnerability_description}

Write the full report using the standard format.
Make it professional, precise, and maximally clear for the triage team.

## Summary
One clear paragraph: vulnerability type, location, what an attacker can do.

## Severity
CVSS v3.1 score with vector breakdown. Justify each metric.
Be honest — programs penalize inflation and reward accuracy.

## Steps to Reproduce
Numbered steps, precise enough that someone unfamiliar with the target can reproduce it.
Include:
- Account setup requirements
- Exact URLs with parameters
- Request/response details
- What to observe at each step

## Impact
Concrete impact. Who is affected, what data/functionality is exposed, real-world scenario.
Avoid vague statements. Quantify if possible.

## Proof of Concept
Describe the evidence: screenshots, HTTP request/response, video.
If providing a PoC payload: make it clearly non-destructive (alert(), not data exfil).

## Suggested Remediation
Specific fix, not generic. Reference the root cause.

## Additional Notes
Any relevant context: related endpoints, similar patterns elsewhere in the app, suggested fix priority.
"""
        return await self.run(prompt)

    async def triage_findings(self, findings: list[str]) -> AgentResult:
        findings_str = "\n".join(f"{i+1}. {f}" for i, f in enumerate(findings))
        prompt = f"""
Triage these bug bounty findings and prioritize which to report first.

Findings:
{findings_str}

For each finding, assess:
1. Estimated severity (Critical/High/Medium/Low)
2. Estimated payout range
3. Likelihood of being a duplicate
4. Effort to write a compelling report
5. Priority (1=report now, 2=report this week, 3=deprioritize)

Then produce a ranked action list: what to report first and why.
"""
        return await self.run(prompt)
