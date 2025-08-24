# Dockerfile (Hugging Face Spaces - Dash)
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# (opcional) ferramentas de build para wheels
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
 && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements.txt .
RUN python -m pip install --upgrade pip && pip install -r requirements.txt

# Código da app
COPY . .

# A Space roteia para a porta 7860
ENV PORT=7860
EXPOSE 7860

# Rode o servidor WSGI do Dash/Flask
CMD ["gunicorn", "app:server", "--bind", "0.0.0.0:7860", "--workers", "2", "--timeout", "120"]

