FROM python:3.11-slim

WORKDIR /app

ENV TZ=America/Sao_Paulo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Criar usuário não-root
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

COPY sistema/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY sistema/ .

# Pastas necessárias + permissões
RUN mkdir -p /app/static/logos /app/data && \
    chown -R appuser:appuser /app && \
    chmod +x /app/entrypoint.sh

EXPOSE 5000

ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

CMD ["/app/entrypoint.sh"]
