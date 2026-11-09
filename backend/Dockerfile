FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 && rm -rf /var/lib/apt/lists/*

COPY requirements-production.txt .
RUN pip install --no-cache-dir -r requirements-production.txt

COPY . .

# Expose port 5001 (as used in main.py)
EXPOSE 5001

# Set python path to current directory so app module is found
ENV PYTHONPATH=/app
ENV RETRIEVAL_BACKEND=lexical PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false

CMD ["python", "-m", "app.main"]
