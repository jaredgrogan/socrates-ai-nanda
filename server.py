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
import httpx
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Dict, Any

# Initialize MCP server
mcp = FastMCP("socrates-ai")

# Logging configuration
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Tracked tools list
registered_tools = []

def track_tool(func):
    """Decorator to track registered tools"""
    registered_tools.append(func.__name__)
    return mcp.tool()(func)

# Tools and Resources
@track_tool
async def get_server_info() -> str:
    """Provide comprehensive server information"""
    return """
    Socrates Academic Research Assistant
    Version: 3.0.0
    Owner: Universitas AI
    Type: Model Context Protocol (MCP) Server
    Capabilities: 
    - Scientific paper search
    - Research analysis
    - Citation generation
    """

@track_tool
async def search_arxiv(query: str, max_results: int = 5) -> str:
    """Search academic papers on arXiv"""
    async with httpx.AsyncClient() as client:
        url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}"
        response = await client.get(url)
        return response.text

# Application lifespan management
@asynccontextmanager
async def app_lifespan(app: Starlette):
    logger.info("Starting Socrates MCP Server")
    yield
    logger.info("Shutting down Socrates MCP Server")

# Create Starlette Application
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
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

    async def root_endpoint(request: Request) -> JSONResponse:
        return JSONResponse(
            status_code=200,
            content={
                "status": "ok",
                "service": "Socrates NANDA MCP",
                "version": "3.0.0",
                "protocol": "Model Context Protocol",
                "public_access": True,
                "tools": registered_tools,
                "message": "MCP Server successfully initialized"
            }
        )

    app = Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=root_endpoint),
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
        lifespan=app_lifespan
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

# Server runner
def run_server(host="0.0.0.0", port=8080):
    uvicorn.run(app, host=host, port=port)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    run_server(port=port)