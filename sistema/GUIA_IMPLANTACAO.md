# Guia de Implantacao — Sistema de DRE na VPS Hostinger

## Stack Escolhida

| Componente       | Tecnologia                          |
|-----------------|-------------------------------------|
| Backend          | Python 3.11 + Flask 3.x            |
| Servidor WSGI    | Gunicorn (2 workers)                |
| Banco de Dados   | SQLite (arquivo local)              |
| Proxy Reverso    | Nginx (Alpine)                      |
| SSL              | Let's Encrypt (Certbot)             |
| Container        | Docker + Docker Compose             |
| Fuso Horario     | America/Sao_Paulo (UTC-3)           |

---

## Estrutura do Projeto

```
sistema/
  app.py                  # Aplicacao principal Flask
  database.py             # Banco de dados e calculos DRE
  requirements.txt        # Dependencias Python
  Dockerfile              # Imagem Docker
  docker-compose.yml      # Orquestracao dos servicos
  .env                    # Variaveis de ambiente (NAO versionar)
  .env.example            # Exemplo de variaveis
  start.sh                # Script para execucao local
  nginx/
    nginx.conf            # Configuracao Nginx com SSL
    nginx-sem-ssl.conf    # Configuracao Nginx sem SSL (inicial)
  templates/              # Templates HTML (Jinja2)
    base.html
    login.html
    dashboard.html
    lancamentos.html
    dre_mensal.html
    usuarios.html
    parametros.html
    api_docs.html
  static/
    logos/                # Logos das empresas (upload)
  data/
    sunomono.db           # Banco SQLite (criado automaticamente)
```

---

## Passo a Passo de Implantacao

### 1. Preparar a VPS Hostinger

Acesse a VPS via SSH:
```bash
ssh root@SEU_IP_VPS
```

Atualize o sistema:
```bash
apt update && apt upgrade -y
```

Instale Docker e Docker Compose:
```bash
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
```

Verifique a instalacao:
```bash
docker --version
docker compose version
```

### 2. Enviar Arquivos para a VPS

Opcao A — Via Git (recomendado):
```bash
cd /opt
git clone SEU_REPOSITORIO.git dre-sistema
cd dre-sistema/sistema
```

Opcao B — Via SCP:
```bash
scp -r ./sistema root@SEU_IP_VPS:/opt/dre-sistema/sistema
ssh root@SEU_IP_VPS
cd /opt/dre-sistema/sistema
```

### 3. Configurar Variaveis de Ambiente

```bash
cp .env.example .env
nano .env
```

Edite o arquivo `.env`:
```env
# OBRIGATORIO: gere uma chave segura
SECRET_KEY=cole_aqui_uma_chave_aleatoria_longa

DB_PATH=/app/data/sunomono.db
FLASK_ENV=production

# Credenciais do usuario master (usadas apenas na 1a execucao)
MASTER_LOGIN=Evelyn
MASTER_SENHA=4@ru4@v4i@me@proteger
MASTER_NOME=Evelyn (Master)
```

Para gerar a SECRET_KEY:
```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 4. Configurar Nginx

**Sem dominio (acesso por IP, sem SSL):**
```bash
cp nginx/nginx-sem-ssl.conf nginx/nginx.conf
```

**Com dominio e SSL:**
Edite `nginx/nginx.conf` e substitua `SEU_DOMINIO.com` pelo seu dominio real.

### 5. Construir e Iniciar

```bash
docker compose up -d --build
```

Verifique se esta rodando:
```bash
docker compose ps
docker compose logs -f app
```

O sistema estara acessivel em: `http://SEU_IP_VPS`

### 6. Configurar SSL (opcional, recomendado)

Se tiver um dominio apontando para a VPS:

```bash
# Primeiro, use nginx-sem-ssl para validar o dominio
docker compose down

# Gere o certificado
docker run --rm -v certbot_certs:/etc/letsencrypt -v certbot_www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d SEU_DOMINIO.com -d www.SEU_DOMINIO.com \
  --email seu@email.com --agree-tos --no-eff-email

# Restaure o nginx.conf com SSL
# (edite nginx/nginx.conf com seu dominio)
docker compose up -d
```

### 7. Criacao do Usuario Master

O usuario master e criado automaticamente na **primeira execucao** do sistema, usando as credenciais definidas no `.env`:

- Login: valor de `MASTER_LOGIN` (padrao: Evelyn)
- Senha: valor de `MASTER_SENHA` (padrao: 4@ru4@v4i@me@proteger)

**IMPORTANTE:** Apos o primeiro login, altere a senha do master pelo sistema.

### 8. Verificar Inicializacao

```bash
# Ver logs da aplicacao
docker compose logs app

# Testar endpoint de status
curl http://localhost/api/v1/status
```

Resposta esperada:
```json
{"status": "ok", "versao": "3.0", "anos": "2026-2036", "fuso": "America/Sao_Paulo"}
```

---

## Banco de Dados

- O banco SQLite fica em `./data/sunomono.db`
- E criado automaticamente na primeira execucao
- O volume Docker garante persistencia entre restarts

---

## Backup

### Backup manual:
```bash
# Copiar o banco de dados
cp /opt/dre-sistema/sistema/data/sunomono.db /opt/backups/sunomono_$(date +%Y%m%d_%H%M%S).db

# Copiar logos
cp -r /opt/dre-sistema/sistema/static/logos /opt/backups/logos_$(date +%Y%m%d)/
```

### Backup automatizado (cron):
```bash
crontab -e
```

Adicione:
```
# Backup diario as 3h da manha
0 3 * * * cp /opt/dre-sistema/sistema/data/sunomono.db /opt/backups/sunomono_$(date +\%Y\%m\%d).db
```

Crie a pasta de backups:
```bash
mkdir -p /opt/backups
```

---

## Atualizacao Futura

```bash
cd /opt/dre-sistema/sistema

# Baixar atualizacoes (se usar Git)
git pull origin main

# Reconstruir e reiniciar
docker compose down
docker compose up -d --build

# Verificar logs
docker compose logs -f app
```

O sistema executa migracoes automaticamente (`migrar_db()`) ao iniciar.

---

## Comandos Uteis

```bash
# Ver status dos containers
docker compose ps

# Ver logs em tempo real
docker compose logs -f

# Reiniciar apenas a aplicacao
docker compose restart app

# Parar tudo
docker compose down

# Reconstruir sem cache
docker compose build --no-cache
docker compose up -d

# Acessar shell do container
docker compose exec app bash

# Ver uso de disco do banco
ls -lh data/sunomono.db
```

---

## Resolucao de Problemas

### "502 Bad Gateway"
O container da aplicacao nao esta rodando:
```bash
docker compose logs app
docker compose restart app
```

### "Permission denied" no banco
```bash
chmod 777 data/
docker compose restart app
```

### Aplicacao nao inicia
Verifique as variaveis de ambiente:
```bash
docker compose exec app env | grep -E "SECRET|DB_PATH|FLASK"
```

### Resetar banco (CUIDADO: perde todos os dados)
```bash
docker compose down
rm data/sunomono.db
docker compose up -d
```

---

## Seguranca

- **NUNCA** versione o arquivo `.env` no Git
- Altere a `SECRET_KEY` do padrao para uma chave aleatoria
- Altere a senha do master apos o primeiro login
- Configure SSL o quanto antes
- Faca backups regulares do banco de dados
- Mantenha o Docker e o sistema operacional atualizados
