"""
app.py – Sistema de DRE
Flask + SQLite | 4 níveis de usuário | Multilojas | Fuso: America/Sao_Paulo
"""
import os
import json
import re
import secrets
import csv
import io
import time
import urllib.request as urlreq
from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, jsonify, abort, send_from_directory,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
from datetime import datetime, timezone, timedelta
from collections import defaultdict

from database import (
    get_db, init_db, migrar_db,
    calcular_dre, resumo_anual, resumo_todos_anos, comparativo_marcas,
    usuario_pode_mes, get_config, set_config,
    get_config_mensal, set_config_mensal,
    MESES, ANOS, ANO_INICIO, ANO_FIM, TIPOS_USUARIO,
    get_tema, gerar_api_key, validar_api_key,
    get_lojas_usuario, get_perfil_loja, get_lojas_gestor,
    copiar_parametros_loja,
    get_talentos_notas, salvar_talento_nota, get_acesso_talentos,
    get_bancos_talentos, get_bancos_usuario, get_banco_by_slug,
    salvar_banco_talentos as db_salvar_banco_talentos,
    excluir_banco_talentos, set_banco_sync, set_usuario_bancos,
    get_modulos_sistema, get_modulos_usuario_ids, set_usuario_modulos_acesso,
    salvar_modulo_sistema, excluir_modulo_sistema,
    salvar_chat_mensagem, get_chat_historico,
    salvar_sugestao, get_sugestoes, marcar_sugestao_lida,
    get_grupos_lista, get_grupo_by_slug, get_tema_grupo,
    salvar_tema_grupo, salvar_grupo,
)

# ──────────────────────────────────────────
#  APP
# ──────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))
app.config["UPLOAD_FOLDER"] = os.path.join(os.path.dirname(__file__), "static", "logos")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024  # 5 MB
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
FUSO_BR = timezone(timedelta(hours=-3))

# ── Rate limiting para login ──
_login_attempts = defaultdict(list)  # {ip: [timestamps]}
_LOGIN_MAX_ATTEMPTS = 8
_LOGIN_WINDOW = 300  # 5 minutos


# ── CSRF Protection ──
def gerar_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = secrets.token_hex(32)
    return session["_csrf_token"]

app.jinja_env.globals["csrf_token"] = gerar_csrf_token

# Rotas isentas de CSRF (APIs externas, webhooks)
_CSRF_EXEMPT = {"/api/", "/suporte-chat/"}

@app.before_request
def verificar_csrf():
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return
    # Isentar rotas de API
    for prefix in _CSRF_EXEMPT:
        if request.path.startswith(prefix):
            return
    token = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or token != session.get("_csrf_token"):
        # Fallback: se não tem sessão ativa (login), aceitar
        if "usuario_id" not in session:
            return
        abort(403)


@app.after_request
def security_headers(response):
    """Adiciona headers de segurança em todas as respostas."""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if os.environ.get("FLASK_ENV") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


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

    # Acesso ao Banco de Talentos
    acesso_talentos = {}
    bancos_usuario = []
    if uid:
        bancos_usuario = get_bancos_usuario(uid, tipo)
        acesso_talentos = get_acesso_talentos(uid, tipo)

    # Grupo e tema do grupo
    grupo_id = session.get("grupo_id", 1)
    tema_grupo = get_tema_grupo(grupo_id)

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
        acesso_talentos=acesso_talentos,
        bancos_usuario=bancos_usuario,
        acesso_banco_talentos=len(bancos_usuario) > 0,
        grupo_id=grupo_id,
        tema_grupo=tema_grupo,
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
def _pos_login_redirect(uid, tipo):
    """Após login, todos vão para a tela inicial do hub."""
    return redirect(url_for("home"))


@app.route("/", methods=["GET", "POST"])
def login():
    if "usuario_id" in session:
        return _pos_login_redirect(session["usuario_id"], session.get("tipo", ""))

    erro = None
    if request.method == "POST":
        ip = request.remote_addr or "unknown"
        agora_ts = time.time()
        _login_attempts[ip] = [t for t in _login_attempts[ip] if agora_ts - t < _LOGIN_WINDOW]
        if len(_login_attempts[ip]) >= _LOGIN_MAX_ATTEMPTS:
            erro = "Muitas tentativas de login. Aguarde alguns minutos."
            return render_template("login.html", erro=erro)

        lv = request.form.get("login", "").strip()
        sv = request.form.get("senha", "")
        conn = get_db()
        u = conn.execute("SELECT * FROM usuarios WHERE login=? AND ativo=1", (lv,)).fetchone()
        conn.close()

        dummy_hash = "pbkdf2:sha256:600000$x$0000000000000000000000000000000000000000000000000000000000000000"
        check_password_hash(dummy_hash, sv) if not u else None
        senha_ok = check_password_hash(u["senha_hash"], sv) if u else False

        if u and senha_ok:
            loja_inicial = 1
            if u["tipo"] != "master":
                lojas = get_lojas_usuario(u["id"], u["tipo"])
                if lojas:
                    loja_inicial = lojas[0]["id"]

            conn2 = get_db()
            conn2.execute(
                "UPDATE usuarios SET ultimo_acesso=? WHERE id=?",
                (agora_br().strftime("%Y-%m-%d %H:%M:%S"), u["id"]),
            )
            conn2.commit()
            conn2.close()

            session.update(
                usuario_id=u["id"],
                nome=u["nome"],
                tipo=u["tipo"],
                nivel=u["nivel"] if u["nivel"] else u["tipo"],
                grupo_id=u["grupo_id"] if u["grupo_id"] else 1,
                loja_id=loja_inicial,
                ano_sel=agora_br().year,
                tema_preferido=u["tema_preferido"] or "escuro",
            )
            return _pos_login_redirect(u["id"], u["tipo"])

        _login_attempts[ip].append(agora_ts)
        erro = "Login ou senha incorretos."

    return render_template("login.html", erro=erro)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/home")
@login_required
def home():
    uid = session["usuario_id"]
    tipo = session.get("tipo", "")
    conn = get_db()
    u = conn.execute("SELECT acesso_dre, acesso_banco_talentos FROM usuarios WHERE id=?", (uid,)).fetchone()
    conn.close()
    acesso_dre_u = u["acesso_dre"] if u else 1
    bancos = get_bancos_usuario(uid, tipo)
    tem_bt = bool(bancos)
    pode_usuarios = tipo in ("master", "gestor")
    return render_template(
        "home.html",
        acesso_dre=acesso_dre_u,
        tem_bt=tem_bt,
        bancos_bt=bancos,
        pode_usuarios=pode_usuarios,
    )


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
        elif acao == "fechar_caixa":
            turno = request.form.get("turno")
            if turno and data_lanc:
                conn.execute(
                    "DELETE FROM abertura_caixa WHERE loja_id=? AND data=? AND turno=?",
                    (loja_id, data_lanc, turno),
                )
                conn.commit()
                nomes_t = {"almoco": "Almoço", "jantar": "Jantar", "pos_meia_noite": "Pós-meia-noite"}
                flash(f"Caixa {nomes_t.get(turno, turno)} fechado com sucesso!", "success")
            else:
                flash("Erro ao fechar caixa.", "danger")

        elif acao == "abertura_caixa":
            turno = request.form.get("turno")
            valor = float(request.form.get("valor_abertura", 0))
            if turno not in ("almoco", "jantar", "pos_meia_noite"):
                flash("Turno inválido.", "danger")
            elif valor < 0:
                flash("Valor não pode ser negativo.", "danger")
            else:
                from datetime import datetime as dt_cls, timezone as tz_cls, timedelta as td_cls
                agora = dt_cls.now(tz_cls(td_cls(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
                conn.execute("""
                    INSERT INTO abertura_caixa(loja_id, data, turno, valor, usuario_id, criado_em)
                    VALUES(?,?,?,?,?,?)
                    ON CONFLICT(loja_id, data, turno) DO UPDATE SET
                        valor=excluded.valor, usuario_id=excluded.usuario_id, criado_em=excluded.criado_em
                """, (loja_id, data_lanc, turno, valor, uid, agora))
                conn.commit()
                flash("Abertura de caixa registrada!", "success")

        elif acao == "caixa":
            fp_id = request.form.get("forma_pagamento_id")
            plt_id = request.form.get("plataforma_id") or None
            marca_id = request.form.get("marca_id") or None
            turno = request.form.get("turno") or None
            valor = float(request.form.get("valor", 0))
            # Validar que existe abertura de caixa
            if not turno or not data_lanc:
                # Tenta detectar pela última abertura geral da loja
                ab = conn.execute(
                    "SELECT turno, data FROM abertura_caixa WHERE loja_id=? ORDER BY data DESC, id DESC LIMIT 1",
                    (loja_id,),
                ).fetchone()
                if ab:
                    turno = turno or ab["turno"]
                    data_lanc = data_lanc or ab["data"]
            if not turno or not data_lanc:
                flash("Nenhum caixa aberto. Registre uma abertura de caixa primeiro.", "danger")
            elif turno not in ("almoco", "jantar", "pos_meia_noite"):
                flash("Nenhum caixa aberto. Registre uma abertura de caixa primeiro.", "danger")
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

    aberturas = conn.execute("""
        SELECT ac.*, u.nome as usuario_nome
        FROM abertura_caixa ac
        JOIN usuarios u ON u.id = ac.usuario_id
        WHERE ac.loja_id = ? AND strftime('%Y', ac.data) = ?
        ORDER BY ac.data DESC, ac.id DESC LIMIT 50
    """, (loja_id, str(ano))).fetchall()

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
        aberturas=[dict(r) for r in aberturas],
        meses_ok=meses_ok,
    )


@app.route("/lancamentos/excluir/<string:tabela>/<int:lid>", methods=["POST"])
@login_required
@role_required("master", "gestor")
def excluir_lancamento(tabela, lid):
    if tabela not in {"lancamentos_caixa", "lancamentos_despesa", "aporte_sangria", "abertura_caixa"}:
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


@app.route("/lancamentos/turno-ativo")
@login_required
def turno_ativo():
    """Retorna o turno ativo (última abertura) para uma data ou o mais recente."""
    loja_id = loja_selecionada()
    data = request.args.get("data", "")
    nomes = {"almoco": "Almoço (CX 1)", "jantar": "Jantar (CX 2)", "pos_meia_noite": "Pós-meia-noite (CX 3)"}
    conn = get_db()
    if data:
        ab = conn.execute(
            "SELECT turno, data, valor FROM abertura_caixa WHERE loja_id=? AND data=? ORDER BY id DESC LIMIT 1",
            (loja_id, data),
        ).fetchone()
    else:
        # Retorna o caixa mais recente (para modal de login)
        ab = conn.execute(
            "SELECT turno, data, valor FROM abertura_caixa WHERE loja_id=? ORDER BY data DESC, id DESC LIMIT 1",
            (loja_id,),
        ).fetchone()
    conn.close()
    if ab:
        return jsonify({
            "turno": ab["turno"],
            "turno_nome": nomes.get(ab["turno"], ab["turno"]),
            "data": ab["data"],
            "valor": ab["valor"],
        })
    return jsonify({"turno": None})


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

    # Enriquece com lojas vinculadas e permissões de bancos
    lista_enriquecida = []
    for u in lista:
        vinculos = conn.execute("""
            SELECT ul.perfil, l.nome as loja_nome, l.id as loja_id
            FROM usuario_lojas ul
            JOIN lojas l ON l.id = ul.loja_id
            WHERE ul.usuario_id = ?
            ORDER BY l.nome
        """, (u["id"],)).fetchall()
        banco_ids_rows = conn.execute(
            "SELECT banco_id FROM usuario_bancos_talentos WHERE usuario_id=?", (u["id"],)
        ).fetchall()
        modulo_ids_u = conn.execute(
            "SELECT modulo_id FROM usuario_modulos WHERE usuario_id=?", (u["id"],)
        ).fetchall()
        lista_enriquecida.append({
            "id": u["id"], "login": u["login"], "nome": u["nome"],
            "tipo": u["tipo"], "ativo": u["ativo"],
            "criado_em": u["criado_em"],
            "ultimo_acesso": u["ultimo_acesso"] if "ultimo_acesso" in u.keys() else None,
            "vinculos": [dict(v) for v in vinculos],
            "banco_ids": [b["banco_id"] for b in banco_ids_rows],
            "acesso_banco_talentos": bool(banco_ids_rows),
            "acesso_dre": u["acesso_dre"] if "acesso_dre" in u.keys() else 1,
            "modulo_ids": [r["modulo_id"] for r in modulo_ids_u],
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

    bancos_talentos_list = [dict(b) for b in conn.execute("SELECT * FROM bancos_talentos WHERE ativo=1 ORDER BY nome").fetchall()] if tipo == "master" else []
    modulos_sistema_list = get_modulos_sistema() if tipo == "master" else []
    conn.close()
    return render_template(
        "usuarios.html",
        lista=lista_enriquecida,
        lojas=lojas,
        lojas_disponiveis=lojas_disponiveis,
        bancos_talentos_list=bancos_talentos_list,
        modulos_sistema_list=modulos_sistema_list,
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

    # Master pode criar master, gestor, loja, leitor
    if tipo_sess == "master" and tipo_novo not in ("master", "gestor", "loja", "leitor"):
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

        # Módulos de acesso (só master pode definir)
        if tipo_sess == "master":
            modulo_ids = [int(m) for m in request.form.getlist("modulo_ids") if m]
            set_usuario_modulos_acesso(conn, novo_id, modulo_ids)

        # Permissões Banco de Talentos (só master pode definir)
        if tipo_sess == "master":
            banco_ids = [int(b) for b in request.form.getlist("banco_talentos_ids") if b]
            conn.execute("DELETE FROM usuario_bancos_talentos WHERE usuario_id=?", (novo_id,))
            for bid in banco_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO usuario_bancos_talentos(usuario_id, banco_id) VALUES(?,?)",
                    (novo_id, bid)
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

    # Atualiza módulos de acesso (só master pode alterar)
    if tipo_sess == "master":
        modulo_ids = [int(m) for m in request.form.getlist("modulo_ids") if m]
        set_usuario_modulos_acesso(conn, uid, modulo_ids)

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

    # Permissões Banco de Talentos (só master pode definir)
    if tipo_sess == "master":
        banco_ids = [int(b) for b in request.form.getlist("banco_talentos_ids") if b]
        conn.execute("DELETE FROM usuario_bancos_talentos WHERE usuario_id=?", (uid,))
        for bid in banco_ids:
            conn.execute(
                "INSERT OR IGNORE INTO usuario_bancos_talentos(usuario_id, banco_id) VALUES(?,?)",
                (uid, bid)
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
        "cor_primaria": request.form.get("cor_primaria", "#3d8f60"),
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
                set_config("meta_faturamento_mensal", request.form.get("meta", "50000"), loja_id)
                # Salvar royalties e marketing por mês
                ano_cfg = int(request.form.get("ano_config", agora_br().year))
                for m in range(1, 13):
                    val_roy = request.form.get(f"royalties_{m}", "")
                    val_mkt = request.form.get(f"mkt_{m}", "")
                    if val_roy != "":
                        set_config_mensal(loja_id, ano_cfg, m, "royalties", float(val_roy or 0))
                    if val_mkt != "":
                        set_config_mensal(loja_id, ano_cfg, m, "verba_marketing", float(val_mkt or 0))
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

        conn.close()
        return redirect(url_for("parametros"))

    conn.close()
    ano_config = int(request.args.get("ano_config", agora_br().year))
    royalties_mensal = get_config_mensal(loja_id, ano_config, "royalties")
    mkt_mensal = get_config_mensal(loja_id, ano_config, "verba_marketing")
    return render_template(
        "parametros.html",
        fps=fps, plats=plats, cats=cats,
        marcas=marcas, tipos_fat=tipos_fat,
        tipos_desp=tipos_desp, tipos_lanc=tipos_lanc,
        lojas=lojas, api_keys=api_keys,
        meta=get_config("meta_faturamento_mensal", loja_id, "50000"),
        royalties_mensal=royalties_mensal,
        mkt_mensal=mkt_mensal,
        ano_config=ano_config,
        anos=ANOS,
        meses=MESES,
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


# ──────────────────────────────────────────
#  BANCO DE TALENTOS – módulo separado (/talentos/)
# ──────────────────────────────────────────
# Cache em memória para candidatos por slug
_sheets_cache = {}  # {slug: {"data": [...], "ts": timestamp}}
SHEETS_CACHE_TTL = 30  # segundos


def parse_sheets_url(url):
    """Converte qualquer URL do Google Sheets em URL de CSV direto."""
    if not url:
        return None
    if "tqx=out:csv" in url:
        return url
    match_id = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', url)
    if not match_id:
        return None
    sheet_id = match_id.group(1)
    match_gid = re.search(r'[#&?]gid=(\d+)', url)
    gid = match_gid.group(1) if match_gid else "0"
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/gviz/tq?tqx=out:csv&gid={gid}"


def fetch_candidatos(slug, fonte_url):
    """Busca candidatos do Google Sheets, com cache por slug."""
    now = time.time()
    cached = _sheets_cache.get(slug)
    if cached and (now - cached["ts"]) < SHEETS_CACHE_TTL:
        return cached["data"]
    csv_url = parse_sheets_url(fonte_url)
    if not csv_url:
        return cached["data"] if cached else []
    try:
        req = urlreq.Request(csv_url, headers={"User-Agent": "Mozilla/5.0"})
        with urlreq.urlopen(req, timeout=15) as resp:
            raw = resp.read().decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(raw))
        rows = [{k.strip(): (v.strip() if v else "") for k, v in r.items() if k} for r in reader]
        _sheets_cache[slug] = {"data": rows, "ts": now}
        return rows
    except Exception:
        return cached["data"] if cached else []


def extrair_unidade(unidade_interesse):
    """Extrai o nome da unidade do campo 'Unidade interesse' (parte antes do @)."""
    if not unidade_interesse:
        return ""
    if "@" in unidade_interesse:
        return unidade_interesse.split("@")[0].strip()
    return unidade_interesse.strip()


def _parse_candidatos(rows):
    """Converte linhas CSV em lista de candidatos normalizada."""
    candidatos, areas = [], set()
    for i, r in enumerate(rows):
        uni_raw = r.get("Unidade interesse", r.get("Unidade Interesse", r.get("Unidade_interesse", "")))
        area = r.get("Area de interesse", r.get("Area_de_interesse", "")).strip()
        if area:
            areas.add(area)
        candidatos.append({
            "idx": i,
            "data": r.get("Data", ""),
            "status": r.get("Status", ""),
            "nome": r.get("Nome", ""),
            "email": r.get("Email", r.get("email", "")),
            "telefone": r.get("Telefone", ""),
            "telefone_recado": r.get("Telefone recado", r.get("Telefone Recado", "")),
            "cep": r.get("Cep", r.get("CEP", "")),
            "cidade": r.get("Cidade", ""),
            "bairro": r.get("Bairro", ""),
            "unidade_interesse": uni_raw,
            "unidade": extrair_unidade(uni_raw),
            "area_interesse": area,
            "tem_experiencia": r.get("Tem experiencia", r.get("Tem_experiencia", "")),
            "tempo_experiencia": r.get("Tempo de experiencia", r.get("Tempo_de_experiencia", "")),
            "disponibilidade": r.get("Disponibilidade", ""),
            "pretensao_salarial": r.get("Pretensao salarial", r.get("Pretensao_salarial", "")),
            "resumo_experiencias": r.get("Resumo experiencias", r.get("Resumo_experiencias", "")),
        })
    return candidatos, sorted(areas)


@app.route("/talentos/")
@login_required
def talentos_index():
    uid = session["usuario_id"]
    tipo = session["tipo"]
    bancos = get_bancos_usuario(uid, tipo)
    if not bancos:
        flash("Você não tem acesso ao Banco de Talentos.", "danger")
        return redirect(url_for("dashboard"))
    return render_template("talentos/index.html", bancos=bancos)


@app.route("/modulos/salvar", methods=["POST"])
@login_required
@role_required("master")
def modulo_salvar():
    nome = request.form.get("nome", "").strip()
    slug = request.form.get("slug", "").strip()
    descricao = request.form.get("descricao", "").strip()
    icone = request.form.get("icone", "bi-puzzle").strip()
    mid = request.form.get("modulo_id") or None
    if not nome or not slug:
        flash("Nome e slug são obrigatórios.", "danger")
        return redirect(url_for("usuarios"))
    try:
        salvar_modulo_sistema(nome, slug, descricao, icone, int(mid) if mid else None)
        flash(f"Módulo '{nome}' salvo.", "success")
    except Exception as e:
        flash(f"Erro: {e}", "danger")
    return redirect(url_for("usuarios"))


@app.route("/modulos/<int:mid>/excluir", methods=["POST"])
@login_required
@role_required("master")
def modulo_excluir(mid):
    excluir_modulo_sistema(mid)
    flash("Módulo excluído.", "success")
    return redirect(url_for("usuarios"))


@app.route("/talentos/admin/")
@login_required
@role_required("master")
def talentos_admin():
    bancos = get_bancos_talentos(apenas_ativos=False)
    return render_template("talentos/admin.html", bancos=bancos)


@app.route("/talentos/admin/salvar", methods=["POST"])
@login_required
@role_required("master")
def talentos_admin_salvar():
    banco_id = request.form.get("banco_id") or None
    nome = request.form.get("nome", "").strip()
    slug = request.form.get("slug", "").strip()
    fonte_url = request.form.get("fonte_url", "").strip()
    if not nome or not slug:
        flash("Nome e slug são obrigatórios.", "danger")
        return redirect(url_for("talentos_admin"))
    if not re.match(r'^[a-z0-9\-]+$', slug):
        flash("Slug deve conter apenas letras minúsculas, números e hífens.", "danger")
        return redirect(url_for("talentos_admin"))
    try:
        db_salvar_banco_talentos(nome, slug, fonte_url, banco_id)
        flash("Banco de talentos salvo.", "success")
    except Exception as e:
        flash(f"Erro ao salvar: {e}", "danger")
    return redirect(url_for("talentos_admin"))


@app.route("/talentos/admin/<int:bid>/excluir", methods=["POST"])
@login_required
@role_required("master")
def talentos_admin_excluir(bid):
    excluir_banco_talentos(bid)
    flash("Banco de talentos removido.", "info")
    return redirect(url_for("talentos_admin"))


@app.route("/talentos/admin/<int:bid>/ativar", methods=["POST"])
@login_required
@role_required("master")
def talentos_admin_ativar(bid):
    conn = get_db()
    conn.execute("UPDATE bancos_talentos SET ativo=1 WHERE id=?", (bid,))
    conn.commit()
    conn.close()
    flash("Banco de talentos reativado.", "success")
    return redirect(url_for("talentos_admin"))


@app.route("/talentos/<slug>")
@login_required
def talentos_banco(slug):
    uid = session["usuario_id"]
    tipo = session["tipo"]
    banco = get_banco_by_slug(slug)
    if not banco:
        flash("Banco de talentos não encontrado.", "danger")
        return redirect(url_for("talentos_index"))
    bancos = get_bancos_usuario(uid, tipo)
    if not any(b["slug"] == slug for b in bancos):
        flash("Você não tem acesso a este Banco de Talentos.", "danger")
        return redirect(url_for("talentos_index"))
    rows = fetch_candidatos(slug, banco.get("fonte_url", ""))
    candidatos, areas = _parse_candidatos(rows)
    notas = get_talentos_notas(slug)
    filtro_area = request.args.get("area", "")
    return render_template(
        "talentos/banco.html",
        banco=banco,
        candidatos=candidatos,
        notas=notas,
        areas=areas,
        filtro_area=filtro_area,
        bancos=bancos,
    )


@app.route("/talentos/<slug>/nota", methods=["POST"])
@login_required
def talentos_nota(slug):
    uid = session["usuario_id"]
    tipo = session["tipo"]
    banco = get_banco_by_slug(slug)
    if not banco:
        return redirect(url_for("talentos_index"))
    bancos = get_bancos_usuario(uid, tipo)
    if not any(b["slug"] == slug for b in bancos):
        flash("Sem permissão.", "danger")
        return redirect(url_for("talentos_index"))
    email = request.form.get("email", "").strip()
    if not email:
        flash("Candidato não identificado.", "danger")
        return redirect(url_for("talentos_banco", slug=slug))
    salvar_talento_nota(
        slug, email,
        1 if request.form.get("ex_funcionario") else 0,
        1 if request.form.get("contratou") else 0,
        request.form.get("observacao", "").strip(),
        uid,
    )
    flash("Informações do candidato atualizadas.", "success")
    area = request.form.get("filtro_area", "")
    return redirect(url_for("talentos_banco", slug=slug, area=area))


@app.route("/talentos/<slug>/sync")
@login_required
def talentos_sync(slug):
    uid = session["usuario_id"]
    tipo = session["tipo"]
    bancos = get_bancos_usuario(uid, tipo)
    if not any(b["slug"] == slug for b in bancos):
        flash("Sem permissão.", "danger")
        return redirect(url_for("talentos_index"))
    _sheets_cache.pop(slug, None)
    banco = get_banco_by_slug(slug)
    if banco:
        set_banco_sync(banco["id"])
    flash("Banco de talentos sincronizado.", "success")
    return redirect(url_for("talentos_banco", slug=slug))


# Rotas antigas → redirecionam para novo módulo
@app.route("/banco-talentos")
@app.route("/banco-talentos/<banco>")
@login_required
def banco_talentos(banco="sunomono"):
    return redirect(url_for("talentos_banco", slug=banco))


# ══════════════════════════════════════════
#  CHAT DE SUPORTE (Qwen via DashScope)
# ══════════════════════════════════════════
_chat_system_prompt = ""
_prompt_path = os.path.join(os.path.dirname(__file__), "chat_system_prompt.txt")
if os.path.exists(_prompt_path):
    with open(_prompt_path, "r", encoding="utf-8") as _f:
        _chat_system_prompt = _f.read()

# Rate limiter simples: max 20 msgs/min por usuário
_chat_rate = {}
CHAT_RATE_LIMIT = 20
CHAT_RATE_WINDOW = 60


def _check_rate(uid):
    now = time.time()
    entries = _chat_rate.get(uid, [])
    entries = [t for t in entries if now - t < CHAT_RATE_WINDOW]
    if len(entries) >= CHAT_RATE_LIMIT:
        return False
    entries.append(now)
    _chat_rate[uid] = entries
    return True


def chamar_llm(mensagens):
    """Chama a API Groq (LLM) para gerar resposta."""
    api_key = os.environ.get("GROQ_API_KEY", "")
    if not api_key:
        return "Desculpe, o serviço de chat não está configurado no momento. Por favor, entre em contato com o administrador."

    payload = json.dumps({
        "model": "llama-3.3-70b-versatile",
        "messages": mensagens,
        "max_tokens": 1024,
        "temperature": 0.7,
    }).encode("utf-8")

    req = urlreq.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0",
        },
    )
    try:
        with urlreq.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data.get("choices", [{}])[0].get("message", {}).get("content", "Desculpe, não consegui gerar uma resposta.")
    except Exception as e:
        app.logger.error(f"Erro Groq API: {e}")
        return "Desculpe, estou com dificuldade para processar sua mensagem. Tente novamente em alguns instantes."


@app.route("/suporte-chat")
@login_required
def suporte_chat():
    sid = request.args.get("session_id", "")
    if not sid:
        sid = secrets.token_hex(16)
    historico = get_chat_historico(sid)
    sugestoes_count = 0
    if session.get("tipo") == "master":
        sugestoes_count = len(get_sugestoes(lida=0))
    return render_template(
        "suporte_chat.html",
        session_id=sid,
        historico=historico,
        sugestoes_count=sugestoes_count,
    )


@app.route("/suporte-chat/historico")
@login_required
def suporte_chat_historico():
    sid = request.args.get("session_id", "")
    if not sid:
        return jsonify({"historico": []})
    historico = get_chat_historico(sid)
    return jsonify({"historico": historico})


@app.route("/suporte-chat/enviar", methods=["POST"])
@login_required
def suporte_chat_enviar():
    uid = session["usuario_id"]
    if not _check_rate(uid):
        return jsonify({"resposta": "Você enviou muitas mensagens em pouco tempo. Aguarde um momento."}), 429

    data = request.get_json(silent=True) or {}
    msg = (data.get("mensagem") or "").strip()[:2000]
    sid = (data.get("session_id") or "").strip()
    if not msg or not sid:
        return jsonify({"erro": "Mensagem ou sessão inválida."}), 400

    # Saudação inicial — salva localmente sem chamar Qwen
    if msg == "__SAUDACAO_INICIAL__":
        saudacao = "Olá! 👋 Bem-vindo(a) ao suporte do Sistema de DRE!\n\nCom quem tenho o prazer de falar?"
        salvar_chat_mensagem(sid, uid, "assistant", saudacao)
        return jsonify({"resposta": ""})

    # Salva mensagem do usuário
    salvar_chat_mensagem(sid, uid, "user", msg)

    # Monta histórico para o Qwen
    historico = get_chat_historico(sid)
    mensagens = [{"role": "system", "content": _chat_system_prompt}]
    for h in historico:
        mensagens.append({"role": h["role"], "content": h["content"]})

    # Chama Qwen
    resposta = chamar_llm(mensagens)

    # Salva resposta
    salvar_chat_mensagem(sid, uid, "assistant", resposta)

    return jsonify({"resposta": resposta})


@app.route("/suporte-chat/sugestao", methods=["POST"])
@login_required
def suporte_chat_sugestao():
    uid = session["usuario_id"]
    nome = session.get("nome", "")
    data = request.get_json(silent=True) or {}
    sugestao = (data.get("sugestao") or "").strip()[:1000]
    if not sugestao:
        return jsonify({"erro": "Sugestão vazia."}), 400
    salvar_sugestao(uid, nome, sugestao)
    return jsonify({"ok": True})


@app.route("/suporte-chat/avaliar", methods=["POST"])
@login_required
def suporte_chat_avaliar():
    uid = session["usuario_id"]
    nome = session.get("nome", "")
    data = request.get_json(silent=True) or {}
    estrelas = int(data.get("estrelas", 0))
    feedback = (data.get("feedback") or "").strip()[:1000]
    if estrelas < 1 or estrelas > 5:
        return jsonify({"erro": "Avaliação inválida."}), 400
    # Salva como sugestão tipo 'avaliacao'
    from datetime import datetime, timezone, timedelta
    agora = datetime.now(timezone(timedelta(hours=-3))).strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db()
    conn.execute(
        "INSERT INTO chat_sugestoes(usuario_id, nome_usuario, sugestao, criado_em, estrelas, tipo) VALUES(?,?,?,?,?,?)",
        (uid, nome, feedback or f"Avaliação: {estrelas} estrela(s)", agora, estrelas, "avaliacao"),
    )
    conn.commit()
    conn.close()
    return jsonify({"ok": True})


@app.route("/suporte-chat/sugestoes")
@login_required
@role_required("master")
def suporte_chat_sugestoes():
    sugestoes = get_sugestoes()
    return render_template("suporte_sugestoes.html", sugestoes=sugestoes)


@app.route("/suporte-chat/sugestoes/<int:sid>/lida", methods=["POST"])
@login_required
@role_required("master")
def suporte_marcar_lida(sid):
    marcar_sugestao_lida(sid)
    flash("Sugestão marcada como lida.", "success")
    return redirect(url_for("suporte_chat_sugestoes"))


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
    print("\n  Sistema de DRE")
    print("  http://localhost:5000\n")
    debug = os.environ.get("FLASK_ENV", "production") == "development"
    app.run(debug=debug, host="0.0.0.0", port=5000)
