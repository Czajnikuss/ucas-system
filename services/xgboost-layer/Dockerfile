FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y build-essential && rm -rf /var/lib/apt/lists/*

# Install deps step by step to avoid timeout
RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn==0.32.0 pydantic==2.9.0
RUN pip install --no-cache-dir numpy==1.26.4 scipy
RUN pip install --no-cache-dir scikit-learn==1.5.2 joblib==1.4.2
RUN pip install --no-cache-dir gensim==4.3.3
RUN pip install --no-cache-dir "xgboost<2.0.0"

COPY main.py .
RUN mkdir -p /data/models

EXPOSE 8020
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8020"]