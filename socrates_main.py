from typing import Any, List, Dict, Optional
import httpx
import asyncio
import xml.etree.ElementTree as ET
import re
import os
import json
import io
import tempfile
import requests
from mcp.server.fastmcp import FastMCP
import PyPDF2
from datetime import datetime

# Initialize FastMCP server
mcp = FastMCP("socrates")

# Set server metadata for self-awareness
SERVER_METADATA = {
    "name": "Socrates",
    "version": "3.0.0",
    "description": "Academic Research Assistant for finding, analyzing, and citing scientific papers",
    "owner": "Universitas AI",
    "capabilities": [
        "arxiv_search",
        "paper_analysis",
        "full_text_extraction",
        "citation_generation",
        "paper_download"
    ]
}

# Add server information resource
@mcp.resource("socrates://info")
def get_server_info() -> str:
    """Get information about the Socrates MCP server"""
    return json.dumps(SERVER_METADATA, indent=2)

# Constants
ARXIV_API_BASE = "http://export.arxiv.org/api/query"
CACHE_DIR = os.path.join(os.path.expanduser("~"), "socrates_cache")
PDF_CACHE_DIR = os.path.join(CACHE_DIR, "pdfs")
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "arxiv_papers")
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(PDF_CACHE_DIR, exist_ok=True)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Store recent papers for citation and download functionality
RECENT_PAPERS = []

# Register XML namespaces
namespaces = {
    'atom': 'http://www.w3.org/2005/Atom',
    'opensearch': 'http://a9.com/-/spec/opensearch/1.1/',
    'arxiv': 'http://arxiv.org/schemas/atom'
}

# Register namespaces for ElementTree
for prefix, uri in namespaces.items():
    ET.register_namespace(prefix, uri)

async def search_arxiv(query: str, max_results: int = 10) -> List[Dict[str, Any]]:
    """
    Search ArXiv API for papers matching the query.
    Returns list of paper metadata dictionaries.
    """
    params = {
        'search_query': query,
        'max_results': max_results,
        'sortBy': 'relevance',
        'sortOrder': 'descending'
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(ARXIV_API_BASE, params=params, timeout=30.0)
            response.raise_for_status()
            xml_data = response.text
            
            # Parse XML with explicit namespace handling
            root = ET.fromstring(xml_data)
            
            # Extract results
            entries = root.findall('.//{http://www.w3.org/2005/Atom}entry')
            results = []
            
            for entry in entries:
                # Extract basic metadata
                id_elem = entry.find('.//{http://www.w3.org/2005/Atom}id')
                title_elem = entry.find('.//{http://www.w3.org/2005/Atom}title')
                summary_elem = entry.find('.//{http://www.w3.org/2005/Atom}summary')
                published_elem = entry.find('.//{http://www.w3.org/2005/Atom}published')
                updated_elem = entry.find('.//{http://www.w3.org/2005/Atom}updated')
                
                paper = {
                    'id': id_elem.text if id_elem is not None else None,
                    'title': title_elem.text.strip().replace('\n', ' ') if title_elem is not None else 'No title',
                    'summary': summary_elem.text.strip().replace('\n', ' ') if summary_elem is not None else 'No summary',
                    'published': published_elem.text if published_elem is not None else None,
                    'updated': updated_elem.text if updated_elem is not None else None,
                    'pdf_url': None,
                    'authors': []
                }
                
                # Extract PDF URL
                links = entry.findall('.//{http://www.w3.org/2005/Atom}link')
                for link in links:
                    if link.get('title') == 'pdf':
                        paper['pdf_url'] = link.get('href')
                        break
                
                # Extract authors
                authors = entry.findall('.//{http://www.w3.org/2005/Atom}author/{http://www.w3.org/2005/Atom}name')
                for author in authors:
                    paper['authors'].append(author.text)
                
                # Extract categories/tags
                categories = entry.findall('.//{http://www.w3.org/2005/Atom}category')
                paper['categories'] = [cat.get('term') for cat in categories if cat.get('term')]
                
                results.append(paper)
            
            return results
            
        except Exception as e:
            # Better error handling
            if "opensearch" in str(e):
                raise Exception("ArXiv API XML parsing error with opensearch namespace. Using direct element paths instead.")
            else:
                raise Exception(f"Error searching ArXiv: {str(e)}")

def calculate_relevance_score(paper: Dict[str, Any], query_terms: List[str]) -> float:
    """
    Calculate relevance score of a paper to the search query.
    Higher scores mean more relevant papers.
    """
    score = 0.0
    
    # Convert title and summary to lowercase for case-insensitive matching
    title = paper['title'].lower()
    summary = paper['summary'].lower()
    
    # Check for query terms in title (weighted higher)
    for term in query_terms:
        if term.lower() in title:
            score += 3.0
        if term.lower() in summary:
            score += 1.0
    
    # Additional scoring for recency
    if paper.get('published'):
        try:
            year = int(paper['published'][:4])
            current_year = datetime.now().year
            # More recent papers get higher scores
            recency_bonus = min(1.0, max(0.1, (year - 2010) / (current_year - 2010 + 1)))
            score += recency_bonus
        except:
            # Default recency bonus if we can't parse the year
            score += 0.5
    else:
        # Default recency bonus
        score += 0.5
    
    return score

async def evaluate_papers(papers: List[Dict[str, Any]], query: str) -> List[Dict[str, Any]]:
    """
    Evaluate and rank papers by relevance to the query.
    Returns a sorted list of the most relevant papers.
    """
    # Prepare query terms, removing common words
    stop_words = set(['and', 'the', 'in', 'of', 'a', 'to', 'for', 'is', 'on', 'by'])
    query_terms = [term for term in query.split() if term.lower() not in stop_words]
    
    # Calculate relevance scores
    for paper in papers:
        paper['relevance_score'] = calculate_relevance_score(paper, query_terms)
    
    # Sort papers by relevance score (descending)
    sorted_papers = sorted(papers, key=lambda p: p['relevance_score'], reverse=True)
    
    # Determine how many papers to return (between 3 and 6)
    # Using a threshold of 1.0 for relevance score
    relevant_papers = [p for p in sorted_papers if p['relevance_score'] > 1.0]
    if len(relevant_papers) < 3:
        return sorted_papers[:min(3, len(sorted_papers))]  # Return at least 3 papers (or all if less than 3)
    elif len(relevant_papers) > 6:
        return relevant_papers[:6]  # Return at most 6 papers
    else:
        return relevant_papers  # Return all relevant papers

def format_paper_summary(paper: Dict[str, Any]) -> str:
    """
    Format paper metadata into a readable summary.
    """
    authors = ", ".join(paper['authors'][:3])
    if len(paper['authors']) > 3:
        authors += ", et al."
    
    paper_id = paper['id'].split('/')[-1] if paper['id'] else "unknown"  # Extract ID from URL
    
    summary = f"Title: {paper['title']}\n"
    summary += f"Authors: {authors}\n"
    summary += f"ArXiv ID: {paper_id}\n"
    if paper['pdf_url']:
        summary += f"URL: {paper['pdf_url']}\n"
    if paper['published']:
        summary += f"Published: {paper['published'][:10]}\n"  # Just the date part
    if paper['categories']:
        summary += f"Categories: {', '.join(paper['categories'])}\n\n"
    summary += f"Summary: {paper['summary'][:300]}...\n"
    
    return summary

def format_paper_citation(paper: Dict[str, Any]) -> str:
    """
    Format paper metadata into a citation.
    """
    authors = ", ".join(paper['authors'][:3])
    if len(paper['authors']) > 3:
        authors += ", et al."
    
    paper_id = paper['id'].split('/')[-1] if paper['id'] else "unknown"  # Extract ID from URL
    year = paper['published'][:4] if paper['published'] else "n.d."  # Extract year
    
    citation = f"{authors} ({year}). {paper['title']}. arXiv:{paper_id}."
    
    return citation

def format_citations(papers: List[Dict[str, Any]]) -> str:
    """
    Format papers into academic-style citations as footnotes.
    
    Args:
        papers: List of paper metadata dictionaries
        
    Returns:
        Formatted citation string
    """
    if not papers:
        return ""
    
    citations = "\n\n## References\n"
    
    for i, paper in enumerate(papers, 1):
        authors = ", ".join(paper.get('authors', [])[:3])
        if len(paper.get('authors', [])) > 3:
            authors += ", et al."
        
        paper_id = paper.get('id', '').split('/')[-1] if paper.get('id') else "unknown"
        year = paper.get('published', '')[:4] if paper.get('published') else "n.d."
        title = paper.get('title', 'Unknown title')
        
        citations += f"{i}. {authors} ({year}). {title}. arXiv:{paper_id}.\n"
    
    return citations

async def download_pdf(paper_id: str, pdf_url: str) -> str:
    """Download a PDF from ArXiv and return its local path."""
    # Create a cache filename
    cache_file = os.path.join(PDF_CACHE_DIR, f"{paper_id}.pdf")
    
    # Check if already in cache
    if os.path.exists(cache_file):
        return cache_file
    
    # Download the PDF
    try:
        response = requests.get(pdf_url, stream=True)
        response.raise_for_status()
        
        with open(cache_file, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        return cache_file
    except Exception as e:
        return f"Error downloading PDF: {str(e)}"

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text content from a PDF file."""
    try:
        text = ""
        with open(pdf_path, 'rb') as f:
            pdf_reader = PyPDF2.PdfReader(f)
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        return f"Error extracting text from PDF: {str(e)}"

async def read_paper(paper: Dict[str, Any]) -> Dict[str, Any]:
    """Download and read the content of a paper."""
    if not paper.get('pdf_url'):
        paper['content'] = "PDF URL not available"
        return paper
    
    paper_id = paper['id'].split('/')[-1] if paper['id'] else "unknown"
    
    # Download PDF
    pdf_path = await download_pdf(paper_id, paper['pdf_url'])
    
    # Check if download was successful
    if pdf_path.startswith("Error"):
        paper['content'] = pdf_path  # Store error message
        return paper
    
    # Extract text
    text = extract_text_from_pdf(pdf_path)
    paper['content'] = text
    
    return paper

def detect_download_intent(text: str) -> bool:
    """
    Detect if the user wants to download papers with improved pattern matching.
    
    Args:
        text: User's message text
        
    Returns:
        True if download intent detected, False otherwise
    """
    download_patterns = [
        r"download (?:all|the|these|those) (?:papers|articles|pdfs)",
        r"download (?:the )?papers?",
        r"can (?:you )?download",
        r"save (?:the|these|those) papers?",
        r"get (?:the|these|those) papers?",
        r"download paper \d+",
        r"download papers",
        r"download all",
        r"download arxiv",
        r"please download"
    ]
    
    text_lower = text.lower()
    for pattern in download_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return True
    
    # Also check for simple keyword matching for robustness
    download_keywords = ["download", "save papers", "get papers", "papers to my computer"]
    for keyword in download_keywords:
        if keyword in text_lower:
            return True
    
    return False

@mcp.tool()
async def arxiv_search(query: str, max_results: int = 10) -> str:
    """
    Search ArXiv for papers on a given topic.
    
    Args:
        query: The search query
        max_results: Maximum number of results to return (default: 10)
    """
    try:
        papers = await search_arxiv(query, max_results)
        global RECENT_PAPERS
        RECENT_PAPERS = papers
        
        if not papers:
            return f"No papers found matching '{query}'."
        
        result = f"Found {len(papers)} papers matching '{query}':\n\n"
        
        for i, paper in enumerate(papers, 1):
            result += f"{i}. {paper['title']}\n"
            authors = ", ".join(paper['authors'][:3])
            if len(paper['authors']) > 3:
                authors += ", et al."
            result += f"   Authors: {authors}\n"
            if paper['pdf_url']:
                result += f"   URL: {paper['pdf_url']}\n"
            if paper['published']:
                result += f"   Published: {paper['published'][:10]}\n\n"
        
        # Add citations
        result += format_citations(papers)
        
        # Add instructions for download
        result += "\nTo download any of these papers, simply ask me to 'download these papers' or 'download paper X'."
        
        return result
    
    except Exception as e:
        return f"Error searching ArXiv: {str(e)}"

@mcp.tool()
async def analyze_papers(query: str, max_results: int = 10) -> str:
    """
    Search, evaluate, and analyze papers from ArXiv on a given topic.
    Returns the most relevant papers with detailed summaries.
    
    Args:
        query: The search query
        max_results: Maximum initial results to analyze (default: 10)
    """
    try:
        # Search ArXiv
        all_papers = await search_arxiv(query, max_results)
        
        if not all_papers:
            return f"No papers found matching '{query}'."
        
        # Evaluate and rank papers
        relevant_papers = await evaluate_papers(all_papers, query)
        
        # Store for later reference
        global RECENT_PAPERS
        RECENT_PAPERS = relevant_papers
        
        # Format results
        result = f"Analysis of papers matching '{query}':\n\n"
        result += f"Found {len(relevant_papers)} relevant papers out of {len(all_papers)} results.\n\n"
        
        for i, paper in enumerate(relevant_papers, 1):
            result += f"--- Paper {i} ---\n"
            result += format_paper_summary(paper)
            result += f"Relevance Score: {paper['relevance_score']:.2f}\n\n"
        
        # Add citations
        result += format_citations(relevant_papers)
        
        # Add instructions for download
        result += "\nTo download these papers, simply ask me to 'download these papers'."
        
        return result
        
    except Exception as e:
        return f"Error analyzing papers: {str(e)}"

@mcp.tool()
async def read_papers(query: str, max_results: int = 10) -> str:
    """
    Search, select, download and read the most relevant papers from ArXiv.
    Identifies the 3-6 most relevant papers and provides detailed content analysis.
    
    Args:
        query: The search query
        max_results: Maximum initial results to search (default: 10)
    """
    try:
        # Search ArXiv
        all_papers = await search_arxiv(query, max_results)
        
        if not all_papers:
            return f"No papers found matching '{query}'."
        
        # Evaluate and rank papers
        relevant_papers = await evaluate_papers(all_papers, query)
        
        # Store for later reference
        global RECENT_PAPERS
        RECENT_PAPERS = relevant_papers
        
        # Start response
        result = f"Reading the most relevant papers for '{query}':\n\n"
        result += f"Selected {len(relevant_papers)} papers out of {len(all_papers)} results based on relevance.\n\n"
        
        # Download and read each paper
        paper_contents = []
        for i, paper in enumerate(relevant_papers, 1):
            result += f"--- Processing Paper {i}: {paper['title']} ---\n"
            
            if paper.get('pdf_url'):
                paper_id = paper['id'].split('/')[-1] if paper['id'] else "unknown"
                result += f"Downloading and reading paper (ArXiv ID: {paper_id})...\n"
                
                # Download and read
                paper_with_content = await read_paper(paper)
                
                if paper_with_content.get('content', '').startswith("Error"):
                    result += f"Error: {paper_with_content['content']}\n\n"
                else:
                    content_preview = paper_with_content.get('content', '')[:200] + "..."
                    result += f"Successfully read paper. Content length: {len(paper_with_content.get('content', ''))} characters\n"
                    result += f"Content preview: {content_preview}\n\n"
                    paper_contents.append(paper_with_content)
            else:
                result += "PDF URL not available for this paper.\n\n"
        
        # Summarize findings
        if paper_contents:
            result += "Paper Reading Complete\n\n"
            result += f"Successfully read {len(paper_contents)} papers on '{query}'.\n"
            result += "You can now ask more specific questions about the paper contents.\n"
            
            # ALWAYS add citations
            result += format_citations(relevant_papers)
            
            # Add instructions for download
            result += "\nTo download these papers, simply reply with 'download these papers'."
        else:
            result += "Could not read any papers. Please try a different query or check for errors above."
        
        return result
        
    except Exception as e:
        return f"Error reading papers: {str(e)}"

@mcp.tool()
async def research_question(question: str, max_results: int = 15) -> str:
    """
    Research a question using ArXiv papers.
    Searches for relevant papers, analyzes them, and provides an answer.
    
    Args:
        question: The research question to answer
        max_results: Maximum initial results to analyze (default: 15)
    """
    try:
        # Convert question to search query
        query = question.replace("?", "").replace("!", "")
        
        # Search ArXiv
        all_papers = await search_arxiv(query, max_results)
        
        if not all_papers:
            return f"No papers found relevant to your question: '{question}'"
        
        # Evaluate and rank papers
        relevant_papers = await evaluate_papers(all_papers, query)
        
        # Store for later reference
        global RECENT_PAPERS
        RECENT_PAPERS = relevant_papers
        
        # Download and read each paper
        paper_contents = []
        for paper in relevant_papers:
            if paper.get('pdf_url'):
                paper_with_content = await read_paper(paper)
                paper_contents.append(paper_with_content)
        
        # Format answer
        answer = f"Research findings on: {question}\n\n"
        answer += f"I analyzed {len(paper_contents)} relevant papers from ArXiv to answer your question.\n\n"
        
        # Provide key findings
        answer += "Key papers on this topic:\n\n"
        
        for i, paper in enumerate(paper_contents[:3], 1):  # Show top 3 papers
            answer += f"{i}. {paper['title']}\n"
            if paper['published']:
                answer += f"   Published: {paper['published'][:10]}\n"
            answer += f"   Summary: {paper['summary'][:200]}...\n"
            
            # Extract some content from the paper
            content = paper.get('content', '')
            if content and not content.startswith("Error"):
                # Show a small excerpt
                excerpt = content[:300].replace('\n', ' ')
                answer += f"   Excerpt: {excerpt}...\n\n"
            else:
                answer += "\n"
        
        # ALWAYS add citations explicitly
        answer += format_citations(relevant_papers)
        
        # Add instructions for download
        answer += "\nTo download these papers, simply ask me to 'download these papers'."
        
        return answer
        
    except Exception as e:
        return f"Error researching question: {str(e)}"

@mcp.tool()
async def academic_research(question: str, max_results: int = 15, year_from: int = 2010) -> str:
    """
    Conduct academic research focusing on ArXiv papers with priority over web search.
    Particularly useful for academic and scientific questions.
    
    Args:
        question: The research question to answer
        max_results: Maximum number of papers to analyze (default: 15)
        year_from: Only include papers published from this year onward (default: 2010)
    """
    try:
        # Refine the query to include year constraint if needed
        query = question.replace("?", "").replace("!", "")
        if year_from > 2010:  # Only add year constraint if different from default
            query += f" {year_from}-{datetime.now().year}"
        
        # Get papers from ArXiv
        papers_result = await research_question(query, max_results)
        
        # Return the specialized academic research result
        intro = f"# Academic Research on: {question}\n\n"
        intro += "I've conducted specialized academic research using ArXiv papers. Here are my findings:\n\n"
        
        # Combine with the paper results, which already include citations
        full_response = intro + papers_result
        
        return full_response
    
    except Exception as e:
        return f"Error conducting academic research: {str(e)}"

@mcp.tool()
async def download_papers_to_user(specific_ids: List[str] = None, download_all: bool = False) -> str:
    """
    Download papers to the user's local machine.
    
    Args:
        specific_ids: Optional list of specific paper IDs to download
        download_all: Whether to download all recent papers
        
    Returns:
        Status message about the download
    """
    try:
        global RECENT_PAPERS
        if not RECENT_PAPERS and not specific_ids:
            return "No papers have been searched or specified for download. Please search for papers first."
        
        # Determine which papers to download
        papers_to_download = []
        
        if download_all and RECENT_PAPERS:
            papers_to_download = RECENT_PAPERS
        elif specific_ids:
            papers_to_download = [p for p in RECENT_PAPERS if p['id'].split('/')[-1] in specific_ids]
        
        if not papers_to_download:
            return "No valid papers found to download."
        
        # Download papers
        success_count = 0
        failed_count = 0
        downloaded_papers = []
        
        for paper in papers_to_download:
            if not paper.get('pdf_url'):
                failed_count += 1
                continue
            
            paper_id = paper['id'].split('/')[-1] if paper['id'] else "unknown"
            safe_title = re.sub(r'[\\/*?:"<>|]', "", paper['title'])[:100]  # Create safe filename
            filename = f"{paper_id}_{safe_title}.pdf"
            filepath = os.path.join(DOWNLOAD_DIR, filename)
            
            try:
                response = requests.get(paper['pdf_url'], stream=True)
                response.raise_for_status()
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                success_count += 1
                downloaded_papers.append((paper_id, paper['title'], filepath))
            except Exception:
                failed_count += 1
        
        # Generate report
        result = f"Downloaded {success_count} papers to {DOWNLOAD_DIR}:\n\n"
        
        for paper_id, title, path in downloaded_papers:
            result += f"- {title} (arXiv:{paper_id})\n  Saved to: {path}\n"
        
        if failed_count > 0:
            result += f"\nFailed to download {failed_count} papers."
        
        return result
    
    except Exception as e:
        return f"Error downloading papers: {str(e)}"

@mcp.tool()
async def download_recent_papers() -> str:
    """
    Download all recently accessed papers with one command.
    Shortcut for downloading all papers from the latest search.
    
    Returns:
        Status message about the download
    """
    return await download_papers_to_user(download_all=True)

@mcp.tool()
async def parse_download_request(message: str) -> str:
    """
    Parse a user message for download intent and handle the request.
    
    Args:
        message: User message that may contain download request
        
    Returns:
        Result of download operation or error message
    """
    try:
        if not detect_download_intent(message):
            return "No download request detected. To download papers, ask me to 'download these papers' or similar."
        
        # Check for specific paper mentions
        paper_number_match = re.search(r"paper (\d+)", message, re.IGNORECASE)
        paper_numbers = []
        
        if paper_number_match:
            paper_numbers.append(int(paper_number_match.group(1)))
        
        # Check for multiple papers
        papers_range_match = re.search(r"papers (\d+)(?:\s*-\s*|\s*to\s*)(\d+)", message, re.IGNORECASE)
        if papers_range_match:
            start = int(papers_range_match.group(1))
            end = int(papers_range_match.group(2))
            paper_numbers.extend(range(start, end + 1))
        
        global RECENT_PAPERS
        if paper_numbers:
            # Convert paper numbers to IDs
            if not RECENT_PAPERS:
                return "No papers have been searched yet. Please search for papers first."
            
            specific_ids = []
            for num in paper_numbers:
                if 1 <= num <= len(RECENT_PAPERS):
                    paper_id = RECENT_PAPERS[num-1]['id'].split('/')[-1]
                    specific_ids.append(paper_id)
            
            return await download_papers_to_user(specific_ids=specific_ids)
        else:
            # Download all recent papers
            return await download_papers_to_user(download_all=True)
    
    except Exception as e:
        return f"Error processing download request: {str(e)}"

@mcp.tool()
async def handle_paper_command(command: str) -> str:
    """
    Process various paper-related commands including downloads.
    
    Args:
        command: User command string
        
    Returns:
        Result of command processing
    """
    command_lower = command.lower()
    
    # Check for download intent
    if detect_download_intent(command_lower):
        # Extract specific paper numbers if present
        paper_numbers = []
        paper_matches = re.finditer(r"paper (\d+)", command_lower)
        for match in paper_matches:
            paper_numbers.append(int(match.group(1)))
        
        # Check for paper ranges
        range_match = re.search(r"papers (\d+)[- ](\d+)", command_lower)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2))
            paper_numbers.extend(range(start, end + 1))
        
        # Process download
        global RECENT_PAPERS
        if paper_numbers:
            specific_ids = []
            for num in paper_numbers:
                if 1 <= num <= len(RECENT_PAPERS):
                    paper_id = RECENT_PAPERS[num-1]['id'].split('/')[-1]
                    specific_ids.append(paper_id)
            return await download_papers_to_user(specific_ids=specific_ids)
        else:
            return await download_papers_to_user(download_all=True)
    
    # Handle other paper-related commands here if needed
    return "Unknown paper command. For downloads, please say 'download these papers' or 'download paper X'."

@mcp.tool()
async def server_info(query: str = None) -> str:
    """
    Provide information about the Socrates MCP server.
    
    Args:
        query: Optional specific information to query about the server
    
    Returns:
        Server information
    """
    info = "Socrates Academic Research Assistant\n\n"
    info += "Version: 3.0.0\n"
    info += "Owner: Universitas AI\n"
    info += "Type: Model Context Protocol (MCP) Server\n\n"
    
    if query and "capabilities" in query.lower():
        info += "Capabilities:\n"
        info += "- Search arXiv for scientific papers\n"
        info += "- Analyze and evaluate papers by relevance\n"
        info += "- Extract and read full paper content\n"
        info += "- Generate proper academic citations\n"
        info += "- Answer research questions with citations\n"
        info += "- Download papers for offline access\n"
    elif query and "connection" in query.lower():
        info += "Connection Information:\n"
        info += "- Compatible with any AI assistant that supports MCP\n"
        info += "- Designed for use with NANDA client from MIT Media Lab\n"
        info += "- Works with Claude, GPT, Llama, Grok, and other LLMs\n"
    else:
        info += "Socrates is a specialized academic research assistant that helps you discover, analyze,\n"
        info += "and understand scientific papers from arXiv. It can search for papers, evaluate their\n"
        info += "relevance, extract their content, and provide answers to research questions with\n"
        info += "automatic citations. It can also download papers for offline reading.\n\n"
        info += "This server works with any AI that supports the Model Context Protocol (MCP),\n"
        info += "including Claude, GPT, Llama, Grok, and others via the NANDA client."
    
    return info

# Main execution
if __name__ == "__main__":
    # Run the server
    mcp.run(transport='stdio')