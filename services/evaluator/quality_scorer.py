import json
import numpy as np
import httpx
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity
# TrainingSample accessed via db.query
# Config loaded inline
import numpy as np
import httpx
from sklearn.metrics.pairwise import cosine_similarity
from datetime import datetime

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

# Programmatic Metrics Calculator
class MetricsCalculator:
    def __init__(self, config):
        self.config = config
    
    def calculate_alignment(self, sample_embedding, category_samples):
        """Embedding similarity to category centroid"""
        if not category_samples:
            return 0.5
        
        category_embeddings = np.array([s.embedding for s in category_samples if s.embedding is not None])
        if len(category_embeddings) == 0:
            return 0.5
            
        centroid = np.mean(category_embeddings, axis=0)
        similarity = cosine_similarity(
            sample_embedding.reshape(1, -1),
            centroid.reshape(1, -1)
        )[0][0]
        
        # Normalize to 0-1
        return float((similarity + 1) / 2)
    
    def calculate_informativeness(self, text):
        """Length + word diversity score"""
        words = text.split()
        word_count = len(words)
        unique_words = len(set(words))
        
        # Length factor (normalize to 200 words)
        length_factor = min(word_count / 200, 1.0)
        
        # Diversity factor
        diversity_factor = unique_words / word_count if word_count > 0 else 0
        
        return float(0.7 * length_factor + 0.3 * diversity_factor)
    
    def calculate_uniqueness(self, sample_embedding, nearest_samples):
        """Inverse of avg similarity to nearest neighbors"""
        if not nearest_samples or len(nearest_samples) == 0:
            return 0.8  # Default high if no comparison
        
        similarities = []
        for neighbor in nearest_samples:
            if neighbor.embedding is not None:
                sim = cosine_similarity(
                    sample_embedding.reshape(1, -1),
                    neighbor.embedding.reshape(1, -1)
                )[0][0]
                similarities.append(sim)
        
        if not similarities:
            return 0.8
            
        avg_sim = np.mean(similarities)
        # Convert to uniqueness: high similarity = low uniqueness
        uniqueness = 1.0 - ((avg_sim + 1) / 2)
        return float(max(0, uniqueness))
    
    def calculate_density(self, sample_embedding, all_samples, radius=0.3):
        """Samples within radius / total samples"""
        if not all_samples or len(all_samples) < 2:
            return 0.5
        
        count_in_radius = 0
        for other in all_samples:
            if other.embedding is not None:
                sim = cosine_similarity(
                    sample_embedding.reshape(1, -1),
                    other.embedding.reshape(1, -1)
                )[0][0]
                
                # Similarity directly indicates closeness (higher = closer)
                # Count samples with high similarity (> threshold)
                if sim > (1.0 - radius):  # If sim > 0.7, distance < 0.3
                    count_in_radius += 1
        
        density = count_in_radius / len(all_samples)
        return float(min(density, 1.0))

# Simplified LLM Scorer
async def score_sample_llm(sample, context):
    """Get qualitative LLM score only"""
    prompt = f"""
Rate this training sample's value (0.0-1.0):

Text: "{sample.text}"
Category: {sample.category}
Assigned Label: {sample.category}

Consider:
- Is the text clear and well-written?
- Does it represent the category well?
- Would it help train a classifier?

Return ONLY this JSON (no markdown, no extra text):
{{"score": 0.85, "reasoning": "Clear example"}}
"""
    
    try:
        response = await httpx.AsyncClient(timeout=60).post(
            f"http://ollama:11434/api/generate",
            json={
                "model": "phi3:mini",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 300, "temperature": 0.3}
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            llm_text = result.get("response", "").strip()
            
            # Strip markdown
            cleaned = llm_text.replace("``````", "").strip()
            # Try to extract just JSON object if text continues after
            if "{" in cleaned and "}" in cleaned:
                start = cleaned.find("{")
                end = cleaned.rfind("}") + 1
                cleaned = cleaned[start:end]
            
            try:
                score_data = json.loads(cleaned)
                return score_data.get("score", 0.5), score_data.get("reasoning", "")
            except json.JSONDecodeError:
                print(f"⚠️ JSON parse failed: {cleaned[:100]}")
                return 0.5, "LLM response parsing failed"
                
    except Exception as e:
        print(f"❌ LLM scoring error: {e}")
        return 0.5, f"Exception: {str(e)}"

# Main Hybrid Scorer
async def score_sample_hybrid(sample, context_samples, config):
    """Combine programmatic metrics + LLM judgment"""
    
    # 1. Calculate programmatic metrics
    calc = MetricsCalculator(config)
    
    category_samples = [s for s in context_samples if s.category == sample.category]
    
    metrics = {
        "alignment": calc.calculate_alignment(sample.embedding, category_samples),
        "informativeness": calc.calculate_informativeness(sample.text),
        "uniqueness": calc.calculate_uniqueness(sample.embedding, context_samples[:6]),
        "density": calc.calculate_density(sample.embedding, context_samples, radius=0.3)
    }
    
    # 2. Get LLM qualitative score
    llm_score, llm_reasoning = await score_sample_llm(sample, context_samples)
    
    # 3. Weighted combine
    weights = config["quality"]["weights"]
    programmatic_score = (
        metrics["alignment"] * weights["alignment"] +
        metrics["informativeness"] * weights["informativeness"] +
        metrics["uniqueness"] * weights["uniqueness"] +
        metrics["density"] * weights["density"]
    )
    
    # Final: 70% metrics + 30% LLM
    final_score = 0.7 * programmatic_score + 0.3 * llm_score
    
    # Enhanced reasoning
    reasoning = f"LLM: {llm_reasoning} | Metrics: A={metrics['alignment']:.2f} I={metrics['informativeness']:.2f} U={metrics['uniqueness']:.2f} D={metrics['density']:.2f}"
    
    return final_score, reasoning, metrics


# Integration with existing DB update function
async def score_and_update_sample(sample, all_samples, config, db_session):
    '''Score sample using hybrid approach and update DB'''
    try:
        # Get context samples
        context = [s for s in all_samples if s.id != sample.id][:50]
        
        # Hybrid scoring
        final_score, reasoning, metrics = await score_sample_hybrid(
            sample, context, config
        )
        
        # Update database
        sample.quality_score = final_score
        sample.quality_reasoning = reasoning
        sample.quality_metrics = metrics
        sample.quality_scored_at = datetime.utcnow()
        
        db_session.commit()
        
        print(f"  ✓ Sample {sample.id}: score={final_score:.3f}")
        return True
        
    except Exception as e:
        print(f"  ✗ Error scoring {sample.id}: {e}")
        sample.quality_score = 0.5
        sample.quality_reasoning = f"Error: {str(e)}"
        db_session.commit()
        return False
# === Compatibility wrapper for main.py ===
async def score_sample_quality(sample, categorizer, db):
    """Standalone wrapper - queries DB + embeddings service directly"""
    
    try:
        # 1. Get sample embeddings via embeddings service
        async with httpx.AsyncClient(timeout=10.0) as emb_client:
            # Get embedding for current sample if missing
            sample_emb = sample.embedding
            if sample_emb is None or (isinstance(sample_emb, str) and sample_emb):
                emb_response = await emb_client.post(
                    "http://ucas-embeddings:8050/embed",
                    json={"texts": [sample.text], "normalize": True}
                )
                if emb_response.status_code == 200:
                    emb_data = emb_response.json()
                    sample_emb = np.array(emb_data["embeddings"][0])
            elif isinstance(sample_emb, str):
                # Deserialize from JSON string
                sample_emb = np.array(json.loads(sample_emb))
            elif not isinstance(sample_emb, np.ndarray):
                sample_emb = np.array(sample_emb)
        
        # 2. Query DB for similar samples (raw SQL - no ORM dependency)
        from sqlalchemy import text
        query = text("""
            SELECT id, text, category, embedding
            FROM training_samples
            WHERE categorizer_id = :cat_id
              AND embedding IS NOT NULL
              AND id != :sample_id
              AND is_active = true
            LIMIT 50
        """)
        
        result = db.execute(query, {
            "cat_id": str(categorizer.id),
            "sample_id": str(sample.id)
        })
        
        # 3. Build context samples with deserialized embeddings
        class SampleProxy:
            def __init__(self, row):
                self.id = row[0]
                self.text = row[1]
                self.category = row[2]
                # Deserialize embedding from JSONB string
                emb_raw = row[3]
                if isinstance(emb_raw, str):
                    self.embedding = np.array(json.loads(emb_raw))
                elif emb_raw:
                    self.embedding = np.array(emb_raw)
                else:
                    self.embedding = None
        
        context_samples = [SampleProxy(row) for row in result.fetchall()]
        
        # 4. Load config
        import yaml
        with open('/app/config/config.yaml') as f:
            config = yaml.safe_load(f)
        
        # 5. Create sample proxy with embedding
        class CurrentSampleProxy:
            def __init__(self, sample, embedding):
                self.id = sample.id
                self.text = sample.text
                self.category = sample.category
                self.embedding = embedding
        
        sample_proxy = CurrentSampleProxy(sample, sample_emb)
        
        # 6. Call hybrid scorer
        final_score, reasoning, metrics = await score_sample_hybrid(
            sample_proxy, context_samples, config
        )
        
        return {
            "score": final_score,
            "reasoning": reasoning,
            "metrics": metrics
        }
        
    except Exception as e:
        import traceback
        print(f"❌ Error in score_sample_quality: {e}")
        traceback.print_exc()
        return {
            "score": 0.5,
            "reasoning": f"Error: {str(e)}",
            "metrics": {}
        }