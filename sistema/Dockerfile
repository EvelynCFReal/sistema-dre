# ─────────────────────────────────────────────────────────────
#  Dockerfile – Sistema de DRE | 2026–2036
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Fuso horário de Brasília
ENV TZ=America/Sao_Paulo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# Dependências do sistema
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

# Pastas necessárias + permissões
RUN mkdir -p /app/static/logos /app/data && \
    groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app

EXPOSE 5000

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

USER appuser

# Gunicorn otimizado: 4 workers, timeout 60s, reciclagem de memória
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--timeout", "60", "--max-requests", "1000", "--max-requests-jitter", "100", "--access-logfile", "-", "app:app"]
