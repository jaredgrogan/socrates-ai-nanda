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
import sys
import traceback

# Import your existing MCP server
from socrates_main import mcp

# Enhanced logging for Render
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

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
    tools = []
    try:
        tools = list(mcp._tools.keys())
    except Exception as e:
        logger.error(f"Error getting tools: {e}")
        
    return JSONResponse(
        content={
            "status": "ok", 
            "message": "Socrates API is running",
            "tools": tools
        }, 
        status_code=200
    )

# Create a Starlette application with SSE transport
def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application with SSE transport."""
    sse = SseServerTransport("/messages/")
    
    async def handle_sse(request: Request) -> None:
        try:
            logger.info(f"SSE connection attempt from {request.client}")
            async with sse.connect_sse(
                request.scope,
                request.receive,
                request._send,
            ) as (read_stream, write_stream):
                logger.info("SSE connection established successfully")
                await mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp_server.create_initialization_options(),
                )
        except Exception as e:
            logger.error(f"SSE error: {traceback.format_exc()}")
    
    # Create base app with routes
    app = Starlette(
        debug=debug,
        routes=[
            Route("/", endpoint=homepage, methods=["GET"]),
            Route("/status", endpoint=status_handler, methods=["GET"]),
            Route("/sse", endpoint=handle_sse),
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
try:
    mcp_server = mcp._mcp_server
    app = create_starlette_app(mcp_server, debug=True)
    logger.info("Application created successfully")
except Exception as e:
    logger.critical(f"Failed to create application: {e}")
    logger.critical(traceback.format_exc())
    raise

# For local development and Render
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(app, host="0.0.0.0", port=port)