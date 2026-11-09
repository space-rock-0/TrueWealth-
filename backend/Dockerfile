FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng && rm -rf /var/lib/apt/lists/*

COPY requirements-production.txt .
RUN pip install --no-cache-dir -r requirements-production.txt

COPY . .

# Expose port 5001 (as used in main.py)
EXPOSE 5001

# Set python path to current directory so app module is found
ENV PYTHONPATH=/app
ENV RETRIEVAL_BACKEND=lexical PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 TOKENIZERS_PARALLELISM=false
ENV OCR_ENGINE=tesseract OCR_ISOLATED=true

# Verify real scanned-PDF extraction while building the production image.
RUN python scripts/check_statement_ocr.py

CMD ["python", "-m", "app.main"]
