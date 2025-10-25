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
        
        category_embeddings = np.array([s.embedding for s in category_samples if s.embedding])
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
                
                # Distance = 1 - similarity
                distance = 1.0 - sim
                if distance < radius:
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
                "options": {"num_predict": 150, "temperature": 0.3}
            }
        )
        
        if response.status_code == 200:
            result = response.json()
            llm_text = result.get("response", "").strip()
            
            # Strip markdown
            cleaned = llm_text.replace("``````", "").strip()
            
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
