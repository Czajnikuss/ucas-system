"""
Evaluator Service - Quality scoring and dataset curation
Standalone service for training data quality management
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Dict, Any, List, Optional
import uuid

from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from models.database import (
    engine, SessionLocal, get_db,
    Categorizer, TrainingSample, CurationRun
)
from quality_scorer import score_sample_quality
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
# BACKGROUND WORKER
# ============================================

async def background_scoring_worker():
    """
    Background worker that periodically scores unscored samples
    Runs every N seconds (configured in config.yaml)
    """
    global background_task_running
    
    interval = config.get('quality.background_scoring.interval_seconds', 300)
    batch_size = config.get('quality.background_scoring.batch_size', 5)
    
    print(f"🔄 Background worker started (interval: {interval}s, batch: {batch_size})", flush=True)
    
    while background_task_running:
        try:
            db = SessionLocal()
            
            # Get all categorizers
            categorizers = db.query(Categorizer).all()
            
            for categorizer in categorizers:
                try:
                    # Get unscored samples
                    unscored_samples = (
                        db.query(TrainingSample)
                        .filter(
                            TrainingSample.categorizer_id == categorizer.id,
                            TrainingSample.is_active == True,
                            TrainingSample.quality_score == None,
                            TrainingSample.embedding != None
                        )
                        .limit(batch_size)
                        .all()
                    )
                    
                    if unscored_samples:
                        print(f"📊 Scoring {len(unscored_samples)} samples for {categorizer.categorizer_id}", flush=True)
                        
                        for sample in unscored_samples:
                            try:
                                # Score sample
                                result = await score_sample_quality(sample, categorizer, db)
                                
                                # Update sample
                                sample.quality_score = result.get('score', 0.5)
                                sample.quality_scored_at = datetime.utcnow()
                                sample.quality_reasoning = result.get('reasoning', '')
                                sample.quality_metrics = result.get('metrics', {})
                                
                                db.commit()
                                print(f"  ✓ Sample {sample.id}: score={sample.quality_score:.3f}", flush=True)
                                
                            except Exception as e:
                                print(f"  ✗ Error scoring sample {sample.id}: {e}", flush=True)
                                db.rollback()
                        
                        # Check if curation is needed
                        await check_curation_trigger(categorizer.id, db)
                        
                except Exception as e:
                    print(f"✗ Error processing categorizer {categorizer.categorizer_id}: {e}", flush=True)
                    db.rollback()
            
            db.close()
            
        except Exception as e:
            print(f"✗ Background worker error: {e}", flush=True)
        
        # Wait for next interval
        await asyncio.sleep(interval)
    
    print("🛑 Background worker stopped", flush=True)


# ============================================
# HELPER FUNCTIONS
# ============================================

async def check_curation_trigger(categorizer_id: uuid.UUID, db: Session) -> bool:
    """
    Check if curation should be triggered based on unscored sample count
    Returns True if curation was triggered
    """
    threshold = config.get('quality.curation.trigger_threshold', 50)
    
    # Count unscored samples using DB function
    query = text("SELECT count_unscored_samples(:cat_id)")
    unscored_count = db.execute(query, {"cat_id": str(categorizer_id)}).scalar()
    
    if unscored_count >= threshold:
        print(f"🔔 Curation trigger: {unscored_count} unscored samples (threshold: {threshold})", flush=True)
        await run_curation_pipeline(categorizer_id, db)
        return True
    
    return False


async def run_curation_pipeline(categorizer_id: uuid.UUID, db: Session):
    """
    Run full curation pipeline:
    1. Archive low-quality samples (score < min threshold)
    2. Keep top N samples by quality
    3. Record curation run stats
    """
    start_time = datetime.utcnow()
    
    categorizer = db.query(Categorizer).filter(Categorizer.id == categorizer_id).first()
    if not categorizer:
        print(f"✗ Categorizer {categorizer_id} not found", flush=True)
        return
    
    print(f"🔧 Starting curation for {categorizer.categorizer_id}", flush=True)
    
    # Stats before
    total_before = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True
    ).count()
    
    avg_quality_before_result = db.query(
        text("AVG(quality_score)")
    ).select_from(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True,
        TrainingSample.quality_score != None
    ).scalar()
    avg_quality_before = float(avg_quality_before_result) if avg_quality_before_result else 0.0
    
    # 1. Archive samples below min quality threshold
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
    print(f"  ✓ Archived {len(low_quality_samples)} low-quality samples (< {min_quality})", flush=True)
    
    # 2. Keep top N samples by quality
    max_dataset_size = config.get('quality.curation.dataset_max_size', 800)
    
    active_samples = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True,
        TrainingSample.quality_score != None
    ).order_by(TrainingSample.quality_score.desc()).all()
    
    if len(active_samples) > max_dataset_size:
        # Archive excess (lowest quality)
        to_archive = active_samples[max_dataset_size:]
        for sample in to_archive:
            sample.is_active = False
            sample.archived_at = datetime.utcnow()
            sample.archive_reason = "exceeded_max_dataset_size"
        
        db.commit()
        print(f"  ✓ Archived {len(to_archive)} excess samples (keeping top {max_dataset_size})", flush=True)
    
    # Stats after
    total_after = db.query(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True
    ).count()
    
    avg_quality_after_result = db.query(
        text("AVG(quality_score)")
    ).select_from(TrainingSample).filter(
        TrainingSample.categorizer_id == categorizer_id,
        TrainingSample.is_active == True,
        TrainingSample.quality_score != None
    ).scalar()
    avg_quality_after = float(avg_quality_after_result) if avg_quality_after_result else 0.0
    
    # Get iteration number
    query_iter = text("SELECT get_curation_iteration(:cat_id)")
    iteration_number = db.execute(query_iter, {"cat_id": str(categorizer_id)}).scalar()
    
    # Record curation run
    curation_run = CurationRun(
        categorizer_id=categorizer_id,
        run_at=start_time,
        trigger_reason="threshold_met",
        iteration_number=iteration_number,
        total_samples_before=total_before,
        total_samples_after=total_after,
        archived_count=(total_before - total_after),
        removed_low_quality_count=len(low_quality_samples),
        avg_quality_before=avg_quality_before,
        avg_quality_after=avg_quality_after,
        config={
            "min_quality_score": min_quality,
            "dataset_max_size": max_dataset_size,
            "trigger_threshold": config.get('quality.curation.trigger_threshold', 50)
        },
        triggered_reevaluation=False,
        processing_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000)
    )
    
    db.add(curation_run)
    db.commit()
    
    print(f"  ✓ Curation complete: {total_before} → {total_after} samples", flush=True)
    print(f"  ✓ Quality: {avg_quality_before:.3f} → {avg_quality_after:.3f}", flush=True)
    print(f"  ✓ Iteration: {iteration_number}", flush=True)


# ============================================
# FASTAPI APP
# ============================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager - start/stop background worker
    """
    global background_task, background_task_running
    
    # Startup
    print("🚀 Evaluator service starting...", flush=True)
    
    if config.get('quality.background_scoring.enabled', True):
        background_task_running = True
        background_task = asyncio.create_task(background_scoring_worker())
        print("✓ Background worker enabled", flush=True)
    else:
        print("⚠️ Background worker disabled in config", flush=True)
    
    yield
    
    # Shutdown
    print("🛑 Evaluator service shutting down...", flush=True)
    
    if background_task:
        background_task_running = False
        background_task.cancel()
        try:
            await background_task
        except asyncio.CancelledError:
            pass
    
    print("✓ Shutdown complete", flush=True)


app = FastAPI(
    title="UCAS Evaluator Service",
    version="1.0.0",
    lifespan=lifespan
)


# ============================================
# API ENDPOINTS
# ============================================

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "evaluator",
        "background_worker": "running" if background_task_running else "stopped"
    }


@app.post("/score_sample")
async def score_sample_endpoint(request: ScoreSampleRequest, db: Session = Depends(get_db)):
    """
    Score a single sample manually (bypasses background worker)
    """
    try:
        # Get sample and categorizer
        sample = db.query(TrainingSample).filter(
            TrainingSample.id == uuid.UUID(request.sample_id)
        ).first()
        
        if not sample:
            raise HTTPException(status_code=404, detail="Sample not found")
        
        categorizer = db.query(Categorizer).filter(
            Categorizer.id == uuid.UUID(request.categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        # Score sample
        result = await score_sample_quality(sample, categorizer, db)
        
        # Update sample
        sample.quality_score = result.get('score', 0.5)
        sample.quality_scored_at = datetime.utcnow()
        sample.quality_reasoning = result.get('reasoning', '')
        sample.quality_metrics = result.get('metrics', {})
        
        db.commit()
        
        return {
            "status": "scored",
            "sample_id": str(sample.id),
            "score": sample.quality_score,
            "reasoning": sample.quality_reasoning,
            "metrics": sample.quality_metrics
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/score_batch")
async def score_batch_endpoint(request: ScoreBatchRequest, db: Session = Depends(get_db)):
    """
    Score a batch of unscored samples for a categorizer
    """
    try:
        categorizer = db.query(Categorizer).filter(
            Categorizer.id == uuid.UUID(request.categorizer_id)
        ).first()
        
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        batch_size = request.batch_size or config.get('quality.background_scoring.batch_size', 5)
        
        # Get unscored samples
        unscored_samples = (
            db.query(TrainingSample)
            .filter(
                TrainingSample.categorizer_id == categorizer.id,
                TrainingSample.is_active == True,
                TrainingSample.quality_score == None,
                TrainingSample.embedding != None
            )
            .limit(batch_size)
            .all()
        )
        
        results = []
        for sample in unscored_samples:
            try:
                result = await score_sample_quality(sample, categorizer, db)
                
                sample.quality_score = result.get('score', 0.5)
                sample.quality_scored_at = datetime.utcnow()
                sample.quality_reasoning = result.get('reasoning', '')
                sample.quality_metrics = result.get('metrics', {})
                
                db.commit()
                
                results.append({
                    "sample_id": str(sample.id),
                    "score": sample.quality_score
                })
                
            except Exception as e:
                print(f"✗ Error scoring sample {sample.id}: {e}", flush=True)
                db.rollback()
        
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
    """
    Get curation status for a categorizer
    """
    try:
        cat_uuid = uuid.UUID(categorizer_id)
        
        # Use DB function
        query_unscored = text("SELECT count_unscored_samples(:cat_id)")
        unscored_count = db.execute(query_unscored, {"cat_id": str(cat_uuid)}).scalar()
        
        # Total active samples
        total_active = db.query(TrainingSample).filter(
            TrainingSample.categorizer_id == cat_uuid,
            TrainingSample.is_active == True
        ).count()
        
        # Avg quality
        avg_quality_result = db.query(
            text("AVG(quality_score)")
        ).select_from(TrainingSample).filter(
            TrainingSample.categorizer_id == cat_uuid,
            TrainingSample.is_active == True,
            TrainingSample.quality_score != None
        ).scalar()
        avg_quality = float(avg_quality_result) if avg_quality_result else None
        
        threshold = config.get('quality.curation.trigger_threshold', 50)
        needs_curation = unscored_count >= threshold
        
        return CurationStatusResponse(
            categorizer_id=categorizer_id,
            unscored_count=unscored_count,
            needs_curation=needs_curation,
            total_active_samples=total_active,
            avg_quality_score=avg_quality
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/run_curation")
async def run_curation_endpoint(request: RunCurationRequest, db: Session = Depends(get_db)):
    """
    Manually trigger curation for a categorizer
    """
    try:
        cat_uuid = uuid.UUID(request.categorizer_id)
        
        categorizer = db.query(Categorizer).filter(Categorizer.id == cat_uuid).first()
        if not categorizer:
            raise HTTPException(status_code=404, detail="Categorizer not found")
        
        await run_curation_pipeline(cat_uuid, db)
        
        return {
            "status": "curation_complete",
            "categorizer_id": str(cat_uuid)
        }
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
