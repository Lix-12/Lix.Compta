# loterie.py
from flask import Flask, request, jsonify, session, redirect
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
import json
from datetime import datetime
import random
import string
from functools import wraps

DB_CONFIG = {
    'host': 'switchback.proxy.rlwy.net',
    'port': 18902,
    'user': 'root',
    'password': 'aFyeiXTJRMuwpgQSZByoOiyOvyLEJlhK',
    'database': 'railway',
    'charset': 'utf8mb4',
    'autocommit': True
}

app = Flask(__name__, static_folder='.', static_url_path='')

def get_db():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        return conn
    except Error as e:
        print(f"Erreur MySQL: {e}")
        return None

class Loterie:
    def __init__(self):
        self._init_db()
    
    def _init_db(self):
        """Initialise les tables nécessaires pour la loterie"""
        conn = get_db()
        if not conn:
            print("Impossible de se connecter à la base de données")
            return
        
        cursor = conn.cursor()
        
        try:
            # Table des clients de loterie
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS loterie_clients (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    prenom VARCHAR(100) NOT NULL,
                    nom VARCHAR(100) NOT NULL,
                    telephone VARCHAR(20) NOT NULL,
                    email VARCHAR(255),
                    date_creation DATETIME NOT NULL,
                    total_achats INT DEFAULT 0,
                    nb_tickets_achetes INT DEFAULT 0,
                    derniere_activite DATETIME,
                    notes TEXT,
                    INDEX idx_telephone (telephone)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            ''')
            
            # Table des tickets de loterie
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS loterie_tickets (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    numero_ticket VARCHAR(50) UNIQUE NOT NULL,
                    client_id INT NOT NULL,
                    grille INT NOT NULL,
                    numeros VARCHAR(50) NOT NULL,  -- Stocké comme "n1,n2,n3"
                    prix INT NOT NULL,
                    date_achat DATETIME NOT NULL,
                    vendu_par VARCHAR(50) NOT NULL,
                    INDEX idx_client (client_id),
                    INDEX idx_date (date_achat),
                    FOREIGN KEY (client_id) REFERENCES loterie_clients(id) ON DELETE CASCADE,
                    FOREIGN KEY (vendu_par) REFERENCES users(username) ON DELETE CASCADE
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            ''')
            
            # Table des paramètres de loterie (juste le prix)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS loterie_settings (
                    id INT PRIMARY KEY DEFAULT 1,
                    prix_ticket INT DEFAULT 100,
                    CHECK (id = 1)
                ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
            ''')
            
            # Insérer les paramètres par défaut si nécessaire
            cursor.execute('SELECT * FROM loterie_settings WHERE id = 1')
            result = cursor.fetchone()
            if not result:
                cursor.execute('''
                    INSERT INTO loterie_settings (id, prix_ticket)
                    VALUES (1, 100)
                ''')
            
            conn.commit()
            print("Tables de loterie créées/vérifiées avec succès")
            
        except Error as e:
            print(f"Erreur lors de l'initialisation des tables: {e}")
            conn.rollback()
        finally:
            cursor.close()
            conn.close()
    
    # ========== GESTION DES CLIENTS ==========
    
    def trouver_ou_creer_client(self, prenom, nom, telephone, email=None, notes=None):
        """
        Trouve un client existant par téléphone ou en crée un nouveau
        """
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            # Chercher par téléphone
            cursor.execute('''
                SELECT * FROM loterie_clients 
                WHERE telephone = %s 
                ORDER BY derniere_activite DESC 
                LIMIT 1
            ''', (telephone,))
            
            client = cursor.fetchone()
            maintenant = datetime.now()
            
            if client:
                # Mettre à jour la dernière activité
                client_id = client['id']
                cursor.execute('''
                    UPDATE loterie_clients 
                    SET derniere_activite = %s 
                    WHERE id = %s
                ''', (maintenant, client_id))
            else:
                # Créer un nouveau client
                cursor.execute('''
                    INSERT INTO loterie_clients 
                    (prenom, nom, telephone, email, date_creation, derniere_activite, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (prenom, nom, telephone, email, maintenant, maintenant, notes))
                client_id = cursor.lastrowid
            
            conn.commit()
            return client_id
            
        except Error as e:
            print(f"Erreur lors de la recherche/création client: {e}")
            conn.rollback()
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_client(self, client_id):
        """Récupère les informations d'un client"""
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('SELECT * FROM loterie_clients WHERE id = %s', (client_id,))
            client = cursor.fetchone()
            return client
        except Error as e:
            print(f"Erreur lors de la récupération du client: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_client_par_telephone(self, telephone):
        """Récupère un client par son téléphone"""
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('SELECT * FROM loterie_clients WHERE telephone = %s', (telephone,))
            client = cursor.fetchone()
            return client
        except Error as e:
            print(f"Erreur lors de la recherche par téléphone: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_tous_les_clients(self, limite=100):
        """Récupère tous les clients"""
        conn = get_db()
        if not conn:
            return []
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('''
                SELECT * FROM loterie_clients 
                ORDER BY derniere_activite DESC 
                LIMIT %s
            ''', (limite,))
            clients = cursor.fetchall()
            return clients
        except Error as e:
            print(f"Erreur lors de la récupération des clients: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    # ========== GESTION DES TICKETS ==========
    
    def get_prix_ticket(self):
        """Récupère le prix actuel d'un ticket"""
        conn = get_db()
        if not conn:
            return 100
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('SELECT prix_ticket FROM loterie_settings WHERE id = 1')
            result = cursor.fetchone()
            return result['prix_ticket'] if result else 100
        except Error as e:
            print(f"Erreur lors de la récupération du prix: {e}")
            return 100
        finally:
            cursor.close()
            conn.close()
    
    def set_prix_ticket(self, nouveau_prix):
        """Modifie le prix du ticket"""
        conn = get_db()
        if not conn:
            return False
        
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                UPDATE loterie_settings 
                SET prix_ticket = %s 
                WHERE id = 1
            ''', (nouveau_prix,))
            conn.commit()
            return True
        except Error as e:
            print(f"Erreur lors de la modification du prix: {e}")
            conn.rollback()
            return False
        finally:
            cursor.close()
            conn.close()
    
    def _generer_numero_ticket_unique(self):
        """Génère un numéro de ticket unique"""
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor()
        
        try:
            while True:
                # Format: LOT-AAAANNNN (ex: LOT-2024001234)
                annee = datetime.now().strftime('%Y')
                random_part = ''.join(random.choices(string.digits, k=6))
                numero = f"LOT-{annee}{random_part}"
                
                cursor.execute('SELECT id FROM loterie_tickets WHERE numero_ticket = %s', (numero,))
                exists = cursor.fetchone()
                
                if not exists:
                    return numero
        finally:
            cursor.close()
            conn.close()
    
    def acheter_tickets(self, client_data, tickets_data, vendeur):
        """
        Achète un ou plusieurs tickets de loterie
        
        Args:
            client_data: dict avec prenom, nom, telephone, email (optionnel)
            tickets_data: list de dict avec grille et numeros [n1, n2, n3]
            vendeur: username de la personne qui vend
        """
        conn = get_db()
        if not conn:
            return {
                'success': False,
                'message': "Impossible de se connecter à la base de données"
            }
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            # 1. Trouver ou créer le client
            client_id = self.trouver_ou_creer_client(
                prenom=client_data['prenom'],
                nom=client_data['nom'],
                telephone=client_data['telephone'],
                email=client_data.get('email')
            )
            
            if not client_id:
                return {
                    'success': False,
                    'message': "Erreur lors de la création du client"
                }
            
            # 2. Récupérer le prix du ticket
            prix_unitaire = self.get_prix_ticket()
            prix_total = prix_unitaire * len(tickets_data)
            
            # 3. Créer les tickets
            date_achat = datetime.now()
            tickets_crees = []
            
            for ticket in tickets_data:
                numero_ticket = self._generer_numero_ticket_unique()
                
                # Convertir la liste de numéros en chaîne "n1,n2,n3"
                numeros_str = ','.join(str(n) for n in sorted(ticket['numeros']))
                
                cursor.execute('''
                    INSERT INTO loterie_tickets 
                    (numero_ticket, client_id, grille, numeros, prix, date_achat, vendu_par)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    numero_ticket,
                    client_id,
                    ticket['grille'],
                    numeros_str,
                    prix_unitaire,
                    date_achat,
                    vendeur
                ))
                
                tickets_crees.append({
                    'numero': numero_ticket,
                    'grille': ticket['grille'],
                    'numeros': ticket['numeros'],
                    'prix': prix_unitaire
                })
            
            # 4. Mettre à jour les stats du client
            cursor.execute('''
                UPDATE loterie_clients 
                SET total_achats = total_achats + %s,
                    nb_tickets_achetes = nb_tickets_achetes + %s,
                    derniere_activite = %s
                WHERE id = %s
            ''', (prix_total, len(tickets_data), date_achat, client_id))
            
            conn.commit()
            
            return {
                'success': True,
                'message': f"{len(tickets_data)} ticket(s) acheté(s) avec succès",
                'client_id': client_id,
                'tickets': tickets_crees,
                'prix_total': prix_total,
                'date_achat': date_achat.isoformat()
            }
            
        except Error as e:
            print(f"Erreur lors de l'achat: {e}")
            conn.rollback()
            return {
                'success': False,
                'message': f"Erreur lors de l'achat: {str(e)}"
            }
        finally:
            cursor.close()
            conn.close()
    
    def get_tickets_client(self, client_id, limite=50):
        """Récupère tous les tickets d'un client"""
        conn = get_db()
        if not conn:
            return []
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('''
                SELECT * FROM loterie_tickets 
                WHERE client_id = %s 
                ORDER BY date_achat DESC 
                LIMIT %s
            ''', (client_id, limite))
            
            tickets = cursor.fetchall()
            
            # Convertir la chaîne de numéros en liste
            for ticket in tickets:
                ticket['numeros'] = [int(n) for n in ticket['numeros'].split(',')]
            
            return tickets
        except Error as e:
            print(f"Erreur lors de la récupération des tickets: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    def get_ticket(self, numero_ticket):
        """Récupère un ticket par son numéro"""
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('''
                SELECT t.*, c.prenom, c.nom, c.telephone 
                FROM loterie_tickets t
                JOIN loterie_clients c ON t.client_id = c.id
                WHERE t.numero_ticket = %s
            ''', (numero_ticket,))
            
            ticket = cursor.fetchone()
            
            if ticket:
                ticket['numeros'] = [int(n) for n in ticket['numeros'].split(',')]
            
            return ticket
        except Error as e:
            print(f"Erreur lors de la récupération du ticket: {e}")
            return None
        finally:
            cursor.close()
            conn.close()
    
    def get_tous_les_tickets(self, limite=100):
        """Récupère tous les tickets (pour l'admin)"""
        conn = get_db()
        if not conn:
            return []
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('''
                SELECT t.*, c.prenom, c.nom, c.telephone, u.username as vendeur_nom
                FROM loterie_tickets t
                JOIN loterie_clients c ON t.client_id = c.id
                LEFT JOIN users u ON t.vendu_par = u.username
                ORDER BY t.date_achat DESC 
                LIMIT %s
            ''', (limite,))
            
            tickets = cursor.fetchall()
            
            # Convertir la chaîne de numéros en liste
            for ticket in tickets:
                ticket['numeros'] = [int(n) for n in ticket['numeros'].split(',')]
            
            return tickets
        except Error as e:
            print(f"Erreur lors de la récupération des tickets: {e}")
            return []
        finally:
            cursor.close()
            conn.close()
    
    # ========== STATISTIQUES SIMPLES ==========
    
    def get_stats_ventes(self):
        """Récupère les statistiques de vente"""
        conn = get_db()
        if not conn:
            return {}
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            stats = {}
            
            # Nombre total de tickets
            cursor.execute('SELECT COUNT(*) as total FROM loterie_tickets')
            stats['total_tickets'] = cursor.fetchone()['total']
            
            # Chiffre d'affaires total
            cursor.execute('SELECT SUM(prix) as ca FROM loterie_tickets')
            stats['chiffre_affaires'] = cursor.fetchone()['ca'] or 0
            
            # Nombre de clients
            cursor.execute('SELECT COUNT(*) as total_clients FROM loterie_clients')
            stats['total_clients'] = cursor.fetchone()['total_clients']
            
            # Ventes aujourd'hui
            cursor.execute('''
                SELECT COUNT(*) as nb_tickets, SUM(prix) as total
                FROM loterie_tickets
                WHERE DATE(date_achat) = CURDATE()
            ''')
            today = cursor.fetchone()
            stats['aujourd_hui'] = {
                'nb_tickets': today['nb_tickets'] or 0,
                'total': today['total'] or 0
            }
            
            # Top vendeurs
            cursor.execute('''
                SELECT vendu_par, COUNT(*) as nb_tickets, SUM(prix) as total
                FROM loterie_tickets
                GROUP BY vendu_par
                ORDER BY total DESC
                LIMIT 5
            ''')
            stats['top_vendeurs'] = cursor.fetchall()
            
            return stats
            
        except Error as e:
            print(f"Erreur lors de la récupération des stats: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()
    
    def get_rapport_journalier(self, date=None):
        """Rapport des ventes pour une date donnée"""
        if date is None:
            date = datetime.now().date()
        
        conn = get_db()
        if not conn:
            return {}
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('''
                SELECT COUNT(*) as nb_tickets, SUM(prix) as total_ventes
                FROM loterie_tickets
                WHERE DATE(date_achat) = %s
            ''', (date,))
            
            row = cursor.fetchone()
            
            cursor.execute('''
                SELECT COUNT(DISTINCT client_id) as nb_clients
                FROM loterie_tickets
                WHERE DATE(date_achat) = %s
            ''', (date,))
            
            nb_clients = cursor.fetchone()['nb_clients']
            
            return {
                'date': date.isoformat(),
                'nb_tickets': row['nb_tickets'] or 0,
                'total_ventes': row['total_ventes'] or 0,
                'nb_clients': nb_clients or 0
            }
            
        except Error as e:
            print(f"Erreur lors de la récupération du rapport: {e}")
            return {}
        finally:
            cursor.close()
            conn.close()

# À AJOUTER DANS VOTRE app.py

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

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
    
    loterie = Loterie()
    resultat = loterie.acheter_tickets(
        client_data=client_data,
        tickets_data=tickets_data,
        vendeur=session['username']
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
        tickets = loterie.get_tickets_client(client['id'])
        return jsonify({
            'client': client,
            'tickets': tickets
        })
    
    return jsonify({'client': None})

@app.route('/api/loterie/tickets/recherche', methods=['GET'])
@login_required
def rechercher_ticket():
    """Recherche un ticket par son numéro"""
    numero = request.args.get('numero')
    if not numero:
        return jsonify({'error': 'Numéro de ticket requis'}), 400
    
    loterie = Loterie()
    ticket = loterie.get_ticket(numero)
    
    if ticket:
        return jsonify(ticket)
    
    return jsonify({'error': 'Ticket non trouvé'}), 404

@app.route('/api/loterie/stats', methods=['GET'])
@login_required
def get_stats_loterie():
    """Récupère les statistiques de vente"""
    loterie = Loterie()
    stats = loterie.get_stats_ventes()
    return jsonify(stats)