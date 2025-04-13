from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

app = FastAPI()

# Aggressive CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

@app.get("/", response_class=JSONResponse)
async def root():
    return {
        "status": "public",
        "service": "Socrates NANDA MCP",
        "version": "1.0.0",
        "public_access": True
    }

@app.get("/status", response_class=JSONResponse)
async def status():
    return {
        "status": "running",
        "message": "Endpoint is publicly accessible"
    }