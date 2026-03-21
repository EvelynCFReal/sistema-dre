# 🖥️ GUIA COMPLETO: VPS Hostinger + Docker + GitHub
## Sistema DRE Sunomono 2026–2036
### Explicado do zero para quem nunca usou

---

> **O que você vai ter no final:**  
> ✅ Sistema rodando na internet com seu próprio domínio  
> ✅ HTTPS (cadeado verde no navegador)  
> ✅ Acesso de qualquer computador ou celular  
> ✅ Dados salvos permanentemente no servidor  
> ✅ Sistema que reinicia sozinho se cair  

---

## 🗺️ VISÃO GERAL DO QUE VOCÊ VAI FAZER

```
Seu Computador           GitHub              VPS Hostinger
      │                     │                      │
      │── push do código ──►│                      │
      │                     │── git clone ─────── ►│
      │                     │                      │── docker compose up
      │                     │                      │── Sistema rodando!
      │                     │                      │
      │◄──── acessa pelo domínio ──────────────────│
```

---

# PARTE 1 — PREPARAR O GITHUB

---

## PASSO 1 — Criar conta e repositório no GitHub

1. Acesse **https://github.com** → clique **Sign up**
2. Preencha e-mail, senha, nome de usuário → confirme por e-mail
3. Após login, clique **"+"** (canto superior direito) → **"New repository"**
4. Preencha:
   - **Name:** `dre-sunomono`
   - Marque **Private** ← seus dados ficam privados
5. Clique **Create repository**
6. Anote a URL: `https://github.com/SEU_USUARIO/dre-sunomono.git`

---

## PASSO 2 — Instalar o Git e enviar o código

**No Windows:** Baixe em https://git-scm.com → instale com todas as opções padrão → abra o **Git Bash**

**No Mac/Linux:** Abra o Terminal

Dentro da pasta do sistema, execute **um comando por vez**:

```bash
git init
cp .env.example .env
git add .
git commit -m "DRE Sunomono - versão inicial"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/dre-sunomono.git
git push -u origin main
```

> Quando pedir login, entre com usuário e senha do GitHub

✅ Código no GitHub!

---

# PARTE 2 — PREPARAR A VPS HOSTINGER

---

## PASSO 3 — Comprar e configurar a VPS

### 3.1 — Comprar na Hostinger

1. Acesse **https://www.hostinger.com.br/vps-hosting**
2. Escolha o plano **KVM 1** (o mais barato, suficiente para começar)
   - CPU: 1 vCPU · RAM: 1 GB · SSD: 20 GB
3. Finalize a compra

> 💡 Se tiver um domínio, aponte-o para o IP da VPS depois (passo 5)

### 3.2 — Configurar o sistema operacional

No painel da Hostinger (hPanel):
1. Clique em **VPS** → na sua VPS → **Manage**
2. Clique em **OS & Panel**
3. Escolha: **Ubuntu 22.04** (sem painel de controle, só o sistema puro)
4. Clique **Change OS** → confirme

> ⚠️ Aguarde 5-10 minutos para reinstalar

### 3.3 — Pegar o IP e senha root

No painel da VPS:
1. Copie o **IP da VPS** (algo como `91.108.4.220`)
2. Em **Details**, veja/redefina a **senha root**

---

## PASSO 4 — Conectar na VPS pelo terminal

### No Windows

1. Abra o **Putty** ou use o **Windows Terminal**
2. Se usar Windows Terminal:
   ```
   ssh root@91.108.4.220
   ```
   (substitua pelo IP da sua VPS)
3. Quando aparecer "yes/no", digite `yes` e Enter
4. Digite a senha root (a senha não aparece na tela — é normal)

### No Mac/Linux

```bash
ssh root@91.108.4.220
```

> 💡 O terminal vai parecer diferente — você está dentro do servidor agora!

---

## PASSO 5 — Preparar o servidor (execute tudo isso no servidor)

### 5.1 — Atualizar o sistema

```bash
apt update && apt upgrade -y
```
> Aguarde terminar (pode demorar 2-3 minutos)

### 5.2 — Instalar o Docker

```bash
curl -fsSL https://get.docker.com | sh
```
> Aguarde a instalação

Verifique:
```bash
docker --version
docker compose version
```
Deve mostrar as versões instaladas.

### 5.3 — Instalar o Git

```bash
apt install git -y
```

---

## PASSO 6 — Baixar o sistema no servidor

```bash
# Cria uma pasta organizada
mkdir -p /opt/sunomono
cd /opt/sunomono

# Baixa o código do GitHub
git clone https://github.com/SEU_USUARIO/dre-sunomono.git .
```

> Se o repositório for privado, o GitHub vai pedir seu usuário e senha.  
> Para não precisar digitar toda vez, crie um "Personal Access Token":  
> GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic) → Generate new token  
> Marque o escopo `repo` → copie o token → use como senha

---

## PASSO 7 — Configurar o .env no servidor

```bash
cp .env.example .env
nano .env
```

O editor vai abrir. Edite assim:

```
SECRET_KEY=escreva_aqui_uma_frase_longa_e_aleatória_sem_espaços_2026
DB_PATH=/app/data/sunomono.db
FLASK_ENV=production
```

Para sair do nano:
- Pressione `Ctrl + X`
- Pressione `Y`  
- Pressione `Enter`

---

## PASSO 8 — Iniciar o sistema SEM SSL (primeira vez)

Primeiro, use a configuração sem HTTPS para testar:

```bash
# Copia a configuração nginx sem SSL
cp nginx/nginx-sem-ssl.conf nginx/nginx.conf

# Cria as pastas necessárias
mkdir -p data static/logos certbot/conf certbot/www

# Sobe o sistema (sem o certbot por enquanto)
docker compose up -d sunomono nginx
```

Aguarde o download das imagens (1-2 min na primeira vez).

Verifique se está rodando:
```bash
docker compose ps
```

Deve aparecer `running` para `dre-sunomono` e `dre-nginx`.

**Teste no navegador:** `http://SEU_IP_DA_VPS`

Se aparecer a tela de login → ✅ funcionou!

Login: `Evelyn` | Senha: `4@ru4@v4i@me@proteger`

---

## PASSO 9 — Configurar domínio e SSL (HTTPS)

### 9.1 — Apontar o domínio para a VPS

No seu provedor de domínio (Hostinger, Registro.br, GoDaddy...):

1. Acesse o gerenciamento de DNS do domínio
2. Crie/edite o registro tipo **A**:
   - **Nome/Host:** `@` (ou em branco = domínio raiz)
   - **Valor/Destino:** `91.108.4.220` (IP da sua VPS)
3. Crie outro registro tipo **A**:
   - **Nome/Host:** `www`
   - **Valor/Destino:** `91.108.4.220`
4. Aguarde propagação: 5 minutos a 24 horas (geralmente 15-30 min)

Teste: `http://SEU_DOMINIO.com` deve abrir o sistema

### 9.2 — Ativar HTTPS com Let's Encrypt (gratuito)

No servidor, edite o `nginx/nginx.conf` principal:

```bash
# Substitua SEU_DOMINIO.com pelo seu domínio real nas próximas linhas
sed -i 's/SEU_DOMINIO.com/meusite.com.br/g' nginx/nginx.conf
sed -i 's/SEU_EMAIL@email.com/meuemail@gmail.com/g' docker-compose.yml
```

Gere o certificado SSL:

```bash
# Para o nginx para liberar a porta 80
docker compose stop nginx

# Gera o certificado
docker compose --profile ssl run --rm certbot

# Reinicia o nginx com SSL
docker compose up -d nginx
```

Teste: `https://SEU_DOMINIO.com` → deve abrir com o cadeado verde! 🔒

### 9.3 — Renovação automática do SSL

O certificado Let's Encrypt expira a cada 90 dias. Configure renovação automática:

```bash
crontab -e
```

Adicione esta linha no final:

```
0 3 * * * cd /opt/sunomono && docker compose run --rm certbot renew && docker compose restart nginx
```

Salve: `Ctrl+X` → `Y` → `Enter`

---

## PASSO 10 — Sistema funcionando! ✅

Acesse **https://SEU_DOMINIO.com**

Login: `Evelyn` | Senha: `4@ru4@v4i@me@proteger`

> ⚠️ **Primeira coisa a fazer:** Entre em Configurações → Empresa e altere os dados da sua empresa

---

# PARTE 3 — MANUTENÇÃO DO SERVIDOR

---

## Comandos úteis do dia a dia

```bash
# Sempre entre nesta pasta antes
cd /opt/sunomono

# Ver se está rodando
docker compose ps

# Ver os últimos logs
docker compose logs --tail=50

# Reiniciar o sistema
docker compose restart

# Parar tudo
docker compose down

# Iniciar novamente
docker compose up -d
```

---

## Atualizar o sistema quando houver nova versão

```bash
cd /opt/sunomono

# Baixa as atualizações do GitHub
git pull

# Reconstrói e reinicia
docker compose up -d --build
```

> Os dados são preservados — ficam na pasta `data/` que está fora do container

---

## Backup dos dados

O banco de dados fica em `/opt/sunomono/data/sunomono.db`

### Backup manual:
```bash
cp /opt/sunomono/data/sunomono.db /opt/sunomono/data/backup_$(date +%Y%m%d).db
```

### Backup automático diário para o GitHub:
```bash
crontab -e
```

Adicione:
```
0 2 * * * cd /opt/sunomono && cp data/sunomono.db data/backup_$(date +\%Y\%m\%d).db
```

### Copiar backup para o seu computador:
```bash
# No SEU computador (não no servidor):
scp root@SEU_IP:/opt/sunomono/data/sunomono.db ~/Desktop/backup_sunomono.db
```

---

## Monitorar uso de recursos

```bash
# Uso de CPU e RAM do Docker
docker stats

# Espaço em disco
df -h

# Memória
free -h
```

---

## Redefinir senha do Master (emergência)

```bash
cd /opt/sunomono
docker compose exec sunomono python3 -c "
from database import get_db
from werkzeug.security import generate_password_hash
conn = get_db()
conn.execute(\"UPDATE usuarios SET senha_hash=? WHERE login='Evelyn'\",
             (generate_password_hash('NovaSenha123!'),))
conn.commit()
conn.close()
print('Senha redefinida para: NovaSenha123!')
"
```

---

## Aumentar a VPS (se ficar lento)

Se o sistema ficar lento com muitos usuários:
1. No hPanel da Hostinger → VPS → **Upgrade**
2. Escolha um plano maior
3. Não perde os dados

---

# PARTE 4 — PROBLEMAS COMUNS

---

### ❌ "Connection refused" ao conectar pelo SSH
- Aguarde mais alguns minutos após a criação da VPS
- Confirme o IP correto no painel da Hostinger

### ❌ Site não abre no navegador
```bash
# Veja se os containers estão rodando
docker compose ps

# Veja os erros
docker compose logs nginx
docker compose logs sunomono
```

### ❌ "Permission denied" no servidor
Execute os comandos com `sudo`, ou já esteja como root (que é o padrão na Hostinger)

### ❌ Domínio não abre (mas IP abre)
- DNS ainda propagando — aguarde até 24h
- Teste: `nslookup SEU_DOMINIO.com` — deve mostrar o IP da VPS

### ❌ Erro de SSL / certificado não gerado
```bash
# Tente novamente após o domínio estar propagado
docker compose --profile ssl run --rm certbot certonly --webroot \
  -w /var/www/certbot --email SEU_EMAIL -d SEU_DOMINIO.com \
  --agree-tos --no-eff-email --force-renewal
```

### ❌ Sistema parou de responder
```bash
# Reinicia tudo
docker compose down
docker compose up -d
```

---

# RESUMO DOS COMANDOS (cole e salve)

```bash
# ── INSTALAÇÃO (só uma vez no servidor) ──────────────
curl -fsSL https://get.docker.com | sh
apt install git -y
mkdir -p /opt/sunomono && cd /opt/sunomono
git clone https://github.com/SEU_USUARIO/dre-sunomono.git .
cp .env.example .env && nano .env   # edite o SECRET_KEY
mkdir -p data static/logos certbot/conf certbot/www
cp nginx/nginx-sem-ssl.conf nginx/nginx.conf
docker compose up -d sunomono nginx

# ── DIA A DIA ────────────────────────────────────────
cd /opt/sunomono
docker compose ps          # ver status
docker compose logs        # ver logs
docker compose restart     # reiniciar
docker compose up -d --build   # atualizar após git pull

# ── BACKUP ───────────────────────────────────────────
cp data/sunomono.db data/backup_$(date +%Y%m%d).db
```

---

*Dúvidas? Abra um Issue no GitHub do projeto.*  
*Sistema DRE Sunomono · 2026-2036*
