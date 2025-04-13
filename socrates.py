# socrates.py (wrapper)
from socrates_main import (
    # Import all your tools and key functions
    arxiv_search,
    analyze_papers,
    read_papers,
    research_question,
    academic_research,
    download_papers_to_user,
    server_info,
    download_recent_papers,
    parse_download_request,
    handle_paper_command,
    
    # Import the MCP server and FastMCP instance
    mcp,
    FastMCP
)

# Re-export the MCP server and other critical components
__all__ = [
    'arxiv_search',
    'analyze_papers',
    'read_papers',
    'research_question',
    'academic_research',
    'download_papers_to_user',
    'server_info',
    'download_recent_papers',
    'parse_download_request',
    'handle_paper_command',
    'mcp',
    'FastMCP'
]