# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from collections import Counter
import numpy as np
from unidecode import unidecode

app = FastAPI(
    title="UCAS Tags Layer",
    version="3.0.0",
    description="Multi-language keyword-based categorization (Polish optimized)"
)

# Polish stopwords
POLISH_STOPWORDS = set([
    'i', 'w', 'na', 'z', 'do', 'o', 'a', 'że', 'się', 'nie', 'jest', 'was', 'być',
    'to', 'ja', 'he', 'jak', 'dla', 'po', 'ale', 'od', 'za', 'przez', 'przy',
    'lub', 'oraz', 'tylko', 'może', 'gdzie', 'kiedy', 'który', 'ta', 'ten', 'tego',
    'bardzo', 'może', 'mnie', 'mi', 'sobie', 'tym', 'też', 'już', 'co', 'czy'
])

# Storage
categorizer_keywords: Dict[str, Dict[str, List[str]]] = {}
categorizer_stats: Dict[str, Dict] = {}
categorizer_configs: Dict[str, Dict] = {}

class TrainRequest(BaseModel):
    categorizer_id: str
    training_data: List[Dict[str, str]]
    max_keywords: int = 10
    min_keyword_length: int = 3
    normalize_text: bool = True  # Convert ą→a, ł→l for better matching
    use_polish_stopwords: bool = True

class ClassifyRequest(BaseModel):
    categorizer_id: str
    text: str

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    matched_keywords: List[str] = []
    original_keywords: List[str] = []  # Before normalization
    all_matches: Dict[str, List[str]] = {}
    method: str = "tags"

def normalize_polish_text(text: str, should_normalize: bool = True) -> str:
    """
    Normalize Polish text for better matching
    ą→a, ę→e, ć→c, ł→l, ń→n, ó→o, ś→s, ź/ż→z
    """
    if not should_normalize:
        return text
    return unidecode(text)

def tokenize_text(text: str, min_length: int = 3) -> List[str]:
    """Tokenize supporting Polish characters"""
    # Pattern includes Polish diacritics
    words = re.findall(r'\b[\w]+\b', text.lower(), re.UNICODE)
    return [w for w in words if len(w) >= min_length]

@app.get("/")
async def root():
    return {
        "service": "UCAS Tags Layer",
        "status": "running",
        "version": "3.0.0",
        "features": ["polish_stopwords", "text_normalization", "utf8_support"],
        "trained_categorizers": len(categorizer_keywords)
    }

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "trained_categorizers": len(categorizer_keywords),
        "polish_support": True
    }

def calculate_discriminative_score(word, category_freq, all_category_freqs):
    """Calculate category uniqueness score"""
    total_freq = sum(all_category_freqs.values())
    if total_freq == 0:
        return 0
    
    category_ratio = category_freq / total_freq
    num_categories_with_word = sum(1 for freq in all_category_freqs.values() if freq > 0)
    diversity_penalty = 1.0 / num_categories_with_word
    
    return category_ratio * diversity_penalty

@app.post("/train")
async def train(request: TrainRequest):
    """
    Train with full Polish language support
    """
    try:
        # Store config
        categorizer_configs[request.categorizer_id] = {
            "normalize_text": request.normalize_text,
            "use_polish_stopwords": request.use_polish_stopwords,
            "max_keywords": request.max_keywords
        }
        
        # Normalize texts
        texts = [sample["text"] for sample in request.training_data]
        categories = [sample["category"] for sample in request.training_data]
        
        if request.normalize_text:
            texts_normalized = [normalize_polish_text(t) for t in texts]
        else:
            texts_normalized = texts
        
        unique_categories = list(set(categories))
        
        # Word frequency analysis
        global_word_freq = Counter()
        category_word_freq = {cat: Counter() for cat in unique_categories}
        
        for text_norm, category in zip(texts_normalized, categories):
            words = tokenize_text(text_norm, request.min_keyword_length)
            
            # Filter stopwords
            if request.use_polish_stopwords:
                words = [w for w in words if w not in POLISH_STOPWORDS]
            
            global_word_freq.update(words)
            category_word_freq[category].update(words)
        
        keywords_by_category = {}
        
        for category in unique_categories:
            category_texts = [t for t, c in zip(texts_normalized, categories) if c == category]
            
            if len(category_texts) < 1:
                continue
            
            try:
                # Custom stopwords
                stopwords_to_use = list(POLISH_STOPWORDS) if request.use_polish_stopwords else None
                
                vectorizer = TfidfVectorizer(
                    max_features=request.max_keywords * 3,
                    ngram_range=(1, 2),
                    stop_words=stopwords_to_use,
                    lowercase=True,
                    min_df=1,
                    token_pattern=r'\b[\w]+\b'  # Support Unicode
                )
                
                tfidf_matrix = vectorizer.fit_transform(category_texts)
                feature_names = vectorizer.get_feature_names_out()
                avg_tfidf = np.mean(tfidf_matrix.toarray(), axis=0)
                
                word_scores = {}
                for word, tfidf_score in zip(feature_names, avg_tfidf):
                    word_freq = category_word_freq[category][word]
                    
                    all_freqs = {cat: category_word_freq[cat][word] for cat in unique_categories}
                    discriminative = calculate_discriminative_score(word, word_freq, all_freqs)
                    
                    freq_score = word_freq / max(global_word_freq.values())
                    
                    combined_score = (
                        tfidf_score * 0.5 +
                        discriminative * 0.3 +
                        freq_score * 0.2
                    )
                    
                    word_scores[word] = {
                        'combined': combined_score,
                        'tfidf': tfidf_score,
                        'discriminative': discriminative,
                        'frequency': word_freq
                    }
                
                sorted_words = sorted(word_scores.items(), key=lambda x: x[1]['combined'], reverse=True)
                top_keywords = [word for word, scores in sorted_words[:request.max_keywords]]
                keywords_by_category[category] = top_keywords
                
                if request.categorizer_id not in categorizer_stats:
                    categorizer_stats[request.categorizer_id] = {}
                
                categorizer_stats[request.categorizer_id][category] = {
                    'samples': len(category_texts),
                    'keyword_scores': {k: v for k, v in sorted_words[:request.max_keywords]}
                }
                
            except Exception as e:
                word_freq = category_word_freq[category]
                top_keywords = [word for word, freq in word_freq.most_common(request.max_keywords)]
                keywords_by_category[category] = top_keywords
        
        categorizer_keywords[request.categorizer_id] = keywords_by_category
        
        return {
            "status": "trained",
            "categorizer_id": request.categorizer_id,
            "categories": list(keywords_by_category.keys()),
            "keywords": keywords_by_category,
            "training_samples": len(texts),
            "config": {
                "normalized": request.normalize_text,
                "polish_stopwords": request.use_polish_stopwords
            },
            "extraction_method": "multi-metric with Polish support"
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    """Classify with Polish text normalization"""
    if request.categorizer_id not in categorizer_keywords:
        return ClassifyResponse(
            category=None,
            confidence=0.0,
            method="tags"
        )
    
    config = categorizer_configs.get(request.categorizer_id, {})
    keywords_map = categorizer_keywords[request.categorizer_id]
    
    # Normalize input text
    text_to_match = normalize_polish_text(request.text, config.get("normalize_text", True))
    
    category_scores = {}
    category_matches = {}
    
    for category, keywords in keywords_map.items():
        matches = []
        score = 0
        
        for keyword in keywords:
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            if re.search(pattern, text_to_match.lower(), re.UNICODE):
                matches.append(keyword)
                score += len(keyword.split()) * 2
        
        if matches:
            category_scores[category] = score
            category_matches[category] = matches
    
    if not category_scores:
        return ClassifyResponse(
            category=None,
            confidence=0.0,
            all_matches={},
            method="tags"
        )
    
    best_category = max(category_scores.items(), key=lambda x: x[1])[0]
    
    return ClassifyResponse(
        category=best_category,
        confidence=1.0,
        matched_keywords=category_matches[best_category],
        all_matches=category_matches,
        method="tags"
    )

@app.get("/categorizers/{categorizer_id}/keywords")
async def get_keywords(categorizer_id: str):
    if categorizer_id not in categorizer_keywords:
        raise HTTPException(status_code=404, detail="Categorizer not trained")
    
    response = {
        "categorizer_id": categorizer_id,
        "keywords": categorizer_keywords[categorizer_id],
        "config": categorizer_configs.get(categorizer_id, {})
    }
    
    if categorizer_id in categorizer_stats:
        response["statistics"] = categorizer_stats[categorizer_id]
    
    return response

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)