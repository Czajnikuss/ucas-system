import os
import redis
import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response

app = FastAPI(
    title="UCAS API Gateway",
    version="1.1.0",
    description="Universal Categorization as a Service - API Gateway (Dynamic Routing)",
    docs_url="/swagger"
)

REDIS_HOST = os.getenv("REDIS_HOST", "redis")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD", "ucas_redis_pass")
ORCHESTRATOR_URL = os.getenv("ORCHESTRATOR_URL", "http://orchestrator:8001")

try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=6379,
        password=REDIS_PASSWORD,
        decode_responses=True
    )
    redis_client.ping()
    print(f"✅ Connected to Redis at {REDIS_HOST}")
except Exception as e:
    print(f"🔴 Redis connection failed: {e}")
    redis_client = None

@app.get("/")
async def root():
    return {
        "service": "UCAS API Gateway",
        "status": "running",
        "routing": "dynamic",
        "version": "1.1.0"
    }

@app.get("/health")
async def health_check():
    redis_status = "disconnected"
    orchestrator_status = "unknown"
    
    if redis_client:
        try:
            redis_client.ping()
            redis_status = "healthy"
        except Exception:
            redis_status = "unhealthy"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{ORCHESTRATOR_URL}/health", timeout=3.0)
            if response.status_code == 200:
                orchestrator_status = "healthy"
    except Exception:
        orchestrator_status = "unreachable"
    
    overall_status = "healthy" if redis_status == "healthy" and orchestrator_status == "healthy" else "degraded"
    
    return {
        "status": overall_status,
        "services": {
            "redis": redis_status,
            "orchestrator": orchestrator_status
        }
    }

@app.get("/test/redis")
async def test_redis():
    if not redis_client:
        raise HTTPException(status_code=503, detail="Redis not available")
    
    redis_client.set("api_test", "Gateway is working!", ex=60)
    value = redis_client.get("api_test")
    
    return {
        "redis_connection": "OK",
        "test_value": value
    }

@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def gateway_route(path: str, request: Request):
    """Dynamiczne proxy przekierowujące zapytania do Orchestratora"""
    target_url = f"{ORCHESTRATOR_URL}/{path}"
    
    body = await request.body()
    headers = dict(request.headers)
    
    # Wycinamy Host, żeby httpx wstawił poprawny host wewnętrzny kontenera
    headers.pop("host", None)
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=request.method,
                url=target_url,
                headers=headers,
                params=request.query_params,
                content=body,
                timeout=60.0
            )
            
            return Response(
                content=response.content,
                status_code=response.status_code,
                headers=dict(response.headers)
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=503, detail=f"Target service unreachable: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)