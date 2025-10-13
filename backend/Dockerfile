FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    tesseract-ocr \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install dependencies in stages with longer timeouts
# Stage 1: Install basic dependencies (fast)
RUN pip install --default-timeout=1000 --no-cache-dir \
    fastapi==0.109.0 \
    uvicorn[standard]==0.27.0 \
    pydantic==2.5.3 \
    pydantic-settings==2.1.0 \
    httpx==0.26.0

# Stage 2: Install database dependencies
RUN pip install --default-timeout=1000 --no-cache-dir \
    psycopg2-binary==2.9.9 \
    sqlalchemy==2.0.25 \
    alembic==1.13.1 \
    qdrant-client==1.7.0 \
    redis==5.0.1 \
    minio==7.2.3

# Stage 3: Install document processing (smaller packages)
RUN pip install --default-timeout=1000 --no-cache-dir \
    PyMuPDF==1.23.8 \
    python-docx==1.1.0 \
    pytesseract==0.3.10 \
    pdf2image==1.16.3

# Stage 4: Install ML packages (LARGE - with retries)
# Using CPU-only PyTorch to reduce size from 670MB to ~200MB
RUN pip install --default-timeout=2000 --retries 5 --no-cache-dir \
    torch==2.1.2 --index-url https://download.pytorch.org/whl/cpu

# Stage 5: Install transformers and sentence-transformers
RUN pip install --default-timeout=1000 --no-cache-dir \
    transformers==4.37.0 \
    sentence-transformers==2.3.1 \
    spacy==3.7.2

# Stage 6: Install remaining dependencies
RUN pip install --default-timeout=1000 --no-cache-dir \
    openai==1.10.0 \
    groq==0.4.1 \
    cohere==4.43 \
    anthropic==0.8.1 \
    rank-bm25==0.2.2 \
    langchain==0.1.4 \
    langchain-community==0.0.16 \
    langchain-openai==0.0.5 \
    ragas==0.1.1 \
    datasets==2.16.1

# Stage 7: Install utilities
RUN pip install --default-timeout=1000 --no-cache-dir \
    python-multipart==0.0.6 \
    python-jose[cryptography]==3.3.0 \
    passlib[bcrypt]==1.7.4 \
    python-dotenv==1.0.0 \
    aiofiles==23.2.1 \
    tqdm==4.66.1 \
    numpy==1.26.3 \
    pandas==2.1.4 \
    scikit-learn==1.4.0 \
    prometheus-client==0.19.0

# Download spaCy model (FIXED - using direct pip install)
RUN pip install --default-timeout=1000 --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.7.1/en_core_web_sm-3.7.1-py3-none-any.whl

# Copy application code
COPY . .

# Create directories
RUN mkdir -p documents/uploads documents/raw documents/processed

# Expose port
EXPOSE 8001

# Run application
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001", "--reload"]