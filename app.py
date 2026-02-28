import os
import json
from datetime import datetime, timedelta

# ------------------ Classe API pour communiquer avec JS ------------------
class Api:
    def __init__(self):
        # Utilisateur connecté par défaut (peut être changé via l'interface)
        self.current_user = {
            "username": "admin",
            "grade": "direction"  # grades: employe, responsable, direction
        }
    
    def getCurrentUser(self):
        """Retourne l'utilisateur actuel"""
        return self.current_user
    
    def login(self, username, password):
        """Connexion utilisateur (simulation)"""
        users = self.getUsers()
        
        if username in users and users[username]["password"] == password:
            self.current_user = {
                "username": username,
                "grade": users[username]["grade"]
            }
            print(f"Connexion réussie: {username} ({users[username]['grade']})")
            return {"success": True, "user": self.current_user}
        
        print(f"Échec de connexion pour: {username}")
        return {"success": False, "message": "Identifiants incorrects"}
    
    def getUsers(self):
        """Récupère la liste des utilisateurs"""
        try:
            with open("users.json", "r", encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # Créer les utilisateurs par défaut
            default_users = {
                "admin": {"password": "admin123", "grade": "direction", "nom": "Administrateur"},
                "manager": {"password": "manager123", "grade": "responsable", "nom": "Manager"},
                "employe1": {"password": "emp123", "grade": "employe", "nom": "Employé 1"},
                "employe2": {"password": "emp456", "grade": "employe", "nom": "Employé 2"}
            }
            self.saveUsers(default_users)
            return default_users
    
    def saveUsers(self, users):
        """Sauvegarde les utilisateurs"""
        with open("users.json", "w", encoding='utf-8') as f:
            json.dump(users, f, indent=2, ensure_ascii=False)
    
    def updateUserGrade(self, username, new_grade):
        """Met à jour le grade d'un utilisateur (réservé à la direction)"""
        if self.current_user["grade"] != "direction":
            return {"success": False, "message": "Accès refusé: seule la direction peut modifier les grades"}
        
        users = self.getUsers()
        if username not in users:
            return {"success": False, "message": "Utilisateur non trouvé"}
        
        users[username]["grade"] = new_grade
        self.saveUsers(users)
        
        print(f"Grade mis à jour: {username} -> {new_grade}")
        return {"success": True, "message": f"Grade de {username} mis à jour vers {new_grade}"}
    
    def addUser(self, username, password, grade, nom):
        """Ajoute un nouvel utilisateur (réservé à la direction)"""
        if self.current_user["grade"] != "direction":
            return {"success": False, "message": "Accès refusé: seule la direction peut ajouter des utilisateurs"}
        
        users = self.getUsers()
        if username in users:
            return {"success": False, "message": "Nom d'utilisateur déjà existant"}
        
        users[username] = {
            "password": password,
            "grade": grade,
            "nom": nom
        }
        self.saveUsers(users)
        
        print(f"Nouvel utilisateur ajouté: {username} ({grade})")
        return {"success": True, "message": f"Utilisateur {username} ajouté avec succès"}
    def getData(self):
        """Récupère les données depuis le fichier JSON"""
        try:
            with open("data.json", "r", encoding='utf-8') as f:
                data = json.load(f)
                
            # Calculer les données dérivées à partir des ventes réelles
            calculated_data = self.calculateDerivedData(data)
            return calculated_data
            
        except FileNotFoundError:
            # Créer le fichier avec des données par défaut vides
            default_data = {
                "ventes_historique": [],  # Liste de toutes les ventes avec timestamps
                "services_vendus": {},    # Compteur des services vendus
                "ventes_par_jour": {},    # Ventes groupées par jour
                "total_mensuel": 0,       # Total du mois en cours
                "salaires": [3000, 3200, 3100, 3300, 3150, 3050, 3250],  # Données fixes
                "charges": [500, 600, 550, 650, 575, 525, 625]           # Données fixes
            }
            self.saveData(default_data)
            return self.calculateDerivedData(default_data)
    def calculateDerivedData(self, raw_data):
        """Calcule les données pour les graphiques à partir des ventes réelles"""
        from collections import defaultdict
        
        # Initialiser les structures de données
        ventes_par_jour = defaultdict(float)
        services_count = defaultdict(int)
        ventes_recentes = []
        
        # Traiter l'historique des ventes
        for vente in raw_data.get("ventes_historique", []):
            date = vente["date"][:10]  # YYYY-MM-DD
            montant = vente["total"]
            
            ventes_par_jour[date] += montant
            ventes_recentes.append(montant)
            
            # Compter les services
            for item in vente["items"]:
                services_count[item["name"]] += item["qty"]
        
        # Obtenir les 7 derniers jours
        today = datetime.now()
        last_7_days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(6, -1, -1)]
        
        # Données pour les graphiques
        accueil_data = [ventes_par_jour.get(day, 0) for day in last_7_days]
        ventes_data = list(services_count.values())[:7] if services_count else [0] * 7
        
        # Calcul du bilan (progression sur 7 périodes)
        total_ventes = sum(accueil_data)
        bilan_data = []
        cumul = 0
        for i, vente in enumerate(accueil_data):
            cumul += vente
            bilan_data.append(cumul)
        
        # Ventes récentes (dernières 7 ventes)
        recentes_data = ventes_recentes[-7:] if len(ventes_recentes) >= 7 else ventes_recentes + [0] * (7 - len(ventes_recentes))
        
        return {
            "accueil": accueil_data,
            "ventes": ventes_data,
            "bilan": bilan_data,
            "recentes": recentes_data,
            "salaires": raw_data.get("salaires", [3000, 3200, 3100, 3300, 3150, 3050, 3250]),
            "charges": raw_data.get("charges", [500, 600, 550, 650, 575, 525, 625]),
            "services_stats": dict(services_count),
            "total_ca": total_ventes,
            "nb_ventes": len(raw_data.get("ventes_historique", []))
        }

    def saveData(self, data):
        """Sauvegarde les données dans le fichier JSON"""
        with open("data.json", "w", encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def receiveCart(self, cart_items):
        """Reçoit un panier complet et l'enregistre comme une vente"""
        if not cart_items or len(cart_items) == 0:
            return "Panier vide"
            
        total = sum(item["price"] * item["qty"] for item in cart_items)
        
        print(f"Vente reçue : {len(cart_items)} articles pour {total}€")
        
        # Charger les données existantes
        try:
            with open("data.json", "r", encoding='utf-8') as f:
                data = json.load(f)
        except FileNotFoundError:
            data = {
                "ventes_historique": [],
                "services_vendus": {},
                "ventes_par_jour": {},
                "total_mensuel": 0,
                "salaires": [3000, 3200, 3100, 3300, 3150, 3050, 3250],
                "charges": [500, 600, 550, 650, 575, 525, 625]
            }
        
        # Ajouter la nouvelle vente
        nouvelle_vente = {
            "date": datetime.now().isoformat(),
            "total": total,
            "items": cart_items,
            "id": len(data.get("ventes_historique", [])) + 1
        }
        
        if "ventes_historique" not in data:
            data["ventes_historique"] = []
        
        data["ventes_historique"].append(nouvelle_vente)
        
        # Mettre à jour les compteurs de services
        if "services_vendus" not in data:
            data["services_vendus"] = {}
            
        for item in cart_items:
            service_name = item["name"]
            if service_name in data["services_vendus"]:
                data["services_vendus"][service_name] += item["qty"]
            else:
                data["services_vendus"][service_name] = item["qty"]
        
        # Sauvegarder
        self.saveData(data)
        
        print(f"Vente enregistrée avec succès. Total des ventes: {len(data['ventes_historique'])}")
        return "OK"

def main():
    # Vérifier que le fichier HTML existe
    html_file = os.path.abspath("test.html")
    if not os.path.exists(html_file):
        print(f"Erreur : Le fichier {html_file} n'existe pas !")
        return
    
    # Créer l'URL pour le fichier HTML
    url = f"file:///{html_file.replace(os.sep, '/')}"
    
    # Créer l'instance de l'API
    api = Api()
    print("Lancement de l'application...")
    print(f"Fichier HTML : {html_file}")

if __name__ == "__main__":
    main()