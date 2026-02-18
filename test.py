import streamlit as st
import json
import os
import hashlib
import time
from datetime import datetime

# ==========================================
# CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(
    page_title="NoVA AI - L'excellence Bureautique",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Constantes
DATA_FILE = "nova_database.json"
ADMIN_CODE = "02110240"
WHATSAPP_NUMBER = "2250171542505"

# ==========================================
# GESTION DES DONNÉES
# ==========================================
def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {"users": {}, "orders": [], "files": {}}
    return {"users": {}, "orders": [], "files": {}}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# Initialisation du store
if "db" not in st.session_state:
    st.session_state.db = load_data()
if "user" not in st.session_state:
    st.session_state.user = None
if "page" not in st.session_state:
    st.session_state.page = "home"

# ==========================================
# STYLE CSS PERSONNALISÉ
# ==========================================
def local_css():
    st.markdown("""
        <style>
        /* Global Style */
        .stApp {
            background-color: #0E1117;
            color: #E0E0E0;
        }
        
        /* Titres */
        .main-header {
            font-family: 'Trebuchet MS', sans-serif;
            background: linear-gradient(90deg, #00C9FF 0%, #92FE9D 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 3.5rem;
            text-align: center;
            margin-bottom: 1rem;
        }

        /* Cartes Premium */
        .premium-card {
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid #FFD700;
            border-radius: 15px;
            padding: 20px;
            text-align: center;
            box-shadow: 0 4px 15px rgba(255, 215, 0, 0.1);
        }

        /* Boutons */
        .stButton>button {
            width: 100%;
            border-radius: 8px;
            height: 3em;
            background-color: #1E88E5 !important;
            color: white !important;
            font-weight: bold;
            border: none;
            transition: 0.3s;
        }
        .stButton>button:hover {
            background-color: #1565C0 !important;
            transform: scale(1.02);
        }

        /* Status de commande */
        .status-badge {
            padding: 5px 12px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: bold;
        }
        
        /* WhatsApp Style */
        .wa-button {
            display: inline-block;
            background-color: #25D366;
            color: white !important;
            padding: 10px 20px;
            border-radius: 10px;
            text-decoration: none;
            font-weight: bold;
            margin-top: 10px;
        }
        </style>
    """, unsafe_allow_html=True)

# ==========================================
# COMPOSANTS UI
# ==========================================

def sidebar_nav():
    with st.sidebar:
        st.image("https://cdn-icons-png.flaticon.com/512/2103/2103633.png", width=100)
        st.title("Menu NoVA")
        
        if st.session_state.user:
            st.write(f"👤 **{st.session_state.user}**")
            if st.button("Se déconnecter"):
                st.session_state.user = None
                st.rerun()
        else:
            if st.button("Accéder à mon espace"):
                st.session_state.page = "login"
                st.rerun()

        st.divider()
        st.info("NoVA AI : Votre assistant bureautique propulsé par l'intelligence artificielle 24h/24.")
        
        # Bouton Support
        st.markdown(f"""
            <a href="https://wa.me/{WHATSAPP_NUMBER}?text=Besoin%20d'aide" class="wa-button">
                💬 Agent Support
            </a>
        """, unsafe_allow_html=True)

def login_page():
    st.markdown("<h1 class='main-header'>IDENTIFICATION</h1>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Connexion")
        with st.form("login_form"):
            username = st.text_input("Identifiant Nova")
            wa = st.text_input("Numéro WhatsApp")
            if st.form_submit_button("Entrer dans mon espace"):
                db = st.session_state.db
                if username in db["users"] and db["users"][username]["wa"] == wa:
                    st.session_state.user = username
                    st.session_state.page = "dashboard"
                    st.rerun()
                else:
                    st.error("Identifiants incorrects.")

    with col2:
        st.subheader("Nouveau Membre")
        with st.form("signup_form"):
            new_user = st.text_input("Choisir un Identifiant")
            new_wa = st.text_input("Numéro WhatsApp (Clé de sécurité)")
            if st.form_submit_button("Créer mon compte"):
                if new_user and new_wa:
                    db = st.session_state.db
                    if new_user not in db["users"]:
                        db["users"][new_user] = {"wa": new_wa, "date": str(datetime.now())}
                        save_data(db)
                        st.session_state.user = new_user
                        st.session_state.page = "dashboard"
                        st.success("Compte créé avec succès !")
                        st.rerun()
                    else:
                        st.warning("Cet identifiant est déjà utilisé.")

def dashboard_page():
    user = st.session_state.user
    db = st.session_state.db
    
    st.markdown(f"<h1 class='main-header'>BIENVENUE {user.upper()}</h1>", unsafe_allow_html=True)
    
    # Bannière Premium
    st.markdown("""
        <div class="premium-card">
            <h2 style="color:#FFD700;">🌟 MODE PREMIUM ACTIF (v3.0)</h2>
            <p>Bénéficiez de la puissance de calcul 10<sup>10</sup> pour vos traitements complexes.</p>
        </div>
    """, unsafe_allow_html=True)
    st.write("")

    tab1, tab2 = st.tabs(["🚀 DÉPLOYER UNE MISSION", "📂 MES LIVRABLES"])

    with tab1:
        st.subheader("Détails de l'intervention")
        service = st.selectbox("Type de Service", [
            "Data & Excel Analytics",
            "Exposé Complet & Mise en page",
            "Conception PowerPoint",
            "Design Graphique IA",
            "Rédaction CV & Lettre"
        ])
        
        details = st.text_area("Cahier des charges", placeholder="Décrivez précisément votre besoin...")
        
        if st.button("ACTIVER L'ALGORITHME NOVA"):
            if details:
                # Simulation de calcul
                with st.spinner("Initialisation des serveurs NoVA..."):
                    bar = st.progress(0)
                    for i in range(100):
                        time.sleep(0.02)
                        bar.progress(i + 1)
                
                # Enregistrement
                new_order = {
                    "id": hashlib.md5(str(time.time()).encode()).hexdigest()[:8].upper(),
                    "user": user,
                    "service": service,
                    "details": details,
                    "status": "En cours",
                    "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M")
                }
                db["orders"].append(new_order)
                save_data(db)
                st.success(f"Mission {new_order['id']} déployée avec succès !")
                st.balloons()
            else:
                st.error("Veuillez fournir les détails de la mission.")

    with tab2:
        st.subheader("Suivi de vos fichiers")
        
        # Filtre les commandes de l'utilisateur
        user_orders = [o for o in db["orders"] if o["user"] == user]
        user_files = db["files"].get(user, [])
        
        if not user_orders and not user_files:
            st.info("Aucune mission en cours ou terminée.")
        
        # Fichiers prêts
        if user_files:
            st.markdown("#### ✅ Fichiers prêts au téléchargement")
            for file in user_files:
                col1, col2 = st.columns([4, 1])
                col1.write(f"📄 **{file['name']}**")
                col2.markdown(f"[Télécharger]({file['url']})")
                st.divider()

        # Commandes en cours
        if user_orders:
            st.markdown("#### ⏳ Missions en cours de traitement")
            for order in reversed(user_orders):
                with st.expander(f"Mission {order['id']} - {order['service']}"):
                    st.write(f"**Date :** {order['timestamp']}")
                    st.write(f"**Description :** {order['details']}")
                    st.write(f"**Statut :** 🟠 {order['status']}")

# ==========================================
# CONSOLE ADMIN
# ==========================================
def admin_panel():
    with st.expander("🛠 Console de Livraison (Admin)"):
        code = st.text_input("Clé Maître", type="password")
        if code == ADMIN_CODE:
            db = st.session_state.db
            if not db["orders"]:
                st.write("Aucune demande en attente.")
            else:
                for i, order in enumerate(db["orders"]):
                    st.write(f"📦 {order['user']} | {order['service']}")
                    st.info(order['details'])
                    
                    link = st.text_input(f"Lien de téléchargement pour {order['id']}", key=f"link_{i}")
                    if st.button(f"Livrer la mission {order['id']}", key=f"btn_{i}"):
                        if link:
                            user = order['user']
                            if user not in db["files"]:
                                db["files"][user] = []
                            
                            db["files"][user].append({
                                "name": f"Livrable {order['service']} ({order['id']})",
                                "url": link
                            })
                            db["orders"].pop(i)
                            save_data(db)
                            st.rerun()

# ==========================================
# LOGIQUE PRINCIPALE
# ==========================================
local_css()
sidebar_nav()

if st.session_state.user:
    dashboard_page()
    admin_panel()
elif st.session_state.page == "login":
    login_page()
else:
    # Page d'accueil publique
    st.markdown("<h1 class='main-header'>NOVA AI PLATFORM</h1>", unsafe_allow_html=True)
    st.image("https://images.unsplash.com/photo-1677442136019-21780ecad995?q=80&w=1000&auto=format&fit=crop", use_container_width=True)
    
    st.markdown("""
    ### Bienvenue sur l'IA bureautique la plus avancée.
    - **Vitesse** : Traitement instantané de vos données.
    - **Qualité** : Rendu professionnel certifié NoVA.
    - **Disponibilité** : 24h/24 et 7j/7.
    """)
    
    if st.button("🚀 COMMENCER MAINTENANT"):
        st.session_state.page = "login"
        st.rerun()
