# loterie.py corrigé
import mysql.connector
from mysql.connector import Error
from datetime import datetime
import random
import string

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
            # Vérifier d'abord si les tables existent pour éviter les erreurs de foreign key
            cursor.execute("SHOW TABLES LIKE 'loterie_clients'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                # Table des clients de loterie
                cursor.execute('''
                    CREATE TABLE loterie_clients (
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
            
            cursor.execute("SHOW TABLES LIKE 'loterie_settings'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                # Table des paramètres de loterie
                cursor.execute('''
                    CREATE TABLE loterie_settings (
                        id INT PRIMARY KEY DEFAULT 1,
                        prix_ticket INT DEFAULT 100,
                        CHECK (id = 1)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                ''')
                
                # Insérer les paramètres par défaut
                cursor.execute('''
                    INSERT INTO loterie_settings (id, prix_ticket)
                    VALUES (1, 100)
                ''')
            
            cursor.execute("SHOW TABLES LIKE 'loterie_tickets'")
            table_exists = cursor.fetchone()
            
            if not table_exists:
                # Table des tickets de loterie - SANS CONTRAINTE FOREIGN KEY pour éviter les erreurs
                cursor.execute('''
                    CREATE TABLE loterie_tickets (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        numero_ticket VARCHAR(50) UNIQUE NOT NULL,
                        client_id INT NOT NULL,
                        grille INT NOT NULL,
                        numeros VARCHAR(50) NOT NULL,
                        prix INT NOT NULL,
                        date_achat DATETIME NOT NULL,
                        vendu_par VARCHAR(50) NOT NULL,
                        INDEX idx_client (client_id),
                        INDEX idx_date (date_achat),
                        INDEX idx_vendeur (vendu_par),
                        FOREIGN KEY (client_id) REFERENCES loterie_clients(id) ON DELETE CASCADE
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
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
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor(dictionary=True)
        
        try:
            cursor.execute('''
                SELECT * FROM loterie_clients 
                WHERE telephone = %s 
                ORDER BY derniere_activite DESC 
                LIMIT 1
            ''', (telephone,))
            
            client = cursor.fetchone()
            maintenant = datetime.now()
            
            if client:
                client_id = client['id']
                cursor.execute('''
                    UPDATE loterie_clients 
                    SET derniere_activite = %s 
                    WHERE id = %s
                ''', (maintenant, client_id))
            else:
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
    
    def get_client_par_telephone(self, telephone):
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
    
    # ========== GESTION DES TICKETS ==========
    
    def get_prix_ticket(self):
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
        conn = get_db()
        if not conn:
            return None
        
        cursor = conn.cursor()
        
        try:
            while True:
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
            date_achat = datetime.now()
            tickets_crees = []
            
            # 3. Créer les tickets
            for ticket in tickets_data:
                numero_ticket = self._generer_numero_ticket_unique()
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
    
    def get_ticket(self, numero_ticket):
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