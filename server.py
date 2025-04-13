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
import json
import sys

# Enhanced Logging Configuration
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),  # Output to console
        logging.FileHandler('/tmp/socrates_mcp_detailed.log', mode='a')  # Append mode for persistent logging
    ]
)
logger = logging.getLogger(__name__)

# Comprehensive Exception Handling
def log_unhandled_exceptions(exc_type, exc_value, exc_traceback):
    logger.critical(
        "Uncaught exception",
        exc_info=(exc_type, exc_value, exc_traceback)
    )

sys.excepthook = log_unhandled_exceptions

# Initialize MCP server with error handling
try:
    mcp = FastMCP("socrates")
    logger.info("MCP Server initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize MCP server: {e}")
    logger.critical(traceback.format_exc())
    raise

# Use Vercel-compatible storage paths with extensive logging
CACHE_DIR = "/tmp/socrates_cache"
PDF_CACHE_DIR = "/tmp/socrates_pdfs"
DOWNLOAD_DIR = "/tmp/arxiv_papers"

# Create directories with comprehensive error handling
try:
    for directory in [CACHE_DIR, PDF_CACHE_DIR, DOWNLOAD_DIR]:
        try:
            os.makedirs(directory, exist_ok=True)
            logger.info(f"Successfully created directory: {directory}")
        except Exception as dir_error:
            logger.error(f"Could not create directory {directory}: {dir_error}")
except Exception as e:
    logger.critical(f"Critical error creating directories: {e}")
    logger.critical(traceback.format_exc())

# Rest of the implementation remains the same as in the previous version...

# Modified create_starlette_app with enhanced error handling
def create_starlette_app(mcp_server: Server, *, debug: bool = True) -> Starlette:
    """Create a Starlette application with enhanced error logging and diagnostics"""
    sse = SseServerTransport(
        "/messages/", 
        session_timeout=120,
        max_connections=20
    )
    
    async def handle_sse(request: Request) -> None:
        try:
            # Extensive connection logging
            logger.info(f"SSE connection attempt from {request.client}")
            logger.info(f"Request headers: {dict(request.headers)}")
            logger.info(f"Request scope: {request.scope}")
            
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as (read_stream, write_stream):
                logger.info("SSE connection established successfully")
                
                try:
                    await mcp_server.run(
                        read_stream,
                        write_stream,
                        mcp_server.create_initialization_options(),
                    )
                except Exception as run_error:
                    logger.error(f"MCP server run error: {run_error}")
                    logger.error(traceback.format_exc())
                    raise
        except Exception as connection_error:
            logger.error(f"SSE connection error: {connection_error}")
            logger.error(traceback.format_exc())
            raise

    # Create base app with routes
    app = Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=homepage, methods=["GET"]),
            Route("/status", endpoint=status_handler, methods=["GET"]),
            Route("/sse", endpoint=handle_sse),
            Route("/sse-debug", endpoint=sse_debug),
            Mount("/messages/", app=sse.handle_post_message),
        ]
    )
    
    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.critical(f"Unhandled exception in request: {exc}")
        logger.critical(traceback.format_exc())
        return JSONResponse(
            status_code=500, 
            content={
                "error": "Internal Server Error",
                "details": str(exc),
                "traceback": traceback.format_exc()
            }
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

# Comprehensive tool registration logging
try:
    registered_tools = list(mcp._tools.keys())
    logger.info(f"Registered MCP Tools: {registered_tools}")
except Exception as e:
    logger.critical(f"Error retrieving registered tools: {e}")
    logger.critical(traceback.format_exc())
    registered_tools = []

# Application creation with error handling
try:
    mcp_server = mcp._mcp_server
    app = create_starlette_app(mcp_server, debug=True)
    logger.info("Application created successfully")
except Exception as e:
    logger.critical(f"Failed to create application: {e}")
    logger.critical(traceback.format_exc())
    raise

# For local development
if __name__ == "__main__":
    try:
        uvicorn.run(app, host="0.0.0.0", port=8080)
    except Exception as e:
        logger.critical(f"Server startup failed: {e}")
        logger.critical(traceback.format_exc())
        raise