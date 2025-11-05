# services/dashboard-admin/main.py
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import httpx
import os

app = FastAPI(title="UCAS Admin Dashboard")
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

ORCHESTRATOR_URL = os.getenv('ORCHESTRATOR_URL', 'http://orchestrator:8001')
EVALUATOR_URL = os.getenv('EVALUATOR_URL', 'http://evaluator:8060')

@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            cats_resp = await client.get(f"{ORCHESTRATOR_URL}/categorizers")
            categorizers = cats_resp.json() if cats_resp.status_code == 200 else []
        except:
            categorizers = []
        
        try:
            health_resp = await client.get(f"{ORCHESTRATOR_URL}/health")
            health = health_resp.json() if health_resp.status_code == 200 else {}
        except:
            health = {"status": "error"}
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "categorizers": categorizers,
        "health": health,
        "total_categorizers": len(categorizers)
    })

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dashboard-admin"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
