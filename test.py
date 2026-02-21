import streamlit as st
import json
import os
import hashlib
import time
from datetime import datetime
import streamlit.components.v1 as components
from supabase import create_client

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
ADMIN_CODE = "02110240"

# --- CONNEXION SUPABASE ---
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- FONCTION NORMALISATION NUMÉRO WHATSAPP ---
def normalize_wa(numero):
    if not numero:
        return ""
    numero = numero.strip().replace(" ", "").replace("-", "").replace("+", "")
    if numero.startswith("0") and not numero.startswith("00"):
        numero = "225" + numero
    return numero

# --- FONCTIONS SUPABASE ---
def load_db():
    try:
        # Charger users
        users_rows = supabase.table("users").select("*").execute().data
        users = {r["uid"]: {"whatsapp": r["whatsapp"], "email": r["email"], "joined": r["joined"]} for r in users_rows}

        # Charger demandes
        demandes_rows = supabase.table("demandes").select("*").execute().data
        demandes = []
        for r in demandes_rows:
            demandes.append({
                "id": r["id"],
                "user": r["uid"],
                "service": r["service"],
                "desc": r["description"],
                "whatsapp": r["whatsapp"],
                "status": r["status"],
                "incomplet": r["incomplet"],
                "champs_manquants": json.loads(r["champs_manquants"]) if r["champs_manquants"] else [],
                "timestamp": r["timestamp"]
            })

        # Charger liens
        liens_rows = supabase.table("liens").select("*").execute().data
        liens = {}
        for r in liens_rows:
            if r["uid"] not in liens:
                liens[r["uid"]] = []
            liens[r["uid"]].append({"name": r["name"], "url": r["url"], "date": r["date"]})

        return {"users": users, "demandes": demandes, "liens": liens}
    except Exception as e:
        st.error(f"Erreur chargement Supabase : {e}")
        return {"users": {}, "demandes": [], "liens": {}}

def save_user(uid, whatsapp, email="Non renseigné"):
    try:
        supabase.table("users").upsert({
            "uid": uid, "whatsapp": whatsapp,
            "email": email, "joined": str(datetime.now())
        }).execute()
    except Exception as e:
        st.error(f"Erreur sauvegarde utilisateur : {e}")

def save_demande(req):
    try:
        supabase.table("demandes").upsert({
            "id": req["id"],
            "uid": req["user"],
            "service": req["service"],
            "description": req["desc"],
            "whatsapp": req["whatsapp"],
            "status": req["status"],
            "incomplet": req["incomplet"],
            "champs_manquants": json.dumps(req["champs_manquants"]),
            "timestamp": req["timestamp"]
        }).execute()
    except Exception as e:
        st.error(f"Erreur sauvegarde demande : {e}")

def delete_demande(req_id):
    try:
        supabase.table("demandes").delete().eq("id", req_id).execute()
    except Exception as e:
        st.error(f"Erreur suppression demande : {e}")

def save_lien(uid, name, url, date):
    try:
        supabase.table("liens").insert({
            "uid": uid, "name": name, "url": url, "date": date
        }).execute()
    except Exception as e:
        st.error(f"Erreur sauvegarde lien : {e}")

def save_db(data):
    # Compatibilité — non utilisée directement, remplacée par les fonctions spécifiques
    pass

# --- CONFIGURATION WHATSAPP ---
WHATSAPP_NUMBER = "2250171542505"
PREMIUM_MSG = "J'aimerais passer à la version Nova Premium pour bénéficier de la puissance 10^10 et de l'IA de pointe."
SUPPORT_MSG = "Bonjour, j'ai besoin d'assistance sur mon espace Nova AI."
whatsapp_premium_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={PREMIUM_MSG.replace(' ', '%20')}"
whatsapp_support_url = f"https://wa.me/{WHATSAPP_NUMBER}?text={SUPPORT_MSG.replace(' ', '%20')}"

if "db" not in st.session_state:
    st.session_state["db"] = load_db()

if "current_user" not in st.session_state:
    st.session_state["current_user"] = None

if "view" not in st.session_state:
    st.session_state["view"] = "home"

if "is_glowing" not in st.session_state:
    st.session_state["is_glowing"] = False

if "show_premium_modal" not in st.session_state:
    st.session_state["show_premium_modal"] = False

if "premium_formule" not in st.session_state:
    st.session_state["premium_formule"] = None

if "show_service_warning" not in st.session_state:
    st.session_state["show_service_warning"] = False

if "last_service_seen" not in st.session_state:
    st.session_state["last_service_seen"] = None

if "warning_triggered" not in st.session_state:
    st.session_state["warning_triggered"] = False

if "intro_played" not in st.session_state:
    st.session_state["intro_played"] = False

if "show_install_guide" not in st.session_state:
    st.session_state["show_install_guide"] = False

if "install_guide_uid" not in st.session_state:
    st.session_state["install_guide_uid"] = ""

# Reconnaissance automatique via cookie navigateur (session persistante)
if st.session_state["current_user"] is None:
    # 1. Vérifier d'abord l'URL
    stored_user = st.query_params.get("user_id")
    if stored_user and stored_user in st.session_state["db"]["users"]:
        st.session_state["current_user"] = stored_user
    else:
        # 2. Lire le cookie via localStorage
        components.html("""
            <script>
            var uid = localStorage.getItem('nova_user_id');
            if (uid) {
                // Passer l'uid à Streamlit via l'URL
                var url = new URL(window.location.href);
                url.searchParams.set('user_id', uid);
                window.location.href = url.toString();
            }
            </script>
        """, height=0)

# Sauvegarder dans localStorage à chaque connexion
if st.session_state["current_user"]:
    uid_connecte = st.session_state["current_user"]
    components.html(f"""
        <script>
        localStorage.setItem('nova_user_id', '{uid_connecte}');
        </script>
    """, height=0)

# ==========================================
# DESIGN ET STYLE (CSS AVANCÉ)
# ==========================================

def inject_custom_css():
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        
        * { font-family: 'Poppins', sans-serif; }

        /* FOND APP */
        .stApp {
            background: #0f0c29;
            background: -webkit-linear-gradient(to right, #24243e, #302b63, #0f0c29);
            background: linear-gradient(to right, #24243e, #302b63, #0f0c29);
            color: #ffffff;
            transition: filter 0.5s ease;
        }
        
        /* EFFET D'ILLUMINATION GLOBALE */
        @keyframes glow-pulse {
            0% { filter: brightness(1) saturate(1); box-shadow: inset 0 0 0px transparent; }
            50% { filter: brightness(1.8) saturate(1.5); box-shadow: inset 0 0 100px rgba(0, 210, 255, 0.5); }
            100% { filter: brightness(1) saturate(1); box-shadow: inset 0 0 0px transparent; }
        }

        /* TITRE PRINCIPAL */
        .main-title {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            font-weight: 800;
            font-size: 3.5rem !important;
            text-align: center;
            margin-bottom: 20px;
            text-shadow: 0px 0px 20px rgba(0, 210, 255, 0.3);
        }

        /* --- STYLISATION DES ONGLETS (TABS) --- */
        .stTabs [data-baseweb="tab-list"] {
            gap: 20px;
            background-color: rgba(255, 255, 255, 0.05);
            padding: 10px;
            border-radius: 15px;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        .stTabs [data-baseweb="tab"] {
            height: 60px;
            white-space: pre-wrap;
            background-color: rgba(0, 210, 255, 0.1);
            border-radius: 10px;
            color: white !important;
            font-weight: 700 !important;
            font-size: 1.2rem !important;
            transition: all 0.3s ease;
            border: 1px solid transparent;
            padding: 0 25px;
        }

        .stTabs [data-baseweb="tab"]:nth-child(2) {
            border: 1px solid #2ecc71 !important;
            box-shadow: 0 0 15px rgba(46, 204, 113, 0.2);
            background-color: rgba(46, 204, 113, 0.1);
        }

        .stTabs [data-baseweb="tab"]:hover {
            background-color: rgba(0, 210, 255, 0.3);
            transform: translateY(-2px);
        }

        .stTabs [aria-selected="true"] {
            background-color: rgba(0, 210, 255, 0.6) !important;
            border: 1px solid #00d2ff !important;
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.4);
        }

        /* --- ANIMATION BORDURE MULTICOLORE --- */
        @keyframes border-rainbow {
            0% { border-color: #00d2ff; box-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
            25% { border-color: #3a7bd5; box-shadow: 0 0 10px rgba(58, 123, 213, 0.3); }
            50% { border-color: #FFD700; box-shadow: 0 0 15px rgba(255, 215, 0, 0.3); }
            75% { border-color: #2ecc71; box-shadow: 0 0 10px rgba(46, 204, 113, 0.3); }
            100% { border-color: #00d2ff; box-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
        }

        /* --- ELEMENTS DE FORMULAIRE --- */
        .stTextInput label, .stSelectbox label, .stTextArea label {
            color: #00d2ff !important;
            font-weight: 600 !important;
            font-size: 1.1rem !important;
            margin-bottom: 5px;
        }
        
        div[data-baseweb="input"], div[data-baseweb="select"] > div {
            border: 1px solid rgba(0, 210, 255, 0.3) !important;
            background-color: rgba(0, 0, 0, 0.5) !important;
            color: white !important;
            border-radius: 10px !important;
        }

        /* ZONE DE TEXTE ARC-EN-CIEL */
        .stTextArea textarea {
            background-color: rgba(0, 0, 0, 0.6) !important;
            color: white !important;
            border-radius: 10px !important;
            border: 2px solid #00d2ff !important;
            animation: border-rainbow 4s linear infinite;
            transition: transform 0.3s;
        }
        
        .stTextArea textarea:focus {
            transform: scale(1.01);
            animation: border-rainbow 1.5s linear infinite;
        }

        /* --- LOGO STRIP --- */
        .logo-container {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 30px;
            margin-top: 20px;
            padding: 15px;
            background: rgba(255, 255, 255, 0.03);
            border-radius: 15px;
        }
        .logo-item {
            width: 45px;
            height: 45px;
            filter: grayscale(0.5) opacity(0.7);
            transition: all 0.3s ease;
        }
        .logo-item:hover {
            filter: grayscale(0) opacity(1);
            transform: translateY(-5px) scale(1.1);
        }

        /* --- CARTE PREMIUM --- */
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

        .premium-title {
            color: #FFD700 !important;
            font-size: 1.5rem;
            font-weight: 800;
            text-transform: uppercase;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }

        .premium-desc {
            color: #ffffff !important;
            font-size: 1rem;
            margin-bottom: 20px;
            line-height: 1.5;
        }

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
            transition: transform 0.2s, box-shadow 0.2s;
            border: none;
            cursor: pointer;
        }
        .btn-gold:hover {
            transform: scale(1.05);
            box-shadow: 0 8px 25px rgba(255, 215, 0, 0.6);
        }

        /* BOUTONS STREAMLIT */
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
        .stButton>button:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0, 210, 255, 0.5);
        }

        /* --- INFO BOX (Sidebar) --- */
        .info-card {
            background: rgba(0, 0, 0, 0.4) !important;
            border-left: 4px solid #00d2ff;
            padding: 15px;
            border-radius: 0 10px 10px 0;
            margin-bottom: 15px;
            box-shadow: 2px 2px 10px rgba(0,0,0,0.3);
        }
        .info-title {
            color: #00d2ff !important;
            font-weight: bold;
            font-size: 1.1rem;
            display: block;
            margin-bottom: 8px;
            text-transform: uppercase;
        }

        /* --- CARTE DE LIVRABLE --- */
        .file-card {
            background: rgba(255, 255, 255, 0.08);
            border: 2px solid rgba(46, 204, 113, 0.5);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
            box-shadow: 0 4px 15px rgba(0, 0, 0, 0.3);
            animation: slideIn 0.5s ease;
        }
        
        @keyframes slideIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

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
        .support-btn:hover {
            background: #25D366;
            color: white !important;
        }

        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #00d2ff , #3a7bd5);
        }
        </style>
    """, unsafe_allow_html=True)
    
    if st.session_state["is_glowing"]:
        st.markdown('<style>.stApp { animation: glow-pulse 1.5s ease-in-out infinite; }</style>', unsafe_allow_html=True)

# ==========================================
# PAGES ET COMPOSANTS
# ==========================================

def show_auth_page():

    # --- CSS exclusif à la page d'authentification ---
    st.markdown("""
    <style>
    /* ===== ANIMATIONS ===== */
    @keyframes shimmer {
        0%   { background-position: -200% center; }
        100% { background-position:  200% center; }
    }
    @keyframes float-up {
        0%   { opacity: 0; transform: translateY(30px); }
        100% { opacity: 1; transform: translateY(0); }
    }
    @keyframes letter-pop {
        0%   { opacity: 0; transform: translateY(20px) scale(0.8); }
        60%  { transform: translateY(-4px) scale(1.05); }
        100% { opacity: 1; transform: translateY(0) scale(1); }
    }
    @keyframes glow-border {
        0%   { box-shadow: 0 0 8px rgba(255,215,0,0.3), inset 0 0 8px rgba(255,215,0,0.05); }
        50%  { box-shadow: 0 0 28px rgba(255,215,0,0.7), inset 0 0 20px rgba(255,215,0,0.08); }
        100% { box-shadow: 0 0 8px rgba(255,215,0,0.3), inset 0 0 8px rgba(255,215,0,0.05); }
    }
    @keyframes particle-drift {
        0%   { transform: translateY(0px) translateX(0px) rotate(0deg); opacity: 0.6; }
        33%  { transform: translateY(-18px) translateX(8px) rotate(120deg); opacity: 1; }
        66%  { transform: translateY(-8px) translateX(-6px) rotate(240deg); opacity: 0.7; }
        100% { transform: translateY(0px) translateX(0px) rotate(360deg); opacity: 0.6; }
    }
    @keyframes scanline {
        0%   { top: -10%; }
        100% { top: 110%; }
    }
    @keyframes pulse-dot {
        0%, 100% { opacity: 1; transform: scale(1); }
        50%       { opacity: 0.4; transform: scale(0.6); }
    }

    /* ===== HERO HEADER ===== */
    .auth-hero {
        text-align: center;
        padding: 40px 20px 10px 20px;
        animation: float-up 0.8s ease both;
    }
    .auth-logo-ring {
        width: 90px; height: 90px;
        border-radius: 50%;
        margin: 0 auto 18px auto;
        background: radial-gradient(circle at 35% 35%, #fff8e1, #FFD700 40%, #b8860b);
        box-shadow: 0 0 0 4px rgba(255,215,0,0.2), 0 0 40px rgba(255,215,0,0.5);
        display: flex; align-items: center; justify-content: center;
        font-size: 2.6rem;
        animation: glow-border 3s ease-in-out infinite;
        position: relative;
    }
    .auth-logo-ring::after {
        content: '';
        position: absolute;
        inset: -6px;
        border-radius: 50%;
        border: 2px dashed rgba(255,215,0,0.4);
        animation: particle-drift 6s linear infinite;
    }

    /* ===== TITRE ANIMÉ LETTRE PAR LETTRE ===== */
    .auth-title-wrap { display: flex; justify-content: center; gap: 2px; flex-wrap: wrap; margin-bottom: 6px; }
    .auth-letter {
        font-size: 3rem;
        font-weight: 800;
        background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
        background-size: 200% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: letter-pop 0.5s ease both, shimmer 3s linear infinite;
        display: inline-block;
        line-height: 1.1;
    }
    .auth-subtitle {
        color: rgba(255,215,0,0.65);
        font-size: 0.95rem;
        letter-spacing: 4px;
        text-transform: uppercase;
        animation: float-up 1s ease 0.5s both;
        margin-bottom: 6px;
    }
    .auth-tagline {
        color: rgba(255,255,255,0.4);
        font-size: 0.82rem;
        letter-spacing: 1.5px;
        animation: float-up 1s ease 0.8s both;
    }

    /* ===== SÉPARATEUR ===== */
    .auth-divider {
        display: flex; align-items: center; gap: 14px;
        margin: 28px auto 32px auto; max-width: 420px;
        animation: float-up 1s ease 1s both;
    }
    .auth-divider-line { flex: 1; height: 1px; background: linear-gradient(90deg, transparent, rgba(255,215,0,0.5), transparent); }
    .auth-divider-dot {
        width: 6px; height: 6px; border-radius: 50%; background: #FFD700;
        animation: pulse-dot 1.8s ease-in-out infinite;
    }

    /* ===== CARTES DE FORMULAIRE ===== */
    .auth-card {
        background: linear-gradient(145deg, rgba(20,15,5,0.95), rgba(35,25,5,0.9));
        border: 1px solid rgba(255,215,0,0.35);
        border-radius: 22px;
        padding: 32px 28px 28px 28px;
        position: relative;
        overflow: hidden;
        animation: float-up 0.9s ease both;
        animation-delay: var(--card-delay, 0s);
    }
    .auth-card::before {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; height: 3px;
        background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
        background-size: 200% auto;
        animation: shimmer 2.5s linear infinite;
        border-radius: 22px 22px 0 0;
    }
    .auth-card::after {
        content: '';
        position: absolute;
        width: 180px; height: 180px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255,215,0,0.06), transparent 70%);
        bottom: -60px; right: -60px;
        pointer-events: none;
    }
    /* Scanline subtile */
    .auth-card .scanline {
        position: absolute;
        left: 0; right: 0; height: 2px;
        background: linear-gradient(90deg, transparent, rgba(255,215,0,0.12), transparent);
        animation: scanline 4s linear infinite;
        pointer-events: none;
    }

    /* ===== EN-TÊTE CARTE ===== */
    .auth-card-header {
        display: flex; align-items: center; gap: 12px;
        margin-bottom: 22px;
    }
    .auth-card-icon {
        width: 44px; height: 44px; border-radius: 12px;
        display: flex; align-items: center; justify-content: center;
        font-size: 1.4rem;
        background: linear-gradient(135deg, rgba(255,215,0,0.15), rgba(255,215,0,0.05));
        border: 1px solid rgba(255,215,0,0.3);
        box-shadow: 0 0 12px rgba(255,215,0,0.15);
    }
    .auth-card-title {
        color: #FFD700 !important;
        font-size: 1.15rem;
        font-weight: 800;
        letter-spacing: 0.5px;
        margin: 0;
        text-transform: uppercase;
    }
    .auth-card-desc {
        color: rgba(255,255,255,0.35);
        font-size: 0.75rem;
        margin-top: 2px;
        letter-spacing: 0.5px;
    }

    /* ===== CHAMPS DE FORMULAIRE (override doré) ===== */
    .auth-page .stTextInput label {
        color: rgba(255,215,0,0.8) !important;
        font-size: 0.82rem !important;
        font-weight: 600 !important;
        letter-spacing: 1px;
        text-transform: uppercase;
    }
    .auth-page div[data-baseweb="input"] {
        background: rgba(0,0,0,0.5) !important;
        border: 1px solid rgba(255,215,0,0.25) !important;
        border-radius: 12px !important;
        transition: border-color 0.3s, box-shadow 0.3s !important;
    }
    .auth-page div[data-baseweb="input"]:focus-within {
        border-color: rgba(255,215,0,0.7) !important;
        box-shadow: 0 0 0 3px rgba(255,215,0,0.12) !important;
    }

    /* ===== ANIMATIONS PERMANENTES BOUTONS ===== */
    @keyframes btn-shimmer {
        0%   { background-position: -300% center; }
        100% { background-position:  300% center; }
    }
    @keyframes btn-float {
        0%, 100% { transform: translateY(0px);   box-shadow: 0 6px 25px rgba(255,215,0,0.45), 0 0 0 0 rgba(255,215,0,0.2); }
        50%       { transform: translateY(-4px);  box-shadow: 0 14px 35px rgba(255,215,0,0.65), 0 0 18px 4px rgba(255,215,0,0.15); }
    }
    @keyframes btn-glow-ring {
        0%, 100% { box-shadow: 0 6px 25px rgba(255,215,0,0.45), 0 0  0px rgba(255,215,0,0);   }
        50%       { box-shadow: 0 6px 25px rgba(255,215,0,0.45), 0 0 22px rgba(255,215,0,0.35); }
    }

    /* ===== BOUTONS DORÉ PREMIUM ===== */
    .auth-page .stButton > button {
        background: linear-gradient(
            90deg,
            #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500
        ) !important;
        background-size: 300% auto !important;
        color: #0a0800 !important;
        font-weight: 800 !important;
        font-size: 0.92rem !important;
        letter-spacing: 2.5px !important;
        text-transform: uppercase !important;
        border-radius: 50px !important;
        border: none !important;
        padding: 0.82rem 1.8rem !important;
        width: 100% !important;
        position: relative !important;
        overflow: hidden !important;
        /* Shimmer en boucle permanente */
        animation: btn-shimmer 3s linear infinite, btn-float 3.5s ease-in-out infinite !important;
        cursor: pointer !important;
    }
    /* Reflet blanc glissant par-dessus */
    .auth-page .stButton > button::before {
        content: '' !important;
        position: absolute !important;
        top: 0 !important; left: -75% !important;
        width: 50% !important; height: 100% !important;
        background: linear-gradient(
            120deg,
            transparent 30%,
            rgba(255,255,255,0.35) 50%,
            transparent 70%
        ) !important;
        animation: btn-shimmer 3s linear infinite !important;
        pointer-events: none !important;
    }
    /* Anneau de glow en dessous du bouton */
    .auth-page .stButton > button::after {
        content: '' !important;
        position: absolute !important;
        inset: 0 !important;
        border-radius: 50px !important;
        box-shadow: 0 0 0 2px rgba(255,215,0,0.5) !important;
        animation: btn-glow-ring 2s ease-in-out infinite !important;
        pointer-events: none !important;
    }

    /* ===== BADGE SÉCURITÉ ===== */
    .auth-secure-badge {
        display: flex; align-items: center; justify-content: center;
        gap: 8px; margin-top: 28px;
        color: rgba(255,215,0,0.35);
        font-size: 0.72rem; letter-spacing: 1.5px; text-transform: uppercase;
        animation: float-up 1s ease 1.2s both;
    }
    .auth-secure-badge span { font-size: 0.9rem; }
    </style>
    """, unsafe_allow_html=True)

    # --- Hero header ---
    letters = list("NOVA AI")
    letter_spans = "".join(
        f'<span class="auth-letter" style="animation-delay:{i*0.07:.2f}s">'
        f'{"&nbsp;" if c == " " else c}</span>'
        for i, c in enumerate(letters)
    )
    st.markdown(f"""
    <div class="auth-hero">
        <div class="auth-logo-ring">⚡</div>
        <div class="auth-title-wrap">{letter_spans}</div>
        <div class="auth-subtitle">Plateforme IA bureautique</div>
        <div class="auth-tagline">Intelligence · Excellence · Performance</div>
    </div>
    <div class="auth-divider">
        <div class="auth-divider-line"></div>
        <div class="auth-divider-dot"></div>
        <div class="auth-divider-line"></div>
    </div>
    """, unsafe_allow_html=True)

    # --- Deux colonnes de formulaires ---
    st.markdown('<div class="auth-page">', unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown("""
        <div class="auth-card" style="--card-delay:1.1s;">
            <div class="scanline"></div>
            <div class="auth-card-header">
                <div class="auth-card-icon">🔐</div>
                <div>
                    <div class="auth-card-title">Accès Membre</div>
                    <div class="auth-card-desc">Identifiez-vous pour accéder à votre espace</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        with st.form("login"):
            uid    = st.text_input("Identifiant Nova", placeholder="Votre identifiant...")
            wa_auth = st.text_input("Numéro WhatsApp", placeholder="Ex: 22501...")
            if st.form_submit_button("⚡ S'IDENTIFIER"):
                db = st.session_state["db"]
                if uid in db["users"] and db["users"][uid]["whatsapp"] == normalize_wa(wa_auth):
                    st.session_state["current_user"] = uid
                    st.session_state["view"] = "home"
                    st.session_state["show_install_guide"] = True
                    st.session_state["install_guide_uid"] = uid
                    st.query_params["user_id"] = uid
                    st.rerun()
                else:
                    st.error("❌ Identifiant ou numéro inconnu.")

    with col2:
        st.markdown("""
        <div class="auth-card" style="--card-delay:1.3s;">
            <div class="scanline"></div>
            <div class="auth-card-header">
                <div class="auth-card-icon">✨</div>
                <div>
                    <div class="auth-card-title">Nouveau Compte</div>
                    <div class="auth-card-desc">Rejoignez l'élite Nova AI dès maintenant</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        with st.form("signup"):
            new_uid = st.text_input("Identifiant au choix", placeholder="Choisissez un identifiant...")
            new_wa  = st.text_input("Votre WhatsApp (clé d'accès)", placeholder="Ex: 22507...")
            if st.form_submit_button("💎 REJOINDRE NOVA AI"):
                if new_uid and new_wa:
                    db = st.session_state["db"]
                    if new_uid not in db["users"]:
                        db["users"][new_uid] = {
                            "whatsapp": normalize_wa(new_wa),
                            "email": "Non renseigné",
                            "joined": str(datetime.now())
                        }
                        save_user(new_uid, normalize_wa(new_wa))
                        st.session_state["current_user"] = new_uid
                        st.session_state["view"] = "home"
                        st.session_state["show_install_guide"] = True
                        st.session_state["install_guide_uid"] = new_uid
                        st.session_state["db"] = load_db()
                        st.query_params["user_id"] = new_uid
                        st.rerun()
                    else:
                        st.warning("⚠️ Identifiant déjà utilisé.")
                else:
                    st.error("Champs obligatoires.")

    st.markdown('</div>', unsafe_allow_html=True)

    # --- Badge sécurité bas de page ---
    st.markdown("""
    <div class="auth-secure-badge">
        <span>🔒</span> Connexion sécurisée &nbsp;·&nbsp; <span>⚡</span> Nova AI &nbsp;·&nbsp; <span>🛡️</span> Données protégées
    </div>
    """, unsafe_allow_html=True)

    # --- Voix de guidage à la connexion (ElevenLabs login.mp3) ---
    audio_path_login = "login.mp3"
    if os.path.exists(audio_path_login):
        with open(audio_path_login, "rb") as f:
            audio_b64_login = __import__('base64').b64encode(f.read()).decode()
        components.html(f"""
            <script>
            (function() {{
                setTimeout(function() {{
                    var b64 = "{audio_b64_login}";
                    var binary = atob(b64);
                    var bytes = new Uint8Array(binary.length);
                    for (var i = 0; i < binary.length; i++) {{
                        bytes[i] = binary.charCodeAt(i);
                    }}
                    var blob = new Blob([bytes], {{type: "audio/mpeg"}});
                    var url = URL.createObjectURL(blob);
                    var audio = new Audio(url);
                    audio.volume = 1;
                    audio.play().catch(function(e) {{ console.log("Autoplay bloqué:", e); }});
                }}, 3000);
            }})();
            </script>
        """, height=0)

def main_dashboard():
    user = st.session_state["current_user"]
    db = st.session_state["db"]
    
    with st.sidebar:
        st.markdown(f"### 👤 {user if user else 'Visiteur'}")
        if user:
            st.markdown(f"📱 **{db['users'][user]['whatsapp']}**")
            if st.button("Quitter la session"):
                st.session_state["current_user"] = None
                st.query_params.clear()
                components.html("<script>localStorage.removeItem('nova_user_id');</script>", height=0)
                st.rerun()
        else:
            if st.button("Connexion"):
                st.session_state["view"] = "auth"
                st.rerun()
        
        st.divider()
        st.markdown(f"""
            <div class="info-card">
                <span class="info-title">🚀 LIVRAISON NOVA</span>
                <span style="color:#eee; font-size:0.9rem;">
                    Vos résultats IA apparaissent dans l'onglet <b>"📂 MES LIVRABLES"</b>.
                    <br><br>
                    Suivi instantané 24h/24.
                </span>
            </div>
        """, unsafe_allow_html=True)
        st.markdown(f'<a href="{whatsapp_support_url}" target="_blank" class="support-btn">💬 Support Nova</a>', unsafe_allow_html=True)

    st.markdown("<h1 class='main-title'>NOVA AI PLATFORM</h1>", unsafe_allow_html=True)

    # --- Message vocal d'accueil ElevenLabs (une seule fois par session, après 3 secondes) ---
    if not st.session_state["intro_played"]:
        st.session_state["intro_played"] = True
        audio_path = "intro.mp3"
        if os.path.exists(audio_path):
            with open(audio_path, "rb") as f:
                audio_b64 = __import__('base64').b64encode(f.read()).decode()
            components.html(f"""
                <script>
                (function() {{
                    setTimeout(function() {{
                        var b64 = "{audio_b64}";
                        var binary = atob(b64);
                        var bytes = new Uint8Array(binary.length);
                        for (var i = 0; i < binary.length; i++) {{
                            bytes[i] = binary.charCodeAt(i);
                        }}
                        var blob = new Blob([bytes], {{type: "audio/mpeg"}});
                        var url = URL.createObjectURL(blob);
                        var audio = new Audio(url);
                        audio.volume = 1;
                        audio.play().catch(function(e) {{ console.log("Autoplay bloqué:", e); }});
                    }}, 3000);
                }})();
                </script>
            """, height=0)

    # ==========================================
    # CARTE PREMIUM + FENÊTRE INTERNE (session_state)
    # ==========================================
    wa_jour = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%20Journalier%20%C3%A0%20600%20FC."
    wa_10j  = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%2010%20Jours%20%C3%A0%201000%20FC."
    wa_30j  = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%2030%20Jours%20%C3%A0%202500%20FC."

    # --- Bouton d'ouverture de la fenêtre premium ---
    st.markdown("""
        <div class="premium-card">
            <div class="premium-title">⭐ ACCÉLÉRATEUR NOVA PREMIUM ⭐</div>
            <div class="premium-desc">
                Passez au niveau supérieur : IA illimitée et puissance de calcul <b>10<sup>10</sup></b>.
            </div>
        </div>
    """, unsafe_allow_html=True)

    col_btn_center = st.columns([1, 2, 1])[1]
    with col_btn_center:
        if st.button("💎 ACTIVER NOVA PREMIUM", key="open_premium"):
            st.session_state["show_premium_modal"] = True
            st.rerun()

    # --- Page dédiée premium (affichée si show_premium_modal = True) ---
    if st.session_state["show_premium_modal"] and not st.session_state["premium_formule"]:

        st.markdown("""
        <style>
        @keyframes gold-shimmer {
            0%   { background-position: -300% center; }
            100% { background-position:  300% center; }
        }
        @keyframes gold-glow {
            0%,100% { box-shadow: 0 0 15px rgba(255,215,0,0.3); }
            50%      { box-shadow: 0 0 40px rgba(255,215,0,0.8); }
        }
        @keyframes gold-float {
            0%,100% { transform: translateY(0px); }
            50%      { transform: translateY(-8px); }
        }
        @keyframes gold-particle {
            0%   { transform: translateY(0) scale(1); opacity:0.8; }
            50%  { transform: translateY(-20px) scale(1.4); opacity:1; }
            100% { transform: translateY(0) scale(1); opacity:0.8; }
        }
        @keyframes slide-up {
            0%   { opacity:0; transform: translateY(30px); }
            100% { opacity:1; transform: translateY(0); }
        }
        .prem-page { padding: 20px 0; }
        .prem-stars { position:fixed; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:0; overflow:hidden; }
        .prem-star  { position:absolute; animation: gold-particle 3s ease-in-out infinite; font-size:1.2rem; }
        .prem-title {
            font-size: 2.5rem;
            font-weight: 800;
            background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500);
            background-size: 300% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gold-shimmer 3s linear infinite;
            text-align: center;
            letter-spacing: 2px;
        }
        .prem-card {
            background: linear-gradient(145deg, rgba(10,7,0,0.98), rgba(25,18,0,0.96));
            border: 2px solid #FFD700;
            border-radius: 24px;
            padding: 30px 20px;
            text-align: center;
            position: relative;
            overflow: hidden;
            animation: slide-up 0.6s ease both, gold-glow 3s ease-in-out infinite;
            cursor: pointer;
            transition: transform 0.3s;
        }
        .prem-card:hover { transform: translateY(-5px) scale(1.02); }
        .prem-card::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0; height: 4px;
            background: linear-gradient(90deg, #7a5500, #FFD700, #fff5c0, #FFD700, #7a5500);
            background-size: 200% auto;
            animation: gold-shimmer 2s linear infinite;
        }
        .prem-price {
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(90deg, #FFD700, #fff5c0, #FFD700);
            background-size: 200% auto;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            animation: gold-shimmer 2s linear infinite;
        }
        .prem-btn {
            display: block;
            background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500);
            background-size: 300% auto;
            color: #0a0800 !important;
            font-weight: 800;
            font-size: 0.95rem;
            padding: 12px 20px;
            border-radius: 50px;
            text-decoration: none;
            animation: gold-shimmer 3s linear infinite;
            margin-top: 12px;
            letter-spacing: 1px;
            border: none;
            cursor: pointer;
            width: 100%;
        }
        </style>

        <div class="prem-page">
            <div class="prem-stars">
                <span class="prem-star" style="top:5%;  left:8%;  animation-delay:0s;">✨</span>
                <span class="prem-star" style="top:12%; left:85%; animation-delay:0.5s;">💎</span>
                <span class="prem-star" style="top:40%; left:3%;  animation-delay:1s;">⭐</span>
                <span class="prem-star" style="top:65%; left:90%; animation-delay:0.3s;">✨</span>
                <span class="prem-star" style="top:80%; left:15%; animation-delay:1.5s;">💎</span>
                <span class="prem-star" style="top:90%; left:70%; animation-delay:0.8s;">⭐</span>
            </div>
            <div style="position:relative; z-index:1; text-align:center; margin-bottom:25px;">
                <div style="font-size:3rem; animation: gold-float 3s ease-in-out infinite;">👑</div>
                <div class="prem-title">NOVA PREMIUM</div>
                <div style="color:rgba(255,215,0,0.5); font-size:0.82rem; letter-spacing:3px; text-transform:uppercase; margin-top:6px;">
                    Choisissez votre formule d'excellence
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        col1_p, col2_p, col3_p = st.columns(3)

        with col1_p:
            st.markdown("""
            <div class="prem-card" style="animation-delay:0.2s;">
                <div style="font-size:2.5rem; margin-bottom:10px; animation: gold-float 3s ease-in-out infinite;">🌅</div>
                <div style="color:#FFD700; font-weight:800; font-size:1rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:6px;">Journalier</div>
                <div class="prem-price">600 FC</div>
                <div style="color:rgba(255,255,255,0.35); font-size:0.78rem; margin-bottom:14px;">par jour</div>
                <div style="background:rgba(255,215,0,0.08); border:1px solid rgba(255,215,0,0.2); border-radius:12px; padding:10px; margin-bottom:6px;">
                    <span style="color:#FFD700; font-size:0.85rem; font-weight:700;">⚡ 1,5 génération IA / jour</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🌅 Choisir Journalier", key="prem_jour"):
                st.session_state["premium_formule"] = "journalier"
                st.rerun()

        with col2_p:
            st.markdown("""
            <div class="prem-card" style="animation-delay:0.4s; border-color:#fff5c0; box-shadow: 0 0 50px rgba(255,215,0,0.5);">
                <div style="background:linear-gradient(90deg,#FFD700,#fff5c0,#FFD700); background-size:200% auto; animation:gold-shimmer 2s linear infinite; color:#000; font-size:0.7rem; font-weight:800; padding:4px 16px; border-radius:20px; display:inline-block; margin-bottom:10px; letter-spacing:2px;">⭐ POPULAIRE</div>
                <div style="font-size:2.5rem; margin-bottom:10px; animation: gold-float 3s ease-in-out infinite 0.5s;">🔟</div>
                <div style="color:#FFD700; font-weight:800; font-size:1rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:6px;">10 Jours</div>
                <div class="prem-price">1 000 FC</div>
                <div style="color:rgba(255,255,255,0.35); font-size:0.78rem; margin-bottom:14px;">10 jours</div>
                <div style="background:rgba(255,215,0,0.08); border:1px solid rgba(255,215,0,0.2); border-radius:12px; padding:10px; margin-bottom:6px;">
                    <span style="color:#FFD700; font-size:0.85rem; font-weight:700;">⚡ 4 générations IA / jour</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("🔟 Choisir 10 Jours", key="prem_10j"):
                st.session_state["premium_formule"] = "10jours"
                st.rerun()

        with col3_p:
            st.markdown("""
            <div class="prem-card" style="animation-delay:0.6s;">
                <div style="font-size:2.5rem; margin-bottom:10px; animation: gold-float 3s ease-in-out infinite 1s;">👑</div>
                <div style="color:#FFD700; font-weight:800; font-size:1rem; letter-spacing:2px; text-transform:uppercase; margin-bottom:6px;">30 Jours</div>
                <div class="prem-price">2 500 FC</div>
                <div style="color:rgba(255,255,255,0.35); font-size:0.78rem; margin-bottom:14px;">30 jours</div>
                <div style="background:rgba(255,215,0,0.08); border:1px solid rgba(255,215,0,0.2); border-radius:12px; padding:10px; margin-bottom:6px;">
                    <span style="color:#FFD700; font-size:0.85rem; font-weight:700;">⚡ 8,5 générations IA / jour</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            if st.button("👑 Choisir 30 Jours", key="prem_30j"):
                st.session_state["premium_formule"] = "30jours"
                st.rerun()

        st.markdown("<br>", unsafe_allow_html=True)
        col_close = st.columns([1, 2, 1])[1]
        with col_close:
            if st.button("✕ Fermer", key="close_premium"):
                st.session_state["show_premium_modal"] = False
                st.rerun()

    # --- Page dédiée par formule ---
    if st.session_state["premium_formule"]:
        formule = st.session_state["premium_formule"]
        if formule == "journalier":
            emoji, nom, prix, duree, gen, wa_url_f = "🌅", "JOURNALIER", "600 FC", "1 jour", "1,5 génération IA / jour", wa_jour
        elif formule == "10jours":
            emoji, nom, prix, duree, gen, wa_url_f = "🔟", "10 JOURS", "1 000 FC", "10 jours", "4 générations IA / jour", wa_10j
        else:
            emoji, nom, prix, duree, gen, wa_url_f = "👑", "30 JOURS", "2 500 FC", "30 jours", "8,5 générations IA / jour", wa_30j

        st.markdown(f"""
        <style>
        @keyframes pg-shimmer {{ 0% {{ background-position:-300% center; }} 100% {{ background-position:300% center; }} }}
        @keyframes pg-glow {{ 0%,100% {{ box-shadow:0 0 20px rgba(255,215,0,0.3); }} 50% {{ box-shadow:0 0 60px rgba(255,215,0,0.9); }} }}
        @keyframes pg-float {{ 0%,100% {{ transform:translateY(0); }} 50% {{ transform:translateY(-12px); }} }}
        @keyframes pg-particle {{ 0% {{ transform:translateY(0) scale(1); opacity:0.8; }} 50% {{ transform:translateY(-25px) scale(1.5); opacity:1; }} 100% {{ transform:translateY(0) scale(1); opacity:0.8; }} }}
        @keyframes pg-slide {{ 0% {{ opacity:0; transform:translateY(40px); }} 100% {{ opacity:1; transform:translateY(0); }} }}
        @keyframes pg-rotate {{ 0% {{ transform:rotate(0deg); }} 100% {{ transform:rotate(360deg); }} }}

        .pg-stars {{ position:fixed; top:0; left:0; width:100%; height:100%; pointer-events:none; z-index:0; overflow:hidden; }}
        .pg-star   {{ position:absolute; animation: pg-particle 3s ease-in-out infinite; }}

        .pg-ring {{
            width:120px; height:120px; border-radius:50%;
            background: radial-gradient(circle at 35% 35%, #fff8e1, #FFD700 40%, #b8860b);
            box-shadow: 0 0 0 6px rgba(255,215,0,0.2), 0 0 60px rgba(255,215,0,0.7);
            display:flex; align-items:center; justify-content:center;
            font-size:3.5rem; margin:0 auto 20px auto;
            animation: pg-glow 2s ease-in-out infinite, pg-float 3s ease-in-out infinite;
            position:relative;
        }}
        .pg-ring::after {{
            content:'';
            position:absolute; inset:-10px;
            border-radius:50%;
            border:3px dashed rgba(255,215,0,0.5);
            animation: pg-rotate 8s linear infinite;
        }}
        .pg-title {{
            font-size:2.5rem; font-weight:800;
            background: linear-gradient(90deg,#7a5500,#b8860b,#FFD700,#fff5c0,#FFD700,#b8860b,#7a5500);
            background-size:300% auto;
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            animation: pg-shimmer 2.5s linear infinite;
            text-align:center; letter-spacing:3px; text-transform:uppercase;
        }}
        .pg-card {{
            background: linear-gradient(145deg, rgba(10,7,0,0.98), rgba(25,18,0,0.96));
            border:2px solid #FFD700; border-radius:28px;
            padding:35px 25px; max-width:550px; margin:20px auto;
            position:relative; overflow:hidden;
            animation: pg-slide 0.7s ease both, pg-glow 3s ease-in-out infinite;
        }}
        .pg-card::before {{
            content:'';
            position:absolute; top:0; left:0; right:0; height:4px;
            background: linear-gradient(90deg,#7a5500,#FFD700,#fff5c0,#FFD700,#7a5500);
            background-size:200% auto;
            animation: pg-shimmer 2s linear infinite;
        }}
        .pg-price {{
            font-size:3.5rem; font-weight:800;
            background:linear-gradient(90deg,#FFD700,#fff5c0,#FFD700);
            background-size:200% auto;
            -webkit-background-clip:text; -webkit-text-fill-color:transparent;
            animation:pg-shimmer 2s linear infinite;
            text-align:center;
        }}
        .pg-feature {{
            background:rgba(255,215,0,0.07);
            border:1px solid rgba(255,215,0,0.25);
            border-radius:14px; padding:14px 18px;
            margin-bottom:12px; font-size:0.9rem;
            color:rgba(255,255,255,0.85);
            animation: pg-slide 0.5s ease both;
        }}
        .pg-feature b {{ color:#FFD700; }}
        .pg-wa-btn {{
            display:block;
            background:linear-gradient(90deg,#7a5500,#b8860b,#FFD700,#fff5c0,#FFD700,#b8860b,#7a5500);
            background-size:300% auto;
            color:#0a0800 !important; font-weight:800; font-size:1.1rem;
            padding:16px 30px; border-radius:50px;
            text-decoration:none; text-align:center;
            animation: pg-shimmer 3s linear infinite, pg-glow 2.5s ease-in-out infinite;
            margin-top:20px; letter-spacing:2px;
        }}
        </style>

        <div style="padding:30px 10px; position:relative;">
            <div class="pg-stars">
                <span class="pg-star" style="top:5%;  left:6%;  font-size:1.4rem; animation-delay:0s;">✨</span>
                <span class="pg-star" style="top:10%; left:88%; font-size:1rem;   animation-delay:0.5s;">💎</span>
                <span class="pg-star" style="top:30%; left:2%;  font-size:1.2rem; animation-delay:1s;">⭐</span>
                <span class="pg-star" style="top:55%; left:93%; font-size:1.4rem; animation-delay:0.3s;">✨</span>
                <span class="pg-star" style="top:70%; left:10%; font-size:1rem;   animation-delay:1.5s;">💎</span>
                <span class="pg-star" style="top:85%; left:75%; font-size:1.2rem; animation-delay:0.8s;">⭐</span>
                <span class="pg-star" style="top:45%; left:48%; font-size:0.9rem; animation-delay:2s;">✨</span>
            </div>

            <div style="position:relative; z-index:1; text-align:center; margin-bottom:10px;">
                <div class="pg-ring">{emoji}</div>
                <div class="pg-title">NOVA {nom}</div>
                <div style="color:rgba(255,215,0,0.5); font-size:0.8rem; letter-spacing:3px; text-transform:uppercase; margin-top:6px;">
                    Formule Premium · Excellence Garantie
                </div>
            </div>

            <div class="pg-card" style="position:relative; z-index:1;">
                <div class="pg-price">{prix}</div>
                <div style="color:rgba(255,255,255,0.4); font-size:0.82rem; text-align:center; margin-bottom:20px;">/ {duree}</div>

                <div class="pg-feature" style="animation-delay:0.2s;"><b>⚡ Puissance ·</b> {gen}</div>
                <div class="pg-feature" style="animation-delay:0.3s;"><b>🚀 Accès ·</b> Priorité absolue sur toutes les missions Nova</div>
                <div class="pg-feature" style="animation-delay:0.4s;"><b>🤖 IA ·</b> Algorithme Nova de pointe — puissance 10<sup>10</sup></div>
                <div class="pg-feature" style="animation-delay:0.5s;"><b>💬 Support ·</b> Assistance WhatsApp dédiée 24h/24</div>
                <div class="pg-feature" style="animation-delay:0.6s;"><b>📦 Livraison ·</b> Résultats ultra-rapides dans votre espace Nova</div>

                <a href="{wa_url_f}" target="_blank" class="pg-wa-btn">
                    💎 ACTIVER MAINTENANT SUR WHATSAPP
                </a>
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_back = st.columns([1, 2, 1])[1]
        with col_back:
            if st.button("← Retour aux formules", key="back_premium"):
                st.session_state["premium_formule"] = None
                st.rerun()

    tab1, tab2 = st.tabs(["🚀 DÉPLOYER UNE TÂCHE", "📂 MES LIVRABLES (CLOUD)"])

    with tab1:

        # --- Dictionnaire des prérequis par service ---
        SERVICE_PREREQUIS = {
            "📝 Exposé scolaire complet IA": {
                "icone": "📝",
                "titre": "Exposé Scolaire Complet IA",
                "intro": "Pour que nous puissions générer votre exposé avec précision et professionnalisme, veuillez nous fournir les informations suivantes dans votre cahier des charges :",
                "items": [
                    ("🎯", "Le thème ou sujet de l'exposé"),
                    ("🏫", "Le niveau scolaire (Collège, Lycée, Université...)"),
                    ("📏", "Le nombre de pages désiré"),
                    ("🏢", "L'école ou l'établissement concerné"),
                    ("📚", "La matière ou discipline concernée"),
                ],
                "note": "Plus vos informations sont précises, plus le résultat sera adapté à vos attentes."
            },
            "📊 Data & Excel Analytics": {
                "icone": "📊",
                "titre": "Data & Excel Analytics",
                "intro": "Pour traiter vos données efficacement, merci de préciser dans votre cahier des charges :",
                "items": [
                    ("📁", "Le type de fichier à traiter (Excel, CSV, autre...)"),
                    ("🎯", "L'objectif de l'analyse (tableau de bord, graphiques, calculs...)"),
                    ("📋", "Une description des données ou colonnes présentes"),
                    ("🔢", "Le nombre approximatif de lignes ou d'entrées"),
                ],
                "note": "Vous pouvez également joindre un fichier exemple via WhatsApp après la soumission."
            },
            "⚙️ Pack Office (Word/Excel/PPT)": {
                "icone": "⚙️",
                "titre": "Pack Office — Word / Excel / PowerPoint",
                "intro": "Pour réaliser votre document Office au standard professionnel, précisez :",
                "items": [
                    ("📄", "Le type de document souhaité (Word, Excel ou PowerPoint)"),
                    ("🎯", "Le sujet ou contenu du document"),
                    ("📏", "Le nombre de pages ou diapositives souhaité"),
                    ("🎨", "Un style ou thème de couleurs si vous en avez un"),
                ],
                "note": "Précisez si vous souhaitez un logo ou une charte graphique particulière."
            },
            "🎨 Création Design IA": {
                "icone": "🎨",
                "titre": "Création Design IA",
                "intro": "Pour créer un design à la hauteur de vos attentes, indiquez-nous :",
                "items": [
                    ("🖼️", "Le type de visuel (affiche, bannière, logo, flyer...)"),
                    ("📐", "Le format ou dimensions souhaitées"),
                    ("🎨", "Les couleurs ou thème visuel préféré"),
                    ("✍️", "Les textes ou messages à intégrer"),
                    ("🏢", "Le nom de votre entreprise ou projet"),
                ],
                "note": "Une référence visuelle ou exemple que vous aimez accélérera le travail."
            },
            "📚 Affiches & Reçus": {
                "icone": "📚",
                "titre": "Affiches & Reçus",
                "intro": "Pour concevoir votre affiche ou reçu, nous aurons besoin de :",
                "items": [
                    ("🏢", "Le nom de votre entreprise ou organisation"),
                    ("📋", "Les informations à faire apparaître (prix, date, lieu, contacts...)"),
                    ("🎨", "La couleur principale ou identité visuelle"),
                    ("📐", "Le format désiré (A4, A5, reçu thermique...)"),
                ],
                "note": "Un logo ou image à intégrer peut être envoyé via WhatsApp."
            },
            "👔 CV & Lettre de Motivation": {
                "icone": "👔",
                "titre": "CV & Lettre de Motivation",
                "intro": "Pour rédiger votre CV ou lettre de motivation de façon percutante, fournissez :",
                "items": [
                    ("👤", "Votre nom complet et coordonnées"),
                    ("🎓", "Vos diplômes et formations"),
                    ("💼", "Vos expériences professionnelles"),
                    ("🎯", "Le poste ou secteur visé"),
                    ("✨", "Vos compétences clés et atouts"),
                ],
                "note": "Précisez si vous souhaitez uniquement le CV, la lettre, ou les deux."
            },
            "📄 Conversion & Fichier PDF": {
                "icone": "📄",
                "titre": "Conversion & Fichier PDF",
                "intro": "Pour traiter votre fichier correctement, indiquez-nous :",
                "items": [
                    ("📁", "Le format du fichier source (Word, Excel, image, autre...)"),
                    ("🔄", "Le format de sortie souhaité (PDF, Word, Excel...)"),
                    ("📋", "Le nombre de fichiers à convertir"),
                    ("🔒", "Si le PDF doit être protégé par mot de passe"),
                ],
                "note": "Envoyez votre fichier directement via WhatsApp après la soumission."
            },
            "📝 Création de Sujets & Examens": {
                "icone": "📝",
                "titre": "Création de Sujets & Examens",
                "intro": "Pour concevoir votre devoir ou examen sur mesure, veuillez nous préciser :",
                "items": [
                    ("🎓", "Le niveau scolaire (Primaire, Collège, Lycée, Université...)"),
                    ("📚", "La matière ou discipline concernée"),
                    ("🎯", "Le type de sujet (devoir surveillé, examen, contrôle, concours...)"),
                    ("📏", "Le nombre de questions ou d'exercices souhaité"),
                    ("⏱️", "La durée prévue pour l'épreuve"),
                    ("🏢", "L'établissement scolaire ou l'institution"),
                ],
                "note": "Précisez si vous souhaitez un corrigé ou un barème de notation en accompagnement."
            },
        }

        col_f, col_wa = st.columns(2)
        with col_f:
            st.markdown("#### 🛠️ Service Nova")
            service = st.selectbox(
                "Type d'intervention",
                [
                    "📊 Data & Excel Analytics",
                    "📝 Exposé scolaire complet IA",
                    "📝 Création de Sujets & Examens",
                    "⚙️ Pack Office (Word/Excel/PPT)",
                    "🎨 Création Design IA",
                    "📚 Affiches & Reçus",
                    "👔 CV & Lettre de Motivation",
                    "📄 Conversion & Fichier PDF"
                ]
            )
        with col_wa:
            st.markdown("#### 📞 Notification")
            default_wa = db["users"][user]["whatsapp"] if user else ""
            wa_display = st.text_input("WhatsApp de contact", value=default_wa, placeholder="225...")

        # Service Excel : déclenchement uniquement à la saisie
        SERVICE_SAISIE = "📊 Data & Excel Analytics"

        # Reset quand le service change
        if service != st.session_state["last_service_seen"]:
            st.session_state["last_service_seen"] = service
            st.session_state["warning_triggered"] = False
            st.session_state["show_service_warning"] = False
            # Pour les autres services : déclencher immédiatement
            if service != SERVICE_SAISIE and service in SERVICE_PREREQUIS:
                st.session_state["show_service_warning"] = True

        # --- Fenêtre d'avertissement (affichée AVANT le textarea pour les autres services) ---
        if st.session_state["show_service_warning"] and service in SERVICE_PREREQUIS and service != SERVICE_SAISIE:
            info = SERVICE_PREREQUIS[service]

            # Mapping service → fichier MP3
            SERVICE_AUDIO = {
                "📝 Exposé scolaire complet IA":   "prerequis_expose.mp3",
                "📝 Création de Sujets & Examens": "prerequis_examens.mp3",
                "⚙️ Pack Office (Word/Excel/PPT)": "prerequis_office.mp3",
                "🎨 Création Design IA":           "prerequis_design.mp3",
                "📚 Affiches & Reçus":             "prerequis_affiches.mp3",
                "👔 CV & Lettre de Motivation":    "prerequis_cv.mp3",
                "📄 Conversion & Fichier PDF":     "prerequis_pdf.mp3",
            }

            st.info(f"""
**{info["icone"]} {info["titre"]} — Informations requises**

{info["intro"]}

{"".join(f"- {icone} {texte}\n" for icone, texte in info["items"])}
💡 *{info["note"]}*
""")
            # Lecture MP3 ElevenLabs si disponible, sinon Web Speech
            audio_file = SERVICE_AUDIO.get(service)
            if audio_file and os.path.exists(audio_file):
                with open(audio_file, "rb") as f:
                    b64 = __import__('base64').b64encode(f.read()).decode()
                components.html(f"""
                    <script>
                    (function() {{
                        var binary = atob("{b64}");
                        var bytes = new Uint8Array(binary.length);
                        for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                        var blob = new Blob([bytes], {{type: "audio/mpeg"}});
                        var audio = new Audio(URL.createObjectURL(blob));
                        audio.volume = 1;
                        audio.play().catch(function(e) {{ console.log(e); }});
                    }})();
                    </script>
                """, height=0)
            col_mid = st.columns([1, 2, 1])[1]
            with col_mid:
                if st.button("✅ J'ai compris, je continue ma demande", key="close_service_warning"):
                    st.session_state["show_service_warning"] = False
                    components.html("<script>window.speechSynthesis.cancel();</script>", height=0)
                    st.rerun()

        # --- Champ de saisie ---
        st.markdown("#### 📝 Spécifications de la mission")
        prompt = st.text_area("Cahier des charges Nova", height=150, placeholder="Détaillez votre projet pour une exécution parfaite...")

        # --- Excel uniquement : déclenchement à la première frappe ---
        if service == SERVICE_SAISIE and service in SERVICE_PREREQUIS:
            if prompt and not st.session_state["warning_triggered"]:
                st.session_state["warning_triggered"] = True
                st.session_state["show_service_warning"] = True
                st.rerun()

            if st.session_state["show_service_warning"]:
                info = SERVICE_PREREQUIS[service]

                st.info(f"""
**{info["icone"]} {info["titre"]} — Informations requises**

{info["intro"]}

{"".join(f"- {icone} {texte}\n" for icone, texte in info["items"])}
💡 *{info["note"]}*
""")
                # Lecture MP3 ElevenLabs Excel
                if os.path.exists("prerequis_excel.mp3"):
                    with open("prerequis_excel.mp3", "rb") as f:
                        b64_excel = __import__('base64').b64encode(f.read()).decode()
                    components.html(f"""
                        <script>
                        (function() {{
                            var binary = atob("{b64_excel}");
                            var bytes = new Uint8Array(binary.length);
                            for (var i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
                            var blob = new Blob([bytes], {{type: "audio/mpeg"}});
                            var audio = new Audio(URL.createObjectURL(blob));
                            audio.volume = 1;
                            audio.play().catch(function(e) {{ console.log(e); }});
                        }})();
                        </script>
                    """, height=0)
                col_mid = st.columns([1, 2, 1])[1]
                with col_mid:
                    if st.button("✅ J'ai compris, je continue ma demande", key="close_service_warning"):
                        st.session_state["show_service_warning"] = False
                        components.html("<script>window.speechSynthesis.cancel();</script>", height=0)
                        st.rerun()
        
        # LOGO STRIP
        st.markdown("""
        <div class="logo-container">
            <svg class="logo-item" viewBox="0 0 24 24" fill="#217346"><path d="M16.2 21H2.8c-.4 0-.8-.4-.8-.8V3.8c0-.4.4-.8.8-.8h13.4c.4 0 .8.4.8.8v16.4c0 .4-.4.8-.8.8z"/><path d="M14.7 15.3l-2.2-3.3 2.2-3.3h-1.6l-1.4 2.2-1.4-2.2H8.7l2.2 3.3-2.2 3.3h1.6l1.4-2.2 1.4 2.2z" fill="white"/></svg>
            <svg class="logo-item" viewBox="0 0 24 24" fill="#2b579a"><path d="M16.2 21H2.8c-.4 0-.8-.4-.8-.8V3.8c0-.4.4-.8.8-.8h13.4c.4 0 .8.4.8.8v16.4c0 .4-.4.8-.8.8z"/><path d="M11.5 15.3V8.7h1.4c.8 0 1.4.3 1.8.8.4.5.6 1.1.6 1.8s-.2 1.3-.6 1.8c-.4.5-1 .8-1.8.8h-1.4z" fill="white"/></svg>
            <svg class="logo-item" viewBox="0 0 24 24" fill="#3776ab"><path d="M12 2C6.47 2 2 6.47 2 12s4.47 10 10 10 10-4.47 10-10S17.53 2 12 2zm-1 14.5h-1v-5h1v5zm0-6.5h-1V9h1v1z"/></svg>
            <svg class="logo-item" viewBox="0 0 24 24" fill="#d24726"><path d="M16.2 21H2.8c-.4 0-.8-.4-.8-.8V3.8c0-.4.4-.8.8-.8h13.4c.4 0 .8.4.8.8v16.4c0 .4-.4.8-.8.8z"/><path d="M8.7 8.7h1.5v5.1h2.5v1.5H8.7V8.7z" fill="white"/></svg>
            <svg class="logo-item" viewBox="0 0 24 24" fill="#ff9900"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
        </div>
        <p style="text-align:center; color:rgba(255,255,255,0.4); font-size:0.8rem; margin-top:5px;">Data • Dev • Design • Expertise • Rapidité</p>
        """, unsafe_allow_html=True)

        # Indicateur visuel des champs manquants (sans bloquer)
        champs_manquants = []
        if not wa_display:
            champs_manquants.append("WhatsApp de contact")
        if not prompt:
            champs_manquants.append("Cahier des charges")
        if champs_manquants:
            st.markdown(f"""
            <div style="
                background: rgba(241,196,15,0.08);
                border: 1px dashed rgba(241,196,15,0.4);
                border-radius: 10px;
                padding: 10px 16px;
                margin-top: 8px;
                color: rgba(241,196,15,0.85);
                font-size: 0.85rem;
            ">
                ⚠️ Veuillez s'il vous plaît détailler vos besoins comme il se doit, afin d'éviter que votre demande soit refusée.
            </div>
            """, unsafe_allow_html=True)

        if st.button("ACTIVER L'ALGORITHME NOVA"):
            st.session_state["is_glowing"] = True
            st.rerun()

        if st.session_state["is_glowing"]:
            progress_placeholder = st.empty()
            status_text = st.empty()
            bar = progress_placeholder.progress(0)
            for percent_complete in range(100):
                time.sleep(0.02)
                bar.progress(percent_complete + 1)
                status_text.markdown(f"<p style='text-align:center; color:#00d2ff; font-size:1.2rem; font-weight:bold;'>NOVA PROCESSING : {percent_complete + 1}%</p>", unsafe_allow_html=True)

            # Statut selon complétude
            statut = "En attente de vérification (informations incomplètes)" if champs_manquants else "Traitement Nova en cours..."

            new_req = {
                "id": hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8],
                "user": user if user else "guest",
                "service": service,
                "desc": prompt if prompt else "(aucune description fournie)",
                "whatsapp": normalize_wa(wa_display) if wa_display else "(non renseigné)",
                "status": statut,
                "incomplet": bool(champs_manquants),
                "champs_manquants": champs_manquants,
                "timestamp": str(datetime.now())
            }
            st.session_state["db"]["demandes"].append(new_req)
            save_demande(new_req)
            st.session_state["db"] = load_db()
            st.session_state["is_glowing"] = False
            progress_placeholder.empty()
            status_text.empty()
            if user:
                st.success("✅ Mission enregistrée ! L'équipe Nova examinera votre demande.")

                # Voix ElevenLabs confirmation.mp3
                audio_path_confirm = "confirmation.mp3"
                if os.path.exists(audio_path_confirm):
                    with open(audio_path_confirm, "rb") as f:
                        audio_b64_confirm = __import__('base64').b64encode(f.read()).decode()
                    components.html(f"""
                        <script>
                        (function() {{
                            var b64 = "{audio_b64_confirm}";
                            var binary = atob(b64);
                            var bytes = new Uint8Array(binary.length);
                            for (var i = 0; i < binary.length; i++) {{
                                bytes[i] = binary.charCodeAt(i);
                            }}
                            var blob = new Blob([bytes], {{type: "audio/mpeg"}});
                            var url = URL.createObjectURL(blob);
                            var audio = new Audio(url);
                            audio.volume = 1;
                            audio.play().catch(function(e) {{ console.log("Autoplay bloqué:", e); }});
                        }})();
                        </script>
                    """, height=0)

                st.balloons()
                time.sleep(20)
                st.rerun()
            else:
                st.session_state["view"] = "auth"
                st.rerun()

    with tab2:
        if not user:
            st.warning("🔒 Authentification requise pour accéder au Cloud Nova.")
        else:
            fresh_db = load_db()
            user_links = fresh_db["liens"].get(user, [])
            user_reqs = [r for r in fresh_db["demandes"] if r["user"] == user]
            
            st.markdown("""
                <div style="background: rgba(46, 204, 113, 0.1); padding: 15px; border-radius: 10px; border: 1px dashed #2ecc71; margin-bottom: 20px; text-align: center;">
                    <h2 style="color: #2ecc71; margin: 0;">📥 HUB DE TÉLÉCHARGEMENT NOVA</h2>
                    <p style="color: white; font-size: 0.9rem;">Accédez à vos actifs numériques terminés.</p>
                </div>
            """, unsafe_allow_html=True)

            if user_links:
                for link in user_links:
                    st.markdown(f"""
                    <div class="file-card">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <div>
                                <h3 style="color:#00d2ff; margin:0;">💎 {link['name']}</h3>
                                <p style="color:#aaa; font-size:0.85rem; margin: 5px 0;">Finalisé le {link.get('date', 'Aujourd\'hui')}</p>
                            </div>
                            <a href="{link['url']}" target="_blank" style="text-decoration:none;">
                                <button style="padding:10px 25px; background:#2ecc71; color:white; border:none; border-radius:30px; font-weight:bold; cursor:pointer; box-shadow: 0 4px 10px rgba(46,204,113,0.3);">
                                    📥 TÉLÉCHARGER
                                </button>
                            </a>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            
            if user_reqs:
                st.markdown("#### ⏳ Missions Nova en préparation")
                for r in user_reqs:
                    st.markdown(f"""
                        <div class="file-card" style="border-left: 5px solid #f1c40f; border-color: rgba(241, 196, 15, 0.3);">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <strong style="color: #f1c40f;">{r['service']}</strong><br>
                                    <span style="color:#eee; font-size: 0.9rem;">Status: {r['status']}</span>
                                </div>
                                <div class="spinner" style="width: 20px; height: 20px; border: 3px solid rgba(255,255,255,0.1); border-top: 3px solid #f1c40f; border-radius: 50%; animation: spin 1s linear infinite;"></div>
                            </div>
                        </div>
                        <style>@keyframes spin {{ 0% {{ transform: rotate(0deg); }} 100% {{ transform: rotate(360deg); }} }}</style>
                    """, unsafe_allow_html=True)
            
            if not user_links and not user_reqs:
                st.info("Votre espace Nova est vide. Déployez votre première tâche !")
            
            st.write("---")
            st.markdown("### 🆘 Support Nova Direct")
            col_rel, col_sup = st.columns(2)
            with col_rel:
                relance_msg = f"Bonjour, je souhaite un status sur ma mission Nova (ID: {user})."
                wa_relance = f"https://wa.me/{WHATSAPP_NUMBER}?text={relance_msg.replace(' ', '%20')}"
                st.markdown(f'<a href="{wa_relance}" target="_blank" class="support-btn" style="border-color:#f1c40f; color:#f1c40f !important;">🔔 Relancer Nova</a>', unsafe_allow_html=True)
            with col_sup:
                st.markdown(f'<a href="{whatsapp_support_url}" target="_blank" class="support-btn">🙋 Agent Nova</a>', unsafe_allow_html=True)

    with st.expander("🛠 Console Admin Nova"):
        if st.text_input("Master Key", type="password") == ADMIN_CODE:

            current_db = st.session_state["db"]

            st.markdown("### 🛡️ Panneau de contrôle Nova")

            if not current_db["demandes"]:
                st.info("✅ Aucune mission en attente.")

            def wa_url(numero, texte):
                encoded = texte.replace(" ", "%20").replace("'", "%27").replace("\n", "%0A")
                return f"https://wa.me/{numero}?text={encoded}"

            for i, req in enumerate(current_db["demandes"]):
                client_wa_raw    = req.get("whatsapp", "(non renseigné)")
                client_wa        = normalize_wa(client_wa_raw)
                client_nom       = req.get("user", "Inconnu")
                service          = req.get("service", "—")
                description      = req.get("desc", "(aucune description)")
                req_id           = req.get("id", f"{i+1}")
                timestamp        = req.get("timestamp", "")[:16] if req.get("timestamp") else "—"
                est_incomplet    = req.get("incomplet", False)
                champs_manquants = req.get("champs_manquants", [])

                # Séparateur entre demandes
                if i > 0:
                    st.divider()

                # Infos de la mission sur des lignes simples
                st.markdown(f"**Mission `#{req_id}`** · {timestamp}" + (" — ⚠️ *Incomplet : " + ", ".join(champs_manquants) + "*" if est_incomplet else ""))
                st.markdown(f"👤 **Client :** {client_nom}")
                st.markdown(f"📱 **WhatsApp :** {client_wa}")
                st.markdown(f"🛠️ **Service demandé :** {service}")
                st.markdown(f"📝 **Détails de la demande :** {description}")

                # Messages WhatsApp
                if est_incomplet and champs_manquants:
                    champs_str = ", ".join(champs_manquants)
                    msg_rejet = (f"Bonjour {client_nom}, nous avons reçu votre demande Nova AI "
                                 f"concernant : {service}. Cependant, nous ne pouvons pas la traiter "
                                 f"car les informations suivantes sont manquantes : {champs_str}. "
                                 f"Merci de soumettre à nouveau votre demande en complétant tous les champs. "
                                 f"— Équipe Nova AI ⚡")
                else:
                    msg_rejet = (f"Bonjour {client_nom}, nous avons bien reçu votre demande Nova AI "
                                 f"concernant : {service}. Malheureusement, nous ne sommes pas en mesure "
                                 f"de traiter cette mission pour le moment. Merci de nous recontacter. "
                                 f"— Équipe Nova AI ⚡")

                msg_succes = (f"✅ Bonjour {client_nom} ! Votre mission Nova AI ({service}) est terminée ! "
                              f"Rendez-vous dans votre espace Nova pour récupérer votre livrable. "
                              f"Merci de votre confiance. — Équipe Nova AI ⚡")

                msg_recu = (f"📬 Bonjour {client_nom}, nous confirmons la réception de votre demande "
                            f"Nova AI : {service}. Votre mission est en cours de traitement. "
                            f"Vous serez notifié dès qu'elle sera finalisée. — Équipe Nova AI ⚡")

                url_rejet  = wa_url(client_wa, msg_rejet)
                url_succes = wa_url(client_wa, msg_succes)
                url_recu   = wa_url(client_wa, msg_recu)

                # 3 boutons WhatsApp
                col_rejet, col_recu, col_succes = st.columns(3)
                with col_rejet:
                    st.markdown(f'<a href="{url_rejet}" target="_blank" style="display:block; text-align:center; padding:10px; border-radius:10px; background:rgba(231,76,60,0.15); border:1px solid rgba(231,76,60,0.5); color:#e74c3c; font-weight:700; text-decoration:none;">❌ Rejeter</a>', unsafe_allow_html=True)
                with col_recu:
                    st.markdown(f'<a href="{url_recu}" target="_blank" style="display:block; text-align:center; padding:10px; border-radius:10px; background:rgba(255,215,0,0.1); border:1px solid rgba(255,215,0,0.4); color:#FFD700; font-weight:700; text-decoration:none;">📬 Reçu</a>', unsafe_allow_html=True)
                with col_succes:
                    st.markdown(f'<a href="{url_succes}" target="_blank" style="display:block; text-align:center; padding:10px; border-radius:10px; background:rgba(46,204,113,0.15); border:1px solid rgba(46,204,113,0.5); color:#2ecc71; font-weight:700; text-decoration:none;">✅ Succès</a>', unsafe_allow_html=True)

                # Livraison
                url_dl = st.text_input("🔗 Lien de livraison", key=f"url_{i}", placeholder="https://drive.google.com/...")
                if st.button("📦 LIVRER LA MISSION", key=f"btn_{i}"):
                    if url_dl:
                        save_lien(req['user'], req['service'], url_dl, datetime.now().strftime("%d/%m/%Y"))
                        delete_demande(req['id'])
                        st.session_state["db"] = load_db()
                        st.rerun()

# ==========================================
# RUNTIME
# ==========================================

inject_custom_css()

# Gestion de la persistance via localStorage
components.html("""
    <script>
    const user = localStorage.getItem('nova_user');
    const urlParams = new URLSearchParams(window.parent.location.search);
    const currentUser = urlParams.get('user_id');
    
    if (user && !currentUser && !window.parent.location.href.includes('logout')) {
        window.parent.location.href = window.parent.location.origin + window.parent.location.pathname + '?user_id=' + user;
    }
    if (!currentUser && user && window.parent.location.href.includes('logout')) {
        localStorage.removeItem('nova_user');
    }
    if (currentUser && user !== currentUser) {
        localStorage.setItem('nova_user', currentUser);
    }
    </script>
""", height=0)

# ==========================================
# PAGE GUIDE INSTALLATION PWA
# ==========================================
def show_install_guide(uid):
    lien = f"https://espace-partage-8.streamlit.app/?user_id={uid}"
    st.markdown(f"""
    <style>
    @keyframes float-letter {{
        0%   {{ transform: translateY(0px) rotate(-3deg); opacity:0.7; }}
        50%  {{ transform: translateY(-18px) rotate(3deg); opacity:1; }}
        100% {{ transform: translateY(0px) rotate(-3deg); opacity:0.7; }}
    }}
    @keyframes shimmer-gold {{
        0%   {{ background-position: -300% center; }}
        100% {{ background-position:  300% center; }}
    }}
    @keyframes pulse-ring {{
        0%   {{ box-shadow: 0 0 0 0 rgba(255,215,0,0.5); }}
        70%  {{ box-shadow: 0 0 0 20px rgba(255,215,0,0); }}
        100% {{ box-shadow: 0 0 0 0 rgba(255,215,0,0); }}
    }}
    @keyframes star-drift {{
        0%   {{ transform: translateY(0) translateX(0) scale(1); opacity:0.8; }}
        33%  {{ transform: translateY(-25px) translateX(10px) scale(1.3); opacity:1; }}
        66%  {{ transform: translateY(-10px) translateX(-8px) scale(0.9); opacity:0.6; }}
        100% {{ transform: translateY(0) translateX(0) scale(1); opacity:0.8; }}
    }}
    @keyframes slide-in-up {{
        0%   {{ opacity:0; transform: translateY(40px); }}
        100% {{ opacity:1; transform: translateY(0); }}
    }}
    @keyframes glow-line {{
        0%,100% {{ opacity:0.4; }}
        50%      {{ opacity:1; }}
    }}

    .guide-page {{
        min-height: 100vh;
        padding: 40px 20px;
        text-align: center;
    }}
    .guide-stars {{
        position: fixed;
        top: 0; left: 0;
        width: 100%; height: 100%;
        pointer-events: none;
        z-index: 0;
        overflow: hidden;
    }}
    .guide-star {{
        position: absolute;
        font-size: 1rem;
        animation: star-drift 4s ease-in-out infinite;
    }}
    .guide-title-wrap {{
        display: flex;
        justify-content: center;
        gap: 4px;
        flex-wrap: wrap;
        margin-bottom: 8px;
        position: relative;
        z-index: 1;
    }}
    .guide-letter {{
        font-size: 2.8rem;
        font-weight: 800;
        background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
        background-size: 300% auto;
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        animation: float-letter 3s ease-in-out infinite, shimmer-gold 3s linear infinite;
        display: inline-block;
    }}
    .guide-card {{
        background: linear-gradient(145deg, rgba(15,10,2,0.97), rgba(30,20,5,0.95));
        border: 1px solid rgba(255,215,0,0.4);
        border-radius: 24px;
        padding: 30px 25px;
        margin: 15px auto;
        max-width: 600px;
        position: relative;
        overflow: hidden;
        animation: slide-in-up 0.7s ease both;
        z-index: 1;
    }}
    .guide-card::before {{
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; height: 3px;
        background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
        background-size: 200% auto;
        animation: shimmer-gold 2.5s linear infinite;
        border-radius: 24px 24px 0 0;
    }}
    .guide-lien-box {{
        background: rgba(0,0,0,0.5);
        border: 1px solid rgba(0,210,255,0.5);
        border-radius: 14px;
        padding: 14px 18px;
        margin: 18px 0;
        word-break: break-all;
        font-size: 0.95rem;
        font-weight: 700;
        color: #00d2ff;
        letter-spacing: 0.5px;
        animation: glow-line 2s ease-in-out infinite;
    }}
    .guide-step {{
        background: rgba(255,255,255,0.04);
        border: 1px solid rgba(255,215,0,0.15);
        border-radius: 14px;
        padding: 14px 16px;
        margin-bottom: 10px;
        text-align: left;
        font-size: 0.88rem;
        color: rgba(255,255,255,0.85);
        animation: slide-in-up 0.6s ease both;
    }}
    .guide-step b {{ color: #00d2ff; }}
    .guide-btn {{
        display: inline-block;
        background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500);
        background-size: 300% auto;
        color: #0a0800 !important;
        font-weight: 800;
        font-size: 1.05rem;
        padding: 14px 35px;
        border-radius: 50px;
        text-decoration: none;
        box-shadow: 0 6px 25px rgba(255,215,0,0.45);
        animation: shimmer-gold 3s linear infinite, pulse-ring 2.5s ease-in-out infinite;
        margin-top: 10px;
        letter-spacing: 1px;
    }}
    .guide-section-title {{
        color: #FFD700;
        font-weight: 800;
        font-size: 1rem;
        text-align: left;
        margin-bottom: 10px;
        margin-top: 18px;
        letter-spacing: 1px;
        text-transform: uppercase;
    }}
    </style>

    <div class="guide-page">

        <!-- Étoiles flottantes -->
        <div class="guide-stars">
            <span class="guide-star" style="top:8%; left:5%; animation-delay:0s;">✨</span>
            <span class="guide-star" style="top:15%; left:88%; animation-delay:0.8s;">⭐</span>
            <span class="guide-star" style="top:35%; left:3%; animation-delay:1.5s;">💫</span>
            <span class="guide-star" style="top:60%; left:92%; animation-delay:0.3s;">✨</span>
            <span class="guide-star" style="top:75%; left:7%; animation-delay:1.2s;">⭐</span>
            <span class="guide-star" style="top:85%; left:80%; animation-delay:0.6s;">💫</span>
            <span class="guide-star" style="top:50%; left:50%; animation-delay:2s;">✨</span>
        </div>

        <!-- Titre animé -->
        <div style="position:relative; z-index:1; margin-bottom:6px;">
            <div style="font-size:3.5rem; margin-bottom:10px;">📲</div>
            <div class="guide-title-wrap">
                {''.join(f'<span class="guide-letter" style="animation-delay:{i*0.12}s">{c if c != " " else "&nbsp;"}</span>' for i, c in enumerate("NOVA AI"))}
            </div>
            <div style="color:rgba(255,215,0,0.6); font-size:0.85rem; letter-spacing:4px; text-transform:uppercase; margin-top:4px;">
                Votre Application Personnelle
            </div>
        </div>

        <!-- Carte principale -->
        <div class="guide-card" style="animation-delay:0.2s;">
            <div style="color:white; font-size:1rem; font-weight:600; margin-bottom:4px;">
                🎉 Bienvenue <span style="color:#FFD700;">{uid}</span> !
            </div>
            <div style="color:rgba(255,255,255,0.5); font-size:0.82rem; margin-bottom:6px;">
                Installez votre espace Nova AI en quelques secondes — ne vous reconnectez plus jamais.
            </div>

            <div style="color:rgba(255,255,255,0.4); font-size:0.75rem; margin-bottom:4px; text-transform:uppercase; letter-spacing:1px;">🔗 Votre lien personnel</div>
            <div class="guide-lien-box">{lien}</div>

            <div style="text-align:center; margin-bottom:8px;">
                <a href="{lien}" target="_blank" class="guide-btn">⚡ Ouvrir Mon Espace Nova</a>
            </div>
        </div>

        <!-- Android -->
        <div class="guide-card" style="animation-delay:0.4s;">
            <div class="guide-section-title">📱 Android — Chrome</div>
            <div class="guide-step" style="animation-delay:0.5s;"><b>Étape 1 ·</b> Appuyez sur <b>"Ouvrir Mon Espace Nova"</b> ci-dessus</div>
            <div class="guide-step" style="animation-delay:0.6s;"><b>Étape 2 ·</b> Appuyez sur les <b>⋮ trois points</b> en haut à droite du navigateur</div>
            <div class="guide-step" style="animation-delay:0.7s;"><b>Étape 3 ·</b> Choisissez <b>"Ajouter à l'écran d'accueil"</b></div>
            <div class="guide-step" style="animation-delay:0.8s;"><b>Étape 4 ·</b> Confirmez — l'icône Nova AI apparaît sur votre écran 🎉</div>
        </div>

        <!-- iPhone -->
        <div class="guide-card" style="animation-delay:0.6s;">
            <div class="guide-section-title">🍎 iPhone — Safari</div>
            <div class="guide-step" style="animation-delay:0.7s;"><b>Étape 1 ·</b> Appuyez sur <b>"Ouvrir Mon Espace Nova"</b> ci-dessus</div>
            <div class="guide-step" style="animation-delay:0.8s;"><b>Étape 2 ·</b> Appuyez sur l'icône <b>📤 Partager</b> en bas de Safari</div>
            <div class="guide-step" style="animation-delay:0.9s;"><b>Étape 3 ·</b> Faites défiler et choisissez <b>"Sur l'écran d'accueil"</b></div>
            <div class="guide-step" style="animation-delay:1.0s;"><b>Étape 4 ·</b> Appuyez sur <b>"Ajouter"</b> — Nova AI est installé 🎉</div>
        </div>

        <!-- Badge -->
        <div style="position:relative; z-index:1; margin-top:20px; color:rgba(255,215,0,0.3); font-size:0.72rem; letter-spacing:2px; text-transform:uppercase;">
            🔒 Accès sécurisé &nbsp;·&nbsp; ⚡ Nova AI &nbsp;·&nbsp; 🛡️ Données protégées
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_c = st.columns([1, 2, 1])[1]
    with col_c:
        if st.button("✅ J'ai installé — Accéder à mon espace", key="guide_done"):
            st.session_state["show_install_guide"] = False
            st.rerun()

if st.session_state["view"] == "auth" and st.session_state["current_user"] is None:
    show_auth_page()
elif st.session_state.get("show_install_guide"):
    show_install_guide(st.session_state["install_guide_uid"])
else:
    main_dashboard()
