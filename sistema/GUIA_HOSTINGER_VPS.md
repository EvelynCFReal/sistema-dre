# 🚀 GUIA COMPLETO — VPS Hostinger + Docker
## Sistema DRE Sunomono 2026–2050
### Para quem nunca usou VPS ou linha de comando

---

## 🧠 ENTENDA ANTES DE COMEÇAR

**O que é uma VPS?**  
Um computador na nuvem que fica ligado 24 horas por dia. Você acessa ele pelo terminal (uma tela preta com comandos). A Hostinger vende esses computadores com planos mensais.

**Por que usar VPS em vez de rodar no computador local?**  
- Fica online 24h, mesmo com o computador desligado
- Você acessa de qualquer lugar pelo navegador
- Mais seguro e profissional

**O que você terá no final:**  
✅ Sistema rodando em `https://seudominio.com.br`  
✅ Cadeado SSL (conexão segura)  
✅ Reinicia sozinho se cair  
✅ Banco de dados com backup automático

---

## 📋 O QUE VOCÊ PRECISA

| Item | Onde conseguir | Custo aproximado |
|---|---|---|
| VPS Hostinger | hostinger.com.br | R$ 25-50/mês |
| Domínio (.com.br) | registro.br ou hostinger | R$ 40/ano |
| Conta no GitHub | github.com | Gratuito |

**Plano de VPS recomendado na Hostinger:**  
**KVM 2** (2 vCPU, 8GB RAM) — suficiente para até 10 lojas  
ou  
**KVM 1** (1 vCPU, 4GB RAM) — suficiente para 1-3 lojas

---

# PARTE 1 — PREPARAR O GITHUB

---

## PASSO 1 — Subir o código para o GitHub

> Se você já fez isso no guia anterior, pule para o **PASSO 5**.

1. Crie conta em **github.com**
2. Clique no **+** → **New repository**
3. Nome: `dre-sunomono` → marque **Private** → **Create repository**
4. Instale o Git em **git-scm.com**
5. Abra o Git Bash, entre na pasta do sistema e execute:

```bash
git init
cp .env.example .env
git add .
git commit -m "Sistema DRE Sunomono 2026-2050"
git branch -M main
git remote add origin https://github.com/SEU-USUARIO/dre-sunomono.git
git push -u origin main
```

> Substitua `SEU-USUARIO` pelo seu nome de usuário do GitHub

---

# PARTE 2 — CONFIGURAR A VPS HOSTINGER

---

## PASSO 2 — Comprar e configurar a VPS

1. Acesse **hostinger.com.br**
2. Clique em **VPS** no menu
3. Escolha o plano **KVM 1** ou **KVM 2**
4. Na configuração:
   - **Sistema Operacional:** Ubuntu 22.04 LTS ← MUITO IMPORTANTE
   - Crie uma senha forte para o root (anote!)
5. Finalize a compra
6. Aguarde 5-10 minutos para o servidor ficar pronto

---

## PASSO 3 — Acessar a VPS pelo terminal

### No Windows:
1. Abra o **PowerShell** (clique no menu Iniciar → pesquise "PowerShell")
2. Digite o comando abaixo substituindo o IP pelo IP da sua VPS (Hostinger mostra no painel):

```
ssh root@SEU_IP_DA_VPS
```

Exemplo: `ssh root@185.220.101.45`

3. Vai aparecer: `Are you sure you want to continue connecting (yes/no)?`
4. Digite `yes` e pressione Enter
5. Digite a senha que você criou no Passo 2

> 💡 No Windows 10/11, o SSH já vem instalado. Se não funcionar, baixe o **PuTTY** em putty.org

### No Mac/Linux:
Abra o Terminal e execute o mesmo comando:
```bash
ssh root@SEU_IP_DA_VPS
```

**Você verá algo assim — isso significa que funcionou:**
```
Welcome to Ubuntu 22.04.3 LTS
root@vps123456:~#
```

✅ Você está dentro da VPS!

---

## PASSO 4 — Instalar o Docker na VPS

Copie e cole este bloco inteiro no terminal (é um comando só com várias linhas):

```bash
apt update && apt upgrade -y && \
curl -fsSL https://get.docker.com | sh && \
systemctl enable docker && \
systemctl start docker && \
echo "✅ Docker instalado!"
```

Aguarde alguns minutos. Ao final verá: `✅ Docker instalado!`

Verifique:
```bash
docker --version
docker compose version
```

---

## PASSO 5 — Instalar o Git na VPS

```bash
apt install git -y
git --version
```

---

## PASSO 6 — Baixar o sistema do GitHub

```bash
cd /opt
git clone https://github.com/SEU-USUARIO/dre-sunomono.git sunomono
cd sunomono
```

> Substitua `SEU-USUARIO` pelo seu usuário GitHub  
> Se o repositório for privado, o GitHub pedirá seu login e senha (ou token)

**Para repositório privado:**  
1. No GitHub, clique na foto → **Settings** → **Developer settings** → **Personal access tokens** → **Tokens (classic)** → **Generate new token**
2. Marque a opção **repo**
3. Copie o token gerado
4. No comando git clone, use: `https://SEU-USUARIO:TOKEN@github.com/SEU-USUARIO/dre-sunomono.git`

---

## PASSO 7 — Configurar o arquivo .env

```bash
cp .env.example .env
nano .env
```

Vai abrir um editor de texto. Edite a linha `SECRET_KEY`:

```
SECRET_KEY=EscreumaChaveAleatóriaLongaAqui123456789
DB_PATH=/app/data/sunomono.db
FLASK_ENV=production
```

Para sair do nano:
- Pressione **Ctrl+X**
- Pressione **Y** para confirmar
- Pressione **Enter**

---

## PASSO 8 — Configurar o domínio

### 8a. Apontar o domínio para a VPS

1. No painel do seu provedor de domínio (Registro.br, Hostinger, etc.)
2. Vá em **DNS** ou **Gerenciar Domínio**
3. Edite o registro **A**:
   - **Nome/Host:** `@` (para o domínio principal)
   - **Valor/IP:** O IP da sua VPS (ex: `185.220.101.45`)
   - **TTL:** 3600
4. Adicione outro registro **A**:
   - **Nome/Host:** `www`
   - **Valor/IP:** O IP da sua VPS
5. Clique em **Salvar**

> ⏰ Aguarde até 24 horas para o DNS propagar, mas geralmente leva 30 minutos.

### 8b. Atualizar o nginx.conf com seu domínio

```bash
nano nginx/nginx.conf
```

Substitua **TODOS** os lugares onde aparece `SEU_DOMINIO.com` pelo seu domínio real.  
Exemplo: troque `SEU_DOMINIO.com` por `meurestaurante.com.br`

Salve com **Ctrl+X** → **Y** → **Enter**

---

## PASSO 9 — Criar as pastas necessárias

```bash
mkdir -p data static/logos
```

---

## PASSO 10 — Iniciar o sistema SEM SSL primeiro

Antes de ativar o SSL, o sistema precisa estar rodando em HTTP para o Certbot conseguir verificar o domínio.

```bash
docker compose up -d sunomono nginx
```

Aguarde 30 segundos e verifique:
```bash
docker compose ps
```

Deve mostrar os containers como **Up**.

Teste acessando `http://SEU_IP_DA_VPS` no navegador — deve aparecer a tela de login.

---

## PASSO 11 — Gerar o certificado SSL (HTTPS)

> ⚠️ Só faça isso depois que o DNS estiver apontando corretamente para a VPS (Passo 8)

Substitua `SEU_DOMINIO.com` e `seu@email.com` pelos seus dados reais:

```bash
docker compose run --rm certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email seu@email.com \
  --agree-tos \
  --no-eff-email \
  -d SEU_DOMINIO.com \
  -d www.SEU_DOMINIO.com
```

Se der certo, vai mostrar:
```
Successfully received certificate.
Certificate is saved at: /etc/letsencrypt/live/SEU_DOMINIO.com/fullchain.pem
```

---

## PASSO 12 — Reiniciar tudo com SSL

```bash
docker compose restart nginx
docker compose ps
```

Agora acesse **https://SEU_DOMINIO.com** no navegador.

Deve aparecer um cadeado 🔒 na barra de endereço!

---

## PASSO 13 — Fazer o primeiro login

- **URL:** `https://SEU_DOMINIO.com`
- **Login:** `Evelyn`
- **Senha:** `4@ru4@v4i@me@proteger`

**🔐 MUDE A SENHA IMEDIATAMENTE após o primeiro login!**

---

# PARTE 3 — MANUTENÇÃO

---

## Comandos essenciais (execute dentro da pasta `/opt/sunomono`)

```bash
# Ver se está rodando
docker compose ps

# Ver logs em tempo real
docker compose logs -f

# Reiniciar
docker compose restart

# Parar
docker compose down

# Iniciar
docker compose up -d

# Ver uso de recursos
docker stats
```

---

## Backup automático dos dados

O banco de dados fica em `/opt/sunomono/data/sunomono.db`.

**Criar backup manual:**
```bash
cp /opt/sunomono/data/sunomono.db /opt/sunomono/data/backup_$(date +%Y%m%d).db
```

**Backup automático todo dia às 3h da manhã:**
```bash
crontab -e
```

No editor que abrir, adicione esta linha no final:
```
0 3 * * * cp /opt/sunomono/data/sunomono.db /opt/sunomono/data/backup_$(date +\%Y\%m\%d).db
```

Salve com **Ctrl+X** → **Y** → **Enter**

---

## Atualizar o sistema quando houver nova versão

```bash
cd /opt/sunomono
git pull
docker compose up -d --build
```

---

## Renovação automática do SSL

O certificado SSL dura 90 dias. O container `certbot` já renova automaticamente. Para verificar:

```bash
docker compose logs certbot
```

---

# PARTE 4 — SOLUÇÃO DE PROBLEMAS

---

### ❌ "Connection refused" ao acessar o site

```bash
docker compose ps
docker compose logs sunomono
```

Se o container `sunomono` não estiver UP:
```bash
docker compose up -d --build
```

---

### ❌ Certificado SSL não funciona

Verifique se o DNS está apontando corretamente:
```bash
nslookup SEU_DOMINIO.com
```

O IP retornado deve ser o IP da sua VPS.

---

### ❌ "Permission denied" em algum arquivo

```bash
chmod -R 755 /opt/sunomono/data
chmod -R 755 /opt/sunomono/static/logos
```

---

### ❌ Sistema lento ou fora do ar depois de muito tempo

A VPS pode ter ficado sem memória. Reinicie:
```bash
docker compose restart
```

Se persistir, aumente o plano de VPS na Hostinger.

---

### ❌ Esqueci a senha do usuário Master

Execute na VPS:
```bash
docker compose exec sunomono python3 -c "
from database import get_db
from werkzeug.security import generate_password_hash
conn = get_db()
conn.execute(\"UPDATE usuarios SET senha_hash=? WHERE login='Evelyn'\",
             (generate_password_hash('NovaSenha123'),))
conn.commit()
conn.close()
print('Senha redefinida para: NovaSenha123')
"
```

Troque `NovaSenha123` pela senha que quiser.

---

# RESUMO DOS COMANDOS

```bash
# Acessar a VPS
ssh root@SEU_IP

# Instalar tudo (primeira vez)
apt update && curl -fsSL https://get.docker.com | sh && apt install git -y

# Baixar o sistema
cd /opt && git clone https://github.com/SEU-USUARIO/dre-sunomono.git sunomono && cd sunomono

# Configurar
cp .env.example .env && nano .env && mkdir -p data static/logos

# Iniciar
docker compose up -d

# Ver status
docker compose ps

# Atualizar
git pull && docker compose up -d --build
```

---

## 📞 Suporte Hostinger

- **Chat ao vivo:** hostinger.com.br → botão de suporte
- **Base de conhecimento:** support.hostinger.com.br
- Mencione que você está usando **Ubuntu 22.04 com Docker**

---

*Sistema DRE Sunomono · Suporta 2026 a 2050 · Deploy em VPS Hostinger*
