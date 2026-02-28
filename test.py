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

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = 'votre_cle_secrete_tres_secrete_12345'
app.config['SESSION_COOKIE_SAMESITE'] = 'None'
app.config['SESSION_COOKIE_SECURE'] = True
app.config['SESSION_COOKIE_HTTPONLY'] = True

# Configuration CORS complète
CORS(app, 
     supports_credentials=True,
     origins=["http://localhost:5000", "http://127.0.0.1:5000"],
     methods=["GET", "POST", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     expose_headers=["Content-Type"])

# Middleware pour gérer les pré-vols CORS
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Credentials', 'true')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

# Route pour gérer les pré-vols CORS
@app.route('/api/<path:path>', methods=['OPTIONS'])
def handle_options(path):
    return '', 200

# Données utilisateurs - initialiser comme dictionnaire vide
users = {}

# Fichier de données
DATA_FILE = "data.json"
GRADES_FILE = "grades.json"
SETTINGS_FILE = "settings.json"
SHIFTS_FILE = "shifts.json"
ADVERTS_FILE = "adverts.json"

# Grades par défaut: commission (%) et salaire_max (salaire fixe de base)
DEFAULT_GRADES = {
    "Apprenti": {"commission": 2, "salaire_fixe": 1500},
    "CDD": {"commission": 5, "salaire_fixe": 2800},
    "CDI": {"commission": 5, "salaire_fixe": 3200},
    "Chef d'équipe": {"commission": 10, "salaire_fixe": 4000},
    "DRH": {"commission": 5, "salaire_fixe": 5000},
    "CO-PDG": {"commission": 15, "salaire_fixe": 7000},
    "PDG": {"commission": 20, "salaire_fixe": 8000}
}

# --- Lottery Management ---
LOTTERY_FILE = "lottery.json"

def load_lottery_settings():
    """Charge les paramètres de la loterie"""
    try:
        with open(LOTTERY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        # Paramètres par défaut
        default_settings = {
            "ticket_price": 100,
            "last_updated": datetime.now().isoformat(),
            "updated_by": "system"
        }
        save_lottery_settings(default_settings)
        return default_settings
    except Exception as e:
        print(f"Erreur lors du chargement de la loterie: {e}")
        return {"ticket_price": 100}

def save_lottery_settings(settings):
    """Sauvegarde les paramètres de la loterie"""
    try:
        with open(LOTTERY_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de la loterie: {e}")

@app.route('/api/lottery/price', methods=['GET', 'OPTIONS'])
def get_lottery_price():
    """Route pour obtenir le prix de la loterie"""
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    lottery_settings = load_lottery_settings()
    return jsonify({
        "price": lottery_settings.get("ticket_price", 100)
    })

@app.route('/api/lottery/update', methods=['POST', 'OPTIONS'])
def update_lottery_price():
    """Route pour modifier le prix de la loterie"""
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    # Seuls PDG, CO-PDG et DRH peuvent modifier le prix
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403

    data = request.get_json()
    new_price = data.get('price')
    
    if new_price is None:
        return jsonify({"success": False, "message": "Prix requis"}), 400
        
    try:
        new_price = float(new_price)
        if new_price < 1:
            return jsonify({"success": False, "message": "Le prix doit être supérieur à 0"}), 400
    except ValueError:
        return jsonify({"success": False, "message": "Prix invalide"}), 400

    lottery_settings = load_lottery_settings()
    lottery_settings["ticket_price"] = new_price
    lottery_settings["last_updated"] = datetime.now().isoformat()
    lottery_settings["updated_by"] = session['user']['username']
    
    save_lottery_settings(lottery_settings)

    return jsonify({
        "success": True,
        "message": f"Prix de la loterie modifié à {new_price}$",
        "price": new_price
    })

@app.route('/api/lottery/history', methods=['GET', 'OPTIONS'])
def get_lottery_history():
    """Route pour obtenir l'historique des modifications de prix"""
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    
    lottery_settings = load_lottery_settings()
    
    # Retourner les infos de dernière modification
    return jsonify({
        "current_price": lottery_settings.get("ticket_price", 100),
        "last_updated": lottery_settings.get("last_updated"),
        "updated_by": lottery_settings.get("updated_by")
    })

# ...existing code...

def load_grades():
    try:
        with open(GRADES_FILE, 'r', encoding='utf-8') as f:
            grades = json.load(f)
            # S'assurer que toutes les clés existent
            for g, cfg in DEFAULT_GRADES.items():
                if g not in grades:
                    grades[g] = cfg
                else:
                    grades[g].setdefault('commission', cfg['commission'])
                    grades[g].setdefault('salaire_fixe', cfg['salaire_fixe'])
            return grades
    except FileNotFoundError:
        save_grades(DEFAULT_GRADES)
        return DEFAULT_GRADES

def save_grades(grades):
    with open(GRADES_FILE, 'w', encoding='utf-8') as f:
        json.dump(grades, f, indent=2, ensure_ascii=False)

# Réglages globaux (objectif hebdomadaire)
DEFAULT_SETTINGS = {
    "objectif_hebdo": 10000,
    "advert_title": "",
    "advert_image": "",
    "advert_text": ""
}

def load_settings():
    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)
            # Ensure key exists
            settings.setdefault('objectif_hebdo', DEFAULT_SETTINGS['objectif_hebdo'])
            settings.setdefault('advert_title', DEFAULT_SETTINGS['advert_title'])
            settings.setdefault('advert_image', DEFAULT_SETTINGS['advert_image'])
            settings.setdefault('advert_text', DEFAULT_SETTINGS['advert_text'])
            # Sinon, le charger depuis le fichier lottery.json
            if 'lottery_price' not in settings:
                lottery = load_lottery_settings()
                settings['lottery_price'] = lottery.get("ticket_price", 100)
            return settings
    except FileNotFoundError:
        # Try to create file; if not possible, return defaults
        try:
            save_settings(DEFAULT_SETTINGS)
        except PermissionError:
            pass
        return DEFAULT_SETTINGS
    except PermissionError:
        # Cannot read file due to permissions; use defaults
        return DEFAULT_SETTINGS

def save_settings(settings):
    try:
        # Si le prix de la loterie est dans les settings, le sauvegarder aussi dans lottery.json
        if 'lottery_price' in settings:
            lottery = load_lottery_settings()
            lottery["ticket_price"] = settings['lottery_price']
            lottery["last_updated"] = datetime.now().isoformat()
            lottery["updated_by"] = session.get('user', {}).get('username', 'system') if session else 'system'
            save_lottery_settings(lottery)
        
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except PermissionError:
        # Silently ignore if cannot write; settings will be in-memory only
        pass

def load_data():
    try:
        with open(DATA_FILE, "r", encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "ventes_historique": [],
            "services_vendus": {},
            "ventes_par_jour": {},
            "total_mensuel": 0
        }

def save_data(data):
    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def load_json_safe(path, default):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        return default
    except Exception:
        return default

def save_json_safe(path, content):
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(content, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def calculate_derived_data(raw_data):
    ventes_par_jour = defaultdict(float)
    services_count = defaultdict(int)
    ventes_recentes = []
    
    # Semaine courante (Lundi->Dimanche) en Europe/Paris
    # Déterminer le fuseau Europe/Paris si disponible, sinon tomber en local
    if ZoneInfo:
        try:
            tz = ZoneInfo("Europe/Paris")
        except Exception:
            tz = None
    else:
        tz = None
    now = datetime.now(tz) if tz else datetime.now()
    start_of_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    week_dates = [(start_of_week + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(0, 7)]

    for vente in raw_data.get("ventes_historique", []):
        date_str = vente.get("date", "")[:10]
        montant = vente.get("total", 0)
        if date_str in week_dates:
            ventes_par_jour[date_str] += montant
        ventes_recentes.append(montant)
        
        for item in vente.get("items", []):
            services_count[item.get("name")] += item.get("qty", 0)
    
    accueil_data = [ventes_par_jour.get(day, 0) for day in week_dates]
    ventes_data = list(services_count.values())[:7] if services_count else [0] * 7
    
    total_ventes = sum(accueil_data)
    bilan_data = []
    cumul = 0
    for vente in accueil_data:
        cumul += vente
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
        "nb_ventes": len(raw_data.get("ventes_historique", []))
    }

@app.route('/api/my_stats', methods=['GET', 'OPTIONS'])
def get_my_stats():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    username = session['user']['username']
    user_data = users.get(username, {})
    grades_cfg = load_grades()
    user_grade = user_data.get("grade", "")
    grade_cfg = grades_cfg.get(user_grade, {"commission": 0, "salaire_fixe": 0})
    
    # Calculer les stats personnelles
    raw_data = load_data()
    user_ventes = [
        vente for vente in raw_data.get("ventes_historique", [])
        if vente.get("vendeur") == username
    ]
    
    total_ca_personnel = sum(vente.get("total", 0) for vente in user_ventes)
    nb_ventes_personnel = len(user_ventes)
    
    # Calculer la commission et le salaire total
    commission_amount = (total_ca_personnel * grade_cfg.get("commission", 0)) / 100
    salaire_total = grade_cfg.get("salaire_fixe", 0) + commission_amount
    
    # Calculer la progression vers l'objectif
    # Objectif désormais global et hebdomadaire
    settings = load_settings()
    objectif_ca = settings.get("objectif_hebdo", 0)
    progression_objectif = (total_ca_personnel / objectif_ca * 100) if objectif_ca > 0 else 0
    
    return jsonify({
        "user_info": {
            "nom": user_data.get("nom", ""),
            "prenom": user_data.get("prenom", ""),
            "grade": user_data.get("grade", ""),
            "salaire_fixe": grade_cfg.get("salaire_fixe", 0),
            "commission_pourcentage": grade_cfg.get("commission", 0),
            "objectif_ca": objectif_ca
        },
        "performance": {
            "total_ca": total_ca_personnel,
            "nb_ventes": nb_ventes_personnel,
            "commission_amount": commission_amount,
            "salaire_total": salaire_total,
            "progression_objectif": min(progression_objectif, 100)
        }
    })

# Decorator pour vérifier l'authentification
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated_function

# Routes principales
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

# Routes API
@app.route('/api/login', methods=['POST', 'OPTIONS'])
def api_login():
    if request.method == 'OPTIONS':
        return '', 200
        
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    
    if username in users and users[username]["password"] == password:
        session['user'] = {
            "username": username,
            "grade": users[username]["grade"]
        }
        return jsonify({"success": True, "user": session['user']})
    
    return jsonify({"success": False, "message": "Identifiants incorrects"})

@app.route('/api/current_user', methods=['GET', 'OPTIONS'])
def get_current_user():
    if request.method == 'OPTIONS':
        return '', 200
    return jsonify(session.get('user', {}))

@app.route('/api/data', methods=['GET', 'OPTIONS'])
def get_data():
    if request.method == 'OPTIONS':
        return '', 200
    raw_data = load_data()
    calculated_data = calculate_derived_data(raw_data)
    return jsonify(calculated_data)

# ...existing code...

@app.route('/api/users/update', methods=['POST', 'OPTIONS'])
def update_user():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
        
    # Vérifier les permissions
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
        
    data = request.get_json()
    username = data.get('username')
    updates = data.get('updates', {})
    
    if not username or not updates:
        return jsonify({"success": False, "message": "Données manquantes"}), 400
        
    try:
        # Charger les utilisateurs
        with open('users.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            
        if username not in users:
            return jsonify({"success": False, "message": "Utilisateur non trouvé"}), 404
            
        # Mettre à jour les données
        users[username].update(updates)
        
        # Sauvegarder les modifications
        with open('users.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
            
        return jsonify({
            "success": True,
            "message": "Utilisateur mis à jour",
            "user": users[username]
        })
        
    except Exception as e:
        print(f"Erreur mise à jour utilisateur: {e}")
        return jsonify({"success": False, "message": str(e)}), 500

# ...existing code...

@app.route('/api/users/update_grade', methods=['POST', 'OPTIONS'])
def update_user_grade_route():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    # Seuls PDG, CO-PDG et DRH peuvent modifier les grades
    user_grade = session['user']['grade']
    if user_grade not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    
    data = request.get_json()
    username = data.get('username')
    new_grade = data.get('grade')
    
    if not username or not new_grade:
        return jsonify({"success": False, "message": "Données manquantes"})
    
    if username not in users:
        return jsonify({"success": False, "message": "Utilisateur non trouvé"})
    
    # Validation des nouveaux grades
    grades_valides = ['Apprenti', 'CDD', 'CDI', 'Chef d\'équipe', 'DRH', 'CO-PDG', 'PDG']
    if new_grade not in grades_valides:
        return jsonify({"success": False, "message": "Grade invalide"})
    
    users[username]["grade"] = new_grade
    save_users()
    
    return jsonify({"success": True, "message": f"Grade de {username} mis à jour vers {new_grade}"})
@app.route('/api/cart', methods=['POST', 'OPTIONS'])
def receive_cart():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    cart_items = request.get_json()
    if not cart_items:
        return jsonify({"error": "Panier vide"}), 400
    
    total = sum(item["price"] * item["qty"] for item in cart_items)
    
    data = load_data()
    
    nouvelle_vente = {
        "date": datetime.now().isoformat(),
        "total": total,
        "items": cart_items,
        "id": len(data.get("ventes_historique", [])) + 1,
        "vendeur": session['user']['username']
    }
    
    if "ventes_historique" not in data:
        data["ventes_historique"] = []
    data["ventes_historique"].append(nouvelle_vente)
    
    if "services_vendus" not in data:
        data["services_vendus"] = {}
    
    for item in cart_items:
        service_name = item["name"]
        if service_name in data["services_vendus"]:
            data["services_vendus"][service_name] += item["qty"]
        else:
            data["services_vendus"][service_name] = item["qty"]
    
    save_data(data)
    return jsonify({"success": True, "message": "Vente enregistrée"})

@app.route('/api/my_data', methods=['GET', 'OPTIONS'])
def get_my_data():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    raw_data = load_data()
    
    user_ventes = [
        vente for vente in raw_data.get("ventes_historique", [])
        if vente.get("vendeur") == session['user']['username']
    ]
    
    user_raw_data = raw_data.copy()
    user_raw_data["ventes_historique"] = user_ventes
    
    calculated_data = calculate_derived_data(user_raw_data)
    # Inclure la liste brute des ventes de l'utilisateur pour l'affichage détaillé
    calculated_data["ventes_historique"] = user_ventes
    return jsonify(calculated_data)

@app.route('/api/users', methods=['GET', 'OPTIONS'])
def get_users_route():
    if request.method == 'OPTIONS':
        return '', 200
        
    # Vérifier que l'utilisateur a le droit de voir la gestion des utilisateurs
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    # Seuls PDG, CO-PDG et DRH peuvent accéder
    user_grade = session['user']['grade']
    if user_grade not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    
    return jsonify(users)

@app.route('/api/users/delete', methods=['POST', 'DELETE', 'OPTIONS'])
def delete_user_route():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    # Autoriser PDG, CO-PDG et DRH à supprimer
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
    
    data = request.get_json()
    username = data.get('username')
    
    if not username:
        return jsonify({"success": False, "message": "Nom d'utilisateur requis"})
    
    if username not in users:
        return jsonify({"success": False, "message": "Utilisateur non trouvé"})
    
    if username == session['user']['username']:
        return jsonify({"success": False, "message": "Vous ne pouvez pas supprimer votre propre compte"})
    
    del users[username]
    save_users()
    
    return jsonify({"success": True, "message": f"Utilisateur {username} supprimé avec succès"})

@app.route('/api/global_data', methods=['GET', 'OPTIONS'])
def get_global_data():
    if request.method == 'OPTIONS':
        return '', 200
        
    raw_data = load_data()
    calculated_data = calculate_derived_data(raw_data)
    return jsonify(calculated_data)

@app.route('/api/users/add', methods=['POST', 'OPTIONS'])
def add_user_route():
    if request.method == 'OPTIONS':
        return '', 200
        
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    # Seuls PDG, CO-PDG et DRH peuvent ajouter des utilisateurs
    user_grade = session['user']['grade']
    if user_grade not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403

    
    data = request.get_json()
    username = data.get('username')
    password = data.get('password')
    nom = data.get('nom')
    prenom = data.get('prenom')
    grade = data.get('grade')
    # salaire_fixe et commission sont désormais définis par grade
    # objectif_ca est désormais global; ne pas le lire ici
    
    # Validation des champs requis
    if not all([username, password, nom, prenom, grade]):
        return jsonify({"success": False, "message": "Tous les champs obligatoires sont requis"})
    
    if username in users:
        return jsonify({"success": False, "message": "Nom d'utilisateur déjà existant"})
    
    # Validation des nouveaux grades
    grades_valides = ['Apprenti', 'CDD', 'CDI', 'Chef d\'équipe', 'DRH', 'CO-PDG', 'PDG']
    if grade not in grades_valides:
        return jsonify({"success": False, "message": "Grade invalide"})
    
    # plus de validation commission ici car dépend du grade
    
    # Créer le nouvel utilisateur
    users[username] = {
        "password": password,
        "grade": grade,
        "nom": nom,
        "prenom": prenom,
        # Les paramètres salaire/commission sont pilotés par le grade
        # objectif_ca est global
    }
    
    save_users()
    return jsonify({"success": True, "message": f"Utilisateur {username} ajouté avec succès"})

@app.route('/api/settings', methods=['GET', 'OPTIONS'])
def get_settings_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    return jsonify(load_settings())

@app.route('/api/settings/update', methods=['POST', 'OPTIONS'])
def update_settings_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    user_grade = session['user']['grade']
    if user_grade not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403

    body = request.get_json() or {}
    settings = load_settings()
    # objectif_hebdo (optionnel)
    if 'objectif_hebdo' in body:
        try:
            objectif_val = float(body.get('objectif_hebdo'))
            if objectif_val < 0:
                return jsonify({"success": False, "message": "L'objectif doit être positif"})
            settings['objectif_hebdo'] = objectif_val
        except (TypeError, ValueError):
            return jsonify({"success": False, "message": "Valeur invalide pour objectif_hebdo"})
    # Modèle d'advert (optionnel)
    if 'advert_title' in body:
        settings['advert_title'] = str(body.get('advert_title') or '')
    if 'advert_image' in body:
        settings['advert_image'] = str(body.get('advert_image') or '')
    if 'advert_text' in body:
        settings['advert_text'] = str(body.get('advert_text') or '')
    save_settings(settings)
    return jsonify({"success": True, "message": "Réglages mis à jour"})

# --- Shifts (prise de service) ---
@app.route('/api/shifts/logs', methods=['GET'])
def shifts_logs():
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    
    if session['user']['grade'] not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403
        
    shifts = load_json_safe(SHIFTS_FILE, [])
    
    enriched_shifts = []
    for shift in shifts:
        try:
            # Assurer que les dates sont au bon format
            start_time = datetime.fromisoformat(shift['start'].replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(shift['end'].replace('Z', '+00:00')) if shift['end'] else datetime.now()
            
            # Calculer la durée
            duration = end_time - start_time
            hours = duration.seconds // 3600
            minutes = (duration.seconds % 3600) // 60
            
            # Formater les dates en français
            start_str = start_time.strftime("%d/%m/%Y à %H:%M:%S")
            end_str = end_time.strftime("%d/%m/%Y à %H:%M:%S") if shift['end'] else "En cours"
            
            enriched_shifts.append({
                "username": shift['username'],
                "start": start_str,
                "end": end_str,
                "duration": f"{hours}h {minutes}min",
                "duration_minutes": duration.seconds // 60,
                "is_active": shift['end'] is None
            })
        except (ValueError, TypeError) as e:
            print(f"Erreur avec le shift: {shift}, erreur: {e}")
            continue
    
    # Trier par date décroissante
    enriched_shifts.sort(key=lambda x: x['start'], reverse=True)
    
    return jsonify(enriched_shifts)

@app.route('/api/shifts/start', methods=['POST'])
def start_shift():
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
        
    username = session['user']['username']
    shifts = load_json_safe(SHIFTS_FILE, [])
    
    # Vérifier si un shift est déjà actif
    active_shift = next((s for s in shifts if s['username'] == username and s['end'] is None), None)
    if active_shift:
        return jsonify({"success": True, "message": "Shift déjà en cours", "shift": active_shift})
    
    # Créer nouveau shift avec date ISO format
    new_shift = {
        "username": username,
        "start": datetime.now().isoformat(),
        "end": None
    }
    
    shifts.append(new_shift)
    save_json_safe(SHIFTS_FILE, shifts)
    return jsonify({"success": True, "shift": new_shift})

@app.route('/api/shifts/stop', methods=['POST'])
def stop_shift():
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
        
    username = session['user']['username']
    shifts = load_json_safe(SHIFTS_FILE, [])
    
    # Trouver le dernier shift actif
    for shift in reversed(shifts):
        if shift['username'] == username and shift['end'] is None:
            shift['end'] = datetime.now().isoformat()
            save_json_safe(SHIFTS_FILE, shifts)
            return jsonify({"success": True, "shift": shift})
    
    return jsonify({"success": False, "message": "Aucun shift en cours"})

# --- Adverts ---
@app.route('/api/adverts/create', methods=['POST'])
def create_advert():
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    data = request.get_json() or {}
    title = data.get('title', '').strip()
    image = data.get('image', '').strip()
    text = data.get('text', '').strip()
    if not title and not text:
        return jsonify({"success": False, "message": "Contenu vide"})
    adverts = load_json_safe(ADVERTS_FILE, [])
    entry = {
        "username": session['user']['username'],
        "date": datetime.now().isoformat(),
        "title": title,
        "image": image,
        "text": text
    }
    adverts.append(entry)
    save_json_safe(ADVERTS_FILE, adverts)
    return jsonify({"success": True, "advert": entry})

@app.route('/api/adverts/logs', methods=['GET'])
def adverts_logs():
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    # Interdit au DRH (mais PDG et CO-PDG OK)
    grade = session['user']['grade']
    if grade == 'DRH':
        return jsonify({"error": "Accès refusé"}), 403
    if grade not in ['PDG', 'CO-PDG']:
        return jsonify({"error": "Accès refusé"}), 403
    adverts = load_json_safe(ADVERTS_FILE, [])
    return jsonify(adverts)

@app.route('/api/grades', methods=['GET', 'OPTIONS'])
def get_grades_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    return jsonify(load_grades())

@app.route('/api/grades/update', methods=['POST', 'OPTIONS'])
def update_grade_route():
    if request.method == 'OPTIONS':
        return '', 200
    if 'user' not in session:
        return jsonify({"error": "Non authentifié"}), 401
    # Seuls PDG, CO-PDG et DRH peuvent modifier les règles de grade
    user_grade = session['user']['grade']
    if user_grade not in ['PDG', 'CO-PDG', 'DRH']:
        return jsonify({"error": "Accès refusé"}), 403

    body = request.get_json() or {}
    grade_name = body.get('grade')
    commission = body.get('commission')
    salaire_fixe = body.get('salaire_fixe')

    if not grade_name:
        return jsonify({"success": False, "message": "Grade manquant"})

    grades_cfg = load_grades()
    if grade_name not in grades_cfg:
        return jsonify({"success": False, "message": "Grade invalide"})

    # Validations
    try:
        if commission is not None:
            commission_val = float(commission)
            if commission_val < 0 or commission_val > 100:
                return jsonify({"success": False, "message": "Commission doit être entre 0 et 100"})
            grades_cfg[grade_name]['commission'] = commission_val
        if salaire_fixe is not None:
            salaire_val = float(salaire_fixe)
            if salaire_val < 0:
                return jsonify({"success": False, "message": "Salaire fixe ne peut pas être négatif"})
            grades_cfg[grade_name]['salaire_fixe'] = salaire_val
    except ValueError:
        return jsonify({"success": False, "message": "Valeurs invalides"})

    save_grades(grades_cfg)
    return jsonify({"success": True, "message": f"Paramètres du grade {grade_name} mis à jour"})

def save_users():
    """Sauvegarde les utilisateurs dans un fichier JSON"""
    try:
        with open('users.json', 'w', encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde des utilisateurs: {e}")

def load_users():
    """Charge les utilisateurs depuis un fichier JSON"""
    global users
    try:
        with open('users.json', 'r', encoding='utf-8') as f:
            users = json.load(f)
            print("Utilisateurs chargés:", users)
    except FileNotFoundError:
        # Utiliser les utilisateurs par défaut
        # Utilisateurs par défaut avec nouveaux grades
        users = {
            "admin": {
                "password": "admin123", 
                "grade": "PDG", 
                "nom": "Dupont",
                "prenom": "Pierre",
                "salaire_fixe": 8000,
                "commission": 20,
                "objectif_ca": 50000
            },
            "rh": {
                "password": "rh123", 
                "grade": "DRH", 
                "nom": "Martin",
                "prenom": "Marie",
                "salaire_fixe": 5000,
                "commission": 5,
                "objectif_ca": 0
            },
            "chef1": {
                "password": "chef123", 
                "grade": "Chef d'équipe", 
                "nom": "Leroy",
                "prenom": "Jean",
                "salaire_fixe": 4000,
                "commission": 10,
                "objectif_ca": 30000
            },
            "employe1": {
                "password": "cdi123", 
                "grade": "CDI", 
                "nom": "Bernard",
                "prenom": "Sophie",
                "salaire_fixe": 3200,
                "commission": 5,
                "objectif_ca": 20000
            },
            "employe2": {
                "password": "cdd123", 
                "grade": "CDD", 
                "nom": "Petit",
                "prenom": "Thomas",
                "salaire_fixe": 2800,
                "commission": 5,
                "objectif_ca": 15000
            },
            "apprenti1": {
                "password": "app123", 
                "grade": "Apprenti", 
                "nom": "Dubois",
                "prenom": "Lucas",
                "salaire_fixe": 1500,
                "commission": 2,
                "objectif_ca": 5000
            }
        }
        save_users()
        print("Utilisateurs par défaut créés")
    except Exception as e:
        print(f"Erreur lors du chargement des utilisateurs: {e}")

# Chargez les utilisateurs au démarrage
load_users()

if __name__ == '__main__':
    if not os.path.exists('data.json'):
        with open('data.json', 'w') as f:
            json.dump({
                "ventes_historique": [],
                "services_vendus": {},
                "ventes_par_jour": {},
                "total_mensuel": 0
            }, f)
    
    app.run(debug=True, port=5000, host='0.0.0.0')