from fastapi import FastAPI, status
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

@app.get("/", status_code=status.HTTP_200_OK)
async def root():
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "service": "Socrates NANDA MCP",
            "version": "1.0.0",
            "public_access": True,
            "message": "Endpoint successfully accessed"
        }
    )

@app.get("/status", status_code=status.HTTP_200_OK)
async def status():
    return JSONResponse(
        status_code=200,
        content={
            "status": "running",
            "message": "Endpoint is publicly accessible"
        }
    )