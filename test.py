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
        users_rows = supabase.table("users").select("*").execute().data
        users = {r["uid"]: {"whatsapp": r["whatsapp"], "email": r["email"], "joined": r["joined"]} for r in users_rows}

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
    pass

# --- NOTIFICATION EMAIL ---
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

# ==========================================
# GEMINI AI — GÉNÉRATION AUTOMATIQUE
# ==========================================

def get_modeles_disponibles(api_key):
    """Appelle ListModels et retourne les modèles supportant generateContent."""
    import urllib.request as _ur
    import urllib.error
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
        req = _ur.Request(url, headers={"Content-Type": "application/json"}, method="GET")
        with _ur.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        modeles = []
        # Exclure les modèles non-texte (audio, image, tts, etc.)
        exclusions = ["tts", "audio", "image", "imagen", "veo", "robotics",
                      "embedding", "aqa", "computer-use", "research", "nano-banana",
                      "gemma", "preview"]
        for m in data.get("models", []):
            if "generateContent" in m.get("supportedGenerationMethods", []):
                nom = m["name"].replace("models/", "")
                if not any(excl in nom.lower() for excl in exclusions):
                    modeles.append(nom)
        # Priorité : flash-lite → flash → pro → autres
        def priorite(nom):
            if "flash-lite" in nom: return 0
            if "flash" in nom:      return 1
            if "pro" in nom:        return 2
            return 3
        modeles_tries = sorted(modeles, key=priorite)
        return modeles_tries
    except Exception as e:
        # Fallback statique si ListModels échoue
        return ["gemini-2.0-flash-lite", "gemini-2.0-flash", "gemini-2.5-flash"]


def generer_avec_gemini(service, description, client_nom):
    """Génère un document complet via Gemini AI."""
    try:
        import urllib.request as _ur
        import urllib.error

        api_key = st.secrets["GEMINI_API_KEY"]

        # --- Prompts spécialisés par service ---
        if "Exposé" in service:
            prompt = f"""Tu es un expert académique. Rédige un exposé scolaire complet, structuré et professionnel sur :

{description}

Structure OBLIGATOIRE :
# PAGE DE GARDE
(Titre, matière, niveau scolaire, établissement, date)

# INTRODUCTION
(Accroche, problématique, annonce du plan)

# DÉVELOPPEMENT
## Partie 1 : (titre pertinent)
## Partie 2 : (titre pertinent)
## Partie 3 : (titre pertinent)

# CONCLUSION
(Synthèse, ouverture)

# BIBLIOGRAPHIE
(Sources et références)

Rédige en français, sois détaillé et professionnel. Minimum 3 pages."""

        elif "Examens" in service or "Sujets" in service:
            prompt = f"""Tu es un professeur expérimenté. Crée un sujet d'examen COMPLET et DÉTAILLÉ basé sur cette demande :

{description}

RÈGLES ABSOLUES :
- Rédige le sujet COMPLET avec toutes les questions réelles et précises (PAS de pointillés, PAS de [À compléter])
- Pour le texte à trous : écris le texte COMPLET avec les mots manquants remplacés par ___________ (10 underscores)
- Pour Vrai/Faux : écris chaque affirmation complète et précise
- Pour les exercices complexes : donne tous les données numériques, schémas décrits en texte, questions détaillées
- Termine TOUJOURS avec le CORRIGÉ COMPLET avec les bonnes réponses

Structure OBLIGATOIRE :

# EN-TÊTE OFFICIEL
Établissement : [nom]
Matière : [matière]
Niveau : [niveau]
Durée : [durée]
Barème total : /20

# CONSIGNES GÉNÉRALES
[consignes précises]

# EXERCICE 1 — [Titre] ([X] points)
[Contenu complet de l'exercice avec toutes les questions réelles]

# EXERCICE 2 — [Titre Vrai ou Faux] ([X] points)
Consigne : Pour chacune des affirmations suivantes, indiquez V (Vrai) ou F (Faux) dans la colonne prévue.

⚠️ IMPORTANT : Tu DOIS ABSOLUMENT présenter les affirmations dans un tableau markdown exactement comme ci-dessous. N'utilise JAMAIS une liste numérotée pour cet exercice.

| N° | Affirmation | Réponse (V/F) |
|----|-------------|---------------|
| 1 | [affirmation complète et précise sur le sujet demandé] |  |
| 2 | [affirmation complète et précise sur le sujet demandé] |  |
| 3 | [affirmation complète et précise sur le sujet demandé] |  |
| 4 | [affirmation complète et précise sur le sujet demandé] |  |
| 5 | [affirmation complète et précise sur le sujet demandé] |  |

RÈGLES pour la colonne "Réponse (V/F)" : laisser VIDE (juste un espace) — c'est l'étudiant qui remplira.

# EXERCICE 3 — [Titre] ([X] points)
[Contenu complet de l'exercice avec toutes les questions réelles]

---

# CORRIGÉ COMPLET

## Corrigé Exercice 1
[Réponses complètes et détaillées]

## Corrigé Exercice 2
[Réponses complètes et détaillées]

## Corrigé Exercice 3
[Réponses complètes et détaillées]

IMPORTANT :
- Si la demande ne mentionne PAS de corrigé, génère UNIQUEMENT le sujet (PAS de corrigé)
- Si la demande mentionne explicitement "avec corrigé" ou "corrigé", alors ajoute le corrigé
- N'utilise JAMAIS de notation LaTeX ($, \\, \\text{{}}, \\frac{{}}) dans le document final
- Écris les formules en texte simple : ex "omega = 2*pi*f", "XL = L*omega", "|Z| = sqrt(R² + X²)"
- Écris les unités en clair : Ohm, Hz, rad/s, W, V, A, VA, VAR
- Les symboles grecs s'écrivent en toutes lettres : omega, phi, delta, sigma

Rédige en français, sois précis et technique, niveau adapté à la demande."""

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

        # Payload Gemini
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 8192
            }
        }).encode("utf-8")

        # Découverte automatique des modèles disponibles via ListModels
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
                # Lire le corps de la réponse pour voir la vraie erreur
                try:
                    corps_erreur = e.read().decode("utf-8")
                    erreur_detail = json.loads(corps_erreur).get("error", {}).get("message", corps_erreur[:200])
                except:
                    erreur_detail = str(e)
                erreurs.append(f"{modele} → HTTP {e.code}: {erreur_detail}")
                if e.code in [429, 503]:  # Quota / surcharge → essayer suivant
                    time.sleep(2)
                    continue
                # Autre erreur HTTP (403, 400...) → arrêter, afficher
                return f"❌ Erreur Gemini ({modele}) HTTP {e.code} : {erreur_detail}"
            except Exception as e:
                erreurs.append(f"{modele} → {type(e).__name__}: {e}")
                continue

        # Tous les modèles ont échoué → afficher les vraies erreurs
        detail = " | ".join(erreurs)
        return f"❌ Gemini indisponible. Détails : {detail}"

    except Exception as e:
        return f"❌ Erreur Gemini : {e}"


def creer_docx(contenu, service, client_nom):
    """Génère un fichier .docx propre et professionnel à partir du contenu Gemini."""
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    from io import BytesIO
    import re

    doc = Document()

    # Marges
    for section in doc.sections:
        section.top_margin    = Cm(2)
        section.bottom_margin = Cm(2)
        section.left_margin   = Cm(2.5)
        section.right_margin  = Cm(2.5)

    # Style par défaut
    style = doc.styles["Normal"]
    style.font.name = "Arial"
    style.font.size = Pt(11)

    # ─── Bandeau en-tête ────────────────────────────────────────────
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
    # Titre centré avec fond bleu
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

    # Ligne séparatrice
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

    # ─── Parsing Markdown → Word propre ─────────────────────────────
    def add_formatted_para(doc, text, style_name="Normal", bold=False, size=11, color=None, align=None):
        """Ajoute un paragraphe en gérant le gras inline **texte**"""
        p = doc.add_paragraph(style=style_name)
        if align:
            p.alignment = align
        # Découper sur **bold**
        parts = re.split(r"(\*\*[^*]+\*\*)", text)
        for part in parts:
            if part.startswith("**") and part.endswith("**"):
                run = p.add_run(part[2:-2])
                run.bold = True
            else:
                # Nettoyer les * simples résiduels
                clean = part.replace("*", "").replace("`", "")
                run = p.add_run(clean)
                run.bold = bold
            run.font.name = "Arial"
            run.font.size = Pt(size)
            if color:
                run.font.color.rgb = RC(*color)
        return p

    # ─── Nettoyage LaTeX → texte lisible ───────────────────────────
    import re as _re
    def nettoyer_latex(texte):
        # Supprimer environnements LaTeX $...$
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
        # Fermer les parenthèses ouvertes non fermées
        opens = f.count("(") - f.count(")")
        if opens > 0:
            f += ")" * opens
        return f

    contenu = nettoyer_latex(contenu)
    # Nettoyer aussi les \ résiduels hors $
    contenu = contenu.replace("\\,", " ").replace("\\text{", "").replace("\\", "")

    lignes = contenu.split("\n")
    i = 0
    while i < len(lignes):
        l = lignes[i].rstrip()

        # Sauter les séparateurs markdown
        if l.strip() in ["---", "***", "___", "*"]:
            doc.add_paragraph("")
            i += 1
            continue

        # Headings
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

        # ─── Tableau Markdown | col1 | col2 | ───────────────────────
        if l.startswith("|") and l.endswith("|"):
            # Collecter toutes les lignes du tableau
            table_lines = []
            while i < len(lignes) and lignes[i].strip().startswith("|") and lignes[i].strip().endswith("|"):
                row = lignes[i].strip()
                # Ignorer les séparateurs |---|---|
                if not re.match(r"^[\|\s\-:]+$", row):
                    cells = [c.strip() for c in row.strip("|").split("|")]
                    table_lines.append(cells)
                i += 1

            if table_lines:
                from docx.shared import Inches
                from docx.oxml.ns import qn
                from docx.oxml import OxmlElement

                # Largeurs colonnes adaptées
                n_cols = max(len(r) for r in table_lines)
                col_widths_map = {
                    2: [3.0, 6.0],
                    3: [1.0, 7.5, 2.5],   # N° | Affirmation | Réponse
                    4: [1.0, 5.0, 2.5, 2.5],
                }
                col_widths = col_widths_map.get(n_cols, [9.0/n_cols]*n_cols)

                from docx.shared import Cm as DocxCm
                table = doc.add_table(rows=0, cols=n_cols)
                table.style = "Table Grid"

                for r_idx, row_data in enumerate(table_lines):
                    row_obj = table.add_row()
                    is_header = (r_idx == 0)
                    # En-tête plus compact, lignes de données plus hautes pour aérer
                    row_obj.height = DocxCm(0.9 if is_header else 1.5)
                    from docx.oxml.ns import qn as _qn
                    from docx.oxml import OxmlElement as _OE
                    # Fixer la hauteur exacte
                    trPr = row_obj._tr.get_or_add_trPr()
                    trHeight = _OE("w:trHeight")
                    trHeight.set(_qn("w:val"), str(int((0.9 if is_header else 1.5) * 567)))
                    trHeight.set(_qn("w:hRule"), "exact")
                    trPr.append(trHeight)

                    for c_idx, cell_text in enumerate(row_data):
                        cell = row_obj.cells[c_idx]
                        if c_idx < len(col_widths):
                            cell.width = DocxCm(col_widths[c_idx])
                        # Padding interne
                        tc = cell._tc
                        tcPr = tc.get_or_add_tcPr()
                        tcMar = _OE("w:tcMar")
                        for side in ["top","bottom","left","right"]:
                            m = _OE(f"w:{side}")
                            m.set(_qn("w:w"), "120")
                            m.set(_qn("w:type"), "dxa")
                            tcMar.append(m)
                        tcPr.append(tcMar)
                        # Fond bleu pour en-tête, gris alternant pour données
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
                        # Espacement vertical dans la cellule
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

        # Listes numérotées  1. ou 1)
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

        # Listes à puces  - ou *
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

        # Ligne vide
        if not l.strip():
            doc.add_paragraph("")
            i += 1
            continue

        # Ligne tout en gras (ex: **TITRE**)
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

        # Paragraphe normal avec gras inline possible
        add_formatted_para(doc, l.strip())
        i += 1

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def creer_xlsx(description, client_nom):
    """Génère un vrai fichier Excel .xlsx de suivi des dépenses."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    from io import BytesIO

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

    # ─── Feuille 1 : Saisie Dépenses ───────────────────────────────
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

    # ─── Feuille 2 : Catégories ─────────────────────────────────────
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

    # ─── Feuille 3 : Tableau de Bord ────────────────────────────────
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

if "show_service_warning" not in st.session_state:
    st.session_state["show_service_warning"] = False

if "last_service_seen" not in st.session_state:
    st.session_state["last_service_seen"] = None

if "warning_triggered" not in st.session_state:
    st.session_state["warning_triggered"] = False

if "intro_played" not in st.session_state:
    st.session_state["intro_played"] = False

# ← NOUVEAU : stockage des résultats Gemini
if "gemini_results" not in st.session_state:
    st.session_state["gemini_results"] = {}

# Reconnaissance automatique via cookie navigateur (session persistante)
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

# ==========================================
# DESIGN ET STYLE (CSS AVANCÉ)
# ==========================================

def inject_custom_css():
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

        /* GEMINI CARD */
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
        </style>
    """, unsafe_allow_html=True)
    
    if st.session_state["is_glowing"]:
        st.markdown('<style>.stApp { animation: glow-pulse 1.5s ease-in-out infinite; }</style>', unsafe_allow_html=True)

# ==========================================
# PAGE AUTH
# ==========================================

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
        animation: btn-shimmer 3s linear infinite, btn-float 3.5s ease-in-out infinite !important;
        cursor: pointer !important;
    }
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
    .auth-page .stButton > button::after {
        content: '' !important;
        position: absolute !important;
        inset: 0 !important;
        border-radius: 50px !important;
        box-shadow: 0 0 0 2px rgba(255,215,0,0.5) !important;
        animation: btn-glow-ring 2s ease-in-out infinite !important;
        pointer-events: none !important;
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
                            "joined": str(datetime.now())
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

# ==========================================
# DASHBOARD PRINCIPAL
# ==========================================

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
    # PREMIUM CARD
    # ==========================================
    wa_jour = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%20Journalier%20%C3%A0%20600%20FC."
    wa_10j  = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%2010%20Jours%20%C3%A0%201000%20FC."
    wa_30j  = f"https://wa.me/{WHATSAPP_NUMBER}?text=Je%20souhaite%20l%27abonnement%20Nova%20Premium%2030%20Jours%20%C3%A0%202500%20FC."

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

    with tab1:

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

            if user_links:
                for link in user_links:
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

    # ==========================================
    # CONSOLE ADMIN
    # ==========================================
    with st.expander("🛠 Console Admin Nova"):
        if st.text_input("Master Key", type="password") == ADMIN_CODE:

            current_db = st.session_state["db"]
            st.markdown("### 🛡️ Panneau de contrôle Nova")

            if not current_db["demandes"]:
                st.info("✅ Aucune mission en attente.")

            def wa_url(numero, texte):
                encoded = texte.replace(" ", "%20").replace("'", "%27").replace("\n", "%0A")
                return f"https://wa.me/{numero}?text={encoded}"

            # Services éligibles à la génération Gemini automatique
            SERVICES_GEMINI = [
                "📝 Exposé scolaire complet IA",
                "📝 Création de Sujets & Examens",
                "👔 CV & Lettre de Motivation",
                "⚙️ Pack Office (Word/Excel/PPT)",
                "📊 Data & Excel Analytics",
            ]

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

                if i > 0:
                    st.divider()

                st.markdown(f"**Mission `#{req_id}`** · {timestamp}" + (" — ⚠️ *Incomplet : " + ", ".join(champs_manquants) + "*" if est_incomplet else ""))
                st.markdown(f"👤 **Client :** {client_nom}")
                st.markdown(f"📱 **WhatsApp :** {client_wa}")
                st.markdown(f"🛠️ **Service demandé :** {service}")
                st.markdown(f"📝 **Détails de la demande :** {description}")

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

                # ==========================================
                # BOUTON GEMINI (services éligibles)
                # ==========================================
                if service in SERVICES_GEMINI:
                    st.markdown("<br>", unsafe_allow_html=True)
                    st.markdown(f"""
                    <div class="gemini-card">
                        <div class="gemini-title">🤖 GEMINI AI — GÉNÉRATION AUTOMATIQUE DISPONIBLE</div>
                        <div class="gemini-sub">Génère le document complet en .docx en 30-60 secondes</div>
                    </div>
                    """, unsafe_allow_html=True)

                    # Bouton diagnostic
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

                    # Afficher résultat si déjà généré
                    if req_id in st.session_state["gemini_results"]:
                        result = st.session_state["gemini_results"][req_id]

                        with st.expander("👁️ Aperçu du contenu généré", expanded=False):
                            st.markdown(result["contenu"])

                        # Téléchargement selon le service :
                        # 📊 Data & Excel Analytics → .xlsx
                        # Tous les autres (Exposé, CV, Sujets, Pack Office...) → .docx
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
                                # Exposé, CV, Sujets/Examens, Pack Office, Affiches, PDF → .docx
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

                # Livraison
                st.markdown("<br>", unsafe_allow_html=True)
                url_dl = st.text_input("🔗 Lien de livraison (Google Drive...)", key=f"url_{i}", placeholder="https://drive.google.com/...")
                if st.button("📦 LIVRER LA MISSION AU CLIENT", key=f"btn_{i}", use_container_width=True):
                    if url_dl:
                        save_lien(req['user'], req['service'], url_dl, datetime.now().strftime("%d/%m/%Y"))
                        delete_demande(req['id'])
                        # Nettoyer le résultat Gemini si existant
                        if req_id in st.session_state["gemini_results"]:
                            del st.session_state["gemini_results"][req_id]
                        st.session_state["db"] = load_db()
                        st.success(f"✅ Mission livrée à {client_nom} !")
                        st.rerun()

# ==========================================
# RUNTIME
# ==========================================

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
