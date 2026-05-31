# -*- coding: utf-8 -*-
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid
import httpx

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text, func
from sqlalchemy.orm import Session

from models.database import (
    engine, SessionLocal, get_db,
    Categorizer, TrainingSample, CurationRun
)
from quality_scorer import score_sample_quality, Sample as QualitySample
from config_loader import config

# ============================================
# GLOBAL STATE
# ============================================

background_task = None
background_task_running = False

# ============================================
# PYDANTIC MODELS
# ============================================

class ScoreSampleRequest(BaseModel):
    sample_id: str
    categorizer_id: str

class ScoreBatchRequest(BaseModel):
    categorizer_id: str
    batch_size: Optional[int] = None

class ScoreSpecificRequest(BaseModel):
    categorizer_id: str
    sample_ids: List[str]

class ResetScoresRequest(BaseModel):
    categorizer_id: str

class CurationStatusResponse(BaseModel):
    categorizer_id: str
    unscored_count: int
    needs_curation: bool
    total_active_samples: int
    avg_quality_score: Optional[float]

class RunCurationRequest(BaseModel):
    categorizer_id: str
    force: bool = False

# ============================================
# CORE LOGIC
# ============================================

async def get_remote_embeddings_batch(texts: List[str]) -> List[List[float]]:
    """Pobiera wektory hurtowo, z paginacją po 100 sztuk by nie łamać limitów API."""
    if not texts:
        return []
        
    chunk_size = 100
    all_embeddings = []
    
    async with httpx.AsyncClient() as client:
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i:i + chunk_size]
            try:
                resp = await client.post("http://embeddings-service:8050/embed", json={"texts": chunk}, timeout=60.0)
                if resp.status_code == 200:
                    data = resp.json()
                    if "embeddings" in data:
                        all_embeddings.extend(data["embeddings"])
                    else:
                        all_embeddings.extend([[0.0] * 384 for _ in chunk])
                else:
                    print(f"🔴 Błąd Embeddings API [{resp.status_code}]: {resp.text}", flush=True)
                    all_embeddings.extend([[0.0] * 384 for _ in chunk])
            except Exception as e:
                print(f"🔴 Błąd połączenia z Embeddings: {e}", flush=True)
                all_embeddings.extend([[0.0] * 384 for _ in chunk])
                
    return all_embeddings

async def check_curation_trigger(categorizer_id: uuid.UUID, db: Session) -> bool:
    threshold = config.get('quality.curation.trigger_threshold', 50)
    
    unscored_count = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True,
        TrainingSample.quality_score == None
    ).count()
    
    if unscored_count >= threshold:
        print(f"🔔 Curation trigger: {unscored_count} unscored samples", flush=True)
        await run_curation_pipeline(categorizer_id, db)
        return True
    
    return False

async def run_curation_pipeline(categorizer_id: uuid.UUID, db: Session):
    start_time = datetime.utcnow()
    
    categorizer = db.query(Categorizer).filter(Categorizer.id == categorizer_id).first()
    if not categorizer:
        return
    
    min_quality = config.get('quality.curation.min_quality_score', 0.1)
    
    low_quality_samples = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True,
        TrainingSample.quality_score != None,
        TrainingSample.quality_score < min_quality
    ).all()
    
    for sample in low_quality_samples:
        sample.is_active = False
        sample.archived_at = datetime.utcnow()
        sample.archive_reason = f"low_quality_score_{sample.quality_score:.3f}"
    
    db.commit()
    print(f"  ✓ Archived {len(low_quality_samples)} low-quality samples", flush=True)

async def build_historical_context(categorizer_id: uuid.UUID, db: Session) -> List[QualitySample]:
    bg_samples_db = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True
    ).limit(1000).all()
    
    if not bg_samples_db:
        return []
        
    texts_to_embed = [bg.text for bg in bg_samples_db]
    embeddings_matrix = await get_remote_embeddings_batch(texts_to_embed)
    
    hist_samples = []
    for bg, emb in zip(bg_samples_db, embeddings_matrix):
        hist_samples.append(QualitySample(text=bg.text, category=bg.category, embedding=emb))
        
    return hist_samples

# ============================================
# BACKGROUND WORKER
# ============================================

async def background_scoring_worker():
    global background_task_running
    
    interval = config.get('quality.background_scoring.interval_seconds', 300)
    batch_size = config.get('quality.background_scoring.batch_size', 5)
    
    while background_task_running:
        db = SessionLocal()
        try:
            categorizers = db.query(Categorizer).all()
            
            for categorizer in categorizers:
                try:
                    unscored_samples = (
                        db.query(TrainingSample)
                        .filter(
                            TrainingSample.categorizer_id == categorizer.id,
                            TrainingSample.is_active == True,
                            TrainingSample.quality_score == None
                        )
                        .limit(batch_size)
                        .all()
                    )
                    
                    if unscored_samples:
                        print(f"📊 Scoring {len(unscored_samples)} samples for {categorizer.categorizer_id}", flush=True)
                        
                        hist_samples = await build_historical_context(categorizer.id, db)
                        
                        unscored_texts = [s.text for s in unscored_samples]
                        unscored_embs = await get_remote_embeddings_batch(unscored_texts)
                        
                        for db_sample, emb in zip(unscored_samples, unscored_embs):
                            new_sample = QualitySample(text=db_sample.text, category=db_sample.category, embedding=emb)
                            
                            try:
                                score = score_sample_quality(new_sample, hist_samples)
                                reason = f"Zgodność etykiet k-NN: {score:.2f}"
                            except Exception as e:
                                score = min(0.99, len(db_sample.text) / 250.0 + 0.15)
                                reason = f"Ocena heurystyczna (błąd algorytmu): {score:.2f}"
                            
                            db_sample.quality_score = float(score)
                            db_sample.quality_scored_at = datetime.utcnow()
                            db_sample.quality_reasoning = reason
                            
                        db.commit()
                        await check_curation_trigger(categorizer.id, db)
                        
                except Exception as e:
                    db.rollback()
        except Exception:
            # Blad na poziomie cyklu (np. chwilowa utrata polaczenia) — sesja zamknieta w finally
            pass
        finally:
            db.close()

        await asyncio.sleep(interval)

# ============================================
# FASTAPI APP
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global background_task, background_task_running
    print("🚀 Evaluator service starting...", flush=True)
    
    if config.get('quality.background_scoring.enabled', True):
        background_task_running = True
        background_task = asyncio.create_task(background_scoring_worker())
        print("✓ Background worker enabled", flush=True)
    
    yield
    
    if background_task:
        background_task_running = False
        background_task.cancel()

app = FastAPI(title="UCAS Evaluator Service", version="1.0.8", lifespan=lifespan)

# ============================================
# API ENDPOINTS
# ============================================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "worker": "running" if background_task_running else "stopped"}

@app.post("/reset_scores")
async def reset_scores_endpoint(request: ResetScoresRequest, db: Session = Depends(get_db)):
    try:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == request.categorizer_id) |
            (Categorizer.name == request.categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
            
        db.query(TrainingSample).filter(
            TrainingSample.categorizer_id == categorizer.id
        ).update({
            "quality_score": None,
            "quality_scored_at": None,
            "quality_reasoning": None
        }, synchronize_session=False)
        
        db.commit()
        return {"status": "success", "message": "Oceny wyzerowane"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/score_specific")
async def score_specific_endpoint(request: ScoreSpecificRequest, db: Session = Depends(get_db)):
    try:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == request.categorizer_id) |
            (Categorizer.name == request.categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
            
        try:
            sample_uuids = [uuid.UUID(s_id) for s_id in request.sample_ids]
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid UUID format")

        samples_to_score = db.query(TrainingSample).filter(
            TrainingSample.categorizer_id == categorizer.id,
            TrainingSample.id.in_(sample_uuids)
        ).all()

        if not samples_to_score:
            return {"status": "success", "scored_count": 0, "results": []}

        hist_samples = await build_historical_context(categorizer.id, db)
        
        texts_to_embed = [s.text for s in samples_to_score]
        embs = await get_remote_embeddings_batch(texts_to_embed)

        results = []
        for db_sample, emb in zip(samples_to_score, embs):
            new_sample = QualitySample(text=db_sample.text, category=db_sample.category, embedding=emb)
            try:
                score = score_sample_quality(new_sample, hist_samples)
                reason = f"Wymuszona ocena selektywna: {score:.2f}"
            except Exception as e:
                score = min(0.99, len(db_sample.text) / 250.0 + 0.15)
                reason = f"Heurystyka awaryjna: {score:.2f}"
                
            db_sample.quality_score = float(score)
            db_sample.quality_scored_at = datetime.utcnow()
            db_sample.quality_reasoning = reason
            results.append({"sample_id": str(db_sample.id), "score": score})

        db.commit()
        return {"status": "success", "scored_count": len(results), "results": results}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/score_batch")
async def score_batch_endpoint(request: ScoreBatchRequest, db: Session = Depends(get_db)):
    try:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == request.categorizer_id) |
            (Categorizer.name == request.categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        batch_size = request.batch_size or 10
        
        unscored_samples = (
            db.query(TrainingSample)
            .filter(
                TrainingSample.categorizer_id == categorizer.id,
                TrainingSample.is_active == True,
                TrainingSample.quality_score == None
            )
            .limit(batch_size)
            .all()
        )
        
        if not unscored_samples:
            return {"status": "batch_scored", "categorizer_id": str(categorizer.id), "scored_count": 0, "results": []}

        hist_samples = await build_historical_context(categorizer.id, db)
        
        unscored_texts = [s.text for s in unscored_samples]
        embs = await get_remote_embeddings_batch(unscored_texts)
        
        results = []
        for db_sample, emb in zip(unscored_samples, embs):
            new_sample = QualitySample(text=db_sample.text, category=db_sample.category, embedding=emb)
            
            try:
                score = score_sample_quality(new_sample, hist_samples)
                reason = f"Zgodność etykiet k-NN (hurtowo): {score:.2f}"
            except Exception as e:
                score = min(0.99, len(db_sample.text) / 250.0 + 0.15)
                reason = f"Heurystyka awaryjna: {score:.2f}"
                
            db_sample.quality_score = float(score)
            db_sample.quality_scored_at = datetime.utcnow()
            db_sample.quality_reasoning = reason
            results.append({"sample_id": str(db_sample.id), "score": score})
            
        db.commit()
        return {
            "status": "batch_scored",
            "categorizer_id": str(categorizer.id),
            "scored_count": len(results),
            "results": results
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/curation_status/{categorizer_id}")
async def get_curation_status(categorizer_id: str, db: Session = Depends(get_db)):
    try:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == categorizer_id) |
            (Categorizer.name == categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
            
        cat_uuid = categorizer.id
        
        unscored_count = db.query(TrainingSample).filter(
            TrainingSample.categorizer_id == cat_uuid,
            TrainingSample.is_active == True,
            TrainingSample.quality_score == None
        ).count()
        
        total_active = db.query(TrainingSample).filter(
            TrainingSample.categorizer_id == cat_uuid,
            TrainingSample.is_active == True
        ).count()
        
        avg_quality_result = db.query(func.avg(TrainingSample.quality_score)).filter(
            TrainingSample.categorizer_id == cat_uuid,
            TrainingSample.is_active == True,
            TrainingSample.quality_score != None
        ).scalar()
        avg_quality = float(avg_quality_result) if avg_quality_result else None
        
        return CurationStatusResponse(
            categorizer_id=categorizer_id,
            unscored_count=unscored_count,
            needs_curation=(unscored_count >= config.get('quality.curation.trigger_threshold', 50)),
            total_active_samples=total_active,
            avg_quality_score=avg_quality
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/run_curation")
async def run_curation_endpoint(request: RunCurationRequest, db: Session = Depends(get_db)):
    try:
        categorizer = db.query(Categorizer).filter(
            (Categorizer.categorizer_id == request.categorizer_id) |
            (Categorizer.name == request.categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        await run_curation_pipeline(categorizer.id, db)
        return {"status": "curation_complete"}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))