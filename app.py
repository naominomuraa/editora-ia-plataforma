from flask import (Flask, render_template_string, request, redirect,
                   url_for, session, send_from_directory, abort)
from werkzeug.security import generate_password_hash, check_password_hash
from jinja2 import DictLoader
import sqlite3, os, json, secrets, smtplib, io
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta
from functools import wraps

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

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

# ── Email config ───────────────────────────────────────────────────────────────
MAIL_USER = os.environ.get('MAIL_USERNAME', '')
MAIL_PASS = os.environ.get('MAIL_PASSWORD', '')

def _send_email(to_addr, subject, html):
    """Send via Gmail SMTP. Returns True on success."""
    if not (MAIL_USER and MAIL_PASS and to_addr):
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From']    = f'Clube do Saber <{MAIL_USER}>'
        msg['To']      = to_addr
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        with smtplib.SMTP('smtp.gmail.com', 587) as s:
            s.starttls()
            s.login(MAIL_USER, MAIL_PASS)
            s.send_message(msg)
        return True
    except Exception as ex:
        print(f'[mail] {ex}')
        return False

def _welcome_html(username, password, login_url):
    return f'''<div style="font-family:Arial,sans-serif;max-width:500px;margin:auto">
  <div style="background:linear-gradient(135deg,#16213e,#533483);padding:28px 32px;border-radius:12px 12px 0 0;text-align:center">
    <h1 style="color:#fff;margin:0;font-size:1.4rem">&#128218; Clube do Saber</h1>
    <p style="color:rgba(255,255,255,.7);margin:6px 0 0;font-size:.9rem">Biblioteca de Ebooks Profissionais</p>
  </div>
  <div style="background:#fff;padding:28px 32px;border-radius:0 0 12px 12px;border:1px solid #eee;border-top:none">
    <h2 style="color:#1a1a2e;margin-top:0">Bem-vindo(a)! &#127881;</h2>
    <p style="color:#555;line-height:1.6">Seu acesso ao <strong>Clube do Saber</strong> foi criado. Guarde seus dados:</p>
    <div style="background:#f8f9fa;border:1px solid #e9ecef;border-radius:8px;padding:16px;margin:16px 0">
      <p style="margin:4px 0;color:#555;font-size:.9rem"><strong>Usu&#225;rio:</strong> {username}</p>
      <p style="margin:4px 0;color:#555;font-size:.9rem"><strong>Senha:</strong> {password}</p>
    </div>
    <a href="{login_url}" style="display:block;background:#6C3483;color:#fff;text-align:center;padding:13px;border-radius:8px;text-decoration:none;font-weight:700">
      &#128273; Acessar a Plataforma
    </a>
    <p style="color:#bbb;font-size:.75rem;margin:20px 0 0;text-align:center">N&#227;o compartilhe suas credenciais</p>
  </div>
</div>'''

def _reset_html(reset_url):
    return f'''<div style="font-family:Arial,sans-serif;max-width:500px;margin:auto">
  <div style="background:linear-gradient(135deg,#16213e,#533483);padding:28px 32px;border-radius:12px 12px 0 0;text-align:center">
    <h1 style="color:#fff;margin:0;font-size:1.4rem">&#128218; Clube do Saber</h1>
  </div>
  <div style="background:#fff;padding:28px 32px;border-radius:0 0 12px 12px;border:1px solid #eee;border-top:none">
    <h2 style="color:#1a1a2e;margin-top:0">&#128273; Redefinir Senha</h2>
    <p style="color:#555;line-height:1.6">Clique no bot&#227;o abaixo para criar uma nova senha. O link &#233; v&#225;lido por <strong>1 hora</strong>.</p>
    <a href="{reset_url}" style="display:block;background:#6C3483;color:#fff;text-align:center;padding:13px;border-radius:8px;text-decoration:none;font-weight:700;margin:20px 0">
      Redefinir Minha Senha
    </a>
    <p style="color:#bbb;font-size:.75rem;margin:0;text-align:center">Se n&#227;o solicitou, ignore este e-mail.</p>
  </div>
</div>'''

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
  <title>{% block title %}Clube do Saber{% endblock %}</title>
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
{% block title %}Login · Clube do Saber{% endblock %}
{% block body %}
<div class="login-bg d-flex align-items-center justify-content-center min-vh-100">
  <div class="login-card shadow-lg">
    <div class="text-center mb-4">
      <div class="brand-icon mb-3"><i class="bi bi-book-half"></i></div>
      <h1 class="brand-title">Clube do Saber</h1>
      <p class="brand-sub">Biblioteca de Ebooks Profissionais</p>
    </div>
    {% if error %}
    <div class="alert alert-danger d-flex align-items-center gap-2 py-2">
      <i class="bi bi-exclamation-circle-fill"></i><span>{{ error }}</span>
    </div>
    {% endif %}
    {% if success %}
    <div class="alert alert-success d-flex align-items-center gap-2 py-2">
      <i class="bi bi-check-circle-fill"></i><span>{{ success }}</span>
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
      <div class="mb-2">
        <label class="form-label fw-semibold text-muted small">SENHA</label>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-lock text-muted"></i></span>
          <input type="password" name="password" class="form-control border-start-0 ps-0" placeholder="••••••••" required>
        </div>
      </div>
      <div class="text-end mb-4">
        <a href="/forgot" class="text-muted small" style="font-size:.8rem">Esqueci minha senha</a>
      </div>
      <button type="submit" class="btn btn-brand w-100 py-2 fw-semibold">
        <i class="bi bi-box-arrow-in-right me-2"></i>Entrar
      </button>
    </form>
    <p class="text-center text-muted small mt-4 mb-0">Acesso restrito · Apenas usuários autorizados</p>
  </div>
</div>
{% endblock %}"""

FORGOT_TMPL = """{% extends 'base' %}
{% block title %}Esqueci minha senha · Clube do Saber{% endblock %}
{% block body %}
<div class="login-bg d-flex align-items-center justify-content-center min-vh-100">
  <div class="login-card shadow-lg">
    <div class="text-center mb-4">
      <div class="brand-icon mb-3"><i class="bi bi-key"></i></div>
      <h1 class="brand-title" style="font-size:1.3rem">Esqueci minha senha</h1>
      <p class="brand-sub">Informe seu e-mail para receber o link de redefinição</p>
    </div>
    {% if no_email %}
    <div class="alert alert-info d-flex align-items-center gap-2 py-2">
      <i class="bi bi-info-circle-fill"></i>
      <span>Redefinição por e-mail não está ativa. Entre em contato com o administrador.</span>
    </div>
    {% elif sent %}
    <div class="alert alert-success d-flex align-items-center gap-2 py-2">
      <i class="bi bi-envelope-check-fill"></i>
      <span>Se esse e-mail estiver cadastrado, você receberá o link em breve.</span>
    </div>
    {% else %}
    {% if error %}
    <div class="alert alert-danger d-flex align-items-center gap-2 py-2">
      <i class="bi bi-exclamation-circle-fill"></i><span>{{ error }}</span>
    </div>
    {% endif %}
    <form method="POST">
      <div class="mb-4">
        <label class="form-label fw-semibold text-muted small">E-MAIL</label>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-envelope text-muted"></i></span>
          <input type="email" name="email" class="form-control border-start-0 ps-0" placeholder="seu@email.com" autofocus required>
        </div>
      </div>
      <button type="submit" class="btn btn-brand w-100 py-2 fw-semibold">
        <i class="bi bi-send me-2"></i>Enviar Link
      </button>
    </form>
    {% endif %}
    <div class="text-center mt-4">
      <a href="/login" class="text-muted small"><i class="bi bi-arrow-left me-1"></i>Voltar ao login</a>
    </div>
  </div>
</div>
{% endblock %}"""

RESET_TMPL = """{% extends 'base' %}
{% block title %}Nova senha · Clube do Saber{% endblock %}
{% block body %}
<div class="login-bg d-flex align-items-center justify-content-center min-vh-100">
  <div class="login-card shadow-lg">
    <div class="text-center mb-4">
      <div class="brand-icon mb-3"><i class="bi bi-shield-lock"></i></div>
      <h1 class="brand-title" style="font-size:1.3rem">Nova Senha</h1>
      <p class="brand-sub">Clube do Saber</p>
    </div>
    {% if invalid %}
    <div class="alert alert-warning d-flex align-items-center gap-2 py-2">
      <i class="bi bi-clock-history"></i>
      <span>Este link expirou ou é inválido. <a href="/forgot">Solicite um novo.</a></span>
    </div>
    {% elif done %}
    <div class="alert alert-success d-flex align-items-center gap-2 py-2">
      <i class="bi bi-check-circle-fill"></i><span>Senha alterada com sucesso!</span>
    </div>
    <a href="/login" class="btn btn-brand w-100 py-2 fw-semibold mt-2">
      <i class="bi bi-box-arrow-in-right me-2"></i>Ir para Login
    </a>
    {% else %}
    {% if error %}
    <div class="alert alert-danger d-flex align-items-center gap-2 py-2">
      <i class="bi bi-exclamation-circle-fill"></i><span>{{ error }}</span>
    </div>
    {% endif %}
    <form method="POST">
      <div class="mb-3">
        <label class="form-label fw-semibold text-muted small">NOVA SENHA</label>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-lock text-muted"></i></span>
          <input type="password" name="password" class="form-control border-start-0 ps-0" placeholder="••••••••" autofocus required minlength="6">
        </div>
      </div>
      <div class="mb-4">
        <label class="form-label fw-semibold text-muted small">CONFIRMAR SENHA</label>
        <div class="input-group">
          <span class="input-group-text bg-white border-end-0"><i class="bi bi-lock-fill text-muted"></i></span>
          <input type="password" name="password2" class="form-control border-start-0 ps-0" placeholder="••••••••" required minlength="6">
        </div>
      </div>
      <button type="submit" class="btn btn-brand w-100 py-2 fw-semibold">
        <i class="bi bi-check-lg me-2"></i>Salvar Nova Senha
      </button>
    </form>
    {% endif %}
  </div>
</div>
{% endblock %}"""

DASHBOARD_TMPL = """{% extends 'base' %}
{% block title %}Biblioteca · Clube do Saber{% endblock %}
{% block body %}
<nav class="navbar navbar-dark top-nav px-4">
  <a class="navbar-brand d-flex align-items-center gap-2" href="/dashboard">
    <i class="bi bi-book-half fs-5"></i><span class="fw-bold">Clube do Saber</span>
  </a>
  <div class="d-flex align-items-center gap-3">
    <span class="text-white-50 small d-none d-sm-inline"><i class="bi bi-book me-1"></i>{{ total }} ebooks</span>
    <a href="/download/Clube_do_Saber_50_Ebooks.zip" class="btn btn-sm btn-outline-light">
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
{% block title %}Admin · Clube do Saber{% endblock %}
{% block body %}
<nav class="navbar navbar-dark top-nav px-4">
  <a class="navbar-brand d-flex align-items-center gap-2" href="/dashboard">
    <i class="bi bi-book-half fs-5"></i><span class="fw-bold">Clube do Saber</span>
    <span class="badge bg-warning text-dark ms-1 small">Admin</span>
  </a>
  <div class="d-flex align-items-center gap-2">
    {% if mail_ok %}
    <span class="badge bg-success text-white"><i class="bi bi-envelope-check me-1"></i>E-mail ativo</span>
    {% else %}
    <span class="badge bg-secondary text-white" title="Configure MAIL_USERNAME e MAIL_PASSWORD no Render"><i class="bi bi-envelope-x me-1"></i>E-mail inativo</span>
    {% endif %}
    <a href="/dashboard" class="btn btn-sm btn-outline-light"><i class="bi bi-grid me-1"></i>Biblioteca</a>
    <a href="/logout" class="btn btn-sm btn-dark"><i class="bi bi-box-arrow-right me-1"></i>Sair</a>
  </div>
</nav>
<div class="container-fluid py-4 px-4" style="max-width:960px">

  <!-- Alerts -->
  {% if msg == 'added' %}
  <div class="alert alert-success d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-check-circle-fill"></i>
    <span>Usuário criado com sucesso{% if emailed == '1' %} · E-mail de boas-vindas enviado ✉️{% endif %}.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'imported' %}
  <div class="alert alert-success d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-check-circle-fill"></i>
    <span><strong>{{ created }}</strong> usuário(s) importado(s){% if skipped != '0' %}, <strong>{{ skipped }}</strong> já existia(m){% endif %}{% if emailed != '0' %}, <strong>{{ emailed }}</strong> e-mail(s) enviado(s) ✉️{% endif %}.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'import_err' %}
  <div class="alert alert-danger d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-exclamation-circle-fill"></i><span>Erro ao ler o arquivo. Verifique se é um .xlsx válido.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'no_xlsx' %}
  <div class="alert alert-warning d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-exclamation-triangle-fill"></i><span>Biblioteca openpyxl não instalada. Adicione ao requirements.txt.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'exists' %}
  <div class="alert alert-danger d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-exclamation-circle-fill"></i><span>Usuário já existe.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'deleted' %}
  <div class="alert alert-info d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-trash-fill"></i><span>Usuário removido.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'self' %}
  <div class="alert alert-warning d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-shield-exclamation"></i><span>Não pode remover a própria conta.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'empty' %}
  <div class="alert alert-danger d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-exclamation-circle-fill"></i><span>Usuário e senha são obrigatórios.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'pwd_ok' %}
  <div class="alert alert-success d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-key-fill"></i><span>Senha alterada com sucesso.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% elif msg == 'empty_pass' %}
  <div class="alert alert-danger d-flex align-items-center gap-2 alert-dismissible">
    <i class="bi bi-exclamation-circle-fill"></i><span>A nova senha não pode ser vazia.</span>
    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
  </div>
  {% endif %}

  <h1 class="h4 fw-bold mb-4"><i class="bi bi-shield-fill me-2 text-warning"></i>Gerenciar Usuários</h1>

  <!-- Adicionar usuário -->
  <div class="card shadow-sm mb-4">
    <div class="card-header fw-semibold"><i class="bi bi-person-plus-fill me-2 text-brand"></i>Adicionar Usuário</div>
    <div class="card-body">
      <form method="POST" action="/admin/add">
        <div class="row g-3">
          <div class="col-md-3"><label class="form-label small fw-semibold text-muted">USUÁRIO *</label><input type="text" name="username" class="form-control" placeholder="nome_usuario" required></div>
          <div class="col-md-3"><label class="form-label small fw-semibold text-muted">SENHA *</label><input type="password" name="password" class="form-control" placeholder="••••••••" required></div>
          <div class="col-md-3"><label class="form-label small fw-semibold text-muted">E-MAIL {% if mail_ok %}<span class="text-success small">(enviará boas-vindas)</span>{% endif %}</label><input type="email" name="email" class="form-control" placeholder="email@ex.com"></div>
          <div class="col-md-2 d-flex align-items-end"><div class="form-check mb-2"><input type="checkbox" name="is_admin" id="is_admin" class="form-check-input"><label for="is_admin" class="form-check-label small">Admin</label></div></div>
          <div class="col-md-1 d-flex align-items-end"><button type="submit" class="btn btn-brand w-100"><i class="bi bi-plus-lg"></i></button></div>
        </div>
      </form>
    </div>
  </div>

  <!-- Importar Excel -->
  <div class="card shadow-sm mb-4">
    <div class="card-header fw-semibold"><i class="bi bi-file-earmark-excel-fill me-2 text-success"></i>Importar por Planilha Excel</div>
    <div class="card-body">
      <p class="text-muted small mb-3">
        Faça upload de um arquivo <strong>.xlsx</strong> com as colunas: <code>usuario</code>, <code>senha</code>, <code>email</code> (opcional).<br>
        A primeira linha deve ter os cabeçalhos. Os dados começam na segunda linha.
      </p>
      <form method="POST" action="/admin/import" enctype="multipart/form-data">
        <div class="row g-3 align-items-end">
          <div class="col"><input type="file" name="file" class="form-control" accept=".xlsx" required></div>
          <div class="col-auto"><button type="submit" class="btn btn-success"><i class="bi bi-upload me-1"></i>Importar</button></div>
        </div>
        {% if mail_ok %}
        <div class="form-check mt-2">
          <input type="checkbox" name="send_email" id="send_email_import" class="form-check-input" checked>
          <label for="send_email_import" class="form-check-label small text-muted">Enviar e-mail de boas-vindas para cada usuário com e-mail cadastrado</label>
        </div>
        {% endif %}
      </form>
    </div>
  </div>

  <!-- Tabela de usuários -->
  <div class="card shadow-sm">
    <div class="card-header fw-semibold d-flex justify-content-between align-items-center">
      <span><i class="bi bi-people-fill me-2 text-brand"></i>Usuários Cadastrados</span>
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
TMPLS = {
    'base':      BASE_TMPL,
    'login':     LOGIN_TMPL,
    'forgot':    FORGOT_TMPL,
    'reset':     RESET_TMPL,
    'dashboard': DASHBOARD_TMPL,
    'admin':     ADMIN_TMPL,
}

app = Flask(__name__)
app.jinja_loader = DictLoader(TMPLS)
app.secret_key = os.environ.get('SECRET_KEY', 'clube-saber-change-me-in-production')
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
    db.execute("""CREATE TABLE IF NOT EXISTS reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        token TEXT UNIQUE NOT NULL,
        expires_at TEXT NOT NULL,
        used INTEGER DEFAULT 0
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
    @wraps(f)
    def w(*a, **kw):
        if 'uid' not in session: return redirect('/login')
        return f(*a, **kw)
    return w

def admin_required(f):
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
    success = request.args.get('success')
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
    return R('login', error=error, success=success)

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

# ── Forgot / Reset password ───────────────────────────────────────────────────
@app.route('/forgot', methods=['GET', 'POST'])
def forgot():
    mail_active = bool(MAIL_USER and MAIL_PASS)
    if not mail_active:
        return R('forgot', no_email=True, sent=False, error=None)
    sent = False
    error = None
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE email=?', (email,)).fetchone()
        if row:
            token = secrets.token_urlsafe(32)
            expires = (datetime.utcnow() + timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')
            db.execute('INSERT INTO reset_tokens(user_id,token,expires_at) VALUES(?,?,?)',
                       (row['id'], token, expires))
            db.commit()
            reset_url = request.host_url.rstrip('/') + f'/reset/{token}'
            _send_email(email, '🔑 Redefinir senha · Clube do Saber', _reset_html(reset_url))
        db.close()
        sent = True  # always show success (security: don't reveal if email exists)
    return R('forgot', no_email=False, sent=sent, error=error)

@app.route('/reset/<token>', methods=['GET', 'POST'])
def reset(token):
    db = get_db()
    row = db.execute(
        'SELECT * FROM reset_tokens WHERE token=? AND used=0', (token,)
    ).fetchone()
    if not row:
        db.close()
        return R('reset', invalid=True, done=False, error=None)
    # Check expiry
    expires = datetime.strptime(row['expires_at'], '%Y-%m-%d %H:%M:%S')
    if datetime.utcnow() > expires:
        db.close()
        return R('reset', invalid=True, done=False, error=None)
    error = None
    done = False
    if request.method == 'POST':
        p1 = request.form.get('password', '')
        p2 = request.form.get('password2', '')
        if not p1:
            error = 'A senha não pode ser vazia.'
        elif p1 != p2:
            error = 'As senhas não coincidem.'
        else:
            db.execute('UPDATE users SET password_hash=? WHERE id=?',
                       (generate_password_hash(p1), row['user_id']))
            db.execute('UPDATE reset_tokens SET used=1 WHERE id=?', (row['id'],))
            db.commit()
            done = True
    db.close()
    return R('reset', invalid=False, done=done, error=error)

# ── Admin routes ──────────────────────────────────────────────────────────────
def _admin_ctx():
    return dict(
        mail_ok=bool(MAIL_USER and MAIL_PASS),
        msg=request.args.get('msg', ''),
        cur_id=session['uid'],
        created=request.args.get('created', '0'),
        skipped=request.args.get('skipped', '0'),
        emailed=request.args.get('emailed', '0'),
    )

@app.route('/admin')
@admin_required
def admin():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY is_admin DESC, created_at DESC').fetchall()
    db.close()
    return R('admin', users=users, uname=session['uname'], **_admin_ctx())

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
                   (u, e, generate_password_hash(p), adm))
        db.commit()
        emailed = 0
        if e and MAIL_USER and MAIL_PASS:
            login_url = request.host_url.rstrip('/') + '/login'
            html = _welcome_html(u, p, login_url)
            if _send_email(e, '🎓 Seu acesso ao Clube do Saber foi criado!', html):
                emailed = 1
        return redirect(f'/admin?msg=added&emailed={emailed}')
    except sqlite3.IntegrityError:
        return redirect('/admin?msg=exists')
    finally:
        db.close()

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

@app.route('/admin/import', methods=['POST'])
@admin_required
def import_users():
    if not HAS_OPENPYXL:
        return redirect('/admin?msg=no_xlsx')
    f = request.files.get('file')
    if not f:
        return redirect('/admin?msg=import_err')
    send_mail = bool(request.form.get('send_email')) and bool(MAIL_USER and MAIL_PASS)
    try:
        wb = openpyxl.load_workbook(io.BytesIO(f.read()))
        ws = wb.active
        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            return redirect('/admin?msg=import_err')
        # Detect header row
        first = [str(c).lower().strip() if c else '' for c in rows[0]]
        has_header = any(h in first for h in ('usuario', 'username', 'senha', 'password', 'email'))
        data_rows = rows[1:] if has_header else rows
        created = skipped = emailed = 0
        db = get_db()
        login_url = request.host_url.rstrip('/') + '/login'
        for row in data_rows:
            if not row or len(row) < 2: continue
            username = str(row[0]).strip() if row[0] else ''
            password = str(row[1]).strip() if row[1] else ''
            email    = str(row[2]).strip() if len(row) > 2 and row[2] else ''
            if not username or not password: continue
            try:
                db.execute('INSERT INTO users(username,email,password_hash,is_admin) VALUES(?,?,?,0)',
                           (username, email, generate_password_hash(password)))
                db.commit()
                created += 1
                if send_mail and email:
                    html = _welcome_html(username, password, login_url)
                    if _send_email(email, '🎓 Seu acesso ao Clube do Saber foi criado!', html):
                        emailed += 1
            except sqlite3.IntegrityError:
                skipped += 1
        db.close()
        return redirect(f'/admin?msg=imported&created={created}&skipped={skipped}&emailed={emailed}')
    except Exception as ex:
        print(f'[import] {ex}')
        return redirect('/admin?msg=import_err')

# ── Start ─────────────────────────────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
