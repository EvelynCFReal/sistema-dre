# 🍣 Sistema DRE Sunomono 2026–2050

> Gestão Financeira · DRE Multi-ano · Multi-loja · API REST

## 🚀 Iniciar (desenvolvimento local)

```bash
cp .env.example .env
docker compose -f docker-compose-local.yml up -d
# Acesse: http://localhost:5000
```

## 🌐 Iniciar (VPS / produção com SSL)

```bash
# Leia o GUIA_HOSTINGER_VPS.md para instruções completas
docker compose up -d
```

## 🔑 Login inicial
- **Usuário:** `Evelyn`
- **Senha:** `4@ru4@v4i@me@proteger`

## 📅 Anos suportados
**2026 até 2050** — selecione o ano no topbar do sistema

## 📚 Documentação
- `GUIA_HOSTINGER_VPS.md` — Deploy na VPS Hostinger (passo a passo para iniciantes)
- `GUIA_GITHUB_DOCKER.md` — GitHub e Docker local
- `MANUAL.md` — Manual completo do sistema
- `/api/docs` — Documentação da API REST

## ⚡ Comandos Docker

```bash
docker compose ps           # Status
docker compose logs -f      # Logs
docker compose restart      # Reiniciar
docker compose up -d --build  # Atualizar
```
