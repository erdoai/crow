"""Knowledge tools — search and write PARA knowledge entries."""

from crow.agents.tools import tool_def

SEARCH_DEF = tool_def(
    name="knowledge.search",
    description="Search your PARA knowledge base via semantic + keyword matching.",
    parameters={
        "properties": {
            "query": {
                "type": "string",
                "description": "What to search for",
            },
            "category": {
                "type": "string",
                "description": "Filter by PARA category",
                "enum": ["project", "area", "resource", "archive"],
            },
        },
        "required": ["query"],
    },
)

WRITE_DEF = tool_def(
    name="knowledge.write",
    description="Write a new learning to your PARA knowledge base.",
    parameters={
        "properties": {
            "category": {
                "type": "string",
                "description": "PARA category",
                "enum": ["project", "area", "resource"],
            },
            "title": {
                "type": "string",
                "description": "Short title for this knowledge entry",
            },
            "content": {
                "type": "string",
                "description": "The learning/knowledge in markdown",
            },
            "tags": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional tags for categorization",
            },
        },
        "required": ["category", "title", "content"],
    },
)

ARCHIVE_DEF = tool_def(
    name="knowledge.archive",
    description="Archive a knowledge entry (move to archives).",
    parameters={
        "properties": {
            "knowledge_id": {
                "type": "string",
                "description": "ID of the knowledge entry to archive",
            },
        },
        "required": ["knowledge_id"],
    },
)
