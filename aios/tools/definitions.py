"""
Anthropic-compatible tool definitions for AIOS agents.
Tools give agents the ability to interact with the real world.
"""

WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": "Search the web for current information. Use for research, fact-checking, and finding recent data.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "num_results": {"type": "integer", "description": "Number of results (1-10)", "default": 5},
        },
        "required": ["query"],
    },
}

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read a file from the filesystem.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute or relative file path"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["path"],
    },
}

WRITE_FILE_TOOL = {
    "name": "write_file",
    "description": "Write content to a file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File path to write"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {"type": "string", "enum": ["write", "append"], "default": "write"},
        },
        "required": ["path", "content"],
    },
}

LIST_FILES_TOOL = {
    "name": "list_files",
    "description": "List files in a directory with optional glob pattern.",
    "input_schema": {
        "type": "object",
        "properties": {
            "directory": {"type": "string", "description": "Directory path"},
            "pattern": {"type": "string", "description": "Glob pattern (e.g., '*.py')", "default": "*"},
            "recursive": {"type": "boolean", "default": False},
        },
        "required": ["directory"],
    },
}

EXECUTE_CODE_TOOL = {
    "name": "execute_python",
    "description": "Execute Python code in a sandboxed environment. Returns stdout and stderr.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
        },
        "required": ["code"],
    },
}

MEMORY_QUERY_TOOL = {
    "name": "query_memory",
    "description": "Query the AIOS memory system for relevant past context.",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to search for in memory"},
            "memory_type": {
                "type": "string",
                "enum": ["episodic", "semantic", "project", "procedural", "preference", "all"],
                "default": "all",
            },
            "top_k": {"type": "integer", "default": 5},
        },
        "required": ["query"],
    },
}

MEMORY_STORE_TOOL = {
    "name": "store_memory",
    "description": "Store a new memory in the AIOS memory system.",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Content to store"},
            "memory_type": {
                "type": "string",
                "enum": ["episodic", "semantic", "project", "procedural", "preference"],
            },
            "importance": {"type": "number", "description": "Importance score 0-10", "default": 5.0},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["content", "memory_type"],
    },
}

CVE_LOOKUP_TOOL = {
    "name": "cve_lookup",
    "description": "Look up details for a CVE identifier including CVSS score, affected versions, and patches.",
    "input_schema": {
        "type": "object",
        "properties": {
            "cve_id": {"type": "string", "description": "CVE identifier (e.g., CVE-2024-1234)"},
        },
        "required": ["cve_id"],
    },
}

DEPENDENCY_AUDIT_TOOL = {
    "name": "dependency_audit",
    "description": "Check dependencies for known CVEs using OSV database.",
    "input_schema": {
        "type": "object",
        "properties": {
            "package": {"type": "string", "description": "Package name"},
            "version": {"type": "string", "description": "Package version"},
            "ecosystem": {"type": "string", "description": "e.g., PyPI, npm, Go, Maven"},
        },
        "required": ["package", "version", "ecosystem"],
    },
}

SECURITY_SCAN_TOOL = {
    "name": "security_scan",
    "description": "Run a static security analysis on code. Checks for OWASP Top 10 vulnerabilities.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code to analyze"},
            "language": {"type": "string", "description": "Programming language"},
            "severity_threshold": {
                "type": "string",
                "enum": ["critical", "high", "medium", "low"],
                "default": "medium",
            },
        },
        "required": ["code", "language"],
    },
}

# Tool sets per agent role
TOOL_DEFINITIONS = {
    "researcher": [WEB_SEARCH_TOOL, MEMORY_QUERY_TOOL],
    "coder": [READ_FILE_TOOL, WRITE_FILE_TOOL, LIST_FILES_TOOL, EXECUTE_CODE_TOOL, SECURITY_SCAN_TOOL],
    "memory_manager": [MEMORY_QUERY_TOOL, MEMORY_STORE_TOOL],
    "fact_checker": [WEB_SEARCH_TOOL],
    "analyst": [EXECUTE_CODE_TOOL, MEMORY_QUERY_TOOL],
    "browser": [WEB_SEARCH_TOOL],
    "file_manager": [READ_FILE_TOOL, WRITE_FILE_TOOL, LIST_FILES_TOOL],
    "security": [SECURITY_SCAN_TOOL, READ_FILE_TOOL, LIST_FILES_TOOL, WEB_SEARCH_TOOL, CVE_LOOKUP_TOOL, DEPENDENCY_AUDIT_TOOL],
    "vuln_researcher": [WEB_SEARCH_TOOL, CVE_LOOKUP_TOOL, DEPENDENCY_AUDIT_TOOL, SECURITY_SCAN_TOOL],
}


def get_tools_for_agent(agent_name: str) -> list[dict]:
    return TOOL_DEFINITIONS.get(agent_name, [])
