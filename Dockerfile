FROM python:3.10-slim

# Evita pyc e força stdout imediato
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# O Spaces injeta a var $PORT; o gunicorn precisa escutar nela
CMD ["bash", "-lc", "gunicorn app:server -b 0.0.0.0:$PORT --workers 2 --threads 2 --timeout 120"]
