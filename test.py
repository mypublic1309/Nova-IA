import streamlit as st
import json
import os
import bcrypt
import time
from datetime import datetime
import streamlit.components.v1 as components

# ==========================================
# CONFIGURATION ET CONSTANTES
# ==========================================
st.set_page_config(
    page_title="L'IA bureautique NoVA AI", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_FILE = "data_nova_v3.json"
# Hash par défaut pour le code admin (exemple: "02110240")
ADMIN_CODE_HASH = bcrypt.hashpw(b"02110240", bcrypt.gensalt()).decode()

WHATSAPP_NUMBER = "2250171542505"
PREMIUM_MSG = "J'aimerais passer à la version Nova Premium pour bénéficier de la puissance 10^10 et de l'IA de pointe."
SUPPORT_MSG = "Bonjour, j'ai besoin d'assistance sur mon espace Nova AI."

whatsapp_premium_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={PREMIUM_MSG.replace(' ', '%20')}"
whatsapp_support_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={SUPPORT_MSG.replace(' ', '%20')}"


# ==========================================
# UTILITAIRES DE SÉCURITÉ
# ==========================================

def hash_password(plain_password: str) -> str:
    return bcrypt.hashpw(plain_password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain_password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def verify_admin_code(input_code: str) -> bool:
    try:
        return bcrypt.checkpw(input_code.encode("utf-8"), ADMIN_CODE_HASH.encode("utf-8"))
    except Exception:
        return False


# ==========================================
# LOGIQUE DE DONNÉES
# ==========================================

def load_db():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"users": {}, "demandes": [], "liens": {}}
    return {"users": {}, "demandes": [], "liens": {}}

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

if "db" not in st.session_state:
    st.session_state["db"] = load_db()
if "current_user" not in st.session_state:
    st.session_state["current_user"] = None
if "view" not in st.session_state:
    st.session_state["view"] = "auth"  # Default to auth
if "is_glowing" not in st.session_state:
    st.session_state["is_glowing"] = False
if "auth_tab" not in st.session_state:
    st.session_state["auth_tab"] = "login"

# Récupération de l'utilisateur depuis l'URL si présent (persistance simple)
if st.session_state["current_user"] is None:
    stored_user = st.query_params.get("user_id")
    if stored_user and stored_user in st.session_state["db"]["users"]:
        st.session_state["current_user"] = stored_user
        st.session_state["view"] = "home"


# ==========================================
# CSS GLOBAL + PAGE AUTH
# ==========================================

def inject_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=JetBrains+Mono:wght@300;400;600&display=swap');
        
        * { font-family: 'Syne', sans-serif; box-sizing: border-box; }
        code, input { font-family: 'JetBrains Mono', monospace !important; }

        .stApp {
            background: #05050f;
            color: #ffffff;
        }

        /* === PAGE AUTH CUSTOM === */
        .auth-wrapper {
            min-height: 85vh;
            display: flex;
            align-items: center;
            justify-content: center;
            position: relative;
            overflow: hidden;
            padding: 40px 0;
        }

        /* Grille de fond animée */
        .auth-grid-bg {
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background-image:
                linear-gradient(rgba(0, 210, 255, 0.04) 1px, transparent 1px),
                linear-gradient(90deg, rgba(0, 210, 255, 0.04) 1px, transparent 1px);
            background-size: 50px 50px;
            animation: gridShift 20s linear infinite;
            pointer-events: none;
            z-index: 0;
        }

        @keyframes gridShift {
            0% { transform: translateY(0); }
            100% { transform: translateY(50px); }
        }

        /* Orbes lumineux */
        .auth-orb-1 {
            position: fixed;
            width: 500px; height: 500px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(0, 140, 255, 0.12) 0%, transparent 70%);
            top: -100px; left: -100px;
            animation: orbFloat1 8s ease-in-out infinite;
            pointer-events: none;
            z-index: 0;
        }
        .auth-orb-2 {
            position: fixed;
            width: 400px; height: 400px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(120, 0, 255, 0.1) 0%, transparent 70%);
            bottom: -50px; right: -50px;
            animation: orbFloat2 10s ease-in-out infinite;
            pointer-events: none;
            z-index: 0;
        }
        .auth-orb-3 {
            position: fixed;
            width: 300px; height: 300px;
            border-radius: 50%;
            background: radial-gradient(circle, rgba(0, 255, 200, 0.06) 0%, transparent 70%);
            top: 50%; right: 20%;
            animation: orbFloat1 12s ease-in-out infinite reverse;
            pointer-events: none;
            z-index: 0;
        }

        @keyframes orbFloat1 {
            0%, 100% { transform: translate(0, 0); }
            50% { transform: translate(30px, 30px); }
        }
        @keyframes orbFloat2 {
            0%, 100% { transform: translate(0, 0); }
            50% { transform: translate(-20px, -25px); }
        }

        /* Logo Nova (auth) */
        .nova-logo-auth {
            text-align: center;
            margin-bottom: 40px;
            position: relative;
            z-index: 2;
        }
        .nova-logo-auth .logo-symbol {
            font-size: 3.5rem;
            display: block;
            filter: drop-shadow(0 0 20px rgba(0, 210, 255, 0.6));
            animation: logoPulse 3s ease-in-out infinite;
        }
        .nova-logo-auth .logo-name {
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #00d2ff 0%, #ffffff 50%, #3a7bd5 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            letter-spacing: 6px;
            text-transform: uppercase;
            display: block;
            line-height: 1;
        }
        .nova-logo-auth .logo-tagline {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.7rem;
            color: rgba(0, 210, 255, 0.5);
            letter-spacing: 4px;
            text-transform: uppercase;
            margin-top: 6px;
            display: block;
        }

        @keyframes logoPulse {
            0%, 100% { filter: drop-shadow(0 0 15px rgba(0, 210, 255, 0.5)); }
            50% { filter: drop-shadow(0 0 35px rgba(0, 210, 255, 0.9)); }
        }

        /* Conteneur principal auth */
        .auth-card-container {
            position: relative;
            z-index: 2;
            width: 100%;
            max-width: 900px;
            margin: 0 auto;
        }

        /* Switcher d'onglets custom */
        .auth-switcher {
            display: flex;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(0, 210, 255, 0.15);
            border-radius: 16px;
            padding: 5px;
            margin-bottom: 30px;
            gap: 5px;
        }
        .auth-tab-btn {
            flex: 1;
            padding: 14px;
            text-align: center;
            border-radius: 12px;
            cursor: pointer;
            font-weight: 700;
            font-size: 0.95rem;
            letter-spacing: 1px;
            text-transform: uppercase;
            transition: all 0.3s ease;
            color: rgba(255,255,255,0.4);
            border: none;
            background: transparent;
        }
        .auth-tab-btn.active {
            background: linear-gradient(135deg, rgba(0,210,255,0.15), rgba(58,123,213,0.2));
            color: #00d2ff;
            border: 1px solid rgba(0, 210, 255, 0.3);
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.1), inset 0 0 20px rgba(0, 210, 255, 0.05);
        }

        /* Panneau de formulaire */
        .auth-panel {
            background: rgba(10, 10, 25, 0.8);
            border: 1px solid rgba(0, 210, 255, 0.12);
            border-radius: 24px;
            padding: 45px 50px;
            backdrop-filter: blur(20px);
            -webkit-backdrop-filter: blur(20px);
            box-shadow:
                0 0 0 1px rgba(0, 210, 255, 0.05),
                0 30px 80px rgba(0, 0, 0, 0.6),
                inset 0 1px 0 rgba(255,255,255,0.05);
            position: relative;
            overflow: hidden;
        }

        .auth-panel::before {
            content: '';
            position: absolute;
            top: 0; left: 10%; right: 10%;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(0, 210, 255, 0.4), transparent);
        }

        /* Titre du panel */
        .auth-panel-title {
            font-size: 1.5rem;
            font-weight: 800;
            color: white;
            margin-bottom: 6px;
        }
        .auth-panel-sub {
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.75rem;
            color: rgba(0, 210, 255, 0.5);
            margin-bottom: 35px;
            letter-spacing: 1px;
        }

        /* Badge de statut */
        .status-badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(46, 204, 113, 0.1);
            border: 1px solid rgba(46, 204, 113, 0.3);
            border-radius: 50px;
            padding: 4px 12px;
            font-size: 0.7rem;
            color: #2ecc71;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 1px;
            margin-bottom: 30px;
        }
        .status-dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: #2ecc71;
            animation: statusBlink 1.5s ease-in-out infinite;
        }
        @keyframes statusBlink {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }

        /* Séparateur vertical */
        .auth-divider-v {
            width: 1px;
            background: linear-gradient(to bottom, transparent, rgba(0, 210, 255, 0.2), transparent);
            margin: 0 30px;
            align-self: stretch;
        }

        /* Avantages (colonne droite) */
        .auth-benefits {
            padding: 10px 0;
        }
        .benefit-item {
            display: flex;
            align-items: flex-start;
            gap: 14px;
            margin-bottom: 22px;
            opacity: 0;
            animation: fadeSlideIn 0.5s ease forwards;
        }
        .benefit-item:nth-child(1) { animation-delay: 0.1s; }
        .benefit-item:nth-child(2) { animation-delay: 0.2s; }
        .benefit-item:nth-child(3) { animation-delay: 0.3s; }
        .benefit-item:nth-child(4) { animation-delay: 0.4s; }

        @keyframes fadeSlideIn {
            from { opacity: 0; transform: translateX(15px); }
            to { opacity: 1; transform: translateX(0); }
        }

        .benefit-icon {
            width: 40px; height: 40px;
            border-radius: 10px;
            background: rgba(0, 210, 255, 0.08);
            border: 1px solid rgba(0, 210, 255, 0.15);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.1rem;
            flex-shrink: 0;
        }
        .benefit-text strong {
            display: block;
            color: white;
            font-size: 0.9rem;
            font-weight: 700;
            margin-bottom: 2px;
        }
        .benefit-text span {
            color: rgba(255,255,255,0.4);
            font-size: 0.78rem;
            line-height: 1.4;
        }

        /* Ligne décorative "stats" */
        .auth-stats-row {
            display: flex;
            gap: 20px;
            margin-top: 35px;
            padding-top: 25px;
            border-top: 1px solid rgba(255,255,255,0.05);
        }
        .auth-stat {
            flex: 1;
            text-align: center;
        }
        .auth-stat-val {
            font-size: 1.4rem;
            font-weight: 800;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            display: block;
        }
        .auth-stat-label {
            font-size: 0.65rem;
            color: rgba(255,255,255,0.3);
            text-transform: uppercase;
            letter-spacing: 1px;
            font-family: 'JetBrains Mono', monospace;
        }

        /* === CHAMPS STREAMLIT CUSTOMISÉS === */
        .stTextInput label {
            color: rgba(0, 210, 255, 0.7) !important;
            font-weight: 600 !important;
            font-size: 0.78rem !important;
            letter-spacing: 1.5px !important;
            text-transform: uppercase !important;
            margin-bottom: 6px !important;
            font-family: 'JetBrains Mono', monospace !important;
        }
        div[data-baseweb="input"] {
            border: 1px solid rgba(0, 210, 255, 0.2) !important;
            background-color: rgba(0, 10, 30, 0.6) !important;
            border-radius: 12px !important;
            transition: all 0.3s !important;
        }
        div[data-baseweb="input"]:focus-within {
            border-color: rgba(0, 210, 255, 0.6) !important;
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.1) !important;
        }
        div[data-baseweb="input"] input {
            color: white !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 0.9rem !important;
        }

        /* Bouton submit auth */
        .stForm .stButton > button {
            background: linear-gradient(135deg, #00d2ff, #3a7bd5) !important;
            border: none !important;
            border-radius: 14px !important;
            padding: 14px !important;
            font-weight: 700 !important;
            font-size: 0.9rem !important;
            letter-spacing: 2px !important;
            text-transform: uppercase !important;
            width: 100% !important;
            transition: all 0.3s !important;
            box-shadow: 0 4px 25px rgba(0, 210, 255, 0.25) !important;
            margin-top: 15px !important;
        }
        .stForm .stButton > button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 8px 35px rgba(0, 210, 255, 0.4) !important;
        }

        /* Message d'erreur/succès */
        .stAlert {
            border-radius: 12px !important;
            border: none !important;
            font-family: 'JetBrains Mono', monospace !important;
            font-size: 0.8rem !important;
        }

        /* === DASHBOARD === */
        .stApp {
            background: #05050f;
        }
        .main-title {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 3.5rem !important;
            text-align: center;
            margin-bottom: 20px;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
            background-color: rgba(255, 255, 255, 0.05);
            padding: 10px;
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        .stTabs [data-baseweb="tab"] {
            height: 60px;
            background-color: rgba(0, 210, 255, 0.1);
            border-radius: 10px;
            color: white !important;
            font-weight: 700 !important;
            font-size: 1.1rem !important;
            transition: all 0.3s ease;
            border: 1px solid transparent;
            padding: 0 25px;
        }
        .stTabs [data-baseweb="tab"]:nth-child(2) {
            border: 1px solid #2ecc71 !important;
            background-color: rgba(46, 204, 113, 0.1);
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(0, 210, 255, 0.6) !important;
            border: 1px solid #00d2ff !important;
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.4);
        }
        @keyframes border-rainbow {
            0% { border-color: #00d2ff; }
            25% { border-color: #3a7bd5; }
            50% { border-color: #FFD700; }
            75% { border-color: #2ecc71; }
            100% { border-color: #00d2ff; }
        }
        .stTextArea label { color: #00d2ff !important; font-weight: 600 !important; font-size: 1.1rem !important; }
        .stSelectbox label { color: #00d2ff !important; font-weight: 600 !important; font-size: 1.1rem !important; }
        div[data-baseweb="select"] > div {
            border: 1px solid rgba(0, 210, 255, 0.3) !important;
            background-color: rgba(0, 0, 0, 0.5) !important;
            color: white !important;
            border-radius: 10px !important;
        }
        .stTextArea textarea {
            background-color: rgba(0, 0, 0, 0.6) !important;
            color: white !important;
            border-radius: 10px !important;
            border: 2px solid #00d2ff !important;
            animation: border-rainbow 4s linear infinite;
        }
        @keyframes glow-pulse {
            0% { filter: brightness(1); }
            50% { filter: brightness(1.8) saturate(1.5); }
            100% { filter: brightness(1); }
        }
        .premium-card {
            background: rgba(20, 20, 30, 0.8);
            border: 2px solid #FFD700;
            border-radius: 20px;
            padding: 25px;
            text-align: center;
            margin-bottom: 30px;
            box-shadow: 0 0 30px rgba(255, 215, 0, 0.2);
            position: relative;
            overflow: hidden;
        }
        .premium-card::before {
            content: "";
            position: absolute;
            top: 0; left: 0; width: 100%; height: 5px;
            background: linear-gradient(90deg, #FFD700, #FF8C00, #FFD700);
        }
        .premium-title { color: #FFD700 !important; font-size: 1.5rem; font-weight: 800; text-transform: uppercase; margin-bottom: 10px; letter-spacing: 1px; }
        .premium-desc { color: #ffffff !important; font-size: 1rem; margin-bottom: 20px; line-height: 1.5; }
        .btn-gold {
            background: linear-gradient(45deg, #FFD700, #FF8C00);
            color: #000 !important;
            padding: 12px 30px;
            border-radius: 50px;
            text-decoration: none;
            font-weight: 800;
            font-size: 1.1rem;
            display: inline-block;
            box-shadow: 0 5px 15px rgba(255, 215, 0, 0.4);
            transition: transform 0.2s;
        }
        .btn-gold:hover { transform: scale(1.05); }
        .stButton>button {
            border-radius: 12px;
            padding: 0.8rem 2rem;
            background: linear-gradient(90deg, #00d2ff 0%, #3a7bd5 100%);
            border: none;
            color: white !important;
            font-weight: 700;
            font-size: 1.1rem;
            width: 100%;
            margin-top: 10px;
            box-shadow: 0 4px 10px rgba(0, 210, 255, 0.3);
            transition: 0.3s;
        }
        .stButton>button:hover { transform: translateY(-2px); box-shadow: 0 6px 20px rgba(0, 210, 255, 0.5); }
        .info-card { background: rgba(0, 0, 0, 0.4) !important; border-left: 4px solid #00d2ff; padding: 15px; border-radius: 0 10px 10px 0; margin-bottom: 15px; }
        .info-title { color: #00d2ff !important; font-weight: bold; font-size: 1.1rem; display: block; margin-bottom: 8px; text-transform: uppercase; }
        .file-card {
            background: rgba(255, 255, 255, 0.08);
            border: 2px solid rgba(46, 204, 113, 0.5);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
            animation: slideIn 0.5s ease;
        }
        @keyframes slideIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }
        .support-btn {
            display: block;
            text-decoration: none;
            background: transparent;
            border: 2px solid #25D366;
            color: #25D366 !important;
            padding: 10px;
            border-radius: 10px;
            font-weight: bold;
            text-align: center;
            margin-top: 10px;
            transition: 0.3s;
        }
        .support-btn:hover { background: #25D366; color: white !important; }
        .logo-container {
            display: flex; justify-content: center; align-items: center;
            gap: 30px; margin-top: 20px; padding: 15px;
            background: rgba(255, 255, 255, 0.03); border-radius: 15px;
        }
        .logo-item { width: 45px; height: 45px; filter: grayscale(0.5) opacity(0.7); transition: all 0.3s ease; }
        .logo-item:hover { filter: grayscale(0) opacity(1); transform: translateY(-5px) scale(1.1); }
        .stProgress > div > div > div > div { background-image: linear-gradient(to right, #00d2ff, #3a7bd5); }
        </style>
    """, unsafe_allow_html=True)
    
    if st.session_state["is_glowing"]:
        st.markdown('<style>.stApp { animation: glow-pulse 1.5s ease-in-out infinite; }</style>', unsafe_allow_html=True)


# ==========================================
# PAGE AUTHENTIFICATION REDESIGNÉE
# ==========================================

def show_auth_page():
    # Fond animé
    st.markdown("""
        <div class="auth-grid-bg"></div>
        <div class="auth-orb-1"></div>
        <div class="auth-orb-2"></div>
        <div class="auth-orb-3"></div>
    """, unsafe_allow_html=True)

    # Logo central
    st.markdown("""
        <div class="nova-logo-auth">
            <span class="logo-symbol">⚡</span>
            <span class="logo-name">NOVA AI</span>
            <span class="logo-tagline">Bureautique Intelligente · Powered by AI</span>
        </div>
    """, unsafe_allow_html=True)

    # Disposition 2 colonnes : formulaire | avantages
    col_form, col_sep, col_info = st.columns([5, 0.1, 4])

    with col_form:
        st.markdown('<div class="auth-panel">', unsafe_allow_html=True)
        
        # Switcher login / signup
        tab_col1, tab_col2 = st.columns(2)
        with tab_col1:
            if st.button("🔐  Connexion", key="switch_login", use_container_width=True):
                st.session_state["auth_tab"] = "login"
                st.rerun()
        with tab_col2:
            if st.button("✨  Créer un compte", key="switch_signup", use_container_width=True):
                st.session_state["auth_tab"] = "signup"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)

        # Badge en ligne
        st.markdown("""
            <div class="status-badge">
                <div class="status-dot"></div>
                SYSTÈME OPÉRATIONNEL · NOVA v3.0
            </div>
        """, unsafe_allow_html=True)

        # Formulaire LOGIN
        if st.session_state["auth_tab"] == "login":
            st.markdown('<div class="auth-panel-title">Bon retour 👋</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-panel-sub">// Authentifiez-vous pour accéder à votre espace</div>', unsafe_allow_html=True)

            with st.form("login_form"):
                uid = st.text_input("Identifiant Nova", placeholder="ex: john_nova")
                wa_auth = st.text_input("Numéro WhatsApp", placeholder="ex: 22501XXXXXXX", type="password")

                submitted = st.form_submit_button("→  S'IDENTIFIER")
                if submitted:
                    db = st.session_state["db"]
                    if uid in db["users"]:
                        stored = db["users"][uid]["whatsapp"]
                        is_valid = False
                        if stored.startswith("$2b$") or stored.startswith("$2a$"):
                            is_valid = verify_password(wa_auth, stored)
                        else:
                            is_valid = (stored == wa_auth)
                            if is_valid:
                                db["users"][uid]["whatsapp"] = hash_password(wa_auth)
                                save_db(db)
                        if is_valid:
                            st.session_state["current_user"] = uid
                            st.session_state["view"] = "home"
                            st.query_params["user_id"] = uid
                            st.rerun()
                        else:
                            st.error("❌ Identifiant ou numéro incorrect.")
                    else:
                        st.error("❌ Identifiant introuvable.")

            st.markdown("""
                <div style="text-align:center; margin-top:20px; font-size:0.78rem; color:rgba(255,255,255,0.25); font-family:'JetBrains Mono',monospace;">
                    Pas encore de compte ? Créez-en un en quelques secondes →
                </div>
            """, unsafe_allow_html=True)

        # Formulaire SIGNUP
        else:
            st.markdown('<div class="auth-panel-title">Rejoignez Nova ⚡</div>', unsafe_allow_html=True)
            st.markdown('<div class="auth-panel-sub">// Créez votre espace en quelques secondes</div>', unsafe_allow_html=True)

            with st.form("signup_form"):
                new_uid = st.text_input("Choisissez un identifiant", placeholder="ex: marie_nova")
                new_wa = st.text_input("Numéro WhatsApp (clé d'accès)", placeholder="ex: 22501XXXXXXX", type="password")

                submitted = st.form_submit_button("→  CRÉER MON ESPACE")
                if submitted:
                    if new_uid and new_wa:
                        db = st.session_state["db"]
                        if new_uid not in db["users"]:
                            db["users"][new_uid] = {
                                "whatsapp": hash_password(new_wa),
                                "email": "Non renseigné",
                                "joined": str(datetime.now())
                            }
                            st.session_state["current_user"] = new_uid
                            st.session_state["view"] = "home"
                            save_db(db)
                            st.query_params["user_id"] = new_uid
                            st.rerun()
                        else:
                            st.warning("⚠️ Identifiant déjà utilisé. Choisissez-en un autre.")
                    else:
                        st.error("Tous les champs sont obligatoires.")

            st.markdown("""
                <div style="text-align:center; margin-top:20px; font-size:0.78rem; color:rgba(255,255,255,0.25); font-family:'JetBrains Mono',monospace;">
                    🔒 Votre numéro est chiffré et jamais partagé.
                </div>
            """, unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)  # close auth-panel

    # Séparateur vertical (simulé)
    with col_sep:
        st.markdown("""
            <div style="width:1px; min-height:500px; background: linear-gradient(to bottom, transparent, rgba(0,210,255,0.2), transparent); margin:0 auto;"></div>
        """, unsafe_allow_html=True)

    # Colonne avantages
    with col_info:
        st.markdown("""
            <div style="padding-top: 20px;">
                <div style="font-family:'JetBrains Mono',monospace; font-size:0.7rem; color:rgba(0,210,255,0.5); letter-spacing:3px; text-transform:uppercase; margin-bottom:25px;">
                    // Pourquoi Nova AI ?
                </div>

                <div class="benefit-item">
                    <div class="benefit-icon">📊</div>
                    <div class="benefit-text">
                        <strong>Data & Analytics</strong>
                        <span>Tableaux Excel, dashboards et rapports générés par IA en quelques minutes.</span>
                    </div>
                </div>

                <div class="benefit-item">
                    <div class="benefit-icon">⚡</div>
                    <div class="benefit-text">
                        <strong>Livraison Ultra-Rapide</strong>
                        <span>Vos livrables sont prêts et téléchargeables directement depuis votre espace.</span>
                    </div>
                </div>

                <div class="benefit-item">
                    <div class="benefit-icon">🎨</div>
                    <div class="benefit-text">
                        <strong>Design & Documents</strong>
                        <span>CV, affiches, présentations PowerPoint et bien plus.</span>
                    </div>
                </div>

                <div class="benefit-item">
                    <div class="benefit-icon">🔒</div>
                    <div class="benefit-text">
                        <strong>Sécurité Maximale</strong>
                        <span>Accès chiffré, données protégées. Votre espace est privé.</span>
                    </div>
                </div>

                <div class="auth-stats-row">
                    <div class="auth-stat">
                        <span class="auth-stat-val">10¹⁰</span>
                        <span class="auth-stat-label">Puissance</span>
                    </div>
                    <div class="auth-stat">
                        <span class="auth-stat-val">24/7</span>
                        <span class="auth-stat-label">Disponible</span>
                    </div>
                    <div class="auth-stat">
                        <span class="auth-stat-val">∞</span>
                        <span class="auth-stat-label">Possibilités</span>
                    </div>
                </div>
            </div>
        """, unsafe_allow_html=True)

    # Lien support discret en bas
    st.markdown(f"""
        <div style="text-align:center; margin-top:40px; padding-top:20px; border-top:1px solid rgba(255,255,255,0.05);">
            <span style="font-size:0.75rem; color:rgba(255,255,255,0.2); font-family:'JetBrains Mono',monospace;">
                Besoin d'aide ? 
            </span>
            <a href="{whatsapp_support_url}" target="_blank" style="font-size:0.75rem; color:rgba(0,210,255,0.5); text-decoration:none; margin-left:8px;">
                Contacter le support Nova →
            </a>
        </div>
    """, unsafe_allow_html=True)


# ==========================================
# DASHBOARD PRINCIPAL
# ==========================================

def main_dashboard():
    user = st.session_state["current_user"]
    db = st.session_state["db"]
    
    # === SIDEBAR ===
    with st.sidebar:
        st.markdown(f"### 👤 {user}")
        if user in db['users']:
            # Simuler un masquage de numéro pour l'affichage
            safe_num = "******"
            st.markdown(f"📱 **Compte Sécurisé**")
        
        if st.button("Déconnexion", use_container_width=True):
            st.session_state["current_user"] = None
            st.session_state["view"] = "auth"
            st.query_params.clear()
            st.rerun()
        
        st.divider()
        st.markdown(f"""
            <div class="info-card">
                <span class="info-title">🚀 LIVRAISON NOVA</span>
                <span style="color:#eee; font-size:0.9rem;">
                    Vos résultats IA apparaissent dans l'onglet <b>"📂 MES LIVRABLES"</b>.
                    <br><br>Suivi instantané 24h/24.
                </span>
            </div>
        """, unsafe_allow_html=True)
        
        st.markdown(f"""
            <a href="{whatsapp_support_url}" class="support-btn" target="_blank">
                📞 Contacter le Support
            </a>
        """, unsafe_allow_html=True)

        # Admin Access (Hidden in expander)
        with st.expander("Admin Access"):
            admin_code = st.text_input("Code Admin", type="password")
            if st.button("Accès Admin"):
                if verify_admin_code(admin_code):
                     st.session_state["is_admin"] = True
                     st.success("Mode Admin Activé")
                else:
                    st.error("Code incorrect")

    # === MAIN CONTENT ===
    st.markdown('<div class="main-title">ESPACE NOVA AI ⚡</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["⚡ NOUVELLE MISSION", "📂 MES LIVRABLES", "💎 PREMIUM 10¹⁰"])

    # --- TAB 1: NOUVELLE DEMANDE ---
    with tab1:
        st.markdown("### 🛠️ Configurer votre assistant IA")
        
        with st.form("nova_task_form"):
            col_type, col_deadline = st.columns([1, 1])
            with col_type:
                task_type = st.selectbox("Type de mission", 
                    ["📊 Analyse Excel & Data", "📝 Rédaction Word / Rapport", "🎨 Présentation PowerPoint", "🖼️ Création Visuelle / Affiche", "🔎 Recherche Approfondie", "💻 Autre"]
                )
            with col_deadline:
                deadline = st.date_input("Date limite souhaitée", datetime.now())

            description = st.text_area("Instructions détaillées pour l'IA", height=150, placeholder="Décrivez précisément ce que Nova doit réaliser pour vous...")
            
            uploaded_file = st.file_uploader("Fichier de contexte (Optionnel)", type=['pdf', 'docx', 'xlsx', 'txt', 'png', 'jpg'])
            
            submit_task = st.form_submit_button("🚀 LANCER LA MISSION NOVA")

            if submit_task:
                if description:
                    new_id = len(db["demandes"]) + 1
                    file_name = uploaded_file.name if uploaded_file else "Aucun"
                    
                    new_request = {
                        "id": new_id,
                        "user": user,
                        "type": task_type,
                        "desc": description,
                        "file": file_name,
                        "date": str(datetime.now().strftime("%Y-%m-%d %H:%M")),
                        "status": "En attente",
                        "deadline": str(deadline)
                    }
                    
                    db["demandes"].append(new_request)
                    save_db(db)
                    
                    st.success("✅ Mission transmise à l'IA Nova ! Traitement en cours...")
                    st.balloons()
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error("⚠️ Veuillez fournir des instructions pour l'IA.")

        # Affichage des logos outils
        st.markdown("""
            <div class="logo-container">
                <img src="https://upload.wikimedia.org/wikipedia/commons/3/34/Microsoft_Office_Excel_%282019%E2%80%93present%29.svg" class="logo-item" title="Excel">
                <img src="https://upload.wikimedia.org/wikipedia/commons/f/fd/Microsoft_Office_Word_%282019%E2%80%93present%29.svg" class="logo-item" title="Word">
                <img src="https://upload.wikimedia.org/wikipedia/commons/0/0d/Microsoft_Office_PowerPoint_%282019%E2%80%93present%29.svg" class="logo-item" title="PowerPoint">
                <img src="https://upload.wikimedia.org/wikipedia/commons/a/a7/React-icon.svg" class="logo-item" title="Code & Dev">
            </div>
        """, unsafe_allow_html=True)

    # --- TAB 2: MES LIVRABLES ---
    with tab2:
        st.markdown("### 📂 Vos dossiers traités")
        
        user_requests = [r for r in db["demandes"] if r["user"] == user]
        
        if not user_requests:
            st.info("Aucune mission en cours. Lancez votre première demande dans l'onglet 'Nouvelle Mission'.")
        else:
            # Trier par ID décroissant (plus récent en premier)
            for req in sorted(user_requests, key=lambda x: x['id'], reverse=True):
                status_color = "#f39c12" if req["status"] == "En attente" else "#2ecc71"
                status_icon = "⏳" if req["status"] == "En attente" else "✅"
                
                # Vérifier s'il y a un lien de téléchargement (dans db['liens'] ou directement dans la demande)
                download_link = db["liens"].get(str(req["id"]), None)
                
                with st.container():
                    st.markdown(f"""
                        <div class="file-card">
                            <div style="display:flex; justify-content:space-between; align-items:center;">
                                <h3 style="margin:0; color:#00d2ff;">Mission #{req['id']} : {req['type']}</h3>
                                <span style="background:{status_color}; padding:5px 10px; border-radius:5px; font-weight:bold; color:black;">
                                    {status_icon} {req['status']}
                                </span>
                            </div>
                            <p style="color:#aaa; font-size:0.9rem; margin-top:10px;">📅 {req['date']} | 📎 Fichier joint : {req['file']}</p>
                            <div style="background:rgba(0,0,0,0.3); padding:10px; border-radius:8px; margin-top:10px; font-family:'JetBrains Mono'; font-size:0.85rem; color:#ddd;">
                                {req['desc']}
                            </div>
                        </div>
                    """, unsafe_allow_html=True)
                    
                    if download_link:
                        st.markdown(f"""
                            <a href="{download_link}" target="_blank" style="text-decoration:none;">
                                <button style="background:linear-gradient(90deg, #2ecc71, #27ae60); color:white; border:none; padding:10px 20px; border-radius:8px; font-weight:bold; cursor:pointer; width:100%; margin-top:5px;">
                                    📥 TÉLÉCHARGER LE RÉSULTAT
                                </button>
                            </a>
                        """, unsafe_allow_html=True)
                    elif req["status"] == "Terminé":
                        st.info("Le traitement est terminé. Le lien de téléchargement apparaîtra ici sous peu.")

    # --- TAB 3: PREMIUM ---
    with tab3:
        st.markdown(f"""
            <div class="premium-card">
                <div class="premium-title">🚀 Passez à la vitesse Lumière</div>
                <div class="premium-desc">
                    La version gratuite de Nova est puissante, mais <b>Nova Premium</b> est sans limite.
                    <br><br>
                    ✅ <b>Priorité absolue</b> sur le traitement des dossiers<br>
                    ✅ <b>Fichiers volumineux</b> acceptés<br>
                    ✅ <b>Support dédié</b> par ingénieur IA<br>
                    ✅ <b>Mode Créatif Avancé</b> (DALL-E 3, GPT-4 Turbo)
                </div>
                <a href="{whatsapp_premium_url}" target="_blank" class
