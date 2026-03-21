#!/bin/bash
# ─────────────────────────────────────────────────────────────
#  start.sh – Inicializa o Sistema de DRE | 2026–2036
# ─────────────────────────────────────────────────────────────
set -e
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo ""
echo "  Sistema de DRE | 2026-2036"
echo "  Inicializando..."
echo ""

# Verifica Python
if ! command -v python3 &>/dev/null; then
    echo "  Python3 nao encontrado. Instale Python 3.9+ e tente novamente."
    exit 1
fi

# Cria venv se não existir
if [ ! -d "venv" ]; then
    echo "  Criando ambiente virtual..."
    python3 -m venv venv
fi

# Ativa venv
source venv/bin/activate

# Instala dependências
echo "  Instalando dependencias..."
pip install --quiet -r requirements.txt

echo ""
echo "  Pronto!"
echo "  Acesse: http://localhost:5000"
echo ""

# Inicia servidor
python3 app.py
