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


def generer_avec_gemini(service, description, client_nom):
    try:
        import urllib.request as _ur
        import urllib.error

        api_key = st.secrets["GEMINI_API_KEY"]

        # ================================================================
        # PROMPT — EXPOSÉ SCOLAIRE (Système scolaire ivoirien & africain)
        # ================================================================
        if "Exposé" in service:
            prompt = f"""Tu es un expert académique spécialisé dans le système scolaire ivoirien et africain francophone.
Tu connais parfaitement les programmes officiels de Côte d'Ivoire et des pays d'Afrique francophone (Sénégal, Mali, Burkina Faso, Bénin, Togo, Cameroun, Guinée, Congo, Gabon, etc.).

=== SYSTÈME SCOLAIRE DE RÉFÉRENCE ===

PRIMAIRE (Côte d'Ivoire) :
- Niveaux : CP1, CP2, CE1, CE2, CM1, CM2
- Matières : Lecture, Écriture, Calcul, Sciences d'Éveil, Histoire-Géographie, Éducation Civique et Morale, EPS
- Examen de fin de cycle : CEPE (Certificat d'Études Primaires Élémentaires) — fin CM2
- Ton attendu : Simple, concret, illustré d'exemples locaux africains (animaux, fleuves, villages, personnages historiques africains)
- Longueur : 1 à 2 pages, vocabulaire accessible, phrases courtes

COLLÈGE — 1er Cycle du Secondaire :
- Niveaux : 6ème, 5ème, 4ème, 3ème
- Matières : Français, Mathématiques, Sciences Physiques et Chimie, SVT (Sciences de la Vie et de la Terre), Histoire-Géographie, Anglais (LV1), Espagnol (LV2 optionnel), EPS, EDHC (Éducation aux Droits de l'Homme et à la Citoyenneté)
- Examen de fin de cycle : BEPC (Brevet d'Études du Premier Cycle) — fin 3ème
- Auteurs ivoiriens & africains fréquemment étudiés : Bernard Dadié ("Climbié", "Un Nègre à Paris"), Ahmadou Kourouma ("Allah n'est pas obligé"), Camara Laye ("L'Enfant Noir"), Mongo Beti, Ferdinand Oyono, Cheikh Hamidou Kane
- Ton attendu : Structuré et progressif, exemples tirés du quotidien africain et ivoirien
- Longueur : 2 à 4 pages selon le niveau

LYCÉE — 2ème Cycle du Secondaire :
- Niveaux : 2nde, 1ère, Terminale
- SÉRIES DU BAC IVOIRIEN — à respecter impérativement :
  * Série A1 : Lettres, Philosophie et Arts — matières phares : Français/Philosophie, Histoire-Géo, Langues vivantes, Latin
  * Série A2 : Lettres et Langues Vivantes — matières phares : Français, Anglais, Espagnol, Histoire-Géo
  * Série B  : Sciences Économiques et Sociales — matières phares : Économie générale, Économie d'entreprise, Comptabilité, Droit, Maths
  * Série C  : Mathématiques et Sciences Physiques — matières phares : Maths, Physique-Chimie, SVT (coefficient réduit)
  * Série D  : Sciences de la Nature et de la Vie — matières phares : SVT, Maths, Sciences Physiques, Histoire-Géo
  * Série E  : Mathématiques et Technologie — matières phares : Maths, Technologie industrielle, Sciences Physiques
  * Série F  : Sciences et Technologies Industrielles (plusieurs sous-séries : F1, F2, F3)
  * Série G  : Sciences et Technologies de Gestion — matières phares : Comptabilité, Informatique de gestion, Économie, Droit
  * Série H  : Informatique — matières phares : Informatique, Maths, Algorithmique, Réseaux
- Examen de fin de cycle : BAC (Baccalauréat ivoirien) — fin de Terminale
- Ton attendu : Analytique, argumenté, avec plan dialectique ou thématique selon la matière ; vocabulaire soutenu
- Longueur : 3 à 6 pages selon le niveau et la série

UNIVERSITÉ / ENSEIGNEMENT SUPÉRIEUR :
- Système LMD : Licence (L1, L2, L3), Master (M1, M2), Doctorat
- Principales institutions ivoiriennes : Université Félix Houphouët-Boigny (Cocody-Abidjan), Université Alassane Ouattara (Bouaké), Université Lorougnon Guédé (Daloa), Université Jean Lorougnon Guédé, INP-HB (Institut National Polytechnique Félix Houphouët-Boigny — Yamoussoukro), Grandes Écoles : ESCAE, HEC-CI, ESA, INPHB, CAFOP (pour les enseignants)
- Filières : Droit, Sciences Économiques, Médecine, Pharmacie, Lettres et Civilisations, Sciences et Technologies, Informatique, Sciences Sociales, STAPS, etc.
- Ton attendu : Académique, critique, avec références théoriques, auteurs cités, notes de bas de page si besoin
- Longueur : 5 à 10 pages minimum

CONTEXTE CULTUREL & GÉOGRAPHIQUE IVOIRIEN À INTÉGRER DANS LES EXEMPLES :
- Géographie : Abidjan (capitale économique), Yamoussoukro (capitale politique), Bouaké, Daloa, Korhogo, Man, San-Pédro | Fleuves : Comoé, Bandama, Sassandra, N'zi | Forêts : Banco, Taï | Lac Kossou | Golfe de Guinée
- Histoire & personnalités : Félix Houphouët-Boigny (père fondateur), Laurent Gbagbo, Alassane Ouattara, Samory Touré, Behanzin, Shaka Zulu (Afrique) | Sur la scène panafricaine : Thomas Sankara, Kwame Nkrumah, Patrice Lumumba, Nelson Mandela, Julius Nyerere
- Économie : cacao (1er producteur mondial), café, anacarde (noix de cajou), caoutchouc, palmier à huile | FCFA (franc CFA) | UEMOA, CEDEAO | Port autonome d'Abidjan | BVRM (Bourse Régionale des Valeurs Mobilières)
- Culture & traditions : masques Baoulé, Dan (Yacouba), Gouro, Sénoufo | Fête du Dipri (Gomon), Fête des Ignames, Fête de la Paix (Abidjan) | Musique : coupé-décalé, zouglou, afrobeat ivoirien | Tenues : boubou, kita, pagne wax

=== MISSION ===

Rédige un exposé scolaire COMPLET, STRUCTURÉ et PROFESSIONNEL basé sur cette demande :

{description}

RÈGLES ABSOLUES :
- Identifie précisément le niveau scolaire mentionné (CP1 à CM2 = Primaire | 6ème à 3ème = Collège | 2nde/1ère/Tle + série = Lycée | L1-Doctorat = Université)
- Si le niveau n'est pas précisé, déduis-le depuis le sujet et adapte-toi intelligemment
- Adapte le vocabulaire, la profondeur d'analyse et la longueur au niveau détecté
- Intègre des exemples concrets tirés du contexte ivoirien et africain quand c'est pertinent
- Respecte les programmes officiels ivoiriens pour les matières concernées
- N'utilise JAMAIS de notation LaTeX ($, \\, \\frac, \\text) — écris toujours en texte clair
- Rédige exclusivement en français, avec une orthographe irréprochable

Structure OBLIGATOIRE :

# PAGE DE GARDE
Titre de l'exposé :
Matière :
Niveau scolaire / Série (si lycée) :
Établissement :
Présenté par :
Date :
Année scolaire :

# INTRODUCTION
(Accroche contextuelle liée à la réalité ivoirienne ou africaine si possible, problématique claire, annonce du plan)

# DÉVELOPPEMENT

## I. [Titre de la première grande partie]
### 1.1 [Sous-partie]
### 1.2 [Sous-partie]

## II. [Titre de la deuxième grande partie]
### 2.1 [Sous-partie]
### 2.2 [Sous-partie]

## III. [Titre de la troisième grande partie — si pertinent selon le niveau]
### 3.1 [Sous-partie]
### 3.2 [Sous-partie]

# CONCLUSION
(Synthèse des idées principales, réponse à la problématique, ouverture sur un enjeu actuel en lien avec l'Afrique ou la Côte d'Ivoire si possible)

# BIBLIOGRAPHIE
(Manuels scolaires ivoiriens si applicable, auteurs africains, sources pertinentes)

Rédige en français. Minimum 3 pages complètes et détaillées."""

        # ================================================================
        # PROMPT — SUJETS & EXAMENS (Système scolaire ivoirien & africain)
        # ================================================================
        elif "Examens" in service or "Sujets" in service:
            prompt = f"""Tu es un professeur expérimenté et un concepteur officiel de sujets d'examens pour le système scolaire ivoirien et africain francophone.
Tu maîtrises parfaitement les formats d'épreuves du CEPE, BEPC et BAC ivoirien, ainsi que les évaluations universitaires.

=== SYSTÈME SCOLAIRE ET FORMATS D'EXAMENS DE RÉFÉRENCE ===

PRIMAIRE — CEPE :
- Niveaux concernés : CM1, CM2
- Matières et formats officiels CEPE :
  * Dictée + Questions de grammaire/orthographe
  * Rédaction (narration simple, description, lettre)
  * Calcul (opérations, problèmes arithmétiques concrets)
  * Sciences d'Éveil (questions sur le corps humain, l'environnement, l'hygiène)
  * Histoire-Géographie (questions sur la Côte d'Ivoire et l'Afrique)
- Barème : /20 par matière, QCM simple ou questions ouvertes courtes
- Contexte des problèmes : marchés ivoiriens, villages, plantations de cacao/café, animaux africains

COLLÈGE — BEPC :
- Niveaux concernés : 6ème, 5ème, 4ème, 3ème (BEPC en fin de 3ème)
- Formats officiels BEPC par matière :
  * Français : Texte support (auteur africain de préférence) + questions de compréhension + vocabulaire + grammaire/conjugaison + production écrite (rédaction, lettre formelle, dialogue)
  * Mathématiques : Exercices de calcul pur + problème contextualisé + géométrie (théorème de Thalès, Pythagore, constructions) + statistiques
  * Sciences Physiques : Exercice Physique (mécanique, électricité, optique) + Exercice Chimie (atomes, molécules, réactions)
  * SVT : Questions de cours + schéma légendé à compléter + étude de document (tableau, graphique)
  * Histoire-Géo : Étude de document (texte ou carte) + paragraphe argumenté + croquis de carte
  * Anglais : Texte + compréhension + vocabulaire + expression écrite
  * EDHC : Questions sur la citoyenneté, les droits, les institutions ivoiriennes
- Durée typique : 2h à 4h selon la matière
- Barème : sur 20 points

LYCÉE — BAC IVOIRIEN :
- Niveaux : 2nde, 1ère, Terminale
- Formats officiels par série et matière :

  SÉRIE A1/A2 (Lettres) :
  * Français/Philo : Dissertation littéraire ou philosophique (thèse, antithèse, synthèse) OU Commentaire composé OU Résumé + Discussion + Écriture d'invention
  * Histoire-Géo : Composition (introduction + plan + conclusion) + Étude de document(s)
  * Langues vivantes : Compréhension de texte + Expression écrite + Questions de grammaire

  SÉRIE B (Économie) :
  * Économie générale : Dissertation économique ou étude de cas avec documents
  * Comptabilité : Exercices de journaux comptables, bilan, compte de résultat, états financiers
  * Droit : Cas pratique juridique + questions de cours
  * Maths Série B : Statistiques, probabilités, fonctions, suites numériques

  SÉRIE C (Maths-Sciences Physiques) :
  * Maths Série C : 3 exercices (Analyse : fonctions, dérivées, intégrales | Algèbre-Géométrie : vecteurs, complexes, probabilités | Statistiques/Suites)
  * Sciences Physiques Série C : 2 exercices Physique (mécanique, électricité, ondes) + 1 exercice Chimie (chimie organique, équilibres)

  SÉRIE D (Sciences Naturelles) :
  * SVT Série D : Restitution de connaissances + Exploitation de documents + Résolution de problème scientifique
  * Maths Série D : similaire C mais coefficients différents
  * Sciences Physiques Série D : format similaire C

  SÉRIE G (Gestion) :
  * Comptabilité/Gestion : Analyse de situations d'entreprise, travaux comptables, tableaux de bord
  * Informatique de gestion : Algorithmique simple, tableur, base de données

  SÉRIE H (Informatique) :
  * Algorithmique et programmation : Pseudo-code, organigramme, analyse de programme
  * Réseaux : Questions sur TCP/IP, architecture réseau
  * Bases de données : SQL, modèle entité-relation

UNIVERSITÉ :
- Formats : Partiel (1h-2h), Examen final (3h-4h), Contrôle continu
- Types de questions : QCM, questions de cours ouvertes, études de cas, dissertations académiques, problèmes, exercices techniques
- Structure : En-tête officiel de l'université + Consignes strictes + Questions numérotées + Barème détaillé

CONTEXTE IVOIRIEN POUR LES PROBLÈMES ET CAS PRATIQUES :
- Économie : prix du cacao, taux de change FCFA/Euro, budget d'un ménage ivoirien, entreprise abidjanaise, plantation d'anacarde
- Géographie : distances entre villes ivoiriennes (Abidjan-Bouaké : 340 km), superficie de la Côte d'Ivoire (322 463 km²), population (~27 millions)
- Histoire : colonisation française, indépendance 1960, Houphouët-Boigny, miracle ivoirien, crises politiques
- Sciences : maladies tropicales (paludisme, choléra), culture du cacao, énergie solaire en Afrique, barrages (Kossou, Taabo, Soubré)
- Maths : marchés, transport en commun (gbakas, woros-woros), surfaces agricoles, statistiques démographiques ivoiriennes

=== MISSION ===

Crée un sujet d'examen COMPLET et DÉTAILLÉ basé sur cette demande :

{description}

RÈGLES ABSOLUES :
- Identifie le niveau (Primaire/Collège/Lycée/Université), la matière, la série (si lycée) et le type d'épreuve
- Respecte EXACTEMENT le format officiel ivoirien de l'épreuve demandée
- Rédige toutes les questions COMPLÈTES et PRÉCISES (PAS de pointillés, PAS de [À compléter], PAS de [Insérer question ici])
- Pour le texte à trous : écris le texte COMPLET avec les mots manquants remplacés par ___________ (10 underscores)
- Pour Vrai/Faux : présente OBLIGATOIREMENT dans un tableau markdown (jamais en liste)
- Pour les exercices : donne TOUTES les données numériques, TOUTES les questions réelles et précises
- Contextualise les problèmes dans la réalité ivoirienne et africaine quand c'est possible
- Termine avec le CORRIGÉ COMPLET uniquement si la demande le mentionne
- N'utilise JAMAIS de notation LaTeX ($, \\, \\frac, \\text{{}}) — écris les formules en texte clair
- Formules en texte clair : "omega = 2 x pi x f", "XL = L x omega", "racine(R² + X²)", "1/2 x m x v²"
- Symboles grecs en toutes lettres : omega, phi, delta, sigma, alpha, beta, gamma, pi, theta
- Unités en clair : Ohm, Hz, rad/s, Watt, Volt, Ampère, VA, VAR, Newton, Joule, Pascal, mol/L, km/h, m/s²

Structure OBLIGATOIRE :

# EN-TÊTE OFFICIEL
Établissement : [nom de l'école/lycée/université]
Année scolaire : [ex: 2025-2026]
Matière : [matière]
Série : [série si lycée, sinon niveau]
Niveau : [niveau exact]
Type d'épreuve : [Contrôle de connaissances / Devoir surveillé / BAC blanc / Examen final...]
Durée : [durée]
Coefficient : [coefficient si connu]
Barème total : /20

# CONSIGNES GÉNÉRALES
[Consignes précises et officielles adaptées au niveau]

# EXERCICE 1 — [Titre explicite] ([X] points)
[Contenu complet avec toutes les questions réelles, données, schémas décrits en texte]

# EXERCICE 2 — [Titre : Vrai ou Faux si applicable] ([X] points)
[Si Vrai/Faux : TOUJOURS en tableau markdown :]

| N° | Affirmation | Réponse (V/F) |
|----|-------------|---------------|
| 1 | [affirmation complète] |  |
| 2 | [affirmation complète] |  |

# EXERCICE 3 — [Titre explicite] ([X] points)
[Contenu complet]

---

# CORRIGÉ COMPLET
(Inclure UNIQUEMENT si la demande mentionne "avec corrigé" ou "corrigé")

## Corrigé Exercice 1
[Réponses complètes, justifiées, avec méthode détaillée]

## Corrigé Exercice 2
[Réponses complètes avec justification de chaque V/F]

## Corrigé Exercice 3
[Réponses complètes avec méthode détaillée]

Rédige en français, sois rigoureux et adapté au niveau scolaire ivoirien concerné."""

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
(Liste des onglets avec description)

## STRUCTURE DES COLONNES PAR FEUILLE
(En-têtes, types de données)

## FORMULES EXCEL CLÉS
(Avec syntaxe exacte : =SOMME(), =RECHERCHEV(), =SI(), etc.)

## DONNÉES D'EXEMPLE
(5-10 lignes d'exemple réalistes)

## MISE EN FORME RECOMMANDÉE
(Couleurs, styles, graphiques suggérés)

## TABLEAU DE BORD
(Description du tableau de bord final)

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
    p_titre = doc.add_paragraph()
    p_titre.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run_t = p_titre.add_run("⚡ NOVA AI  —  " + service.replace("📝","").replace("👔","").replace("📊","").replace("⚙️","").replace("🎨","").replace("📚","").replace("📄","").strip())
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
            background: #0a0800 !important;
            background: -webkit-linear-gradient(135deg, #0a0800 0%, #1a1200 30%, #0d0900 60%, #1a1000 100%) !important;
            background: linear-gradient(135deg, #0a0800 0%, #1a1200 30%, #0d0900 60%, #1a1000 100%) !important;
            color: #fff8e1 !important;
        }

        /* Particules dorées en arrière-plan */
        .stApp::before {
            content: '';
            position: fixed;
            inset: 0;
            background:
                radial-gradient(ellipse at 10% 20%, rgba(255,215,0,0.06) 0%, transparent 50%),
                radial-gradient(ellipse at 90% 80%, rgba(255,140,0,0.05) 0%, transparent 50%),
                radial-gradient(ellipse at 50% 50%, rgba(184,134,11,0.04) 0%, transparent 70%);
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
            border: 1px solid rgba(255,215,0,0.35) !important;
            background-color: rgba(10,8,0,0.7) !important;
            color: #fff8e1 !important;
        }
        .stTextArea textarea {
            background-color: rgba(10,8,0,0.8) !important;
            color: #fff8e1 !important;
            border: 2px solid #FFD700 !important;
            animation: border-gold 4s linear infinite !important;
        }
        @keyframes border-gold {
            0%   { border-color: #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.3); }
            33%  { border-color: #FF8C00; box-shadow: 0 0 15px rgba(255,140,0,0.3); }
            66%  { border-color: #b8860b; box-shadow: 0 0 10px rgba(184,134,11,0.3); }
            100% { border-color: #FFD700; box-shadow: 0 0 10px rgba(255,215,0,0.3); }
        }

        /* ===== BOUTONS OR ===== */
        .stButton>button {
            background: linear-gradient(90deg, #7a5500, #b8860b, #FFD700, #b8860b, #7a5500) !important;
            background-size: 200% auto !important;
            color: #0a0800 !important;
            box-shadow: 0 4px 15px rgba(255,215,0,0.4) !important;
            animation: shimmer-gold 3s linear infinite !important;
        }
        .stButton>button:hover {
            box-shadow: 0 6px 25px rgba(255,215,0,0.6) !important;
            transform: translateY(-2px) !important;
        }

        /* ===== SIDEBAR OR ===== */
        section[data-testid="stSidebar"] {
            background: linear-gradient(180deg, #0d0900 0%, #1a1000 100%) !important;
            border-right: 1px solid rgba(255,215,0,0.2) !important;
        }

        /* ===== INFO-CARD OR ===== */
        .info-card {
            border-left: 4px solid #FFD700 !important;
            background: rgba(255,215,0,0.05) !important;
        }
        .info-title { color: #FFD700 !important; }

        /* ===== FILE-CARD OR ===== */
        .file-card {
            border: 2px solid rgba(255,215,0,0.4) !important;
            background: rgba(255,215,0,0.04) !important;
        }

        /* ===== PROGRESS BAR OR ===== */
        .stProgress > div > div > div > div {
            background-image: linear-gradient(to right, #b8860b, #FFD700, #FF8C00) !important;
        }

        /* ===== EXPANDER OR ===== */
        .streamlit-expanderHeader {
            color: #FFD700 !important;
            border: 1px solid rgba(255,215,0,0.2) !important;
            background: rgba(255,215,0,0.05) !important;
        }

        /* ===== DIVIDER OR ===== */
        hr { border-color: rgba(255,215,0,0.2) !important; }

        /* ===== METRIC OR ===== */
        [data-testid="stMetric"] {
            background: rgba(255,215,0,0.06) !important;
            border: 1px solid rgba(255,215,0,0.2) !important;
            border-radius: 12px !important;
            padding: 10px !important;
        }
        [data-testid="stMetricValue"] { color: #FFD700 !important; }

        /* ===== SUCCESS / INFO / WARNING OR ===== */
        .stSuccess {
            background: rgba(255,215,0,0.08) !important;
            border: 1px solid rgba(255,215,0,0.3) !important;
            color: #FFD700 !important;
        }
        .stInfo {
            background: rgba(255,215,0,0.05) !important;
            border: 1px solid rgba(255,215,0,0.2) !important;
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
            st.markdown("""
            <div style="background:linear-gradient(135deg,rgba(255,215,0,.1),rgba(255,140,0,.06));
                 border:1px solid rgba(255,215,0,.5);border-radius:12px;padding:12px 18px;margin:10px 0;">
                <span style="color:#FFD700;font-weight:800;">⚡ PREMIUM — Génération IA automatique activée</span>
                <span style="color:rgba(255,255,255,.5);font-size:.8rem;display:block;margin-top:3px;">
                    Votre document sera généré et livré en moins d'1 minute après soumission.
                </span>
            </div>""", unsafe_allow_html=True)

        label_btn = "⚡ GÉNÉRER MAINTENANT AVEC L'IA NOVA" if (premium_actif and service in SERVICES_GEMINI) else "ACTIVER L'ALGORITHME NOVA"
        if st.button(label_btn):
            if not user:
                st.session_state["view"] = "auth"
                st.rerun()

            elif premium_actif and service in SERVICES_GEMINI and not champs_manquants:
                import threading

                processing_box = st.empty()
                processing_box.markdown("""
                <div class="nova-processing">
                    <div class="nova-processing-title">⚡ NOVA IA EST EN COURS DE TRAITEMENT</div>
                    <div class="nova-processing-sub">Génération automatique en cours · Merci de patienter (max 1 minute)</div>
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
                            nom  = f"NovaAI_{user}_{service[:20].strip()}.xlsx".replace(" ", "_").replace("/", "-")
                            mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        else:
                            buf  = creer_docx(contenu, service, user)
                            nom  = f"NovaAI_{user}_{service[:20].strip()}.docx".replace(" ", "_").replace("/", "-")
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
                    label_prog.markdown(f"<p style='text-align:center;color:#FFD700;font-weight:bold;'>⚡ Nova IA traite votre demande... {pct}%</p>", unsafe_allow_html=True)
                    time.sleep(0.5)
                thread.join()

                barre.progress(100)
                label_prog.markdown("<p style='text-align:center;color:#2ecc71;font-weight:bold;'>✅ Traitement terminé !</p>", unsafe_allow_html=True)
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
                    save_lien(user, service, f"__local__{result_holder['nom']}", datetime.now().strftime("%d/%m/%Y"))
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
                                    nom_fichier = f"NovaAI_{client_nom}_Suivi_Depenses.xlsx".replace(" ", "_")
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
                                    nom_fichier = f"NovaAI_{client_nom}_{result['service'][:20].strip()}.docx".replace(" ", "_").replace("/", "-")
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
