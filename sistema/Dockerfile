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

# Criar usuário não-root
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

# Dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Código da aplicação
COPY . .

# Pastas necessárias + permissões
RUN mkdir -p /app/static/logos /app/data && \
    chown -R appuser:appuser /app

EXPOSE 5000

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# Entrypoint que ajusta permissões de volumes montados e roda como appuser
COPY <<'ENTRY' /app/entrypoint.sh
#!/bin/sh
# Ajusta permissões em volumes montados (roda como root inicialmente)
chown -R appuser:appuser /app/data /app/static/logos 2>/dev/null || true
exec su -s /bin/sh appuser -c 'exec gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 60 --max-requests 1000 --max-requests-jitter 100 --access-logfile - app:app'
ENTRY
RUN chmod +x /app/entrypoint.sh

CMD ["/app/entrypoint.sh"]
