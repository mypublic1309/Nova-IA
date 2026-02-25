import streamlit as st
import json
import os
import hashlib
import time
from datetime import datetime, timedelta
from io import BytesIO
import streamlit.components.v1 as components
from supabase import create_client

st.set_page_config(
    page_title="L'IA bureautique NoVA AI", 
    page_icon="⚡", 
    layout="wide",
    initial_sidebar_state="expanded"
)

DATA_FILE = "data_nova_v3.json"
ADMIN_CODE = "02110240"

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def normalize_wa(numero):
    if not numero:
        return ""
    numero = numero.strip().replace(" ", "").replace("-", "").replace("+", "")
    if numero.startswith("0") and not numero.startswith("00"):
        numero = "225" + numero
    return numero

def load_db():
    try:
        users_rows = supabase.table("users").select("*").execute().data
        users = {}
        for r in users_rows:
            users[r["uid"]] = {
                "whatsapp": r["whatsapp"],
                "email": r.get("email", "Non renseigné"),
                "joined": r["joined"],
                "premium": r.get("premium", False),
                "premium_plan": r.get("premium_plan", None),
                "premium_expiry": r.get("premium_expiry", None),
            }
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

def save_user(uid, whatsapp, email="Non renseigné", premium=False, premium_plan=None, premium_expiry=None):
    try:
        supabase.table("users").upsert({
            "uid": uid, "whatsapp": whatsapp,
            "email": email, "joined": str(datetime.now()),
            "premium": premium, "premium_plan": premium_plan, "premium_expiry": premium_expiry,
        }).execute()
    except Exception as e:
        st.error(f"Erreur sauvegarde utilisateur : {e}")

def update_premium_status(uid, premium, premium_plan, premium_expiry):
    try:
        supabase.table("users").update({
            "premium": premium, "premium_plan": premium_plan, "premium_expiry": premium_expiry,
        }).eq("uid", uid).execute()
    except Exception as e:
        st.error(f"Erreur mise à jour premium : {e}")

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
    pass

def envoyer_notification(client_nom, client_wa, service, description):
    try:
        import resend
        resend.api_key = st.secrets["RESEND_API_KEY"]
        corps = f"""
🔔 NOUVELLE COMMANDE NOVA AI

👤 Client      : {client_nom}
📱 WhatsApp    : {client_wa}
🛠️ Service     : {service}
📝 Description : {description}

⏰ Reçue le {datetime.now().strftime("%d/%m/%Y à %H:%M")}

Connectez-vous à la console admin pour traiter cette mission.
        """
        resend.Emails.send({
            "from": "Nova AI <onboarding@resend.dev>",
            "to": [st.secrets["EMAIL_RECEIVER"]],
            "subject": f"🔔 Nouvelle commande Nova AI — {service}",
            "text": corps
        })
        st.toast("📧 Notification email envoyée !", icon="✅")
    except Exception as e:
        st.toast(f"❌ Email échoué : {e}", icon="⚠️")

PLANS_PREMIUM = {
    "Journalier": {"jours": 1,  "prix": "600 FC",  "emoji": "🌅", "generations": 1},
    "10 Jours":   {"jours": 10, "prix": "1000 FC", "emoji": "🔟", "generations": 4},
    "30 Jours":   {"jours": 30, "prix": "2500 FC", "emoji": "👑", "generations": 8},
}

def is_premium_actif(user_data):
    if not user_data.get("premium"):
        return False
    expiry = user_data.get("premium_expiry")
    if not expiry:
        return False
    try:
        return datetime.now() < datetime.fromisoformat(expiry)
    except:
        return False

def get_premium_info(user_data):
    if not is_premium_actif(user_data):
        return None
    try:
        expiry_dt  = datetime.fromisoformat(user_data["premium_expiry"])
        jours_rest = (expiry_dt - datetime.now()).days
        return {
            "plan":           user_data.get("premium_plan", "—"),
            "expiry":         expiry_dt.strftime("%d/%m/%Y à %H:%M"),
            "jours_restants": jours_rest,
        }
    except:
        return None

def activer_premium(uid, plan_name):
    jours  = PLANS_PREMIUM[plan_name]["jours"]
    expiry = datetime.now() + timedelta(days=jours)
    update_premium_status(uid, True, plan_name, expiry.isoformat())
    if "db" in st.session_state and uid in st.session_state["db"]["users"]:
        st.session_state["db"]["users"][uid].update({
            "premium": True, "premium_plan": plan_name,
            "premium_expiry": expiry.isoformat(),
        })

def desactiver_premium(uid):
    update_premium_status(uid, False, None, None)
    if "db" in st.session_state and uid in st.session_state["db"]["users"]:
        st.session_state["db"]["users"][uid].update({
            "premium": False, "premium_plan": None, "premium_expiry": None,
        })

def get_modeles_disponibles(api_key):
    import urllib.request as _ur
    import urllib.error
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = _ur.Request(url, headers={"Content-Type": "application/json"}, method="GET")
        with _ur.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        modeles = []
        exclusions = ["tts", "audio", "image", "imagen", "veo", "robotics",
                      "embedding", "aqa", "computer-use", "research", "nano-banana",
                      "gemma", "preview"]
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                nom = m["name"].replace("models/", "")
                if not any(excl in nom.lower() for excl in exclusions):
                    modeles.append(nom)
        def priorite(nom):
            if "flash-lite" in nom: return 0
            if "flash" in nom:      return 1
            if "pro" in nom:        return 2
            return 3
        modeles_tries = sorted(modeles, key=priorite)
        return modeles_tries
    except Exception as e:
        return ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"]


# ================================================================
# SECTION MOTEUR NOVA — Enseignement complet du rendu Word à Gemini
# ================================================================
SECTION_MOTEUR_NOVA = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 0 — FONCTIONNEMENT INTERNE DU MOTEUR NOVA (LIS EN PREMIER — CRITIQUE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LE MOTEUR NOVA CONVERTIT TON TEXTE LIGNE PAR LIGNE EN DOCUMENT WORD PROFESSIONNEL.
Chaque token que tu écris a un effet précis et prévisible dans le fichier .docx final.

╔══════════════════════════════════════════════════════════════════╗
║  ARCHITECTURE DES PAGES — RÈGLE ABSOLUE PRIORITAIRE             ║
╚══════════════════════════════════════════════════════════════════╝

---SAUT_DE_PAGE--- = VRAI SAUT DE PAGE WORD (<w:br type="page"/>)
Ce token crée physiquement une nouvelle feuille dans le document Word.

UTILISATION EXCLUSIVE :
✅ Après la page de garde  → ---SAUT_DE_PAGE---
✅ Après le sommaire       → ---SAUT_DE_PAGE---
❌ JAMAIS entre intro, parties, conclusion, bibliographie

STRUCTURE CORRECTE D'UN EXPOSÉ :
┌─────────────────────────────────────────┐
│  PAGE DE GARDE (complète, centrée)      │
├─────────────────────────────────────────┤ ← ---SAUT_DE_PAGE---
│  SOMMAIRE (complet, une page)           │
├─────────────────────────────────────────┤ ← ---SAUT_DE_PAGE---
│  INTRODUCTION                           │
│  PARTIE I + sous-parties                │  ← flux continu
│  PARTIE II + sous-parties               │     (pas de saut
│  PARTIE III + sous-parties              │      de page ici)
│  CONCLUSION                             │
│  BIBLIOGRAPHIE                          │
└─────────────────────────────────────────┘

╔══════════════════════════════════════════════════════════════════╗
║  TITRES → STYLES HEADING WORD EXACTS                            ║
╚══════════════════════════════════════════════════════════════════╝

# Titre      → Heading 1 Word (Arial 16pt, bleu 1F4E79, GRAS)
               Réservé : INTRODUCTION, CONCLUSION, BIBLIOGRAPHIE, SOMMAIRE

## Titre     → Heading 2 Word (Arial 14pt, bleu 2E75B6, gras)
               Réservé : I. GRANDE PARTIE, II. GRANDE PARTIE, III. GRANDE PARTIE

### Titre    → Heading 3 Word (Arial 12pt, gras)
               Réservé : 1.1 Sous-partie, 1.2 Sous-partie, 2.1 Sous-partie

#### Titre   → Heading 4 Word (Arial 11pt, gras italique)
               Réservé : sous-sous-parties très rares

HIÉRARCHIE STRICTE — ne jamais sauter un niveau :
✅ # → ## → ### (correct)
❌ # → ### directement (Heading 3 sans Heading 2 = structure Word cassée)

╔══════════════════════════════════════════════════════════════════╗
║  GRAS → **texte** DANS LE CORPS DU DOCUMENT                     ║
╚══════════════════════════════════════════════════════════════════╝

**mot** ou **groupe de mots** → Gras Arial 11pt dans le paragraphe courant

OBLIGATOIRE POUR :
• Termes techniques à la 1re occurrence : La **photosynthèse** désigne...
• Chiffres et données clés : **2,2 millions de tonnes**, **45%**, **322 463 km²**
• Noms d'auteurs : **KOUROUMA Ahmadou**, **DADIÉ Bernard**, **TADJO Véronique**
• Institutions : **FAO**, **BCEAO**, **INS-CI**, **UEMOA**, **CEDEAO**
• Dates historiques : **7 août 1960**, **2025-2026**, **1993**
• Dans les sujets d'examens : **Question 1**, **1.a)**, **Consigne :**, **TRAVAIL DEMANDÉ :**
• En-têtes administratifs : **RÉPUBLIQUE DE CÔTE D'IVOIRE**, **Matière :**, **Durée :**

╔══════════════════════════════════════════════════════════════════╗
║  SÉPARATEURS → LIGNES WORD RÉELLES                              ║
╚══════════════════════════════════════════════════════════════════╝

════════════════════════════════════════════════════════
→ Ligne ÉPAISSE bleue marine (sz=12, couleur #1F4E79)
→ QUAND : entre deux grandes parties (fin Partie I, début Partie II)
           entre deux exercices différents dans un sujet d'examen

────────────────────────────────────────────────────────
→ Ligne FINE grise (sz=4, couleur #AAAAAA)
→ QUAND : entre sous-parties, entre questions d'un même exercice

---SAUT_DE_PAGE---
→ Saut de page physique Word (nouvelle feuille blanche)
→ QUAND : uniquement après page de garde ET après sommaire

Note : toujours laisser une ligne vide avant ET après ════ et ────

╔══════════════════════════════════════════════════════════════════╗
║  TABLEAUX → CONVERSION AUTOMATIQUE EN TABLEAU WORD              ║
╚══════════════════════════════════════════════════════════════════╝

Syntaxe à utiliser (respecter EXACTEMENT) :

**Tableau N : [Titre précis et descriptif]**
| En-tête 1 | En-tête 2 | En-tête 3 |
|-----------|-----------|-----------|
| Valeur A  | Valeur B  | Valeur C  |
*Source : [Institution réelle, Année]*

Résultat automatique dans Word :
— En-tête : fond bleu foncé (#1F4E79) + texte blanc + gras
— Lignes alternées : bleu très clair (#EEF3FA) et blanc
— Bordures grises sur toutes les cellules
— Largeurs : 2 col → [3cm,6cm] | 3 col → [1cm,7.5cm,2.5cm] | 4 col → [1cm,5cm,2.5cm,2.5cm]

RÈGLES TABLEAUX :
✅ **Tableau N : [Titre]** AVANT le tableau (ligne séparée)
✅ *Source : [Référence]* APRÈS le tableau (ligne séparée)
✅ Ligne |---|---| obligatoire entre en-tête et données
✅ Contenu de cellule = texte court, une seule ligne
❌ Jamais de retour à la ligne dans une cellule
❌ Jamais de fusion de cellules

╔══════════════════════════════════════════════════════════════════╗
║  LISTES → PUCES ET NUMÉROS WORD                                  ║
╚══════════════════════════════════════════════════════════════════╝

- item (tiret + espace)     → Puce Word • (List Bullet, Arial 11pt)
1. item (chiffre + point)   → Numéro Word 1. 2. 3. (List Number, Arial 11pt)

AUTORISÉ dans : sommaire, bibliographie, consignes, choix QCM, lignes de réponse
INTERDIT dans : corps du développement d'un exposé (utiliser paragraphes en prose)
INTERDIT : puces unicode directes (•, ◆, ▶) — seul le tiret "-" est reconnu

╔══════════════════════════════════════════════════════════════════╗
║  FORMULES SCIENTIFIQUES — TEXTE CLAIR OBLIGATOIRE               ║
╚══════════════════════════════════════════════════════════════════╝

LE MOTEUR NE PEUT PAS RENDRE LE LATEX. Toutes les formules en texte pur :

MATHS :
  Fraction  : (a + b) / (c - d)         [jamais \\frac{a+b}{c-d}]
  Puissance : x au carré, x au cube     [jamais x² en exposant Unicode]
  Racine    : racine carrée de (b² - 4ac)
  Équation  : ax² + bx + c = 0, delta = b² - 4ac
  Solutions : x1 = (-b + racine(delta)) / (2a)
  Somme     : Somme de i=1 à n de (xi), moyenne = (Somme xi) / n

PHYSIQUE :
  Mécanique   : F = m x a (N, kg, m/s²) | v = d / t | Ec = (1/2) x m x v²
  Électricité : U = R x I (V, Ohm, A) | P = U x I (W) | P = R x I²
  Ondes       : v = lambda x f | f = 1 / T | omega = 2 x pi x f
  Optique     : n = sin(i1) / sin(i2) = c / v_milieu
  Pression    : P = F / S (Pa) | Boyle : P x V = constante

CHIMIE / SVT :
  Photosynthèse : 6 CO2 + 6 H2O + énergie lumineuse → C6H12O6 + 6 O2
  Respiration   : C6H12O6 + 6 O2 → 6 CO2 + 6 H2O + énergie (ATP)
  pH            : pH = -log([H+]) | acide si pH < 7, basique si pH > 7
  Concentration : C = n / V (mol/L) | Dilution : C1 x V1 = C2 x V2
  Gaz parfaits  : P x V = n x R x T (R = 8,314 J/(mol.K))

Symboles grecs TOUJOURS en lettres : alpha, beta, gamma, delta, epsilon,
theta, lambda, mu, nu, pi (≈ 3,14159), sigma, tau, phi, psi, omega

Unités en clair : Newton (N), Volt (V), Ampère (A), Ohm (Ω écrit Ohm),
Watt (W), Joule (J), Pascal (Pa), mol par litre (mol/L)

╔══════════════════════════════════════════════════════════════════╗
║  LISTE NOIRE — ABSOLUMENT INTERDIT                               ║
╚══════════════════════════════════════════════════════════════════╝

❌ LaTeX : $x$, \\frac{{}}{{}}, \\omega, \\text{{}}, \\left(, \\right), \\\\
❌ HTML  : <br>, <b>, <strong>, <p>, <div>, <span>
❌ Italique seul *texte* → remplacer par **gras**
❌ Exposants Unicode : CO₂, H₂O, x² → écrire "CO2", "H2O", "x au carré"
❌ Caractères grecs Unicode : ω, φ, λ, Δ → écrire en lettres
❌ Faux sous-titres "— Sous-section" → utiliser ### Sous-section
❌ Alignement par espaces multiples → utiliser un tableau markdown
❌ "[À compléter]", "[...]", "[insérer]", "[Auteur fictif]" → tout rédiger
❌ Commentaires de structure : "# ═══════" dans le texte visible

╔══════════════════════════════════════════════════════════════════╗
║  TABLEAU BILAN — CE QUE TU ÉCRIS → CE QUE WORD PRODUIT         ║
╚══════════════════════════════════════════════════════════════════╝

| Ce que tu écris              | Ce que Word affiche                         |
|------------------------------|---------------------------------------------|
| # INTRODUCTION               | Titre 1 Arial 16pt bleu foncé gras          |
| ## I. PREMIÈRE PARTIE        | Titre 2 Arial 14pt bleu gras                |
| ### 1.1 Sous-partie          | Titre 3 Arial 12pt gras                     |
| #### Détail                  | Titre 4 Arial 11pt gras italique            |
| **terme**                    | Gras Arial 11pt dans le paragraphe          |
| ════════════════              | Ligne épaisse bleue de séparation           |
| ────────────────              | Ligne fine grise de séparation              |
| ---SAUT_DE_PAGE---           | Vrai saut de page Word (nouvelle feuille)   |
| Tableau markdown             | Tableau Word formaté bleu/blanc/gris        |
| - item                       | Puce Word List Bullet                       |
| 1. item                      | Numérotation Word List Number               |
| Texte ordinaire              | Paragraphe Arial 11pt Normal                |
| ligne vide                   | Espacement naturel entre paragraphes        |
"""


def generer_avec_gemini(service, description, client_nom):
    try:
        import urllib.request as _ur
        import urllib.error

        api_key = st.secrets["GEMINI_API_KEY"]

        # ================================================================
        # PROMPT — EXPOSÉ SCOLAIRE
        # ================================================================
        if "Exposé" in service:
            prompt = f"""Tu es un expert académique de haut niveau ET un maître absolu de la génération de documents Word professionnels pour le système éducatif ivoirien et africain francophone.
Tu as été formé sur des milliers d'exposés scolaires primés et tu maîtrises parfaitement chaque aspect : typographie, structure, rhétorique académique, contextualisation culturelle et rendu Word via python-docx.

╔══════════════════════════════════════════════════════════════════╗
║     ENCYCLOPÉDIE EXPERTE — GÉNÉRATION DOCUMENT WORD NOVA AI     ║
╚══════════════════════════════════════════════════════════════════╝

{SECTION_MOTEUR_NOVA}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — ART DE LA RÉDACTION ACADÉMIQUE — RHÉTORIQUE ET STYLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ARCHITECTURE D'UN PARAGRAPHE PARFAIT — MODÈLE PEEL :
1. POINT (topic sentence) : "La Côte d'Ivoire occupe une position dominante dans l'économie mondiale du cacao."
2. EXPLICATION : développe le point, définit les termes en **gras**, explique les mécanismes
3. EXEMPLE IVOIRIEN/AFRICAIN : fait précis, chiffre sourcé, événement daté, citation
4. LIEN (transition) : "Cette réalité économique nous conduit naturellement à examiner..."
→ Minimum 8 lignes par paragraphe, 3 paragraphes minimum par sous-partie

CONNECTEURS LOGIQUES — VARIER OBLIGATOIREMENT (jamais répéter deux fois de suite) :

INTRODUIRE : "Il convient tout d'abord de souligner", "Force est de constater que", "Il importe de noter",
"À ce titre,", "Dans cette perspective,", "En premier lieu,"

DÉVELOPPER : "En effet,", "De surcroît,", "Par ailleurs,", "Qui plus est,", "Il convient également",
"À cet égard,", "Dans ce sens,", "En outre,"

ILLUSTRER : "Ainsi,", "C'est notamment le cas de", "À titre illustratif,", "Par exemple,",
"On peut citer à cet effet", "L'exemple ivoirien est à ce titre éloquent :",
"Comme en témoigne", "À titre d'exemple concret,"

OPPOSER : "Cependant,", "Néanmoins,", "Toutefois,", "En revanche,", "Or,",
"Il convient de relativiser", "Malgré tout,"

CONCLURE/TRANSITER : "En définitive,", "Au regard de ces éléments,",
"C'est dans cette logique que", "Ces constats nous amènent à examiner",
"Ainsi avons-nous établi que"

TYPES DE PLANS À CHOISIR SELON LE SUJET :
- THÉMATIQUE : I (Nature/Définition) → II (Causes/Mécanismes) → III (Effets/Solutions)
- DIALECTIQUE : I (Thèse : position dominante) → II (Antithèse : limites/critiques) → III (Synthèse/Dépassement)
- CHRONOLOGIQUE : I (Passé/Origines) → II (Présent/État actuel) → III (Avenir/Perspectives)
- ANALYTIQUE : I (Dimension économique) → II (Dimension sociale/culturelle) → III (Dimension politique/environnementale)

CONSTRUCTION D'UNE PROBLÉMATIQUE DE QUALITÉ :
- "Dans quelle mesure [sujet] contribue-t-il à [enjeu pour CI/Afrique] ?"
- "Comment [phénomène] se manifeste-t-il en Côte d'Ivoire et quels en sont les impacts ?"
- "En quoi [sujet] représente-t-il à la fois [avantage] et [défi] pour [acteurs] ?"
- "Si [thèse commune], dans quelle mesure peut-on affirmer que [antithèse nuancée] ?"

CITATIONS ET RÉFÉRENCES — FORMAT ACADÉMIQUE RIGOUREUX :
- Citation directe : « La forêt tropicale est le poumon de la planète. » (FAO, 2022, p. 12)
- Citation courte intégrée : Selon KOUROUMA (1970), « les soleils des indépendances » symbolisent...
- Paraphrase : D'après les travaux de TADJO (2004), la mémoire collective africaine se construit...
- Source institutionnelle : Le Ministère de l'Agriculture (2023) indique que la production cacaoyère...
- Statistique sourcée : Selon la FAO (2023), la Côte d'Ivoire produit **2,2 millions de tonnes** de cacao...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — SYSTÈME SCOLAIRE IVOIRIEN COMPLET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRIMAIRE (CP1, CP2, CE1, CE2, CM1, CM2) — Examen : CEPE (fin CM2) :
- Vocabulaire simple, phrases max 15 mots, exemples de vie quotidienne ivoirienne
- 1 à 2 pages — structure : Intro courte / Corps 2-3 paragraphes / Conclusion

COLLÈGE 1er CYCLE (6ème, 5ème, 4ème, 3ème) — Examen : BEPC :
- Vocabulaire courant, termes disciplinaires définis en **gras**
- 2 à 4 pages — 2 grandes parties + 2 sous-parties chacune
- Auteurs : Bernard Dadié, Camara Laye, Ahmadou Kourouma, Mongo Beti, Ferdinand Oyono

LYCÉE 2nd CYCLE (2nde, 1ère, Terminale) — Examen : BAC ivoirien :
- A1 (Lettres-Philo) : style littéraire, rhétorique, auteurs africains
- A2 (Lettres-SH) : approche socioéconomique, EDHC
- B (Économie) : chiffres, tableaux obligatoires, gestion d'entreprise
- C (Maths-PC) : rigueur scientifique maximale, formules en texte clair
- D (Maths-SVT) : biologie, écologie, médecine tropicale
- E (Maths-Techno) : ingénierie appliquée
- 4 à 7 pages — 3 grandes parties + 2 à 3 sous-parties par partie

UNIVERSITÉ (L1 à Doctorat) — Système LMD :
- L1-L3 : Introduction aux disciplines, revue de littérature, méthodologie de base
- M1-M2 : Cadre théorique, hypothèses, méthodologie rigoureuse
- Doctorat : Contribution originale, état de l'art exhaustif
- Institutions : UFHB Cocody, UAO Bouaké, UJLOG Daloa, INP-HB Yamoussoukro, ESATIC
- 8 à 20 pages selon niveau

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — BASE DE CONNAISSANCES IVOIRIENNE ET AFRICAINE ENRICHIE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GÉOGRAPHIE : 322 463 km², ~28M habitants (2024), cap. politique Yamoussoukro, cap. économique Abidjan
Villes : Bouaké, Daloa, Korhogo, San-Pédro, Man, Odienné, Abengourou, Gagnoa
Fleuves : Comoé (1160km), Bandama (960km), Sassandra (650km), Cavally, Bia
Lacs : Kossou (1700km², 3e lac artificiel Afrique), Buyo, Taabo, Ayamé
Relief : Monts Nimba (1752m, UNESCO), Monts Toura, plateau central, plaine côtière
Végétation : forêt dense humide (Sud, 30% territoire), savane arbustive (Centre-Nord)
Sites UNESCO : Forêt de Taï, Parc de la Comoé, Monts Nimba

HISTOIRE : Indépendance 7 août 1960 | Félix Houphouët-Boigny (1960-1993, père fondateur)
"Miracle ivoirien" (1960-1980), crise 2002 (rébellion Nord-Sud), crise 2010-2011 (post-électorale)
Alassane Ouattara (2011-présent) | Plan National de Développement (PND 2021-2025)
Résistance : Samory Touré (1898) | Colonisation française (1843-1960)

ÉCONOMIE : PIB ~70Md USD (2023) | Croissance ~6-7%/an | Émergence visée 2030
Cacao : 1er mondial (45% production, 2,2M tonnes/an) | Café : 3e africain
Anacarde : 1er africain (800 000 t/an) | Hévéa, palmier à huile, coton, banane, ananas
Port d'Abidjan : 1er conteneurs Afrique de l'Ouest, >30M tonnes/an
Port San-Pédro : 2e port cacaoyer mondial
Barrages : Soubré (275MW, 2017), Kossou (174MW, 1972), Buyo (165MW, 1980), Taabo, Ayamé
Monnaie : FCFA (XOF) | UEMOA, CEDEAO, UA

CULTURE : ~60 ethnies | Akan (Baoulé 23%, Agni), Krou (Bété, Dida), Mandé (Malinké, Dioula), Gur (Sénoufo, Lobi)
Musique : coupé-décalé (DJ Arafat, Magic System), zouglou, afrobeats
Gastronomie : attiéké, kedjenou, foutou, aloco, placali, garba, graine, bangui

LITTÉRATURE AFRICAINE FRANCOPHONE :
Ivoiriens : DADIÉ Bernard (Climbié 1956, Un Nègre à Paris 1959), KOUROUMA Ahmadou (Les Soleils des Indépendances 1968, Monnè 1990), TADJO Véronique (Reine Pokou 2004), ADIAFFI Jean-Marie (La Carte d'identité 1980)
Africains : LAYE Camara (L'Enfant Noir 1953), BETI Mongo (Mission Terminée 1957), OYONO Ferdinand (Une Vie de Boy 1956), SENGHOR Léopold Sédar (négritude), SEMBÈNE Ousmane (Les Bouts de Bois de Dieu 1960), ACHEBE Chinua (Things Fall Apart 1958)

SCIENCES ET ENVIRONNEMENT :
Biodiversité : 150+ espèces mammifères, 700+ oiseaux, hippopotame pygmée, éléphant de forêt, chimpanzé de Taï
Déforestation : 16M ha en 1900 → 3,4M ha aujourd'hui (perte 79% couverture forestière)
Maladies : paludisme (Plasmodium falciparum, 1re cause mortalité CI), tuberculose, VIH/SIDA
Forêt de Taï : 536 000 ha, classée UNESCO, chimpanzés étudiés par primatologues

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — LES 10 RÈGLES ABSOLUES DE LA GÉNÉRATION NOVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RÈGLE 1 — COMPLÉTUDE TOTALE : Zéro "[à compléter]", "[...]", "[insérer]" → TOUT rédigé intégralement
RÈGLE 2 — LONGUEUR SUBSTANTIELLE : Minimum 4 pages réelles — viser 6 à 10 pages selon niveau
RÈGLE 3 — QUALITÉ LINGUISTIQUE : Orthographe irréprochable, style académique soutenu
RÈGLE 4 — CONTEXTUALISATION : Min 3 exemples ivoiriens/africains concrets ET chiffrés par grande partie
RÈGLE 5 — ZÉRO LaTeX : Toutes formules en texte clair (voir Section 0)
RÈGLE 6 — PAGINATION CORRECTE : Page de garde seule → ---SAUT_DE_PAGE--- → Sommaire seul → ---SAUT_DE_PAGE--- → flux continu
RÈGLE 7 — ADAPTATION NIVEAU : Vocabulaire + profondeur + longueur adaptés au niveau détecté
RÈGLE 8 — PROSE DANS LE DÉVELOPPEMENT : Corps = paragraphes continus, jamais de listes
RÈGLE 9 — DONNÉES PRÉCISES ET SOURCÉES : Chiffres réels, dates précises, institutions réelles
RÈGLE 10 — VRAIS AUTEURS ET ŒUVRES : Citer de vraies œuvres d'auteurs réels — jamais fictifs

=== MISSION ===
Rédige un exposé scolaire COMPLET, STRUCTURÉ, PROFESSIONNEL et ENCYCLOPÉDIQUE :
{description}

=== STRUCTURE OBLIGATOIRE DU DOCUMENT ===

**[NOM COMPLET DE L'ÉTABLISSEMENT EN MAJUSCULES]**
[Ville], Côte d'Ivoire
Année scolaire : 2025 - 2026

────────────────────────────────────────────────────────

EXPOSÉ DE [MATIÈRE EN MAJUSCULES]

**[TITRE COMPLET EN MAJUSCULES]**

────────────────────────────────────────────────────────

**Matière :**                    [Matière complète]
**Niveau / Série :**             [Niveau exact]
**Présenté par :**               [Noms complets]
**Sous la direction de :**       [Titre + Nom du professeur]
**Date de présentation :**       [Date complète]
**Année scolaire :**             2025 - 2026

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

# SOMMAIRE

────────────────────────────────────────────────────────

Introduction ............................................................. p. 3

**I. [Titre accrocheur de la 1re grande partie]** ....................... p. 4
   1.1 [Titre 1re sous-partie] ........................................... p. 4
   1.2 [Titre 2e sous-partie] ............................................ p. 5

**II. [Titre accrocheur de la 2e grande partie]** ........................ p. 6
   2.1 [Titre 1re sous-partie] ........................................... p. 6
   2.2 [Titre 2e sous-partie] ............................................ p. 7

**III. [Titre de la 3e grande partie — lycée/université]** ............... p. 8
   3.1 [Titre sous-partie] ............................................... p. 8
   3.2 [Titre sous-partie] ............................................... p. 9

Conclusion ............................................................... p. 10
Bibliographie ............................................................ p. 11

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

# INTRODUCTION

────────────────────────────────────────────────────────

[ACCROCHE — min 6 lignes : fait saisissant, statistique sourcée ou citation d'auteur africain]

[CONTEXTUALISATION — min 5 lignes : contexte historique/géographique/scientifique]

[PROBLÉMATIQUE : "Ainsi, nous pouvons nous demander : [question centrale bien formulée] ?"]

[ANNONCE DU PLAN : "Pour répondre à cette problématique, nous étudierons dans un premier temps [I], puis dans un deuxième temps [II], et enfin [III]."]

════════════════════════════════════════════════════════

## I. [TITRE 1re GRANDE PARTIE EN MAJUSCULES]

════════════════════════════════════════════════════════

### 1.1 [Titre descriptif de la 1re sous-partie]

────────────────────────────────────────────────────────

[PARAGRAPHE 1 — 8 à 10 lignes : topic sentence + développement PEEL + exemple ivoirien chiffré]

[PARAGRAPHE 2 — 8 à 10 lignes : approfondissement + angle différent + connecteurs variés]

[SI PERTINENT — Tableau de données :
**Tableau 1 : [Titre précis]**
| Indicateur | Côte d'Ivoire | Afrique de l'Ouest | Monde |
|------------|--------------|---------------------|-------|
| [Donnée]   | [Valeur]     | [Valeur]            | [Valeur] |
*Source : [Institution réelle, Année]*]

[PARAGRAPHE 3 — synthèse 1.1 + transition vers 1.2]

────────────────────────────────────────────────────────

### 1.2 [Titre descriptif de la 2e sous-partie]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Dernier paragraphe : transition vers Partie II.]

════════════════════════════════════════════════════════

## II. [TITRE 2e GRANDE PARTIE EN MAJUSCULES]

════════════════════════════════════════════════════════

### 2.1 [Titre précis]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Analyse progresse depuis Partie I.]

────────────────────────────────────────────────────────

### 2.2 [Titre précis]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Transition vers Partie III ou Conclusion.]

════════════════════════════════════════════════════════

## III. [TITRE 3e GRANDE PARTIE — LYCÉE ET UNIVERSITÉ UNIQUEMENT]

════════════════════════════════════════════════════════

### 3.1 [Titre précis]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Dimension prospective et enjeux futurs pour CI et Afrique.]

────────────────────────────────────────────────────────

### 3.2 [Titre précis]

────────────────────────────────────────────────────────

[3 paragraphes. Dernier : phrase conclusive forte ouvrant sur la Conclusion.]

════════════════════════════════════════════════════════

# CONCLUSION

────────────────────────────────────────────────────────

[SYNTHÈSE — min 7 lignes : résume chaque grande partie en 1-2 phrases fortes. Reformule sans répéter.]

[RÉPONSE À LA PROBLÉMATIQUE — min 5 lignes : répond clairement et avec nuance à la question de l'intro.]

[OUVERTURE — min 4 lignes : enjeu futur pour CI/Afrique, lien autre domaine, question nouvelle.]

────────────────────────────────────────────────────────

# BIBLIOGRAPHIE

────────────────────────────────────────────────────────

**Manuels scolaires et ouvrages pédagogiques :**
- MINISTÈRE ÉDUCATION NATIONALE CI, *[Titre manuel officiel]*, CEDA/NEI, Abidjan, 2022
- [AUTEUR NOM Prénom], *[Titre réel du manuel]*, [Éditeur réel], [Ville], [Année]

**Ouvrages de référence :**
- [AUTEUR NOM Prénom], *[Titre réel de l'ouvrage]*, [Maison d'édition réelle], [Année]

**Littérature africaine et ivoirienne :**
- DADIÉ Bernard, *Climbié*, Présence Africaine, Paris, 1956
- KOUROUMA Ahmadou, *Les Soleils des Indépendances*, Seuil, Paris, 1970

**Sources institutionnelles :**
- FAO, *[Titre du rapport pertinent]*, Rome, [Année]
- INS-CI, *Annuaire statistique [Année]*, Abidjan

**Ressources numériques :**
- [Organisation], *[Titre page]*, [En ligne], URL : www.[site-réel].org, consulté le [date]

────────────────────────────────────────────────────────

Rédige maintenant l'exposé COMPLET en français avec la plus grande rigueur académique. TOUT doit être rédigé intégralement avec de vrais contenus enrichis — aucun "[à compléter]", aucune zone vide."""


        # ================================================================
        # PROMPT — SUJETS & EXAMENS
        # ================================================================
        elif "Examens" in service or "Sujets" in service:
            prompt = f"""Tu es un professeur expert, concepteur officiel de sujets d'examens ET maître de la génération de documents Word professionnels pour le système scolaire ivoirien et africain francophone.

╔══════════════════════════════════════════════════════════════════╗
║   ENCYCLOPÉDIE EXPERTE — GÉNÉRATION SUJETS D'EXAMENS NOVA AI   ║
╚══════════════════════════════════════════════════════════════════╝

{SECTION_MOTEUR_NOVA}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — TOUS LES FORMATS D'EXERCICES AVEC EXEMPLES COMPLETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORMAT 1 — QCM (QUESTIONS À CHOIX MULTIPLES) :
**Consigne :** Cochez la lettre correspondant à la SEULE bonne réponse par question.

**Question 1** (1 point)
Quelle est la capitale politique de la Côte d'Ivoire ?
□ **A)** Abidjan
□ **B)** Bouaké
□ **C)** Yamoussoukro
□ **D)** San-Pédro

RÈGLES QCM :
- Chaque distractor doit être PLAUSIBLE et de longueur similaire à la bonne réponse
- La bonne réponse doit varier de position (A, B, C, D)
- Les distractors doivent tester de vraies erreurs courantes des élèves

FORMAT 2 — VRAI OU FAUX :
**Consigne :** Indiquez si chaque affirmation est Vraie (V) ou Fausse (F). Justifiez OBLIGATOIREMENT les affirmations fausses.

| N° | Affirmations | V | F |
|----|-------------|---|---|
| 1 | La Côte d'Ivoire est le premier producteur mondial de cacao avec environ 45% de la production mondiale. | ☐ | ☐ |
| 2 | [Affirmation complète] | ☐ | ☐ |

FORMAT 3 — TEXTE LACUNAIRE :
**Consigne :** Complétez le texte avec les mots de la liste. Chaque mot utilisé UNE SEULE FOIS.
**Liste de mots :** [ mot1 — mot2 — mot3 — mot4 ]
La _______________ est le processus par lequel les végétaux utilisent la _______________ pour transformer le _______________ et l'eau en _______________.

FORMAT 4 — QUESTIONS OUVERTES :
**1.** Définissez **[terme]** et précisez [complément]. *(2 points)*
.......................................................................................
.......................................................................................

FORMAT 5 — ÉTUDE DE DOCUMENT :
[Texte COMPLET min 150 mots, ancré dans réalité ivoirienne — jamais "[insérer texte ici]"]
**Questions :**
**1.** [Question compréhension] *(1 point)*
**2.** [Question analyse] *(2 points)*

FORMAT 6 — PROBLÈME MATHS (contexte ivoirien OBLIGATOIRE) :
Marchés : Adjamé, Bouaké, Korhogo | Monnaie : FCFA uniquement
Agriculture : cacao (350 FCFA/kg achat, 1200 FCFA/kg export), anacarde (300 FCFA/kg)
Transport : gbaka Abidjan 200 FCFA, woro-woro 150 FCFA, SOTRA 100 FCFA
Électricité CIE : ~50-80 FCFA/kWh | 1 EUR = 655,957 FCFA (taux fixe)

FORMAT 7 — EXERCICE SCIENTIFIQUE SVT/PC :
**PARTIE A — Restitution de connaissances** (X points) : définitions, légendes de schéma
**PARTIE B — Exploitation de documents** (X points) : tableau de données + analyse + interprétation

FORMAT 8 — PRODUCTION ÉCRITE :
Sujet complet + consignes détaillées + grille d'évaluation en tableau

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — SYSTÈMES D'EXAMENS IVOIRIENS — PROGRAMMES OFFICIELS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CEPE (Certificat d'Études Primaires Élémentaires) — Fin CM2 :
- Matières : Français (dictée, rédaction, questions), Mathématiques, Sciences d'Éveil
- 3 à 4 exercices par matière, 2h d'épreuve, /20
- Thèmes CI : vie au village, marché, famille, école, animaux, plantes locales

BEPC (Brevet d'Études du Premier Cycle) — Fin 3ème :
- Français, Maths, PC, SVT, Histoire-Géo, Anglais
- Durée : 2h à 4h selon matière, /20

BAC IVOIRIEN — Terminale :
Série A1 (Lettres-Philo) : Français (dissertation, commentaire composé), Philo, Histoire-Géo
Série B (Économie-Gestion) : Économie, Comptabilité, Maths financières
Série C (Maths-PC) : Maths (4h), PC (4h), Philo — rigueur maximale
Série D (Maths-SVT) : Maths, SVT (biologie, géologie), médecine tropicale

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — DONNÉES IVOIRIENNES POUR LA CONTEXTUALISATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATHS CONTEXTUALISÉS :
- Cacao : 350 FCFA/kg achat, 1 200 FCFA/kg export, 2,2 millions tonnes/an
- Anacarde : 250-400 FCFA/kg, 800 000 t/an, région Korhogo/Odienné
- Transport : gbaka 200 FCFA, woro-woro 150 FCFA, bus SOTRA 100 FCFA
- Électricité CIE : tarif social ~50 FCFA/kWh, tarif normal ~80 FCFA/kWh
- 1 USD ≈ 600 FCFA, 1 EUR = 655,957 FCFA (taux fixe)
- Prix riz local : 400 FCFA/kg, attiéké : 200 FCFA/portion, garba : 300-500 FCFA

SCIENCES CONTEXTUALISÉS :
- Barrage Soubré : 275 MW, inauguré 2017, fleuve Sassandra
- Barrage Kossou : 174 MW, inauguré 1972, fleuve Bandama, lac 1700 km²
- Température Abidjan : 26°C moyenne, précipitations 1800 mm/an
- Paludisme CI : ~3 millions cas/an, Plasmodium falciparum, traitement Coartem
- Forêt de Taï : 536 000 ha, UNESCO, chimpanzés de Taï

HISTOIRE-GÉO CONTEXTUALISÉS :
- CI : 322 463 km², 26 régions, 14 districts depuis 2011
- Frontières : Liberia (Ouest), Guinée (Nord-Ouest), Mali (Nord), Burkina Faso (Nord-Est), Ghana (Est)
- Dates clés : 1843 (protectorat), 1893 (colonie), 1960 (indépendance), 1990 (multipartisme)
- UEMOA : 8 pays | CEDEAO : 15 pays d'Afrique de l'Ouest, création 1975

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — RÈGLES ABSOLUES DE CONCEPTION DES SUJETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RÈGLE 1 — COMPLÉTUDE : Jamais "[À compléter]", "[insérer question]" → TOUT rédigé intégralement
RÈGLE 2 — QUESTIONS RÉELLES : Tous QCM complets, tous textes lacunaires entièrement rédigés
RÈGLE 3 — CONTEXTE CI : Problèmes maths en FCFA, sciences avec données CI (barrages, maladies)
RÈGLE 4 — ZÉRO LaTeX : "F = m x a" jamais "$F = ma$"
RÈGLE 5 — BARÈME COHÉRENT : Total toujours = 20 points, répartition logique
RÈGLE 6 — ADAPTATION NIVEAU : CEPE/BEPC/BAC série précise — adapter strictement
RÈGLE 7 — PAGINATION : En-tête officiel → ---SAUT_DE_PAGE--- → exercices en flux continu
RÈGLE 8 — CORRIGÉ : Inclure UNIQUEMENT si "corrigé" ou "correction" mentionné dans la demande

=== MISSION ===
Crée un sujet d'examen COMPLET, PARFAITEMENT STRUCTURÉ et TOTALEMENT RÉDIGÉ :
{description}

=== STRUCTURE OBLIGATOIRE ===

**RÉPUBLIQUE DE CÔTE D'IVOIRE**
Union — Discipline — Travail

────────────────────────────────────────────────────────

**Établissement :** [Nom complet de l'établissement]
**Année scolaire :** 2025 — 2026
**Matière :** [Matière complète]
**Niveau / Série :** [ex: Terminale D]
**Type d'épreuve :** [Devoir Surveillé n°1 / Examen Blanc / BAC Blanc...]
**Durée :** [ex: 3 heures]
**Coefficient :** [ex: 5]
**Barème total :** /20

────────────────────────────────────────────────────────

**Nom et Prénoms :** ..............................................
**Numéro de table :** .............. **Salle :** .................
**Signature du surveillant :** ...................................

────────────────────────────────────────────────────────

**CONSIGNES GÉNÉRALES :**
- Lisez attentivement l'intégralité du sujet avant de commencer
- Répondez sur la copie dans l'ordre des questions ou en indiquant le numéro
- Les réponses doivent être rédigées en français correct et lisible
- Les téléphones portables et documents sont strictement interdits
- Toute tentative de fraude entraîne l'exclusion immédiate
- La présentation, la propreté et la lisibilité sont prises en compte

────────────────────────────────────────────────────────

**Tableau 1 : Barème de notation**
| Exercice | Intitulé | Points |
|----------|----------|--------|
| Exercice 1 | [Intitulé complet] | /[X] |
| Exercice 2 | [Intitulé complet] | /[X] |
| Exercice 3 | [Intitulé complet] | /[X] |
| **TOTAL** | | **/20** |

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

[RÉDIGER TOUS LES EXERCICES ICI — formats choisis selon le niveau et la matière]
[Séparer chaque exercice avec ════════════════════════════════════════════════════════]
[Questions séparées par ────────────────────────────────────────────────────────────]

[CORRIGÉ COMPLET ICI — UNIQUEMENT SI "corrigé" ou "correction" mentionné dans la demande]

Rédige le sujet d'examen COMPLET en français. Tout intégralement rédigé. Aucune zone vide. Contexte ivoirien dans CHAQUE exercice."""

        elif "CV" in service:
            prompt = f"""Tu es un expert RH et recrutement. Crée un CV et une lettre de motivation professionnels basés sur :

{description}

# CURRICULUM VITAE

## INFORMATIONS PERSONNELLES
## PROFIL / RÉSUMÉ PROFESSIONNEL
## EXPÉRIENCES PROFESSIONNELLES
## FORMATION & DIPLÔMES
## COMPÉTENCES TECHNIQUES
## COMPÉTENCES LINGUISTIQUES
## CENTRES D'INTÉRÊT

---

# LETTRE DE MOTIVATION

(Structure complète : accroche percutante, présentation, motivation, valeur ajoutée, conclusion)

Rédige en français, ton professionnel et percutant."""

        elif "Pack Office" in service:
            prompt = f"""Tu es un expert bureautique. Crée le contenu complet et professionnel pour :

{description}

Fournis un document structuré avec :
- Titres et sous-titres hiérarchisés
- Paragraphes complets et détaillés
- Tableaux si pertinent
- Recommandations de mise en forme

Rédige en français, format professionnel et exhaustif."""

        elif "Excel" in service or "Data" in service:
            prompt = f"""Tu es un expert Excel et Data Analytics. Crée une structure complète pour :

{description}

## FEUILLES À CRÉER
## STRUCTURE DES COLONNES PAR FEUILLE
## FORMULES EXCEL CLÉS
## DONNÉES D'EXEMPLE
## MISE EN FORME RECOMMANDÉE
## TABLEAU DE BORD

Rédige en français, sois très précis et technique."""

        else:
            prompt = f"""Tu es un expert professionnel. Réalise cette mission de façon complète et professionnelle :

{description}

Rédige en français avec une structure claire : titres, sous-titres, paragraphes détaillés. Sois exhaustif et professionnel."""

        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 8192
            }
        }).encode("utf-8")

        modeles = get_modeles_disponibles(api_key)
        if not modeles:
            return "❌ Aucun modèle Gemini disponible pour generateContent avec cette clé API."
        erreurs = []

        for modele in modeles:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{modele}:generateContent?key={api_key}"
                req = _ur.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with _ur.urlopen(req, timeout=60) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    texte = result["candidates"][0]["content"]["parts"][0]["text"]
                    return texte
            except urllib.error.HTTPError as e:
                try:
                    corps_erreur = e.read().decode("utf-8")
                    erreur_detail = json.loads(corps_erreur).get("error", {}).get("message", corps_erreur[:200])
                except:
                    erreur_detail = str(e)
                erreurs.append(f"{modele} → HTTP {e.code}: {erreur_detail}")
                if e.code in [429, 503]:
                    time.sleep(2)
                    continue
                return f"❌ Erreur Gemini ({modele}) HTTP {e.code} : {erreur_detail}"
            except Exception as e:
                erreurs.append(f"{modele} → {type(e).__name__}: {e}")
                continue

        detail = " | ".join(erreurs)
        return f"❌ Gemini indisponible. Détails : {detail}"

    except Exception as e:
        return f"❌ Erreur Gemini : {e}"


def creer_docx(contenu, service, client_nom):
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    import re

    doc = Document()

    for section in doc.sections:
        section.top_margin    = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)

    from docx.oxml import OxmlElement
    def set_cell_bg(cell, hex_color):
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), hex_color)
        tcPr.append(shd)

    from docx.shared import RGBColor as RC

    # ── EN-TÊTE NOVA uniquement pour services bureautiques (pas exposés/examens/CV)
    SERVICES_PROFESSIONNELS = ["Exposé", "Examens", "Sujets", "CV", "Lettre"]
    est_professionnel = any(kw in service for kw in SERVICES_PROFESSIONNELS)

    if not est_professionnel:
        p_titre = doc.add_paragraph()
        p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_t = p_titre.add_run(
            "⚡ NOVA AI  —  " + service.replace("📝","").replace("👔","")
            .replace("📊","").replace("⚙️","").replace("🎨","")
            .replace("📚","").replace("📄","").strip()
        )
        run_t.bold = True
        run_t.font.size = Pt(16)
        run_t.font.color.rgb = RC(0x1F, 0x4E, 0x79)
        run_t.font.name = "Arial"

        p_info = doc.add_paragraph()
        p_info.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run_i = p_info.add_run(
            f"Client : {client_nom}     |     Généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}"
        )
        run_i.font.size = Pt(10)
        run_i.font.color.rgb = RC(0x7F, 0x7F, 0x7F)
        run_i.font.name = "Arial"
        run_i.italic = True

        p_sep = doc.add_paragraph()
        pPr = p_sep._p.get_or_add_pPr()
        pBdr = OxmlElement("w:pBdr")
        bottom = OxmlElement("w:bottom")
        bottom.set(qn("w:val"), "single")
        bottom.set(qn("w:sz"), "6")
        bottom.set(qn("w:space"), "1")
        bottom.set(qn("w:color"), "1F4E79")
        pBdr.append(bottom)
        pPr.append(pBdr)
        doc.add_paragraph("")

    def add_formatted_para(doc, text, style_name="Normal", bold=False, size=11, color=None, align=None):
        p = doc.add_paragraph(style=style_name)
        if align:
            p.alignment = align
        parts = re.split(r"(\*\*[^*]+\*\*)", text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                run = p.add_run(part[2:-2])
                run.bold = True
            else:
                clean = part.replace("*", "").replace("`", "")
                run = p.add_run(clean)
                run.bold = bold
            run.font.name = "Arial"
            run.font.size = Pt(size)
            if color:
                run.font.color.rgb = RC(*color)
        return p

    import re as _re
    def nettoyer_latex(texte):
        texte = _re.sub(r"\$([^$]+)\$", lambda m: nettoyer_formule(m.group(1)), texte)
        return texte

    def nettoyer_formule(f):
        f = f.replace(r"\,", " ")
        f = f.replace(r"\text{", "").replace("}", "")
        f = f.replace(r"\frac{", "(").replace("}{", ")/(")
        f = f.replace(r"\sqrt{", "sqrt(")
        f = f.replace(r"\omega", "omega")
        f = f.replace(r"\varphi", "phi")
        f = f.replace(r"\pi", "pi")
        f = f.replace(r"\cdot", "x")
        f = f.replace(r"\times", "x")
        f = f.replace(r"\approx", "≈")
        f = f.replace(r"\left(", "(").replace(r"\right)", ")")
        f = f.replace("\\\\", "")
        f = f.replace("{", "").replace("}", "")
        f = f.strip()
        opens = f.count("(") - f.count(")")
        if opens > 0:
            f += ")" * opens
        return f

    contenu = nettoyer_latex(contenu)
    contenu = contenu.replace("\\,", " ").replace("\\text{", "").replace("\\", "")

    lignes = contenu.split("\n")
    i = 0
    while i < len(lignes):
        l = lignes[i].rstrip()

        # ── SAUT DE PAGE RÉEL WORD ─────────────────────────────────
        if l.strip() == "---SAUT_DE_PAGE---":
            p_break = doc.add_paragraph()
            run_break = p_break.add_run()
            br = OxmlElement("w:br")
            br.set(qn("w:type"), "page")
            run_break._r.append(br)
            i += 1
            continue

        # ── LIGNES DE SÉPARATION ════ ET ──── ─────────────────────
        if l.strip().startswith("════") or l.strip().startswith("━━━━"):
            p_line = doc.add_paragraph()
            pPr2 = p_line._p.get_or_add_pPr()
            pBdr2 = OxmlElement("w:pBdr")
            bot2 = OxmlElement("w:bottom")
            bot2.set(qn("w:val"), "single")
            bot2.set(qn("w:sz"), "12")
            bot2.set(qn("w:space"), "1")
            bot2.set(qn("w:color"), "1F4E79")
            pBdr2.append(bot2)
            pPr2.append(pBdr2)
            i += 1
            continue

        if l.strip().startswith("────") or l.strip().startswith("----"):
            p_line = doc.add_paragraph()
            pPr2 = p_line._p.get_or_add_pPr()
            pBdr2 = OxmlElement("w:pBdr")
            bot2 = OxmlElement("w:bottom")
            bot2.set(qn("w:val"), "single")
            bot2.set(qn("w:sz"), "4")
            bot2.set(qn("w:space"), "1")
            bot2.set(qn("w:color"), "AAAAAA")
            pBdr2.append(bot2)
            pPr2.append(pBdr2)
            i += 1
            continue

        if l.strip() in ["---", "***", "___", "*"]:
            doc.add_paragraph("")
            i += 1
            continue

        if l.startswith("#### "):
            p = doc.add_heading(l[5:].strip(), level=4)
            i += 1
            continue
        if l.startswith("### "):
            p = doc.add_heading(l[4:].strip(), level=3)
            i += 1
            continue
        if l.startswith("## "):
            p = doc.add_heading(l[3:].strip(), level=2)
            i += 1
            continue
        if l.startswith("# "):
            if l.startswith("# ═") or l.startswith("# #") or l.startswith("# ─"):
                i += 1
                continue
            p = doc.add_heading(l[2:].strip(), level=1)
            i += 1
            continue

        if l.startswith("|") and l.endswith("|"):
            table_lines = []
            while i < len(lignes) and lignes[i].strip().startswith("|") and lignes[i].strip().endswith("|"):
                row = lignes[i].strip()
                if not re.match(r"^[\|\s\-:]+$", row):
                    cells = [c.strip() for c in row.strip("|").split("|")]
                    table_lines.append(cells)
                i += 1

            if table_lines:
                from docx.shared import Cm as DocxCm
                n_cols = max(len(r) for r in table_lines)
                col_widths_map = {
                    2: [3.0, 6.0],
                    3: [1.0, 7.5, 2.5],
                    4: [1.0, 5.0, 2.5, 2.5],
                    5: [0.8, 5.0, 1.5, 1.5, 1.2],
                }
                col_widths = col_widths_map.get(n_cols, [9.0/n_cols]*n_cols)
                table = doc.add_table(rows=0, cols=n_cols)
                table.style = "Table Grid"

                for r_idx, row_data in enumerate(table_lines):
                    row_obj = table.add_row()
                    is_header = (r_idx == 0)
                    from docx.oxml.ns import qn as _qn
                    from docx.oxml import OxmlElement as _OE
                    trPr = row_obj._tr.get_or_add_trPr()
                    trHeight = _OE("w:trHeight")
                    trHeight.set(_qn("w:val"), str(int((0.9 if is_header else 1.5) * 567)))
                    trHeight.set(_qn("w:hRule"), "exact")
                    trPr.append(trHeight)

                    for c_idx, cell_text in enumerate(row_data):
                        cell = row_obj.cells[c_idx]
                        if c_idx < len(col_widths):
                            cell.width = DocxCm(col_widths[c_idx])
                        tc = cell._tc
                        tcPr = tc.get_or_add_tcPr()
                        tcMar = _OE("w:tcMar")
                        for side in ["top","bottom","left","right"]:
                            m = _OE(f"w:{side}")
                            m.set(_qn("w:w"), "120")
                            m.set(_qn("w:type"), "dxa")
                            tcMar.append(m)
                        tcPr.append(tcMar)
                        if is_header:
                            shd = _OE("w:shd")
                            shd.set(_qn("w:val"), "clear")
                            shd.set(_qn("w:color"), "auto")
                            shd.set(_qn("w:fill"), "1F4E79")
                            tcPr.append(shd)
                        elif r_idx % 2 == 0:
                            shd = _OE("w:shd")
                            shd.set(_qn("w:val"), "clear")
                            shd.set(_qn("w:color"), "auto")
                            shd.set(_qn("w:fill"), "EEF3FA")
                            tcPr.append(shd)

                        para = cell.paragraphs[0]
                        para.alignment = WD_ALIGN_PARAGRAPH.CENTER if c_idx in [0, n_cols-1] else WD_ALIGN_PARAGRAPH.LEFT
                        para.paragraph_format.space_before = Pt(2)
                        para.paragraph_format.space_after = Pt(2)
                        run = para.add_run(cell_text)
                        run.font.name = "Arial"
                        run.font.size = Pt(10)
                        run.bold = is_header
                        if is_header:
                            run.font.color.rgb = RC(0xFF, 0xFF, 0xFF)

                doc.add_paragraph("")
            continue

        m_num = re.match(r"^(\d+)[.)]\s+(.*)", l)
        if m_num:
            p = doc.add_paragraph(style="List Number")
            parts = re.split(r"(\*\*[^*]+\*\*)", m_num.group(2))
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part[2:-2]); run.bold = True
                else:
                    run = p.add_run(part.replace("*","").replace("`",""))
            for run in p.runs:
                run.font.name = "Arial"; run.font.size = Pt(11)
            i += 1
            continue

        if re.match(r"^[\-\*\•]\s+", l):
            texte = re.sub(r"^[\-\*\•]\s+", "", l)
            p = doc.add_paragraph(style="List Bullet")
            parts = re.split(r"(\*\*[^*]+\*\*)", texte)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = p.add_run(part[2:-2]); run.bold = True
                else:
                    run = p.add_run(part.replace("*","").replace("`",""))
            for run in p.runs:
                run.font.name = "Arial"; run.font.size = Pt(11)
            i += 1
            continue

        if not l.strip():
            doc.add_paragraph("")
            i += 1
            continue

        if l.strip().startswith("**") and l.strip().endswith("**") and l.strip().count("**") == 2:
            texte = l.strip()[2:-2]
            p = doc.add_paragraph()
            run = p.add_run(texte)
            run.bold = True
            run.font.name = "Arial"
            run.font.size = Pt(12)
            run.font.color.rgb = RC(0x1F, 0x4E, 0x79)
            i += 1
            continue

        add_formatted_para(doc, l.strip())
        i += 1

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def creer_xlsx(description, client_nom):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    BLEU_FONCE = "1F4E79"
    BLEU_CLAIR = "BDD7EE"
    BLANC      = "FFFFFF"
    GRIS       = "F2F2F2"

    def hdr(cell, bg=BLEU_FONCE, fg=BLANC, bold=True, size=11):
        cell.font = Font(bold=bold, color=fg, name="Arial", size=size)
        cell.fill = PatternFill("solid", start_color=bg)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def brd(cell):
        s = Side(style="thin", color="CCCCCC")
        cell.border = Border(top=s, bottom=s, left=s, right=s)

    ws1 = wb.active
    ws1.title = "Saisie Dépenses"
    ws1.sheet_view.showGridLines = False

    ws1.merge_cells("A1:H1")
    t = ws1["A1"]
    t.value = f"SUIVI DES DÉPENSES — JANVIER 2026  |  {client_nom}"
    hdr(t, size=13); ws1.row_dimensions[1].height = 34

    ws1.merge_cells("A2:H2")
    ws1["A2"].value = f"Généré le {datetime.now().strftime('%d/%m/%Y')} — Nova AI"
    ws1["A2"].font = Font(italic=True, color="7F7F7F", name="Arial", size=10)
    ws1["A2"].alignment = Alignment(horizontal="center")

    cols   = ["N°","Date","Description","Catégorie","Bénéficiaire","Montant (FCFA)","Mode Paiement","Notes"]
    widths = [5, 13, 30, 18, 20, 18, 16, 25]
    for c,(h,w) in enumerate(zip(cols,widths),1):
        cell = ws1.cell(row=3,column=c,value=h); hdr(cell); brd(cell)
        ws1.column_dimensions[get_column_letter(c)].width = w
    ws1.row_dimensions[3].height = 26

    rows = [
        [1,"01/01/2026","Courses alimentaires","Alimentation","Supermarché",15000,"Espèces",""],
        [2,"03/01/2026","Transport taxi","Transport","Taxi",5000,"Mobile Money",""],
        [3,"05/01/2026","Facture électricité","Factures","CIE",22000,"Virement","Janvier 2026"],
        [4,"07/01/2026","Restaurant déjeuner","Restauration","Maquis du coin",7500,"Espèces",""],
        [5,"10/01/2026","Recharge téléphone","Communication","Orange CI",3000,"Mobile Money",""],
        [6,"12/01/2026","Médicaments pharmacie","Santé","Pharmacie Plus",12000,"Espèces",""],
        [7,"15/01/2026","Internet mensuel","Communication","MTN CI",8000,"Virement","Abonnement mensuel"],
        [8,"18/01/2026","Vêtements enfants","Habillement","Marché",20000,"Espèces",""],
        [9,"22/01/2026","Loyer","Logement","Propriétaire",150000,"Virement","Loyer janvier"],
        [10,"28/01/2026","Courses alimentaires","Alimentation","Marché",18000,"Espèces","Fin de mois"],
    ]
    for r,row in enumerate(rows,4):
        bg = GRIS if r%2==0 else BLANC
        for c,val in enumerate(row,1):
            cell = ws1.cell(row=r,column=c,value=val)
            cell.font = Font(name="Arial",size=10,
                             bold=(c==6), color=("1F4E79" if c==6 else "000000"))
            cell.fill = PatternFill("solid",start_color=bg)
            cell.alignment = Alignment(vertical="center",
                                       horizontal="center" if c in [1,2,6,7] else "left")
            brd(cell)
            if c==6: cell.number_format = '#,##0 "FCFA"'

    tr = len(rows)+4
    ws1.merge_cells(f"A{tr}:E{tr}")
    hdr(ws1[f"A{tr}"],size=11); ws1[f"A{tr}"].value="TOTAL JANVIER"; brd(ws1[f"A{tr}"])
    tot = ws1[f"F{tr}"]
    tot.value=f"=SUM(F4:F{tr-1})"
    tot.number_format='#,##0 "FCFA"'; hdr(tot); brd(tot)
    ws1.row_dimensions[tr].height=28

    ws2 = wb.create_sheet("Catégories")
    ws2.sheet_view.showGridLines = False
    ws2.merge_cells("A1:D1"); t2=ws2["A1"]; t2.value="CATÉGORIES DE DÉPENSES"; hdr(t2,size=13); ws2.row_dimensions[1].height=32

    h2=["Catégorie","Budget Prévu (FCFA)","Total Réel (FCFA)","Écart (FCFA)"]
    for c,(h,w) in enumerate(zip(h2,[25,22,22,22]),1):
        cell=ws2.cell(row=2,column=c,value=h); hdr(cell,bg="2E75B6"); brd(cell)
        ws2.column_dimensions[get_column_letter(c)].width=w

    cats=[("Alimentation",50000),("Transport",20000),("Factures",30000),
          ("Restauration",15000),("Communication",15000),("Santé",20000),
          ("Habillement",25000),("Logement",150000),("Loisirs",10000),("Autres",10000)]
    for r,(cat,budget) in enumerate(cats,3):
        bg = BLEU_CLAIR if r%2==0 else BLANC
        c1=ws2.cell(row=r,column=1,value=cat); c1.font=Font(name="Arial",size=10,bold=True)
        c1.fill=PatternFill("solid",start_color=bg); c1.alignment=Alignment(vertical="center"); brd(c1)
        c2=ws2.cell(row=r,column=2,value=budget); c2.number_format='#,##0 "FCFA"'
        c2.font=Font(name="Arial",size=10,color="0000FF")
        c2.fill=PatternFill("solid",start_color=bg); c2.alignment=Alignment(horizontal="center"); brd(c2)
        c3=ws2.cell(row=r,column=3,value=f"=SUMIF('Saisie Dépenses'!D:D,A{r},'Saisie Dépenses'!F:F)")
        c3.number_format='#,##0 "FCFA"'; c3.fill=PatternFill("solid",start_color=bg)
        c3.alignment=Alignment(horizontal="center"); brd(c3); c3.font=Font(name="Arial",size=10)
        c4=ws2.cell(row=r,column=4,value=f"=B{r}-C{r}"); c4.number_format='#,##0 "FCFA"'
        c4.fill=PatternFill("solid",start_color=bg); c4.alignment=Alignment(horizontal="center"); brd(c4)
        c4.font=Font(name="Arial",size=10)

    tr2=len(cats)+3
    ws2.cell(row=tr2,column=1,value="TOTAL")
    hdr(ws2.cell(row=tr2,column=1)); brd(ws2.cell(row=tr2,column=1))
    for col in [2,3,4]:
        cell=ws2.cell(row=tr2,column=col,value=f"=SUM({get_column_letter(col)}3:{get_column_letter(col)}{tr2-1})")
        cell.number_format='#,##0 "FCFA"'; hdr(cell); brd(cell)

    ws3 = wb.create_sheet("Tableau de Bord")
    ws3.sheet_view.showGridLines = False
    ws3.merge_cells("A1:E1"); t3=ws3["A1"]; t3.value="TABLEAU DE BORD — JANVIER 2026"
    hdr(t3,size=13); ws3.row_dimensions[1].height=34

    ws3.column_dimensions["A"].width=26; ws3.column_dimensions["B"].width=22
    ws3.column_dimensions["C"].width=4;  ws3.column_dimensions["D"].width=26
    ws3.column_dimensions["E"].width=22

    kpis=[
        ("Total Dépenses Janvier","='Saisie Dépenses'!F14",BLEU_FONCE),
        ("Budget Total Prévu",    "='Catégories'!B13",    "2E75B6"),
        ("Écart Budget/Réel",     "='Catégories'!D13",    "375623"),
        ("Nb de Transactions",    "=COUNTA('Saisie Dépenses'!A4:A1000)-1","7F7F7F"),
    ]
    positions=[(3,1,2),(3,4,5),(6,1,2),(6,4,5)]
    for (row,cl,cv),(label,formula,bg) in zip(positions,kpis):
        lc=ws3.cell(row=row,column=cl,value=label)
        lc.font=Font(bold=True,name="Arial",size=11,color=BLANC)
        lc.fill=PatternFill("solid",start_color=bg)
        lc.alignment=Alignment(horizontal="center",vertical="center"); ws3.row_dimensions[row].height=32
        vc=ws3.cell(row=row,column=cv,value=formula)
        vc.number_format='#,##0 "FCFA"' if "Nb" not in label else "0"
        vc.font=Font(bold=True,name="Arial",size=13,color=BLANC)
        vc.fill=PatternFill("solid",start_color=bg)
        vc.alignment=Alignment(horizontal="center",vertical="center")

    ws3.merge_cells("A9:E9"); rh=ws3["A9"]
    rh.value="RÉCAPITULATIF PAR CATÉGORIE"; hdr(rh,bg="2E75B6",size=12); ws3.row_dimensions[9].height=28

    rh2=["Catégorie","Budget (FCFA)","Réel (FCFA)","Écart (FCFA)","% Consommé"]
    for c,h in enumerate(rh2,1):
        cell=ws3.cell(row=10,column=c,value=h); hdr(cell); brd(cell)
        ws3.column_dimensions[get_column_letter(c)].width=[26,18,18,18,14][c-1]

    for r,cat in enumerate([c for c,_ in cats],11):
        cat_row=r-8
        bg=BLEU_CLAIR if r%2==0 else BLANC
        c1=ws3.cell(row=r,column=1,value=cat)
        c1.font=Font(name="Arial",size=10,bold=True)
        c1.fill=PatternFill("solid",start_color=bg); c1.alignment=Alignment(vertical="center"); brd(c1)
        for col,formula in enumerate([
            f"='Catégories'!B{cat_row+2}",
            f"='Catégories'!C{cat_row+2}",
            f"='Catégories'!D{cat_row+2}",
            f"=IF(B{r}=0,0,C{r}/B{r})",
        ],2):
            cell=ws3.cell(row=r,column=col,value=formula)
            cell.font=Font(name="Arial",size=10)
            cell.fill=PatternFill("solid",start_color=bg)
            cell.alignment=Alignment(horizontal="center"); brd(cell)
            cell.number_format='#,##0 "FCFA"' if col<6 else "0.0%"

    buf=BytesIO(); wb.save(buf); buf.seek(0)
    return buf


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
if "show_service_warning" not in st.session_state:
    st.session_state["show_service_warning"] = False
if "last_service_seen" not in st.session_state:
    st.session_state["last_service_seen"] = None
if "warning_triggered" not in st.session_state:
    st.session_state["warning_triggered"] = False
if "intro_played" not in st.session_state:
    st.session_state["intro_played"] = False
if "gemini_results" not in st.session_state:
    st.session_state["gemini_results"] = {}
if "premium_livrable" not in st.session_state:
    st.session_state["premium_livrable"] = None

if st.session_state["current_user"] is None:
    stored_user = st.query_params.get("user_id")
    if stored_user and stored_user in st.session_state["db"]["users"]:
        st.session_state["current_user"] = stored_user
    else:
        components.html("""
            <script>
            var uid = localStorage.getItem('nova_user_id');
            if (uid) {
                var url = new URL(window.location.href);
                url.searchParams.set('user_id', uid);
                window.location.href = url.toString();
            }
            </script>
        """, height=0)

if st.session_state["current_user"]:
    uid_connecte = st.session_state["current_user"]
    components.html(f"""
        <script>
        localStorage.setItem('nova_user_id', '{uid_connecte}');
        </script>
    """, height=0)

def inject_custom_css():
    _user = st.session_state.get("current_user")
    _db   = st.session_state.get("db", {})
    _ud   = _db.get("users", {}).get(_user, {}) if _user else {}
    _premium = is_premium_actif(_ud)

    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { font-family: 'Poppins', sans-serif; }
        .stApp {
            background: #0f0c29;
            background: -webkit-linear-gradient(to right, #24243e, #302b63, #0f0c29);
            background: linear-gradient(to right, #24243e, #302b63, #0f0c29);
            color: #ffffff;
        }
        @keyframes glow-pulse {
            0% { filter: brightness(1) saturate(1); }
            50% { filter: brightness(1.8) saturate(1.5); }
            100% { filter: brightness(1) saturate(1); }
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
            font-size: 1.2rem !important;
            border: 1px solid transparent;
            padding: 0 25px;
        }
        .stTabs [data-baseweb="tab"]:nth-child(2) {
            border: 1px solid #2ecc71 !important;
            background-color: rgba(46, 204, 113, 0.1);
        }
        .stTabs [data-baseweb="tab"]:hover { background-color: rgba(0, 210, 255, 0.3); }
        .stTabs [aria-selected="true"] {
            background-color: rgba(0, 210, 255, 0.6) !important;
            border: 1px solid #00d2ff !important;
            box-shadow: 0 0 20px rgba(0, 210, 255, 0.4);
        }
        @keyframes border-rainbow {
            0% { border-color: #00d2ff; }
            50% { border-color: #FFD700; }
            100% { border-color: #00d2ff; }
        }
        .stTextInput label, .stSelectbox label, .stTextArea label {
            color: #00d2ff !important;
            font-weight: 600 !important;
            font-size: 1.1rem !important;
        }
        div[data-baseweb="input"], div[data-baseweb="select"] > div {
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
            width: 45px; height: 45px;
            filter: grayscale(0.5) opacity(0.7);
            transition: all 0.3s ease;
        }
        .logo-item:hover { filter: grayscale(0) opacity(1); transform: translateY(-5px) scale(1.1); }
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
        .premium-title { color: #FFD700 !important; font-size: 1.5rem; font-weight: 800; text-transform: uppercase; }
        .premium-desc { color: #ffffff !important; font-size: 1rem; margin-bottom: 20px; }
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
        }
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
        .info-card {
            background: rgba(0, 0, 0, 0.4) !important;
            border-left: 4px solid #00d2ff;
            padding: 15px;
            border-radius: 0 10px 10px 0;
            margin-bottom: 15px;
        }
        .info-title { color: #00d2ff !important; font-weight: bold; font-size: 1.1rem; display: block; margin-bottom: 8px; text-transform: uppercase; }
        .file-card {
            background: rgba(255, 255, 255, 0.08);
            border: 2px solid rgba(46, 204, 113, 0.5);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 15px;
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
        .support-btn:hover { background: #25D366; color: white !important; }
        .stProgress > div > div > div > div { background-image: linear-gradient(to right, #00d2ff , #3a7bd5); }
        .gemini-card {
            background: linear-gradient(135deg, rgba(0,210,255,0.08), rgba(58,123,213,0.12));
            border: 2px solid rgba(0,210,255,0.4);
            border-radius: 14px;
            padding: 16px 20px;
            margin: 12px 0;
        }
        .gemini-title { color: #00d2ff; font-weight: 800; font-size: 0.95rem; }
        .badge-premium {
            display: inline-flex; align-items: center; gap: 6px;
            background: linear-gradient(135deg, #FFD700, #FF8C00);
            color: #000; font-weight: 800; font-size: 0.75rem;
            padding: 4px 12px; border-radius: 20px;
        }
        .badge-free {
            display: inline-flex; align-items: center; gap: 6px;
            background: rgba(255,255,255,0.1); color: rgba(255,255,255,0.5);
            font-size: 0.75rem; padding: 4px 12px; border-radius: 20px;
            border: 1px solid rgba(255,255,255,0.2);
        }
        .admin-premium-row {
            background: rgba(255,215,0,0.06); border: 1px solid rgba(255,215,0,0.25);
            border-radius: 14px; padding: 16px 20px; margin-bottom: 12px;
        }
        .admin-user-name { color: #fff; font-weight: 700; font-size: 1rem; }
        .admin-user-meta { color: rgba(255,255,255,0.45); font-size: 0.8rem; }
        @keyframes nova-pulse {
            0%,100% { box-shadow: 0 0 20px rgba(255,215,0,0.4); }
            50%      { box-shadow: 0 0 60px rgba(255,215,0,0.9); }
        }
        .nova-processing {
            background: linear-gradient(135deg, rgba(255,215,0,0.1), rgba(255,140,0,0.08));
            border: 2px solid #FFD700; border-radius: 20px;
            padding: 30px; text-align: center; margin: 20px 0;
            animation: nova-pulse 2s ease-in-out infinite;
        }
        .nova-processing-title { color: #FFD700; font-size: 1.6rem; font-weight: 800; }
        .nova-processing-sub   { color: rgba(255,255,255,0.7); font-size: 1rem; margin-top: 8px; }
        .livrable-auto {
            background: linear-gradient(135deg, rgba(46,204,113,0.12), rgba(0,210,255,0.08));
            border: 2px solid #2ecc71; border-radius: 20px; padding: 28px; margin: 20px 0;
            box-shadow: 0 0 30px rgba(46,204,113,0.2);
        }
        .livrable-auto-title { color: #2ecc71; font-size: 1.4rem; font-weight: 800; }
        </style>
    """, unsafe_allow_html=True)

    if _premium:
        st.markdown("""
        <style>
        @keyframes shimmer-gold {
            0%   { background-position: -200% center; }
            100% { background-position:  200% center; }
        }
        .stApp {
            background: linear-gradient(135deg, #3d2800 0%, #4a3200 20%, #3a2600 40%, #4d3500 60%, #3d2900 80%, #2d1f00 100%) !important;
            color: #fff8e1 !important;
        }
        .stApp::before {
            content: '';
            position: fixed;
            inset: 0;
            background:
                radial-gradient(ellipse at 10% 10%, rgba(255,215,0,0.30) 0%, transparent 40%),
                radial-gradient(ellipse at 90% 90%, rgba(255,160,0,0.25) 0%, transparent 40%),
                radial-gradient(ellipse at 50% 50%, rgba(255,200,0,0.12) 0%, transparent 60%);
            pointer-events: none;
            z-index: 0;
        }
        .main-title {
            background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b) !important;
            background-size: 200% auto !important;
            -webkit-background-clip: text !important;
            -webkit-text-fill-color: transparent !important;
            animation: shimmer-gold 3s linear infinite !important;
            filter: drop-shadow(0 0 20px rgba(255,215,0,0.5));
        }
        .stTabs [data-baseweb="tab-list"] { background-color: rgba(255,215,0,0.05) !important; border: 1px solid rgba(255,215,0,0.2) !important; }
        .stTabs [data-baseweb="tab"] { background-color: rgba(255,215,0,0.07) !important; color: #FFD700 !important; }
        .stTabs [aria-selected="true"] { background-color: rgba(255,215,0,0.3) !important; border: 1px solid #FFD700 !important; }
        .stTextInput label, .stSelectbox label, .stTextArea label { color: #FFD700 !important; }
        div[data-baseweb="input"], div[data-baseweb="select"] > div { border: 1px solid rgba(255,215,0,0.6) !important; background-color: rgba(70,48,0,0.80) !important; }
        .stTextArea textarea { background-color: rgba(65,44,0,0.80) !important; color: #fff8e1 !important; border: 2px solid #FFD700 !important; }
        .stButton>button {
            background: linear-gradient(90deg, #8a6200, #c49a00, #FFD700, #c49a00, #8a6200) !important;
            background-size: 200% auto !important;
            color: #1a0f00 !important;
            animation: shimmer-gold 3s linear infinite !important;
        }
        section[data-testid="stSidebar"] { background: linear-gradient(180deg, #3a2800 0%, #4a3400 40%, #3a2800 100%) !important; border-right: 2px solid rgba(255,215,0,0.4) !important; }
        .info-card { border-left: 4px solid #FFD700 !important; background: rgba(255,215,0,0.10) !important; }
        .info-title { color: #FFD700 !important; }
        .support-btn { border: 2px solid #FFD700 !important; color: #FFD700 !important; }
        .support-btn:hover { background: #FFD700 !important; color: #0a0800 !important; }
        .stProgress > div > div > div > div { background-image: linear-gradient(to right, #b8860b, #FFD700) !important; }
        .file-card { border: 2px solid rgba(255,215,0,0.5) !important; background: rgba(20,12,0,0.5) !important; }
        .livrable-auto { background: linear-gradient(135deg, rgba(255,215,0,0.12), rgba(255,140,0,0.08)) !important; border: 2px solid #FFD700 !important; }
        .livrable-auto-title { color: #FFD700 !important; }
        hr { border-color: rgba(255,215,0,0.2) !important; }
        [data-testid="stMetric"] { background: rgba(255,215,0,0.10) !important; border: 1px solid rgba(255,215,0,0.35) !important; border-radius: 12px !important; }
        [data-testid="stMetricValue"] { color: #FFD700 !important; }
        </style>
        """, unsafe_allow_html=True)

    if st.session_state["is_glowing"]:
        st.markdown('<style>.stApp { animation: glow-pulse 1.5s ease-in-out infinite; }</style>', unsafe_allow_html=True)


def show_auth_page():
    st.markdown("""
    <style>
    @keyframes shimmer { 0% { background-position: -200% center; } 100% { background-position: 200% center; } }
    @keyframes float-up { 0% { opacity: 0; transform: translateY(30px); } 100% { opacity: 1; transform: translateY(0); } }
    @keyframes letter-pop { 0% { opacity: 0; transform: translateY(20px) scale(0.8); } 60% { transform: translateY(-4px) scale(1.05); } 100% { opacity: 1; transform: translateY(0) scale(1); } }
    @keyframes glow-border { 0% { box-shadow: 0 0 8px rgba(255,215,0,0.3); } 50% { box-shadow: 0 0 28px rgba(255,215,0,0.7); } 100% { box-shadow: 0 0 8px rgba(255,215,0,0.3); } }
    .auth-hero { text-align: center; padding: 40px 20px 10px 20px; animation: float-up 0.8s ease both; }
    .auth-logo-ring {
        width: 90px; height: 90px; border-radius: 50%; margin: 0 auto 18px auto;
        background: radial-gradient(circle at 35% 35%, #fff8e1, #FFD700 40%, #b8860b);
        box-shadow: 0 0 0 4px rgba(255,215,0,0.2), 0 0 40px rgba(255,215,0,0.5);
        display: flex; align-items: center; justify-content: center; font-size: 2.6rem;
        animation: glow-border 3s ease-in-out infinite;
    }
    .auth-title-wrap { display: flex; justify-content: center; gap: 2px; flex-wrap: wrap; margin-bottom: 6px; }
    .auth-letter {
        font-size: 3rem; font-weight: 800;
        background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
        background-size: 200% auto;
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        animation: letter-pop 0.5s ease both, shimmer 3s linear infinite;
        display: inline-block;
    }
    .auth-subtitle { color: rgba(255,215,0,0.65); font-size: 0.95rem; letter-spacing: 4px; text-transform: uppercase; }
    .auth-card {
        background: linear-gradient(145deg, rgba(20,15,5,0.95), rgba(35,25,5,0.9));
        border: 1px solid rgba(255,215,0,0.35); border-radius: 22px; padding: 32px 28px;
        position: relative; overflow: hidden; animation: float-up 0.9s ease both;
    }
    .auth-card::before {
        content: ''; position: absolute; top: 0; left: 0; right: 0; height: 3px;
        background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
        background-size: 200% auto; animation: shimmer 2.5s linear infinite; border-radius: 22px 22px 0 0;
    }
    .auth-card-title { color: #FFD700 !important; font-size: 1.15rem; font-weight: 800; text-transform: uppercase; }
    .auth-page .stButton > button {
        background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500) !important;
        background-size: 300% auto !important; color: #0a0800 !important;
        font-weight: 800 !important; letter-spacing: 2.5px !important; text-transform: uppercase !important;
        border-radius: 50px !important; animation: shimmer 3s linear infinite !important;
    }
    </style>
    """, unsafe_allow_html=True)

    letters = list("NOVA AI")
    letter_spans = "".join(
        f'<span class="auth-letter" style="animation-delay:{i*0.07:.2f}s">{"&nbsp;" if c == " " else c}</span>'
        for i, c in enumerate(letters)
    )
    st.markdown(f"""
    <div class="auth-hero">
        <div class="auth-logo-ring">⚡</div>
        <div class="auth-title-wrap">{letter_spans}</div>
        <div class="auth-subtitle">Plateforme IA bureautique</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="auth-page">', unsafe_allow_html=True)
    col1, col2 = st.columns(2, gap="large")

    with col1:
        st.markdown('<div class="auth-card"><div class="auth-card-title">🔐 Accès Membre</div></div>', unsafe_allow_html=True)
        with st.form("login"):
            uid    = st.text_input("Identifiant Nova", placeholder="Votre identifiant...")
            wa_auth = st.text_input("Numéro WhatsApp", placeholder="Ex: 22501...")
            if st.form_submit_button("⚡ S'IDENTIFIER"):
                db = st.session_state["db"]
                if uid in db["users"] and db["users"][uid]["whatsapp"] == normalize_wa(wa_auth):
                    st.session_state["current_user"] = uid
                    st.session_state["view"] = "home"
                    st.query_params["user_id"] = uid
                    st.rerun()
                else:
                    st.error("❌ Identifiant ou numéro inconnu.")

    with col2:
        st.markdown('<div class="auth-card"><div class="auth-card-title">✨ Nouveau Compte</div></div>', unsafe_allow_html=True)
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
                            "joined": str(datetime.now()),
                            "premium": False, "premium_plan": None, "premium_expiry": None,
                        }
                        save_user(new_uid, normalize_wa(new_wa))
                        st.session_state["current_user"] = new_uid
                        st.session_state["view"] = "home"
                        st.session_state["db"] = load_db()
                        st.query_params["user_id"] = new_uid
                        st.rerun()
                    else:
                        st.warning("⚠️ Identifiant déjà utilisé.")
                else:
                    st.error("Champs obligatoires.")

    st.markdown('</div>', unsafe_allow_html=True)

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
                    for (var i = 0; i < binary.length; i++) {{ bytes[i] = binary.charCodeAt(i); }}
                    var blob = new Blob([bytes], {{type: "audio/mpeg"}});
                    var audio = new Audio(URL.createObjectURL(blob));
                    audio.volume = 1;
                    audio.play().catch(function(e) {{ console.log(e); }});
                }}, 3000);
            }})();
            </script>
        """, height=0)


def show_main_page():
    inject_custom_css()
    db   = st.session_state["db"]
    uid  = st.session_state["current_user"]
    user = db["users"].get(uid, {})
    premium = is_premium_actif(user)
    premium_info = get_premium_info(user)

    SERVICES = {
        "📚 Exposé scolaire complet IA":       {"cat": "education", "premium_only": False},
        "📝 Sujets & Examens IA":              {"cat": "education", "premium_only": False},
        "👔 CV & Lettre de motivation IA":     {"cat": "pro",       "premium_only": False},
        "📊 Pack Office & Rédaction IA":       {"cat": "office",    "premium_only": False},
        "⚙️ Data Analytics Excel IA":          {"cat": "data",      "premium_only": False},
    }

    with st.sidebar:
        st.markdown(f"""
        <div style='text-align:center; padding:15px 0;'>
            <div style='font-size:2rem;'>{"👑" if premium else "⚡"}</div>
            <div style='color:{"#FFD700" if premium else "#00d2ff"}; font-weight:800; font-size:1.1rem;'>{uid}</div>
            <div style='color:rgba(255,255,255,0.5); font-size:0.8rem; margin-top:4px;'>
                {"✨ MEMBRE PREMIUM" if premium else "Membre Standard"}
            </div>
        </div>
        """, unsafe_allow_html=True)

        if premium and premium_info:
            st.markdown(f"""
            <div style='background:rgba(255,215,0,0.1); border:1px solid #FFD700; border-radius:12px; padding:12px; margin:10px 0; text-align:center;'>
                <div style='color:#FFD700; font-weight:700;'>Plan {premium_info["plan"]}</div>
                <div style='color:rgba(255,255,255,0.6); font-size:0.8rem;'>Expire le {premium_info["expiry"]}</div>
                <div style='color:#FFD700; font-size:0.85rem; margin-top:4px;'>{premium_info["jours_restants"]} jours restants</div>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("---")
        st.markdown("<div style='color:rgba(255,255,255,0.5); font-size:0.75rem; text-transform:uppercase; letter-spacing:2px; padding:5px 0;'>Navigation</div>", unsafe_allow_html=True)

        nav_items = [
            ("🏠", "Accueil",         "home"),
            ("📁", "Mes Fichiers",    "files"),
            ("💎", "Premium",         "premium"),
            ("⚙️", "Mon Compte",      "account"),
        ]
        for icon, label, view_key in nav_items:
            active = st.session_state["view"] == view_key
            if st.button(f"{icon} {label}", key=f"nav_{view_key}",
                         help=label,
                         type="primary" if active else "secondary"):
                st.session_state["view"] = view_key
                st.rerun()

        st.markdown("---")
        st.markdown(f"""<a href="{whatsapp_support_url}" target="_blank" class="support-btn">💬 Support WhatsApp</a>""", unsafe_allow_html=True)

        if st.button("🚪 Déconnexion"):
            st.session_state["current_user"] = None
            st.query_params.clear()
            st.rerun()

    view = st.session_state["view"]

    # ──────────────────────────────────────────────────────────────
    # VUE : HOME (Commander un service)
    # ──────────────────────────────────────────────────────────────
    if view == "home":
        st.markdown('<h1 class="main-title">⚡ NOVA AI</h1>', unsafe_allow_html=True)
        st.markdown("<p style='text-align:center; color:rgba(255,255,255,0.6); font-size:1.1rem;'>Votre assistant bureautique propulsé par l'IA</p>", unsafe_allow_html=True)

        if not premium:
            st.markdown(f"""
            <div class="premium-card">
                <div class="premium-title">👑 NOVA PREMIUM</div>
                <div class="premium-desc">Débloquez la puissance 10^10 — Générations illimitées, qualité maximale</div>
                <a href="{whatsapp_premium_url}" target="_blank" class="btn-gold">⚡ ACTIVER PREMIUM</a>
            </div>
            """, unsafe_allow_html=True)

        st.markdown("### 🎯 Commander un service")

        with st.form("order_form"):
            service = st.selectbox("Service souhaité", list(SERVICES.keys()))
            client_nom = st.text_input("Votre nom complet", placeholder="Ex: KOUASSI Aya Marie")
            description = st.text_area(
                "Décrivez précisément votre besoin",
                height=160,
                placeholder="Ex: Exposé sur la déforestation en Côte d'Ivoire — Terminale D — 5 pages minimum..."
            )
            auto_gen = st.checkbox("⚡ Générer automatiquement avec l'IA Nova", value=True)
            submitted = st.form_submit_button("🚀 ENVOYER MA COMMANDE", type="primary")

        if submitted:
            if not description.strip() or not client_nom.strip():
                st.error("❌ Veuillez remplir tous les champs.")
            else:
                req_id = hashlib.md5(f"{uid}{time.time()}".encode()).hexdigest()[:10]
                req = {
                    "id": req_id, "user": uid, "service": service,
                    "desc": description, "whatsapp": user.get("whatsapp", ""),
                    "status": "en_attente", "incomplet": False,
                    "champs_manquants": [], "timestamp": str(datetime.now())
                }
                db["demandes"].append(req)
                save_demande(req)
                envoyer_notification(client_nom, user.get("whatsapp",""), service, description)

                if auto_gen:
                    with st.spinner("⚡ Nova AI génère votre document..."):
                        contenu = generer_avec_gemini(service, description, client_nom)

                    st.session_state["gemini_results"][req_id] = {
                        "contenu": contenu, "service": service,
                        "client_nom": client_nom, "description": description
                    }
                    st.session_state["premium_livrable"] = req_id
                    st.rerun()
                else:
                    st.success("✅ Commande envoyée ! Vous serez contacté sur WhatsApp.")

        # Affichage livrable IA
        if st.session_state.get("premium_livrable"):
            req_id = st.session_state["premium_livrable"]
            res    = st.session_state["gemini_results"].get(req_id)
            if res:
                st.markdown(f"""
                <div class="livrable-auto">
                    <div class="livrable-auto-title">✅ Document généré par Nova AI</div>
                    <div style='color:rgba(255,255,255,0.7); margin-top:8px;'>
                        {res["service"]} — {res["client_nom"]}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    buf_docx = creer_docx(res["contenu"], res["service"], res["client_nom"])
                    st.download_button(
                        "📄 Télécharger Word (.docx)",
                        data=buf_docx,
                        file_name=f"Nova_{res['service'][:20].strip()}_{res['client_nom'][:15].strip()}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        type="primary"
                    )
                with col2:
                    if st.button("✖ Fermer"):
                        st.session_state["premium_livrable"] = None
                        st.rerun()

                with st.expander("📋 Voir le contenu généré"):
                    st.markdown(res["contenu"])

    # ──────────────────────────────────────────────────────────────
    # VUE : MES FICHIERS
    # ──────────────────────────────────────────────────────────────
    elif view == "files":
        st.markdown("## 📁 Mes Fichiers")
        liens_user = db.get("liens", {}).get(uid, [])
        resultats  = st.session_state.get("gemini_results", {})

        if not liens_user and not resultats:
            st.info("Aucun fichier pour le moment. Passez une commande depuis l'accueil !")
            return

        if resultats:
            st.markdown("### ⚡ Fichiers générés en session")
            for req_id, res in resultats.items():
                with st.container():
                    st.markdown(f"""<div class="file-card">
                        <b style='color:#00d2ff;'>{res['service']}</b><br>
                        <small style='color:rgba(255,255,255,0.5);'>{res['client_nom']}</small>
                    </div>""", unsafe_allow_html=True)
                    buf = creer_docx(res["contenu"], res["service"], res["client_nom"])
                    st.download_button(
                        "📄 Télécharger .docx",
                        data=buf,
                        file_name=f"Nova_{res['service'][:20].strip()}.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        key=f"dl_{req_id}"
                    )

        if liens_user:
            st.markdown("### 🔗 Fichiers partagés par l'admin")
            for lien in reversed(liens_user):
                st.markdown(f"""<div class="file-card">
                    <b style='color:#2ecc71;'>{lien['name']}</b><br>
                    <small style='color:rgba(255,255,255,0.5);'>{lien['date']}</small><br>
                    <a href="{lien['url']}" target="_blank" style='color:#00d2ff;'>📥 Télécharger</a>
                </div>""", unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────────────
    # VUE : PREMIUM
    # ──────────────────────────────────────────────────────────────
    elif view == "premium":
        st.markdown("## 💎 Plans Premium Nova AI")

        if premium and premium_info:
            st.success(f"✅ Vous êtes déjà Premium ({premium_info['plan']}) — expire le {premium_info['expiry']}")

        for plan_name, plan_data in PLANS_PREMIUM.items():
            st.markdown(f"""
            <div class="premium-card">
                <div class="premium-title">{plan_data['emoji']} Plan {plan_name}</div>
                <div class="premium-desc">
                    <b>{plan_data['prix']}</b> — {plan_data['jours']} jour(s) d'accès<br>
                    {plan_data['generations']} génération(s) incluse(s)
                </div>
                <a href="{whatsapp_premium_url}" target="_blank" class="btn-gold">Commander ce plan</a>
            </div>
            """, unsafe_allow_html=True)

    # ──────────────────────────────────────────────────────────────
    # VUE : MON COMPTE
    # ──────────────────────────────────────────────────────────────
    elif view == "account":
        st.markdown("## ⚙️ Mon Compte")
        st.markdown(f"""
        <div class="info-card">
            <span class="info-title">Informations</span>
            <b>Identifiant :</b> {uid}<br>
            <b>WhatsApp :</b> {user.get('whatsapp','—')}<br>
            <b>Membre depuis :</b> {user.get('joined','—')[:10]}<br>
            <b>Statut :</b> {"👑 Premium actif" if premium else "Standard"}
        </div>
        """, unsafe_allow_html=True)

        mes_demandes = [d for d in db["demandes"] if d["user"] == uid]
        if mes_demandes:
            st.markdown("### 📋 Mes commandes")
            for d in reversed(mes_demandes[-5:]):
                st.markdown(f"""<div class="info-card">
                    <span class="info-title">{d['service']}</span>
                    <b>Statut :</b> {d['status']} — <small>{d['timestamp'][:16]}</small>
                </div>""", unsafe_allow_html=True)


def show_admin_page():
    inject_custom_css()
    db = st.session_state["db"]

    st.markdown("## 🛠️ Console Admin — Nova AI")

    tabs = st.tabs(["📋 Commandes", "👥 Utilisateurs", "🔗 Envoyer Fichier", "💎 Premium"])

    # ── ONGLET COMMANDES ──────────────────────────────────────────
    with tabs[0]:
        st.markdown("### 📋 Toutes les commandes")
        demandes = db.get("demandes", [])
        if not demandes:
            st.info("Aucune commande.")
        else:
            for d in reversed(demandes):
                user_wa = db["users"].get(d["user"], {}).get("whatsapp", "—")
                with st.expander(f"#{d['id'][:6]} — {d['service']} — {d['status']}"):
                    st.write(f"**Client :** {d['user']} | **WA :** {user_wa}")
                    st.write(f"**Description :** {d['desc']}")
                    st.write(f"**Date :** {d['timestamp'][:16]}")

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        if st.button("✅ Marquer livré", key=f"done_{d['id']}"):
                            d["status"] = "livré"
                            save_demande(d)
                            st.rerun()
                    with col2:
                        if st.button("⚙️ En cours", key=f"wip_{d['id']}"):
                            d["status"] = "en_cours"
                            save_demande(d)
                            st.rerun()
                    with col3:
                        if st.button("🗑️ Supprimer", key=f"del_{d['id']}"):
                            db["demandes"].remove(d)
                            delete_demande(d["id"])
                            st.rerun()

    # ── ONGLET UTILISATEURS ───────────────────────────────────────
    with tabs[1]:
        st.markdown("### 👥 Utilisateurs enregistrés")
        users = db.get("users", {})
        st.metric("Total membres", len(users))
        for uid_u, udata in users.items():
            premium_actif = is_premium_actif(udata)
            badge = "👑 PREMIUM" if premium_actif else "Standard"
            st.markdown(f"""
            <div class="admin-premium-row">
                <span class="admin-user-name">{uid_u}</span>
                <span style='margin-left:10px; color:{"#FFD700" if premium_actif else "rgba(255,255,255,0.4)"}; font-size:0.8rem;'>{badge}</span>
                <div class="admin-user-meta">WA: {udata.get('whatsapp','—')} | Depuis: {udata.get('joined','—')[:10]}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── ONGLET ENVOYER FICHIER ────────────────────────────────────
    with tabs[2]:
        st.markdown("### 🔗 Envoyer un fichier à un client")
        with st.form("send_file"):
            target_uid = st.selectbox("Client destinataire", list(db.get("users", {}).keys()))
            file_name  = st.text_input("Nom du fichier")
            file_url   = st.text_input("URL du fichier (Google Drive, Dropbox...)")
            if st.form_submit_button("📤 Envoyer"):
                if target_uid and file_name and file_url:
                    date_now = datetime.now().strftime("%d/%m/%Y %H:%M")
                    save_lien(target_uid, file_name, file_url, date_now)
                    if target_uid not in db["liens"]:
                        db["liens"][target_uid] = []
                    db["liens"][target_uid].append({"name": file_name, "url": file_url, "date": date_now})
                    st.success(f"✅ Fichier envoyé à {target_uid}")
                else:
                    st.error("Remplissez tous les champs.")

    # ── ONGLET PREMIUM ────────────────────────────────────────────
    with tabs[3]:
        st.markdown("### 💎 Gestion des abonnements Premium")
        users = db.get("users", {})

        col1, col2 = st.columns(2)
        with col1:
            st.markdown("#### Activer un plan")
            with st.form("activate_premium"):
                target = st.selectbox("Utilisateur", list(users.keys()), key="prem_act_uid")
                plan   = st.selectbox("Plan", list(PLANS_PREMIUM.keys()))
                if st.form_submit_button("✅ Activer"):
                    activer_premium(target, plan)
                    st.session_state["db"] = load_db()
                    st.success(f"✅ Premium {plan} activé pour {target}")
                    st.rerun()

        with col2:
            st.markdown("#### Désactiver")
            with st.form("deactivate_premium"):
                target2 = st.selectbox("Utilisateur", list(users.keys()), key="prem_deact_uid")
                if st.form_submit_button("❌ Désactiver"):
                    desactiver_premium(target2)
                    st.session_state["db"] = load_db()
                    st.success(f"Premium désactivé pour {target2}")
                    st.rerun()

        st.markdown("#### Membres Premium actifs")
        for uid_u, udata in users.items():
            if is_premium_actif(udata):
                info = get_premium_info(udata)
                st.markdown(f"""
                <div class="admin-premium-row">
                    <span class="admin-user-name">👑 {uid_u}</span>
                    <div class="admin-user-meta">Plan: {info['plan']} | Expire: {info['expiry']} | {info['jours_restants']} jours restants</div>
                </div>
                """, unsafe_allow_html=True)


# ──────────────────────────────────────────────────────────────────
# POINT D'ENTRÉE PRINCIPAL
# ──────────────────────────────────────────────────────────────────
def main():
    query = st.query_params
    admin_code = query.get("admin")

    if admin_code == ADMIN_CODE:
        show_admin_page()
    elif st.session_state["current_user"] is None:
        show_auth_page()
    else:
        show_main_page()


if __name__ == "__main__":
    main()
