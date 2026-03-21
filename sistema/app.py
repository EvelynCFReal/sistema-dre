"""
app.py – Sistema de DRE | 2026–2036
Flask + SQLite | 4 níveis de usuário | Multilojas | Fuso: America/Sao_Paulo
"""
import os
import json
import re
import secrets
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, send_from_directory,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timezone, timedelta

from database import (
    get_db, init_db, migrar_db,
    calcular_dre, resumo_anual, resumo_todos_anos, comparativo_marcas,
    usuario_pode_mes, get_config, set_config,
    MESES, ANOS, ANO_INICIO, ANO_FIM, TIPOS_USUARIO,
    get_tema, gerar_api_key, validar_api_key,
    get_lojas_usuario, get_perfil_loja, get_lojas_gestor,
    copiar_parametros_loja,
)

# ──────────────────────────────────────────
#  APP
# ──────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static", "logos")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "svg", "webp"}
FUSO_BR = timezone(timedelta(hours=-3))


def agora_br():
    return datetime.now(FUSO_BR)


def allowed_file(fn):
    return "." in fn and fn.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ──────────────────────────────────────────
#  HELPERS
# ──────────────────────────────────────────
def ano_selecionado():
    """Ano selecionado na sessão, dentro do intervalo válido."""
    ano = session.get("ano_sel", agora_br().year)
    return max(ANO_INICIO, min(ANO_FIM, int(ano)))


def loja_selecionada():
    """Loja selecionada na sessão. Se a loja estiver inativa, troca para uma ativa."""
    lid = session.get("loja_id", 1)
    uid = session.get("usuario_id")
    tipo = session.get("tipo", "")
    if uid:
        lojas = get_lojas_usuario(uid, tipo)
        ids_ativos = [l["id"] for l in lojas]
        if lid not in ids_ativos and ids_ativos:
            lid = ids_ativos[0]
            session["loja_id"] = lid
    return lid


# ──────────────────────────────────────────
#  DECORADORES
# ──────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def deco(*a, **kw):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*a, **kw)
    return deco


def role_required(*roles):
    def dec(f):
        @wraps(f)
        def deco(*a, **kw):
            if session.get("tipo") not in roles:
                flash("Acesso negado.", "danger")
                if session.get("tipo") == "loja":
                    return redirect(url_for("lancamentos"))
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return deco
    return dec


def perfil_loja_required(*perfis):
    """Verifica se o perfil do usuário na loja selecionada está entre os permitidos.
    Master sempre passa. Para gestor/loja/leitor, verifica o perfil na loja atual."""
    def dec(f):
        @wraps(f)
        def deco(*a, **kw):
            tipo = session.get("tipo", "")
            if tipo == "master":
                return f(*a, **kw)
            uid = session.get("usuario_id")
            loja_id = loja_selecionada()
            perfil = get_perfil_loja(uid, loja_id, tipo)
            if perfil not in perfis:
                flash("Sem permissão para esta ação nesta loja.", "warning")
                return redirect(url_for("dashboard"))
            return f(*a, **kw)
        return deco
    return dec


def api_auth(permissao="read"):
    def dec(f):
        @wraps(f)
        def deco(*a, **kw):
            chave = request.headers.get("X-API-Key") or request.args.get("api_key")
            if not chave:
                return jsonify({"erro": "API key obrigatória", "codigo": "AUTH_REQUIRED"}), 401
            row = validar_api_key(chave, permissao)
            if not row:
                return jsonify({"erro": "API key inválida ou sem permissão", "codigo": "AUTH_FAILED"}), 403
            request.api_key_row = row
            return f(*a, **kw)
        return deco
    return dec


# ──────────────────────────────────────────
#  CONTEXT PROCESSOR
# ──────────────────────────────────────────
@app.context_processor
def inject_globals():
    loja_id = loja_selecionada()
    ano_sel = ano_selecionado()
    tema = get_tema(loja_id)
    agora = agora_br()

    # Tema do usuário (claro/escuro)
    tema_usuario = session.get("tema_preferido", "escuro")

    # Lojas acessíveis
    uid = session.get("usuario_id")
    tipo = session.get("tipo", "")
    lojas_user = []
    perfil_loja = None
    if uid:
        lojas_user = get_lojas_usuario(uid, tipo)
        # Perfil do usuário na loja atualmente selecionada
        perfil_loja = get_perfil_loja(uid, loja_id, tipo) if tipo != "master" else "master"

    return dict(
        meses=MESES,
        anos=ANOS,
        ano=ano_sel,
        ano_atual_real=agora.year,
        mes_atual=agora.month,
        user_tipo=tipo,
        user_nome=session.get("nome", ""),
        user_id=uid,
        tema=tema,
        tema_usuario=tema_usuario,
        loja_id_sel=loja_id,
        lojas_user=lojas_user,
        perfil_loja=perfil_loja,
        ANO_INICIO=ANO_INICIO,
        ANO_FIM=ANO_FIM,
    )


# ──────────────────────────────────────────
#  SELECIONAR ANO (global)
# ──────────────────────────────────────────
@app.route("/selecionar-ano", methods=["POST"])
@login_required
def selecionar_ano_route():
    ano = int(request.form.get("ano", agora_br().year))
    ano = max(ANO_INICIO, min(ANO_FIM, ano))
    session["ano_sel"] = ano
    return redirect(request.referrer or url_for("dashboard"))


# ──────────────────────────────────────────
#  SELECIONAR LOJA (global, fica travada)
# ──────────────────────────────────────────
@app.route("/selecionar-loja", methods=["POST"])
@login_required
def selecionar_loja():
    loja_id = int(request.form.get("loja_id", 1))
    tipo = session.get("tipo")
    uid = session.get("usuario_id")

    # Valida se o usuário tem acesso
    if tipo != "master":
        perfil = get_perfil_loja(uid, loja_id, tipo)
        if not perfil:
            flash("Sem permissão para esta loja.", "danger")
            return redirect(request.referrer or url_for("dashboard"))

    session["loja_id"] = loja_id
    return redirect(request.referrer or url_for("dashboard"))


# ──────────────────────────────────────────
#  ALTERNAR TEMA (claro/escuro)
# ──────────────────────────────────────────
@app.route("/alternar-tema", methods=["POST"])
@login_required
def alternar_tema():
    atual = session.get("tema_preferido", "escuro")
    novo = "claro" if atual == "escuro" else "escuro"
    session["tema_preferido"] = novo
    # Persiste no banco
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET tema_preferido=? WHERE id=?",
        (novo, session["usuario_id"]),
    )
    conn.commit()
    conn.close()
    return redirect(request.referrer or url_for("dashboard"))


# ──────────────────────────────────────────
#  AUTH
# ──────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        if session.get("tipo") == "loja":
            return redirect(url_for("lancamentos"))
        return redirect(url_for("dashboard"))

    erro = None
    if request.method == "POST":
        lv = request.form.get("login", "").strip()
        sv = request.form.get("senha", "")
        conn = get_db()
        u = conn.execute(
            "SELECT * FROM usuarios WHERE login=? AND ativo=1", (lv,)
        ).fetchone()
        conn.close()

        if u and check_password_hash(u["senha_hash"], sv):
            # Determina loja inicial
            loja_inicial = 1
            if u["tipo"] != "master":
                lojas = get_lojas_usuario(u["id"], u["tipo"])
                if not lojas:
                    erro = "Nenhuma empresa ativa vinculada ao seu acesso. Contate o administrador."
                    return render_template("login.html", erro=erro)
                loja_inicial = lojas[0]["id"]

            session.update(
                usuario_id=u["id"],
                nome=u["nome"],
                tipo=u["tipo"],
                loja_id=loja_inicial,
                ano_sel=agora_br().year,
                tema_preferido=u["tema_preferido"] or "escuro",
            )

            if u["tipo"] == "loja":
                return redirect(url_for("lancamentos"))
            return redirect(url_for("dashboard"))
        erro = "Login ou senha incorretos."

    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ──────────────────────────────────────────
#  DASHBOARD
# ──────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    tipo = session["tipo"]
    uid = session["usuario_id"]
    loja_id = loja_selecionada()
    ano = ano_selecionado()

    # Usuário loja não acessa dashboard
    if tipo == "loja":
        flash("Acesso restrito. Redirecionado para lançamentos.", "warning")
        return redirect(url_for("lancamentos"))

    # Usuário leitor: só pode ver lojas permitidas
    if tipo == "leitor":
        perfil = get_perfil_loja(uid, loja_id, tipo)
        if not perfil:
            flash("Sem permissão para esta loja.", "danger")
            return redirect(url_for("login"))

    conn = get_db()
    marcas_lista = conn.execute("SELECT * FROM marcas WHERE ativo=1 AND loja_id=? ORDER BY nome", (loja_id,)).fetchall()
    conn.close()

    marca_id = request.args.get("marca_id", type=int)

    resumo = resumo_anual(loja_id, ano, marca_id=marca_id)
    anual = resumo["meses"]
    fat_marca_anual_raw = resumo["fat_marca_anual"]
    desp_marca_anual_raw = resumo["desp_marca_anual"]
    agora = agora_br()
    mes_ref = agora.month if ano == agora.year else 12
    dre_mes = calcular_dre(loja_id, ano, mes_ref, marca_id=marca_id)
    fat_total = sum(m["faturamento"] for m in anual)
    res_total = sum(m["resultado"] for m in anual)
    desp_total = sum(m["despesas"] for m in anual)
    todos_anos = resumo_todos_anos(loja_id)

    # Comparativo de marcas do mês de referência
    comp_marcas = comparativo_marcas(loja_id, ano, mes_ref)

    # Converte dicts em listas ordenadas para o template
    fat_marca_anual = sorted(
        [{"nome": k, **v} for k, v in fat_marca_anual_raw.items()],
        key=lambda x: x["bruto"], reverse=True
    )
    desp_marca_anual = sorted(
        [{"nome": k, "total": v} for k, v in desp_marca_anual_raw.items()],
        key=lambda x: x["total"], reverse=True
    )

    return render_template(
        "dashboard.html",
        anual=anual,
        dre_mes=dre_mes,
        fat_total=fat_total,
        res_total=res_total,
        desp_total=desp_total,
        loja_sel=loja_id,
        mes_ref=mes_ref,
        todos_anos=todos_anos,
        meta=float(get_config("meta_faturamento_mensal", loja_id, "50000")),
        marcas=marcas_lista,
        marca_sel=marca_id,
        comp_marcas=comp_marcas,
        fat_marca_anual=fat_marca_anual,
        desp_marca_anual=desp_marca_anual,
    )


# ──────────────────────────────────────────
#  RELATÓRIO RESUMIDO
# ──────────────────────────────────────────
@app.route("/relatorio-resumido")
@login_required
def relatorio_resumido():
    tipo = session["tipo"]
    if tipo == "loja":
        flash("Acesso restrito.", "warning")
        return redirect(url_for("lancamentos"))

    loja_id = loja_selecionada()
    ano = ano_selecionado()
    resumo = resumo_anual(loja_id, ano)
    anual = resumo["meses"]
    fat_marca_anual = resumo["fat_marca_anual"]
    desp_marca_anual = resumo["desp_marca_anual"]
    fat_total = sum(m["faturamento"] for m in anual)
    res_total = sum(m["resultado"] for m in anual)
    desp_total = sum(m["despesas"] for m in anual)
    conn = get_db()
    loja = conn.execute("SELECT nome FROM lojas WHERE id=?", (loja_id,)).fetchone()
    conn.close()

    # DRE detalhado de cada mês para o relatório
    dres_mensal = []
    for mes_i in range(1, 13):
        dre_m = calcular_dre(loja_id, ano, mes_i)
        dres_mensal.append(dre_m)

    return render_template(
        "relatorio_resumido.html",
        anual=anual,
        fat_total=fat_total,
        res_total=res_total,
        desp_total=desp_total,
        loja_nome=loja["nome"] if loja else "",
        meta=float(get_config("meta_faturamento_mensal", loja_id, "50000")),
        dres_mensal=dres_mensal,
        fat_marca_anual=fat_marca_anual,
        desp_marca_anual=desp_marca_anual,
    )


# ──────────────────────────────────────────
#  RELATÓRIO DETALHADO
# ──────────────────────────────────────────
@app.route("/relatorio-detalhado")
@login_required
def relatorio_detalhado():
    tipo = session["tipo"]
    if tipo == "loja":
        flash("Acesso restrito.", "warning")
        return redirect(url_for("lancamentos"))

    loja_id = loja_selecionada()
    ano = ano_selecionado()
    mes = request.args.get("mes", type=int)

    conn = get_db()

    filtro_mes = ""
    params_cx = [loja_id, str(ano)]
    params_dp = [loja_id, str(ano)]
    params_ap = [loja_id, str(ano)]
    if mes and 1 <= mes <= 12:
        filtro_mes = " AND strftime('%m', {col}) = ?"
        mes_str = f"{mes:02d}"
        params_cx.append(mes_str)
        params_dp.append(mes_str)
        params_ap.append(mes_str)

    caixas = conn.execute(f"""
        SELECT lc.data, lc.turno, lc.valor, lc.taxa_aplicada, lc.criado_em,
               fp.nome as forma_pagamento, p.nome as plataforma, u.nome as usuario,
               m.nome as marca
        FROM lancamentos_caixa lc
        JOIN formas_pagamento fp ON fp.id = lc.forma_pagamento_id
        LEFT JOIN plataformas p ON p.id = lc.plataforma_id
        LEFT JOIN marcas m ON m.id = lc.marca_id
        JOIN usuarios u ON u.id = lc.usuario_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ?
        {filtro_mes.format(col='lc.data') if mes else ''}
        ORDER BY lc.data, lc.criado_em
    """, params_cx).fetchall()

    despesas = conn.execute(f"""
        SELECT ld.data, ld.valor, ld.descricao, ld.criado_em,
               cd.nome as categoria, cd.tipo as tipo_cat, u.nome as usuario,
               m.nome as marca
        FROM lancamentos_despesa ld
        JOIN categorias_despesa cd ON cd.id = ld.categoria_id
        LEFT JOIN marcas m ON m.id = ld.marca_id
        JOIN usuarios u ON u.id = ld.usuario_id
        WHERE ld.loja_id = ? AND strftime('%Y', ld.data) = ?
        {filtro_mes.format(col='ld.data') if mes else ''}
        ORDER BY ld.data, ld.criado_em
    """, params_dp).fetchall()

    aportes = conn.execute(f"""
        SELECT a.data, a.tipo, a.valor, a.descricao, a.criado_em, u.nome as usuario,
               m.nome as marca
        FROM aporte_sangria a
        LEFT JOIN marcas m ON m.id = a.marca_id
        JOIN usuarios u ON u.id = a.usuario_id
        WHERE a.loja_id = ? AND strftime('%Y', a.data) = ?
        {filtro_mes.format(col='a.data') if mes else ''}
        ORDER BY a.data, a.criado_em
    """, params_ap).fetchall()

    loja = conn.execute("SELECT nome FROM lojas WHERE id=?", (loja_id,)).fetchone()
    conn.close()

    periodo = f"{MESES[mes-1]} de {ano}" if mes else f"Ano {ano} (todos os meses)"

    return render_template(
        "relatorio_detalhado.html",
        caixas=[dict(r) for r in caixas],
        despesas=[dict(r) for r in despesas],
        aportes=[dict(r) for r in aportes],
        loja_nome=loja["nome"] if loja else "",
        mes_selecionado=mes,
        periodo=periodo,
    )


# ──────────────────────────────────────────
#  DRE MENSAL
# ──────────────────────────────────────────
@app.route("/dre/<int:mes>")
@login_required
def dre_mensal(mes):
    tipo = session["tipo"]
    uid = session["usuario_id"]
    loja_id = loja_selecionada()
    ano = ano_selecionado()

    if mes < 1 or mes > 12:
        flash("Mês inválido.", "danger")
        return redirect(url_for("dashboard"))

    # Usuário loja não acessa DRE
    if tipo == "loja":
        flash("Acesso restrito.", "warning")
        return redirect(url_for("lancamentos"))

    # Verifica permissão na loja
    if tipo not in ("master",):
        perfil = get_perfil_loja(uid, loja_id, tipo)
        if not perfil:
            flash("Sem permissão para esta loja.", "danger")
            return redirect(url_for("dashboard"))

    conn = get_db()
    marcas_lista = conn.execute("SELECT * FROM marcas WHERE ativo=1 AND loja_id=? ORDER BY nome", (loja_id,)).fetchall()
    conn.close()

    marca_id = request.args.get("marca_id", type=int)

    dre = calcular_dre(loja_id, ano, mes, marca_id=marca_id)
    comp_marcas = comparativo_marcas(loja_id, ano, mes)

    return render_template(
        "dre_mensal.html",
        dre=dre,
        mes=mes,
        nome_mes=MESES[mes - 1],
        loja_sel=loja_id,
        marcas=marcas_lista,
        marca_sel=marca_id,
        comp_marcas=comp_marcas,
    )


# ──────────────────────────────────────────
#  LANÇAMENTOS
# ──────────────────────────────────────────
@app.route("/lancamentos", methods=["GET", "POST"])
@login_required
@role_required("master", "gestor", "loja")
def lancamentos():
    uid = session["usuario_id"]
    tipo = session["tipo"]
    loja_id = loja_selecionada()
    ano = ano_selecionado()

    # Verifica permissão na loja
    if tipo != "master":
        perfil = get_perfil_loja(uid, loja_id, tipo)
        if not perfil or perfil == "leitor":
            flash("Sem permissão de lançamento nesta loja.", "warning")
            return redirect(url_for("dashboard") if tipo != "loja" else url_for("login"))

    conn = get_db()
    fps = conn.execute("SELECT * FROM formas_pagamento WHERE ativo=1 AND loja_id=? ORDER BY nome", (loja_id,)).fetchall()
    plats = conn.execute("SELECT * FROM plataformas WHERE ativo=1 AND loja_id=? ORDER BY nome", (loja_id,)).fetchall()
    cats = conn.execute("SELECT * FROM categorias_despesa WHERE ativo=1 AND loja_id=? ORDER BY tipo, nome", (loja_id,)).fetchall()
    marcas_lista = conn.execute("SELECT * FROM marcas WHERE ativo=1 AND loja_id=? ORDER BY nome", (loja_id,)).fetchall()

    if request.method == "POST":
        acao = request.form.get("acao")
        data_lanc = request.form.get("data")

        if data_lanc:
            partes = data_lanc.split("-")
            ano_lanc = int(partes[0])
            mes_lanc = int(partes[1])
        else:
            ano_lanc = ano
            mes_lanc = agora_br().month

        if ano_lanc < ANO_INICIO or ano_lanc > ANO_FIM:
            flash(f"Ano inválido. Permitido: {ANO_INICIO}–{ANO_FIM}.", "danger")
        elif tipo == "loja" and not usuario_pode_mes(uid, loja_id, ano_lanc, mes_lanc):
            flash("Sem permissão para lançar neste mês/ano.", "danger")
        elif acao == "caixa":
            fp_id = request.form.get("forma_pagamento_id")
            plt_id = request.form.get("plataforma_id") or None
            marca_id = request.form.get("marca_id") or None
            turno = request.form.get("turno")
            valor = float(request.form.get("valor", 0))
            if turno not in ("almoco", "jantar", "pos_meia_noite"):
                flash("Turno inválido.", "danger")
            elif valor <= 0:
                flash("Valor deve ser maior que zero.", "danger")
            else:
                # Grava a taxa vigente no momento do lançamento
                taxa_atual = conn.execute(
                    "SELECT taxa FROM formas_pagamento WHERE id=?", (fp_id,)
                ).fetchone()
                taxa_val = taxa_atual["taxa"] if taxa_atual else 0
                conn.execute(
                    """INSERT INTO lancamentos_caixa
                    (loja_id, data, turno, forma_pagamento_id, plataforma_id, marca_id, valor, taxa_aplicada, usuario_id)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                    (loja_id, data_lanc, turno, fp_id, plt_id, marca_id, valor, taxa_val, uid),
                )
                conn.commit()
                flash("Lançamento de caixa salvo!", "success")
        elif acao == "despesa":
            cat_id = request.form.get("categoria_id")
            marca_id_d = request.form.get("marca_id") or None
            valor = float(request.form.get("valor", 0))
            desc = request.form.get("descricao", "")
            if valor <= 0:
                flash("Valor deve ser maior que zero.", "danger")
            else:
                conn.execute(
                    """INSERT INTO lancamentos_despesa
                    (loja_id, data, categoria_id, marca_id, valor, descricao, usuario_id)
                    VALUES(?,?,?,?,?,?,?)""",
                    (loja_id, data_lanc, cat_id, marca_id_d, valor, desc, uid),
                )
                conn.commit()
                flash("Despesa salva!", "success")
        elif acao == "aporte_sangria":
            ta = request.form.get("tipo_as")
            marca_id_as = request.form.get("marca_id") or None
            valor = float(request.form.get("valor", 0))
            desc = request.form.get("descricao", "")
            if ta not in ("aporte", "sangria"):
                flash("Tipo inválido.", "danger")
            elif valor <= 0:
                flash("Valor deve ser maior que zero.", "danger")
            else:
                conn.execute(
                    """INSERT INTO aporte_sangria
                    (loja_id, data, tipo, marca_id, valor, descricao, usuario_id)
                    VALUES(?,?,?,?,?,?,?)""",
                    (loja_id, data_lanc, ta, marca_id_as, valor, desc, uid),
                )
                conn.commit()
                flash("Registrado!", "success")

    recentes_cx = conn.execute("""
        SELECT lc.*, fp.nome as fp_nome, p.nome as plt_nome, m.nome as marca_nome
        FROM lancamentos_caixa lc
        JOIN formas_pagamento fp ON fp.id = lc.forma_pagamento_id
        LEFT JOIN plataformas p ON p.id = lc.plataforma_id
        LEFT JOIN marcas m ON m.id = lc.marca_id
        WHERE lc.loja_id = ? AND strftime('%Y', lc.data) = ?
        ORDER BY lc.data DESC, lc.id DESC LIMIT 50
    """, (loja_id, str(ano))).fetchall()

    recentes_desp = conn.execute("""
        SELECT ld.*, cd.nome as cat_nome, cd.tipo as cat_tipo, m.nome as marca_nome
        FROM lancamentos_despesa ld
        JOIN categorias_despesa cd ON cd.id = ld.categoria_id
        LEFT JOIN marcas m ON m.id = ld.marca_id
        WHERE ld.loja_id = ? AND strftime('%Y', ld.data) = ?
        ORDER BY ld.data DESC, ld.id DESC LIMIT 50
    """, (loja_id, str(ano))).fetchall()
    conn.close()

    # Meses permitidos para usuário loja
    meses_ok = list(range(1, 13))
    if tipo == "loja":
        db2 = get_db()
        perms = db2.execute(
            "SELECT mes FROM permissoes_meses WHERE usuario_id=? AND loja_id=? AND ano=?",
            (uid, loja_id, ano),
        ).fetchall()
        db2.close()
        meses_ok = [p["mes"] for p in perms]

    return render_template(
        "lancamentos.html",
        fps=fps,
        plats=plats,
        cats=cats,
        marcas=marcas_lista,
        loja_sel=loja_id,
        recentes_cx=recentes_cx,
        recentes_desp=recentes_desp,
        meses_ok=meses_ok,
    )


@app.route("/lancamentos/excluir/<string:tabela>/<int:lid>", methods=["POST"])
@login_required
@role_required("master", "gestor")
def excluir_lancamento(tabela, lid):
    if tabela not in {"lancamentos_caixa", "lancamentos_despesa", "aporte_sangria"}:
        abort(400)
    loja_id = loja_selecionada()
    conn = get_db()
    # Verifica se o lançamento pertence à loja selecionada
    r = conn.execute(f"SELECT loja_id FROM {tabela} WHERE id=?", (lid,)).fetchone()
    if not r or r["loja_id"] != loja_id:
        flash("Lançamento não encontrado nesta loja.", "danger")
    else:
        conn.execute(f"DELETE FROM {tabela} WHERE id=?", (lid,))
        conn.commit()
        flash("Excluído.", "info")
    conn.close()
    return redirect(url_for("lancamentos"))


# ──────────────────────────────────────────
#  USUÁRIOS E EMPRESAS
# ──────────────────────────────────────────
@app.route("/usuarios")
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def usuarios():
    tipo = session["tipo"]
    uid = session["usuario_id"]
    conn = get_db()

    if tipo == "master":
        lista = conn.execute("""
            SELECT u.* FROM usuarios u ORDER BY u.tipo, u.nome
        """).fetchall()
    else:
        # Gestor vê apenas usuários vinculados às lojas onde é gestor
        lojas_gestor = get_lojas_gestor(uid)
        if not lojas_gestor:
            conn.close()
            flash("Sem lojas como gestor.", "warning")
            return redirect(url_for("dashboard"))
        placeholders = ",".join("?" * len(lojas_gestor))
        lista = conn.execute(f"""
            SELECT DISTINCT u.* FROM usuarios u
            JOIN usuario_lojas ul ON ul.usuario_id = u.id
            WHERE ul.loja_id IN ({placeholders}) AND u.tipo IN ('loja','leitor')
            ORDER BY u.nome
        """, lojas_gestor).fetchall()

    # Enriquece com lojas vinculadas
    lista_enriquecida = []
    for u in lista:
        vinculos = conn.execute("""
            SELECT ul.perfil, l.nome as loja_nome, l.id as loja_id
            FROM usuario_lojas ul
            JOIN lojas l ON l.id = ul.loja_id
            WHERE ul.usuario_id = ?
            ORDER BY l.nome
        """, (u["id"],)).fetchall()
        lista_enriquecida.append({
            "id": u["id"], "login": u["login"], "nome": u["nome"],
            "tipo": u["tipo"], "ativo": u["ativo"],
            "criado_em": u["criado_em"],
            "vinculos": [dict(v) for v in vinculos],
        })

    # Master vê todas as lojas (inclusive inativas) para poder gerenciar
    if tipo == "master":
        lojas = [dict(r) for r in conn.execute("SELECT * FROM lojas ORDER BY ativo DESC, nome").fetchall()]
    else:
        lojas = [dict(r) for r in conn.execute("SELECT * FROM lojas WHERE ativo=1 ORDER BY nome").fetchall()]

    # Lojas disponíveis para vincular usuários (somente ativas)
    if tipo == "gestor":
        lojas_disponiveis = [dict(r) for r in conn.execute("""
            SELECT l.* FROM lojas l
            JOIN usuario_lojas ul ON ul.loja_id = l.id
            WHERE ul.usuario_id = ? AND ul.perfil = 'gestor' AND l.ativo = 1
            ORDER BY l.nome
        """, (uid,)).fetchall()]
    else:
        lojas_disponiveis = [l for l in lojas if l["ativo"]]

    conn.close()
    return render_template(
        "usuarios.html",
        lista=lista_enriquecida,
        lojas=lojas,
        lojas_disponiveis=lojas_disponiveis,
    )


@app.route("/usuarios/novo", methods=["POST"])
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def novo_usuario():
    tipo_sess = session["tipo"]
    uid_sess = session["usuario_id"]
    tipo_novo = request.form.get("tipo")
    login_v = request.form.get("login", "").strip()
    nome_v = request.form.get("nome", "").strip()
    senha_v = request.form.get("senha", "")

    if not login_v or not nome_v or not senha_v:
        flash("Preencha todos os campos.", "danger")
        return redirect(url_for("usuarios"))

    if len(senha_v) < 6:
        flash("Senha deve ter no mínimo 6 caracteres.", "danger")
        return redirect(url_for("usuarios"))

    # Gestor só pode criar loja ou leitor
    if tipo_sess == "gestor" and tipo_novo not in ("loja", "leitor"):
        flash("Sem permissão para criar este tipo de usuário.", "danger")
        return redirect(url_for("usuarios"))

    # Master pode criar gestor, loja, leitor
    if tipo_sess == "master" and tipo_novo not in ("gestor", "loja", "leitor"):
        flash("Tipo de usuário inválido.", "danger")
        return redirect(url_for("usuarios"))

    # Multilojas: coleta vínculos
    lojas_perfis = {}
    loja_ids = request.form.getlist("loja_ids")
    perfis = request.form.getlist("perfis")
    for i, lid in enumerate(loja_ids):
        if lid:
            p = perfis[i] if i < len(perfis) else tipo_novo
            lojas_perfis[int(lid)] = p

    # Se não veio multilojas, tenta formato simples
    if not lojas_perfis:
        loja_unica = request.form.get("loja_id")
        if loja_unica:
            lojas_perfis[int(loja_unica)] = tipo_novo

    # Gestor: valida que só vincula às lojas onde é gestor
    if tipo_sess == "gestor":
        minhas_lojas = set(get_lojas_gestor(uid_sess))
        for lid in lojas_perfis:
            if lid not in minhas_lojas:
                flash(f"Sem permissão para vincular à loja ID {lid}.", "danger")
                return redirect(url_for("usuarios"))

    conn = get_db()
    try:
        cur = conn.execute(
            "INSERT INTO usuarios(login, senha_hash, nome, tipo) VALUES(?,?,?,?)",
            (login_v, generate_password_hash(senha_v), nome_v, tipo_novo),
        )
        novo_id = cur.lastrowid

        for lid, perfil in lojas_perfis.items():
            conn.execute(
                "INSERT OR IGNORE INTO usuario_lojas(usuario_id, loja_id, perfil) VALUES(?,?,?)",
                (novo_id, lid, perfil),
            )

        conn.commit()
        flash(f"Usuário '{nome_v}' criado com sucesso!", "success")
    except Exception as e:
        flash(f"Erro ao criar usuário: {e}", "danger")
    conn.close()
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:uid>/editar", methods=["POST"])
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def editar_usuario(uid):
    tipo_sess = session["tipo"]
    uid_sess = session["usuario_id"]
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()

    if not u:
        flash("Usuário não encontrado.", "danger")
        conn.close()
        return redirect(url_for("usuarios"))

    # Gestor não pode editar master ou outros gestores
    if tipo_sess == "gestor" and u["tipo"] in ("master", "gestor"):
        flash("Sem permissão.", "danger")
        conn.close()
        return redirect(url_for("usuarios"))

    nome_v = request.form.get("nome", "").strip()
    if nome_v:
        conn.execute("UPDATE usuarios SET nome=? WHERE id=?", (nome_v, uid))

    # Atualiza vínculos (multilojas)
    loja_ids = request.form.getlist("loja_ids")
    perfis = request.form.getlist("perfis")

    if loja_ids:
        # Valida permissão do gestor
        if tipo_sess == "gestor":
            minhas_lojas = set(get_lojas_gestor(uid_sess))
            # Remove apenas vínculos das lojas que o gestor administra
            for lid in minhas_lojas:
                conn.execute(
                    "DELETE FROM usuario_lojas WHERE usuario_id=? AND loja_id=?",
                    (uid, lid),
                )
        else:
            conn.execute("DELETE FROM usuario_lojas WHERE usuario_id=?", (uid,))

        for i, lid in enumerate(loja_ids):
            if lid:
                perfil = perfis[i] if i < len(perfis) else u["tipo"]
                if tipo_sess == "gestor" and int(lid) not in minhas_lojas:
                    continue
                conn.execute(
                    "INSERT OR IGNORE INTO usuario_lojas(usuario_id, loja_id, perfil) VALUES(?,?,?)",
                    (uid, int(lid), perfil),
                )

    conn.commit()
    conn.close()
    flash("Usuário atualizado.", "success")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:uid>/ativar", methods=["POST"])
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def toggle_usuario(uid):
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if u and u["tipo"] != "master":
        novo = 0 if u["ativo"] else 1
        conn.execute("UPDATE usuarios SET ativo=? WHERE id=?", (novo, uid))
        conn.commit()
        flash(f"Usuário {'ativado' if novo else 'bloqueado'}.", "info")
    conn.close()
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:uid>/excluir", methods=["POST"])
@login_required
@role_required("master")
def excluir_usuario(uid):
    if uid == session["usuario_id"]:
        flash("Não é possível excluir o próprio usuário.", "danger")
        return redirect(url_for("usuarios"))
    conn = get_db()
    u = conn.execute("SELECT * FROM usuarios WHERE id=?", (uid,)).fetchone()
    if u and u["tipo"] == "master":
        flash("Não é possível excluir um usuário master.", "danger")
    elif u:
        conn.execute("DELETE FROM usuario_lojas WHERE usuario_id=?", (uid,))
        conn.execute("DELETE FROM permissoes_meses WHERE usuario_id=?", (uid,))
        conn.execute("DELETE FROM usuarios WHERE id=?", (uid,))
        conn.commit()
        flash("Usuário excluído.", "info")
    conn.close()
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:uid>/senha", methods=["POST"])
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def trocar_senha(uid):
    nova = request.form.get("nova_senha", "")
    if len(nova) < 6:
        flash("Senha deve ter no mínimo 6 caracteres.", "danger")
        return redirect(url_for("usuarios"))
    conn = get_db()
    conn.execute(
        "UPDATE usuarios SET senha_hash=? WHERE id=?",
        (generate_password_hash(nova), uid),
    )
    conn.commit()
    conn.close()
    flash("Senha alterada.", "success")
    return redirect(url_for("usuarios"))


@app.route("/usuarios/<int:uid>/permissoes", methods=["POST"])
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def salvar_permissoes(uid):
    ano_perm = int(request.form.get("ano_perm", ano_selecionado()))
    loja_perm = int(request.form.get("loja_perm", loja_selecionada()))
    meses_sel = request.form.getlist("meses")

    # Gestor: valida que é gestor desta loja
    if session["tipo"] == "gestor":
        minhas = set(get_lojas_gestor(session["usuario_id"]))
        if loja_perm not in minhas:
            flash("Sem permissão para gerenciar esta loja.", "danger")
            return redirect(url_for("usuarios"))

    conn = get_db()
    conn.execute(
        "DELETE FROM permissoes_meses WHERE usuario_id=? AND loja_id=? AND ano=?",
        (uid, loja_perm, ano_perm),
    )
    for m in meses_sel:
        conn.execute(
            "INSERT OR IGNORE INTO permissoes_meses(usuario_id, loja_id, ano, mes) VALUES(?,?,?,?)",
            (uid, loja_perm, ano_perm, int(m)),
        )
    conn.commit()
    conn.close()
    flash(f"Permissões de {ano_perm} salvas.", "success")
    return redirect(url_for("usuarios"))


# ──────────────────────────────────────────
#  LOJAS (criação dentro de Usuários e Empresas)
# ──────────────────────────────────────────
@app.route("/lojas/nova", methods=["POST"])
@login_required
@role_required("master")
def nova_loja():
    nome = request.form.get("loja_nome", "").strip()
    cnpj = request.form.get("loja_cnpj", "").strip()
    if not nome:
        flash("Nome da loja é obrigatório.", "danger")
        return redirect(url_for("usuarios"))

    conn = get_db()
    cur = conn.execute("INSERT INTO lojas(nome, cnpj) VALUES(?,?)", (nome, cnpj))
    nova_id = cur.lastrowid
    conn.commit()
    conn.close()

    # Copia parâmetros da loja 1 (principal) como base
    copiar_parametros_loja(1, nova_id)

    flash(f"Loja '{nome}' criada!", "success")
    return redirect(url_for("usuarios"))


@app.route("/lojas/<int:lid>/editar", methods=["POST"])
@login_required
@role_required("master")
def editar_loja(lid):
    conn = get_db()
    logo_path = None

    if "logo" in request.files:
        f = request.files["logo"]
        if f and f.filename and allowed_file(f.filename):
            fn = secure_filename(f"logo_{lid}_{f.filename}")
            f.save(os.path.join(app.config["UPLOAD_FOLDER"], fn))
            logo_path = fn

    campos = {
        "nome": request.form.get("nome", "").strip(),
        "cnpj": request.form.get("cnpj", "").strip(),
        "razao_social": request.form.get("razao_social", "").strip(),
        "endereco": request.form.get("endereco", "").strip(),
        "telefone": request.form.get("telefone", "").strip(),
        "email": request.form.get("email", "").strip(),
        "cor_primaria": request.form.get("cor_primaria", "#c8a96e"),
        "cor_secundaria": request.form.get("cor_secundaria", "#3ecf8e"),
        "cor_fundo": request.form.get("cor_fundo", "#0d0f14"),
        "cor_texto": request.form.get("cor_texto", "#e8eaf0"),
        "tema": request.form.get("tema", "escuro"),
    }
    if logo_path:
        campos["logo_path"] = logo_path

    sets = ", ".join(f"{k}=?" for k in campos)
    conn.execute(f"UPDATE lojas SET {sets} WHERE id=?", list(campos.values()) + [lid])
    conn.commit()
    conn.close()
    flash("Dados da empresa salvos!", "success")
    return redirect(url_for("usuarios"))


@app.route("/lojas/<int:lid>/desativar", methods=["POST"])
@login_required
@role_required("master")
def desativar_loja(lid):
    conn = get_db()
    conn.execute("UPDATE lojas SET ativo=0 WHERE id=?", (lid,))
    conn.commit()
    conn.close()
    flash("Loja desativada.", "info")
    return redirect(url_for("usuarios"))


@app.route("/lojas/<int:lid>/ativar", methods=["POST"])
@login_required
@role_required("master")
def ativar_loja(lid):
    conn = get_db()
    conn.execute("UPDATE lojas SET ativo=1 WHERE id=?", (lid,))
    conn.commit()
    conn.close()
    flash("Loja ativada.", "success")
    return redirect(url_for("usuarios"))


@app.route("/lojas/<int:lid>/excluir", methods=["POST"])
@login_required
@role_required("master")
def excluir_loja(lid):
    if lid == 1:
        flash("A loja principal não pode ser excluída.", "danger")
        return redirect(url_for("usuarios"))

    conn = get_db()
    # Remove todos os dados vinculados à loja
    conn.execute("DELETE FROM lancamentos_caixa WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM lancamentos_despesa WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM aporte_sangria WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM formas_pagamento WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM plataformas WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM categorias_despesa WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM marcas WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM tipos_faturamento WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM tipos_despesa WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM tipos_lancamento WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM configuracoes WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM permissoes_meses WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM usuario_lojas WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM api_keys WHERE loja_id=?", (lid,))
    conn.execute("DELETE FROM lojas WHERE id=?", (lid,))
    conn.commit()
    conn.close()
    flash("Loja excluída permanentemente.", "info")
    return redirect(url_for("usuarios"))


# ──────────────────────────────────────────
#  PARÂMETROS GERAIS
# ──────────────────────────────────────────
@app.route("/parametros", methods=["GET", "POST"])
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def parametros():
    tipo_sess = session["tipo"]
    uid_sess = session["usuario_id"]
    loja_id = loja_selecionada()
    conn = get_db()

    fps = conn.execute(
        "SELECT * FROM formas_pagamento WHERE ativo=1 AND loja_id=? ORDER BY nome",
        (loja_id,),
    ).fetchall()
    plats = conn.execute(
        "SELECT * FROM plataformas WHERE ativo=1 AND loja_id=? ORDER BY nome",
        (loja_id,),
    ).fetchall()
    cats = conn.execute(
        "SELECT * FROM categorias_despesa WHERE ativo=1 AND loja_id=? ORDER BY tipo, nome",
        (loja_id,),
    ).fetchall()
    marcas = conn.execute(
        "SELECT * FROM marcas WHERE ativo=1 AND loja_id=? ORDER BY nome",
        (loja_id,),
    ).fetchall()
    tipos_fat = conn.execute(
        "SELECT * FROM tipos_faturamento WHERE ativo=1 AND loja_id=? ORDER BY nome",
        (loja_id,),
    ).fetchall()
    tipos_desp = conn.execute(
        "SELECT * FROM tipos_despesa WHERE ativo=1 AND loja_id=? ORDER BY nome",
        (loja_id,),
    ).fetchall()
    tipos_lanc = conn.execute(
        "SELECT * FROM tipos_lancamento WHERE ativo=1 AND loja_id=? ORDER BY nome",
        (loja_id,),
    ).fetchall()

    api_keys = []
    if tipo_sess == "master":
        api_keys = conn.execute("""
            SELECT ak.*, l.nome as loja_nome FROM api_keys ak
            LEFT JOIN lojas l ON l.id = ak.loja_id
            ORDER BY ak.criado_em DESC
        """).fetchall()

    lojas = conn.execute("SELECT * FROM lojas WHERE ativo=1 ORDER BY nome").fetchall()

    if request.method == "POST":
        acao = request.form.get("acao", "")

        if acao == "config_geral":
            if tipo_sess in ("master", "gestor"):
                set_config("royalties", request.form.get("royalties", "0"), loja_id)
                set_config("verba_marketing", request.form.get("mkt", "0"), loja_id)
                set_config("meta_faturamento_mensal", request.form.get("meta", "50000"), loja_id)
                flash("Configurações salvas.", "success")

        elif acao == "taxa_fp" and tipo_sess in ("master", "gestor"):
            fp_id = request.form.get("fp_id")
            taxa = float(request.form.get("taxa", 0)) / 100
            conn.execute("UPDATE formas_pagamento SET taxa=? WHERE id=?", (taxa, fp_id))
            conn.commit()
            flash("Taxa atualizada.", "success")

        elif acao == "nova_fp":
            nome = request.form.get("fp_nome", "").strip()
            taxa = float(request.form.get("fp_taxa", 0)) / 100
            if nome:
                conn.execute("INSERT INTO formas_pagamento(nome, taxa, loja_id) VALUES(?,?,?)", (nome, taxa, loja_id))
                conn.commit()
                flash("Forma de pagamento criada.", "success")

        elif acao == "nova_plat":
            nome = request.form.get("plt_nome", "").strip()
            if nome:
                conn.execute("INSERT INTO plataformas(nome, loja_id) VALUES(?,?)", (nome, loja_id))
                conn.commit()
                flash("Plataforma criada.", "success")

        elif acao == "nova_cat":
            nome = request.form.get("cat_nome", "").strip()
            tipo_cat = request.form.get("cat_tipo", "outra")
            if nome:
                conn.execute("INSERT INTO categorias_despesa(nome, tipo, loja_id) VALUES(?,?,?)", (nome, tipo_cat, loja_id))
                conn.commit()
                flash("Categoria criada.", "success")

        elif acao == "nova_marca":
            nome = request.form.get("marca_nome", "").strip()
            if nome:
                conn.execute("INSERT INTO marcas(nome, loja_id) VALUES(?,?)", (nome, loja_id))
                conn.commit()
                flash("Marca criada.", "success")

        elif acao == "novo_tipo_fat":
            nome = request.form.get("tipo_fat_nome", "").strip()
            if nome:
                conn.execute("INSERT INTO tipos_faturamento(nome, loja_id) VALUES(?,?)", (nome, loja_id))
                conn.commit()
                flash("Tipo de faturamento criado.", "success")

        elif acao == "novo_tipo_desp":
            nome = request.form.get("tipo_desp_nome", "").strip()
            if nome:
                conn.execute("INSERT INTO tipos_despesa(nome, loja_id) VALUES(?,?)", (nome, loja_id))
                conn.commit()
                flash("Tipo de despesa criado.", "success")

        elif acao == "novo_tipo_lanc":
            nome = request.form.get("tipo_lanc_nome", "").strip()
            if nome:
                conn.execute("INSERT INTO tipos_lancamento(nome, loja_id) VALUES(?,?)", (nome, loja_id))
                conn.commit()
                flash("Tipo de lançamento criado.", "success")

        elif acao == "del_api_key" and tipo_sess == "master":
            kid = request.form.get("key_id")
            if kid:
                conn.execute("DELETE FROM api_keys WHERE id=?", (kid,))
                conn.commit()
                flash("API Key excluída.", "info")

        # Exclusões (deletam de verdade para master, desativam para gestor)
        elif acao.startswith("del_"):
            item_id = request.form.get("item_id")
            tabelas_del = {
                "del_fp": "formas_pagamento",
                "del_plat": "plataformas",
                "del_cat": "categorias_despesa",
                "del_marca": "marcas",
                "del_tipo_fat": "tipos_faturamento",
                "del_tipo_desp": "tipos_despesa",
                "del_tipo_lanc": "tipos_lancamento",
            }
            tab = tabelas_del.get(acao)
            if tab and item_id:
                if tipo_sess == "master":
                    # Master exclui permanentemente
                    conn.execute(f"DELETE FROM {tab} WHERE id=?", (item_id,))
                    conn.commit()
                    flash("Item excluído permanentemente.", "info")
                elif tipo_sess == "gestor":
                    conn.execute(f"UPDATE {tab} SET ativo=0 WHERE id=?", (item_id,))
                    conn.commit()
                    flash("Item desativado.", "info")

        elif acao == "nova_api_key" and tipo_sess == "master":
            nome = request.form.get("key_nome", "").strip()
            klid = request.form.get("key_loja") or None
            perms = ",".join(request.form.getlist("key_perms")) or "read"
            chave = gerar_api_key()
            conn.execute(
                "INSERT INTO api_keys(nome, chave, loja_id, permissoes, criado_por) VALUES(?,?,?,?,?)",
                (nome, chave, klid, perms, session["usuario_id"]),
            )
            conn.commit()
            flash(f"API Key criada: {chave}", "success")

        elif acao == "del_api_key" and tipo_sess == "master":
            kid = request.form.get("key_id")
            conn.execute("DELETE FROM api_keys WHERE id=?", (kid,))
            conn.commit()
            flash("API Key excluída.", "info")

        conn.close()
        return redirect(url_for("parametros"))

    conn.close()
    return render_template(
        "parametros.html",
        fps=fps, plats=plats, cats=cats,
        marcas=marcas, tipos_fat=tipos_fat,
        tipos_desp=tipos_desp, tipos_lanc=tipos_lanc,
        lojas=lojas, api_keys=api_keys,
        royalties=get_config("royalties", loja_id, "1500"),
        mkt=get_config("verba_marketing", loja_id, "0"),
        meta=get_config("meta_faturamento_mensal", loja_id, "50000"),
    )


# ──────────────────────────────────────────
#  MINHA SENHA
# ──────────────────────────────────────────
@app.route("/minha-senha", methods=["POST"])
@login_required
def minha_senha():
    nova = request.form.get("nova", "")
    atual = request.form.get("atual", "")
    conn = get_db()
    u = conn.execute(
        "SELECT * FROM usuarios WHERE id=?", (session["usuario_id"],)
    ).fetchone()
    if not check_password_hash(u["senha_hash"], atual):
        flash("Senha atual incorreta.", "danger")
    elif len(nova) < 6:
        flash("Senha deve ter no mínimo 6 caracteres.", "danger")
    else:
        conn.execute(
            "UPDATE usuarios SET senha_hash=? WHERE id=?",
            (generate_password_hash(nova), session["usuario_id"]),
        )
        conn.commit()
        flash("Senha alterada com sucesso!", "success")
    conn.close()
    return redirect(request.referrer or url_for("dashboard"))


# ──────────────────────────────────────────
#  STATIC – logos
# ──────────────────────────────────────────
@app.route("/static/logos/<path:filename>")
def logo_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ══════════════════════════════════════════
#  API REST PÚBLICA
# ══════════════════════════════════════════
@app.route("/api/docs")
@login_required
def api_docs():
    conn = get_db()
    lojas = conn.execute("SELECT id, nome FROM lojas WHERE ativo=1").fetchall()
    conn.close()
    return render_template("api_docs.html", lojas=lojas)


@app.route("/api/v1/status")
def api_status():
    return jsonify({
        "status": "ok",
        "versao": "3.0",
        "anos": f"{ANO_INICIO}-{ANO_FIM}",
        "fuso": "America/Sao_Paulo",
        "timestamp": agora_br().isoformat(),
    })


@app.route("/api/v1/dre/<int:loja_id>/<int:ano>/<int:mes>")
@api_auth("read")
def api_dre_pub(loja_id, ano, mes):
    if mes < 1 or mes > 12:
        return jsonify({"erro": "Mês inválido"}), 400
    if ano < ANO_INICIO or ano > ANO_FIM:
        return jsonify({"erro": f"Ano fora do intervalo {ANO_INICIO}-{ANO_FIM}"}), 400
    row = request.api_key_row
    if row["loja_id"] and row["loja_id"] != loja_id:
        return jsonify({"erro": "Sem acesso a esta loja"}), 403
    dre = calcular_dre(loja_id, ano, mes)
    return jsonify({
        "loja_id": loja_id, "ano": ano, "mes": mes,
        "nome_mes": MESES[mes - 1],
        "faturamento_bruto": round(dre["total_bruto"], 2),
        "total_taxas": round(dre["total_taxas"], 2),
        "faturamento_liquido": round(dre["fat_liquido"], 2),
        "total_despesas": round(dre["total_despesas"], 2),
        "royalties": dre["royalties"],
        "verba_marketing": dre["mkt"],
        "resultado": round(dre["resultado"], 2),
        "margem_percentual": round(dre["margem"], 2),
        "media_diaria": round(dre["media_diaria"], 2),
        "dias_com_lancamentos": dre["dias_lancados"],
        "faturamento_por_app": {
            k: {"total": round(v["total"], 2), "almoco": round(v["almoco"], 2),
                "jantar": round(v["jantar"], 2), "pos_meia_noite": round(v["pos"], 2)}
            for k, v in dre["fat_app"].items()
        },
        "despesas_por_tipo": {t: round(v, 2) for t, v in dre["totais_desp"].items()},
    })


@app.route("/api/v1/resumo-anual/<int:loja_id>/<int:ano>")
@api_auth("read")
def api_resumo_anual(loja_id, ano):
    if ano < ANO_INICIO or ano > ANO_FIM:
        return jsonify({"erro": f"Ano fora do intervalo {ANO_INICIO}-{ANO_FIM}"}), 400
    row = request.api_key_row
    if row["loja_id"] and row["loja_id"] != loja_id:
        return jsonify({"erro": "Sem acesso"}), 403
    resumo = resumo_anual(loja_id, ano)
    dados = resumo["meses"]
    return jsonify({
        "loja_id": loja_id, "ano": ano, "meses": dados,
        "fat_marca_anual": resumo["fat_marca_anual"],
        "desp_marca_anual": resumo["desp_marca_anual"],
        "totais": {
            "faturamento": round(sum(m["faturamento"] for m in dados), 2),
            "despesas": round(sum(m["despesas"] for m in dados), 2),
            "resultado": round(sum(m["resultado"] for m in dados), 2),
        },
    })


@app.route("/api/v1/lancamentos/caixa", methods=["POST"])
@api_auth("write")
def api_lancar_caixa():
    data = request.get_json()
    if not data:
        return jsonify({"erro": "JSON inválido"}), 400
    for f in ["loja_id", "data", "turno", "forma_pagamento_id", "valor"]:
        if f not in data:
            return jsonify({"erro": f"Campo obrigatório ausente: {f}"}), 400
    if data["turno"] not in ("almoco", "jantar", "pos_meia_noite"):
        return jsonify({"erro": "turno: almoco | jantar | pos_meia_noite"}), 400
    ano_lanc = int(data["data"].split("-")[0])
    if ano_lanc < ANO_INICIO or ano_lanc > ANO_FIM:
        return jsonify({"erro": f"Ano fora do intervalo {ANO_INICIO}-{ANO_FIM}"}), 400
    row = request.api_key_row
    if row["loja_id"] and row["loja_id"] != data["loja_id"]:
        return jsonify({"erro": "Sem acesso"}), 403
    conn = get_db()
    taxa_r = conn.execute(
        "SELECT taxa FROM formas_pagamento WHERE id=?", (data["forma_pagamento_id"],)
    ).fetchone()
    taxa_val = taxa_r["taxa"] if taxa_r else 0
    cur = conn.execute(
        """INSERT INTO lancamentos_caixa
        (loja_id, data, turno, forma_pagamento_id, plataforma_id, marca_id, valor, taxa_aplicada, usuario_id)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (data["loja_id"], data["data"], data["turno"], data["forma_pagamento_id"],
         data.get("plataforma_id"), data.get("marca_id"), float(data["valor"]), taxa_val, row["criado_por"]),
    )
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return jsonify({"sucesso": True, "id": lid}), 201


@app.route("/api/v1/lancamentos/despesa", methods=["POST"])
@api_auth("write")
def api_lancar_despesa():
    data = request.get_json()
    if not data:
        return jsonify({"erro": "JSON inválido"}), 400
    for f in ["loja_id", "data", "categoria_id", "valor"]:
        if f not in data:
            return jsonify({"erro": f"Campo obrigatório: {f}"}), 400
    row = request.api_key_row
    if row["loja_id"] and row["loja_id"] != data["loja_id"]:
        return jsonify({"erro": "Sem acesso"}), 403
    conn = get_db()
    cur = conn.execute(
        """INSERT INTO lancamentos_despesa
        (loja_id, data, categoria_id, marca_id, valor, descricao, usuario_id)
        VALUES(?,?,?,?,?,?,?)""",
        (data["loja_id"], data["data"], data["categoria_id"],
         data.get("marca_id"), float(data["valor"]), data.get("descricao", ""), row["criado_por"]),
    )
    conn.commit()
    lid = cur.lastrowid
    conn.close()
    return jsonify({"sucesso": True, "id": lid}), 201


@app.route("/api/v1/lojas")
@api_auth("read")
def api_lojas():
    conn = get_db()
    r = conn.execute("SELECT id, nome, cnpj, razao_social FROM lojas WHERE ativo=1").fetchall()
    conn.close()
    return jsonify([dict(x) for x in r])


@app.route("/api/v1/formas-pagamento")
@api_auth("read")
def api_fps():
    lid = request.api_key_row["loja_id"] or request.args.get("loja_id", 1, type=int)
    conn = get_db()
    r = conn.execute("SELECT id, nome, taxa FROM formas_pagamento WHERE ativo=1 AND loja_id=?", (lid,)).fetchall()
    conn.close()
    return jsonify([dict(x) for x in r])


@app.route("/api/v1/categorias-despesa")
@api_auth("read")
def api_cats():
    lid = request.api_key_row["loja_id"] or request.args.get("loja_id", 1, type=int)
    conn = get_db()
    r = conn.execute("SELECT id, nome, tipo FROM categorias_despesa WHERE ativo=1 AND loja_id=?", (lid,)).fetchall()
    conn.close()
    return jsonify([dict(x) for x in r])


@app.route("/api/v1/plataformas")
@api_auth("read")
def api_plats():
    lid = request.api_key_row["loja_id"] or request.args.get("loja_id", 1, type=int)
    conn = get_db()
    r = conn.execute("SELECT id, nome FROM plataformas WHERE ativo=1 AND loja_id=?", (lid,)).fetchall()
    conn.close()
    return jsonify([dict(x) for x in r])


# ── API interna (gráficos) ──
@app.route("/api/anual/<int:loja_id>")
@login_required
def api_anual(loja_id):
    ano = int(request.args.get("ano", ano_selecionado()))
    resumo = resumo_anual(loja_id, ano)
    return jsonify(resumo)


@app.route("/api/dre/<int:loja_id>/<int:mes>")
@login_required
def api_dre_interno(loja_id, mes):
    ano = int(request.args.get("ano", ano_selecionado()))
    dre = calcular_dre(loja_id, ano, mes)
    return jsonify({
        **{k: v for k, v in dre.items() if k not in ("fat_bruto", "fat_app", "despesas")},
        "fat_bruto": dict(dre["fat_bruto"]),
        "fat_app": {k: dict(v) for k, v in dre["fat_app"].items()},
        "despesas": {t: dict(v) for t, v in dre["despesas"].items()},
    })


@app.route("/api/permissoes/<int:uid>")
@login_required
@role_required("master", "gestor")
@perfil_loja_required("master", "gestor")
def api_permissoes(uid):
    ano_perm = int(request.args.get("ano", ano_selecionado()))
    loja_perm = int(request.args.get("loja", loja_selecionada()))
    conn = get_db()
    rows = conn.execute(
        "SELECT mes FROM permissoes_meses WHERE usuario_id=? AND loja_id=? AND ano=?",
        (uid, loja_perm, ano_perm),
    ).fetchall()
    conn.close()
    return jsonify({"meses": [r["mes"] for r in rows], "ano": ano_perm, "loja_id": loja_perm})


@app.route("/api/cnpj/<cnpj>")
@login_required
@role_required("master")
def consultar_cnpj(cnpj):
    import urllib.request as ur
    cnpj_limpo = re.sub(r"\D", "", cnpj)
    if len(cnpj_limpo) != 14:
        return jsonify({"erro": "CNPJ inválido"}), 400
    try:
        with ur.urlopen(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}", timeout=5) as r:
            return jsonify(json.loads(r.read()))
    except Exception:
        return jsonify({"erro": "Não foi possível consultar. Preencha manualmente.", "cnpj": cnpj_limpo}), 422


# ── Rota legada para manter compatibilidade ──
@app.route("/configuracoes")
@login_required
def configuracoes_redirect():
    return redirect(url_for("parametros"))


# ══════════════════════════════════════════
#  INICIALIZAÇÃO (executada tanto no Gunicorn quanto diretamente)
# ══════════════════════════════════════════
init_db()
migrar_db()

if __name__ == "__main__":
    print("\n  Sistema de DRE | 2026–2036")
    print("  http://localhost:5000\n")
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    app.run(debug=debug, host="0.0.0.0", port=5000)
