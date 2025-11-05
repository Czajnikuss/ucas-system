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

tags_metadata = [
    {
        "name": "Training",
        "description": "Create and train new categorizers"
    },
    {
        "name": "Classification",
        "description": "Classify text using trained models"
    },
    {
        "name": "Management",
        "description": "Manage categorizers and view metadata"
    },
    {
        "name": "Analytics",
        "description": "Classification history and performance metrics"
    },
    {
        "name": "RAG",
        "description": "Retrieval-augmented generation and similarity search"
    },
    {
        "name": "System",
        "description": "Health checks and system status"
    }
]

app = FastAPI(
    title="UCAS Orchestrator API",
    version="3.1.0",
    openapi_tags=tags_metadata,
    description="""
## UCAS - Universal Categorization and Analysis System

Multi-layer text classification system with cascade architecture.

### Features
* ðŸ·ï¸ **Tags Layer** - Keyword-based exact matching
* ðŸ¤– **XGBoost Layer** - Machine learning classification
* ðŸ§  **LLM Layer** - Large language model reasoning
* ðŸ‘¤ **HIL Layer** - Human-in-the-loop review
* ðŸ“Š **Quality Evaluation** - Hybrid scoring (70% metrics + 30% LLM)
* ðŸ’¾ **Persistence** - Database + file-based model storage
* ðŸ”„ **Auto-curation** - Dataset quality management

### Cascade Strategy
Classifications cascade through layers (tags â†’ xgboost â†’ llm â†’ hil) until 
confidence threshold is met. Lower layers are faster but less accurate.

### Authentication
Currently in development mode (no auth required). Production will use JWT tokens.
    """,
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "UCAS Development Team",
        "url": "https://github.com/your-org/ucas-system",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

app.include_router(training.router)
app.include_router(management.router)
app.include_router(classification.router)
app.include_router(analytics.router)
app.include_router(rag.router)

# Dodaj custom OpenAPI schema z przykÅ‚adami
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

@app.on_event("startup")
async def startup_event():
    init_db()
    
    # PERSISTENCE DISABLED FOR NOW - causing infinite loop
    pass
    print("DEBUG: Startup event started", flush=True)
    
    # Restore categorizers from disk
    print("PERSISTENCE: Restoring categorizers from disk...", flush=True)
    
    from persistence import PERSIST_DIR, load_layer_state
    from pathlib import Path
    
    print(f"PERSISTENCE: Checking {PERSIST_DIR}", flush=True)
    
    if not PERSIST_DIR.exists():
        print("PERSISTENCE: No data directory found", flush=True)
        return
    
    print(f"PERSISTENCE: Found data dir, listing contents...", flush=True)
   

    
    if not PERSIST_DIR.exists():
        print("PERSISTENCE: No data directory found", flush=True)
        return
    
    restored = 0
    for cat_dir in PERSIST_DIR.iterdir():
        if not cat_dir.is_dir():
            continue
        
        categorizer_id = cat_dir.name
        print(f"PERSISTENCE: Found categorizer {categorizer_id}", flush=True)
        
        # Check if categorizer exists in DB
        db_session = SessionLocal()
        try:
            from models.database import Categorizer
            db_cat = db_session.query(Categorizer).filter_by(categorizer_id=categorizer_id).first()
            
            if not db_cat:
                print(f"PERSISTENCE: {categorizer_id} not in DB, skipping", flush=True)
                continue
            
            # Restore layers based on config
            layers = db_cat.layers or []
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                # Restore LLM layer
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
                            print(f"PERSISTENCE: Restored LLM layer for {categorizer_id}", flush=True)
                            restored += 1
                        except Exception as e:
                            print(f"PERSISTENCE: Failed to restore LLM: {e}", flush=True)
                
                # Restore Tags layer
                if "tags" in layers:
                    tags_state = load_layer_state(categorizer_id, "tags")
                    if tags_state:
                        try:
                            response = await client.post(f"{config.get('orchestrator.layers.tags.url')}/restore", json={
                                "categorizer_id": categorizer_id,
                                "keywords": tags_state.get("keywords", {}),
                                "categories": tags_state.get("categories", [])
                            })
                            if response.status_code == 200:
                                print(f"PERSISTENCE: Restored Tags layer for {categorizer_id}", flush=True)
                                restored += 1
                        except Exception as e:
                            print(f"PERSISTENCE: Failed to restore Tags: {e}", flush=True)

                # TODO: Add XGBoost restoration

        finally:
            db_session.close()
    
    print(f"PERSISTENCE: Restored {restored} categorizers", flush=True)
    print("=" * 60, flush=True)

@app.get("/")
async def root():
    return {
        "service": "UCAS Orchestrator",
        "version": "3.0.0",
        "features": ["persistence", "cascade", "fallback"]
    }

@app.get("/health",
    summary="System health check",
    description="""
    Checks health of orchestrator and all connected layers.
    
    **Checks:**
    - Database connectivity
    - Tags layer availability
    - XGBoost layer availability
    - LLM layer availability
    
    **Status values:** `healthy`, `degraded`, `error`, `unreachable`
    """,
    response_description="System health status",
    tags=["System"]
)
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
    
    # Check database - FIX THIS
    try:
        db.execute(text("SELECT 1"))  # Need to import text
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    return {"status": "healthy", "layers": layers_health, "database": db_status}