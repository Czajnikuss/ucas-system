from fastapi import FastAPI, HTTPException, Depends
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel
from typing import Dict, List, Optional
from sqlalchemy.orm import Session
from datetime import datetime
import httpx
import asyncio
import re
from unidecode import unidecode
from sqlalchemy import text
from persistence import save_layer_state, load_layer_state
from models.database import SessionLocal
from models.database import init_db, get_db, Categorizer, TrainingSample, Classification
from config_loader import config
from api import training, management, classification, analytics, rag
from contextlib import asynccontextmanager

async def initialize_persistence_background():
    """Wczytuje stan modeli z dysku i wstrzykuje go z powrotem do warstw w RAM"""
    print("✅ Zaczynam wczytywanie persistence w tle...", flush=True)
    # Czekamy 2 sekundy, żeby warstwy podrzędne zdążyły całkowicie wstać
    await asyncio.sleep(2) 
    
    from persistence import PERSIST_DIR, load_layer_state
    
    if not PERSIST_DIR.exists():
        print("🔴 PERSISTENCE: Brak katalogu z danymi", flush=True)
        return
        
    restored = 0
    for cat_dir in PERSIST_DIR.iterdir():
        if not cat_dir.is_dir():
            continue
            
        categorizer_id = cat_dir.name
        
        db_session = SessionLocal()
        try:
            db_cat = db_session.query(Categorizer).filter_by(categorizer_id=categorizer_id).first()
            if not db_cat:
                continue
                
            layers = db_cat.layers or []
            
            async with httpx.AsyncClient(timeout=60.0) as client:
                # 1. Restore LLM
                if "llm" in layers:
                    llm_config = load_layer_state(categorizer_id, "llm")
                    if llm_config:
                        try:
                            await client.post(f"{config.get('orchestrator.layers.llm.url')}/train", json={
                                "categorizer_id": categorizer_id,
                                "training_data": llm_config.get("training_samples", []),
                                "model": llm_config.get("model", "phi3:mini"),
                                "fallback_category": llm_config.get("fallback_category")
                            })
                            print(f"✅ PERSISTENCE: Przywrócono stan LLM dla {categorizer_id}", flush=True)
                            restored += 1
                        except Exception as e:
                            print(f"🔴 PERSISTENCE: Błąd przywracania LLM dla {categorizer_id}: {e}", flush=True)
                
                # 2. Restore Tags
                if "tags" in layers:
                    tags_state = load_layer_state(categorizer_id, "tags")
                    if tags_state:
                        try:
                            await client.post(f"{config.get('orchestrator.layers.tags.url')}/restore", json={
                                "categorizer_id": categorizer_id,
                                "keywords": tags_state.get("keywords", {}),
                                "categories": tags_state.get("categories", [])
                            })
                            print(f"✅ PERSISTENCE: Przywrócono stan Tags dla {categorizer_id}", flush=True)
                        except Exception as e:
                            print(f"🔴 PERSISTENCE: Błąd przywracania Tags dla {categorizer_id}: {e}", flush=True)
        finally:
            db_session.close()
            
    print(f"✅ Persistence zakończone. Przywrócono do pamięci operacyjnej: {restored} modeli.", flush=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    task = asyncio.create_task(initialize_persistence_background())
    yield
    task.cancel()

app = FastAPI(
    title="UCAS Orchestrator",
    lifespan=lifespan
)

app.include_router(training.router)
app.include_router(management.router)
app.include_router(classification.router)
app.include_router(analytics.router)
app.include_router(rag.router)

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    
    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    
    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

@app.get("/")
async def root():
    return {
        "service": "UCAS Orchestrator",
        "version": "3.1.0",
        "features": ["persistence", "cascade", "fallback"]
    }

@app.get("/health", tags=["System"])
async def health_check(db: Session = Depends(get_db)):
    layers_health = {}
    async with httpx.AsyncClient() as client:
        for name, url_key in [("tags", 'orchestrator.layers.tags.url'), ("xgboost", 'orchestrator.layers.xgboost.url'), ("llm", 'orchestrator.layers.llm.url')]:
            url = config.get(url_key)
            if not url:
                layers_health[name] = "unreachable"
                continue
            try:
                response = await client.get(f"{url}/health", timeout=5.0)
                layers_health[name] = "healthy" if response.status_code == 200 else "error"
            except:
                layers_health[name] = "unreachable"
    
    try:
        db.execute(text("SELECT 1"))
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {"status": "healthy", "layers": layers_health, "database": db_status}