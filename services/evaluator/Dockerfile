FROM python:3.11-slim

WORKDIR /app

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8060

# Run evaluator service
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8060", "--reload"]
