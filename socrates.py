# Import all the tools and functionality from your original implementation
from socrates_main import (
    # Core MCP components
    mcp,
    
    # All tools
    arxiv_search,
    analyze_papers,
    read_papers, 
    research_question,
    academic_research,
    download_papers_to_user,
    download_recent_papers,
    parse_download_request,
    handle_paper_command,
    server_info,
    
    # Constants and helpers
    CACHE_DIR,
    PDF_CACHE_DIR,
    DOWNLOAD_DIR,
    RECENT_PAPERS
)

# Re-export everything to maintain the API
__all__ = [
    'mcp',
    'arxiv_search',
    'analyze_papers',
    'read_papers',
    'research_question',
    'academic_research',
    'download_papers_to_user',
    'download_recent_papers',
    'parse_download_request',
    'handle_paper_command',
    'server_info',
]