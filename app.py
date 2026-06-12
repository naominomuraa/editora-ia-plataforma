from flask import (Flask, render_template_string, request, redirect,
                   url_for, session, send_from_directory, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
import sqlite3, os, json
from functools import wraps

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'users.db')
EBOOKS_DIR = BASE_DIR

# ── Ebook metadata ─────────────────────────────────────────────────────────────
with open(os.path.join(BASE_DIR, 'ebooks_metadata.json'), 'r', encoding='utf-8') as _f:
    EBOOKS = json.load(_f)

CATEGORIES: dict = {}
for _eb in EBOOKS:
    CATEGORIES.setdefault(_eb['categoria'], []).append(_eb)

CAT_ICONS = {
    'IA e Tecnologia':        'bi-cpu-fill',
    'Negócios':               'bi-briefcase-fill',
    'Finanças':               'bi-cash-coin',
    'Importação':             'bi-globe-americas',
    'Liderança':              'bi-star-fill',
    'Desenvolvimento Pessoal':'bi-lightbulb-fill',
    'Varejo':                 'bi-bag-fill',
    'Saúde e Gestão':         'bi-heart-pulse-fill',
}
CAT_COLORS = {
    'IA e Tecnologia':        '#00BCD4',
    'Negócios':               '#F39C12',
    'Finanças':               '#27AE60',
    'Importação':             '#FF6B35',
    'Liderança':              '#C0392B',
    'Desenvolvimento Pessoal':'#9B59B6',
    'Varejo':                 '#E91E63',
    'Saúde e Gestão':         '#16A085',
}

# ── Embedded templates ────────────────────────────────────────────────────────
CSS = """
:root{--brand:#6C3483;--brand-dark:#4a2360;--brand-light:#9b59b6;--sidebar-bg:#16213e;--sidebar-w:240px;--nav-h:56px}
body{background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.login-bg{background:linear-gradient(135deg,#16213e 0%,#0f3460 50%,#533483 100%)}
.login-card{background:#fff;border-radius:16px;padding:2.5rem;width:100%;max-width:400px}
.brand-icon{width:64px;height:64px;background:linear-gradient(135deg,var(--brand),var(--brand-light));border-radius:16px;display:flex;align-items:center;justify-content:center;margin:0 auto;font-size:2rem;color:#fff}
.brand-title{font-size:1.6rem;font-weight:800;color:#1a1a2e;letter-spacing:-.5px}
.brand-sub{color:#6c757d;font-size:.9rem;margin-bottom:0}
.btn-brand{background:var(--brand);color:#fff;border:none}.btn-brand:hover{background:var(--brand-dark);color:#fff}
.text-brand{color:var(--brand)}
.top-nav{background:var(--sidebar-bg);height:var(--nav-h);position:sticky;top:0;z-index:1030;box-shadow:0 2px 8px rgba(0,0,0,.3)}
.sidebar{width:var(--sidebar-w);min-width:var(--sidebar-w);background:#1a1a2e;height:calc(100vh - var(--nav-h));position:sticky;top:var(--nav-h);overflow-y:auto;border-right:1px solid rgba(255,255,255,.05)}
.sidebar-header{color:rgba(255,255,255,.4);font-size:.7rem;letter-spacing:.08em}
.sidebar-link{display:flex;align-items:center;padding:.55rem 1rem;color:rgba(255,255,255,.65);text-decoration:none;font-size:.875rem;transition:background .15s,color .15s;border-left:3px solid transparent}
.sidebar-link:hover{background:rgba(255,255,255,.07);color:#fff}
.sidebar-link.active{background:rgba(108,52,131,.25);color:#fff;border-left-color:var(--brand-light)}
.sidebar-link .badge{background:rgba(255,255,255,.15);font-size:.7rem;font-weight:500}
.cat-icon-badge{width:36px;height:36px;border-radius:10px;display:flex;align-items:center;justify-content:center;font-size:1.1rem;flex-shrink:0}
.ebook-card{background:#fff;border-radius:12px;box-shadow:0 1px 4px rgba(0,0,0,.08);overflow:hidden;display:flex;flex-direction:column;transition:transform .15s,box-shadow .15s}
.ebook-card:hover{transform:translateY(-2px);box-shadow:0 6px 20px rgba(0,0,0,.12)}
.ebook-card-accent{height:4px;width:100%}
.ebook-card-body{padding:1rem;display:flex;flex-direction:column;flex-grow:1}
.ebook-number{font-size:.75rem;font-weight:600;letter-spacing:.05em;color:#adb5bd}
.ebook-title{font-size:.95rem;font-weight:700;line-height:1.3;color:#1a1a2e;margin-bottom:.25rem;flex-grow:1}
.ebook-sub{font-size:.78rem;color:#868e96;line-height:1.4;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.btn-download{background:color-mix(in srgb,var(--btn-color,#6C3483) 12%,transparent);color:var(--btn-color,#6C3483);border:1px solid color-mix(in srgb,var(--btn-color,#6C3483) 30%,transparent);font-size:.8rem;font-weight:600;border-radius:8px;transition:background .15s,color .15s}
.btn-download:hover{background:var(--btn-color,#6C3483);color:#fff;border-color:var(--btn-color,#6C3483)}
.table th{font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:#6c757d}
.sidebar::-webkit-scrollbar{width:4px}.sidebar::-webkit-scrollbar-track{background:transparent}.sidebar::-webkit-scrollbar-thumb{background:rgba(255,255,255,.15);border-radius:4px}
"""

BASE_TMPL = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{% block title %}Editora IA{% endblock %}</title>
  <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
  <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
  <style>""" + CSS + """</style>
</head>
<body>
{% block body %}{% endblock %}
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js"></script>
{% block scripts %}{% endblock %}
</body></html>"""

LOGIN_TMPL = """{% extends 'base' %}
{% block title %}Login · Editora IA{% endblock %}
{% block body %}
<div class="login-bg d-flex align-items-center justify-content-center min-vh-100">
  <div class="login-card shadow-lg">
    <div class="text-center mb-4">
      <div class="brand-icon mb-3"><i class="bi bi-book-half"></i></div>
      <h1 class="brand-title">Editora IA</h1>
      <p class="brand-sub">Biblioteca de Ebooks</p>
    </div>
    {% if error %}
    <div class="alert alert-danger d-flex align-items-center gap-2 py-2">
      <i class="bi bi-exclamation-circle-fill"></i><span>{{ error }}</span>
    </div>
    {% endif %}
    <form method="POST">
      <div class="mb-3">
        <label class="form-label fw-semibold text-muted small">USUÁRIO</label>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-person text-muted"></i></span>
          <input type="text" name="username" class="form-control border-start-0 ps-0" placeholder="seu usuário" autofocus required>
        </div>
      </div>
      <div class="mb-4">
        <label class="form-label fw-semibold text-muted small">SENHA</label>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-lock text-muted"></i></span>
          <input type="password" name="password" class="form-control border-start-0 ps-0" placeholder="••••••••" required>
        </div>
      </div>
      <button type="submit" class="btn btn-brand w-100 py-2 fw-semibold">
        <i class="bi bi-box-arrow-in-right me-2"></i>Entrar
      </button>
    </form>
    <p class="text-center text-muted small mt-4 mb-0">Acesso restrito · Apenas usuários autorizados</p>
  </div>
</div>
{% endblock %}"""

DASHBOARD_TMPL = """{% extends 'base' %}
{% block title %}Biblioteca · Editora IA{% endblock %}
{% block body %}
<nav class="navbar navbar-dark top-nav px-4">
  <a class="navbar-brand d-flex align-items-center gap-2" href="/dashboard">
    <i class="bi bi-book-half fs-5"></i><span class="fw-bold">Editora IA</span>
  </a>
  <div class="d-flex align-items-center gap-3">
    <span class="text-white-50 small d-none d-sm-inline"><i class="bi bi-book me-1"></i>{{ total }} ebooks</span>
    <a href="/download/Editora_IA_50_Ebooks.zip" class="btn btn-sm btn-outline-light">
      <i class="bi bi-download me-1"></i>Baixar Todos
    </a>
    {% if is_adm %}
    <a href="/admin" class="btn btn-sm btn-warning text-dark fw-semibold">
      <i class="bi bi-shield-fill me-1"></i>Admin
    </a>
    {% endif %}
    <div class="dropdown">
      <button class="btn btn-sm btn-dark dropdown-toggle" data-bs-toggle="dropdown">
        <i class="bi bi-person-circle me-1"></i>{{ uname }}
      </button>
      <ul class="dropdown-menu dropdown-menu-end">
        <li><span class="dropdown-item-text text-muted small">Logado como <strong>{{ uname }}</strong></span></li>
        <li><hr class="dropdown-divider"></li>
        <li><a class="dropdown-item text-danger" href="/logout"><i class="bi bi-box-arrow-right me-2"></i>Sair</a></li>
      </ul>
    </div>
  </div>
</nav>
<div class="d-flex" style="min-height:calc(100vh - 56px)">
  <aside class="sidebar d-none d-lg-flex flex-column">
    <div class="sidebar-header px-3 pt-3 pb-2">Categorias</div>
    <nav class="flex-grow-1">
      <a href="#" class="sidebar-link active" onclick="showAll(event)">
        <i class="bi bi-grid-fill me-2"></i><span>Todos</span><span class="badge ms-auto">{{ total }}</span>
      </a>
      {% for cat, ebooks in categories.items() %}
      <a href="#" class="sidebar-link" onclick="filterCat(event, {{ loop.index }})">
        <i class="bi {{ cat_icons.get(cat, 'bi-folder') }} me-2" style="color:{{ cat_colors.get(cat,'#6c757d') }}"></i>
        <span>{{ cat }}</span><span class="badge ms-auto">{{ ebooks|length }}</span>
      </a>
      {% endfor %}
    </nav>
  </aside>
  <main class="flex-grow-1 p-4" style="overflow-y:auto">
    {% for cat, ebooks in categories.items() %}
    <section class="category-section mb-5" id="cat-{{ loop.index }}">
      <div class="d-flex align-items-center gap-2 mb-3">
        <div class="cat-icon-badge" style="background:{{ cat_colors.get(cat,'#6c757d') }}20;color:{{ cat_colors.get(cat,'#6c757d') }}">
          <i class="bi {{ cat_icons.get(cat,'bi-folder') }}"></i>
        </div>
        <h2 class="h5 mb-0 fw-bold">{{ cat }}</h2>
        <span class="badge text-bg-secondary">{{ ebooks|length }}</span>
      </div>
      <div class="row g-3">
        {% for eb in ebooks %}
        <div class="col-12 col-sm-6 col-xl-4">
          <div class="ebook-card h-100">
            <div class="ebook-card-accent" style="background:{{ cat_colors.get(cat,'#6c757d') }}"></div>
            <div class="ebook-card-body">
              <div class="ebook-number text-muted small mb-1">#{{ '%02d'|format(eb.id) }}</div>
              <h3 class="ebook-title">{{ eb.titulo }}</h3>
              <p class="ebook-sub text-muted small mb-3">{{ eb.subtitulo }}</p>
              <a href="/download/{{ eb.filename }}" class="btn btn-sm btn-download w-100"
                 style="--btn-color:{{ cat_colors.get(cat,'#6C3483') }}">
                <i class="bi bi-download me-1"></i>Baixar PDF
              </a>
            </div>
          </div>
        </div>
        {% endfor %}
      </div>
    </section>
    {% endfor %}
  </main>
</div>
{% endblock %}
{% block scripts %}
<script>
function showAll(e){e.preventDefault();document.querySelectorAll('.sidebar-link').forEach(l=>l.classList.remove('active'));e.currentTarget.classList.add('active');document.querySelectorAll('.category-section').forEach(s=>s.style.display='');}
function filterCat(e,n){e.preventDefault();document.querySelectorAll('.sidebar-link').forEach(l=>l.classList.remove('active'));e.currentTarget.classList.add('active');document.querySelectorAll('.category-section').forEach((s,i)=>s.style.display=i+1==n?'':'none');}
</script>
{% endblock %}"""

ADMIN_TMPL = """{% extends 'base' %}
{% block title %}Admin · Editora IA{% endblock %}
{% block body %}
<nav class="navbar navbar-dark top-nav px-4">
  <a class="navbar-brand d-flex align-items-center gap-2" href="/dashboard">
    <i class="bi bi-book-half fs-5"></i><span class="fw-bold">Editora IA</span>
    <span class="badge bg-warning text-dark ms-1 small">Admin</span>
  </a>
  <div class="d-flex gap-2">
    <a href="/dashboard" class="btn btn-sm btn-outline-light"><i class="bi bi-grid me-1"></i>Biblioteca</a>
    <a href="/logout" class="btn btn-sm btn-dark"><i class="bi bi-box-arrow-right me-1"></i>Sair</a>
  </div>
</nav>
<div class="container-fluid py-4 px-4" style="max-width:960px">
  {% set msgs = {'added':('success','bi-check-circle-fill','Usuário criado.'),'exists':('danger','bi-exclamation-circle-fill','Usuário já existe.'),'deleted':('info','bi-trash-fill','Usuário removido.'),'self':('warning','bi-shield-exclamation','Não pode remover a própria conta.'),'empty':('danger','bi-exclamation-circle-fill','Usuário e senha obrigatórios.'),'pwd_ok':('success','bi-key-fill','Senha alterada.'),'empty_pass':('danger','bi-exclamation-circle-fill','Nova senha vazia.')} %}
  {% if msg and msg in msgs %}{% set tp,ic,tx = msgs[msg] %}
  <div class="alert alert-{{ tp }} d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi {{ ic }}"></i><span>{{ tx }}</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>{% endif %}
  <h1 class="h4 fw-bold mb-4"><i class="bi bi-shield-fill me-2 text-warning"></i>Gerenciar Usuários</h1>
  <div class="card shadow-sm mb-4">
    <div class="card-header fw-semibold"><i class="bi bi-person-plus-fill me-2 text-brand"></i>Adicionar Usuário</div>
    <div class="card-body">
      <form method="POST" action="/admin/add">
        <div class="row g-3">
          <div class="col-md-3"><label class="form-label small fw-semibold text-muted">USUÁRIO *</label><input type="text" name="username" class="form-control" placeholder="nome_usuario" required></div>
          <div class="col-md-3"><label class="form-label small fw-semibold text-muted">SENHA *</label><input type="password" name="password" class="form-control" placeholder="••••••••" required></div>
          <div class="col-md-3"><label class="form-label small fw-semibold text-muted">E-MAIL</label><input type="email" name="email" class="form-control" placeholder="email@ex.com"></div>
          <div class="col-md-2 d-flex align-items-end"><div class="form-check mb-2"><input type="checkbox" name="is_admin" id="is_admin" class="form-check-input"><label for="is_admin" class="form-check-label small">Admin</label></div></div>
          <div class="col-md-1 d-flex align-items-end"><button type="submit" class="btn btn-brand w-100"><i class="bi bi-plus-lg"></i></button></div>
        </div>
      </form>
    </div>
  </div>
  <div class="card shadow-sm">
    <div class="card-header fw-semibold d-flex justify-content-between align-items-center">
      <span><i class="bi bi-people-fill me-2 text-brand"></i>Usuários</span>
      <span class="badge bg-secondary">{{ users|length }}</span>
    </div>
    <div class="table-responsive">
      <table class="table table-hover align-middle mb-0">
        <thead class="table-light"><tr><th>Usuário</th><th>E-mail</th><th>Perfil</th><th>Desde</th><th class="text-end">Ações</th></tr></thead>
        <tbody>
          {% for u in users %}
          <tr>
            <td><i class="bi bi-person-circle text-muted me-1"></i><strong>{{ u.username }}</strong>{% if u.id==cur_id %}<span class="badge bg-secondary ms-1 small">você</span>{% endif %}</td>
            <td class="text-muted small">{{ u.email or '—' }}</td>
            <td>{% if u.is_admin %}<span class="badge bg-warning text-dark"><i class="bi bi-shield-fill me-1"></i>Admin</span>{% else %}<span class="badge bg-light text-muted border">Usuário</span>{% endif %}</td>
            <td class="text-muted small">{{ (u.created_at or '')[:10] }}</td>
            <td class="text-end">
              <button class="btn btn-sm btn-outline-secondary me-1" data-bs-toggle="modal" data-bs-target="#pwd-{{ u.id }}"><i class="bi bi-key"></i></button>
              {% if u.id!=cur_id %}<form method="POST" action="/admin/delete/{{ u.id }}" class="d-inline" onsubmit="return confirm('Remover {{ u.username }}?')"><button type="submit" class="btn btn-sm btn-outline-danger"><i class="bi bi-trash"></i></button></form>{% endif %}
            </td>
          </tr>
          <div class="modal fade" id="pwd-{{ u.id }}" tabindex="-1">
            <div class="modal-dialog modal-sm"><div class="modal-content">
              <div class="modal-header"><h6 class="modal-title"><i class="bi bi-key me-2"></i>Senha · {{ u.username }}</h6><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
              <form method="POST" action="/admin/pwd/{{ u.id }}">
                <div class="modal-body"><input type="password" name="pwd" class="form-control" placeholder="Nova senha" required></div>
                <div class="modal-footer"><button type="button" class="btn btn-sm btn-secondary" data-bs-dismiss="modal">Cancelar</button><button type="submit" class="btn btn-sm btn-brand">Salvar</button></div>
              </form>
            </div></div>
          </div>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
{% endblock %}"""

# ── Flask app ─────────────────────────────────────────────────────────────────
TMPLS = {'base': BASE_TMPL, 'login': LOGIN_TMPL, 'dashboard': DASHBOARD_TMPL, 'admin': ADMIN_TMPL}

app = Flask(__name__)
app.jinja_loader = DictLoader(TMPLS)
app.secret_key = os.environ.get('SECRET_KEY', 'editora-ia-change-me-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True

# ── DB helpers ────────────────────────────────────────────────────────────────
def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        email TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    n = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if n == 0:
        u = os.environ.get('ADMIN_USERNAME', 'admin')
        p = os.environ.get('ADMIN_PASSWORD', 'admin123')
        db.execute('INSERT INTO users(username,password_hash,is_admin) VALUES(?,?,1)',
                   (u, generate_password_hash(p)))
        db.commit()
        print(f'[init] Admin criado: {u}')
    db.close()

# ── Decorators ────────────────────────────────────────────────────────────────
def login_required(f):
    from functools import wraps
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in session: return redirect('/login')
        return f(*a, **kw)
    return w

def admin_required(f):
    from functools import wraps
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in session: return redirect('/login')
        if not session.get('adm'): abort(403)
        return f(*a, **kw)
    return w

def R(tmpl, **ctx):
    return render_template_string(TMPLS[tmpl], **ctx)

# ── Routes ────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return redirect('/dashboard' if 'uid' in session else '/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'uid' in session: return redirect('/dashboard')
    error = None
    if request.method == 'POST':
        u = request.form.get('username', '').strip()
        p = request.form.get('password', '')
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE username=?', (u,)).fetchone()
        db.close()
        if row and check_password_hash(row['password_hash'], p):
            session.permanent = True
            session['uid']   = row['id']
            session['uname'] = row['username']
            session['adm']   = bool(row['is_admin'])
            return redirect('/dashboard')
        error = 'Usuário ou senha incorretos.'
    return R('login', error=error)

@app.route('/logout')
def logout():
    session.clear(); return redirect('/login')

@app.route('/dashboard')
@login_required
def dashboard():
    return R('dashboard',
             categories=CATEGORIES, cat_icons=CAT_ICONS, cat_colors=CAT_COLORS,
             uname=session['uname'], is_adm=session.get('adm', False), total=len(EBOOKS))

@app.route('/download/<path:filename>')
@login_required
def download(filename):
    fn = os.path.basename(filename)
    if not (fn.endswith('.pdf') or fn.endswith('.zip')): abort(400)
    return send_from_directory(EBOOKS_DIR, fn, as_attachment=True)

@app.route('/admin')
@admin_required
def admin():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY is_admin DESC, created_at DESC').fetchall()
    db.close()
    return R('admin', users=users, uname=session['uname'],
             msg=request.args.get('msg', ''), cur_id=session['uid'])

@app.route('/admin/add', methods=['POST'])
@admin_required
def add_user():
    u = request.form.get('username', '').strip()
    p = request.form.get('password', '')
    e = request.form.get('email', '').strip()
    adm = 1 if request.form.get('is_admin') else 0
    if not u or not p: return redirect('/admin?msg=empty')
    db = get_db()
    try:
        db.execute('INSERT INTO users(username,email,password_hash,is_admin) VALUES(?,?,?,?)',
                   (u, e, generate_password_hash(p), adm)); db.commit(); msg='added'
    except sqlite3.IntegrityError: msg='exists'
    db.close()
    return redirect(f'/admin?msg={msg}')

@app.route('/admin/delete/<int:uid>', methods=['POST'])
@admin_required
def del_user(uid):
    if uid == session['uid']: return redirect('/admin?msg=self')
    db = get_db()
    db.execute('DELETE FROM users WHERE id=?', (uid,)); db.commit(); db.close()
    return redirect('/admin?msg=deleted')

@app.route('/admin/pwd/<int:uid>', methods=['POST'])
@admin_required
def chg_pwd(uid):
    p = request.form.get('pwd', '')
    if not p: return redirect('/admin?msg=empty_pass')
    db = get_db()
    db.execute('UPDATE users SET password_hash=? WHERE id=?', (generate_password_hash(p), uid))
    db.commit(); db.close()
    return redirect('/admin?msg=pwd_ok')

# ── Start ─────────────────────────────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
