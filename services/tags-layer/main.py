# -*- coding: utf-8 -*-
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional
import re
from sklearn.feature_extraction.text import TfidfVectorizer
import numpy as np
from unidecode import unidecode
import logging

app = FastAPI(
    title="UCAS Tags Layer",
    version="3.1.0",
    description="Multi-language keyword categorization using TF-ICF (Category Level TF-IDF)",
    docs_url="/swagger"
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rozszerzona lista stop words
POLISH_STOPWORDS = {
    'i', 'w', 'na', 'z', 'do', 'o', 'a', 'ze', 'sie', 'nie', 'jest', 'was', 'byc',
    'to', 'ja', 'he', 'jak', 'dla', 'po', 'ale', 'od', 'za', 'przez', 'przy',
    'lub', 'oraz', 'tylko', 'moze', 'gdzie', 'kiedy', 'ktory', 'ta', 'ten', 'tego',
    'bardzo', 'mnie', 'mi', 'sobie', 'tym', 'tez', 'juz', 'co', 'czy', 'ze', 'sa',
    'mimo', 'ze', 'jak', 'brak', 'bez'
}

categorizer_keywords: Dict[str, Dict[str, List[str]]] = {}
categorizer_configs: Dict[str, Dict] = {}

class TrainRequest(BaseModel):
    categorizer_id: str
    training_data: List[Dict[str, str]]
    max_keywords: int = 12
    min_keyword_length: int = 3
    normalize_text: bool = True
    use_polish_stopwords: bool = True

class ClassifyRequest(BaseModel):
    categorizer_id: str
    text: str

class ClassifyResponse(BaseModel):
    category: Optional[str]
    confidence: float
    matched_keywords: List[str] = []
    all_matches: Dict[str, List[str]] = {}
    method: str = "tags"

def normalize_polish_text(text: str, should_normalize: bool = True) -> str:
    if not should_normalize:
        return text
    return unidecode(text).lower()

@app.get("/")
async def root():
    return {
        "service": "UCAS Tags Layer",
        "status": "running",
        "strategy": "TF-ICF",
        "version": "3.1.0"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "trained_categorizers": len(categorizer_keywords)}

@app.post("/train")
async def train(request: TrainRequest):
    try:
        categorizer_configs[request.categorizer_id] = {
            "normalize_text": request.normalize_text,
            "use_polish_stopwords": request.use_polish_stopwords,
            "max_keywords": request.max_keywords
        }
        
        # Agregacja tekstów per kategoria (Klucz do TF-ICF)
        category_corpus = {}
        
        for sample in request.training_data:
            cat = sample["category"]
            txt = sample["text"]
            
            if request.normalize_text:
                txt = normalize_polish_text(txt)
            else:
                txt = txt.lower()
                
            if cat not in category_corpus:
                category_corpus[cat] = []
            category_corpus[cat].append(txt)

        unique_categories = list(category_corpus.keys())
        
        # Łączymy wszystkie sample w jeden ogromny string dla każdej kategorii
        corpus_documents = [" ".join(category_corpus[cat]) for cat in unique_categories]
        
        stopwords_list = list(POLISH_STOPWORDS) if request.use_polish_stopwords else None

        vectorizer = TfidfVectorizer(
            max_features=2000,
            ngram_range=(1, 2),
            stop_words=stopwords_list,
            lowercase=True,
            token_pattern=r'\b[a-zA-Z0-9_]{' + str(request.min_keyword_length) + r',}\b',
            min_df=1
        )
        
        # Obliczenie TF-IDF na poziomie całych kategorii
        tfidf_matrix = vectorizer.fit_transform(corpus_documents)
        feature_names = vectorizer.get_feature_names_out()
        
        keywords_by_category = {}
        
        for i, category in enumerate(unique_categories):
            # Wyciągamy wiersz macierzy dla konkretnej kategorii
            row = tfidf_matrix.getrow(i).toarray()[0]
            
            # Tworzymy pary (słowo, score) i sortujemy malejąco
            word_scores = [(feature_names[idx], score) for idx, score in enumerate(row) if score > 0]
            word_scores.sort(key=lambda x: x[1], reverse=True)
            
            # Pobieramy top N słów kluczowych
            top_keywords = [word for word, score in word_scores[:request.max_keywords]]
            keywords_by_category[category] = top_keywords

        # Inverse-Category-Frequency: usun neutralne slowa bedace top-keywordem w zbyt wielu
        # kategoriach (np. "aplikacja", "system", "prosze"). Takie slowa nie rozrozniaja kategorii,
        # a powodowaly falszywe trafienia (pozytywny feedback -> Blad Techniczny).
        num_cat = len(unique_categories)
        if num_cat >= 2:
            kw_doc_freq = {}
            for kws in keywords_by_category.values():
                for kw in set(kws):
                    kw_doc_freq[kw] = kw_doc_freq.get(kw, 0) + 1
            icf_cutoff = max(2, (num_cat + 1) // 2)  # slowo w >= polowie kategorii = neutralne
            neutral = {kw for kw, c in kw_doc_freq.items() if c >= icf_cutoff}
            if neutral:
                logger.info(f"ICF: pomijam {len(neutral)} neutralnych slow: {sorted(neutral)[:15]}")
                keywords_by_category = {
                    cat: [kw for kw in kws if kw not in neutral]
                    for cat, kws in keywords_by_category.items()
                }

        categorizer_keywords[request.categorizer_id] = keywords_by_category
        
        return {
            "status": "trained",
            "categorizer_id": request.categorizer_id,
            "categories": unique_categories,
            "keywords": keywords_by_category,
            "training_samples": len(request.training_data),
            "extraction_method": "TF-ICF"
        }
        
    except Exception as e:
        logger.error(f"Training failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Training failed: {str(e)}")

@app.post("/classify", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    if request.categorizer_id not in categorizer_keywords:
        return ClassifyResponse(category=None, confidence=0.0)
    
    config = categorizer_configs.get(request.categorizer_id, {})
    keywords_map = categorizer_keywords[request.categorizer_id]
    
    text_to_match = normalize_polish_text(request.text, config.get("normalize_text", True))
    
    category_scores = {}
    category_matches = {}
    
    for category, keywords in keywords_map.items():
        matches = []
        score = 0
        
        for keyword in keywords:
            # Wyszukiwanie dokładnych fraz (uwzględnia n-gramy ze spacjami)
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, text_to_match):
                matches.append(keyword)
                # Dłuższe n-gramy punktują mocniej (2 słowa = waga 2)
                score += len(keyword.split()) 
        
        if matches:
            category_scores[category] = score
            category_matches[category] = matches
    
    if not category_scores:
        return ClassifyResponse(category=None, confidence=0.0)
    
    # Kategoria z największą liczbą trafień wygrywa
    best_category = max(category_scores.items(), key=lambda x: x[1])[0]
    
    # Prosty wzór pewności: zależny od liczby i długości trafień (max cap na 0.99)
    raw_score = category_scores[best_category]
    confidence = min(0.6 + (raw_score * 0.1), 0.99)
    
    return ClassifyResponse(
        category=best_category,
        confidence=confidence,
        matched_keywords=category_matches[best_category],
        all_matches=category_matches
    )

@app.get("/categorizers/{categorizer_id}/keywords")
async def get_keywords(categorizer_id: str):
    if categorizer_id not in categorizer_keywords:
        raise HTTPException(status_code=404, detail="Categorizer not trained")
    
    return {
        "categorizer_id": categorizer_id,
        "keywords": categorizer_keywords[categorizer_id]
    }

@app.post("/restore")
async def restore_categorizer(request: dict):
    categorizer_id = request.get("categorizer_id")
    keywords = request.get("keywords", {})
    categories = request.get("categories", [])
    config_data = request.get("config") or {}

    if not categorizer_id:
        raise HTTPException(status_code=400, detail="categorizer_id required")

    categorizer_keywords[categorizer_id] = keywords
    # Odtwarzamy konfiguracje jawnie, zeby /classify po restarcie dzialal tak samo jak po /train.
    # Jesli warstwa persystencji nie przeslala configu, uzywamy domyslnych (zgodnych z TrainRequest).
    categorizer_configs[categorizer_id] = {
        "normalize_text": config_data.get("normalize_text", True),
        "use_polish_stopwords": config_data.get("use_polish_stopwords", True),
        "max_keywords": config_data.get("max_keywords", 12),
    }
    return {"status": "restored", "categorizer_id": categorizer_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8010)