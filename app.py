from flask import Flask, request, jsonify, session, redirect
from flask_cors import CORS
import json
import os
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None
from collections import defaultdict
from functools import wraps
import mysql.connector
from mysql.connector import Error
from loterie import Loterie

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = 'votre_cle_secrete_tres_secrete_12345'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_NAME'] = 'lix_session'  # ← ajoute ça
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=24)  # ← et ça

CORS(app,
     supports_credentials=True,
     origins=["*"],
     methods=["GET", "POST", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     expose_headers=["Content-Type"])

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    return '', 200

# ─────────────────────────────────────────────
# CONNEXION MYSQL
# ─────────────────────────────────────────────
DB_CONFIG = {
    'host': 'switchback.proxy.rlwy.net',
    'port': 18902,
    'user': 'root',
    'password': 'aFyeiXTJRMuwpgQSZByoOiyOvyLEJlhK',
    'database': 'railway',
    'charset': 'utf8mb4',
    'autocommit': True
}

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Erreur MySQL: {e}")
        return None

# ─────────────────────────────────────────────
# CRÉATION DES TABLES AU DÉMARRAGE
# ─────────────────────────────────────────────
def init_db():
    conn = get_db()
    if not conn:
        print("Impossible de se connecter à MySQL")
        return
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username VARCHAR(100) PRIMARY KEY,
            password VARCHAR(255) NOT NULL,
            grade VARCHAR(50) NOT NULL DEFAULT 'Apprenti',
            nom VARCHAR(100),
            prenom VARCHAR(100),
            id_personnage VARCHAR(50)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ventes (
            id INT AUTO_INCREMENT PRIMARY KEY,
            vendeur VARCHAR(100),
            date DATETIME NOT NULL,
            total FLOAT NOT NULL,
            items JSON NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key_name VARCHAR(100) PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grades (
            grade_name VARCHAR(100) PRIMARY KEY,
            commission FLOAT DEFAULT 0,
            salaire_fixe FLOAT DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS shifts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            start DATETIME NOT NULL,
            end DATETIME
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS adverts (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(100),
            date DATETIME NOT NULL,
            title VARCHAR(255),
            image TEXT,
            text TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS lottery (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ticket_price FLOAT DEFAULT 100,
            last_updated DATETIME,
            updated_by VARCHAR(100)
        )
    """)

    # Données par défaut grades
    default_grades = [
        ('Apprenti', 2, 1500),
        ('CDD', 5, 2800),
        ('CDI', 5, 3200),
        ("Chef d'équipe", 10, 4000),
        ('DRH', 5, 5000),
        ('CO-PDG', 15, 7000),
        ('PDG', 20, 8000),
    ]
    for g in default_grades:
        cursor.execute("""
            INSERT IGNORE INTO grades (grade_name, commission, salaire_fixe)
            VALUES (%s, %s, %s)
        """, g)

    # Utilisateurs par défaut
    default_users = [
        ('admin', 'admin123', 'PDG', 'Dupont', 'Pierre', ''),
        ('rh', 'rh123', 'DRH', 'Martin', 'Marie', ''),
        ('chef1', 'chef123', "Chef d'équipe", 'Leroy', 'Jean', ''),
        ('employe1', 'cdi123', 'CDI', 'Bernard', 'Sophie', ''),
        ('employe2', 'cdd123', 'CDD', 'Petit', 'Thomas', ''),
        ('apprenti1', 'app123', 'Apprenti', 'Dubois', 'Lucas', ''),
    ]
    for u in default_users:
        cursor.execute("""
            INSERT IGNORE INTO users (username, password, grade, nom, prenom, id_personnage)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, u)

    # Settings par défaut
    default_settings = [
        ('objectif_hebdo', '10000'),
        ('advert_title', ''),
        ('advert_image', ''),
        ('advert_text', ''),
    ]
    for s in default_settings:
        cursor.execute("INSERT IGNORE INTO settings (key_name, value) VALUES (%s, %s)", s)

    # Lottery par défaut
    cursor.execute("SELECT COUNT(*) FROM lottery")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO lottery (ticket_price, last_updated, updated_by) VALUES (100, NOW(), 'system')")

    conn.commit()
    cursor.close()
    conn.close()
    print("Base de données initialisée ✅")

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────
def get_settings():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT key_name, value FROM settings")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {r['key_name']: r['value'] for r in rows}

def set_setting(key, value):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO settings (key_name, value) VALUES (%s, %s) ON DUPLICATE KEY UPDATE value=%s",
                   (key, str(value), str(value)))
    conn.commit()
    cursor.close()
    conn.close()

def get_grades():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM grades")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {r['grade_name']: {'commission': r['commission'], 'salaire_fixe': r['salaire_fixe']} for r in rows}

def get_users():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return {r['username']: {k: v for k, v in r.items() if k != 'username'} for r in rows}

def calculate_derived_data(ventes, filter_user=None):
    if ZoneInfo:
        try:
            tz = ZoneInfo("Europe/Paris")
        except Exception:
            tz = None
    else:
        tz = None
    now = datetime.now(tz) if tz else datetime.now()
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

    ventes_par_jour = defaultdict(float)
    services_count = defaultdict(int)
    ventes_recentes = []

    for vente in ventes:
        if filter_user and vente.get('vendeur') != filter_user:
            continue
        date_str = vente['date'][:10] if isinstance(vente['date'], str) else vente['date'].strftime("%Y-%m-%d")
        montant = vente['total']
        if date_str in week_dates:
            ventes_par_jour[date_str] += montant
        ventes_recentes.append(montant)
        items = vente['items'] if isinstance(vente['items'], list) else json.loads(vente['items'])
        for item in items:
            services_count[item.get('name', '')] += item.get('qty', 0)

    accueil_data = [ventes_par_jour.get(day, 0) for day in week_dates]
    ventes_data = list(services_count.values())[:7] if services_count else [0] * 7
    total_ventes = sum(accueil_data)
    cumul = 0
    bilan_data = []
    for v in accueil_data:
        cumul += v
        bilan_data.append(cumul)
    recentes_data = ventes_recentes[-7:] if len(ventes_recentes) >= 7 else ventes_recentes + [0] * (7 - len(ventes_recentes))

    return {
        "accueil": accueil_data,
        "ventes": ventes_data,
        "bilan": bilan_data,
        "recentes": recentes_data,
        "salaires": [3000, 3200, 3100, 3300, 3150, 3050, 3250],
        "charges": [500, 600, 550, 650, 575, 525, 625],
        "services_stats": dict(services_count),
        "total_ca": total_ventes,
        "nb_ventes": len(ventes_recentes)
    }

def load_all_ventes():
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM ventes ORDER BY date DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    return rows

# ─────────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

@app.route('/')
@login_required
def index():
    return app.send_static_file('test.html')

@app.route('/login')
def login_page():
    return app.send_static_file('login.html')

@app.route('/logout')
def logout_route():
    session.pop('user', None)
    return redirect('/login')

@app.route('/api/login', methods=['POST', 'OPTIONS'])
def api_login():
    if request.method == 'OPTIONS':
        return '', 200
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s AND password=%s", (username, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    if user:
        session.permanent = True
        session['user'] = {'username': user['username'], 'grade': user['grade']}
        return jsonify({"success": True, "user": session['user']})
    return jsonify({"success": False, "message": "Identifiants incorrects"})

@app.route('/api/current_user', methods=['GET', 'OPTIONS'])
def get_current_user():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify(session.get('user', {}))

# ─────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────
@app.route('/api/data', methods=['GET', 'OPTIONS'])
def get_data():
    if request.method == 'OPTIONS':
        return '', 200
    ventes = load_all_ventes()
    return jsonify(calculate_derived_data(ventes))

@app.route('/api/global_data', methods=['GET', 'OPTIONS'])
def get_global_data():
    if request.method == 'OPTIONS':
        return '', 200
    ventes = load_all_ventes()
    return jsonify(calculate_derived_data(ventes))

@app.route('/api/my_data', methods=['GET', 'OPTIONS'])
def get_my_data():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    username = session['user']['username']
    ventes = load_all_ventes()
    data = calculate_derived_data(ventes, filter_user=username)
    user_ventes = [v for v in ventes if v.get('vendeur') == username]
    for v in user_ventes:
        if not isinstance(v['items'], list):
            v['items'] = json.loads(v['items'])
        if isinstance(v['date'], datetime):
            v['date'] = v['date'].isoformat()
    data['ventes_historique'] = user_ventes
    return jsonify(data)

@app.route('/api/my_stats', methods=['GET', 'OPTIONS'])
def get_my_stats():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    username = session['user']['username']
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM users WHERE username=%s", (username,))
    user_data = cursor.fetchone() or {}
    cursor.close()
    conn.close()
    grades_cfg = get_grades()
    user_grade = user_data.get('grade', '')
    grade_cfg = grades_cfg.get(user_grade, {'commission': 0, 'salaire_fixe': 0})
    ventes = load_all_ventes()
    user_ventes = [v for v in ventes if v.get('vendeur') == username]
    total_ca = sum(v['total'] for v in user_ventes)
    nb_ventes = len(user_ventes)
    commission_amount = (total_ca * grade_cfg['commission']) / 100
    salaire_total = grade_cfg['salaire_fixe'] + commission_amount
    settings = get_settings()
    objectif_ca = float(settings.get('objectif_hebdo', 10000))
    progression = (total_ca / objectif_ca * 100) if objectif_ca > 0 else 0
    return jsonify({
        "user_info": {
            "nom": user_data.get('nom', ''),
            "prenom": user_data.get('prenom', ''),
            "grade": user_grade,
            "salaire_fixe": grade_cfg['salaire_fixe'],
            "commission_pourcentage": grade_cfg['commission'],
            "objectif_ca": objectif_ca
        },
        "performance": {
            "total_ca": total_ca,
            "nb_ventes": nb_ventes,
            "commission_amount": commission_amount,
            "salaire_total": salaire_total,
            "progression_objectif": min(progression, 100)
        }
    })

@app.route('/api/cart', methods=['POST', 'OPTIONS'])
def receive_cart():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.get_json()
    cart_items = data.get('items', [])
    if not cart_items:
        return jsonify({"success": False, "message": "Panier vide"})
    total = sum(item['price'] * item['qty'] for item in cart_items)
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ventes (vendeur, date, total, items)
        VALUES (%s, %s, %s, %s)
    """, (session['user']['username'], datetime.now(), total, json.dumps(cart_items)))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Vente de {total}$ enregistrée"})

# ─────────────────────────────────────────────
# USERS
# ─────────────────────────────────────────────
@app.route('/api/users', methods=['GET', 'OPTIONS'])
def get_users_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    return jsonify(get_users())

@app.route('/api/users/add', methods=['POST', 'OPTIONS'])
def add_user_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    nom = data.get('nom')
    prenom = data.get('prenom')
    id = data.get('id')
    grade = data.get('grade')
    if not all([username, password, nom, prenom, id, grade]):
        return jsonify({"success": False, "message": "Tous les champs sont requis"})
    grades_valides = ['Apprenti', 'CDD', 'CDI', "Chef d'équipe", 'DRH', 'CO-PDG', 'PDG']
    if grade not in grades_valides:
        return jsonify({"success": False, "message": "Grade invalide"})
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO users (username, password, grade, nom, prenom, id_personnage) VALUES (%s,%s,%s,%s,%s,%s)",
                       (username, password, grade, nom, prenom, id))
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": f"Utilisateur {username} ajouté"})
    except Error:
        return jsonify({"success": False, "message": "Nom d'utilisateur déjà existant"})

@app.route('/api/users/update', methods=['POST', 'OPTIONS'])
def update_user():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    username = data.get('username')
    updates = data.get('updates', {})
    if not username:
        return jsonify({"success": False, "message": "Username requis"})
    conn = get_db()
    cursor = conn.cursor()
    fields = []
    values = []
    for key in ['nom', 'prenom', 'grade', 'password', 'id_personnage']:
        if key in updates:
            fields.append(f"{key}=%s")
            values.append(updates[key])
    if not fields:
        return jsonify({"success": False, "message": "Rien à mettre à jour"})
    values.append(username)
    cursor.execute(f"UPDATE users SET {', '.join(fields)} WHERE username=%s", values)
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Utilisateur mis à jour"})

@app.route('/api/users/update_grade', methods=['POST', 'OPTIONS'])
def update_user_grade_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    username = data.get('username')
    new_grade = data.get('grade')
    grades_valides = ['Apprenti', 'CDD', 'CDI', "Chef d'équipe", 'DRH', 'CO-PDG', 'PDG']
    if new_grade not in grades_valides:
        return jsonify({"success": False, "message": "Grade invalide"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET grade=%s WHERE username=%s", (new_grade, username))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Grade de {username} mis à jour"})

@app.route('/api/users/delete', methods=['POST', 'OPTIONS'])
def delete_user_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    username = data.get('username')
    if username == session['user']['username']:
        return jsonify({"success": False, "message": "Impossible de supprimer votre propre compte"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM users WHERE username=%s", (username,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Utilisateur {username} supprimé"})

@app.route('/api/users/reset-password', methods=['POST', 'OPTIONS'])
def reset_password():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    if not password or len(password) < 4:
        return jsonify({"success": False, "message": "Mot de passe trop court"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET password=%s WHERE username=%s", (password, username))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": "Mot de passe réinitialisé"})

# ─────────────────────────────────────────────
# GRADES
# ─────────────────────────────────────────────
@app.route('/api/grades', methods=['GET', 'OPTIONS'])
def get_grades_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    return jsonify(get_grades())

@app.route('/api/grades/update', methods=['POST', 'OPTIONS'])
def update_grade_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    body = request.get_json() or {}
    grade_name = body.get('grade')
    commission = body.get('commission')
    salaire_fixe = body.get('salaire_fixe')
    if not grade_name:
        return jsonify({"success": False, "message": "Grade manquant"})
    conn = get_db()
    cursor = conn.cursor()
    if commission is not None:
        cursor.execute("UPDATE grades SET commission=%s WHERE grade_name=%s", (float(commission), grade_name))
    if salaire_fixe is not None:
        cursor.execute("UPDATE grades SET salaire_fixe=%s WHERE grade_name=%s", (float(salaire_fixe), grade_name))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "message": f"Grade {grade_name} mis à jour"})

# ─────────────────────────────────────────────
# SETTINGS
# ─────────────────────────────────────────────
@app.route('/api/settings', methods=['GET', 'OPTIONS'])
def get_settings_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    s = get_settings()
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT ticket_price FROM lottery ORDER BY id DESC LIMIT 1")
    lottery = cursor.fetchone()
    cursor.close()
    conn.close()
    s['lottery_price'] = lottery['ticket_price'] if lottery else 100
    return jsonify(s)

@app.route('/api/settings/update', methods=['POST', 'OPTIONS'])
def update_settings_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    body = request.get_json() or {}
    if 'objectif_hebdo' in body:
        set_setting('objectif_hebdo', body['objectif_hebdo'])
    if 'advert_title' in body:
        set_setting('advert_title', body['advert_title'])
    if 'advert_image' in body:
        set_setting('advert_image', body['advert_image'])
    if 'advert_text' in body:
        set_setting('advert_text', body['advert_text'])
    if 'lottery_price' in body:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("UPDATE lottery SET ticket_price=%s, last_updated=NOW(), updated_by=%s",
                       (float(body['lottery_price']), session['user']['username']))
        conn.commit()
        cursor.close()
        conn.close()
    return jsonify({"success": True, "message": "Réglages mis à jour"})

# ─────────────────────────────────────────────
# LOTTERY
# ─────────────────────────────────────────────
@app.route('/api/lottery/price', methods=['GET', 'OPTIONS'])
def get_lottery_price():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT ticket_price FROM lottery ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify({"price": row['ticket_price'] if row else 100})

@app.route('/api/lottery/update', methods=['POST', 'OPTIONS'])
def update_lottery_price():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    data = request.get_json()
    new_price = float(data.get('price', 0))
    if new_price < 1:
        return jsonify({"success": False, "message": "Prix invalide"})
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE lottery SET ticket_price=%s, last_updated=NOW(), updated_by=%s",
                   (new_price, session['user']['username']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "price": new_price})

@app.route('/api/lottery/history', methods=['GET', 'OPTIONS'])
def get_lottery_history():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM lottery ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if row and isinstance(row.get('last_updated'), datetime):
        row['last_updated'] = row['last_updated'].isoformat()
    return jsonify(row or {})

@app.route('/api/loterie/prix', methods=['GET'])
@login_required
def get_prix_loterie():
    """Récupère le prix d'un ticket"""
    loterie = Loterie()
    return jsonify({'prix': loterie.get_prix_ticket()})

@app.route('/api/loterie/prix', methods=['POST'])
@login_required
def set_prix_loterie():
    """Modifie le prix d'un ticket (direction uniquement)"""
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    
    data = request.get_json()
    nouveau_prix = data.get('prix')
    
    if not nouveau_prix or nouveau_prix < 1:
        return jsonify({'success': False, 'message': 'Prix invalide'}), 400
    
    loterie = Loterie()
    success = loterie.set_prix_ticket(nouveau_prix)
    
    if success:
        return jsonify({'success': True, 'message': 'Prix mis à jour'})
    else:
        return jsonify({'success': False, 'message': 'Erreur lors de la mise à jour'}), 500

@app.route('/api/loterie/acheter', methods=['POST'])
@login_required
def acheter_tickets():
    """Achète des tickets de loterie"""
    data = request.get_json()
    
    # Vérifier les données client
    client_data = {
        'prenom': data.get('prenom'),
        'nom': data.get('nom'),
        'telephone': data.get('telephone'),
        'email': data.get('email')
    }
    
    if not all([client_data['prenom'], client_data['nom'], client_data['telephone']]):
        return jsonify({'success': False, 'message': 'Informations client incomplètes'}), 400
    
    # Vérifier les tickets
    tickets_data = data.get('tickets', [])
    if not tickets_data:
        return jsonify({'success': False, 'message': 'Aucun ticket à acheter'}), 400
    
    # Vérifier que chaque ticket a 3 numéros uniques
    for ticket in tickets_data:
        if len(ticket.get('numeros', [])) != 3:
            return jsonify({'success': False, 'message': 'Chaque ticket doit avoir 3 numéros'}), 400
        if len(set(ticket['numeros'])) != 3:
            return jsonify({'success': False, 'message': 'Les numéros d\'un ticket doivent être uniques'}), 400
        for num in ticket['numeros']:
            if num < 0 or num > 100:
                return jsonify({'success': False, 'message': 'Les numéros doivent être entre 0 et 100'}), 400
    username = session['user']['username']
    loterie = Loterie()
    resultat = loterie.acheter_tickets(
        client_data=client_data,
        tickets_data=tickets_data,
        vendeur=username
    )
    
    return jsonify(resultat)

@app.route('/api/loterie/clients/recherche', methods=['GET'])
@login_required
def rechercher_client():
    """Recherche un client par téléphone"""
    telephone = request.args.get('telephone')
    if not telephone:
        return jsonify({'error': 'Téléphone requis'}), 400
    
    loterie = Loterie()
    client = loterie.get_client_par_telephone(telephone)
    
    if client:
        return jsonify({'client': client})
    
    return jsonify({'client': None})

# ─────────────────────────────────────────────
# SHIFTS
# ─────────────────────────────────────────────
@app.route('/api/shifts/start', methods=['POST', 'OPTIONS'])
def start_shift():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    username = session['user']['username']
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM shifts WHERE username=%s AND end IS NULL", (username,))
    active = cursor.fetchone()
    if active:
        cursor.close()
        conn.close()
        return jsonify({"success": True, "message": "Shift déjà en cours", "shift": {"start": active['start'].isoformat()}})
    now = datetime.now()
    cursor.execute("INSERT INTO shifts (username, start) VALUES (%s, %s)", (username, now))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True, "shift": {"start": now.isoformat()}})

@app.route('/api/shifts/stop', methods=['POST', 'OPTIONS'])
def stop_shift():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    username = session['user']['username']
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("UPDATE shifts SET end=NOW() WHERE username=%s AND end IS NULL", (username,))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/shifts/logs', methods=['GET', 'OPTIONS'])
def shifts_logs():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM shifts ORDER BY start DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    result = []
    for s in rows:
        start = s['start']
        end = s['end']
        duration_str = "En cours"
        if end:
            diff = end - start
            h = diff.seconds // 3600
            m = (diff.seconds % 3600) // 60
            duration_str = f"{h}h {m}min"
        result.append({
            "username": s['username'],
            "start": start.strftime("%d/%m/%Y à %H:%M:%S"),
            "end": end.strftime("%d/%m/%Y à %H:%M:%S") if end else "En cours",
            "duration": duration_str,
            "is_active": end is None
        })
    return jsonify(result)

# ─────────────────────────────────────────────
# ADVERTS
# ─────────────────────────────────────────────
@app.route('/api/adverts/create', methods=['POST', 'OPTIONS'])
def create_advert():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.get_json() or {}
    title = data.get('title', '')
    image = data.get('image', '')
    text = data.get('text', '')
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO adverts (username, date, title, image, text) VALUES (%s, NOW(), %s, %s, %s)",
                   (session['user']['username'], title, image, text))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"success": True})

@app.route('/api/adverts/logs', methods=['GET', 'OPTIONS'])
def adverts_logs():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    grade = session['user']['grade']
    if grade not in ['PDG', 'CO-PDG']:
        return jsonify({"error": "Accès refusé"}), 403
    conn = get_db()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM adverts ORDER BY date DESC")
    rows = cursor.fetchall()
    cursor.close()
    conn.close()
    for r in rows:
        if isinstance(r['date'], datetime):
            r['date'] = r['date'].isoformat()
    return jsonify(rows)

# LOTERIE

# ─────────────────────────────────────────────
# DÉMARRAGE
# ─────────────────────────────────────────────
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, port=port, host='0.0.0.0')