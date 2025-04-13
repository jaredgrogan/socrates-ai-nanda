from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

# Create FastAPI app instead of Starlette
app = FastAPI()

# Configure CORS to be fully open
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/")
async def public_root():
    """
    Public root endpoint for NANDA registry compatibility
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "Socrates NANDA Registry",
            "version": "3.0.0",
            "public_access": True,
            "endpoints": [
                "/",
                "/status",
                "/sse"
            ]
        }
    )

@app.get("/status")
async def status():
    """
    Simple status endpoint
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "running",
            "message": "NANDA Registry endpoint is active"
        }
    )