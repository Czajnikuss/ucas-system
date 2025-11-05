# services/dashboard-hil/main.py
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import httpx
import os

app = FastAPI(title="UCAS HIL Review Dashboard")
templates = Jinja2Templates(directory="templates")

HIL_LAYER_URL = os.getenv('HIL_LAYER_URL', 'http://hil-layer:8040')

@app.get("/", response_class=HTMLResponse)
async def hil_home(request: Request):
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            pending_resp = await client.get(f"{HIL_LAYER_URL}/pending?limit=50")
            pending = pending_resp.json() if pending_resp.status_code == 200 else []
        except:
            pending = []
    
    return templates.TemplateResponse("hil_queue.html", {
        "request": request,
        "pending_reviews": pending,
        "total_pending": len(pending)
    })

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "dashboard-hil"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8081)
