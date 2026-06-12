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
    'Livros em Inglês':       'bi-globe2',
    'Clássicos Brasileiros':  'bi-book-fill',
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
    'Livros em Inglês':       '#2196F3',
    'Clássicos Brasileiros':  '#4CAF50',
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
.sidebar-link.active{background:rgba(108,52,131,.25);color:#fff;border-left-c
