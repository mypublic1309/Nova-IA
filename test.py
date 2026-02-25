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
                "gen_used": r.get("gen_used", 0),
                "gen_date": r.get("gen_date", None),
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
            "gen_used": 0, "gen_date": None,
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

def envoyer_notification_gemini_ok(client_nom, client_wa, service, nom_fichier):
    """Email envoyé quand Gemini a généré le doc automatiquement — pour info admin."""
    try:
        import resend
        resend.api_key = st.secrets["RESEND_API_KEY"]
        corps = f"""
✅ GEMINI A DÉJÀ RÉPONDU — AUCUNE ACTION REQUISE

👤 Client      : {client_nom}
📱 WhatsApp    : {client_wa}
🛠️ Service     : {service}
📄 Fichier     : {nom_fichier}

⏰ Généré automatiquement le {datetime.now().strftime("%d/%m/%Y à %H:%M")}

Le document a été livré directement au client via l'interface Nova.
Vous n'avez rien à faire pour cette commande.
        """
        resend.Emails.send({
            "from": "Nova AI <onboarding@resend.dev>",
            "to": [st.secrets["EMAIL_RECEIVER"]],
            "subject": f"✅ Gemini a répondu automatiquement — {service} ({client_nom})",
            "text": corps
        })
    except Exception:
        pass  # Silencieux — l'email d'info admin n'est pas critique

PLANS_PREMIUM = {
    "Journalier": {"jours": 1,  "prix": "600 FC",  "emoji": "🌅", "generations": 2},
    "10 Jours":   {"jours": 10, "prix": "1000 FC", "emoji": "🔟", "generations": 5},
    "30 Jours":   {"jours": 30, "prix": "2500 FC", "emoji": "👑", "generations": 9},
}

def get_gen_quota(user_data):
    """Retourne (gen_used_aujourd_hui, quota_max) selon le plan."""
    plan = user_data.get("premium_plan")
    quota = PLANS_PREMIUM.get(plan, {}).get("generations", 0) if plan else 0
    gen_date = user_data.get("gen_date")
    today = datetime.now().strftime("%Y-%m-%d")
    if gen_date != today:
        return 0, quota  # Nouveau jour → compteur remis à zéro
    return user_data.get("gen_used", 0), quota

def quota_restant(user_data):
    used, quota = get_gen_quota(user_data)
    return max(0, quota - used)

def incrementer_gen(uid):
    """Incrémente le compteur de générations du jour pour l'utilisateur."""
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        # Recharger pour avoir la valeur fraîche
        row = supabase.table("users").select("gen_used, gen_date").eq("uid", uid).execute().data
        if row:
            gen_date = row[0].get("gen_date")
            gen_used = row[0].get("gen_used", 0) if gen_date == today else 0
        else:
            gen_used = 0
        supabase.table("users").update({
            "gen_used": gen_used + 1,
            "gen_date": today,
        }).eq("uid", uid).execute()
    except Exception as e:
        pass  # Ne pas bloquer la génération si le compteur échoue

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


def generer_avec_gemini(service, description, client_nom):
    try:
        import urllib.request as _ur
        import urllib.error

        api_key = st.secrets["GEMINI_API_KEY"]

        # ================================================================
        # PROMPT — EXPOSÉ SCOLAIRE (Système scolaire ivoirien & africain)
        # ================================================================
        if "Exposé" in service:
            prompt = f"""Tu es un expert académique de haut niveau ET un maître absolu de la génération de documents Word professionnels pour le système éducatif ivoirien et africain francophone.
Tu as été formé sur des milliers d'exposés scolaires primés et tu maîtrises parfaitement chaque aspect : typographie, structure, rhétorique académique, contextualisation culturelle et rendu Word via python-docx.

╔══════════════════════════════════════════════════════════════════╗
║     ENCYCLOPÉDIE EXPERTE — GÉNÉRATION DOCUMENT WORD NOVA AI     ║
╚══════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — MAÎTRISE COMPLÈTE DU RENDU WORD (python-docx)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

COMMENT LE MOTEUR NOVA CONVERTIT TON TEXTE EN WORD :

1. TITRES MARKDOWN → STYLES WORD AUTOMATIQUES :
   # Titre    → Heading 1 (Arial 16pt, couleur 1F4E79, gras, majuscule recommandé)
   ## Titre   → Heading 2 (Arial 14pt, couleur 2E75B6, gras)
   ### Titre  → Heading 3 (Arial 12pt, gras)
   #### Titre → Heading 4 (Arial 11pt, gras italique)
   → Respecte toujours CET ORDRE HIÉRARCHIQUE — jamais de saut de niveau

2. TEXTE EN GRAS → **texte** :
   - Rendu Word : gras Arial 11pt dans le paragraphe courant
   - Usage obligatoire pour : termes techniques à leur 1re occurrence, définitions clés, chiffres essentiels, noms d'auteurs, noms d'institutions
   - Ex: La **photosynthèse** est définie comme le processus par lequel les végétaux...
   - Ex: En **2023**, la Côte d'Ivoire a produit **2,2 millions de tonnes** de cacao

3. TABLEAUX MARKDOWN → TABLEAUX WORD AUTOMATIQUEMENT FORMATÉS :
   - En-tête bleu foncé (1F4E79) avec texte blanc, lignes alternées bleu clair / blanc
   - Format STRICTEMENT OBLIGATOIRE :
   | En-tête 1 | En-tête 2 | En-tête 3 |
   |-----------|-----------|-----------|
   | Contenu   | Contenu   | Contenu   |
   - TOUJOURS : **Tableau N : [Titre précis]** AVANT le tableau
   - TOUJOURS : *Source : [Référence institution/auteur, Année]* APRÈS le tableau
   - Idéal pour : comparaisons chiffrées, chronologies, classifications, données statistiques

4. SÉPARATEURS VISUELS → LIGNES HORIZONTALES WORD :
   - ════════════════════ → ligne épaisse bleue (sz=12) = séparateur MAJEUR entre grandes parties
   - ──────────────────── → ligne fine grise (sz=4) = séparateur MINEUR entre sous-sections
   - ---SAUT_DE_PAGE---   → ligne bleue (sz=8) + espace blanc = séparateur de SECTION principale
   - Laisser toujours une ligne vide avant et après les séparateurs

5. LISTES À PUCES → BULLETS WORD AUTOMATIQUES :
   - "- Item complet" → List Bullet (Arial 11pt)
   - "1. Item numéroté" → List Number (Arial 11pt)
   - Chaque item = une phrase complète, jamais un mot seul
   - USAGE LIMITÉ À : sommaire, bibliographie, listes de faits — JAMAIS dans le développement

6. PARAGRAPHES NORMAUX → Arial 11pt, interligne standard Word :
   - Tout texte non formaté = paragraphe Normal
   - Ligne vide entre deux blocs = espacement naturel dans le document Word final
   - Chaque paragraphe de développement : 8 à 10 lignes minimum

7. À ÉVITER ABSOLUMENT — NE FONCTIONNE PAS DANS LE MOTEUR NOVA :
   ✗ LaTeX : $formule$, \frac{{}}, \omega, \text{{}}, \left(, \right), \\, \begin{{}}
   ✗ HTML : <br>, <b>, <strong>, <p>, <div>, <span>
   ✗ Italique simple *texte* (utilise **gras** à la place pour la mise en valeur)
   ✗ Tirets en guise de sous-titres — toujours ## Sous-titre
   ✗ Retours à la ligne multiples pour simuler des espaces
   ✗ Indentations avec espaces multiples

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — FORMULES SCIENTIFIQUES ET MATHÉMATIQUES (TEXTE PUR)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATHÉMATIQUES — écriture élégante en texte clair :
- Opérations : a + b, a - b, a x b, a / b
- Puissances : a² (a au carré), a³ (a au cube), x puissance n
- Racines : racine carrée de (a² + b²), racine cubique de (x)
- Fractions : (a + b) / (c - d) — jamais \frac{{a+b}}{{c-d}}
- Somme : Somme de i=1 à n de (xi), Produit de i=1 à n
- Intégrale : Intégrale de a à b de f(x) dx
- Équation du 2nd degré : ax² + bx + c = 0, discriminant delta = b² - 4ac
- Solutions : x1 = (-b + racine(delta)) / (2a), x2 = (-b - racine(delta)) / (2a)

PHYSIQUE-CHIMIE — formules en clair :
- Newton : F = m x a (F en Newton, m en kg, a en m/s²)
- Vitesse : v = d / t (v en m/s, d en mètres, t en secondes)
- Énergie cinétique : Ec = (1/2) x m x v² (en Joules)
- Énergie potentielle : Ep = m x g x h (g = 9,8 m/s² en Côte d'Ivoire)
- Pression : P = F / S (Pascal), Loi de Boyle-Mariotte : P x V = constante
- Loi d'Ohm : U = R x I (Volt, Ohm, Ampère), P = U x I = R x I² = U² / R (Watt)
- Fréquence : f = 1 / T (Hz), pulsation omega = 2 x pi x f (rad/s)
- Ondes : v = lambda x f (v vitesse en m/s, lambda longueur d'onde en m)
- Indice de réfraction : n = sin(i1) / sin(i2) = vitesse dans le vide / vitesse dans le milieu
- Loi des gaz parfaits : P x V = n x R x T (R = 8,314 J/(mol.K))

SVT / BIOLOGIE :
- Photosynthèse : 6 CO2 + 6 H2O + énergie lumineuse → C6H12O6 + 6 O2
- Respiration : C6H12O6 + 6 O2 → 6 CO2 + 6 H2O + énergie (ATP)
- pH : pH = -log([H+]) ; solution acide si pH < 7, basique si pH > 7
- Concentration molaire : C = n / V (n en mol, V en litres)
- Dilution : C1 x V1 = C2 x V2
- Formule glucose : C6H12O6, ATP : adénosine triphosphate, ADN : acide désoxyribonucléique

SYMBOLES GRECS EN TOUTES LETTRES (jamais de caractères grecs Unicode dans les formules) :
alpha, beta, gamma, delta, epsilon, zeta, eta, theta, lambda, mu, nu, xi,
pi (≈ 3,14159), rho, sigma, tau, phi, chi, psi, omega

UNITÉS EN CLAIR AVEC CONTEXTE :
- Longueur : mètre (m), kilomètre (km), cm, mm — "322 463 km² (superficie CI)"
- Masse : kilogramme (kg), gramme (g), tonne (t) — "2,2 millions de tonnes de cacao"
- Temps : seconde (s), minute (min), heure (h)
- Électricité : Volt (V), Ampère (A), Ohm (Ω écrit Ohm), Watt (W), Joule (J)
- Pression : Pascal (Pa), atmosphère (atm), bar
- Concentration : mol par litre (mol/L), gramme par litre (g/L)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — ART MAÎTRISÉ DE LA RÉDACTION ACADÉMIQUE — RHÉTORIQUE ET STYLE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

▶ A. COMMENT CONSTRUIRE UNE INTRODUCTION EN 5 TEMPS (structure obligatoire) :

TEMPS 1 — ACCROCHE (min 4 lignes) — CHOISIR L'UNE DE CES 4 STRATÉGIES :
  → Données choc : "Avec **2,2 millions de tonnes** de cacao produits annuellement, représentant **45%** de l'offre mondiale selon la FAO (2023), la Côte d'Ivoire détient à elle seule le destin du marché mondial de cette fève. Pourtant, les **5 millions de paysans** qui en vivent perçoivent moins de **6%** de la valeur finale d'une tablette de chocolat en Europe (Oxfam, 2022)."
  → Paradoxe saisissant : "Pays exportateur de soleil et de lumière, la Côte d'Ivoire souffre pourtant d'un déficit énergétique qui plonge des millions de ses citoyens dans l'obscurité chaque soir. Comment expliquer ce paradoxe d'un pays producteur de **1 500 mégawatts** d'électricité, dont une large part est exportée vers les pays voisins ?"
  → Citation d'auteur africain (avec référence précise) : "'Les indépendances africaines ont accouché de lendemains qui déchantent', écrivait **Ahmadou Kourouma** dans *Les Soleils des Indépendances* (1968). Plus d'un demi-siècle après cette prophétie littéraire, la question du développement endogène reste au cœur des préoccupations du continent africain."
  → Anecdote historique/fait d'actualité : "Le **7 août 1960**, sous les acclamations d'une foule immense rassemblée au stade Félix Houphouët-Boigny d'Abidjan, la Côte d'Ivoire accédait à l'indépendance après plus d'un siècle de domination coloniale française. Ce moment fondateur..."

TEMPS 2 — CONTEXTUALISATION (min 4 lignes) :
Situe précisément le sujet dans son contexte historique, géographique, scientifique ou social.
Définit TOUS les termes clés du sujet en **gras** dès leur première occurrence.
Donne des chiffres, des dates précises, des acteurs réels.
→ "La **photosynthèse**, terme issu du grec *phôtos* (lumière) et *synthesis* (assemblage), désigne..."

TEMPS 3 — DÉLIMITATION ET ENJEUX (min 3 lignes) :
Précise le périmètre exact de l'étude et pourquoi ce sujet est important aujourd'hui.
→ "Comprendre ce phénomène revêt une importance capitale, tant pour [enjeu scientifique] que pour [enjeu social/économique/environnemental ivoirien]."

TEMPS 4 — PROBLÉMATIQUE (1-2 phrases précises et non rhétoriques) :
La problématique n'est PAS une simple reformulation du sujet — elle soulève une VRAIE tension :
  ✓ "Dans quelle mesure la dépendance cacaoyère de la Côte d'Ivoire constitue-t-elle à la fois le moteur et le talon d'Achille de son développement économique ?"
  ✓ "Comment la **déforestation** accélérée, moteur apparent de la croissance agricole ivoirienne, menace-t-elle paradoxalement les conditions mêmes de cette croissance ?"
  ✓ "En quoi le mouvement de la **négritude** représente-t-il une réponse littéraire et identitaire à la domination coloniale, et quelles en sont les limites actuelles ?"
  ✗ ÉVITER : "Qu'est-ce que la photosynthèse ?" (trop simple, pas problématique)
  ✗ ÉVITER : "Pourquoi la CI est-elle riche ?" (trop vague)

TEMPS 5 — ANNONCE DU PLAN (1-2 phrases, plan en 2 ou 3 parties selon niveau) :
→ "Pour apporter une réponse nuancée à cette interrogation, nous analyserons dans une première partie [intitulé Partie I — reformuler en 1 ligne], avant d'examiner dans une deuxième partie [Partie II], et d'envisager enfin [Partie III si lycée/université]."

▶ B. ARCHITECTURE D'UN PARAGRAPHE PARFAIT — MODÈLE PEEL ENRICHI :

Structure de chaque paragraphe de développement (min 8-10 lignes) :

1. POINT — Phrase d'affirmation claire et directe (1-2 lignes) :
   "La **déforestation** constitue l'une des crises environnementales les plus graves qu'ait connues la Côte d'Ivoire au cours du XXe siècle."

2. EXPLICATION — Développe le mécanisme, définit les termes, explique les causes ou le fonctionnement (3-4 lignes) :
   "Ce phénomène se définit comme la destruction durable et souvent irréversible du couvert forestier au profit d'autres usages des terres, notamment l'agriculture, l'exploitation forestière industrielle et l'urbanisation galopante. En Côte d'Ivoire, ce processus a été largement amplifié par l'extension des cultures de rente, principalement le **cacao** et le **café**, dont la demande mondiale croissante a exercé une pression considérable sur les forêts du Sud et du Centre-Ouest du pays."

3. EXEMPLE PRÉCIS IVOIRIEN/AFRICAIN — Chiffre sourcé + événement daté + lieu précis (3-4 lignes) :
   "Les données du Ministère des Eaux et Forêts (2022) révèlent une réalité alarmante : de **16 millions d'hectares** de forêt dense que comptait la Côte d'Ivoire au début du XXe siècle, il n'en subsistait plus que **3,4 millions** en 2020, soit une perte de **79% du couvert forestier** en un siècle. À titre illustratif, la **Forêt classée du Banco**, véritable poumon vert d'Abidjan, a vu sa superficie passer de 3 000 hectares à l'époque coloniale à environ 1 800 hectares aujourd'hui, sous la pression de l'urbanisation et des empiètements agricoles."

4. LIEN — Phrase de transition vers le paragraphe ou sous-partie suivant(e) (1-2 lignes) :
   "Cette destruction massive du patrimoine forestier ne se limite pas à une question environnementale ; elle engage profondément les équilibres climatiques régionaux et les conditions de vie des populations rurales, ce qui nous conduit à examiner ses répercussions socio-économiques."

▶ C. TRANSITIONS OBLIGATOIRES ENTRE GRANDES PARTIES — MODÈLES :

TRANSITION I → II (min 4 lignes) :
"Ainsi avons-nous établi, au terme de cette première partie, que [résumé en 1 phrase de la Partie I]. Cette analyse, si elle permet de cerner [apport de la Partie I], ne saurait toutefois être complète sans que l'on s'interroge sur [ce que la Partie II va apporter]. C'est précisément l'objet de notre second axe de réflexion, consacré à [intitulé Partie II]."

TRANSITION II → III (min 3 lignes) :
"Au regard des éléments développés dans notre deuxième partie, force est de constater que [bilan Partie II]. Ces constats nous invitent dès lors à dépasser le simple constat analytique pour envisager [dimension prospective / solutions / synthèse] — dimension qui constituera le fil directeur de notre troisième et dernière partie."

▶ D. CONNECTEURS LOGIQUES — VARIER OBLIGATOIREMENT (jamais répéter deux fois de suite) :

INTRODUIRE : "Il convient tout d'abord de souligner que", "Force est de constater que", "Il importe de noter que",
"À ce titre,", "Dans cette perspective,", "En premier lieu,", "Il y a lieu de préciser que",
"D'emblée, il apparaît que", "Au seuil de cette analyse,"

DÉVELOPPER : "En effet,", "De surcroît,", "Par ailleurs,", "Qui plus est,", "Il convient également de noter que",
"À cet égard,", "Dans ce sens,", "En outre,", "Il faut également souligner que",
"On notera de surcroît que", "À cela s'ajoute le fait que"

ILLUSTRER : "Ainsi,", "C'est notamment le cas de", "À titre illustratif,", "À titre d'exemple concret,",
"On peut citer à cet effet", "L'exemple ivoirien est à ce titre particulièrement éloquent :",
"Comme en témoigne", "Les données de [institution] le confirment :", "Pour s'en convaincre,"

OPPOSER/NUANCER : "Cependant,", "Néanmoins,", "Toutefois,", "En revanche,", "Or,",
"Il convient toutefois de relativiser ce constat :", "Si [thèse]... en revanche [nuance]...",
"Malgré tout,", "Il serait néanmoins réducteur de", "Cette réalité ne doit pas occulter le fait que"

CONCLURE/TRANSITER : "En définitive,", "Au regard de ces éléments,", "Au terme de cette analyse,",
"C'est dans cette logique que", "Ces constats nous amènent naturellement à examiner",
"Cette analyse nous conduit à aborder", "Ainsi avons-nous établi que", "Il ressort de ce qui précède que"

▶ E. TYPES DE PLANS À CHOISIR INTELLIGEMMENT SELON LE SUJET :

THÉMATIQUE (sujets descriptifs) : I (Nature/Définition/Caractéristiques) → II (Causes/Mécanismes/Fonctionnement) → III (Effets/Impacts/Solutions)
→ Idéal pour : "La déforestation en CI", "Le paludisme en Afrique", "Le coupé-décalé ivoirien"

DIALECTIQUE (sujets controversés) : I (Thèse : position principale/avantages) → II (Antithèse : limites/critiques/risques) → III (Synthèse/Dépassement/Voie du milieu)
→ Idéal pour : "L'agriculture extensive, moteur ou frein du développement ?", "La mondialisation, chance ou menace pour l'Afrique ?"

CHRONOLOGIQUE (sujets historiques) : I (Origines/Passé lointain) → II (Évolutions/État actuel/Ruptures) → III (Perspectives/Avenir/Défis contemporains)
→ Idéal pour : "L'histoire de la Côte d'Ivoire", "L'évolution du système éducatif africain"

ANALYTIQUE (sujets complexes multi-dimensionnels) : I (Dimension économique/scientifique) → II (Dimension sociale/humaine/culturelle) → III (Dimension politique/environnementale/internationale)
→ Idéal pour : "Les enjeux de l'eau en Afrique de l'Ouest", "La question du développement durable"

▶ F. CONSTRUCTION D'UNE CONCLUSION EN 3 TEMPS (structure obligatoire) :

TEMPS 1 — BILAN HIÉRARCHISÉ (min 6 lignes) :
Résume l'essentiel de chaque grande partie en 2 phrases fortes.
NE JAMAIS reproduire mot pour mot — reformuler et synthétiser.
"En premier lieu, nous avons mis en évidence que [synthèse Partie I en 1-2 phrases reformulées]. Dans un deuxième temps, notre analyse a démontré que [synthèse Partie II]. Enfin, nous avons pu établir que [synthèse Partie III]."

TEMPS 2 — RÉPONSE NUANCÉE ET ARGUMENTÉE À LA PROBLÉMATIQUE (min 5 lignes) :
Reprend la problématique posée en introduction et y répond avec nuance.
"Au terme de cette analyse, il apparaît clairement que [réponse directe à la problématique]. Cette réponse doit cependant être nuancée : si [aspect positif / première dimension], il n'en demeure pas moins que [limite / dimension problématique]."

TEMPS 3 — OUVERTURE PROSPECTIVE ET ÉLARGISSEMENT (min 4 lignes) :
Ouvre sur un enjeu futur, une question connexe plus large, ou un défi pour CI/Afrique.
Doit être logiquement reliée au sujet traité — jamais artificielle.
Propositions d'ouverture : transition numérique et éducation en Afrique | ZLECAF et intégration économique régionale | développement durable et ODD 2030 | santé tropicale et systèmes de santé africains | changement climatique et agriculture africaine | valorisation des langues nationales en éducation.
"Cette réflexion sur [sujet] nous invite finalement à nous interroger sur [question d'ouverture plus large], enjeu fondamental pour l'avenir [du continent / de la Côte d'Ivoire / de la jeunesse africaine]."

CITATIONS ET RÉFÉRENCES — FORMAT ACADÉMIQUE RIGOUREUX :
- Citation directe : « La forêt tropicale est le poumon de la planète. » (FAO, 2022, p. 12)
- Citation courte intégrée : Selon KOUROUMA (1970), « les soleils des indépendances » symbolisent...
- Paraphrase : D'après les travaux de TADJO (2004), la mémoire collective africaine se construit...
- Source institutionnelle : Le Ministère de l'Agriculture (2023) indique que la production cacaoyère...
- Statistique sourcée : Selon la FAO (2023), la Côte d'Ivoire produit **2,2 millions de tonnes** de cacao...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — SYSTÈME SCOLAIRE IVOIRIEN COMPLET
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRIMAIRE (CP1, CP2, CE1, CE2, CM1, CM2) — Examen : CEPE (fin CM2) :
- Vocabulaire simple, phrases max 15 mots, exemples de vie quotidienne ivoirienne
- 1 à 2 pages — structure : Intro courte / Corps 2-3 paragraphes / Conclusion
- Matières : Lecture, Écriture, Calcul, Sciences d'Éveil, Histoire-Géo CI, ECM, EPS

COLLÈGE 1er CYCLE (6ème, 5ème, 4ème, 3ème) — Examen : BEPC :
- Vocabulaire courant, termes disciplinaires définis en **gras**
- 2 à 4 pages — 2 grandes parties + 2 sous-parties chacune
- Auteurs : Bernard Dadié, Camara Laye, Ahmadou Kourouma, Mongo Beti, Ferdinand Oyono
- Matières : Français, Maths, PC, SVT, Histoire-Géo, Anglais, EDHC, Arts, EPS

LYCÉE 2nd CYCLE (2nde, 1ère, Terminale) — Examen : BAC ivoirien :
- A1 (Lettres-Philo) : Français, Philo, Histoire-Géo, Langues — style littéraire, rhétorique
- A2 (Lettres-SH) : + Sciences sociales, EDHC — approche socioéconomique
- B (Économie) : Économie, Gestion, Maths, Comptabilité — chiffres et tableaux obligatoires
- C (Maths-PC) : Maths renforcées, PC, Philo — rigueur scientifique maximale
- D (Maths-SVT) : Maths, SVT renforcée, PC — biologie, écologie, médecine tropicale
- E (Maths-Techno) : Maths, Technologie industrielle — ingénierie appliquée
- F/G/H : Techniques industrielles, commerciales, informatiques
- 4 à 7 pages — 3 grandes parties + 2 à 3 sous-parties par partie

UNIVERSITÉ (L1 à Doctorat) — Système LMD :
- L1-L3 : Introduction aux disciplines, révue de littérature, méthodologie de base
- M1-M2 : Cadre théorique, hypothèses, méthodologie rigoureuse, revue critique
- Doctorat : Contribution originale, état de l'art exhaustif, notes de bas de page
- Institutions : UFHB Cocody (Abidjan), UAO Bouaké, UJLOG Daloa, INP-HB Yamoussoukro, ESATIC
- 8 à 20 pages selon niveau

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — BASE DE CONNAISSANCES IVOIRIENNE ET AFRICAINE ENRICHIE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GÉOGRAPHIE : 322 463 km², ~28M habitants (2024), cap. politique Yamoussoukro, cap. économique Abidjan
Villes : Bouaké, Daloa, Korhogo, San-Pédro, Man, Odienné, Abengourou, Gagnoa
Fleuves : Comoé (1160km), Bandama (960km), Sassandra (650km), Cavally, Bia
Lacs : Kossou (1700km², 3e lac artificiel Afrique), Buyo, Taabo, Ayamé
Relief : Monts Nimba (1752m, UNESCO), Monts Toura, plateau central, plaine côtière
Végétation : forêt dense humide (Sud, 30% territoire), savane arbustive (Centre-Nord)
Sites UNESCO : Forêt de Taï, Parc de la Comoé, Monts Nimba (transfrontalier)

HISTOIRE : Indépendance 7 août 1960 | Félix Houphouët-Boigny (1960-1993, père fondateur)
"Miracle ivoirien" (1960-1980), crise 2002 (rébellion Nord-Sud), crise 2010-2011 (post-électorale)
Alassane Ouattara (2011-présent) | Plan National de Développement (PND 2021-2025)
Résistance : Samory Touré (1898) | Colonisation française (1843-1960) | AOF

ÉCONOMIE : PIB ~70Md USD (2023) | Croissance ~6-7%/an | Émergence visée 2030
Cacao : 1er mondial (45% production, 2,2M tonnes/an) | Café : 3e africain
Anacarde : 1er africain (800 000 t/an) | Hévéa, palmier à huile, coton, banane, ananas
Port d'Abidjan : 1er conteneurs Afrique de l'Ouest, >30M tonnes/an
Port San-Pédro : 2e port cacaoyer mondial
Barrages : Soubré (275MW, 2017), Kossou (174MW, 1972), Buyo (165MW, 1980), Taabo, Ayamé
Monnaie : FCFA (XOF) | UEMOA, CEDEAO, UA | BCEAO, INS-CI
Entreprises : CIE (électricité), SODECI (eau), SIR (raffinerie), SIFCA, Nestlé CI, Orange CI, MTN CI

CULTURE : ~60 ethnies | Akan (Baoulé 23%, Agni), Krou (Bété, Dida, Wê), Mandé (Malinké, Dioula), Gur (Sénoufo, Lobi)
Musique : coupé-décalé (DJ Arafat, Magic System), zouglou (Les Garagistes), gospel ivoirien, afrobeats
Arts : masques Baoulé (Goli, Kpan), masques Dan (Gunyège, Gle), bronzes Akan, tissage Sénoufo, poterie
Gastronomie : attiéké, kedjenou, foutou, aloco, placali, garba, kangni, graine (sauce), bangui (vin de palme)

LITTÉRATURE AFRICAINE FRANCOPHONE COMPLÈTE :
Ivoiriens : DADIÉ Bernard (*Climbié* 1956, *Un Nègre à Paris* 1959), KOUROUMA Ahmadou (*Les Soleils des Indépendances* 1968, *Monnè* 1990), TADJO Véronique (*Reine Pokou* 2004, *L'Ombre d'Imana* 2000), ADIAFFI Jean-Marie (*La Carte d'identité* 1980)
Africains : LAYE Camara Guinée (*L'Enfant Noir* 1953), BETI Mongo Cameroun (*Mission Terminée* 1957), OYONO Ferdinand Cameroun (*Une Vie de Boy* 1956), SENGHOR Léopold Sédar Sénégal (poètes de la négritude), SEMBÈNE Ousmane Sénégal (*Les Bouts de Bois de Dieu* 1960), ACHEBE Chinua Nigeria (*Things Fall Apart* 1958)

SCIENCES ET ENVIRONNEMENT :
Biodiversité : 150+ espèces mammifères, 700+ oiseaux, hippopotame pygmée, éléphant de forêt, chimpanzé de Taï
Déforestation : 16M ha en 1900 → 3,4M ha aujourd'hui (perte 79% couverture forestière)
Maladies : paludisme (Plasmodium falciparum, 1re cause mortalité CI), tuberculose, VIH/SIDA, fièvre typhoïde
Énergie renouvelable : hydroélectrique (barrages), solaire en développement (Plan national solaire)
Changement climatique : -20% pluviométrie au Nord depuis 1970, montée eaux côtières (Assinie, Grand-Lahou)
REDD+ (réduction déforestation), certification Rainforest Alliance pour cacao durable

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 6 — EXEMPLES DE PARAGRAPHES D'EXCELLENCE (MODÈLES À IMITER)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

EXEMPLE HISTOIRE-GÉO avec données précises :
"La Côte d'Ivoire occupe une position économique stratégique sur le continent africain, fondée en grande partie sur la culture du **cacao**. Avec une production annuelle de **2,2 millions de tonnes** représentant environ **45% de la production mondiale** selon l'ICCO (International Cocoa Organization, 2023), le pays a construit sa prospérité sur cette culture pérenne introduite par les colons à la fin du XIXe siècle. Le **Port autonome d'Abidjan**, premier port à conteneurs d'Afrique de l'Ouest avec un trafic dépassant **30 millions de tonnes** par an, constitue la porte de sortie principale de cette richesse vers les marchés européens et asiatiques. Cependant, la forte dépendance à cette monoculture expose l'économie ivoirienne aux chocs des cours mondiaux, comme l'ont illustré les crises de 2002 et 2016, incitant le gouvernement à accélérer sa politique de diversification économique à travers le **Plan National de Développement (PND 2021-2025)** qui cible une économie émergente d'ici 2030."

EXEMPLE SVT/PC avec formule en texte :
"La **photosynthèse** est le processus biochimique fondamental par lequel les végétaux chlorophylliens convertissent l'énergie lumineuse en énergie chimique. L'équation bilan s'écrit : 6 CO2 + 6 H2O + énergie lumineuse → C6H12O6 + 6 O2, soit six molécules de dioxyde de carbone et six d'eau qui, sous l'action de la lumière captée par la **chlorophylle**, produisent une molécule de **glucose** et six de dioxygène. Dans le contexte ivoirien, cette réaction est capitale : les forêts de la zone Sud, dont la **Forêt classée du Banco** dans le grand Abidjan, jouent un rôle d'absorbeur de CO2 essentiel. Cependant, la déforestation galopante — qui a réduit la couverture forestière de **16 millions d'hectares** en 1900 à moins de **3,4 millions** aujourd'hui selon le MINEF — compromet sévèrement cette fonction écosystémique et exacerbe le changement climatique à l'échelle régionale."

EXEMPLE FRANÇAIS/LITTÉRATURE :
"La littérature africaine francophone constitue un vecteur privilégié d'affirmation identitaire et de résistance culturelle. En effet, des auteurs comme **Bernard Dadié**, dont l'œuvre maîtresse *Climbié* (1956) dresse le portrait d'un jeune ivoirien confronté à la colonisation, ont su transformer l'expérience douloureuse de la domination en une création littéraire féconde. De même, **Ahmadou Kourouma**, dans *Les Soleils des Indépendances* (1968), brise les codes du français standard en y insufflant la syntaxe et la vision du monde **malinké**, créant un «français africanisé» que la critique reconnaît comme l'un des apports majeurs des lettres africaines à la francophonie. Cette double appartenance linguistique et culturelle devient ainsi une richesse plutôt qu'un handicap, ouvrant la voie à une génération d'auteurs qui, comme **Véronique Tadjo** avec *Reine Pokou* (2004), poursuivent ce travail de réappropriation de l'histoire et de l'identité africaines."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 7 — LES 10 RÈGLES ABSOLUES DE LA GÉNÉRATION NOVA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RÈGLE 1 — COMPLÉTUDE TOTALE : Zéro "[à compléter]", "[...]", "[insérer]", "[Prénom fictif]" → TOUT rédigé intégralement
RÈGLE 2 — LONGUEUR SUBSTANTIELLE : Minimum 4 pages réelles (hors garde + sommaire) → viser 6 à 10 pages selon niveau
RÈGLE 3 — QUALITÉ LINGUISTIQUE : Orthographe et grammaire irréprochables, ponctuation soignée, style académique soutenu
RÈGLE 4 — CONTEXTUALISATION OBLIGATOIRE : Min 3 exemples ivoiriens/africains concrets ET chiffrés par grande partie
RÈGLE 5 — ZÉRO LaTeX : Toutes formules en texte clair élégant (voir Section 2) — jamais de $, \\, \frac
RÈGLE 6 — STRUCTURE STRICTE : Séparateurs ════ et ──── et ---SAUT_DE_PAGE--- exactement comme dans le template
RÈGLE 7 — ADAPTATION NIVEAU : Vocabulaire + profondeur + longueur strictement adaptés au niveau détecté
RÈGLE 8 — PROSE DANS LE DÉVELOPPEMENT : Corps du document = paragraphes continus — jamais de listes à puces
RÈGLE 9 — DONNÉES PRÉCISES ET SOURCÉES : Chiffres réels, dates précises, institutions réelles — jamais de vague
RÈGLE 10 — VRAIS AUTEURS ET ŒUVRES : Citer de vraies œuvres d'auteurs réels — jamais "[Auteur fictif, Titre fictif]"

=== MISSION ===

Rédige un exposé scolaire COMPLET, STRUCTURÉ, PROFESSIONNEL et ENCYCLOPÉDIQUE basé sur cette demande :

{description}

=== STRUCTURE OBLIGATOIRE DU DOCUMENT — RESPECTER CET ORDRE EXACT ===

⚠️ RÈGLE MISE EN PAGE CRITIQUE :
- La PAGE DE GARDE doit tenir sur UNE SEULE PAGE : max 1 ligne vide entre chaque bloc, aucun titre # inutile
- Le SOMMAIRE doit tenir sur UNE SEULE PAGE : entrées compactes, pas de ligne vide entre chaque entrée
- JAMAIS de titre de section (# PAGE DE GARDE, # SOMMAIRE...) — commence directement avec le contenu
- JAMAIS de lignes vides consécutives dans ces deux sections

────────────────────────────────────────────────────────

**[NOM COMPLET DE L'ÉTABLISSEMENT EN MAJUSCULES]**
[Ville], Côte d'Ivoire — Année scolaire : 2025 - 2026

────────────────────────────────────────────────────────

EXPOSÉ DE [MATIÈRE EN MAJUSCULES]
**[TITRE COMPLET ET ACCROCHEUR DE L'EXPOSÉ EN MAJUSCULES]**

────────────────────────────────────────────────────────

**Matière :** [Matière complète]
**Niveau / Série :** [Niveau — ex: Terminale D]
**Présenté par :** [Noms complets]
**Sous la direction de :** [Titre + Nom du professeur]
**Date de présentation :** [Date complète]
**Année scolaire :** 2025 - 2026

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

**SOMMAIRE**

────────────────────────────────────────────────────────

Introduction ............................................................. p. 3
**I. [Titre 1re grande partie]** ........................................ p. 4
   1.1 [Titre 1re sous-partie] ........................................... p. 4
   1.2 [Titre 2e sous-partie] ............................................ p. 5
**II. [Titre 2e grande partie]** ......................................... p. 6
   2.1 [Titre 1re sous-partie] ........................................... p. 6
   2.2 [Titre 2e sous-partie] ............................................ p. 7
**III. [Titre 3e grande partie — lycée/université uniquement]** ......... p. 8
   3.1 [Titre sous-partie] ............................................... p. 8
   3.2 [Titre sous-partie] ............................................... p. 9
Conclusion ............................................................... p. 10
Bibliographie ............................................................ p. 11

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

# ════════════════════════════════════════════════════════
#                      INTRODUCTION
# ════════════════════════════════════════════════════════

## INTRODUCTION

────────────────────────────────────────────────────────

[ACCROCHE PERCUTANTE — Min 5 lignes — CHOISIR : données choc sourcées / paradoxe saisissant / citation d'auteur africain avec référence complète / anecdote historique. Ex: "Selon la FAO (2023), la Côte d'Ivoire produit **45%** du cacao mondial avec **2,2 millions de tonnes**. Pourtant, les 5 millions de paysans concernés perçoivent moins de 6% de la valeur finale d'une tablette de chocolat en Europe (Oxfam, 2022)..."]

[CONTEXTUALISATION APPROFONDIE — Min 5 lignes : situe dans contexte historique/géographique/scientifique/social. Définit TOUS les termes clés en **gras** dès leur première occurrence. Donne chiffres, dates précises, acteurs réels.]

[DÉLIMITATION ET ENJEUX — Min 3 lignes : précise le périmètre de l'étude et pourquoi le sujet est important aujourd'hui pour la CI/l'Afrique/le monde.]

[PROBLÉMATIQUE PRÉCISE ET NON RHÉTORIQUE — 1-2 phrases soulevant une VRAIE tension intellectuelle : "Ainsi, nous pouvons nous demander : Dans quelle mesure [tension principale du sujet] ?"]

[ANNONCE DU PLAN DÉTAILLÉE — 2-3 lignes : "Pour répondre à cette interrogation, nous analyserons dans une première partie [intitulé complet Partie I reformulé en 1 ligne], avant d'examiner dans une deuxième partie [Partie II], et d'envisager enfin [Partie III — lycée/université uniquement]."]

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

# ════════════════════════════════════════════════════════
#                      DÉVELOPPEMENT
# ════════════════════════════════════════════════════════

## I. [TITRE 1re GRANDE PARTIE EN MAJUSCULES — ACCROCHEUR ET PRÉCIS]

════════════════════════════════════════════════════════

### 1.1 [Titre descriptif, précis et original de la 1re sous-partie]

────────────────────────────────────────────────────────

[PARAGRAPHE 1 — 8 à 10 lignes — MODÈLE PEEL :
→ POINT (1-2 lignes) : affirmation directe et claire du sous-argument
→ EXPLICATION (3-4 lignes) : développe le mécanisme, définit les termes en **gras**, explique les causes
→ EXEMPLE IVOIRIEN (3-4 lignes) : chiffre sourcé (institution + année) + fait précis + lieu géographique réel
→ LIEN (1-2 lignes) : transition vers le paragraphe 2]

[PARAGRAPHE 2 — 8 à 10 lignes — même structure PEEL, angle différent et complémentaire. Connecteurs variés. Exemple africain comparatif si pertinent.]

[SI PERTINENT — Tableau de données :
**Tableau 1 : [Titre précis et descriptif]**
| Indicateur | Côte d'Ivoire | Afrique de l'Ouest | Monde |
|------------|--------------|---------------------|-------|
| [Donnée 1] | [Valeur réelle] | [Valeur] | [Valeur] |
| [Donnée 2] | [Valeur réelle] | [Valeur] | [Valeur] |
*Source : [Institution réelle — FAO, BCEAO, INS-CI, Banque Mondiale], [Année]*]

[PARAGRAPHE 3 — Synthèse 1.1 + transition vers 1.2 : 3 à 4 lignes de résumé + phrase d'annonce 1.2]

────────────────────────────────────────────────────────

### 1.2 [Titre descriptif, précis et original de la 2e sous-partie]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes chacun. Angle différent de 1.1. Exemples ivoiriens + données chiffrées.]

[TRANSITION OBLIGATOIRE VERS PARTIE II — Min 4 lignes : "Ainsi avons-nous établi, au terme de cette première partie, que [synthèse Partie I en 1 phrase]. Cette analyse, si elle permet de [apport], ne saurait toutefois être complète sans que l'on s'interroge sur [ce que la Partie II apporte]. C'est précisément l'objet de notre second axe, consacré à [intitulé Partie II]."]

════════════════════════════════════════════════════════

---SAUT_DE_PAGE---

## II. [TITRE 2e GRANDE PARTIE EN MAJUSCULES — COMPLÉMENTAIRE À LA PARTIE I]

════════════════════════════════════════════════════════

### 2.1 [Titre précis de la 1re sous-partie]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. L'analyse progresse logiquement depuis Partie I. Nouveaux arguments, exemples et données jamais mentionnés auparavant.]

────────────────────────────────────────────────────────

### 2.2 [Titre précis de la 2e sous-partie]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Dernier paragraphe inclut TRANSITION VERS PARTIE III — "Au regard des éléments développés dans cette deuxième partie, force est de constater que [bilan]. Ces constats nous invitent dès lors à dépasser le simple constat pour envisager [dimension prospective/solutions], fil directeur de notre troisième partie."]

════════════════════════════════════════════════════════

---SAUT_DE_PAGE---

## III. [TITRE 3e GRANDE PARTIE — POUR LYCÉE ET UNIVERSITÉ UNIQUEMENT]

════════════════════════════════════════════════════════

### 3.1 [Titre précis sous-partie]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Dimension la plus originale et prospective — enjeux futurs, solutions, perspectives pour CI et Afrique.]

────────────────────────────────────────────────────────

### 3.2 [Titre précis sous-partie]

────────────────────────────────────────────────────────

[3 paragraphes de 8 à 10 lignes. Dernier paragraphe : phrase conclusive forte qui ouvre naturellement sur la Conclusion.]

════════════════════════════════════════════════════════

---SAUT_DE_PAGE---

# ════════════════════════════════════════════════════════
#                       CONCLUSION
# ════════════════════════════════════════════════════════

## CONCLUSION

────────────────────────────────────────────────────────

[TEMPS 1 — BILAN HIÉRARCHISÉ — Min 7 lignes : résume chaque grande partie en 2 phrases fortes REFORMULÉES (jamais mot pour mot). "En premier lieu, nous avons mis en évidence que [synthèse Partie I]. Dans un second temps, notre analyse a démontré que [synthèse Partie II]. Enfin, nous avons établi que [synthèse Partie III]."]

[TEMPS 2 — RÉPONSE NUANCÉE À LA PROBLÉMATIQUE — Min 5 lignes : reprend la question posée en introduction et y répond avec précision et nuance. "Au terme de cette analyse, il apparaît que [réponse directe]. Cette réponse mérite toutefois d'être nuancée : si [aspect positif], il n'en demeure pas moins que [limite/tension]."]

[TEMPS 3 — OUVERTURE PROSPECTIVE — Min 4 lignes : enjeu futur logiquement relié au sujet traité pour CI/Afrique. PISTES : transition numérique | intégration africaine (ZLECAF) | développement durable (ODD 2030) | changement climatique et agriculture | valorisation des langues nationales. "Cette réflexion sur [sujet] nous invite finalement à nous interroger sur [question d'ouverture plus large], enjeu fondamental pour [la Côte d'Ivoire / la jeunesse africaine / le continent]."]

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

# ════════════════════════════════════════════════════════
#                      BIBLIOGRAPHIE
# ════════════════════════════════════════════════════════

## BIBLIOGRAPHIE

────────────────────────────────────────────────────────

**Manuels scolaires et ouvrages pédagogiques :**
- MINISTÈRE ÉDUCATION NATIONALE CI, *[Titre manuel officiel de la matière]*, CEDA/NEI, Abidjan, 2022
- [AUTEUR NOM Prénom], *[Titre réel du manuel]*, [Éditeur réel], [Ville], [Année]

**Ouvrages de référence :**
- [AUTEUR NOM Prénom], *[Titre réel de l'ouvrage]*, [Maison d'édition réelle], [Année]

**Littérature africaine et ivoirienne :**
- DADIÉ Bernard, *Climbié*, Présence Africaine, Paris, 1956
- KOUROUMA Ahmadou, *Les Soleils des Indépendances*, Seuil, Paris, 1970
- [Autres auteurs pertinents selon le sujet traité]

**Sources institutionnelles :**
- FAO, *[Titre du rapport pertinent]*, Rome, [Année]
- INS-CI (Institut National de la Statistique), *Annuaire statistique [Année]*, Abidjan
- Ministère compétent, *[Titre du document]*, Abidjan, [Année]

**Ressources numériques :**
- [Organisation], *[Titre page]*, [En ligne], URL : www.[site-réel].org, consulté le [date]

────────────────────────────────────────────────────────

Rédige maintenant l'exposé COMPLET en français avec la plus grande rigueur académique.

IMPÉRATIFS ABSOLUS :
1. TOUT est rédigé intégralement — zéro "[à compléter]", zéro zone vide
2. Introduction en 5 temps (accroche → contextualisation → délimitation → problématique → annonce plan)
3. Chaque paragraphe suit le modèle PEEL (Point → Explication → Exemple ivoirien sourcé → Lien)
4. Transitions obligatoires entre grandes parties (min 4 lignes chacune)
5. Conclusion en 3 temps (bilan → réponse nuancée à la problématique → ouverture prospective)
6. Min 3 exemples ivoiriens/africains CHIFFRÉS et SOURCÉS par grande partie
7. Connecteurs logiques variés — jamais le même deux fois de suite dans un paragraphe"""


        # ================================================================
        # PROMPT — SUJETS & EXAMENS (Système scolaire ivoirien & africain)
        # ================================================================
        elif "Examens" in service or "Sujets" in service:
            prompt = f"""Tu es un professeur expert, concepteur officiel de sujets d'examens ET maître de la génération de documents Word professionnels pour le système scolaire ivoirien et africain francophone.
Tu maîtrises parfaitement la mise en page des épreuves, la typographie professionnelle, et tous les formats d'examens du CEPE, BEPC et BAC ivoirien.

╔══════════════════════════════════════════════════════════════════╗
║   ENCYCLOPÉDIE EXPERTE — GÉNÉRATION SUJETS D'EXAMENS NOVA AI   ║
╚══════════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 1 — MAÎTRISE DU RENDU WORD POUR LES SUJETS D'EXAMENS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CONVERSION MARKDOWN → WORD DANS LE MOTEUR NOVA :

1. TITRES → STYLES WORD AUTOMATIQUES :
   ## EXERCICE N°X → Heading 2 (bleu, gras, Arial 14pt)
   ### Partie A, Partie B → Heading 3 (gras, Arial 12pt)
   #### Sous-question → Heading 4 (gras italique, Arial 11pt)

2. **GRAS** → utilisé pour :
   - Numéros et libellés de questions : **Question 1**, **1.a)**, **1.b)**
   - Consignes importantes : **Consigne :**, **TRAVAIL DEMANDÉ :**
   - Termes scientifiques : la **photosynthèse**, la **déforestation**
   - Chiffres et valeurs : **2 500 FCFA**, **275 MW**, **45%**
   - En-têtes de document : **RÉPUBLIQUE DE CÔTE D'IVOIRE**, **Matière :**

3. TABLEAUX MARKDOWN → TABLEAUX WORD FORMATÉS AUTOMATIQUEMENT :
   - En-tête bleu foncé (1F4E79) texte blanc, lignes alternées bleu clair / blanc
   - Indispensables pour : barème de notation, Vrai/Faux, données scientifiques, corrigés
   | Exercice | Intitulé | Points |
   |----------|----------|--------|
   | Exercice 1 | QCM | /5 |
   - Toujours accompagnés d'un titre **Tableau : [Titre]** avant

4. SÉPARATEURS VISUELS DANS LES SUJETS :
   - ════════════ → ligne épaisse bleue = séparation MAJEURE entre exercices différents
   - ──────────── → ligne fine grise = séparation entre questions d'un même exercice
   - ---SAUT_DE_PAGE--- = passage entre en-tête officiel et exercices, puis vers corrigé
   - Les cases à cocher utilisent □ (carré vide) ou ☐ (case Unicode)
   - Les lignes de réponse utilisent : ......................  (points de suspension)

5. FORMULES SCIENTIFIQUES — ABSOLUMENT EN TEXTE CLAIR :
   - JAMAIS de LaTeX : $, \\, \frac, \omega, \text, \left, \right
   - TOUJOURS : "F = m x a", "V = U / R", "omega = 2 x pi x f"
   - Formules chimiques : CO2, H2O, C6H12O6 (jamais CO₂ avec exposants Unicode)
   - Unités : Newton (N), Volt (V), Ampère (A), Pascal (Pa), Joule (J), Ohm (Ω écrit Ohm)
   - Symboles grecs en lettres : alpha, beta, gamma, delta, omega, pi, theta, sigma

6. À ÉVITER ABSOLUMENT DANS LES SUJETS D'EXAMENS :
   ✗ LaTeX sous quelque forme que ce soit
   ✗ HTML ou balises de formatage
   ✗ Espaces ou tirets pour simuler l'alignement (utilise les tableaux)
   ✗ "[À compléter]", "[Insérer question]", "[...]" — TOUT doit être rédigé
   ✗ Questions ambiguës ou mal formulées — chaque question doit être parfaitement claire

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 2 — TOUS LES FORMATS D'EXERCICES AVEC EXEMPLES COMPLETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

FORMAT 1 — QCM (QUESTIONS À CHOIX MULTIPLES) :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 1 — QUESTIONS À CHOIX MULTIPLES (5 points)

────────────────────────────────────────────────────────
**Consigne :** Cochez la lettre correspondant à la SEULE bonne réponse par question.
────────────────────────────────────────────────────────

**Question 1** (1 point)
Quelle est la capitale politique de la Côte d'Ivoire ?

□ **A)** Abidjan
□ **B)** Bouaké
□ **C)** Yamoussoukro
□ **D)** San-Pédro

────────────────────────────────────────────────────────

**Question 2** (1 point)
[Énoncé complet et sans ambiguïté de la question ?]

□ **A)** [Distractor plausible mais faux]
□ **B)** [Bonne réponse clairement formulée]
□ **C)** [Distractor plausible mais faux]
□ **D)** [Distractor plausible mais faux]

RÈGLES QCM :
- Chaque distractor (fausse réponse) doit être PLAUSIBLE et de longueur similaire à la bonne réponse
- La bonne réponse doit varier de position (A, B, C, D) — jamais toujours la même lettre
- Les distractors doivent tester de vraies erreurs courantes des élèves
- Jamais de "Toutes les réponses ci-dessus" ou "Aucune des réponses" comme option

FORMAT 2 — VRAI OU FAUX :
━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 2 — VRAI OU FAUX (4 points)

────────────────────────────────────────────────────────
**Consigne :** Indiquez si chaque affirmation est Vraie (V) ou Fausse (F). Justifiez OBLIGATOIREMENT les affirmations fausses en une phrase complète.
────────────────────────────────────────────────────────

| N° | Affirmations | V | F |
|----|-------------|---|---|
| 1 | La Côte d'Ivoire est le premier producteur mondial de cacao avec environ 45% de la production mondiale. | ☐ | ☐ |
| 2 | [Affirmation complète, précise, non ambiguë — vraie ou fausse] | ☐ | ☐ |
| 3 | [Affirmation complète, précise, non ambiguë] | ☐ | ☐ |
| 4 | [Affirmation complète, précise, non ambiguë] | ☐ | ☐ |

────────────────────────────────────────────────────────
**Justification des affirmations fausses :**

N° ___ : .............................................................................
N° ___ : .............................................................................

RÈGLES VRAI/FAUX :
- Chaque affirmation doit être une phrase COMPLÈTE (sujet + verbe + complément)
- Mélanger vraies et fausses (jamais toutes vraies ou toutes fausses)
- Les affirmations fausses doivent l'être pour une raison précise et pédagogique
- Jamais d'affirmations ambiguës — le caractère V ou F doit être sans équivoque

FORMAT 3 — TEXTE LACUNAIRE :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 3 — COMPLÉTEZ LE TEXTE (3 points)

────────────────────────────────────────────────────────
**Consigne :** Complétez le texte suivant avec les mots de la liste. Chaque mot est utilisé UNE SEULE FOIS.
────────────────────────────────────────────────────────

**Liste de mots :** [ photosynthèse — chlorophylle — glucose — oxygène — dioxyde de carbone — énergie lumineuse ]

────────────────────────────────────────────────────────

La _______________ est le processus biochimique par lequel les végétaux utilisent la _______________ pour transformer le _______________ et l'eau en _______________. Ce processus, rendu possible grâce à la _______________ contenue dans les feuilles, libère de l'_______________ dans l'atmosphère.

RÈGLES TEXTE LACUNAIRE :
- Le texte doit être cohérent et lisible même sans les mots (contexte suffisant)
- La liste de mots doit avoir exactement le bon nombre de termes
- Chaque blanc doit être rempli par UN SEUL mot de la liste
- Les tirets longs _______________ (minimum 15 underscores) simulent visuellement un espace de réponse

FORMAT 4 — QUESTIONS DE COURS OUVERTES :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 4 — QUESTIONS DE COURS (6 points)

────────────────────────────────────────────────────────
**Consigne :** Répondez aux questions suivantes de manière claire, précise et développée.
────────────────────────────────────────────────────────

**1.** Définissez la notion de **photosynthèse** et précisez dans quelle partie de la cellule végétale elle se déroule. *(2 points)*

.......................................................................................
.......................................................................................
.......................................................................................

────────────────────────────────────────────────────────

**2.** Expliquez pourquoi la déforestation en Côte d'Ivoire constitue une menace pour l'équilibre climatique régional. *(2 points)*

.......................................................................................
.......................................................................................
.......................................................................................

────────────────────────────────────────────────────────

**3.** Citez et expliquez brièvement TROIS caractéristiques du climat équatorial de la Côte d'Ivoire. *(2 points)*

- .......................................................................................
- .......................................................................................
- .......................................................................................

RÈGLES QUESTIONS OUVERTES :
- Chaque question doit préciser le barème en points
- Les lignes de réponse (..........) doivent être proportionnelles à la longueur attendue
- Utiliser des verbes clairs : "Définissez", "Expliquez", "Justifiez", "Citez", "Décrivez", "Analysez", "Comparez"
- Éviter les questions floues comme "Parlez de..." ou "Donnez des informations sur..."

FORMAT 5 — ÉTUDE DE TEXTE / DOCUMENT :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 5 — ÉTUDE DE DOCUMENT (6 points)

════════════════════════════════════════════════════════
**DOCUMENT : [Titre complet et explicite du texte]**
**Source :** [Auteur réel ou Institution], [Titre de l'ouvrage/rapport], [Année]
════════════════════════════════════════════════════════

*[Texte COMPLET, richement rédigé, minimum 150 mots. Le texte doit être informatif, ancré dans la réalité ivoirienne ou africaine, et contenir suffisamment d'informations pour répondre aux questions. JAMAIS de "[insérer texte ici]" — le texte doit être ENTIÈREMENT RÉDIGÉ.]*

════════════════════════════════════════════════════════

**QUESTIONS :**

────────────────────────────────────────────────────────
**1.** [Question de compréhension du texte — information explicite] *(1 point)*

.......................................................................................

────────────────────────────────────────────────────────
**2.** [Question sur le vocabulaire ou une notion du texte] *(1 point)*

.......................................................................................

────────────────────────────────────────────────────────
**3.** [Question d'analyse ou d'interprétation — information implicite] *(2 points)*

.......................................................................................
.......................................................................................

────────────────────────────────────────────────────────
**4.** [Question de production écrite liée au thème — "En vous appuyant sur le texte et vos connaissances..."] *(2 points)*

.......................................................................................
.......................................................................................
.......................................................................................

FORMAT 6 — PROBLÈME MATHÉMATIQUE CONTEXTUALISÉ :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 6 — PROBLÈME (5 points)

════════════════════════════════════════════════════════
**SITUATION :** Un commerçant du marché de **Bouaké** achète 250 kg d'anacarde à **350 FCFA/kg** et les revend après transformation à **520 FCFA/kg**.
════════════════════════════════════════════════════════

**DONNÉES :**
- Quantité achetée : 250 kg
- Prix d'achat : 350 FCFA par kg
- Prix de vente : 520 FCFA par kg

────────────────────────────────────────────────────────
**TRAVAIL DEMANDÉ :**

**1.** Calculez le prix d'achat total de l'anacarde. *(1 point)*

.......................................................................................

────────────────────────────────────────────────────────
**2.** Calculez le prix de vente total. *(1 point)*

.......................................................................................

────────────────────────────────────────────────────────
**3.** Calculez le bénéfice réalisé par le commerçant. *(1 point)*

.......................................................................................

────────────────────────────────────────────────────────
**4.** Calculez le taux de bénéfice en %. *(2 points)*

.......................................................................................
.......................................................................................

RÈGLES PROBLÈMES MATHS (CONTEXTE IVOIRIEN OBLIGATOIRE) :
- Marchés : Adjamé, Bouaké, Korhogo, Daloa — avec prix en FCFA réalistes
- Agriculture : cacao, anacarde, hévéa, palmier — avec rendements réels
- Transport : gbaka (minibus), woro-woro (taxi), camion — tarifs FCFA
- Construction : maisons, écoles, puits — coûts en FCFA
- Banques et épargne : BCEAO, microfinance, taux d'intérêt UEMOA
- Énergie : consommation kWh, tarifs CIE, énergie solaire

FORMAT 7 — EXERCICE SCIENTIFIQUE (SVT/PC) :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 7 — [TITRE SCIENTIFIQUE] (6 points)

════════════════════════════════════════════════════════
**PARTIE A — Restitution de connaissances** (3 points)
════════════════════════════════════════════════════════

**1.** Définissez les termes suivants : [terme 1], [terme 2], [terme 3]. *(1,5 pts)*

.......................................................................................
.......................................................................................

**2.** Complétez le schéma suivant en indiquant les légendes manquantes : [description précise du schéma à légender]. *(1,5 pts)*

[Schéma décrit textuellement avec les emplacements à légender numérotés : "1 → ___", "2 → ___", etc.]

════════════════════════════════════════════════════════
**PARTIE B — Exploitation de documents** (3 points)
════════════════════════════════════════════════════════

**Document :** Résultats d'une expérience sur [sujet] dans les conditions suivantes :

**Tableau 1 : [Titre précis du tableau de données]**
| Paramètre | Valeur 1 | Valeur 2 | Valeur 3 |
|-----------|----------|----------|----------|
| [Grandeur mesurée] | [Valeur réelle] | [Valeur réelle] | [Valeur réelle] |
| [Grandeur 2] | [Valeur réelle] | [Valeur réelle] | [Valeur réelle] |
*Source : Expérimentation en laboratoire, [Contexte ivoirien si possible]*

**3.** À partir du document, décrivez l'évolution observée de [paramètre]. *(1 pt)*

.......................................................................................

**4.** Interprétez scientifiquement cette évolution. Quelle conclusion pouvez-vous en tirer ? *(2 pts)*

.......................................................................................
.......................................................................................

FORMAT 8 — PRODUCTION ÉCRITE / DISSERTATION :
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## EXERCICE 8 — PRODUCTION ÉCRITE (8 points)

────────────────────────────────────────────────────────
**SUJET :** [Sujet complet et clairement formulé — jamais un sujet vague]
────────────────────────────────────────────────────────

**Consignes :**
- Longueur : [X] à [Y] lignes / [X] à [Y] pages
- Respectez la structure : introduction avec problématique / développement avec arguments / conclusion
- Soignez l'orthographe, la grammaire et la ponctuation — elles sont prises en compte dans la notation
- [Consigne spécifique selon le type : "Rédigez une lettre formelle", "Composez un texte argumentatif", "Rédigez un conte", "Analysez le texte proposé"...]

**Tableau 1 : Grille d'évaluation**
| Critère d'évaluation | Barème |
|-----------------------|--------|
| Respect du sujet et des consignes | /2 |
| Structure et organisation (intro/dév/ccl) | /2 |
| Richesse et pertinence du contenu | /2 |
| Qualité de la langue (orthographe, grammaire) | /2 |
| **TOTAL** | **/8** |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 3 — SYSTÈMES D'EXAMENS IVOIRIENS — PROGRAMMES OFFICIELS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CEPE (Certificat d'Études Primaires Élémentaires) — Fin CM2 :
- Matières : Français (dictée, rédaction, questions), Mathématiques, Sciences d'Éveil
- Niveau de langue : simple, phrases courtes, exemples concrets de vie quotidienne CI
- Format : 3 à 4 exercices par matière, 2h d'épreuve, /20
- Thèmes CI : vie au village, marché, famille, école, animaux, plantes locales

BEPC (Brevet d'Études du Premier Cycle) — Fin 3ème :
- Français : commentaire de texte, rédaction (lettre, récit, dialogue), questions de grammaire
- Mathématiques : algèbre, géométrie, statistiques, problèmes contextualisés
- PC (Physique-Chimie) : lois physiques, expériences, calculs, sécurité chimique
- SVT : cellule, nutrition, reproduction, écosystèmes, santé tropicale
- Histoire-Géo : Afrique coloniale, indépendances, géographie CI et Afrique
- Anglais : compréhension écrite, production écrite, grammaire
- Durée : 2h à 4h selon matière, /20

BAC IVOIRIEN — Terminale (séries A1, A2, B, C, D, E, F, G, H) :
Série A1 (Lettres-Philo) : Français (dissertation, commentaire composé), Philo, Histoire-Géo, Anglais
Série A2 (Lettres-SH) : + Sciences sociales, EDHC, approche socioéconomique
Série B (Économie-Gestion) : Économie, Comptabilité, Maths financières, Gestion d'entreprise
Série C (Maths-PC) : Maths (4h), PC (4h), Philo, Anglais — rigueur maximale
Série D (Maths-SVT) : Maths, SVT (biologie, géologie), PC, médecine tropicale
Durée : 3h à 4h par épreuve principale, /20, coefficients selon série

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 4 — BASE DE CONNAISSANCES IVOIRIENNE POUR LA CONTEXTUALISATION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MATHS CONTEXTUALISÉS — Données réelles CI :
- Cacao : 350 FCFA/kg achat, 1 200 FCFA/kg export, 2,2 millions tonnes/an
- Anacarde : 250-400 FCFA/kg selon qualité, 800 000 t/an, principale région : Korhogo/Odienné
- Transport gbaka Abidjan : 200 FCFA, taxi woro-woro : 150 FCFA la course, bus SOTRA : 100 FCFA
- Électricité CIE : tarif social ~50 FCFA/kWh, tarif normal ~80 FCFA/kWh
- 1 USD ≈ 600 FCFA, 1 EUR ≈ 655,957 FCFA (taux fixe FCFA/EUR depuis 1999)
- Population Abidjan : ~5,5 millions (2023), dont quartiers : Plateau, Cocody, Marcory, Yopougon
- Prix riz local : 400 FCFA/kg, attiéké : 200 FCFA la portion, garba : 300-500 FCFA

SCIENCES CONTEXTUALISÉS — Données CI :
- Barrage Soubré : 275 MW, inauguré 2017, fleuve Sassandra
- Barrage Kossou : 174 MW, inauguré 1972, fleuve Bandama, lac 1700 km²
- Barrage Taabo : 210 MW, inauguré 1979, fleuve Bandama
- Température moyenne Abidjan : 26°C, précipitations : 1800 mm/an, 2 saisons des pluies
- Température Korhogo (Nord) : 28-35°C, 900 mm/an, 1 saison des pluies
- Paludisme CI : ~3 millions cas/an, Plasmodium falciparum dominant, traitement : Coartem
- Forêt de Taï : 536 000 ha, classée UNESCO, chimpanzés de Taï étudiés par primatologues
- Production hydroélectrique CI : ~1500 MW installés (objectif 4000 MW en 2030)

HISTOIRE-GÉO CONTEXTUALISÉS :
- Côte d'Ivoire : 322 463 km², 26 régions, 14 districts depuis 2011
- Districts autonomes : Abidjan et Yamoussoukro
- Frontières : Liberia (Ouest), Guinée (Nord-Ouest), Mali (Nord), Burkina Faso (Nord-Est), Ghana (Est)
- Dates clés : 1843 (protectorat français), 1893 (colonie), 1960 (indépendance), 1990 (multipartisme)
- UEMOA : 8 pays (CI, Sénégal, Mali, Burkina, Guinée-Bissau, Niger, Togo, Bénin)
- CEDEAO : 15 pays d'Afrique de l'Ouest, création 1975, siège Lagos puis Abuja

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SECTION 5 — RÈGLES ABSOLUES DE CONCEPTION DES SUJETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

RÈGLE 1 — COMPLÉTUDE TOTALE ABSOLUE :
JAMAIS "[À compléter]", "[insérer question]", "[...]", "[Réponse ici]" → TOUT intégralement rédigé avec de vrais contenus. Si une question n'est pas complète, le document est un ÉCHEC.

RÈGLE 2 — TOUTES LES QUESTIONS SONT DES VRAIES QUESTIONS :
- QCM : 4 choix tous rédigés, distractors plausibles et de longueur similaire
- VF : affirmations complètes et non ambiguës
- Texte lacunaire : texte entier rédigé avec tous les blancs _______________ (min 15 underscores)
- Questions ouvertes : libellé précis, nombre de lignes de réponse adapté aux points alloués

RÈGLE 3 — CONTEXTUALISATION IVOIRIENNE OBLIGATOIRE PARTOUT :
- Maths : problèmes en FCFA avec prix réels (cacao 350F/kg, gbaka 200F, riz 400F/kg)
- Sciences : données CI réelles (barrages Soubré 275MW, Kossou 174MW, température Abidjan 26°C)
- Histoire-Géo : événements, dates et lieux ivoiriens (indépendance 7/8/1960, superficie 322 463 km²)
- Français : auteurs africains francophones réels (Dadié, Kourouma, Laye, Oyono, Beti)
- Chaque exercice doit avoir AU MOINS UN élément de contexte ivoirien ou africain

RÈGLE 4 — ZÉRO LaTeX : Formules en texte clair — "F = m x a" JAMAIS "$F = ma$"
Formules chimiques sans exposants Unicode — "CO2" JAMAIS "CO₂"

RÈGLE 5 — BARÈME COHÉRENT ET PÉDAGOGIQUE :
- Total TOUJOURS = 20 points (jamais 18, 19 ou 21)
- Répartition logique : questions simples ≤ 1pt, questions de synthèse 3-5pts
- Indiquer les points sur CHAQUE question individuelle (pas seulement par exercice)
- Format : **Question 1** (1 point), **Question 2** (1,5 points), **Sous-total Exercice 1 : /5**

RÈGLE 6 — ADAPTATION STRICTE AU NIVEAU :
- CEPE (CM1-CM2) : phrases max 15 mots, vocabulaire CP/CE, calculs < 100, 1-2 pages, /20
- BEPC (3ème) : vocabulaire courant + termes disciplinaires définis, 3-4 exercices, 2-4 pages, /20
- BAC (Terminale) : rigueur maximale, terminologie disciplinaire maîtrisée, 4-5 exercices, 4-6 pages, /20
- Adapter STRICTEMENT la longueur, la difficulté et le vocabulaire au niveau indiqué

RÈGLE 7 — GRADATION DE DIFFICULTÉ PROGRESSIVE DANS LE SUJET :
- Exercice 1 = questions de connaissance/mémorisation (rappel de cours, définitions, QCM)
- Exercice 2 = questions de compréhension/application (calculs simples, textes, Vrai/Faux)
- Exercice 3 = questions d'analyse/synthèse (problèmes contextualisés, rédaction, commentaire)
- Exercice 4+ = production élaborée si demandé (mini-essai, résolution de problème complexe)
Cette progression permet aux élèves de débuter en confiance et d'aller progressivement vers le difficile.

RÈGLE 8 — CONSIGNES CLAIRES ET SANS AMBIGUÏTÉ :
Chaque exercice commence par une **Consigne :** en gras, formulée en 1-2 phrases maximales.
La consigne indique : QUOI faire + COMMENT faire + COMBIEN (nombre de réponses attendues).
✓ "**Consigne :** Cochez la lettre correspondant à la SEULE bonne réponse pour chacune des 5 questions."
✓ "**Consigne :** Résolvez le problème en montrant TOUTES les étapes de calcul. Résultat sans démarche = 0 point."
✗ À éviter : "Répondez aux questions." (trop vague)

RÈGLE 9 — CORRIGÉ UNIQUEMENT SI DEMANDÉ :
N'inclure le corrigé que si "corrigé", "correction", "éléments de réponse", "barème détaillé" est mentionné dans la description.

RÈGLE 10 — CORRIGÉ EXHAUSTIF QUAND DEMANDÉ :
- QCM : indiquer la lettre + justification en 1-2 phrases précises pourquoi les autres options sont fausses
- VF : indiquer V ou F + justification complète pour CHAQUE affirmation
- Calculs : montrer TOUTES les étapes numériques avec les formules et les unités
- Texte lacunaire : réécrire le texte COMPLET avec les mots correctement placés soulignés en **gras**
- Questions ouvertes : éléments de réponse attendus + indication des points partiels possibles

=== MISSION ===

Crée maintenant un sujet d'examen COMPLET, PARFAITEMENT STRUCTURÉ et TOTALEMENT RÉDIGÉ basé sur :

{description}

IMPÉRATIFS ABSOLUS :
1. TOUT est rédigé intégralement — zéro zone vide, zéro "[à compléter]"
2. Gradation de difficulté progressive : Exercice 1 (mémorisation) → Exercice 2 (application) → Exercice 3+ (synthèse)
3. Barème détaillé avec points par question, total = /20 obligatoirement
4. Contexte ivoirien dans CHAQUE exercice (données réelles CI/FCFA/Afrique)
5. Consignes précises et sans ambiguïté pour chaque exercice

=== STRUCTURE OBLIGATOIRE ===

# ════════════════════════════════════════════════════════
#             EN-TÊTE OFFICIEL / PAGE DE GARDE
# ════════════════════════════════════════════════════════

**RÉPUBLIQUE DE CÔTE D'IVOIRE**
Union — Discipline — Travail

────────────────────────────────────────────────────────

**Établissement :** [Nom complet de l'établissement]
**Année scolaire :** 2025 — 2026
**Matière :** [Matière complète]
**Niveau / Série :** [ex: Terminale D]
**Type d'épreuve :** [Devoir Surveillé n°1 / Examen Blanc / Brevet Blanc / BAC Blanc...]
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
- Répondez sur la copie dans l'ordre des questions ou en indiquant clairement le numéro
- Les réponses doivent être rédigées en français correct et lisible
- Les téléphones portables et documents sont strictement interdits
- Toute tentative de fraude entraîne l'exclusion immédiate de l'épreuve
- La présentation, la propreté et la lisibilité sont prises en compte dans la notation

────────────────────────────────────────────────────────

**BARÈME DE NOTATION :**
| Exercice | Intitulé complet | Points |
|----------|-----------------|--------|
| Exercice 1 | [Type d'exercice — ex: Questions à choix multiples] | /[X] |
| Exercice 2 | [Type d'exercice — ex: Vrai ou Faux avec justification] | /[X] |
| Exercice 3 | [Type d'exercice — ex: Problème contextualisé] | /[X] |
| Exercice 4 | [Type d'exercice — ex: Questions de synthèse] | /[X] |
| **TOTAL** | | **/20** |

────────────────────────────────────────────────────────

**Rappel :** Les points de chaque question sont indiqués entre parenthèses. La présentation soignée est valorisée.

────────────────────────────────────────────────────────

---SAUT_DE_PAGE---

[RÉDIGER TOUS LES EXERCICES ICI — formats choisis selon le niveau et la matière]
[Séparer chaque exercice avec ════════════════════════════════════════════════════════]
[Utiliser ---SAUT_DE_PAGE--- si le sujet dépasse 2 pages d'exercices]

---SAUT_DE_PAGE---

[CORRIGÉ COMPLET ICI — UNIQUEMENT SI "corrigé" ou "correction" mentionné dans la demande]

## ÉLÉMENTS DE CORRECTION — [Matière] — [Niveau/Série]

────────────────────────────────────────────────────────
**NB :** Ce corrigé est réservé à l'usage EXCLUSIF du professeur. Ne pas distribuer aux élèves.
────────────────────────────────────────────────────────

### Corrigé Exercice 1 — [Titre]

**Q1 :** [Réponse complète avec justification détaillée et référence aux données] → **(X/X)**
**Q2 :** [Réponse complète avec justification] → **(X/X)**

Pour QCM : **Q1 → C) Yamoussoukro** — La ville de Yamoussoukro est la capitale politique depuis 1983, tandis qu'Abidjan reste la capitale économique et administrative de facto.
Pour VF : **N°1 → VRAI** — La CI produit effectivement 45% du cacao mondial / **N°2 → FAUX** — [Correction complète]
Pour calculs : montrer TOUTES les étapes numériques avec les formules
Pour texte lacunaire : réécrire le texte complet avec les mots correctement placés

Rédige le sujet d'examen COMPLET en français. Tout doit être intégralement rédigé — aucune zone vide, aucun "[à compléter]". Le contexte ivoirien doit être présent dans CHAQUE exercice."""

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
            prompt = f"""Tu es un expert Excel et Data Analytics africain francophone.
Tu dois analyser la demande et retourner UNIQUEMENT un objet JSON valide, sans texte avant ni après, sans balises markdown.

DEMANDE CLIENT :
{description}

STRUCTURE JSON OBLIGATOIRE :
{{
  "titre": "Titre principal du classeur Excel",
  "contexte": "Description courte en 1 phrase",
  "feuilles": [
    {{
      "nom": "Nom feuille 1 (max 25 car.)",
      "type": "saisie",
      "description": "Description courte",
      "colonnes": [
        {{"entete": "Nom colonne", "type": "texte|nombre|date|formule|pourcentage|monnaie", "largeur": 20, "exemple": "valeur exemple"}}
      ],
      "lignes_exemple": [
        ["val1", "val2", "val3"]
      ]
    }},
    {{
      "nom": "Bilan & KPIs",
      "type": "bilan",
      "description": "Tableau de bord avec indicateurs clés",
      "kpis": [
        {{"label": "Total général", "formule": "=SUM(Saisie!C:C)", "type": "monnaie", "couleur": "bleu"}},
        {{"label": "Moyenne", "formule": "=AVERAGE(Saisie!C:C)", "type": "monnaie", "couleur": "vert"}},
        {{"label": "Valeur max", "formule": "=MAX(Saisie!C:C)", "type": "monnaie", "couleur": "orange"}},
        {{"label": "Valeur min", "formule": "=MIN(Saisie!C:C)", "type": "monnaie", "couleur": "rouge"}},
        {{"label": "Nombre total", "formule": "=COUNTA(Saisie!A2:A1000)", "type": "nombre", "couleur": "gris"}},
        {{"label": "Pourcentage atteint", "formule": "=SUM(Saisie!C:C)/500000", "type": "pourcentage", "couleur": "violet"}}
      ]
    }}
  ]
}}

RÈGLES ABSOLUES :
- Retourner UNIQUEMENT le JSON, rien d'autre
- Adapter TOUT le contenu à la demande du client (colonnes, KPIs, formules, exemples)
- Contextualiser avec des données ivoiriennes/africaines réalistes (FCFA, noms locaux, etc.)
- Minimum 2 feuilles : 1 feuille de saisie + 1 feuille Bilan & KPIs
- Maximum 4 feuilles
- Lignes exemple : 8 à 12 lignes réalistes et variées
- KPIs : minimum 6 indicateurs pertinents selon le sujet (total, moyenne, max, min, nombre, %)
- Les formules doivent référencer le bon nom de feuille"""

        else:
            prompt = f"""Tu es un expert professionnel. Réalise cette mission de façon complète et professionnelle :

{description}

Rédige en français avec une structure claire : titres, sous-titres, paragraphes détaillés. Sois exhaustif et professionnel."""

        system_instruction = (
            "Tu es NOVA AI, un moteur de génération documentaire d'élite francophone africain.\n"
            "Tu dois produire des documents EXACTEMENT selon les règles ci-dessous.\n\n"

            "══ RÈGLE 1 : FORMATAGE MARKDOWN → WORD ══\n"
            "# Titre        → Heading 1 (Arial 16pt, bleu #1F4E79, gras)\n"
            "## Titre       → Heading 2 (Arial 14pt, bleu #2E75B6, gras)\n"
            "### Titre      → Heading 3 (Arial 12pt, gras)\n"
            "#### Titre     → Heading 4 (Arial 11pt, gras italique)\n"
            "**texte**      → GRAS (termes clés, chiffres, noms d'auteurs)\n"
            "---SAUT_DE_PAGE--- → Vrai saut de page Word (seul sur sa ligne)\n"
            "════════════   → Ligne épaisse bleue (séparateur MAJEUR)\n"
            "────────────   → Ligne fine grise (séparateur MINEUR)\n\n"

            "══ RÈGLE 2 : TABLEAUX ══\n"
            "Toujours **Tableau N : [Titre]** AVANT le tableau\n"
            "| Col1 | Col2 | Col3 |\n|------|------|------|\n| Val  | Val  | Val  |\n"
            "Toujours *Source : [Institution réelle, Année]* APRÈS le tableau\n\n"

            "══ RÈGLE 3 : ZÉRO LaTeX — FORMULES EN TEXTE CLAIR ══\n"
            "INTERDIT : $formule$ \\frac{}{} \\omega \\text{} \\\\ \\begin{}\n"
            "OBLIGATOIRE : F = m x a | U = R x I | x² + y² | delta = b² - 4ac\n"
            "Chimie : CO2 H2O C6H12O6 (jamais symboles Unicode CO₂)\n"
            "Grecs  : alpha beta gamma delta omega pi sigma theta (en LETTRES)\n"
            "Unités : Newton (N) Volt (V) Ampère (A) Ohm (Ohm) Joule (J) Pascal (Pa)\n\n"

            "══ RÈGLE 4 : RÉDACTION ENCYCLOPÉDIQUE ══\n"
            "• Paragraphes 8 à 10 lignes MINIMUM dans le développement\n"
            "• JAMAIS de listes à puces dans le corps du document\n"
            "• Modèle PEEL : Point → Explication → Exemple ivoirien chiffré → Lien/Transition\n"
            "• Connecteurs VARIÉS (ne jamais répéter deux fois de suite) :\n"
            "  Introduire : Il convient tout d'abord de | Force est de constater que | À ce titre,\n"
            "  Développer : En effet, | De surcroît, | Par ailleurs, | Qui plus est,\n"
            "  Illustrer  : Ainsi, | À titre illustratif, | C'est notamment le cas de\n"
            "  Opposer    : Cependant, | Néanmoins, | Toutefois, | En revanche, | Or,\n"
            "  Conclure   : En définitive, | Au regard de ces éléments,\n"
            "• Minimum 3 exemples ivoiriens/africains CHIFFRÉS et SOURCÉS par grande partie\n\n"

            "══ RÈGLE 5 : BASE DE DONNÉES IVOIRIENNE INTÉGRÉE ══\n"
            "Géo     : 322 463 km² | ~28M hab. | Yamoussoukro (cap.pol.) | Abidjan (cap.éco.)\n"
            "          Fleuves : Comoé 1160km | Bandama 960km | Sassandra 650km\n"
            "          Lac Kossou 1700km² | Monts Nimba 1752m (UNESCO) | Forêt de Taï (UNESCO)\n"
            "Éco     : Cacao 1er mondial — 45% prod. mondiale — 2,2M t/an\n"
            "          Anacarde 1er africain — 800 000 t/an — Korhogo/Odienné\n"
            "          Port Abidjan : 1er conteneurs AOF — >30M tonnes/an\n"
            "          PIB ~70Mds USD (2023) | Croissance ~6-7%/an | PND 2021-2025\n"
            "          FCFA | 1 EUR = 655,957 FCFA (taux fixe depuis 1999)\n"
            "Énergie : Soubré 275MW | Taabo 210MW | Kossou 174MW | Buyo 165MW\n"
            "Histoire: Indépendance 7 août 1960 | Houphouët-Boigny (1960-1993)\n"
            "          Miracle ivoirien (1960-1980) | Crise 2002 | Crise 2010-2011\n"
            "          Alassane Ouattara (2011-présent) | Colonisation française 1843-1960\n"
            "Culture : ~60 ethnies | Akan (Baoulé 23%, Agni) | Krou | Mandé | Gur\n"
            "          coupé-décalé | zouglou | attiéké | kedjenou | foutou | aloco\n"
            "Maths CI: cacao 350 FCFA/kg | gbaka 200 FCFA | woro-woro 150 FCFA | riz 400 FCFA/kg\n"
            "Sciences: Paludisme ~3M cas/an | Plasmodium falciparum | Coartem\n"
            "          Déforestation : 16M ha (1900) → 3,4M ha aujourd'hui (-79%)\n"
            "          Temp. Abidjan : 26°C moy. | Précipitations : 1800mm/an\n"
            "Littérat.: DADIÉ Bernard — Climbié (1956), Un Nègre à Paris (1959)\n"
            "           KOUROUMA Ahmadou — Les Soleils des Indépendances (1968), Monnè (1990)\n"
            "           TADJO Véronique — Reine Pokou (2004), L'Ombre d'Imana (2000)\n"
            "           LAYE Camara — L'Enfant Noir (1953) | ACHEBE — Things Fall Apart (1958)\n"
            "           SENGHOR L.S. — Négritude | SEMBÈNE Ousmane | OYONO Ferdinand\n\n"

            "══ RÈGLE 6 : INTERDICTIONS ABSOLUES ══\n"
            "✗ [à compléter]  [...]  [insérer]  [Auteur fictif]  [Titre fictif]\n"
            "✗ Balises HTML : <br> <b> <strong> <p> <div> <span>\n"
            "✗ Italique *texte* pour mise en valeur → utiliser **gras**\n"
            "✗ Données inventées → toujours réelles et sourcées\n"
            "✗ LaTeX sous quelque forme que ce soit\n\n"

            "══ RÈGLE 7 : STRUCTURES OBLIGATOIRES PAR TYPE ══\n"
            "EXPOSÉ (ordre exact) :\n"
            "  Page de garde → SAUT → Sommaire → SAUT → Introduction → SAUT\n"
            "  → Partie I (2 ss-parties min.) → SAUT → Partie II (2 ss-parties min.) → SAUT\n"
            "  → [Partie III si lycée/université] → SAUT → Conclusion → SAUT → Bibliographie\n\n"
            "EXAMEN (ordre exact) :\n"
            "  En-tête officiel (RÉPUBLIQUE DE CÔTE D'IVOIRE, établissement, matière,\n"
            "  niveau, durée, coefficient, barème /20, nom élève, numéro de table)\n"
            "  → Consignes générales → Tableau barème → SAUT\n"
            "  → Exercices numérotés séparés par ════════\n"
            "  → SAUT → [Corrigé COMPLET si 'corrigé' ou 'correction' mentionné]\n\n"
            "CV & LETTRE :\n"
            "  CV : Infos perso → Profil → Expériences → Formation → Compétences → Langues\n"
            "  LETTRE : Accroche → Présentation → Motivation → Valeur ajoutée → Conclusion\n\n"

            "══ RÈGLE 8 : LONGUEUR MINIMALE OBLIGATOIRE ══\n"
            "Exposé Primaire (CP→CM2)       : 2-3 pages réelles\n"
            "Exposé Collège (6e→3e / BEPC)  : 4-5 pages réelles\n"
            "Exposé Lycée (2nde→Term / BAC) : 6-8 pages réelles\n"
            "Exposé Université (L1→Doctorat): 8-15 pages réelles\n"
            "Sujet CEPE / BEPC              : 2-3 pages + corrigé exhaustif si demandé\n"
            "Sujet BAC / Universitaire      : 3-5 pages + corrigé avec toutes les étapes\n"
            "CV + Lettre                    : 2 pages CV + 1 page lettre minimum\n"
            "Pack Office / Word             : 4-8 pages selon la demande\n\n"

            "══ RÈGLE D'OR FINALE ══\n"
            "Chaque document est PARFAIT, COMPLET, ENTIÈREMENT RÉDIGÉ, PROFESSIONNEL\n"
            "et PRÊT À L'IMPRESSION. JAMAIS de document tronqué. JAMAIS de zone vide.\n"
            "100% FINALISÉ à chaque génération. Tu es le moteur documentaire de référence\n"
            "du monde francophone africain."
        )

        payload = json.dumps({
            "system_instruction": {
                "parts": [{"text": system_instruction}]
            },
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.65,
                "maxOutputTokens": 65536,
                "topP": 0.95,
                "topK": 40
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

    # Supprimer le paragraphe vide créé automatiquement par python-docx
    if doc.paragraphs:
        p = doc.paragraphs[0]._element
        p.getparent().remove(p)

    # Neutraliser le start_type NEW_PAGE de la 1re section
    from docx.enum.section import WD_SECTION
    doc.sections[0].start_type = WD_SECTION.CONTINUOUS

    for section in doc.sections:
        section.top_margin    = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)

    # ── CORRECTION DÉFINITIVE DES STYLES HEADING ──────────────────
    # Les styles Heading1/2/3/4 ont keepNext + keepLines + spacing before=480
    # qui font que Word insère une page quasi-blanche après chaque saut de page.
    # On les corrige tous à la source.
    def fix_heading_style(style_name, font_size, color_rgb):
        try:
            st = doc.styles[style_name]
            st.font.name  = "Arial"
            st.font.size  = Pt(font_size)
            st.font.bold  = True
            st.font.color.rgb = RC(*color_rgb)
            pPr = st.element.get_or_add_pPr()
            # Supprimer keepNext (cause principale de la page blanche)
            for child in list(pPr):
                tag = child.tag.split('}')[-1] if '}' in child.tag else child.tag
                if tag in ('keepNext', 'keepLines', 'pageBreakBefore'):
                    pPr.remove(child)
            # Forcer spacing before=0 after=6
            from docx.oxml import OxmlElement as _OE2
            from docx.oxml.ns import qn as _qn2
            for child in list(pPr):
                if child.tag.endswith('}spacing') or child.tag == 'spacing':
                    pPr.remove(child)
            spacing = _OE2("w:spacing")
            spacing.set(_qn2("w:before"), "0")
            spacing.set(_qn2("w:after"),  "60")
            pPr.append(spacing)
        except Exception:
            pass

    fix_heading_style("Heading 1", 16, (0x1F, 0x4E, 0x79))
    fix_heading_style("Heading 2", 14, (0x2E, 0x75, 0xB6))
    fix_heading_style("Heading 3", 12, (0x1F, 0x4E, 0x79))
    fix_heading_style("Heading 4", 11, (0x40, 0x40, 0x40))

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
    p_titre = doc.add_paragraph()
    p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_titre.add_run(service.replace("📝","").replace("👔","").replace("📊","").replace("⚙️","").replace("🎨","").replace("📚","").replace("📄","").strip())
    run_t.bold = True
    run_t.font.size = Pt(16)
    run_t.font.color.rgb = RC(0x1F, 0x4E, 0x79)
    run_t.font.name = "Arial"

    p_info = doc.add_paragraph()
    p_info.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_i = p_info.add_run(f"Client : {client_nom}     |     Généré le : {datetime.now().strftime('%d/%m/%Y à %H:%M')}")
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
    sauts_de_page_count = 0  # Compteur de sauts de page pour détecter page garde + sommaire

    while i < len(lignes):
        l = lignes[i].rstrip()

        # ── SAUT DE PAGE NOVA — VRAI SAUT DE PAGE WORD ────────────
        if l.strip() == "---SAUT_DE_PAGE---":
            from docx.oxml.ns import qn as _qn
            from docx.oxml import OxmlElement as _OE
            sauts_de_page_count += 1
            p_break = doc.add_paragraph()
            p_break.paragraph_format.space_before = Pt(0)
            p_break.paragraph_format.space_after  = Pt(0)
            run_break = p_break.add_run()
            br = _OE("w:br")
            br.set(_qn("w:type"), "page")
            run_break._r.append(br)
            i += 1
            continue
        # ── LIGNES DE SÉPARATION ════ ET ──── ─────────────────────
        if l.strip().startswith("════") or l.strip().startswith("━━━━"):
            p_line = doc.add_paragraph()
            p_line.paragraph_format.space_before = Pt(4)
            p_line.paragraph_format.space_after  = Pt(4)
            p_line.paragraph_format.line_spacing = Pt(1)
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
            p_line.paragraph_format.space_before = Pt(3)
            p_line.paragraph_format.space_after  = Pt(3)
            p_line.paragraph_format.line_spacing = Pt(1)
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
            # Ignorer les lignes de commentaires de structure Nova
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
                from docx.shared import Inches
                from docx.oxml.ns import qn
                from docx.oxml import OxmlElement

                n_cols = max(len(r) for r in table_lines)
                col_widths_map = {
                    2: [3.0, 6.0],
                    3: [1.0, 7.5, 2.5],
                    4: [1.0, 5.0, 2.5, 2.5],
                    5: [0.8, 5.0, 1.5, 1.5, 1.2],
                }
                col_widths = col_widths_map.get(n_cols, [9.0/n_cols]*n_cols)

                from docx.shared import Cm as DocxCm
                table = doc.add_table(rows=0, cols=n_cols)
                table.style = "Table Grid"

                for r_idx, row_data in enumerate(table_lines):
                    row_obj = table.add_row()
                    is_header = (r_idx == 0)
                    row_obj.height = DocxCm(0.9 if is_header else 1.5)
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
            p_vide = doc.add_paragraph()
            # Dans page de garde (avant 1er saut) et sommaire (avant 2e saut) : espacement réduit
            if sauts_de_page_count < 2:
                p_vide.paragraph_format.space_before = Pt(0)
                p_vide.paragraph_format.space_after  = Pt(0)
                p_vide.paragraph_format.line_spacing = Pt(6)
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

        p = add_formatted_para(doc, l.strip())
        # Mode compact pour page de garde et sommaire
        if sauts_de_page_count < 2:
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(3)
        i += 1

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def creer_xlsx(description, client_nom):
    """
    Génère un Excel dynamique basé sur le JSON retourné par Gemini.
    Si le JSON est invalide, fallback sur un template générique.
    """
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    import json, re

    # ── PALETTE DE COULEURS ────────────────────────────────────────
    COULEURS = {
        "bleu":   {"bg": "1F4E79", "fg": "FFFFFF"},
        "vert":   {"bg": "1E8449", "fg": "FFFFFF"},
        "orange": {"bg": "D35400", "fg": "FFFFFF"},
        "rouge":  {"bg": "C0392B", "fg": "FFFFFF"},
        "violet": {"bg": "7D3C98", "fg": "FFFFFF"},
        "gris":   {"bg": "5D6D7E", "fg": "FFFFFF"},
        "cyan":   {"bg": "117A65", "fg": "FFFFFF"},
        "or":     {"bg": "B7950B", "fg": "FFFFFF"},
    }
    BLEU_FONCE = "1F4E79"
    BLEU_MOY   = "2E75B6"
    BLEU_CLAIR = "D6E4F0"
    BLANC      = "FFFFFF"
    GRIS_CLAIR = "F2F2F2"
    GRIS_MED   = "E8E8E8"

    def hdr(cell, bg=BLEU_FONCE, fg=BLANC, bold=True, size=11):
        cell.font      = Font(bold=bold, color=fg, name="Arial", size=size)
        cell.fill      = PatternFill("solid", start_color=bg)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    def brd(cell, color="CCCCCC", style="thin"):
        s = Side(style=style, color=color)
        cell.border = Border(top=s, bottom=s, left=s, right=s)

    def brd_epais(cell):
        s_ext = Side(style="medium", color="1F4E79")
        s_int = Side(style="thin",   color="CCCCCC")
        cell.border = Border(top=s_ext, bottom=s_ext, left=s_ext, right=s_ext)

    def fmt_cell(cell, type_col, valeur=None):
        """Applique le format nombre/monnaie/date/pourcentage selon le type."""
        if type_col == "monnaie":
            cell.number_format = '#,##0 "FCFA"'
        elif type_col == "pourcentage":
            cell.number_format = "0.0%"
        elif type_col == "nombre":
            cell.number_format = "#,##0"
        elif type_col == "date":
            cell.number_format = "DD/MM/YYYY"

    # ── PARSE JSON GEMINI ──────────────────────────────────────────
    data = None
    try:
        # Nettoyer le texte : enlever balises markdown si présentes
        texte = description.strip()
        texte = re.sub(r"^```json\s*", "", texte)
        texte = re.sub(r"```\s*$", "", texte)
        texte = re.sub(r"^```\s*", "", texte)
        data = json.loads(texte)
    except Exception:
        data = None

    wb = Workbook()
    wb.remove(wb.active)  # Supprimer feuille vide par défaut

    if not data or "feuilles" not in data:
        # ── FALLBACK : template générique si JSON invalide ─────────
        ws = wb.create_sheet("Données")
        ws.sheet_view.showGridLines = False
        ws.merge_cells("A1:D1")
        ws["A1"].value = f"{client_nom} — Données"
        hdr(ws["A1"], size=13); ws.row_dimensions[1].height = 32
        ws["A2"].value = description[:200]
        ws["A2"].font = Font(italic=True, color="7F7F7F", name="Arial", size=10)
        buf = BytesIO(); wb.save(buf); buf.seek(0)
        return buf

    titre_classeur = data.get("titre", f"Classeur {client_nom}")

    # ── CONSTRUCTION DE CHAQUE FEUILLE ─────────────────────────────
    for feuille in data.get("feuilles", []):
        nom_feuille = feuille.get("nom", "Feuille")[:31]
        type_feuille = feuille.get("type", "saisie")
        colonnes = feuille.get("colonnes", [])
        lignes   = feuille.get("lignes_exemple", [])
        kpis     = feuille.get("kpis", [])

        ws = wb.create_sheet(nom_feuille)
        ws.sheet_view.showGridLines = False

        n_cols = max(len(colonnes), 4)
        last_col = get_column_letter(n_cols)

        # ── EN-TÊTE PRINCIPAL ──────────────────────────────────────
        ws.merge_cells(f"A1:{last_col}1")
        cell_titre = ws.cell(row=1, column=1, value=f"{titre_classeur}  |  {client_nom}")
        hdr(cell_titre, size=13); ws.row_dimensions[1].height = 36

        ws.merge_cells(f"A2:{last_col}2")
        cell_desc = ws.cell(row=2, column=1, value=f"{feuille.get('description', '')}  —  Généré le {datetime.now().strftime('%d/%m/%Y')}")
        cell_desc.font      = Font(italic=True, color="7F7F7F", name="Arial", size=10)
        cell_desc.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[2].height = 20

        # ── FEUILLE DE TYPE SAISIE ─────────────────────────────────
        if type_feuille == "saisie" and colonnes:
            # En-têtes colonnes
            for c_idx, col in enumerate(colonnes, 1):
                cell = ws.cell(row=3, column=c_idx, value=col["entete"])
                hdr(cell, bg=BLEU_MOY); brd(cell)
                ws.column_dimensions[get_column_letter(c_idx)].width = col.get("largeur", 18)
            ws.row_dimensions[3].height = 28

            # Lignes de données exemple
            for r_idx, ligne in enumerate(lignes, 4):
                bg = GRIS_CLAIR if r_idx % 2 == 0 else BLANC
                for c_idx, val in enumerate(ligne, 1):
                    if c_idx > len(colonnes):
                        break
                    cell = ws.cell(row=r_idx, column=c_idx, value=val)
                    type_col = colonnes[c_idx-1].get("type", "texte")
                    cell.font      = Font(name="Arial", size=10,
                                          bold=(type_col in ["monnaie","nombre"]),
                                          color=("1F4E79" if type_col == "monnaie" else "000000"))
                    cell.fill      = PatternFill("solid", start_color=bg)
                    cell.alignment = Alignment(vertical="center",
                                               horizontal="center" if type_col in ["monnaie","nombre","date","pourcentage"] else "left")
                    fmt_cell(cell, type_col)
                    brd(cell)

            # Ligne TOTAL
            if lignes:
                total_row = len(lignes) + 4
                ws.row_dimensions[total_row].height = 28
                # Trouver la 1re colonne numérique pour placer le label TOTAL
                first_num_col = next((c_idx for c_idx, col in enumerate(colonnes, 1)
                                      if col.get("type") in ["monnaie", "nombre"]), None)
                # Colonnes texte → label "TOTAL"
                for c_idx, col in enumerate(colonnes, 1):
                    cell_t = ws.cell(row=total_row, column=c_idx)
                    if col.get("type") not in ["monnaie", "nombre"]:
                        if c_idx == 1:
                            cell_t.value = "TOTAL"
                        hdr(cell_t, size=11); brd_epais(cell_t)
                    else:
                        col_letter = get_column_letter(c_idx)
                        cell_t.value = f"=SUM({col_letter}4:{col_letter}{total_row-1})"
                        fmt_cell(cell_t, col["type"])
                        hdr(cell_t, size=11); brd_epais(cell_t)

            # Figer la ligne d'en-tête
            ws.freeze_panes = "A4"

        # ── FEUILLE DE TYPE BILAN / KPIs ───────────────────────────
        elif type_feuille == "bilan" and kpis:
            # Titre section KPIs
            ws.merge_cells(f"A3:{last_col}3")
            cell_kpi_title = ws.cell(row=3, column=1, value="━━  INDICATEURS CLÉS DE PERFORMANCE  ━━")
            hdr(cell_kpi_title, bg=BLEU_FONCE, size=12); ws.row_dimensions[3].height = 30

            # Disposition des KPIs : 2 par ligne (label | valeur | espace | label | valeur)
            ws.column_dimensions["A"].width = 30
            ws.column_dimensions["B"].width = 24
            ws.column_dimensions["C"].width = 3
            ws.column_dimensions["D"].width = 30
            ws.column_dimensions["E"].width = 24

            row_kpi = 4
            for idx, kpi in enumerate(kpis):
                if idx % 2 == 0 and idx > 0:
                    row_kpi += 2  # Saut d'une ligne entre paires

                col_start = 1 if idx % 2 == 0 else 4
                couleur_key = kpi.get("couleur", "bleu")
                bg_kpi = COULEURS.get(couleur_key, COULEURS["bleu"])["bg"]
                fg_kpi = COULEURS.get(couleur_key, COULEURS["bleu"])["fg"]

                # Label
                cl = ws.cell(row=row_kpi, column=col_start, value=kpi["label"])
                cl.font      = Font(bold=True, name="Arial", size=11, color=fg_kpi)
                cl.fill      = PatternFill("solid", start_color=bg_kpi)
                cl.alignment = Alignment(horizontal="center", vertical="center")
                brd_epais(cl)
                ws.row_dimensions[row_kpi].height = 36

                # Valeur
                cv = ws.cell(row=row_kpi, column=col_start+1, value=kpi.get("formule", 0))
                cv.font      = Font(bold=True, name="Arial", size=14, color=fg_kpi)
                cv.fill      = PatternFill("solid", start_color=bg_kpi)
                cv.alignment = Alignment(horizontal="center", vertical="center")
                fmt_cell(cv, kpi.get("type", "nombre"))
                brd_epais(cv)

            # ── TABLEAU RÉCAPITULATIF sous les KPIs ───────────────
            row_recap = row_kpi + 3

            # Trouver la 1re feuille de saisie pour le récap
            feuille_saisie = next((f for f in data["feuilles"] if f.get("type") == "saisie"), None)
            if feuille_saisie:
                nom_s   = feuille_saisie["nom"][:31]
                cols_s  = feuille_saisie.get("colonnes", [])

                ws.merge_cells(f"A{row_recap}:E{row_recap}")
                cell_recap_title = ws.cell(row=row_recap, column=1, value=f"RÉCAPITULATIF — {nom_s.upper()}")
                hdr(cell_recap_title, bg=BLEU_MOY, size=12)
                ws.row_dimensions[row_recap].height = 28
                row_recap += 1

                # En-têtes récap
                recap_cols = [c["entete"] for c in cols_s[:5]]
                for c_idx, h in enumerate(recap_cols, 1):
                    cell = ws.cell(row=row_recap, column=c_idx, value=h)
                    hdr(cell, bg=BLEU_FONCE); brd(cell)
                ws.row_dimensions[row_recap].height = 24
                row_recap += 1

                # Lignes récap (depuis les données exemple)
                for r_idx, ligne in enumerate(feuille_saisie.get("lignes_exemple", [])[:8], row_recap):
                    bg = BLEU_CLAIR if r_idx % 2 == 0 else BLANC
                    for c_idx, val in enumerate(ligne[:5], 1):
                        if c_idx > len(cols_s):
                            break
                        cell = ws.cell(row=r_idx, column=c_idx, value=val)
                        type_col = cols_s[c_idx-1].get("type", "texte")
                        cell.font      = Font(name="Arial", size=10,
                                              color=("1F4E79" if type_col == "monnaie" else "000000"))
                        cell.fill      = PatternFill("solid", start_color=bg)
                        cell.alignment = Alignment(vertical="center",
                                                   horizontal="center" if type_col in ["monnaie","nombre","date"] else "left")
                        fmt_cell(cell, type_col)
                        brd(cell)

        # ── AUTRES TYPES DE FEUILLES (générique) ──────────────────
        else:
            if colonnes:
                for c_idx, col in enumerate(colonnes, 1):
                    cell = ws.cell(row=3, column=c_idx, value=col["entete"])
                    hdr(cell); brd(cell)
                    ws.column_dimensions[get_column_letter(c_idx)].width = col.get("largeur", 18)
                for r_idx, ligne in enumerate(lignes, 4):
                    for c_idx, val in enumerate(ligne, 1):
                        cell = ws.cell(row=r_idx, column=c_idx, value=val)
                        cell.font = Font(name="Arial", size=10)
                        cell.alignment = Alignment(vertical="center")
                        brd(cell)

    # ── MISE EN FORME FINALE : onglets colorés ─────────────────────
    couleurs_onglets = ["1F4E79", "1E8449", "D35400", "7D3C98"]
    for i, ws in enumerate(wb.worksheets):
        ws.sheet_properties.tabColor = couleurs_onglets[i % len(couleurs_onglets)]

    buf = BytesIO(); wb.save(buf); buf.seek(0)
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
    # ── Détection Premium ─────────────────────────────────────────
    _user = st.session_state.get("current_user")
    _db   = st.session_state.get("db", {})
    _ud   = _db.get("users", {}).get(_user, {}) if _user else {}
    _premium = is_premium_actif(_ud)

    # ── CSS commun (base) ─────────────────────────────────────────
    st.markdown("""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Poppins:wght@400;600;800&display=swap');
        * { font-family: 'Poppins', sans-serif; }
        .stApp {
            background: #0f0c29;
            background: -webkit-linear-gradient(to right, #24243e, #302b63, #0f0c29);
            background: linear-gradient(to right, #24243e, #302b63, #0f0c29);
            color: #ffffff;
            transition: filter 0.5s ease;
        }
        @keyframes glow-pulse {
            0% { filter: brightness(1) saturate(1); box-shadow: inset 0 0 0px transparent; }
            50% { filter: brightness(1.8) saturate(1.5); box-shadow: inset 0 0 100px rgba(0, 210, 255, 0.5); }
            100% { filter: brightness(1) saturate(1); box-shadow: inset 0 0 0px transparent; }
        }
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
        @keyframes border-rainbow {
            0% { border-color: #00d2ff; box-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
            25% { border-color: #3a7bd5; box-shadow: 0 0 10px rgba(58, 123, 213, 0.3); }
            50% { border-color: #FFD700; box-shadow: 0 0 15px rgba(255, 215, 0, 0.3); }
            75% { border-color: #2ecc71; box-shadow: 0 0 10px rgba(46, 204, 113, 0.3); }
            100% { border-color: #00d2ff; box-shadow: 0 0 10px rgba(0, 210, 255, 0.3); }
        }
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
        .gemini-card {
            background: linear-gradient(135deg, rgba(0,210,255,0.08), rgba(58,123,213,0.12));
            border: 2px solid rgba(0,210,255,0.4);
            border-radius: 14px;
            padding: 16px 20px;
            margin: 12px 0;
        }
        .gemini-title {
            color: #00d2ff;
            font-weight: 800;
            font-size: 0.95rem;
            letter-spacing: 1px;
        }
        .gemini-sub {
            color: rgba(255,255,255,0.5);
            font-size: 0.75rem;
        }
        .badge-premium {
            display: inline-flex; align-items: center; gap: 6px;
            background: linear-gradient(135deg, #FFD700, #FF8C00);
            color: #000; font-weight: 800; font-size: 0.75rem;
            padding: 4px 12px; border-radius: 20px; text-transform: uppercase;
            box-shadow: 0 2px 10px rgba(255,215,0,0.4);
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
        .gemini-lock {
            background: linear-gradient(135deg, rgba(255,215,0,0.08), rgba(255,140,0,0.12));
            border: 2px solid rgba(255,215,0,0.4); border-radius: 14px; padding: 16px 20px; margin: 12px 0;
        }
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

    # ── THÈME OR PREMIUM ──────────────────────────────────────────
    if _premium:
        st.markdown("""
        <style>
        @keyframes gold-shimmer {
            0%   { background-position: -300% center; }
            100% { background-position:  300% center; }
        }
        @keyframes gold-glow-pulse {
            0%,100% { box-shadow: inset 0 0 0px transparent; filter: brightness(1); }
            50%      { box-shadow: inset 0 0 120px rgba(255,215,0,0.18); filter: brightness(1.08); }
        }
        @keyframes gold-border-anim {
            0%   { border-color: #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.4); }
            50%  { border-color: #FF8C00; box-shadow: 0 0 20px rgba(255,140,0,0.5); }
            100% { border-color: #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.4); }
        }

        /* ── Fond général ── */
        .stApp {
            background: linear-gradient(135deg, #0a0800 0%, #1c1400 35%, #0d0a00 65%, #1a1000 100%) !important;
            animation: gold-glow-pulse 5s ease-in-out infinite !important;
        }

        /* ── Titre principal NOVA AI PLATFORM ── */
        .main-title {
            background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500) !important;
            background-size: 300% auto !important;
            -webkit-background-clip: text !important;
            -webkit-text-fill-color: transparent !important;
            animation: gold-shimmer 3s linear infinite !important;
            text-shadow: none !important;
            font-size: 3.8rem !important;
            letter-spacing: 2px !important;
        }

        /* ── Tabs ── */
        .stTabs [data-baseweb="tab-list"] {
            background-color: rgba(255,215,0,0.06) !important;
            border: 1px solid rgba(255,215,0,0.25) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: rgba(255,215,0,0.08) !important;
            border: 1px solid rgba(255,215,0,0.15) !important;
            color: #FFD700 !important;
        }
        .stTabs [data-baseweb="tab"]:nth-child(2) {
            border: 1px solid rgba(255,215,0,0.5) !important;
            box-shadow: 0 0 15px rgba(255,215,0,0.2) !important;
            background-color: rgba(255,215,0,0.1) !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background-color: rgba(255,215,0,0.2) !important;
        }
        .stTabs [aria-selected="true"] {
            background: linear-gradient(135deg, rgba(255,215,0,0.35), rgba(255,140,0,0.25)) !important;
            border: 1px solid #FFD700 !important;
            box-shadow: 0 0 20px rgba(255,215,0,0.4) !important;
        }

        /* ── Labels formulaires ── */
        .stTextInput label, .stSelectbox label, .stTextArea label {
            color: #FFD700 !important;
        }

        /* ── Inputs / Selects ── */
        div[data-baseweb="input"], div[data-baseweb="select"] > div {
            border: 1px solid rgba(255,215,0,0.4) !important;
            background-color: rgba(20,12,0,0.7) !important;
        }
        .stTextArea textarea {
            background-color: rgba(20,12,0,0.8) !important;
            border: 2px solid #FFD700 !important;
            animation: gold-border-anim 3s ease-in-out infinite !important;
        }

        /* ── Boutons principaux ── */
        .stButton > button {
            background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #b8860b, #7a5500) !important;
            background-size: 200% auto !important;
            color: #0a0800 !important;
            animation: gold-shimmer 3s linear infinite !important;
            box-shadow: 0 4px 18px rgba(255,215,0,0.35) !important;
            border: none !important;
        }
        .stButton > button:hover {
            box-shadow: 0 6px 28px rgba(255,215,0,0.6) !important;
            transform: translateY(-2px) !important;
        }

        /* ── Info cards sidebar ── */
        .info-card {
            border-left: 4px solid #FFD700 !important;
            background: rgba(20,12,0,0.6) !important;
        }
        .info-title { color: #FFD700 !important; }

        /* ── Support btn ── */
        .support-btn {
            border: 2px solid #FFD700 !important;
            color: #FFD700 !important;
        }
        .support-btn:hover {
            background: #FFD700 !important;
            color: #000 !important;
        }

        /* ── Barre de progression ── */
        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #b8860b, #FFD700) !important;
        }

        /* ── Gemini card ── */
        .gemini-card {
            background: linear-gradient(135deg, rgba(255,215,0,0.08), rgba(255,140,0,0.06)) !important;
            border: 2px solid rgba(255,215,0,0.5) !important;
        }
        .gemini-title { color: #FFD700 !important; }

        /* ── File cards ── */
        .file-card {
            border: 2px solid rgba(255,215,0,0.5) !important;
            background: rgba(20,12,0,0.5) !important;
        }

        /* ── Livrable auto ── */
        .livrable-auto {
            background: linear-gradient(135deg, rgba(255,215,0,0.12), rgba(255,140,0,0.08)) !important;
            border: 2px solid #FFD700 !important;
            box-shadow: 0 0 35px rgba(255,215,0,0.25) !important;
        }
        .livrable-auto-title { color: #FFD700 !important; }

        /* ── Sidebar ── */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d0900, #1a1200) !important;
            border-right: 1px solid rgba(255,215,0,0.2) !important;
        }

        /* ── Divider ── */
        hr { border-color: rgba(255,215,0,0.2) !important; }

        /* ── Métriques admin ── */
        [data-testid="stMetric"] {
            background: rgba(255,215,0,0.06) !important;
            border: 1px solid rgba(255,215,0,0.2) !important;
            border-radius: 12px !important;
            padding: 10px !important;
        }

        /* ── Logo container ── */
        .logo-container {
            background: rgba(255,215,0,0.04) !important;
            border: 1px solid rgba(255,215,0,0.12) !important;
        }

        /* ── Glow global sur le body ── */
        body::before {
            content: '';
            position: fixed;
            top: 0; left: 0; right: 0; bottom: 0;
            background: radial-gradient(ellipse at 50% 0%, rgba(255,215,0,0.06) 0%, transparent 60%);
            pointer-events: none;
            z-index: 0;
        }
        </style>
        """, unsafe_allow_html=True)

    # ── THÈME OR EXCLUSIF PREMIUM ──────────────────────────────────
    user_now = st.session_state.get("current_user")
    db_now   = st.session_state.get("db", {})
    ud_now   = db_now.get("users", {}).get(user_now, {}) if user_now else {}
    if is_premium_actif(ud_now):
        st.markdown("""
        <style>
        /* ===== FOND OR PREMIUM ===== */
        .stApp {
            background: #2d1f00 !important;
            background: -webkit-linear-gradient(135deg, #3d2800 0%, #4a3200 20%, #3a2600 40%, #4d3500 60%, #3d2900 80%, #2d1f00 100%) !important;
            background: linear-gradient(135deg, #3d2800 0%, #4a3200 20%, #3a2600 40%, #4d3500 60%, #3d2900 80%, #2d1f00 100%) !important;
            color: #fff8e1 !important;
        }

        /* Halos lumineux dorés très visibles */
        .stApp::before {
            content: '';
            position: fixed;
            inset: 0;
            background:
                radial-gradient(ellipse at 10% 10%, rgba(255,215,0,0.30) 0%, transparent 40%),
                radial-gradient(ellipse at 90% 90%, rgba(255,160,0,0.25) 0%, transparent 40%),
                radial-gradient(ellipse at 50% 50%, rgba(255,200,0,0.12) 0%, transparent 60%),
                radial-gradient(ellipse at 85% 10%, rgba(255,215,0,0.20) 0%, transparent 35%),
                radial-gradient(ellipse at 15% 90%, rgba(255,140,0,0.18) 0%, transparent 35%);
            pointer-events: none;
            z-index: 0;
        }

        /* ===== TITRE PRINCIPAL OR ===== */
        .main-title {
            background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b) !important;
            background-size: 200% auto !important;
            -webkit-background-clip: text !important;
            -webkit-text-fill-color: transparent !important;
            animation: shimmer-gold 3s linear infinite !important;
            text-shadow: none !important;
            filter: drop-shadow(0 0 20px rgba(255,215,0,0.5));
        }
        @keyframes shimmer-gold {
            0%   { background-position: -200% center; }
            100% { background-position:  200% center; }
        }

        /* ===== TABS OR ===== */
        .stTabs [data-baseweb="tab-list"] {
            background-color: rgba(255,215,0,0.05) !important;
            border: 1px solid rgba(255,215,0,0.2) !important;
        }
        .stTabs [data-baseweb="tab"] {
            background-color: rgba(255,215,0,0.07) !important;
            border: 1px solid rgba(255,215,0,0.15) !important;
            color: #FFD700 !important;
        }
        .stTabs [data-baseweb="tab"]:nth-child(2) {
            border: 1px solid rgba(255,215,0,0.5) !important;
            box-shadow: 0 0 15px rgba(255,215,0,0.15) !important;
            background-color: rgba(255,215,0,0.1) !important;
        }
        .stTabs [data-baseweb="tab"]:hover {
            background-color: rgba(255,215,0,0.2) !important;
        }
        .stTabs [aria-selected="true"] {
            background-color: rgba(255,215,0,0.3) !important;
            border: 1px solid #FFD700 !important;
            box-shadow: 0 0 20px rgba(255,215,0,0.4) !important;
        }

        /* ===== INPUTS OR ===== */
        .stTextInput label, .stSelectbox label, .stTextArea label {
            color: #FFD700 !important;
        }
        div[data-baseweb="input"], div[data-baseweb="select"] > div {
            border: 1px solid rgba(255,215,0,0.6) !important;
            background-color: rgba(70,48,0,0.80) !important;
            color: #fff8e1 !important;
        }
        .stTextArea textarea {
            background-color: rgba(65,44,0,0.80) !important;
            color: #fff8e1 !important;
            border: 2px solid #FFD700 !important;
            animation: border-gold 4s linear infinite !important;
        }
        @keyframes border-gold {
            0%   { border-color: #FFD700; box-shadow: 0 0 14px rgba(255,215,0,0.55); }
            33%  { border-color: #FF8C00; box-shadow: 0 0 18px rgba(255,140,0,0.45); }
            66%  { border-color: #b8860b; box-shadow: 0 0 14px rgba(184,134,11,0.45); }
            100% { border-color: #FFD700; box-shadow: 0 0 14px rgba(255,215,0,0.55); }
        }

        /* ===== BOUTONS OR ===== */
        .stButton>button {
            background: linear-gradient(90deg, #8a6200, #c49a00, #FFD700, #c49a00, #8a6200) !important;
            background-size: 200% auto !important;
            color: #1a0f00 !important;
            box-shadow: 0 4px 22px rgba(255,215,0,0.55) !important;
            animation: shimmer-gold 3s linear infinite !important;
            font-weight: 800 !important;
        }
        .stButton>button:hover {
            box-shadow: 0 6px 32px rgba(255,215,0,0.75) !important;
            transform: translateY(-2px) !important;
        }

        /* ===== SIDEBAR OR ===== */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #3a2800 0%, #4a3400 40%, #3a2800 100%) !important;
            border-right: 2px solid rgba(255,215,0,0.4) !important;
            box-shadow: 4px 0 25px rgba(255,215,0,0.12) !important;
        }

        /* ===== INFO-CARD OR ===== */
        .info-card {
            border-left: 4px solid #FFD700 !important;
            background: rgba(255,215,0,0.10) !important;
        }
        .info-title { color: #FFD700 !important; }

        /* ===== FILE-CARD OR ===== */
        .file-card {
            border: 2px solid rgba(255,215,0,0.5) !important;
            background: rgba(255,215,0,0.07) !important;
        }

        /* ===== PROGRESS BAR OR ===== */
        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #b8860b, #FFD700, #FF8C00) !important;
        }

        /* ===== EXPANDER OR ===== */
        .streamlit-expanderHeader {
            color: #FFD700 !important;
            border: 1px solid rgba(255,215,0,0.3) !important;
            background: rgba(255,215,0,0.10) !important;
        }

        /* ===== DIVIDER OR ===== */
        hr { border-color: rgba(255,215,0,0.3) !important; }

        /* ===== METRIC OR ===== */
        [data-testid="stMetric"] {
            background: rgba(255,215,0,0.10) !important;
            border: 1px solid rgba(255,215,0,0.35) !important;
            border-radius: 12px !important;
            padding: 10px !important;
        }
        [data-testid="stMetricValue"] { color: #FFD700 !important; }

        /* ===== SUCCESS / INFO / WARNING OR ===== */
        .stSuccess {
            background: rgba(255,215,0,0.12) !important;
            border: 1px solid rgba(255,215,0,0.4) !important;
            color: #FFD700 !important;
        }
        .stInfo {
            background: rgba(255,215,0,0.08) !important;
            border: 1px solid rgba(255,215,0,0.3) !important;
        }

        /* ===== SUPPORT BTN OR ===== */
        .support-btn {
            border: 2px solid #FFD700 !important;
            color: #FFD700 !important;
        }
        .support-btn:hover {
            background: #FFD700 !important;
            color: #0a0800 !important;
        }

        /* ===== SCROLLBAR OR ===== */
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(#FFD700, #b8860b) !important;
        }
        ::-webkit-scrollbar-track {
            background: #0a0800 !important;
        }
        </style>
        """, unsafe_allow_html=True)

    if st.session_state["is_glowing"]:
        st.markdown('<style>.stApp { animation: glow-pulse 1.5s ease-in-out infinite; }</style>', unsafe_allow_html=True)


def show_auth_page():
    st.markdown("""
    <style>
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
    .auth-card .scanline {
        position: absolute;
        left: 0; right: 0; height: 2px;
        background: linear-gradient(90deg, transparent, rgba(255,215,0,0.12), transparent);
        animation: scanline 4s linear infinite;
        pointer-events: none;
    }
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
    .auth-page .stButton > button {
        background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b, #7a5500) !important;
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
        animation: btn-shimmer 3s linear infinite, btn-float 3.5s ease-in-out infinite !important;
        cursor: pointer !important;
    }
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
                            "joined": str(datetime.now()),
                            "premium": False,
                            "premium_plan": None,
                            "premium_expiry": None,
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

    st.markdown("""
    <div class="auth-secure-badge">
        <span>🔒</span> Connexion sécurisée &nbsp;·&nbsp; <span>⚡</span> Nova AI &nbsp;·&nbsp; <span>🛡️</span> Données protégées
    </div>
    """, unsafe_allow_html=True)

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

    if user and user in db["users"]:
        ud = db["users"][user]
        if ud.get("premium") and not is_premium_actif(ud):
            desactiver_premium(user)
            st.session_state["db"] = load_db()
            db = st.session_state["db"]

    user_data     = db["users"].get(user, {}) if user else {}
    premium_actif = is_premium_actif(user_data)
    premium_info  = get_premium_info(user_data)

    with st.sidebar:
        st.markdown(f"### 👤 {user if user else 'Visiteur'}")
        if user:
            st.markdown(f"📱 **{db['users'][user]['whatsapp']}**")
            if premium_actif and premium_info:
                st.markdown(f"""
                <div style="margin:10px 0;">
                    <span class="badge-premium">⭐ PREMIUM — {premium_info['plan']}</span>
                    <div style="color:rgba(255,215,0,0.7);font-size:0.78rem;margin-top:6px;">
                        ⏳ Expire le {premium_info['expiry']} ({premium_info['jours_restants']}j restants)
                    </div>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown('<span class="badge-free">🔓 Compte Gratuit</span>', unsafe_allow_html=True)
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

    if premium_actif:
        st.markdown("""
        <div style="text-align:center; margin-bottom:20px;">
            <div style="font-size:2.2rem; margin-bottom:-10px; filter:drop-shadow(0 0 15px rgba(255,215,0,0.8));">👑</div>
            <h1 class='main-title' style="
                background: linear-gradient(90deg, #b8860b, #FFD700, #fff5c0, #FFD700, #b8860b);
                background-size: 200% auto;
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
                animation: shimmer-gold 3s linear infinite;
                filter: drop-shadow(0 0 25px rgba(255,215,0,0.6));
                font-size: 3.5rem !important;
                font-weight: 800 !important;
                margin-top: 0;
            ">NOVA AI PLATFORM</h1>
            <div style="
                color: rgba(255,215,0,0.6);
                font-size: 0.75rem;
                letter-spacing: 5px;
                text-transform: uppercase;
                margin-top: -10px;
            ">✦ Membre Premium Actif ✦</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("<h1 class='main-title'>NOVA AI PLATFORM</h1>", unsafe_allow_html=True)

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

    wa_jour = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%20Journalier%20%C3%A0%20600%20FC."
    wa_10j  = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%2010%20Jours%20%C3%A0%201000%20FC."
    wa_30j  = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%2030%20Jours%20%C3%A0%202500%20FC."

    if premium_actif and premium_info:
        st.markdown(f"""
        <div style="background:linear-gradient(135deg,rgba(255,215,0,.12),rgba(255,140,0,.08));
             border:2px solid #FFD700;border-radius:20px;padding:20px;text-align:center;margin-bottom:20px;">
            <div style="font-size:1.4rem;font-weight:800;color:#FFD700;">
                ⭐ MEMBRE PREMIUM ACTIF — {premium_info['plan']}
            </div>
            <div style="color:rgba(255,255,255,.7);margin-top:6px;">
                🤖 Génération IA instantanée activée · Expire le <b>{premium_info['expiry']}</b>
                ({premium_info['jours_restants']} jour(s) restant(s))
            </div>
        </div>""", unsafe_allow_html=True)
    else:
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

    if st.session_state["show_premium_modal"]:
        st.markdown("""
            <div style="
                background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
                border: 2px solid #FFD700;
                border-radius: 24px;
                padding: 35px 25px 30px 25px;
                margin: 10px 0 30px 0;
                box-shadow: 0 0 60px rgba(255,215,0,0.25);
            ">
                <h2 style="text-align:center; color:#FFD700; font-size:1.7rem; font-weight:800; margin-bottom:6px; letter-spacing:1px;">
                    ⭐ CHOISISSEZ VOTRE FORMULE NOVA PREMIUM
                </h2>
                <p style="text-align:center; color:rgba(255,255,255,0.55); margin-bottom:30px; font-size:0.95rem;">
                    Sélectionnez le plan qui correspond à vos besoins
                </p>
            </div>
        """, unsafe_allow_html=True)

        col1_p, col2_p, col3_p = st.columns(3)

        with col1_p:
            st.markdown("""
                <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(255,215,0,0.4); border-radius: 18px; padding: 28px 16px; text-align: center; min-height: 300px;">
                    <div style="font-size:2.5rem; margin-bottom:10px;">🌅</div>
                    <div style="color:#FFD700; font-weight:800; font-size:1.1rem; margin-bottom:6px; text-transform:uppercase;">Journalier</div>
                    <div style="color:white; font-size:2rem; font-weight:800; margin:10px 0;">600 FC</div>
                    <div style="color:rgba(255,255,255,0.45); font-size:0.8rem; margin-bottom:16px;">/ par jour</div>
                    <div style="background:rgba(255,215,0,0.1); border-radius:10px; padding:10px; margin-bottom:22px;">
                        <span style="color:#FFD700; font-size:0.9rem;">⚡ 1,5 génération IA / jour</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<a href="{wa_jour}" target="_blank" style="display:block; background:linear-gradient(45deg,#FFD700,#FF8C00); color:#000; font-weight:800; padding:12px; border-radius:50px; text-decoration:none; font-size:1rem; text-align:center; margin-top:10px;">Choisir cette formule</a>', unsafe_allow_html=True)

        with col2_p:
            st.markdown("""
                <div style="background: linear-gradient(135deg, rgba(0,210,255,0.15), rgba(58,123,213,0.15)); border: 2px solid #00d2ff; border-radius: 18px; padding: 28px 16px; text-align: center; min-height: 300px; position: relative;">
                    <div style="background:linear-gradient(90deg,#00d2ff,#3a7bd5); color:white; font-size:0.75rem; font-weight:800; padding:4px 16px; border-radius:20px; display:inline-block; margin-bottom:12px;">⭐ POPULAIRE</div>
                    <div style="font-size:2.5rem; margin-bottom:10px;">🔟</div>
                    <div style="color:#00d2ff; font-weight:800; font-size:1.1rem; margin-bottom:6px; text-transform:uppercase;">10 Jours</div>
                    <div style="color:white; font-size:2rem; font-weight:800; margin:10px 0;">1 000 FC</div>
                    <div style="color:rgba(255,255,255,0.45); font-size:0.8rem; margin-bottom:16px;">/ 10 jours</div>
                    <div style="background:rgba(0,210,255,0.1); border-radius:10px; padding:10px; margin-bottom:22px;">
                        <span style="color:#00d2ff; font-size:0.9rem;">⚡ 4 générations IA / jour</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<a href="{wa_10j}" target="_blank" style="display:block; background:linear-gradient(45deg,#00d2ff,#3a7bd5); color:#fff; font-weight:800; padding:12px; border-radius:50px; text-decoration:none; font-size:1rem; text-align:center; margin-top:10px;">Choisir cette formule</a>', unsafe_allow_html=True)

        with col3_p:
            st.markdown("""
                <div style="background: rgba(255,255,255,0.05); border: 1px solid rgba(46,204,113,0.4); border-radius: 18px; padding: 28px 16px; text-align: center; min-height: 300px;">
                    <div style="font-size:2.5rem; margin-bottom:10px;">👑</div>
                    <div style="color:#2ecc71; font-weight:800; font-size:1.1rem; margin-bottom:6px; text-transform:uppercase;">30 Jours</div>
                    <div style="color:white; font-size:2rem; font-weight:800; margin:10px 0;">2 500 FC</div>
                    <div style="color:rgba(255,255,255,0.45); font-size:0.8rem; margin-bottom:16px;">/ 30 jours</div>
                    <div style="background:rgba(46,204,113,0.1); border-radius:10px; padding:10px; margin-bottom:22px;">
                        <span style="color:#2ecc71; font-size:0.9rem;">⚡ 8,5 générations IA / jour</span>
                    </div>
                </div>
            """, unsafe_allow_html=True)
            st.markdown(f'<a href="{wa_30j}" target="_blank" style="display:block; background:linear-gradient(45deg,#2ecc71,#27ae60); color:#fff; font-weight:800; padding:12px; border-radius:50px; text-decoration:none; font-size:1rem; text-align:center; margin-top:10px;">Choisir cette formule</a>', unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        col_close = st.columns([1, 2, 1])[1]
        with col_close:
            if st.button("✕ Fermer", key="close_premium"):
                st.session_state["show_premium_modal"] = False
                st.rerun()

    tab1, tab2 = st.tabs(["🚀 DÉPLOYER UNE TÂCHE", "📂 MES LIVRABLES (CLOUD)"])

    SERVICES_GEMINI = [
        "📝 Exposé scolaire complet IA",
        "📝 Création de Sujets & Examens",
        "👔 CV & Lettre de Motivation",
        "⚙️ Pack Office (Word/Excel/PPT)",
        "📊 Data & Excel Analytics",
    ]

    with tab1:
        if st.session_state["premium_livrable"]:
            lv = st.session_state["premium_livrable"]
            st.markdown(f"""
            <div class="livrable-auto">
                <div class="livrable-auto-title">✅ Votre document est prêt !</div>
                <div style="color:rgba(255,255,255,.7);margin-top:6px;">
                    Généré en {lv['duree']}s · Service : <b>{lv['service']}</b>
                </div>
            </div>""", unsafe_allow_html=True)
            st.download_button(
                label="📥 TÉLÉCHARGER MON DOCUMENT",
                data=lv["buf"], file_name=lv["nom"], mime=lv["mime"],
                use_container_width=True
            )
            st.info("💡 Votre fichier est aussi disponible dans **📂 Mes Livrables** ci-dessus.")
            if st.button("🔄 Nouvelle mission", key="reset_livrable"):
                st.session_state["premium_livrable"] = None
                st.rerun()
            st.stop()

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

        SERVICE_SAISIE = "📊 Data & Excel Analytics"

        if service != st.session_state["last_service_seen"]:
            st.session_state["last_service_seen"] = service
            st.session_state["warning_triggered"] = False
            st.session_state["show_service_warning"] = False
            if service != SERVICE_SAISIE and service in SERVICE_PREREQUIS:
                st.session_state["show_service_warning"] = True

        if st.session_state["show_service_warning"] and service in SERVICE_PREREQUIS and service != SERVICE_SAISIE:
            info = SERVICE_PREREQUIS[service]

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

        st.markdown("#### 📝 Spécifications de la mission")
        prompt = st.text_area("Cahier des charges Nova", height=150, placeholder="Détaillez votre projet pour une exécution parfaite...")

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

        if premium_actif and service in SERVICES_GEMINI:
            _udata_q = st.session_state["db"]["users"].get(user, {})
            _restant  = quota_restant(_udata_q)
            _plan_q   = _udata_q.get("premium_plan", "")
            _quota_q  = PLANS_PREMIUM.get(_plan_q, {}).get("generations", 0)
            _used_q, _ = get_gen_quota(_udata_q)
            _couleur_quota = "#2ecc71" if _restant > 1 else ("#FFD700" if _restant == 1 else "#e74c3c")
            st.markdown(f"""
            <div style="background:linear-gradient(135deg,rgba(255,215,0,.1),rgba(255,140,0,.06));
                 border:1px solid rgba(255,215,0,.5);border-radius:12px;padding:12px 18px;margin:10px 0;">
                <span style="color:#FFD700;font-weight:800;">⚡ PREMIUM — Génération IA automatique activée</span>
                <span style="color:rgba(255,255,255,.5);font-size:.8rem;display:block;margin-top:3px;">
                    Votre document sera généré et livré en moins d'1 minute.
                </span>
                <span style="color:{_couleur_quota};font-size:.85rem;font-weight:700;display:block;margin-top:6px;">
                    📊 Générations aujourd'hui : {_used_q}/{_quota_q} utilisées — 
                    {'✅ ' + str(_restant) + ' restante(s)' if _restant > 0 else '🚫 Quota atteint — demande manuelle uniquement'}
                </span>
            </div>""", unsafe_allow_html=True)

        label_btn = "⚡ GÉNÉRER MAINTENANT AVEC L'IA NOVA" if (premium_actif and service in SERVICES_GEMINI) else "ACTIVER L'ALGORITHME NOVA"
        if st.button(label_btn):
            if not user:
                st.session_state["view"] = "auth"
                st.rerun()

            elif premium_actif and service in SERVICES_GEMINI and not champs_manquants:
                import threading

                # ── VÉRIFICATION DU QUOTA DE GÉNÉRATIONS ──────────────────
                user_data_frais = st.session_state["db"]["users"].get(user, {})
                restant = quota_restant(user_data_frais)
                plan_actuel = user_data_frais.get("premium_plan", "")
                quota_max = PLANS_PREMIUM.get(plan_actuel, {}).get("generations", 0)
                used_auj, _ = get_gen_quota(user_data_frais)

                if restant <= 0:
                    st.error(f"🚫 Limite de générations atteinte pour aujourd'hui ({used_auj}/{quota_max} utilisées).")
                    st.info("💡 Votre quota se renouvelle demain, ou contactez Nova pour upgrader votre plan.")
                    # Basculer en mode demande manuelle
                    st.session_state["is_glowing"] = True
                    st.rerun()
                else:
                    processing_box = st.empty()
                    processing_box.markdown(f"""
                    <div class="nova-processing">
                        <div class="nova-processing-title">⚡ GÉNÉRATION EN COURS</div>
                        <div class="nova-processing-sub">Génération automatique · Quota restant après cette génération : {restant - 1}/{quota_max}</div>
                    </div>""", unsafe_allow_html=True)

                    barre = st.progress(0)
                    label_prog = st.empty()
                    t_start = time.time()
                    result_holder = {}

                    def generer():
                        try:
                            contenu = generer_avec_gemini(service, prompt, user)
                            if contenu.startswith("❌"):
                                result_holder["erreur"] = contenu
                                return
                            if service == "📊 Data & Excel Analytics":
                                buf  = creer_xlsx(prompt, user)
                                nom  = f"{user}_{service[:20].strip()}.xlsx".replace(" ", "_").replace("/", "-")
                                mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                            else:
                                buf  = creer_docx(contenu, service, user)
                                nom  = f"{user}_{service[:20].strip()}.docx".replace(" ", "_").replace("/", "-")
                                mime = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                            result_holder["buf"]  = buf
                            result_holder["nom"]  = nom
                            result_holder["mime"] = mime
                        except Exception as e:
                            result_holder["erreur"] = f"❌ Erreur : {e}"

                    thread = threading.Thread(target=generer)
                    thread.start()

                    pct = 0
                    while thread.is_alive():
                        elapsed = time.time() - t_start
                        pct = min(int(elapsed / 60 * 90), 90)
                        barre.progress(pct)
                        label_prog.markdown(f"<p style='text-align:center;color:#FFD700;font-weight:bold;'>⚡ Génération en cours... {pct}%</p>", unsafe_allow_html=True)
                        time.sleep(0.5)
                    thread.join()

                    barre.progress(100)
                    label_prog.markdown("<p style='text-align:center;color:#2ecc71;font-weight:bold;'>✅ Document généré !</p>", unsafe_allow_html=True)
                    time.sleep(0.8)
                    barre.empty(); label_prog.empty(); processing_box.empty()

                    duree = int(time.time() - t_start)

                    if "erreur" in result_holder:
                        st.error(result_holder["erreur"])
                        st.info("💡 Votre demande a été transmise à l'équipe Nova pour traitement manuel.")
                        new_req = {
                            "id": hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8],
                            "user": user, "service": service,
                            "desc": prompt, "whatsapp": normalize_wa(wa_display),
                            "status": "Traitement Nova en cours...", "incomplet": False,
                            "champs_manquants": [], "timestamp": str(datetime.now()),
                        }
                        st.session_state["db"]["demandes"].append(new_req)
                        save_demande(new_req)
                    else:
                        # Incrémenter le compteur de générations
                        incrementer_gen(user)
                        save_lien(user, service, f"__local__{result_holder['nom']}", datetime.now().strftime("%d/%m/%Y"))
                        # Email admin — Gemini a déjà répondu
                        wa_display_local = st.session_state["db"]["users"].get(user, {}).get("whatsapp", "—")
                        envoyer_notification_gemini_ok(user, wa_display_local, service, result_holder["nom"])
                        st.session_state["premium_livrable"] = {
                            "buf":     result_holder["buf"],
                            "nom":     result_holder["nom"],
                            "mime":    result_holder["mime"],
                            "service": service,
                            "duree":   duree,
                        }
                        st.session_state["db"] = load_db()
                        st.rerun()

            else:
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
            envoyer_notification(
                client_nom  = user if user else "Visiteur",
                client_wa   = normalize_wa(wa_display) if wa_display else "(non renseigné)",
                service     = service,
                description = prompt if prompt else "(aucune description fournie)"
            )
            st.session_state["db"] = load_db()
            st.session_state["is_glowing"] = False
            progress_placeholder.empty()
            status_text.empty()
            if user:
                st.success("✅ Mission enregistrée ! L'équipe Nova examinera votre demande.")

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

            if st.session_state["premium_livrable"]:
                lv = st.session_state["premium_livrable"]
                st.markdown(f"""
                <div class="livrable-auto">
                    <div class="livrable-auto-title">⚡ Livrable IA Premium</div>
                    <div style="color:rgba(255,255,255,.7);margin-top:4px;">Généré en {lv['duree']}s · {lv['service']}</div>
                </div>""", unsafe_allow_html=True)
                st.download_button(
                    "📥 TÉLÉCHARGER MON DOCUMENT",
                    data=lv["buf"], file_name=lv["nom"], mime=lv["mime"],
                    use_container_width=True
                )
                st.divider()

            if user_links:
                for link in user_links:
                    if link["url"].startswith("__local__"):
                        st.markdown(f"""
                        <div class="file-card" style="border-color:rgba(255,215,0,.5);">
                            <div style="display:flex;justify-content:space-between;align-items:center;">
                                <div>
                                    <h3 style="color:#FFD700;margin:0;">⭐ {link['name']}</h3>
                                    <p style="color:#aaa;font-size:.85rem;margin:5px 0;">Généré le {link.get('date',"Aujourd'hui")} · Téléchargez depuis l'onglet Déployer</p>
                                </div>
                                <span class="badge-premium">IA AUTO</span>
                            </div>
                        </div>""", unsafe_allow_html=True)
                    else:
                        st.markdown(f"""
                        <div class="file-card">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <div>
                                    <h3 style="color:#00d2ff; margin:0;">💎 {link['name']}</h3>
                                    <p style="color:#aaa; font-size:0.85rem; margin: 5px 0;">Finalisé le {link.get('date', "Aujourd'hui")}</p>
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
            admin_tab1, admin_tab2 = st.tabs(["📋 MISSIONS", "👑 GESTION PREMIUM"])

            with admin_tab1:
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
                    client_premium   = is_premium_actif(current_db["users"].get(client_nom, {}))

                    if i > 0:
                        st.divider()

                    col_info, col_badge = st.columns([4, 1])
                    with col_info:
                        st.markdown(f"**Mission `#{req_id}`** · {timestamp}" + (" — ⚠️ *Incomplet : " + ", ".join(champs_manquants) + "*" if est_incomplet else ""))
                        st.markdown(f"👤 **Client :** {client_nom}")
                        st.markdown(f"📱 **WhatsApp :** {client_wa}")
                        st.markdown(f"🛠️ **Service demandé :** {service}")
                        st.markdown(f"📝 **Détails de la demande :** {description}")
                    with col_badge:
                        if client_premium:
                            st.markdown('<span class="badge-premium">⭐ PREMIUM</span>', unsafe_allow_html=True)
                        else:
                            st.markdown('<span class="badge-free">🔓 Gratuit</span>', unsafe_allow_html=True)

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

                    col_rejet, col_recu, col_succes = st.columns(3)
                    with col_rejet:
                        st.markdown(f'<a href="{wa_url(client_wa, msg_rejet)}" target="_blank" style="display:block; text-align:center; padding:10px; border-radius:10px; background:rgba(231,76,60,0.15); border:1px solid rgba(231,76,60,0.5); color:#e74c3c; font-weight:700; text-decoration:none;">❌ Rejeter</a>', unsafe_allow_html=True)
                    with col_recu:
                        st.markdown(f'<a href="{wa_url(client_wa, msg_recu)}" target="_blank" style="display:block; text-align:center; padding:10px; border-radius:10px; background:rgba(255,215,0,0.1); border:1px solid rgba(255,215,0,0.4); color:#FFD700; font-weight:700; text-decoration:none;">📬 Reçu</a>', unsafe_allow_html=True)
                    with col_succes:
                        st.markdown(f'<a href="{wa_url(client_wa, msg_succes)}" target="_blank" style="display:block; text-align:center; padding:10px; border-radius:10px; background:rgba(46,204,113,0.15); border:1px solid rgba(46,204,113,0.5); color:#2ecc71; font-weight:700; text-decoration:none;">✅ Succès</a>', unsafe_allow_html=True)

                    if service in SERVICES_GEMINI:
                        st.markdown("<br>", unsafe_allow_html=True)
                        st.markdown(f"""
                        <div class="gemini-card">
                            <div class="gemini-title">🤖 GEMINI AI — GÉNÉRATION AUTOMATIQUE DISPONIBLE</div>
                            <div class="gemini-sub">Génère le document complet en .docx en 30-60 secondes</div>
                        </div>
                        """, unsafe_allow_html=True)

                        if st.button(f"🔍 Voir modèles disponibles", key=f"diag_{req_id}"):
                            with st.spinner("Interrogation de l'API Gemini..."):
                                modeles_dispo = get_modeles_disponibles(st.secrets["GEMINI_API_KEY"])
                            if modeles_dispo:
                                st.success(f"✅ {len(modeles_dispo)} modèles trouvés :")
                                for m in modeles_dispo:
                                    st.code(m)
                            else:
                                st.error("❌ Aucun modèle disponible — vérifiez votre clé API.")

                        if st.button(f"⚡ APPROUVER & GÉNÉRER AVEC GEMINI", key=f"gemini_{req_id}", use_container_width=True):
                            with st.spinner("🔍 Détection automatique du meilleur modèle disponible..."):
                                modeles_dispo = get_modeles_disponibles(st.secrets["GEMINI_API_KEY"])
                                if modeles_dispo:
                                    st.info(f"✅ Modèle sélectionné : **{modeles_dispo[0]}**")
                                else:
                                    st.error("❌ Aucun modèle Gemini disponible pour cette clé API.")
                            with st.spinner("🤖 Gemini génère le document... (30-60 secondes)"):
                                contenu = generer_avec_gemini(service, description, client_nom)

                            if contenu.startswith("❌"):
                                st.error(contenu)
                            else:
                                st.session_state["gemini_results"][req_id] = {
                                    "contenu": contenu,
                                    "service": service,
                                    "client": client_nom
                                }
                                st.success("✅ Document généré avec succès !")
                                st.rerun()

                        if req_id in st.session_state["gemini_results"]:
                            result = st.session_state["gemini_results"][req_id]

                            with st.expander("👁️ Aperçu du contenu généré", expanded=False):
                                st.markdown(result["contenu"])

                            try:
                                SERVICE_EXCEL = "📊 Data & Excel Analytics"
                                if result["service"] == SERVICE_EXCEL:
                                    buf = creer_xlsx(result.get("desc", ""), result["client"])
                                    nom_fichier = f"{client_nom}_Suivi_Depenses.xlsx".replace(" ", "_")
                                    st.download_button(
                                        label="📥 TÉLÉCHARGER LE FICHIER EXCEL (.xlsx)",
                                        data=buf,
                                        file_name=nom_fichier,
                                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                        key=f"dl_{req_id}",
                                        use_container_width=True
                                    )
                                    st.info("📊 Fichier Excel avec 3 feuilles : Saisie, Catégories, Tableau de Bord")
                                else:
                                    buf = creer_docx(result["contenu"], result["service"], result["client"])
                                    nom_fichier = f"{client_nom}_{result['service'][:20].strip()}.docx".replace(" ", "_").replace("/", "-")
                                    st.download_button(
                                        label="📥 TÉLÉCHARGER LE DOCUMENT WORD (.docx)",
                                        data=buf,
                                        file_name=nom_fichier,
                                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                                        key=f"dl_{req_id}",
                                        use_container_width=True
                                    )
                            except Exception as e:
                                st.error(f"Erreur génération fichier : {e}")

                            st.info("💡 Télécharge → upload sur Google Drive → colle le lien ci-dessous pour livrer au client.")

                    st.markdown("<br>", unsafe_allow_html=True)
                    url_dl = st.text_input("🔗 Lien de livraison (Google Drive...)", key=f"url_{i}", placeholder="https://drive.google.com/...")
                    if st.button("📦 LIVRER LA MISSION AU CLIENT", key=f"btn_{i}", use_container_width=True):
                        if url_dl:
                            save_lien(req['user'], req['service'], url_dl, datetime.now().strftime("%d/%m/%Y"))
                            delete_demande(req['id'])
                            if req_id in st.session_state["gemini_results"]:
                                del st.session_state["gemini_results"][req_id]
                            st.session_state["db"] = load_db()
                            st.success(f"✅ Mission livrée à {client_nom} !")
                            st.rerun()

            with admin_tab2:
                st.markdown("### 👑 Gestion des membres Premium")
                total  = len(current_db["users"])
                prems  = [u for u, d in current_db["users"].items() if is_premium_actif(d)]
                c1, c2, c3 = st.columns(3)
                c1.metric("👥 Total membres", total)
                c2.metric("⭐ Premium actifs", len(prems))
                c3.metric("🔓 Gratuits", total - len(prems))
                st.divider()

                st.markdown("#### ➕ Activer / Gérer un Premium")
                co1, co2, co3 = st.columns([2, 2, 1])
                with co1:
                    uid_target = st.selectbox("Membre", options=list(current_db["users"].keys()),
                        format_func=lambda u: f"{u} {'⭐' if is_premium_actif(current_db['users'][u]) else '🔓'}")
                with co2:
                    plan_ch = st.selectbox("Plan", list(PLANS_PREMIUM.keys()),
                        format_func=lambda p: f"{PLANS_PREMIUM[p]['emoji']} {p} — {PLANS_PREMIUM[p]['prix']}")
                with co3:
                    st.markdown("<br>", unsafe_allow_html=True)
                    if st.button("⚡ ACTIVER", key="btn_act_global"):
                        activer_premium(uid_target, plan_ch)
                        st.session_state["db"] = load_db()
                        st.success(f"✅ Premium **{plan_ch}** activé pour **{uid_target}** !")
                        st.rerun()

                st.divider()
                filtre = st.radio("Afficher", ["Tous", "Premium uniquement", "Gratuits uniquement"], horizontal=True)

                for uid_m, udata in current_db["users"].items():
                    p_actif = is_premium_actif(udata)
                    p_info  = get_premium_info(udata)
                    if filtre == "Premium uniquement" and not p_actif: continue
                    if filtre == "Gratuits uniquement" and p_actif:    continue

                    col_m, col_a = st.columns([3, 2])
                    with col_m:
                        badge = f'<span class="badge-premium">⭐ {udata.get("premium_plan","—")}</span>' if p_actif else '<span class="badge-free">🔓 Gratuit</span>'
                        exp_txt = f"<br><small style='color:rgba(255,215,0,.6);'>Expire : {p_info['expiry']} ({p_info['jours_restants']}j)</small>" if p_actif and p_info else ""
                        st.markdown(f"""<div class="admin-premium-row">
                            <div>
                                <div class="admin-user-name">👤 {uid_m}</div>
                                <div class="admin-user-meta">📱 {udata.get('whatsapp','—')} · {str(udata.get('joined',''))[:10]}</div>
                                {exp_txt}
                            </div>
                            <div>{badge}</div>
                        </div>""", unsafe_allow_html=True)
                    with col_a:
                        if p_actif:
                            cp1, cp2 = st.columns(2)
                            with cp1:
                                ext_p = st.selectbox("", list(PLANS_PREMIUM.keys()), key=f"ext_{uid_m}",
                                    format_func=lambda p: f"{PLANS_PREMIUM[p]['emoji']} {p}")
                                if st.button("➕ Prolonger", key=f"pro_{uid_m}"):
                                    curr_exp = datetime.fromisoformat(udata.get("premium_expiry", datetime.now().isoformat()))
                                    new_exp  = max(curr_exp, datetime.now()) + timedelta(days=PLANS_PREMIUM[ext_p]["jours"])
                                    update_premium_status(uid_m, True, ext_p, new_exp.isoformat())
                                    st.session_state["db"] = load_db()
                                    st.success(f"✅ Prolongé jusqu'au {new_exp.strftime('%d/%m/%Y')} !")
                                    st.rerun()
                            with cp2:
                                st.markdown("<br>", unsafe_allow_html=True)
                                if st.button("🗑️ Révoquer", key=f"rev_{uid_m}"):
                                    desactiver_premium(uid_m)
                                    st.session_state["db"] = load_db()
                                    st.warning(f"Premium révoqué pour {uid_m}.")
                                    st.rerun()
                        else:
                            ap = st.selectbox("", list(PLANS_PREMIUM.keys()), key=f"act_{uid_m}",
                                format_func=lambda p: f"{PLANS_PREMIUM[p]['emoji']} {p}")
                            if st.button("⚡ Activer", key=f"actbtn_{uid_m}"):
                                activer_premium(uid_m, ap)
                                st.session_state["db"] = load_db()
                                st.success(f"✅ Premium activé pour {uid_m} !")
                                st.rerun()


inject_custom_css()

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

if st.session_state["view"] == "auth" and st.session_state["current_user"] is None:
    show_auth_page()
else:
    main_dashboard()
