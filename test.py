import streamlit as st
import json
import os
import hashlib
import time
from datetime import datetime
import streamlit.components.v1 as components
from google.cloud import firestore
from google.oauth2 import service_account

# ==========================================
# CONFIGURATION ET CONSTANTES
# ==========================================
st.set_page_config(
    page_title="L’IA bureautique NoVA AI", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

ADMIN_CODE = "02110240"
WHATSAPP_NUMBER = "2250171542505"
PREMIUM_MSG = "J'aimerais passer à la version Nova Premium pour bénéficier de la puissance 10^10 et de l'IA de pointe."
SUPPORT_MSG = "Bonjour, j'ai besoin d'assistance sur mon espace Nova AI."

whatsapp_premium_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={PREMIUM_MSG.replace(' ', '%20')}"
whatsapp_support_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={SUPPORT_MSG.replace(' ', '%20')}"

# ==========================================
# PERSISTENCE AVEC FIRESTORE (Remplace JSON)
# ==========================================

@st.cache_resource
def get_db_client():
    """Initialise la connexion à Firestore via les Secrets Streamlit"""
    try:
        # Tente de charger les credentials depuis les secrets (pour déploiement Cloud)
        key_dict = json.loads(st.secrets["textkey"])
        creds = service_account.Credentials.from_service_account_info(key_dict)
        return firestore.Client(credentials=creds, project="nova-ai-app")
    except Exception:
        # Fallback local pour développement (nécessite un fichier service_account.json si hors cloud)
        st.warning("⚠️ Mode local : Assurez-vous d'avoir configuré les secrets Firestore.")
        return None

db_client = get_db_client()

def load_nova_data():
    """Charge les données depuis Firestore"""
    data = {"users": {}, "demandes": [], "liens": {}}
    if db_client:
        try:
            # Charger Utilisateurs
            users_ref = db_client.collection("nova_users").stream()
            for doc in users_ref:
                data["users"][doc.id] = doc.to_dict()
            
            # Charger Demandes
            demandes_ref = db_client.collection("nova_demandes").stream()
            for doc in demandes_ref:
                data["demandes"].append(doc.to_dict())
                
            # Charger Liens
            liens_ref = db_client.collection("nova_liens").stream()
            for doc in liens_ref:
                data["liens"][doc.id] = doc.to_dict().get("items", [])
        except Exception as e:
            st.error(f"Erreur de lecture Cloud: {e}")
    return data

def save_user_to_cloud(uid, user_data):
    if db_client:
        db_client.collection("nova_users").document(uid).set(user_data)

def save_demande_to_cloud(req_data):
    if db_client:
        db_client.collection("nova_demandes").document(req_data["id"]).set(req_data)

def save_link_to_cloud(uid, links_list):
    if db_client:
        db_client.collection("nova_liens").document(uid).set({"items": links_list})

def delete_demande_cloud(req_id):
    if db_client:
        db_client.collection("nova_demandes").document(req_id).delete()

# Initialisation Session State
if "db_data" not in st.session_state:
    st.session_state["db_data"] = load_nova_data()

if "current_user" not in st.session_state:
    st.session_state["current_user"] = None

if "view" not in st.session_state:
    st.session_state["view"] = "home"

if "is_glowing" not in st.session_state:
    st.session_state["is_glowing"] = False

# Reconnaissance automatique
if st.session_state["current_user"] is None:
    stored_user = st.query_params.get("user_id")
    if stored_user and stored_user in st.session_state["db_data"]["users"]:
        st.session_state["current_user"] = stored_user

# ==========================================
# DESIGN ET STYLE (CSS)
# ==========================================

def inject_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { font-family: 'Poppins', sans-serif; }
        .stApp {
            background: #0f0c29;
            background: linear-gradient(to right, #24243e, #302b63, #0f0c29);
            color: #ffffff;
        }
        @keyframes glow-pulse {
            0% { filter: brightness(1); }
            50% { filter: brightness(1.5); box-shadow: inset 0 0 50px rgba(0, 210, 255, 0.2); }
            100% { filter: brightness(1); }
        }
        .main-title {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800; font-size: 3rem !important;
            text-align: center; margin-bottom: 20px;
        }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; background-color: rgba(255, 255, 255, 0.05); padding: 5px; border-radius: 15px; }
        .stTabs [data-baseweb="tab"] { color: white !important; font-weight: 700 !important; }
        .stTextArea textarea { border: 2px solid #00d2ff !important; background: rgba(0,0,0,0.5) !important; color: white !important; }
        .premium-card {
            background: rgba(20, 20, 30, 0.8); border: 2px solid #FFD700;
            border-radius: 20px; padding: 20px; text-align: center; margin-bottom: 20px;
        }
        .btn-gold {
            background: linear-gradient(45deg, #FFD700, #FF8C00); color: black !important;
            padding: 10px 25px; border-radius: 50px; font-weight: 800; text-decoration: none; display: inline-block;
        }
        .file-card {
            background: rgba(255, 255, 255, 0.08); border-radius: 15px; padding: 15px; margin-bottom: 10px; border: 1px solid #2ecc71;
        }
        .support-btn {
            display: block; text-decoration: none; border: 2px solid #25D366; color: #25D366 !important;
            padding: 8px; border-radius: 10px; font-weight: bold; text-align: center; margin-top: 10px;
        }
        </style>
    """, unsafe_allow_html=True)
    if st.session_state["is_glowing"]:
        st.markdown('<style>.stApp { animation: glow-pulse 1.5s ease-in-out infinite; }</style>', unsafe_allow_html=True)

# ==========================================
# PAGES
# ==========================================

def show_auth_page():
    st.markdown("<h1 class='main-title'>ESPACE NOVA AI</h1>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔐 Accès Membre")
        with st.form("login"):
            uid = st.text_input("Identifiant Nova")
            wa_auth = st.text_input("Numéro WhatsApp")
            if st.form_submit_button("S'IDENTIFIER"):
                db = st.session_state["db_data"]
                if uid in db["users"] and db["users"][uid]["whatsapp"] == wa_auth:
                    st.session_state["current_user"] = uid
                    st.query_params["user_id"] = uid
                    st.rerun()
                else:
                    st.error("❌ Identifiant ou numéro inconnu.")

    with col2:
        st.subheader("✨ Nouveau Compte")
        with st.form("signup"):
            new_uid = st.text_input("Identifiant au choix")
            new_wa = st.text_input("Votre WhatsApp")
            if st.form_submit_button("REJOINDRE NOVA AI"):
                if new_uid and new_wa:
                    db = st.session_state["db_data"]
                    if new_uid not in db["users"]:
                        user_obj = {
                            "whatsapp": new_wa,
                            "joined": str(datetime.now())
                        }
                        save_user_to_cloud(new_uid, user_obj)
                        st.session_state["db_data"] = load_nova_data()
                        st.session_state["current_user"] = new_uid
                        st.query_params["user_id"] = new_uid
                        st.rerun()
                    else:
                        st.warning("⚠️ Identifiant déjà utilisé.")

def main_dashboard():
    user = st.session_state["current_user"]
    db = st.session_state["db_data"]
    
    with st.sidebar:
        st.markdown(f"### 👤 {user if user else 'Visiteur'}")
        if user:
            st.markdown(f"📱 **{db['users'].get(user, {}).get('whatsapp', '')}**")
            if st.button("Quitter la session"):
                st.session_state["current_user"] = None
                st.query_params.clear()
                st.rerun()
        else:
            if st.button("Connexion"):
                st.session_state["view"] = "auth"
                st.rerun()
        
        st.divider()
        st.markdown('<a href="' + whatsapp_support_url + '" target="_blank" class="support-btn">💬 Support Nova</a>', unsafe_allow_html=True)

    st.markdown("<h1 class='main-title'>NOVA AI PLATFORM</h1>", unsafe_allow_html=True)

    st.markdown(f"""
        <div class="premium-card">
            <div style="color:#FFD700; font-weight:800;">⭐ ACCÉLÉRATEUR NOVA PREMIUM ⭐</div>
            <p>IA illimitée et puissance de calcul <b>10<sup>10</sup></b>.</p>
            <a href="{whatsapp_premium_url}" target="_blank" class="btn-gold">💎 ACTIVER PREMIUM</a>
        </div>
    """, unsafe_allow_html=True)

    tab1, tab2 = st.tabs(["🚀 DÉPLOYER TÂCHE", "📂 MES LIVRABLES (CLOUD)"])

    with tab1:
        col_f, col_wa = st.columns(2)
        with col_f:
            service = st.selectbox("Type d'intervention", ["📊 Data & Excel Analytics", "📝 Exposé scolaire", "⚙️ Pack Office", "🎨 Design IA"])
        with col_wa:
            default_wa = db["users"].get(user, {}).get("whatsapp", "") if user else ""
            wa_display = st.text_input("WhatsApp de contact", value=default_wa)
        
        prompt = st.text_area("Cahier des charges Nova", height=100)
        
        if st.button("ACTIVER L'ALGORITHME NOVA"):
            if prompt and wa_display:
                st.session_state["is_glowing"] = True
                
                # Simulation de calcul
                bar = st.progress(0)
                for i in range(100):
                    time.sleep(0.01)
                    bar.progress(i + 1)
                
                new_req = {
                    "id": hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8],
                    "user": user if user else "guest",
                    "service": service,
                    "desc": prompt,
                    "whatsapp": wa_display,
                    "status": "Traitement Nova en cours...",
                    "timestamp": str(datetime.now())
                }
                save_demande_to_cloud(new_req)
                st.session_state["db_data"] = load_nova_data() # Refresh
                st.session_state["is_glowing"] = False
                st.success("✅ Mission enregistrée dans le Cloud !")
                st.rerun()

    with tab2:
        if not user:
            st.warning("🔒 Connectez-vous pour voir vos fichiers.")
        else:
            user_links = db["liens"].get(user, [])
            user_reqs = [r for r in db["demandes"] if r["user"] == user]
            
            st.markdown("### 📥 HUB DE TÉLÉCHARGEMENT")
            
            if user_links:
                for link in user_links:
                    st.markdown(f"""
                    <div class="file-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h4 style="margin:0; color:#00d2ff;">💎 {link['name']}</h4>
                                <small>Livre le {link.get('date', '')}</small>
                            </div>
                            <a href="{link['url']}" target="_blank" class="btn-gold" style="padding:5px 15px; font-size:0.8rem;">TÉLÉCHARGER</a>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            if user_reqs:
                st.markdown("#### ⏳ En cours...")
                for r in user_reqs:
                    st.info(f"⚙️ {r['service']} : {r['status']}")

    # --- ADMIN CONSOLE ---
    with st.expander("🛠 Console Admin"):
        if st.text_input("Master Key", type="password") == ADMIN_CODE:
            current_db = st.session_state["db_data"]
            for i, req in enumerate(current_db["demandes"]):
                st.write(f"📦 **{req['user']}** - {req['service']}")
                url_dl = st.text_input(f"Lien pour {req['id']}", key=f"adm_url_{i}")
                if st.button(f"LIVRER", key=f"adm_btn_{i}"):
                    links = current_db["liens"].get(req['user'], [])
                    links.append({
                        "name": req['service'], 
                        "url": url_dl,
                        "date": datetime.now().strftime("%d/%m/%Y")
                    })
                    save_link_to_cloud(req['user'], links)
                    delete_demande_cloud(req['id'])
                    st.session_state["db_data"] = load_nova_data()
                    st.rerun()

# ==========================================
# EXECUTION
# ==========================================

inject_custom_css()

# Script de persistance navigateur
components.html(f"""
    <script>
    const user = localStorage.getItem('nova_user');
    const urlParams = new URLSearchParams(window.parent.location.search);
    const currentUser = urlParams.get('user_id');
    
    if (user && !currentUser && !window.parent.location.href.includes('logout')) {{
        window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + '?user_id=' + user;
    }}
    if (currentUser) {{
        localStorage.setItem('nova_user', currentUser);
    }}
    </script>
""", height=0)

if st.session_state["view"] == "auth" and st.session_state["current_user"] is None:
    show_auth_page()
else:
    main_dashboard()
