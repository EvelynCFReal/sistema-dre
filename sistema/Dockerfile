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

# Pastas necessárias
RUN mkdir -p /app/static/logos /app/data

EXPOSE 5000

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Gunicorn para produção
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--timeout", "120", "--access-logfile", "-", "app:app"]
