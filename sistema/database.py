"""
database.py – Sistema de DRE
Banco SQLite com suporte a multilojas, permissões por loja e 4 níveis de usuário.
"""
import sqlite3
import os
import secrets
from datetime import datetime, timezone, timedelta
from werkzeug.security import generate_password_hash

DB_PATH = os.environ.get(
    "DB_PATH", os.path.join(os.path.dirname(__file__), "data", "sunomono.db")
)
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

ANO_INICIO = 2026
_ano_atual = datetime.now(timezone(timedelta(hours=-3))).year
ANO_FIM = max(_ano_atual + 5, 2031)
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
        cor_primaria    TEXT DEFAULT '#3d8f60',
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
            banco           TEXT NOT NULL,
            candidato_email TEXT NOT NULL,
            ex_funcionario  INTEGER DEFAULT 0,
            contratou       INTEGER DEFAULT 0,
            observacao      TEXT DEFAULT '',
            atualizado_por  INTEGER REFERENCES usuarios(id),
            atualizado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(banco, candidato_email)
        )""")
    else:
        # Remove CHECK constraint para suportar bancos dinâmicos
        tbl_sql = c.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='talentos_notas'").fetchone()
        if tbl_sql and "CHECK" in tbl_sql[0]:
            c.execute("ALTER TABLE talentos_notas RENAME TO _talentos_notas_old")
            c.execute("""
            CREATE TABLE talentos_notas (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                banco           TEXT NOT NULL,
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

    # Adiciona colunas de acesso ao Banco de Talentos nos usuários (legado)
    cols_usr = [r[1] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "acesso_talentos_sunomono" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_talentos_sunomono INTEGER DEFAULT 0")
    if "acesso_talentos_monopizza" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_talentos_monopizza INTEGER DEFAULT 0")
    if "acesso_talentos_grupomono" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_talentos_grupomono INTEGER DEFAULT 0")

    # ── Novas colunas de controle de acesso por sistema ──
    if "acesso_dre" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_dre INTEGER DEFAULT 1")
        c.execute("UPDATE usuarios SET acesso_dre=1")
    if "acesso_banco_talentos" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN acesso_banco_talentos INTEGER DEFAULT 0")
        c.execute("""UPDATE usuarios SET acesso_banco_talentos=1
                     WHERE acesso_talentos_sunomono=1 OR acesso_talentos_monopizza=1 OR acesso_talentos_grupomono=1""")

    # ── bancos_talentos (configurável) ──
    if "bancos_talentos" not in tabelas:
        c.execute("""
        CREATE TABLE bancos_talentos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            nome        TEXT NOT NULL,
            slug        TEXT NOT NULL UNIQUE,
            fonte_url   TEXT DEFAULT '',
            ultimo_sync TIMESTAMP,
            ativo       INTEGER DEFAULT 1,
            criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.executemany(
            "INSERT OR IGNORE INTO bancos_talentos(nome, slug, fonte_url) VALUES(?,?,?)",
            [
                ("Sunomono", "sunomono",
                 "https://docs.google.com/spreadsheets/d/18DlMtVIvDzQPvRAx9mASWttpJL4ib4bW36m8xqEc-10/gviz/tq?tqx=out:csv&gid=1788712909"),
                ("Mono Pizza", "monopizza",
                 "https://docs.google.com/spreadsheets/d/1pTNKN6NFGmaHJi8b9klpgbigBOnyLU9SKbc11tqbERo/gviz/tq?tqx=out:csv&gid=0"),
                ("Grupo Mono", "grupomono", ""),
            ]
        )

    # ── usuario_bancos_talentos ──
    if "usuario_bancos_talentos" not in tabelas:
        c.execute("""
        CREATE TABLE usuario_bancos_talentos (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id  INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            banco_id    INTEGER NOT NULL REFERENCES bancos_talentos(id) ON DELETE CASCADE,
            UNIQUE(usuario_id, banco_id)
        )""")
        # Migra permissões das colunas legadas
        bancos_mapa = {}
        for b in c.execute("SELECT id, slug FROM bancos_talentos").fetchall():
            bancos_mapa[b["slug"]] = b["id"]
        mig_cols = [
            ("sunomono", "acesso_talentos_sunomono"),
            ("monopizza", "acesso_talentos_monopizza"),
            ("grupomono", "acesso_talentos_grupomono"),
        ]
        for u2 in c.execute("SELECT id, acesso_talentos_sunomono, acesso_talentos_monopizza, acesso_talentos_grupomono FROM usuarios").fetchall():
            for slug, col in mig_cols:
                if u2[col] and slug in bancos_mapa:
                    c.execute(
                        "INSERT OR IGNORE INTO usuario_bancos_talentos(usuario_id, banco_id) VALUES(?,?)",
                        (u2["id"], bancos_mapa[slug])
                    )

    # grupo_id em bancos_talentos
    cols_bt = [r[1] for r in c.execute("PRAGMA table_info(bancos_talentos)").fetchall()]
    if cols_bt and "grupo_id" not in cols_bt:
        c.execute("ALTER TABLE bancos_talentos ADD COLUMN grupo_id INTEGER DEFAULT 1")
        c.execute("UPDATE bancos_talentos SET grupo_id=1")

    # Coluna de último acesso
    if "ultimo_acesso" not in cols_usr:
        c.execute("ALTER TABLE usuarios ADD COLUMN ultimo_acesso TIMESTAMP")

    # ── Tabela config_mensal (Royalties e Marketing por mês) ──
    if "config_mensal" not in tabelas:
        c.execute("""
        CREATE TABLE config_mensal (
            id      INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_id INTEGER NOT NULL REFERENCES lojas(id),
            ano     INTEGER NOT NULL,
            mes     INTEGER NOT NULL,
            chave   TEXT NOT NULL,
            valor   REAL DEFAULT 0,
            UNIQUE(loja_id, ano, mes, chave)
        )""")

    # ── Tabela abertura_caixa ──
    if "abertura_caixa" not in tabelas:
        c.execute("""
        CREATE TABLE abertura_caixa (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            loja_id    INTEGER NOT NULL REFERENCES lojas(id),
            data       DATE NOT NULL,
            turno      TEXT NOT NULL CHECK(turno IN ('almoco','jantar','pos_meia_noite')),
            valor      REAL DEFAULT 0,
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id),
            criado_em  TIMESTAMP,
            UNIQUE(loja_id, data, turno)
        )""")

    # ── Tabela chat_sugestoes (Sugestões do Chat de Suporte) ──
    if "chat_sugestoes" not in tabelas:
        c.execute("""
        CREATE TABLE chat_sugestoes (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id   INTEGER REFERENCES usuarios(id),
            nome_usuario TEXT DEFAULT '',
            sugestao     TEXT NOT NULL,
            lida         INTEGER DEFAULT 0,
            criado_em    TIMESTAMP
        )""")

    # Adiciona colunas de avaliação nas sugestões
    cols_sug = [r[1] for r in c.execute("PRAGMA table_info(chat_sugestoes)").fetchall()]
    if "estrelas" not in cols_sug:
        c.execute("ALTER TABLE chat_sugestoes ADD COLUMN estrelas INTEGER DEFAULT 0")
    if "tipo" not in cols_sug:
        c.execute("ALTER TABLE chat_sugestoes ADD COLUMN tipo TEXT DEFAULT 'sugestao'")

    # ── Tabela chat_historico (Histórico do Chat de Suporte) ──
    if "chat_historico" not in tabelas:
        c.execute("""
        CREATE TABLE chat_historico (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            usuario_id INTEGER REFERENCES usuarios(id),
            role       TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content    TEXT NOT NULL,
            criado_em  TIMESTAMP
        )""")

    # ── grupos (multi-tenant: cada grupo é um cliente SaaS) ──
    if "grupos" not in tabelas:
        c.execute("""
        CREATE TABLE grupos (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            slug      TEXT NOT NULL UNIQUE,
            plano_id  INTEGER DEFAULT NULL,
            ativo     INTEGER DEFAULT 1,
            criado_em TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.execute("INSERT INTO grupos(id,nome,slug) VALUES(1,'UNYRAX','unyrax')")

    # ── temas_grupo (identidade visual por grupo) ──
    if "temas_grupo" not in tabelas:
        c.execute("""
        CREATE TABLE temas_grupo (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id        INTEGER NOT NULL UNIQUE REFERENCES grupos(id) ON DELETE CASCADE,
            nome_exibicao   TEXT DEFAULT '',
            cor_primaria    TEXT DEFAULT '#3d8f60',
            cor_secundaria  TEXT DEFAULT '#1e5235',
            bg_login_url    TEXT DEFAULT '',
            logo_url        TEXT DEFAULT ''
        )""")
        c.execute("""INSERT INTO temas_grupo(grupo_id,cor_primaria,cor_secundaria)
                     VALUES(1,'#3d7a50','#1c3a28')""")

    # Atualiza grupo padrão para UNYRAX se ainda tiver nome antigo
    c.execute("UPDATE grupos SET nome='UNYRAX', slug='unyrax' WHERE id=1 AND (nome='Grupo Mono' OR slug='grupomono')")
    c.execute("UPDATE temas_grupo SET nome_exibicao='UNYRAX' WHERE grupo_id=1 AND (nome_exibicao='' OR nome_exibicao='Grupo Mono')")

    # Adiciona grupo_id em lojas
    cols_lojas = [r[1] for r in c.execute("PRAGMA table_info(lojas)").fetchall()]
    if "grupo_id" not in cols_lojas:
        c.execute("ALTER TABLE lojas ADD COLUMN grupo_id INTEGER DEFAULT 1")
        c.execute("UPDATE lojas SET grupo_id=1 WHERE grupo_id IS NULL")

    # Adiciona grupo_id e nivel em usuarios
    cols_usr_g = [r[1] for r in c.execute("PRAGMA table_info(usuarios)").fetchall()]
    if "grupo_id" not in cols_usr_g:
        c.execute("ALTER TABLE usuarios ADD COLUMN grupo_id INTEGER DEFAULT 1")
        c.execute("UPDATE usuarios SET grupo_id=1 WHERE grupo_id IS NULL")
    if "nivel" not in cols_usr_g:
        c.execute("ALTER TABLE usuarios ADD COLUMN nivel TEXT DEFAULT 'leitor'")
        c.execute("""UPDATE usuarios SET nivel = CASE tipo
            WHEN 'master'  THEN 'master'
            WHEN 'gestor'  THEN 'gestor'
            WHEN 'loja'    THEN 'loja'
            ELSE 'leitor' END""")

    # ── modulos_sistema (módulos configuráveis do sistema) ──
    if "modulos_sistema" not in tabelas:
        c.execute("""
        CREATE TABLE modulos_sistema (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            nome      TEXT NOT NULL,
            slug      TEXT NOT NULL UNIQUE,
            descricao TEXT DEFAULT '',
            icone     TEXT DEFAULT 'bi-puzzle',
            ativo     INTEGER DEFAULT 1,
            ordem     INTEGER DEFAULT 0
        )""")
        c.execute("INSERT OR IGNORE INTO modulos_sistema(nome,slug,descricao,icone,ordem) VALUES('DRE','dre','Gestão financeira e lançamentos','bi-bar-chart-line',1)")

    # ── usuario_modulos (módulos liberados por usuário) ──
    if "usuario_modulos" not in tabelas:
        c.execute("""
        CREATE TABLE usuario_modulos (
            usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
            modulo_id  INTEGER NOT NULL REFERENCES modulos_sistema(id) ON DELETE CASCADE,
            PRIMARY KEY (usuario_id, modulo_id)
        )""")
        dre_row = c.execute("SELECT id FROM modulos_sistema WHERE slug='dre'").fetchone()
        if dre_row:
            c.execute(
                "INSERT OR IGNORE INTO usuario_modulos(usuario_id,modulo_id) SELECT id,? FROM usuarios WHERE acesso_dre=1",
                (dre_row[0],)
            )

    # ── Módulo Chamados ──

    if "chamados_setores" not in tabelas:
        c.execute("""
        CREATE TABLE chamados_setores (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id        INTEGER DEFAULT 1,
            nome            TEXT NOT NULL,
            cor             TEXT DEFAULT '#3d7a50',
            responsavel_id  INTEGER,
            pode_abrir      INTEGER DEFAULT 1,
            pode_receber    INTEGER DEFAULT 1,
            ativo           INTEGER DEFAULT 1,
            criado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

    if "chamados_etiquetas" not in tabelas:
        c.execute("""
        CREATE TABLE chamados_etiquetas (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id    INTEGER DEFAULT 1,
            nome        TEXT NOT NULL,
            cor         TEXT DEFAULT '#5b8dee',
            ativo       INTEGER DEFAULT 1,
            criado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

    if "chamados_sla" not in tabelas:
        c.execute("""
        CREATE TABLE chamados_sla (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id            INTEGER DEFAULT 1,
            nome                TEXT NOT NULL,
            prioridade          TEXT DEFAULT 'media',
            horas_resposta      REAL DEFAULT 4,
            horas_resolucao     REAL DEFAULT 24,
            dias_semana         TEXT DEFAULT '1,2,3,4,5',
            hora_inicio         TEXT DEFAULT '08:00',
            hora_fim            TEXT DEFAULT '18:00',
            ativo               INTEGER DEFAULT 1,
            criado_em           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
        c.executemany(
            "INSERT INTO chamados_sla(grupo_id,nome,prioridade,horas_resposta,horas_resolucao) VALUES(1,?,?,?,?)",
            [("Urgente — 1h/4h","urgente",1,4),
             ("Alta — 2h/8h","alta",2,8),
             ("Média — 4h/24h","media",4,24),
             ("Baixa — 8h/72h","baixa",8,72)]
        )

    if "chamados" not in tabelas:
        c.execute("""
        CREATE TABLE chamados (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            numero              TEXT NOT NULL UNIQUE,
            grupo_id            INTEGER DEFAULT 1,
            loja_id             INTEGER,
            titulo              TEXT NOT NULL,
            descricao           TEXT DEFAULT '',
            status              TEXT DEFAULT 'aberto',
            prioridade          TEXT DEFAULT 'media',
            categoria           TEXT DEFAULT 'suporte',
            setor_id            INTEGER,
            solicitante_id      INTEGER,
            solicitante_nome    TEXT DEFAULT '',
            solicitante_email   TEXT DEFAULT '',
            solicitante_tel     TEXT DEFAULT '',
            responsavel_id      INTEGER,
            prazo               DATE,
            prazo_sla           TIMESTAMP,
            criado_em           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            atualizado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            fechado_em          TIMESTAMP
        )""")

    if "chamados_comentarios" not in tabelas:
        c.execute("""
        CREATE TABLE chamados_comentarios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chamado_id      INTEGER NOT NULL REFERENCES chamados(id) ON DELETE CASCADE,
            usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
            usuario_nome    TEXT DEFAULT '',
            texto           TEXT NOT NULL,
            tipo            TEXT DEFAULT 'comentario',
            criado_em       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

    if "chamado_etiqueta" not in tabelas:
        c.execute("""
        CREATE TABLE chamado_etiqueta (
            chamado_id  INTEGER NOT NULL REFERENCES chamados(id) ON DELETE CASCADE,
            etiqueta_id INTEGER NOT NULL REFERENCES chamados_etiquetas(id) ON DELETE CASCADE,
            PRIMARY KEY (chamado_id, etiqueta_id)
        )""")

    if "chamado_apoios" not in tabelas:
        c.execute("""
        CREATE TABLE chamado_apoios (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chamado_id      INTEGER NOT NULL REFERENCES chamados(id) ON DELETE CASCADE,
            usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
            usuario_nome    TEXT DEFAULT '',
            adicionado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chamado_id, usuario_id)
        )""")

    if "chamado_acompanhantes" not in tabelas:
        c.execute("""
        CREATE TABLE chamado_acompanhantes (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            chamado_id      INTEGER NOT NULL REFERENCES chamados(id) ON DELETE CASCADE,
            usuario_id      INTEGER NOT NULL REFERENCES usuarios(id),
            usuario_nome    TEXT DEFAULT '',
            adicionado_em   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(chamado_id, usuario_id)
        )""")

    # Migration: setor_id e prazo_sla em chamados existentes
    cols_ch = [r[1] for r in c.execute("PRAGMA table_info(chamados)").fetchall()]
    if cols_ch and "setor_id" not in cols_ch:
        c.execute("ALTER TABLE chamados ADD COLUMN setor_id INTEGER")
    if cols_ch and "prazo_sla" not in cols_ch:
        c.execute("ALTER TABLE chamados ADD COLUMN prazo_sla TIMESTAMP")

    # Seed módulo Chamados
    c.execute("""INSERT OR IGNORE INTO modulos_sistema(nome,slug,descricao,icone,ordem)
                 VALUES('Chamados','chamados','Abertura e acompanhamento de chamados de suporte','bi-headset',3)""")

    # ── planos (SaaS comercial) ──
    if "planos" not in tabelas:
        c.execute("""
        CREATE TABLE planos (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            nome         TEXT NOT NULL,
            descricao    TEXT DEFAULT '',
            preco_mensal REAL DEFAULT 0,
            ativo        INTEGER DEFAULT 1
        )""")
        c.execute("INSERT INTO planos(nome,descricao,preco_mensal) VALUES('Essencial','Módulos básicos',0)")
        c.execute("INSERT INTO planos(nome,descricao,preco_mensal) VALUES('Profissional','Todos os módulos',0)")

    if "planos_modulos" not in tabelas:
        c.execute("""
        CREATE TABLE planos_modulos (
            plano_id  INTEGER NOT NULL REFERENCES planos(id) ON DELETE CASCADE,
            modulo_id INTEGER NOT NULL REFERENCES modulos_sistema(id) ON DELETE CASCADE,
            PRIMARY KEY (plano_id, modulo_id)
        )""")

    if "subscriptions" not in tabelas:
        c.execute("""
        CREATE TABLE subscriptions (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            grupo_id  INTEGER NOT NULL REFERENCES grupos(id) ON DELETE CASCADE,
            plano_id  INTEGER NOT NULL REFERENCES planos(id),
            valido_ate DATE,
            status    TEXT DEFAULT 'ativo'
        )""")

    # ── ÍNDICES PARA PERFORMANCE ──
    c.executescript("""
    CREATE INDEX IF NOT EXISTS idx_lc_loja_data ON lancamentos_caixa(loja_id, data);
    CREATE INDEX IF NOT EXISTS idx_lc_loja_marca ON lancamentos_caixa(loja_id, marca_id);
    CREATE INDEX IF NOT EXISTS idx_lc_loja_data_fp ON lancamentos_caixa(loja_id, data, forma_pagamento_id);
    CREATE INDEX IF NOT EXISTS idx_lc_loja_data_plat ON lancamentos_caixa(loja_id, data, plataforma_id);
    CREATE INDEX IF NOT EXISTS idx_ld_loja_data ON lancamentos_despesa(loja_id, data);
    CREATE INDEX IF NOT EXISTS idx_ld_loja_marca ON lancamentos_despesa(loja_id, marca_id);
    CREATE INDEX IF NOT EXISTS idx_ld_loja_data_cat ON lancamentos_despesa(loja_id, data, categoria_id);
    CREATE INDEX IF NOT EXISTS idx_as_loja_data ON aporte_sangria(loja_id, data);
    CREATE INDEX IF NOT EXISTS idx_config_chave_loja ON configuracoes(chave, loja_id);
    CREATE INDEX IF NOT EXISTS idx_configm_loja_ano_mes ON config_mensal(loja_id, ano, mes, chave);
    CREATE INDEX IF NOT EXISTS idx_fp_loja ON formas_pagamento(loja_id, ativo);
    CREATE INDEX IF NOT EXISTS idx_plat_loja ON plataformas(loja_id, ativo);
    CREATE INDEX IF NOT EXISTS idx_cat_loja ON categorias_despesa(loja_id, ativo);
    CREATE INDEX IF NOT EXISTS idx_marcas_loja ON marcas(loja_id, ativo);
    CREATE INDEX IF NOT EXISTS idx_usuarios_login ON usuarios(login, ativo);
    CREATE INDEX IF NOT EXISTS idx_abertura_loja_data ON abertura_caixa(loja_id, data, turno);
    """)

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


def get_config_mensal(loja_id, ano, chave):
    """Retorna dict {mes: valor} para uma chave (royalties/verba_marketing) em um ano."""
    conn = get_db()
    rows = conn.execute(
        "SELECT mes, valor FROM config_mensal WHERE loja_id=? AND ano=? AND chave=?",
        (loja_id, ano, chave),
    ).fetchall()
    conn.close()
    return {r["mes"]: r["valor"] for r in rows}


def get_config_mensal_valor(loja_id, ano, mes, chave, default=0.0):
    """Retorna o valor de uma chave para um mês/ano específico. Fallback para config fixa."""
    conn = get_db()
    r = conn.execute(
        "SELECT valor FROM config_mensal WHERE loja_id=? AND ano=? AND mes=? AND chave=?",
        (loja_id, ano, mes, chave),
    ).fetchone()
    conn.close()
    if r is not None:
        return r["valor"]
    # Fallback: valor fixo antigo da tabela configuracoes
    return float(get_config(chave, loja_id, str(default)))


def set_config_mensal(loja_id, ano, mes, chave, valor):
    """Define valor mensal para uma chave."""
    conn = get_db()
    conn.execute("""
        INSERT INTO config_mensal(loja_id, ano, mes, chave, valor)
        VALUES(?, ?, ?, ?, ?)
        ON CONFLICT(loja_id, ano, mes, chave) DO UPDATE SET valor=excluded.valor
    """, (loja_id, ano, mes, chave, valor))
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
            "cor_primaria": "#3d8f60", "cor_secundaria": "#3ecf8e",
            "cor_fundo": "#0d0f14", "cor_texto": "#e8eaf0",
            "tema": "escuro", "logo_path": "", "nome": "Sistema de DRE",
            "razao_social": "", "cnpj": "",
        }
    return {
        "cor_primaria": l["cor_primaria"] or "#3d8f60",
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

    royalties = get_config_mensal_valor(loja_id, int(ano_str), int(mes_str), "royalties", 0.0)
    mkt = get_config_mensal_valor(loja_id, int(ano_str), int(mes_str), "verba_marketing", 0.0)
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
    marcas_existentes = {r["marca"] for r in resultado}
    for nome, val in ant_dict.items():
        if nome not in marcas_existentes:
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


_cache_todos_anos = {}  # {loja_id: {"ts": timestamp, "data": [...]}}
_CACHE_TODOS_ANOS_TTL = 300  # 5 minutos

def resumo_todos_anos(loja_id):
    import time as _time
    agora = _time.time()
    cached = _cache_todos_anos.get(loja_id)
    if cached and (agora - cached["ts"]) < _CACHE_TODOS_ANOS_TTL:
        return cached["data"]

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
    _cache_todos_anos[loja_id] = {"ts": agora, "data": resultado}
    return resultado


# ──────────────────────────────────────────
#  BANCO DE TALENTOS
# ──────────────────────────────────────────
def get_talentos_notas(banco):
    """Retorna dict de notas por email do candidato, com nome de quem atualizou."""
    conn = get_db()
    rows = conn.execute(
        """SELECT t.*, u.nome AS atualizado_por_nome
           FROM talentos_notas t
           LEFT JOIN usuarios u ON u.id = t.atualizado_por
           WHERE t.banco=?""", (banco,)
    ).fetchall()
    conn.close()
    return {r["candidato_email"]: dict(r) for r in rows}


def salvar_talento_nota(banco, email, ex_funcionario, contratou, observacao, usuario_id):
    """Insere ou atualiza nota de um candidato."""
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute("""
        INSERT INTO talentos_notas(banco, candidato_email, ex_funcionario, contratou, observacao, atualizado_por, atualizado_em)
        VALUES(?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(banco, candidato_email) DO UPDATE SET
            ex_funcionario=excluded.ex_funcionario,
            contratou=excluded.contratou,
            observacao=excluded.observacao,
            atualizado_por=excluded.atualizado_por,
            atualizado_em=excluded.atualizado_em
    """, (banco, email, ex_funcionario, contratou, observacao, usuario_id, agora))
    conn.commit()
    conn.close()


def get_bancos_talentos(apenas_ativos=True, grupo_id=None):
    """Retorna lista de bancos de talentos, opcionalmente filtrada por grupo."""
    conn = get_db()
    filtros = []
    params = []
    if apenas_ativos:
        filtros.append("bt.ativo=1")
    if grupo_id is not None:
        filtros.append("bt.grupo_id=?")
        params.append(grupo_id)
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    rows = conn.execute(
        f"SELECT bt.*, g.nome as grupo_nome FROM bancos_talentos bt "
        f"LEFT JOIN grupos g ON g.id=bt.grupo_id {where} ORDER BY bt.nome",
        params
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_bancos_usuario(usuario_id, tipo_usuario):
    """Retorna lista de bancos acessíveis ao usuário.
    Masters sem atribuições explícitas recebem acesso a tudo (master original).
    Masters com atribuições explícitas ficam limitados a elas (sub-masters criados via UI)."""
    conn = get_db()
    explicitas = conn.execute(
        "SELECT banco_id FROM usuario_bancos_talentos WHERE usuario_id=?", (usuario_id,)
    ).fetchall()
    if tipo_usuario == "master" and not explicitas:
        conn.close()
        return get_bancos_talentos()
    rows = conn.execute("""
        SELECT bt.* FROM bancos_talentos bt
        JOIN usuario_bancos_talentos ubt ON ubt.banco_id = bt.id
        WHERE ubt.usuario_id = ? AND bt.ativo = 1
        ORDER BY bt.nome
    """, (usuario_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_banco_by_slug(slug):
    """Retorna dados de um banco pelo slug."""
    conn = get_db()
    row = conn.execute("SELECT * FROM bancos_talentos WHERE slug=? AND ativo=1", (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def salvar_banco_talentos(nome, slug, fonte_url, banco_id=None, grupo_id=1):
    """Cria ou atualiza um banco de talentos."""
    conn = get_db()
    if banco_id:
        conn.execute(
            "UPDATE bancos_talentos SET nome=?, slug=?, fonte_url=?, grupo_id=? WHERE id=?",
            (nome, slug, fonte_url, int(grupo_id), int(banco_id))
        )
    else:
        conn.execute(
            "INSERT INTO bancos_talentos(nome, slug, fonte_url, grupo_id) VALUES(?,?,?,?)",
            (nome, slug, fonte_url, int(grupo_id))
        )
    conn.commit()
    conn.close()


def excluir_banco_talentos(banco_id):
    """Desativa um banco de talentos (soft delete)."""
    conn = get_db()
    conn.execute("UPDATE bancos_talentos SET ativo=0 WHERE id=?", (banco_id,))
    conn.commit()
    conn.close()


def set_banco_sync(banco_id):
    """Atualiza o timestamp de último sync."""
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute("UPDATE bancos_talentos SET ultimo_sync=? WHERE id=?", (agora, banco_id))
    conn.commit()
    conn.close()


def set_usuario_bancos(usuario_id, banco_ids):
    """Define quais bancos um usuário pode acessar (substitui todos)."""
    conn = get_db()
    conn.execute("DELETE FROM usuario_bancos_talentos WHERE usuario_id=?", (usuario_id,))
    for bid in banco_ids:
        conn.execute(
            "INSERT OR IGNORE INTO usuario_bancos_talentos(usuario_id, banco_id) VALUES(?,?)",
            (usuario_id, int(bid))
        )
    conn.commit()
    conn.close()


def get_acesso_talentos(usuario_id, tipo_usuario):
    """Retorna dict legado com permissões (slug→bool) baseado no novo sistema."""
    bancos = get_bancos_usuario(usuario_id, tipo_usuario)
    result = {}
    for b in get_bancos_talentos():
        result[b["slug"]] = any(x["slug"] == b["slug"] for x in bancos)
    return result


# ──────────────────────────────────────────
#  CHAT DE SUPORTE
# ──────────────────────────────────────────
def salvar_chat_mensagem(session_id, usuario_id, role, content):
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_historico(session_id, usuario_id, role, content, criado_em) VALUES(?,?,?,?,?)",
        (session_id, usuario_id, role, content, agora),
    )
    conn.commit()
    conn.close()


def get_chat_historico(session_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM chat_historico WHERE session_id=? ORDER BY id",
        (session_id,),
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


def salvar_sugestao(usuario_id, nome_usuario, sugestao):
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_sugestoes(usuario_id, nome_usuario, sugestao, criado_em) VALUES(?,?,?,?)",
        (usuario_id, nome_usuario, sugestao, agora),
    )
    conn.commit()
    conn.close()


def get_sugestoes(lida=None):
    conn = get_db()
    if lida is not None:
        rows = conn.execute(
            "SELECT s.*, u.nome AS usuario_nome FROM chat_sugestoes s LEFT JOIN usuarios u ON u.id=s.usuario_id WHERE s.lida=? ORDER BY s.id DESC",
            (lida,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT s.*, u.nome AS usuario_nome FROM chat_sugestoes s LEFT JOIN usuarios u ON u.id=s.usuario_id ORDER BY s.id DESC"
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def marcar_sugestao_lida(sugestao_id):
    conn = get_db()
    conn.execute("UPDATE chat_sugestoes SET lida=1 WHERE id=?", (sugestao_id,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────
#  GRUPOS (MULTI-TENANT)
# ──────────────────────────────────────────
def get_grupos_lista():
    conn = get_db()
    rows = conn.execute("""
        SELECT g.*, t.cor_primaria, t.cor_secundaria, t.logo_url, t.nome_exibicao
        FROM grupos g LEFT JOIN temas_grupo t ON t.grupo_id=g.id
        WHERE g.ativo=1 ORDER BY g.nome
    """).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_grupo_by_slug(slug):
    conn = get_db()
    row = conn.execute("""
        SELECT g.*, t.cor_primaria, t.cor_secundaria, t.bg_login_url, t.logo_url, t.nome_exibicao
        FROM grupos g LEFT JOIN temas_grupo t ON t.grupo_id=g.id
        WHERE g.slug=? AND g.ativo=1
    """, (slug,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_tema_grupo(grupo_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM temas_grupo WHERE grupo_id=?", (grupo_id,)).fetchone()
    conn.close()
    if not row:
        return {"cor_primaria": "#3d8f60", "cor_secundaria": "#1e5235",
                "bg_login_url": "", "logo_url": "", "nome_exibicao": ""}
    return dict(row)


def salvar_tema_grupo(grupo_id, nome_exibicao, cor_primaria, cor_secundaria, bg_login_url, logo_url):
    conn = get_db()
    conn.execute("""
        INSERT INTO temas_grupo(grupo_id,nome_exibicao,cor_primaria,cor_secundaria,bg_login_url,logo_url)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(grupo_id) DO UPDATE SET
            nome_exibicao=excluded.nome_exibicao,
            cor_primaria=excluded.cor_primaria,
            cor_secundaria=excluded.cor_secundaria,
            bg_login_url=excluded.bg_login_url,
            logo_url=excluded.logo_url
    """, (grupo_id, nome_exibicao, cor_primaria, cor_secundaria, bg_login_url, logo_url))
    conn.commit()
    conn.close()


def get_lojas_grupo(grupo_id):
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM lojas WHERE grupo_id=? AND ativo=1 ORDER BY nome", (grupo_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_stats_grupo(grupo_id):
    conn = get_db()
    n_lojas = conn.execute("SELECT COUNT(*) FROM lojas WHERE grupo_id=? AND ativo=1", (grupo_id,)).fetchone()[0]
    n_users = conn.execute("SELECT COUNT(*) FROM usuarios WHERE grupo_id=? AND ativo=1", (grupo_id,)).fetchone()[0]
    conn.close()
    return {"lojas": n_lojas, "usuarios": n_users}


def salvar_grupo(nome, slug, grupo_id=None):
    conn = get_db()
    try:
        if grupo_id:
            conn.execute("UPDATE grupos SET nome=?,slug=? WHERE id=?", (nome, slug, grupo_id))
        else:
            cur = conn.execute("INSERT INTO grupos(nome,slug) VALUES(?,?)", (nome, slug))
            grupo_id = cur.lastrowid
            conn.execute("INSERT INTO temas_grupo(grupo_id) VALUES(?)", (grupo_id,))
        conn.commit()
        return grupo_id
    finally:
        conn.close()


# ──────────────────────────────────────────
#  MÓDULOS DO SISTEMA
# ──────────────────────────────────────────
def get_modulos_sistema(apenas_ativos=True):
    conn = get_db()
    q = "SELECT * FROM modulos_sistema WHERE ativo=1 ORDER BY ordem, nome" if apenas_ativos else "SELECT * FROM modulos_sistema ORDER BY ordem, nome"
    rows = conn.execute(q).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_modulos_usuario_ids(usuario_id):
    conn = get_db()
    rows = conn.execute("SELECT modulo_id FROM usuario_modulos WHERE usuario_id=?", (usuario_id,)).fetchall()
    conn.close()
    return [r["modulo_id"] for r in rows]


def set_usuario_modulos_acesso(conn, usuario_id, modulo_ids):
    """Salva quais módulos o usuário tem acesso e sincroniza acesso_dre."""
    conn.execute("DELETE FROM usuario_modulos WHERE usuario_id=?", (usuario_id,))
    for mid in modulo_ids:
        conn.execute("INSERT OR IGNORE INTO usuario_modulos(usuario_id,modulo_id) VALUES(?,?)", (usuario_id, int(mid)))
    dre = conn.execute("SELECT id FROM modulos_sistema WHERE slug='dre'").fetchone()
    if dre:
        acesso = 1 if dre["id"] in [int(m) for m in modulo_ids] else 0
        conn.execute("UPDATE usuarios SET acesso_dre=? WHERE id=?", (acesso, usuario_id))


def salvar_modulo_sistema(nome, slug, descricao="", icone="bi-puzzle", modulo_id=None):
    conn = get_db()
    try:
        if modulo_id:
            conn.execute(
                "UPDATE modulos_sistema SET nome=?,slug=?,descricao=?,icone=? WHERE id=? AND slug!='dre'",
                (nome, slug, descricao, icone, modulo_id)
            )
        else:
            conn.execute(
                "INSERT INTO modulos_sistema(nome,slug,descricao,icone) VALUES(?,?,?,?)",
                (nome, slug, descricao, icone)
            )
        conn.commit()
    finally:
        conn.close()


def excluir_modulo_sistema(modulo_id):
    conn = get_db()
    conn.execute("DELETE FROM usuario_modulos WHERE modulo_id=?", (modulo_id,))
    conn.execute("DELETE FROM modulos_sistema WHERE id=? AND slug!='dre'", (modulo_id,))
    conn.commit()
    conn.close()


# ──────────────────────────────────────────
#  MÓDULO CHAMADOS
# ──────────────────────────────────────────

STATUS_CHAMADO  = ["aberto", "em_andamento", "aguardando", "resolvido", "fechado"]
PRIO_CHAMADO    = ["baixa", "media", "alta", "urgente"]
CAT_CHAMADO     = ["suporte", "hardware", "software", "rede", "treinamento", "financeiro", "rh", "outros"]


def _gerar_numero_chamado(conn):
    from datetime import datetime, timezone, timedelta
    ano = datetime.now(timezone(timedelta(hours=-3))).year
    row = conn.execute(
        "SELECT MAX(CAST(SUBSTR(numero, -4) AS INTEGER)) FROM chamados WHERE numero LIKE ?",
        (f"CH-{ano}-%",)
    ).fetchone()
    seq = (row[0] or 0) + 1
    return f"CH-{ano}-{seq:04d}"


def _agora_br():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")


def criar_chamado(grupo_id, loja_id, titulo, descricao, prioridade, categoria,
                  solicitante_id, solicitante_nome, solicitante_email, solicitante_tel,
                  responsavel_id=None, prazo=None):
    conn = get_db()
    numero = _gerar_numero_chamado(conn)
    agora = _agora_br()
    conn.execute("""
        INSERT INTO chamados
            (numero, grupo_id, loja_id, titulo, descricao, prioridade, categoria,
             solicitante_id, solicitante_nome, solicitante_email, solicitante_tel,
             responsavel_id, prazo, criado_em, atualizado_em)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (numero, grupo_id, loja_id, titulo, descricao, prioridade, categoria,
          solicitante_id, solicitante_nome, solicitante_email, solicitante_tel,
          responsavel_id or None, prazo or None, agora, agora))
    cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    conn.close()
    return cid, numero


def get_chamados(grupo_id=None, loja_id=None, status=None, prioridade=None,
                 responsavel_id=None, solicitante_id=None, q=None):
    conn = get_db()
    filtros, params = [], []
    if grupo_id is not None:
        filtros.append("c.grupo_id=?"); params.append(grupo_id)
    if loja_id:
        filtros.append("c.loja_id=?"); params.append(loja_id)
    if status:
        filtros.append("c.status=?"); params.append(status)
    if prioridade:
        filtros.append("c.prioridade=?"); params.append(prioridade)
    if responsavel_id:
        filtros.append("c.responsavel_id=?"); params.append(responsavel_id)
    if solicitante_id:
        filtros.append("c.solicitante_id=?"); params.append(solicitante_id)
    if q:
        filtros.append("(c.titulo LIKE ? OR c.numero LIKE ? OR c.solicitante_nome LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    rows = conn.execute(f"""
        SELECT c.*,
               l.nome as loja_nome,
               r.nome as responsavel_nome
        FROM chamados c
        LEFT JOIN lojas l ON l.id = c.loja_id
        LEFT JOIN usuarios r ON r.id = c.responsavel_id
        {where}
        ORDER BY
            CASE c.status WHEN 'fechado' THEN 1 WHEN 'resolvido' THEN 2 ELSE 0 END,
            CASE c.prioridade WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END,
            c.criado_em DESC
    """, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_chamado(chamado_id):
    conn = get_db()
    row = conn.execute("""
        SELECT c.*,
               l.nome as loja_nome,
               r.nome as responsavel_nome,
               s.nome as solicitante_nome_u,
               sec.nome as setor_nome
        FROM chamados c
        LEFT JOIN lojas l ON l.id = c.loja_id
        LEFT JOIN usuarios r ON r.id = c.responsavel_id
        LEFT JOIN usuarios s ON s.id = c.solicitante_id
        LEFT JOIN chamados_setores sec ON sec.id = c.setor_id
        WHERE c.id=?
    """, (chamado_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def get_comentarios_chamado(chamado_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT * FROM chamados_comentarios
        WHERE chamado_id=? ORDER BY criado_em ASC
    """, (chamado_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def adicionar_comentario_chamado(chamado_id, usuario_id, usuario_nome, texto, tipo="comentario"):
    agora = _agora_br()
    conn = get_db()
    conn.execute("""
        INSERT INTO chamados_comentarios(chamado_id, usuario_id, usuario_nome, texto, tipo, criado_em)
        VALUES(?,?,?,?,?,?)
    """, (chamado_id, usuario_id, usuario_nome, texto, tipo, agora))
    conn.execute("UPDATE chamados SET atualizado_em=? WHERE id=?", (agora, chamado_id))
    conn.commit()
    conn.close()


def atualizar_status_chamado(chamado_id, novo_status, usuario_id, usuario_nome):
    agora = _agora_br()
    conn = get_db()
    old = conn.execute("SELECT status FROM chamados WHERE id=?", (chamado_id,)).fetchone()
    fechado_em = agora if novo_status in ("fechado", "resolvido") else None
    conn.execute(
        "UPDATE chamados SET status=?, atualizado_em=?, fechado_em=? WHERE id=?",
        (novo_status, agora, fechado_em, chamado_id)
    )
    if old:
        label = {"aberto":"Aberto","em_andamento":"Em Andamento","aguardando":"Aguardando",
                 "resolvido":"Resolvido","fechado":"Fechado"}
        conn.execute("""
            INSERT INTO chamados_comentarios(chamado_id,usuario_id,usuario_nome,texto,tipo,criado_em)
            VALUES(?,?,?,?,?,?)
        """, (chamado_id, usuario_id, usuario_nome,
              f"Status alterado: {label.get(old['status'],old['status'])} → {label.get(novo_status,novo_status)}",
              "status", agora))
    conn.commit()
    conn.close()


def atualizar_responsavel_chamado(chamado_id, responsavel_id, responsavel_nome, usuario_id, usuario_nome):
    agora = _agora_br()
    conn = get_db()
    conn.execute(
        "UPDATE chamados SET responsavel_id=?, atualizado_em=? WHERE id=?",
        (responsavel_id or None, agora, chamado_id)
    )
    conn.execute("""
        INSERT INTO chamados_comentarios(chamado_id,usuario_id,usuario_nome,texto,tipo,criado_em)
        VALUES(?,?,?,?,?,?)
    """, (chamado_id, usuario_id, usuario_nome,
          f"Responsável atribuído: {responsavel_nome or 'Nenhum'}",
          "atribuicao", agora))
    conn.commit()
    conn.close()


def editar_chamado(chamado_id, titulo, descricao, prioridade, categoria, loja_id, prazo,
                   solicitante_nome, solicitante_email, solicitante_tel):
    agora = _agora_br()
    conn = get_db()
    conn.execute("""
        UPDATE chamados SET titulo=?,descricao=?,prioridade=?,categoria=?,loja_id=?,prazo=?,
            solicitante_nome=?,solicitante_email=?,solicitante_tel=?,atualizado_em=?
        WHERE id=?
    """, (titulo, descricao, prioridade, categoria, loja_id or None, prazo or None,
          solicitante_nome, solicitante_email, solicitante_tel, agora, chamado_id))
    conn.commit()
    conn.close()


# ── Setores ──
def get_setores_chamados(grupo_id, apenas_ativos=True):
    conn = get_db()
    where = "WHERE grupo_id=? AND ativo=1" if apenas_ativos else "WHERE grupo_id=?"
    rows = conn.execute(f"""
        SELECT s.*, u.nome as responsavel_nome
        FROM chamados_setores s
        LEFT JOIN usuarios u ON u.id=s.responsavel_id
        {where} ORDER BY s.nome
    """, (grupo_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_setor_chamado(grupo_id, nome, cor, responsavel_id, pode_abrir, pode_receber, setor_id=None):
    agora = _agora_br()
    conn = get_db()
    if setor_id:
        conn.execute("""UPDATE chamados_setores SET nome=?,cor=?,responsavel_id=?,pode_abrir=?,pode_receber=?
                        WHERE id=? AND grupo_id=?""",
                     (nome, cor, responsavel_id or None, pode_abrir, pode_receber, setor_id, grupo_id))
    else:
        conn.execute("""INSERT INTO chamados_setores(grupo_id,nome,cor,responsavel_id,pode_abrir,pode_receber,criado_em)
                        VALUES(?,?,?,?,?,?,?)""",
                     (grupo_id, nome, cor, responsavel_id or None, pode_abrir, pode_receber, agora))
    conn.commit(); conn.close()

def excluir_setor_chamado(setor_id, grupo_id):
    conn = get_db()
    conn.execute("UPDATE chamados_setores SET ativo=0 WHERE id=? AND grupo_id=?", (setor_id, grupo_id))
    conn.commit(); conn.close()

# ── Etiquetas ──
def get_etiquetas_chamados(grupo_id, apenas_ativas=True):
    conn = get_db()
    where = "WHERE grupo_id=? AND ativo=1" if apenas_ativas else "WHERE grupo_id=?"
    rows = conn.execute(f"SELECT * FROM chamados_etiquetas {where} ORDER BY nome", (grupo_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_etiqueta_chamado(grupo_id, nome, cor, etiqueta_id=None):
    conn = get_db()
    if etiqueta_id:
        conn.execute("UPDATE chamados_etiquetas SET nome=?,cor=? WHERE id=? AND grupo_id=?",
                     (nome, cor, etiqueta_id, grupo_id))
    else:
        conn.execute("INSERT INTO chamados_etiquetas(grupo_id,nome,cor) VALUES(?,?,?)", (grupo_id, nome, cor))
    conn.commit(); conn.close()

def excluir_etiqueta_chamado(etiqueta_id, grupo_id):
    conn = get_db()
    conn.execute("UPDATE chamados_etiquetas SET ativo=0 WHERE id=? AND grupo_id=?", (etiqueta_id, grupo_id))
    conn.commit(); conn.close()

def get_etiquetas_do_chamado(chamado_id):
    conn = get_db()
    rows = conn.execute("""
        SELECT e.* FROM chamados_etiquetas e
        JOIN chamado_etiqueta ce ON ce.etiqueta_id=e.id
        WHERE ce.chamado_id=?
    """, (chamado_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def set_etiquetas_chamado(chamado_id, etiqueta_ids):
    conn = get_db()
    conn.execute("DELETE FROM chamado_etiqueta WHERE chamado_id=?", (chamado_id,))
    for eid in etiqueta_ids:
        conn.execute("INSERT OR IGNORE INTO chamado_etiqueta(chamado_id,etiqueta_id) VALUES(?,?)", (chamado_id, int(eid)))
    conn.execute("UPDATE chamados SET atualizado_em=? WHERE id=?", (_agora_br(), chamado_id))
    conn.commit(); conn.close()

# ── SLA ──
def get_slas_chamados(grupo_id, apenas_ativos=True):
    conn = get_db()
    where = "WHERE grupo_id=? AND ativo=1" if apenas_ativos else "WHERE grupo_id=?"
    rows = conn.execute(f"SELECT * FROM chamados_sla {where} ORDER BY CASE prioridade WHEN 'urgente' THEN 0 WHEN 'alta' THEN 1 WHEN 'media' THEN 2 ELSE 3 END", (grupo_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def salvar_sla_chamado(grupo_id, nome, prioridade, horas_resposta, horas_resolucao,
                        dias_semana, hora_inicio, hora_fim, sla_id=None):
    conn = get_db()
    if sla_id:
        conn.execute("""UPDATE chamados_sla SET nome=?,prioridade=?,horas_resposta=?,horas_resolucao=?,
                        dias_semana=?,hora_inicio=?,hora_fim=? WHERE id=? AND grupo_id=?""",
                     (nome, prioridade, horas_resposta, horas_resolucao,
                      dias_semana, hora_inicio, hora_fim, sla_id, grupo_id))
    else:
        conn.execute("""INSERT INTO chamados_sla(grupo_id,nome,prioridade,horas_resposta,horas_resolucao,
                        dias_semana,hora_inicio,hora_fim) VALUES(?,?,?,?,?,?,?,?)""",
                     (grupo_id, nome, prioridade, horas_resposta, horas_resolucao,
                      dias_semana, hora_inicio, hora_fim))
    conn.commit(); conn.close()

def excluir_sla_chamado(sla_id, grupo_id):
    conn = get_db()
    conn.execute("UPDATE chamados_sla SET ativo=0 WHERE id=? AND grupo_id=?", (sla_id, grupo_id))
    conn.commit(); conn.close()

def calcular_prazo_sla(grupo_id, prioridade):
    """Calcula o prazo de resolução com base no SLA configurado para a prioridade, respeitando horário comercial."""
    from datetime import datetime, timedelta, timezone
    conn = get_db()
    sla = conn.execute(
        "SELECT * FROM chamados_sla WHERE grupo_id=? AND prioridade=? AND ativo=1 ORDER BY id LIMIT 1",
        (grupo_id, prioridade)
    ).fetchone()
    conn.close()
    if not sla:
        horas = {"urgente":4,"alta":8,"media":24,"baixa":72}.get(prioridade, 24)
        return (_agora_br_dt() + timedelta(hours=horas)).strftime("%Y-%m-%d %H:%M:%S")

    dias = [int(d) for d in sla["dias_semana"].split(",") if d.strip()]
    hi = int(sla["hora_inicio"].split(":")[0])
    hf = int(sla["hora_fim"].split(":")[0])
    horas_restantes = float(sla["horas_resolucao"])
    agora = _agora_br_dt()
    current = agora

    while horas_restantes > 0:
        if current.isoweekday() in dias and hi <= current.hour < hf:
            horas_restantes -= 1
            current += timedelta(hours=1)
        else:
            current += timedelta(hours=1)
            if current.hour >= hf or current.isoweekday() not in dias:
                # Avança para próximo dia útil no horário de início
                current = current.replace(hour=hi, minute=0, second=0, microsecond=0)
                dias_avancados = 0
                while current.isoweekday() not in dias and dias_avancados < 14:
                    current += timedelta(days=1)
                    dias_avancados += 1
    return current.strftime("%Y-%m-%d %H:%M:%S")

def _agora_br_dt():
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=-3))).replace(tzinfo=None)

# ── Apoios e Acompanhantes ──
def get_apoios_chamado(chamado_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM chamado_apoios WHERE chamado_id=? ORDER BY adicionado_em", (chamado_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_acompanhantes_chamado(chamado_id):
    conn = get_db()
    rows = conn.execute("SELECT * FROM chamado_acompanhantes WHERE chamado_id=? ORDER BY adicionado_em", (chamado_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def adicionar_apoio_chamado(chamado_id, usuario_id, usuario_nome, ator_id, ator_nome):
    agora = _agora_br()
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO chamado_apoios(chamado_id,usuario_id,usuario_nome,adicionado_em) VALUES(?,?,?,?)",
                     (chamado_id, usuario_id, usuario_nome, agora))
        conn.execute("""INSERT INTO chamados_comentarios(chamado_id,usuario_id,usuario_nome,texto,tipo,criado_em)
                        VALUES(?,?,?,?,?,?)""",
                     (chamado_id, ator_id, ator_nome, f"Apoio adicionado: {usuario_nome}", "atribuicao", agora))
        conn.execute("UPDATE chamados SET atualizado_em=? WHERE id=?", (agora, chamado_id))
        conn.commit()
    finally:
        conn.close()

def remover_apoio_chamado(chamado_id, usuario_id):
    conn = get_db()
    conn.execute("DELETE FROM chamado_apoios WHERE chamado_id=? AND usuario_id=?", (chamado_id, usuario_id))
    conn.execute("UPDATE chamados SET atualizado_em=? WHERE id=?", (_agora_br(), chamado_id))
    conn.commit(); conn.close()

def adicionar_acompanhante_chamado(chamado_id, usuario_id, usuario_nome, ator_id, ator_nome):
    agora = _agora_br()
    conn = get_db()
    try:
        conn.execute("INSERT OR IGNORE INTO chamado_acompanhantes(chamado_id,usuario_id,usuario_nome,adicionado_em) VALUES(?,?,?,?)",
                     (chamado_id, usuario_id, usuario_nome, agora))
        conn.execute("""INSERT INTO chamados_comentarios(chamado_id,usuario_id,usuario_nome,texto,tipo,criado_em)
                        VALUES(?,?,?,?,?,?)""",
                     (chamado_id, ator_id, ator_nome, f"Acompanhante adicionado: {usuario_nome}", "atribuicao", agora))
        conn.execute("UPDATE chamados SET atualizado_em=? WHERE id=?", (agora, chamado_id))
        conn.commit()
    finally:
        conn.close()

def remover_acompanhante_chamado(chamado_id, usuario_id):
    conn = get_db()
    conn.execute("DELETE FROM chamado_acompanhantes WHERE chamado_id=? AND usuario_id=?", (chamado_id, usuario_id))
    conn.execute("UPDATE chamados SET atualizado_em=? WHERE id=?", (_agora_br(), chamado_id))
    conn.commit(); conn.close()

def get_stats_chamados(grupo_id=None, loja_id=None):
    conn = get_db()
    filtros, params = [], []
    if grupo_id is not None:
        filtros.append("grupo_id=?"); params.append(grupo_id)
    if loja_id:
        filtros.append("loja_id=?"); params.append(loja_id)
    where = ("WHERE " + " AND ".join(filtros)) if filtros else ""
    rows = conn.execute(f"""
        SELECT status, prioridade, COUNT(*) as total
        FROM chamados {where}
        GROUP BY status, prioridade
    """, params).fetchall()
    conn.close()
    stats = {"total": 0, "aberto": 0, "em_andamento": 0, "aguardando": 0,
             "resolvido": 0, "fechado": 0, "urgente": 0, "alta": 0}
    for r in rows:
        stats["total"] += r["total"]
        if r["status"] in stats:
            stats[r["status"]] += r["total"]
        if r["prioridade"] in ("urgente", "alta"):
            stats[r["prioridade"]] += r["total"]
    return stats
