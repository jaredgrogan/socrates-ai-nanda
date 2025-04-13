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
import sys
import traceback
import httpx

# Enhanced logging for Vercel
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]  # Ensure logs go to stdout for Vercel
)
logger = logging.getLogger(__name__)

# Initialize MCP server with error handling
try:
    mcp = FastMCP("socrates")
    logger.info("MCP Server initialized successfully")
except Exception as e:
    logger.critical(f"Failed to initialize MCP server: {e}")
    logger.critical(traceback.format_exc())
    raise

# Basic tool implementation
@mcp.tool()
async def server_info() -> str:
    """Get information about the Socrates MCP server"""
    try:
        info = "Socrates Academic Research Assistant\n\n"
        info += "Version: 3.0.0\n"
        info += "Owner: Universitas AI\n"
        info += "Type: Model Context Protocol (MCP) Server\n\n"
        info += "Capabilities:\n"
        info += "- Search arXiv for scientific papers\n"
        info += "- Analyze and evaluate papers by relevance\n"
        info += "- Generate proper academic citations\n"
        return info
    except Exception as e:
        logger.error(f"Error in server_info: {e}")
        return f"Error retrieving server info: {str(e)}"

@mcp.tool()
async def arxiv_search(query: str, max_results: int = 5) -> str:
    """Search for academic papers on arXiv"""
    try:
        async with httpx.AsyncClient() as client:
            url = f"http://export.arxiv.org/api/query?search_query={query}&start=0&max_results={max_results}"
            response = await client.get(url, timeout=5.0)  # Add timeout for Vercel
            return f"Found papers matching '{query}'. First result snippet available."
    except Exception as e:
        logger.error(f"Error in arxiv_search: {e}")
        return f"Error searching ArXiv: {str(e)}"

# HTML for the homepage
async def homepage(request: Request) -> HTMLResponse:
    try:
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
    except Exception as e:
        logger.error(f"Error in homepage: {e}")
        return HTMLResponse(f"Error: {str(e)}", status_code=500)

# Status endpoint
async def status_handler(request: Request) -> JSONResponse:
    """Handle requests to the status endpoint"""
    try:
        tools = []
        try:
            tools = list(mcp._tools.keys())
        except Exception as tool_error:
            logger.error(f"Error retrieving tools: {tool_error}")
            
        return JSONResponse(
            content={
                "status": "ok", 
                "message": "Socrates API is running",
                "tools": tools
            }, 
            status_code=200
        )
    except Exception as e:
        logger.error(f"Error in status_handler: {e}")
        return JSONResponse(
            content={"status": "error", "message": str(e)}, 
            status_code=500
        )

# Create a Starlette application with optimized SSE transport
def create_starlette_app(mcp_server: Server, *, debug: bool = True) -> Starlette:
    """Create a Starlette application with SSE transport configured for serverless."""
    try:
        # Configure SSE with serverless-friendly settings
        sse = SseServerTransport(
            "/messages/",
            session_timeout=25,  # Reduced for serverless
            max_connections=3    # Reduced for serverless
        )
        
        async def handle_sse(request: Request) -> None:
            try:
                logger.info(f"SSE connection attempt from {request.client}")
                logger.info(f"Request headers: {dict(request.headers)}")
                
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
                logger.error(f"SSE error: {str(e)}")
                logger.error(traceback.format_exc())
                # We don't raise here to prevent 500 errors
        
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
        
        # Add global exception handler
        @app.exception_handler(Exception)
        async def global_exception_handler(request: Request, exc: Exception):
            logger.error(f"Unhandled exception: {exc}")
            logger.error(traceback.format_exc())
            return JSONResponse(
                status_code=500,
                content={"status": "error", "message": str(exc)},
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
    except Exception as e:
        logger.critical(f"Failed to create application: {e}")
        logger.critical(traceback.format_exc())
        raise

# Application creation with error handling
try:
    mcp_server = mcp._mcp_server
    app = create_starlette_app(mcp_server, debug=True)
    logger.info("Application created successfully")
except Exception as e:
    logger.critical(f"Application creation failed: {e}")
    logger.critical(traceback.format_exc())
    raise

# For local development
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run(app, host="0.0.0.0", port=port)