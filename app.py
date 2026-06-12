from flask import (Flask, render_template, request, redirect,
                   url_for, session, send_from_directory, abort)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, os, json
from functools import wraps

app = Flask(__name__, template_folder='.')
app.secret_key = os.environ.get('SECRET_KEY', 'editora-ia-change-me-in-production')
app.config['SESSION_COOKIE_HTTPONLY'] = True

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, 'users.db')
EBOOKS_DIR = BASE_DIR   # PDFs are in the repo root

with open(os.path.join(BASE_DIR, 'ebooks_metadata.json'), 'r', encoding='utf-8') as _f:
    EBOOKS = json.load(_f)

CATEGORIES: dict = {}
for _eb in EBOOKS:
    CATEGORIES.setdefault(_eb['categoria'], []).append(_eb)

CAT_ICONS = {
    'IA e Tecnologia':       'bi-cpu-fill',
    'Negócios':              'bi-briefcase-fill',
    'Finanças':              'bi-cash-coin',
    'Importação':            'bi-globe-americas',
    'Liderança':             'bi-star-fill',
    'Desenvolvimento Pessoal': 'bi-lightbulb-fill',
    'Varejo':                'bi-bag-fill',
    'Saúde e Gestão':        'bi-heart-pulse-fill',
}
CAT_COLORS = {
    'IA e Tecnologia':       '#00BCD4',
    'Negócios':              '#F39C12',
    'Finanças':              '#27AE60',
    'Importação':            '#FF6B35',
    'Liderança':             '#C0392B',
    'Desenvolvimento Pessoal': '#9B59B6',
    'Varejo':                '#E91E63',
    'Saúde e Gestão':        '#16A085',
}

# ── DB helpers ────────────────────────────────────────────────────────────────

def get_db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    db = get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            username     TEXT UNIQUE NOT NULL,
            email        TEXT DEFAULT '',
            password_hash TEXT NOT NULL,
            is_admin     INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    n = db.execute('SELECT COUNT(*) FROM users').fetchone()[0]
    if n == 0:
        u = os.environ.get('ADMIN_USERNAME', 'admin')
        p = os.environ.get('ADMIN_PASSWORD', 'admin123')
        db.execute(
            'INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,1)',
            (u, generate_password_hash(p))
        )
        db.commit()
        print(f'[init] Admin criado: {u}')
    db.close()

# ── Decorators ────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if 'uid' not in session:
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrapped

def admin_required(f):
    @wraps(f)
    def wrapped(*a, **kw):
        if 'uid' not in session:
            return redirect(url_for('login'))
        if not session.get('adm'):
            abort(403)
        return f(*a, **kw)
    return wrapped

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('dashboard') if 'uid' in session else url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'uid' in session:
        return redirect(url_for('dashboard'))
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
            return redirect(url_for('dashboard'))
        error = 'Usuário ou senha incorretos.'
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    return render_template(
        'dashboard.html',
        categories=CATEGORIES,
        cat_icons=CAT_ICONS,
        cat_colors=CAT_COLORS,
        uname=session['uname'],
        is_adm=session.get('adm', False),
        total=len(EBOOKS),
    )

@app.route('/download/<path:filename>')
@login_required
def download(filename):
    fn = os.path.basename(filename)
    if not (fn.endswith('.pdf') or fn.endswith('.zip')):
        abort(400)
    return send_from_directory(EBOOKS_DIR, fn, as_attachment=True)

# ── Admin ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@admin_required
def admin():
    db  = get_db()
    users = db.execute(
        'SELECT * FROM users ORDER BY is_admin DESC, created_at DESC'
    ).fetchall()
    db.close()
    return render_template(
        'admin.html',
        users=users,
        uname=session['uname'],
        msg=request.args.get('msg', ''),
        cur_id=session['uid'],
    )

@app.route('/admin/add', methods=['POST'])
@admin_required
def add_user():
    u   = request.form.get('username', '').strip()
    p   = request.form.get('password', '')
    e   = request.form.get('email', '').strip()
    adm = 1 if request.form.get('is_admin') else 0
    if not u or not p:
        return redirect(url_for('admin') + '?msg=empty')
    db = get_db()
    try:
        db.execute(
            'INSERT INTO users(username,email,password_hash,is_admin) VALUES(?,?,?,?)',
            (u, e, generate_password_hash(p), adm)
        )
        db.commit()
        msg = 'added'
    except sqlite3.IntegrityError:
        msg = 'exists'
    db.close()
    return redirect(url_for('admin') + f'?msg={msg}')

@app.route('/admin/delete/<int:uid>', methods=['POST'])
@admin_required
def del_user(uid):
    if uid == session['uid']:
        return redirect(url_for('admin') + '?msg=self')
    db = get_db()
    db.execute('DELETE FROM users WHERE id=?', (uid,))
    db.commit()
    db.close()
    return redirect(url_for('admin') + '?msg=deleted')

@app.route('/admin/pwd/<int:uid>', methods=['POST'])
@admin_required
def chg_pwd(uid):
    p = request.form.get('pwd', '')
    if not p:
        return redirect(url_for('admin') + '?msg=empty_pass')
    db = get_db()
    db.execute('UPDATE users SET password_hash=? WHERE id=?',
               (generate_password_hash(p), uid))
    db.commit()
    db.close()
    return redirect(url_for('admin') + '?msg=pwd_ok')

# ── Start ─────────────────────────────────────────────────────────────────────

init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
