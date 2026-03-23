"""
database.py – Sistema de DRE | 2026–2036
Banco SQLite com suporte a multilojas, permissões por loja e 4 níveis de usuário.
"""
import sqlite3
import os
import secrets
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "data", "sunomono.db")
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

ANO_INICIO = 2026
ANO_FIM = 2036
ANOS = list(range(ANO_INICIO, ANO_FIM + 1))

MESES = [
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]

TIPOS_USUARIO = ("master", "gestor", "loja", "leitor")


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


# ──────────────────────────────────────────
#  INICIALIZAÇÃO DO BANCO
# ──────────────────────────────────────────
def init_db():
    # Verifica se o banco já foi inicializado (tabela lojas já existe com dados)
    db_is_new = not os.path.exists(DB_PATH) or os.path.getsize(DB_PATH) == 0
    conn = get_db()
    c = conn.cursor()
    # Se o banco já tem lojas cadastradas, não é novo
    if not db_is_new:
        try:
            row = c.execute("SELECT COUNT(*) FROM lojas").fetchone()
            if row and row[0] > 0:
                db_is_new = False
            else:
                db_is_new = True
        except Exception:
            db_is_new = True
    c.executescript("""
    /* Empresas / Lojas */
    CREATE TABLE IF NOT EXISTS lojas (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        nome            TEXT NOT NULL,
        cnpj            TEXT DEFAULT '',
        razao_social    TEXT DEFAULT '',
        endereco        TEXT DEFAULT '',
        telefone        TEXT DEFAULT '',
        email           TEXT DEFAULT '',
        logo_path       TEXT DEFAULT '',
        cor_primaria    TEXT DEFAULT '#c8a96e',
        cor_secundaria  TEXT DEFAULT '#3ecf8e',
        cor_fundo       TEXT DEFAULT '#0d0f14',
        cor_texto       TEXT DEFAULT '#e8eaf0',
        tema            TEXT DEFAULT 'escuro',
        ativo           INTEGER DEFAULT 1,
        criado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    /* Usuários */
    CREATE TABLE IF NOT EXISTS usuarios (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        login       TEXT UNIQUE NOT NULL,
        senha_hash  TEXT NOT NULL,
        nome        TEXT NOT NULL,
        tipo        TEXT NOT NULL CHECK(tipo IN ('master','gestor','loja','leitor')),
        ativo       INTEGER DEFAULT 1,
        tema_preferido TEXT DEFAULT 'escuro',
        criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    /* Vínculo usuário ↔ loja com perfil por loja */
    CREATE TABLE IF NOT EXISTS usuario_lojas (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        loja_id     INTEGER NOT NULL REFERENCES lojas(id) ON DELETE CASCADE,
        perfil      TEXT NOT NULL CHECK(perfil IN ('gestor','loja','leitor')),
        UNIQUE(usuario_id, loja_id)
    );

    /* Permissões de meses (para usuário loja) */
    CREATE TABLE IF NOT EXISTS permissoes_meses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
        loja_id     INTEGER NOT NULL REFERENCES lojas(id) ON DELETE CASCADE,
        ano         INTEGER NOT NULL,
        mes         INTEGER NOT NULL,
        UNIQUE(usuario_id, loja_id, ano, mes)
    );

    /* Formas de pagamento */
    CREATE TABLE IF NOT EXISTS formas_pagamento (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        taxa    REAL DEFAULT 0,
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Plataformas / Apps */
    CREATE TABLE IF NOT EXISTS plataformas (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Categorias de despesa */
    CREATE TABLE IF NOT EXISTS categorias_despesa (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        tipo    TEXT NOT NULL CHECK(tipo IN ('cmv','fixa','motoboy','balcao','financeira','outra')),
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Marcas */
    CREATE TABLE IF NOT EXISTS marcas (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Tipos de faturamento */
    CREATE TABLE IF NOT EXISTS tipos_faturamento (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Tipos de despesa */
    CREATE TABLE IF NOT EXISTS tipos_despesa (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Tipos de lançamento */
    CREATE TABLE IF NOT EXISTS tipos_lancamento (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        nome    TEXT NOT NULL,
        loja_id INTEGER REFERENCES lojas(id),
        ativo   INTEGER DEFAULT 1
    );

    /* Lançamentos de caixa */
    CREATE TABLE IF NOT EXISTS lancamentos_caixa (
        id                  INTEGER PRIMARY KEY AUTOINCREMENT,
        loja_id             INTEGER NOT NULL REFERENCES lojas(id),
        data                DATE NOT NULL,
        turno               TEXT NOT NULL CHECK(turno IN ('almoco','jantar','pos_meia_noite')),
        forma_pagamento_id  INTEGER NOT NULL REFERENCES formas_pagamento(id),
        plataforma_id       INTEGER REFERENCES plataformas(id),
        marca_id            INTEGER REFERENCES marcas(id),
        valor               REAL DEFAULT 0,
        taxa_aplicada       REAL DEFAULT 0,
        usuario_id          INTEGER NOT NULL REFERENCES usuarios(id),
        criado_em           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    /* Lançamentos de despesa */
    CREATE TABLE IF NOT EXISTS lancamentos_despesa (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        loja_id         INTEGER NOT NULL REFERENCES lojas(id),
        data            DATE NOT NULL,
        categoria_id    INTEGER NOT NULL REFERENCES categorias_despesa(id),
        marca_id        INTEGER REFERENCES marcas(id),
        valor           REAL DEFAULT 0,
        descricao       TEXT DEFAULT '',
        usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
        criado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    /* Aporte / Sangria */
    CREATE TABLE IF NOT EXISTS aporte_sangria (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        loja_id     INTEGER NOT NULL REFERENCES lojas(id),
        data        DATE NOT NULL,
        tipo        TEXT NOT NULL CHECK(tipo IN ('aporte','sangria')),
        marca_id    INTEGER REFERENCES marcas(id),
        valor       REAL DEFAULT 0,
        descricao   TEXT DEFAULT '',
        usuario_id  INTEGER NOT NULL REFERENCES usuarios(id),
        criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    /* Configurações por loja */
    CREATE TABLE IF NOT EXISTS configuracoes (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        chave   TEXT NOT NULL,
        valor   TEXT NOT NULL,
        loja_id INTEGER REFERENCES lojas(id),
        UNIQUE(chave, loja_id)
    );

    /* API Keys */
    CREATE TABLE IF NOT EXISTS api_keys (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        nome        TEXT NOT NULL,
        chave       TEXT UNIQUE NOT NULL,
        loja_id     INTEGER REFERENCES lojas(id),
        permissoes  TEXT DEFAULT 'read',
        ativo       INTEGER DEFAULT 1,
        criado_por  INTEGER REFERENCES usuarios(id),
        criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        ultimo_uso  TIMESTAMP
    );
    """)

    # ── SEED: só executa na PRIMEIRA inicialização do banco ──
    # Isso impede que dados deletados pelo usuário sejam recriados após atualizações
    if db_is_new:
        # Seed: loja padrão
        c.execute(
            "INSERT OR IGNORE INTO lojas(id, nome) VALUES(1, 'Loja Principal')"
        )

        # Seed: usuário master (credencial via env ou padrão seguro)
        master_login = os.environ.get("MASTER_LOGIN", "Evelyn")
        master_senha = os.environ.get("MASTER_SENHA", "4@ru4@v4i@me@proteger")
        master_nome = os.environ.get("MASTER_NOME", "Evelyn (Master)")

        if not c.execute(
            "SELECT 1 FROM usuarios WHERE tipo='master'"
        ).fetchone():
            c.execute(
                "INSERT INTO usuarios(login, senha_hash, nome, tipo) VALUES(?,?,?,?)",
                (master_login, generate_password_hash(master_senha), master_nome, "master"),
            )

        # Seed: formas de pagamento padrão (vinculadas à loja 1)
        fps = [
            ("Crédito", 0.018), ("Débito", 0.008),
            ("Pagamento Online Ifood", 0.115), ("Outros pgtos Ifood", 0.08),
            ("Pagamento Online DD", 0.03), ("Pix Loja", 0.0),
            ("ALELO", 0.0399), ("VR", 0.068), ("TR", 0.0399),
            ("SODEXHO", 0.0399), ("Dinheiro", 0.0), ("Moeda", 0.0),
        ]
        for nome, taxa in fps:
            if not c.execute("SELECT 1 FROM formas_pagamento WHERE nome=? AND loja_id=1", (nome,)).fetchone():
                c.execute(
                    "INSERT INTO formas_pagamento(nome, taxa, loja_id) VALUES(?,?,1)",
                    (nome, taxa),
                )

        # Seed: plataformas padrão
        for p in ["DELIVERY DIRETO", "MONO BOX", "SUNOMONO", "MONO POKE", "SUSHILÍCIA"]:
            if not c.execute("SELECT 1 FROM plataformas WHERE nome=? AND loja_id=1", (p,)).fetchone():
                c.execute("INSERT INTO plataformas(nome, loja_id) VALUES(?,1)", (p,))

        # Seed: marcas padrão
        for marca in ["SUNOMONO", "MONO BOX", "MONO POKE", "SUSHILÍCIA"]:
            if not c.execute("SELECT 1 FROM marcas WHERE nome=? AND loja_id=1", (marca,)).fetchone():
                c.execute("INSERT INTO marcas(nome, loja_id) VALUES(?,1)", (marca,))

        # Seed: categorias de despesa padrão
        cats = [
            ("Hortifrutti", "cmv"), ("Mercado", "cmv"), ("Bebidas", "cmv"),
            ("Salmão", "cmv"), ("Atum", "cmv"), ("Peixe Branco", "cmv"),
            ("Camarão", "cmv"), ("Kani", "cmv"), ("Embalagens", "cmv"),
            ("Aluguel", "fixa"), ("Passagem", "fixa"), ("Salários", "fixa"),
            ("Light", "fixa"), ("Gás", "fixa"), ("Contador", "fixa"),
            ("Motoboys", "motoboy"), ("Despesas Balcão", "balcao"),
            ("Taxas/Financeiras", "financeira"), ("Outras Despesas", "outra"),
        ]
        for nome, tipo in cats:
            if not c.execute("SELECT 1 FROM categorias_despesa WHERE nome=? AND loja_id=1", (nome,)).fetchone():
                c.execute(
                    "INSERT INTO categorias_despesa(nome, tipo, loja_id) VALUES(?,?,1)",
                    (nome, tipo),
                )

        # Seed: configurações padrão (vinculadas à loja 1)
        for ch, v in [
            ("royalties", "1500"),
            ("verba_marketing", "0"),
            ("meta_faturamento_mensal", "50000"),
        ]:
            if not c.execute("SELECT 1 FROM configuracoes WHERE chave=? AND loja_id=1", (ch,)).fetchone():
                c.execute(
                    "INSERT INTO configuracoes(chave, valor, loja_id) VALUES(?,?,1)",
                    (ch, v),
                )

    conn.commit()
    conn.close()


# ──────────────────────────────────────────
#  MIGRAÇÃO: adiciona colunas que podem faltar
# ──────────────────────────────────────────
def migrar_db():
    """Executa migrações seguras para manter compatibilidade."""
    conn = get_db()
    c = conn.cursor()

    # Verifica se a tabela usuario_lojas existe
    tabelas = [
        r[0]
        for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    ]

    if "usuario_lojas" not in tabelas:
        c.execute("""
        CREATE TABLE usuario_lojas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            loja_id INTEGER NOT NULL REFERENCES lojas(id) ON DELETE CASCADE,
            perfil TEXT NOT NULL CHECK(perfil IN ('gestor','loja','leitor')),
            UNIQUE(usuario_id, loja_id)
        )""")

        # Migra dados do campo loja_id antigo se existir
        cols = [r[1] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
        if "loja_id" in cols:
            rows = c.execute(
                "SELECT id, tipo, loja_id FROM usuarios WHERE loja_id IS NOT NULL AND tipo != 'master'"
            ).fetchall()
            for r in rows:
                perfil = r[1] if r[1] in ("gestor", "loja", "leitor") else "leitor"
                c.execute(
                    "INSERT OR IGNORE INTO usuario_lojas(usuario_id, loja_id, perfil) VALUES(?,?,?)",
                    (r[0], r[2], perfil),
                )

    # Adiciona tema_preferido se não existir
    cols = [r[1] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "tema_preferido" not in cols:
        c.execute("ALTER TABLE usuarios ADD COLUMN tema_preferido TEXT DEFAULT 'escuro'")

    # Verifica tabelas de parâmetros extras
    for tab, ddl in [
        ("marcas", "CREATE TABLE marcas(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, loja_id INTEGER REFERENCES lojas(id), ativo INTEGER DEFAULT 1)"),
        ("tipos_faturamento", "CREATE TABLE tipos_faturamento(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, loja_id INTEGER REFERENCES lojas(id), ativo INTEGER DEFAULT 1)"),
        ("tipos_despesa", "CREATE TABLE tipos_despesa(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, loja_id INTEGER REFERENCES lojas(id), ativo INTEGER DEFAULT 1)"),
        ("tipos_lancamento", "CREATE TABLE tipos_lancamento(id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, loja_id INTEGER REFERENCES lojas(id), ativo INTEGER DEFAULT 1)"),
    ]:
        if tab not in tabelas:
            c.execute(ddl)

    # Adiciona loja_id em permissoes_meses se não existir
    cols_pm = [r[1] for r in c.execute("PRAGMA table_info(permissoes_meses)").fetchall()]
    if "loja_id" not in cols_pm:
        c.execute("ALTER TABLE permissoes_meses ADD COLUMN loja_id INTEGER REFERENCES lojas(id) DEFAULT 1")

    # Adiciona taxa_aplicada em lancamentos_caixa se não existir
    cols_lc = [r[1] for r in c.execute("PRAGMA table_info(lancamentos_caixa)").fetchall()]
    if "taxa_aplicada" not in cols_lc:
        c.execute("ALTER TABLE lancamentos_caixa ADD COLUMN taxa_aplicada REAL DEFAULT 0")
        # Preenche lançamentos existentes com a taxa atual da forma de pagamento
        c.execute("""
            UPDATE lancamentos_caixa SET taxa_aplicada = (
                SELECT COALESCE(fp.taxa, 0) FROM formas_pagamento fp
                WHERE fp.id = lancamentos_caixa.forma_pagamento_id
            ) WHERE taxa_aplicada = 0 OR taxa_aplicada IS NULL
        """)

    # Adiciona marca_id nas tabelas de lançamento se não existir
    for tab in ["lancamentos_caixa", "lancamentos_despesa", "aporte_sangria"]:
        cols_tab = [r[1] for r in c.execute(f"PRAGMA table_info({tab})").fetchall()]
        if "marca_id" not in cols_tab:
            c.execute(f"ALTER TABLE {tab} ADD COLUMN marca_id INTEGER REFERENCES marcas(id)")

    # Migra itens globais (loja_id=NULL) para loja 1
    # Deleta duplicatas NULL que já existem em loja 1, depois move o restante
    for tab in ["formas_pagamento", "plataformas", "categorias_despesa",
                "marcas", "tipos_faturamento", "tipos_despesa", "tipos_lancamento"]:
        c.execute(f"DELETE FROM {tab} WHERE loja_id IS NULL AND nome IN (SELECT nome FROM {tab} WHERE loja_id=1)")
        c.execute(f"UPDATE {tab} SET loja_id=1 WHERE loja_id IS NULL")
    c.execute("DELETE FROM configuracoes WHERE loja_id IS NULL AND chave IN (SELECT chave FROM configuracoes WHERE loja_id=1)")
    c.execute("UPDATE configuracoes SET loja_id=1 WHERE loja_id IS NULL")

    # ── Tabela talentos_notas (Banco de Talentos) ──
    if "talentos_notas" not in tabelas:
        c.execute("""
        CREATE TABLE talentos_notas (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            banco           TEXT NOT NULL CHECK(banco IN ('sunomono','monopizza','grupomono')),
            candidato_email TEXT NOT NULL,
            ex_funcionario  INTEGER DEFAULT 0,
            contratou       INTEGER DEFAULT 0,
            observacao      TEXT DEFAULT '',
            atualizado_por  INTEGER REFERENCES usuarios(id),
            atualizado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(banco, candidato_email)
        )""")
    else:
        # Migra tabela para aceitar 'grupomono' no CHECK constraint
        tbl_sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='talentos_notas'").fetchone()
        if tbl_sql and "grupomono" not in tbl_sql[0]:
            c.execute("ALTER TABLE talentos_notas RENAME TO _talentos_notas_old")
            c.execute("""
            CREATE TABLE talentos_notas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                banco           TEXT NOT NULL CHECK(banco IN ('sunomono','monopizza','grupomono')),
                candidato_email TEXT NOT NULL,
                ex_funcionario  INTEGER DEFAULT 0,
                contratou       INTEGER DEFAULT 0,
                observacao      TEXT DEFAULT '',
                atualizado_por  INTEGER REFERENCES usuarios(id),
                atualizado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(banco, candidato_email)
            )""")
            c.execute("""INSERT INTO talentos_notas(id,banco,candidato_email,ex_funcionario,contratou,observacao,atualizado_por,atualizado_em)
                         SELECT id,banco,candidato_email,ex_funcionario,contratou,observacao,atualizado_por,atualizado_em FROM _talentos_notas_old""")
            c.execute("DROP TABLE _talentos_notas_old")

    # Adiciona colunas de acesso ao Banco de Talentos nos usuários
    cols_usr = [r[1] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "acesso_talentos_sunomono" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_talentos_sunomono INTEGER DEFAULT 0")
    if "acesso_talentos_monopizza" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_talentos_monopizza INTEGER DEFAULT 0")
    if "acesso_talentos_grupomono" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_talentos_grupomono INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def copiar_parametros_loja(loja_origem_id, loja_destino_id):
    """Copia parâmetros da loja de origem para a loja de destino."""
    conn = get_db()
    c = conn.cursor()

    # Formas de pagamento
    for r in c.execute("SELECT nome, taxa FROM formas_pagamento WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO formas_pagamento(nome, taxa, loja_id) VALUES(?,?,?)", (r[0], r[1], loja_destino_id))

    # Plataformas
    for r in c.execute("SELECT nome FROM plataformas WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO plataformas(nome, loja_id) VALUES(?,?)", (r[0], loja_destino_id))

    # Categorias de despesa
    for r in c.execute("SELECT nome, tipo FROM categorias_despesa WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO categorias_despesa(nome, tipo, loja_id) VALUES(?,?,?)", (r[0], r[1], loja_destino_id))

    # Marcas
    for r in c.execute("SELECT nome FROM marcas WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO marcas(nome, loja_id) VALUES(?,?)", (r[0], loja_destino_id))

    # Tipos de faturamento
    for r in c.execute("SELECT nome FROM tipos_faturamento WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO tipos_faturamento(nome, loja_id) VALUES(?,?)", (r[0], loja_destino_id))

    # Tipos de despesa
    for r in c.execute("SELECT nome FROM tipos_despesa WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO tipos_despesa(nome, loja_id) VALUES(?,?)", (r[0], loja_destino_id))

    # Tipos de lançamento
    for r in c.execute("SELECT nome FROM tipos_lancamento WHERE loja_id=? AND ativo=1", (loja_origem_id,)).fetchall():
        c.execute("INSERT INTO tipos_lancamento(nome, loja_id) VALUES(?,?)", (r[0], loja_destino_id))

    # Configurações
    for r in c.execute("SELECT chave, valor FROM configuracoes WHERE loja_id=?", (loja_origem_id,)).fetchall():
        c.execute("INSERT OR IGNORE INTO configuracoes(chave, valor, loja_id) VALUES(?,?,?)", (r[0], r[1], loja_destino_id))

    conn.commit()
    conn.close()


# ──────────────────────────────────────────
#  HELPERS DE PERMISSÃO
# ──────────────────────────────────────────
def get_lojas_usuario(usuario_id, tipo_usuario):
    """Retorna lojas acessíveis pelo usuário com o perfil de cada uma."""
    conn = get_db()
    if tipo_usuario == "master":
        lojas = conn.execute("SELECT *, 'master' as perfil FROM lojas WHERE ativo=1 ORDER BY nome").fetchall()
    else:
        lojas = conn.execute("""
            SELECT l.*, ul.perfil FROM lojas l
            JOIN usuario_lojas ul ON ul.loja_id = l.id
            WHERE ul.usuario_id = ? AND l.ativo = 1
            ORDER BY l.nome
        """, (usuario_id,)).fetchall()
    conn.close()
    return lojas


def get_perfil_loja(usuario_id, loja_id, tipo_usuario):
    """Retorna o perfil do usuário em determinada loja."""
    if tipo_usuario == "master":
        return "master"
    conn = get_db()
    r = conn.execute(
        "SELECT perfil FROM usuario_lojas WHERE usuario_id=? AND loja_id=?",
        (usuario_id, loja_id),
    ).fetchone()
    conn.close()
    return r["perfil"] if r else None


def usuario_pode_mes(uid, loja_id, ano, mes):
    """Verifica se o usuário tipo loja tem permissão para lançar no mês."""
    conn = get_db()
    r = conn.execute(
        "SELECT 1 FROM permissoes_meses WHERE usuario_id=? AND loja_id=? AND ano=? AND mes=?",
        (uid, loja_id, ano, mes),
    ).fetchone()
    conn.close()
    return r is not None


def get_lojas_gestor(usuario_id):
    """Retorna IDs das lojas onde o usuário é gestor."""
    conn = get_db()
    rows = conn.execute(
        "SELECT loja_id FROM usuario_lojas WHERE usuario_id=? AND perfil='gestor'",
        (usuario_id,),
    ).fetchall()
    conn.close()
    return [r["loja_id"] for r in rows]


# ──────────────────────────────────────────
#  CONFIGURAÇÕES
# ──────────────────────────────────────────
def get_config(chave, loja_id=None, default="0"):
    conn = get_db()
    if loja_id:
        r = conn.execute(
            "SELECT valor FROM configuracoes WHERE chave=? AND loja_id=?",
            (chave, loja_id),
        ).fetchone()
        conn.close()
        return r["valor"] if r else default
    conn.close()
    return default


def set_config(chave, valor, loja_id=None):
    conn = get_db()
    if loja_id:
        conn.execute(
            "INSERT OR REPLACE INTO configuracoes(chave, valor, loja_id) VALUES(?,?,?)",
            (chave, valor, loja_id),
        )
    else:
        conn.execute(
            "INSERT OR REPLACE INTO configuracoes(chave, valor) VALUES(?,?)",
            (chave, valor),
        )
    conn.commit()
    conn.close()


# ──────────────────────────────────────────
#  IDENTIDADE VISUAL
# ──────────────────────────────────────────
def get_tema(loja_id):
    conn = get_db()
    l = conn.execute("SELECT * FROM lojas WHERE id=?", (loja_id,)).fetchone()
    conn.close()
    if not l:
        return {
            "cor_primaria": "#c8a96e", "cor_secundaria": "#3ecf8e",
            "cor_fundo": "#0d0f14", "cor_texto": "#e8eaf0",
            "tema": "escuro", "logo_path": "", "nome": "Sistema de DRE",
            "razao_social": "", "cnpj": "",
        }
    return {
        "cor_primaria": l["cor_primaria"] or "#c8a96e",
        "cor_secundaria": l["cor_secundaria"] or "#3ecf8e",
        "cor_fundo": l["cor_fundo"] or "#0d0f14",
        "cor_texto": l["cor_texto"] or "#e8eaf0",
        "tema": l["tema"] or "escuro",
        "logo_path": l["logo_path"] or "",
        "nome": l["nome"] or "Sistema de DRE",
        "razao_social": l["razao_social"] or "",
        "cnpj": l["cnpj"] or "",
    }


# ──────────────────────────────────────────
#  API KEYS
# ──────────────────────────────────────────
def gerar_api_key():
    return "snm_" + secrets.token_hex(24)


def validar_api_key(chave, permissao="read"):
    conn = get_db()
    r = conn.execute(
        "SELECT * FROM api_keys WHERE chave=? AND ativo=1", (chave,)
    ).fetchone()
    if r:
        conn.execute(
            "UPDATE api_keys SET ultimo_uso=CURRENT_TIMESTAMP WHERE id=?",
            (r["id"],),
        )
        conn.commit()
        perms = r["permissoes"].split(",") if r["permissoes"] else ["read"]
        conn.close()
        return r if permissao in perms else None
    conn.close()
    return None


# ──────────────────────────────────────────
#  CÁLCULO DRE
# ──────────────────────────────────────────
def calcular_dre(loja_id, ano, mes, marca_id=None):
    conn = get_db()
    ano_str = str(ano)
    mes_str = f"{mes:02d}"

    # Filtro de marca opcional
    filtro_marca_cx = ""
    filtro_marca_dp = ""
    params_extra_cx = []
    params_extra_dp = []
    if marca_id:
        filtro_marca_cx = " AND lc.marca_id = ?"
        filtro_marca_dp = " AND ld.marca_id = ?"
        params_extra_cx = [marca_id]
        params_extra_dp = [marca_id]

    # Faturamento por forma de pagamento (usa taxa_aplicada gravada no lançamento)
    rows_fp = conn.execute(f"""
        SELECT fp.nome, SUM(lc.valor) as total, SUM(lc.valor * lc.taxa_aplicada) as total_taxa
        FROM lancamentos_caixa lc
        JOIN formas_pagamento fp ON fp.id = lc.forma_pagamento_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ? AND strftime('%m', lc.data) = ?
        {filtro_marca_cx}
        GROUP BY fp.id, fp.nome
    """, (loja_id, ano_str, mes_str, *params_extra_cx)).fetchall()

    fat_bruto = {}
    total_bruto = 0.0
    total_taxas = 0.0
    for r in rows_fp:
        t = r["total"] or 0.0
        tv = r["total_taxa"] or 0.0
        fat_bruto[r["nome"]] = {"bruto": t, "taxa": tv, "liquido": t - tv}
        total_bruto += t
        total_taxas += tv

    # Faturamento por plataforma
    rows_plt = conn.execute(f"""
        SELECT p.nome,
          SUM(CASE WHEN lc.turno='almoco' THEN lc.valor ELSE 0 END) as almoco,
          SUM(CASE WHEN lc.turno='jantar' THEN lc.valor ELSE 0 END) as jantar,
          SUM(CASE WHEN lc.turno='pos_meia_noite' THEN lc.valor ELSE 0 END) as pos,
          SUM(lc.valor) as total
        FROM lancamentos_caixa lc
        JOIN plataformas p ON p.id = lc.plataforma_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ? AND strftime('%m', lc.data) = ?
        {filtro_marca_cx}
        GROUP BY p.id, p.nome
    """, (loja_id, ano_str, mes_str, *params_extra_cx)).fetchall()

    fat_app = {}
    for r in rows_plt:
        fat_app[r["nome"]] = {
            "almoco": r["almoco"] or 0,
            "jantar": r["jantar"] or 0,
            "pos": r["pos"] or 0,
            "total": r["total"] or 0,
        }

    # Despesas por categoria
    rows_desp = conn.execute(f"""
        SELECT cd.nome, cd.tipo, SUM(ld.valor) as total
        FROM lancamentos_despesa ld
        JOIN categorias_despesa cd ON cd.id = ld.categoria_id
        WHERE ld.loja_id = ? AND strftime('%Y', ld.data) = ? AND strftime('%m', ld.data) = ?
        {filtro_marca_dp}
        GROUP BY cd.id, cd.nome, cd.tipo
    """, (loja_id, ano_str, mes_str, *params_extra_dp)).fetchall()

    despesas = {"cmv": {}, "fixa": {}, "motoboy": {}, "balcao": {}, "financeira": {}, "outra": {}}
    totais_desp = {k: 0.0 for k in despesas}
    for r in rows_desp:
        despesas[r["tipo"]][r["nome"]] = r["total"] or 0
        totais_desp[r["tipo"]] += r["total"] or 0

    royalties = float(get_config("royalties", loja_id, "0"))
    mkt = float(get_config("verba_marketing", loja_id, "0"))
    total_despesas = sum(totais_desp.values())
    resultado = total_bruto - total_taxas - total_despesas - royalties - mkt

    # Faturamento por marca (sempre sem filtro de marca para comparativo)
    rows_marca = conn.execute("""
        SELECT COALESCE(m.nome, 'Sem marca') as marca_nome, COALESCE(m.id, 0) as marca_id,
          SUM(lc.valor) as total, SUM(lc.valor * lc.taxa_aplicada) as total_taxa
        FROM lancamentos_caixa lc
        LEFT JOIN marcas m ON m.id = lc.marca_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ? AND strftime('%m', lc.data) = ?
        GROUP BY COALESCE(m.nome, 'Sem marca'), COALESCE(m.id, 0)
    """, (loja_id, ano_str, mes_str)).fetchall()

    fat_marca = {}
    for r in rows_marca:
        fat_marca[r["marca_nome"]] = {
            "id": r["marca_id"],
            "bruto": r["total"] or 0,
            "taxa": r["total_taxa"] or 0,
            "liquido": (r["total"] or 0) - (r["total_taxa"] or 0),
        }

    # Despesas por marca (sempre sem filtro de marca para comparativo)
    rows_desp_marca = conn.execute("""
        SELECT COALESCE(m.nome, 'Sem marca') as marca_nome, SUM(ld.valor) as total
        FROM lancamentos_despesa ld
        LEFT JOIN marcas m ON m.id = ld.marca_id
        WHERE ld.loja_id = ? AND strftime('%Y', ld.data) = ? AND strftime('%m', ld.data) = ?
        GROUP BY COALESCE(m.nome, 'Sem marca')
    """, (loja_id, ano_str, mes_str)).fetchall()

    desp_marca = {}
    for r in rows_desp_marca:
        desp_marca[r["marca_nome"]] = r["total"] or 0

    dias = conn.execute(f"""
        SELECT COUNT(DISTINCT date(data)) FROM lancamentos_caixa
        WHERE loja_id = ? AND strftime('%Y', data) = ? AND strftime('%m', data) = ?
        {filtro_marca_cx}
    """, (loja_id, ano_str, mes_str, *params_extra_cx)).fetchone()[0] or 1
    conn.close()

    return {
        "fat_bruto": fat_bruto,
        "total_bruto": total_bruto,
        "total_taxas": total_taxas,
        "fat_liquido": total_bruto - total_taxas,
        "fat_app": fat_app,
        "despesas": despesas,
        "totais_desp": totais_desp,
        "total_despesas": total_despesas,
        "royalties": royalties,
        "mkt": mkt,
        "resultado": resultado,
        "margem": (resultado / total_bruto * 100) if total_bruto else 0,
        "media_diaria": total_bruto / dias,
        "dias_lancados": dias,
        "fat_marca": fat_marca,
        "desp_marca": desp_marca,
    }


def resumo_anual(loja_id, ano, marca_id=None):
    dados = []
    fat_marca_anual = {}   # {marca_nome: {bruto, taxa, liquido}}
    desp_marca_anual = {}  # {marca_nome: total}
    for mes in range(1, 13):
        dre = calcular_dre(loja_id, ano, mes, marca_id=marca_id)
        dados.append({
            "mes": mes,
            "nome_mes": MESES[mes - 1],
            "faturamento": dre["total_bruto"],
            "despesas": dre["total_despesas"],
            "royalties": dre["royalties"],
            "mkt": dre["mkt"],
            "resultado": dre["resultado"],
            "margem": dre["margem"],
        })
        # Acumula faturamento por marca
        for nome, vals in dre["fat_marca"].items():
            if nome not in fat_marca_anual:
                fat_marca_anual[nome] = {"bruto": 0, "taxa": 0, "liquido": 0}
            fat_marca_anual[nome]["bruto"] += vals["bruto"]
            fat_marca_anual[nome]["taxa"] += vals["taxa"]
            fat_marca_anual[nome]["liquido"] += vals["liquido"]
        # Acumula despesas por marca
        for nome, val in dre["desp_marca"].items():
            desp_marca_anual[nome] = desp_marca_anual.get(nome, 0) + val
    return {
        "meses": dados,
        "fat_marca_anual": fat_marca_anual,
        "desp_marca_anual": desp_marca_anual,
    }


def comparativo_marcas(loja_id, ano, mes):
    """Retorna comparativo de faturamento por marca: mês atual vs anterior, com variação %."""
    conn = get_db()
    ano_str = str(ano)
    mes_str = f"{mes:02d}"

    # Mês anterior
    if mes == 1:
        mes_ant = 12
        ano_ant = ano - 1
    else:
        mes_ant = mes - 1
        ano_ant = ano
    ano_ant_str = str(ano_ant)
    mes_ant_str = f"{mes_ant:02d}"

    # Faturamento atual por marca
    rows_atual = conn.execute("""
        SELECT COALESCE(m.nome, 'Sem marca') as marca_nome, COALESCE(m.id, 0) as marca_id,
          SUM(lc.valor) as total
        FROM lancamentos_caixa lc
        LEFT JOIN marcas m ON m.id = lc.marca_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ? AND strftime('%m', lc.data) = ?
        GROUP BY COALESCE(m.nome, 'Sem marca'), COALESCE(m.id, 0)
    """, (loja_id, ano_str, mes_str)).fetchall()

    # Faturamento anterior por marca
    rows_ant = conn.execute("""
        SELECT COALESCE(m.nome, 'Sem marca') as marca_nome,
          SUM(lc.valor) as total
        FROM lancamentos_caixa lc
        LEFT JOIN marcas m ON m.id = lc.marca_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ? AND strftime('%m', lc.data) = ?
        GROUP BY COALESCE(m.nome, 'Sem marca')
    """, (loja_id, ano_ant_str, mes_ant_str)).fetchall()
    conn.close()

    ant_dict = {r["marca_nome"]: (r["total"] or 0) for r in rows_ant}

    resultado = []
    melhor_marca = None
    melhor_fat = 0
    for r in rows_atual:
        fat_atual = r["total"] or 0
        fat_ant = ant_dict.get(r["marca_nome"], 0)
        variacao = ((fat_atual - fat_ant) / fat_ant * 100) if fat_ant > 0 else (100.0 if fat_atual > 0 else 0)
        item = {
            "marca": r["marca_nome"],
            "marca_id": r["marca_id"],
            "fat_atual": fat_atual,
            "fat_anterior": fat_ant,
            "variacao": round(variacao, 1),
        }
        resultado.append(item)
        if fat_atual > melhor_fat:
            melhor_fat = fat_atual
            melhor_marca = r["marca_nome"]

    # Adiciona marcas que só existem no mês anterior
    for nome, val in ant_dict.items():
        if nome not in [r["marca"] for r in resultado]:
            resultado.append({
                "marca": nome,
                "marca_id": 0,
                "fat_atual": 0,
                "fat_anterior": val,
                "variacao": -100.0,
            })

    return {
        "comparativo": sorted(resultado, key=lambda x: x["fat_atual"], reverse=True),
        "melhor_marca": melhor_marca,
        "melhor_fat": melhor_fat,
        "mes_anterior": MESES[mes_ant - 1],
    }


def resumo_todos_anos(loja_id):
    resultado = []
    for ano in ANOS:
        resumo = resumo_anual(loja_id, ano)
        dados = resumo["meses"]
        fat = sum(m["faturamento"] for m in dados)
        res = sum(m["resultado"] for m in dados)
        desp = sum(m["despesas"] for m in dados)
        resultado.append({
            "ano": ano,
            "faturamento": fat,
            "resultado": res,
            "despesas": desp,
            "margem": (res / fat * 100) if fat else 0,
        })
    return resultado


# ──────────────────────────────────────────
#  BANCO DE TALENTOS
# ──────────────────────────────────────────
def get_talentos_notas(banco):
    """Retorna dict de notas por email do candidato."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM talentos_notas WHERE banco=?", (banco,)
    ).fetchall()
    conn.close()
    return {r["candidato_email"]: dict(r) for r in rows}


def salvar_talento_nota(banco, email, ex_funcionario, contratou, observacao, usuario_id):
    """Insere ou atualiza nota de um candidato."""
    conn = get_db()
    conn.execute("""
        INSERT INTO talentos_notas(banco, candidato_email, ex_funcionario, contratou, observacao, atualizado_por, atualizado_em)
        VALUES(?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(banco, candidato_email) DO UPDATE SET
            ex_funcionario=excluded.ex_funcionario,
            contratou=excluded.contratou,
            observacao=excluded.observacao,
            atualizado_por=excluded.atualizado_por,
            atualizado_em=CURRENT_TIMESTAMP
    """, (banco, email, ex_funcionario, contratou, observacao, usuario_id))
    conn.commit()
    conn.close()


def get_acesso_talentos(usuario_id, tipo_usuario):
    """Retorna dict com permissões de acesso ao banco de talentos."""
    if tipo_usuario == "master":
        return {"sunomono": True, "monopizza": True, "grupomono": True}
    conn = get_db()
    r = conn.execute(
        "SELECT acesso_talentos_sunomono, acesso_talentos_monopizza, acesso_talentos_grupomono FROM usuarios WHERE id=?",
        (usuario_id,),
    ).fetchone()
    conn.close()
    if not r:
        return {"sunomono": False, "monopizza": False, "grupomono": False}
    return {
        "sunomono": bool(r["acesso_talentos_sunomono"]),
        "monopizza": bool(r["acesso_talentos_monopizza"]),
        "grupomono": bool(r["acesso_talentos_grupomono"]),
    }
