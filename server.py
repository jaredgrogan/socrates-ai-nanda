from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware.cors import CORSMiddleware
from mcp.server.sse import SseServerTransport
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Mount, Route
from mcp.server import Server
import uvicorn
import os
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Dict, Any

# Import your MCP server - CRITICAL LINE
from socrates import mcp

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Set up the application context
@asynccontextmanager
async def app_lifespan(server: Server) -> AsyncIterator[Dict[str, Any]]:
    """Initialize application components"""
    logger.info("Starting Socrates server")
    # Initialize any resources you need
    yield {}  # Empty context for now
    logger.info("Shutting down Socrates server")

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
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                max-width: 800px;
                margin: 0 auto;
                padding: 20px;
            }
            h1 {
                margin-bottom: 10px;
            }
            p {
                line-height: 1.6;
            }
        </style>
    </head>
    <body>
        <h1>Socrates API</h1>
        <p>This is the Socrates academic research assistant API.</p>
        <p>Status: Running</p>
        <p>This server provides academic research tools including:</p>
        <ul>
            <li>ArXiv paper search</li>
            <li>Paper analysis</li>
            <li>Citation generation</li>
            <li>Research question answering</li>
        </ul>
    </body>
    </html>
    """
    return HTMLResponse(html_content)

# Status endpoint
async def status_handler(request: Request) -> JSONResponse:
    """Handle requests to the status endpoint"""
    return JSONResponse(
        content={
            "status": "ok", 
            "message": "Socrates API is running",
            "version": "3.0.0",
            "provider": "Universitas AI",
            "service": "Socrates Academic Research Assistant"
        }, 
        status_code=200
    )

# Create a Starlette application with SSE transport
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application with SSE transport."""
    sse = SseServerTransport("/messages/")
    
    async def handle_sse(request: Request) -> None:
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
    
    # Create base app with routes
    app = Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=homepage, methods=["GET"]),
            Route("/status", endpoint=status_handler, methods=["GET"]),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
        lifespan=app_lifespan
    )
    
    # Add CORS middleware for broader compatibility
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )
    
    return app

def run_server(host="0.0.0.0", port=8080, debug=True):
    """Run the Socrates MCP server"""
    mcp_server = mcp._mcp_server
    app = create_starlette_app(mcp_server, debug=debug)
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.environ.get("PORT", 8080))
    run_server(port=port)