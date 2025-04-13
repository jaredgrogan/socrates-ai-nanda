from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, StreamingResponse
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn
import os
import logging
import traceback
import httpx
import asyncio

# Set up comprehensive logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize MCP server directly
mcp = FastMCP("socrates")

# Use Vercel-compatible storage paths
CACHE_DIR = "/tmp/socrates_cache"
PDF_CACHE_DIR = "/tmp/socrates_pdfs"
DOWNLOAD_DIR = "/tmp/arxiv_papers"

# Create directories with proper error handling
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
    os.makedirs(PDF_CACHE_DIR, exist_ok=True)
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
except Exception as e:
    logger.warning(f"Could not create directories: {e}")

# Basic tool implementation
@mcp.tool()
async def server_info() -> str:
    """Get information about the Socrates MCP server"""
    info = "Socrates Academic Research Assistant\n\n"
    info += "Version: 3.0.0\n"
    info += "Owner: Universitas AI\n"
    info += "Type: Model Context Protocol (MCP) Server\n\n"
    info += "Capabilities:\n"
    info += "- Search arXiv for scientific papers\n"
    info += "- Analyze and evaluate papers by relevance\n"
    info += "- Generate proper academic citations\n"
    return info

@mcp.tool()
async def arxiv_search(query: str, max_results: int = 5) -> str:
    """Search for academic papers on arXiv"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}"
            response = await client.get(url)
            return f"Found papers matching '{query}'. First result: {response.text[:200]}..."
    except Exception as e:
        return f"Error searching ArXiv: {str(e)}"

# HTML for the homepage
async def homepage(request: Request) -> HTMLResponse:
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Socrates API</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
        </style>
    </head>
    <body>
        <h1>Socrates AI</h1>
        <p>Academic Research Assistant by Universitas AI</p>
        <p>Status: Running</p>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

# Status endpoint
async def status_handler(request: Request) -> JSONResponse:
    """Handle requests to the status endpoint"""
    return JSONResponse(
        content={"status": "ok", "message": "Socrates API is running"}, 
        status_code=200
    )

# New SSE stream endpoint
async def sse_stream(request: Request) -> StreamingResponse:
    async def event_generator():
        try:
            while True:
                # Generate MCP-compatible SSE events
                yield f"data: {{\n"
                yield f"  'type': 'keepalive',\n"
                yield f"  'timestamp': {asyncio.get_event_loop().time()},\n"
                yield f"  'tools': {list(mcp._tools.keys())}\n"
                yield f"}}\n\n"
                await asyncio.sleep(15)
        except asyncio.CancelledError:
            logger.info("SSE stream cancelled")

    return StreamingResponse(
        event_generator(), 
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

# Create a Starlette application with SSE transport
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application with SSE transport."""
    sse = SseServerTransport("/messages/")
    
    async def handle_sse(request: Request) -> None:
        try:
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as (read_stream, write_stream):
                await mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp_server.create_initialization_options(),
                )
        except Exception as e:
            logger.error(f"SSE error: {traceback.format_exc()}")
            raise
    
    # Create base app with routes
    app = Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=homepage, methods=["GET"]),
            Route("/status", endpoint=status_handler, methods=["GET"]),
            Route("/sse", endpoint=handle_sse),
            Route("/sse-stream", endpoint=sse_stream),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )
    
    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    
    return app

# Application creation
mcp_server = mcp._mcp_server
app = create_starlette_app(mcp_server, debug=True)

# For local development
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8080)