from flask import Flask, request, jsonify, send_file, send_from_directory, abort
from flask_cors import CORS
import webbrowser, threading
from ela import analyser_ela
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from io import BytesIO
from datetime import datetime
import sqlite3, os

app = Flask(__name__)
CORS(app)

# ════════════════════════════════════════════
# BASE DE DONNÉES SQLITE
# ════════════════════════════════════════════
DB_PATH = os.path.join(os.path.dirname(__file__), 'sidad.db')

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS analyses (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        ref         TEXT UNIQUE,
        fichier     TEXT,
        type        TEXT,
        verdict     TEXT,
        score       REAL,
        score_ela   REAL,
        date        TEXT,
        heure       TEXT,
        agent       TEXT,
        created_at  TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    print("✅ Base de données initialisée :", DB_PATH)

init_db()

# ════════════════════════════════════════════
# GÉNÉRATEUR RÉFÉRENCE
# ════════════════════════════════════════════
def generer_ref():
    now    = datetime.now()
    annee  = now.strftime('%Y')
    mmjj   = now.strftime('%m%d')
    datecle = f'{annee}-{mmjj}'

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM analyses WHERE ref LIKE ?", (f'DOC-{datecle}-%',))
    count = c.fetchone()[0]
    conn.close()

    numero = str(count + 1).zfill(3)
    return f'DOC-{datecle}-{numero}'

# ════════════════════════════════════════════
# COULEURS PDF
# ════════════════════════════════════════════
ROUGE  = colors.HexColor('#CE1126')
JAUNE  = colors.HexColor('#FCD116')
VERT   = colors.HexColor('#009460')
BG     = colors.HexColor('#07080D')
CARD   = colors.HexColor('#0E1018')
SURF   = colors.HexColor('#141720')
BORDER = colors.HexColor('#1E2130')
BLANC  = colors.HexColor('#F0F2F8')
GRIS   = colors.HexColor('#7B8099')
MUTED  = colors.HexColor('#4A5068')
W, H   = A4

def generer_rapport_pdf(data):
    fichier   = data.get('fichier', 'inconnu')
    verdict   = data.get('verdict', 'authentique')
    score     = int(data.get('score', 0))
    type_doc  = data.get('type', 'Document')
    ref       = data.get('ref', '')
    agent     = data.get('agent', 'Inconnu')
    date_str  = data.get('date', datetime.now().strftime('%d/%m/%Y'))
    heure_str = data.get('heure', datetime.now().strftime('%H:%M'))
    zones_pct = data.get('zones', [95, 88, 93, 97, 90])
    resume_pct= data.get('resume', [93, 96, 89, 91, 92])

    if verdict == 'authentique':
        cv = VERT;  lv = 'DOCUMENT AUTHENTIQUE';       ev = 'OK'
        dv = "Ce document presente toutes les caracteristiques d'un document officiel authentique. Aucune anomalie majeure n'a ete detectee."
    elif verdict == 'falsifie':
        cv = ROUGE; lv = 'DOCUMENT FALSIFIE';          ev = 'ALERTE'
        dv = "Ce document presente des anomalies significatives. Des zones ont ete modifiees ou alterees. Une verification manuelle est fortement recommandee."
    else:
        cv = JAUNE; lv = 'REVISION MANUELLE REQUISE';  ev = 'ATTENTION'
        dv = "Le score d'authenticite est incertain. Certaines zones presentent des irregularites. Une verification humaine est recommandee."

    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f'SIDAD Rapport {ref}')

    c.setFillColor(BG); c.rect(0, 0, W, H, fill=1, stroke=0)
    c.setFillColor(CARD); c.rect(0, H-90, W, 90, fill=1, stroke=0)
    fw = W/3
    c.setFillColor(ROUGE); c.rect(0, H-3, fw, 3, fill=1, stroke=0)
    c.setFillColor(JAUNE); c.rect(fw, H-3, fw, 3, fill=1, stroke=0)
    c.setFillColor(VERT);  c.rect(fw*2, H-3, fw, 3, fill=1, stroke=0)

    c.setFillColor(JAUNE); c.roundRect(28, H-73, 36, 36, 6, fill=1, stroke=0)
    c.setFillColor(BG); c.setFont('Helvetica-Bold', 9); c.drawString(31, H-57, 'SIDAD')
    c.setFillColor(BLANC); c.setFont('Helvetica-Bold', 20); c.drawString(74, H-47, 'SIDAD')
    c.setFillColor(GRIS); c.setFont('Helvetica', 8)
    c.drawString(74, H-61, "Systeme Intelligent de Detection d'Authenticite Documentaire")

    c.setFillColor(GRIS); c.setFont('Helvetica', 7.5)
    c.drawRightString(W-28, H-28, f'Reference : {ref}')
    c.drawRightString(W-28, H-40, f'Genere le {date_str} a {heure_str}')
    c.drawRightString(W-28, H-52, f'Agent : {agent}')
    c.drawRightString(W-28, H-64, 'Republique de Guinee')
    c.setStrokeColor(BORDER); c.setLineWidth(1); c.line(0, H-90, W, H-90)

    yv = H-98; bh = 78
    c.setFillColor(cv); c.setFillAlpha(0.07)
    c.rect(20, yv-bh, W-40, bh, fill=1, stroke=0); c.setFillAlpha(1)
    c.setFillColor(cv); c.rect(20, yv-bh, 4, bh, fill=1, stroke=0)

    cx2, cy2, r = 68, yv-bh/2, 28
    c.setFillColor(SURF); c.circle(cx2, cy2, r, fill=1, stroke=0)
    c.setStrokeColor(cv); c.setLineWidth(4)
    c.arc(cx2-r+5, cy2-r+5, cx2+r-5, cy2+r-5, startAng=90, extent=-(360*score/100))
    c.setFillColor(cv); c.setFont('Helvetica-Bold', 15); c.drawCentredString(cx2, cy2+2, f'{score}%')
    c.setFillColor(GRIS); c.setFont('Helvetica', 6); c.drawCentredString(cx2, cy2-10, 'SCORE')

    bw = c.stringWidth(f'{ev}  {lv}', 'Helvetica-Bold', 10) + 20
    c.setFillColor(cv); c.setFillAlpha(0.15)
    c.roundRect(110, yv-22, bw, 18, 4, fill=1, stroke=0); c.setFillAlpha(1)
    c.setFillColor(cv); c.setFont('Helvetica-Bold', 10); c.drawString(118, yv-13, f'{ev}  {lv}')

    c.setFillColor(GRIS); c.setFont('Helvetica', 8)
    mots = dv.split(); ligne = ''; ly3 = yv-38
    for mot in mots:
        t2 = ligne+mot+' '
        if c.stringWidth(t2,'Helvetica',8) > W-155:
            c.drawString(110, ly3, ligne.strip()); ly3 -= 12; ligne = mot+' '
        else: ligne = t2
    if ligne.strip(): c.drawString(110, ly3, ligne.strip())

    y = yv-bh-18
    c.setFillColor(BLANC); c.setFont('Helvetica-Bold', 8.5); c.drawString(28, y, 'INFORMATIONS DU DOCUMENT')
    c.setStrokeColor(cv); c.setLineWidth(1.5); c.line(28, y-5, 210, y-5)
    c.setStrokeColor(BORDER); c.setLineWidth(0.5); c.line(210, y-5, W-28, y-5)

    y -= 16
    meta = [('REF', ref), ('FICHIER', fichier[:32]+'...' if len(fichier)>32 else fichier),
            ('TYPE', type_doc), ('AGENT', agent), ('DATE', date_str), ('HEURE', heure_str)]
    cw = (W-56)/2
    for i,(k,v) in enumerate(meta):
        col = i%2; row = i//2
        xi = 28+col*(cw+4); yi = y-row*22
        c.setFillColor(SURF); c.roundRect(xi, yi-14, cw-4, 20, 3, fill=1, stroke=0)
        c.setFillColor(MUTED); c.setFont('Helvetica-Bold', 6.5); c.drawString(xi+8, yi-3, k)
        c.setFillColor(BLANC); c.setFont('Helvetica', 8.5)
        c.drawString(xi+8+c.stringWidth(k+'   ','Helvetica-Bold',6.5), yi-3, v)

    rows = (len(meta)+1)//2
    yt = y-rows*22-22
    zl = ['Signature officielle','Sceau / Tampon','Typographie du texte','Numero de serie','Metadonnees image']
    rl = ['Coherence visuelle','Detection retouche','Conformite format','Analyse des pixels','Score global IA']

    def cpct(p): return VERT if p>=70 else (JAUNE if p>=40 else ROUGE)

    def tableau(titre, labels, vals, xs, larg, ys):
        c.setFillColor(BLANC); c.setFont('Helvetica-Bold',8.5); c.drawString(xs, ys, titre)
        c.setStrokeColor(cv); c.setLineWidth(1.5); c.line(xs, ys-5, xs+80, ys-5)
        c.setStrokeColor(BORDER); c.setLineWidth(0.5); c.line(xs+80, ys-5, xs+larg, ys-5)
        yr = ys-20
        c.setFillColor(SURF); c.rect(xs, yr-3, larg, 17, fill=1, stroke=0)
        c.setFillColor(MUTED); c.setFont('Helvetica-Bold',6.5)
        c.drawString(xs+6, yr+5, 'ZONE / INDICATEUR'); c.drawRightString(xs+larg-6, yr+5, 'SCORE')
        yr -= 19
        for i,(lab,pct) in enumerate(zip(labels,vals)):
            c.setFillColor(CARD if i%2==0 else SURF); c.rect(xs, yr-3, larg, 17, fill=1, stroke=0)
            c.setFillColor(BLANC); c.setFont('Helvetica',7.5); c.drawString(xs+6, yr+5, lab)
            bx = xs+larg-72; by = yr+7
            c.setFillColor(BORDER); c.roundRect(bx, by, 44, 4, 2, fill=1, stroke=0)
            c.setFillColor(cpct(pct)); c.roundRect(bx, by, 44*pct/100, 4, 2, fill=1, stroke=0)
            c.setFont('Helvetica-Bold',8); c.drawRightString(xs+larg-6, yr+5, f'{pct}%')
            yr -= 19

    tw = (W-56-10)/2
    tableau('ZONES ANALYSEES', zl, zones_pct, 28, tw, yt)
    tableau('RESUME TECHNIQUE', rl, resume_pct, 28+tw+10, tw, yt)

    annee = date_str[-4:] if len(date_str)>=4 else '2026'
    c.setFillColor(SURF); c.rect(0,0,W,36,fill=1,stroke=0)
    c.setFillColor(ROUGE); c.rect(0,0,fw,3,fill=1,stroke=0)
    c.setFillColor(JAUNE); c.rect(fw,0,fw,3,fill=1,stroke=0)
    c.setFillColor(VERT);  c.rect(fw*2,0,fw,3,fill=1,stroke=0)
    c.setStrokeColor(BORDER); c.setLineWidth(0.5); c.line(28,33,W-28,33)
    c.setFillColor(MUTED); c.setFont('Helvetica',7)
    c.drawString(28,20,f'(c) {annee} SIDAD — Systeme Intelligent de Detection d\'Authenticite Documentaire — Republique de Guinee')
    c.drawRightString(W-28,20,f'Ref. {ref}  |  Document Confidentiel')

    c.save(); buf.seek(0)
    return buf


# ════════════════════════════════════════════
# ROUTES
# ════════════════════════════════════════════

DOSSIER = os.path.dirname(os.path.abspath(__file__))

@app.route('/')
def accueil():
    # Page de connexion
    return send_from_directory(DOSSIER, 'index.html')


@app.route('/<page>.html')
def page_html(page):
    # Sert toutes les pages du site (dashboard.html, analyser.html, ...)
    if not os.path.exists(os.path.join(DOSSIER, page + '.html')):
        return send_from_directory(DOSSIER, '404.html'), 404
    return send_from_directory(DOSSIER, page + '.html')


@app.route('/statut')
def statut():
    return 'Le serveur SIDAD fonctionne !'


@app.route('/analyser', methods=['POST'])
def analyser():
    if 'fichier' not in request.files:
        return jsonify({'erreur': 'Aucun fichier recu'}), 400
    fichier = request.files['fichier']
    if fichier.filename == '':
        return jsonify({'erreur': 'Fichier vide'}), 400
    extensions_autorisees = ['jpg', 'jpeg', 'png', 'pdf']
    extension = fichier.filename.rsplit('.', 1)[-1].lower()
    if extension not in extensions_autorisees:
        return jsonify({'erreur': 'Format non supporte'}), 400

    resultat = analyser_ela(fichier)
    return jsonify({
        'fichier':   fichier.filename,
        'verdict':   resultat['verdict'],
        'score':     resultat['score_final'],
        'score_ela': resultat['score_ela'],
        'message':   'Analyse terminee'
    })


@app.route('/sauvegarder', methods=['POST'])
def sauvegarder():
    """Sauvegarder une analyse dans SQLite"""
    data = request.get_json()
    if not data:
        return jsonify({'erreur': 'Donnees manquantes'}), 400

    try:
        ref = generer_ref()
        now = datetime.now()

        conn = get_db()
        c = conn.cursor()
        c.execute('''INSERT OR IGNORE INTO analyses
            (ref, fichier, type, verdict, score, score_ela, date, heure, agent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
            ref,
            data.get('fichier', 'inconnu'),
            data.get('type', 'document'),
            data.get('verdict', 'revision'),
            data.get('score', 0),
            data.get('score_ela', 0),
            now.strftime('%d/%m/%Y'),
            now.strftime('%H:%M'),
            data.get('agent', 'Inconnu')
        ))
        conn.commit()
        conn.close()

        return jsonify({'ref': ref, 'succes': True})
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500


@app.route('/historique', methods=['GET'])
def historique():
    """Récupérer tout l'historique depuis SQLite"""
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM analyses ORDER BY id DESC LIMIT 200')
        rows = c.fetchall()
        conn.close()

        analyses = []
        for row in rows:
            analyses.append({
                'id':      row['id'],
                'ref':     row['ref'],
                'fichier': row['fichier'],
                'type':    row['type'],
                'verdict': row['verdict'],
                'score':   row['score'],
                'date':    row['date'],
                'heure':   row['heure'],
                'agent':   row['agent'],
            })
        return jsonify(analyses)
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500


@app.route('/stats', methods=['GET'])
def stats():
    """Statistiques pour le dashboard"""
    try:
        conn = get_db()
        c = conn.cursor()

        c.execute('SELECT COUNT(*) as total FROM analyses')
        total = c.fetchone()['total']

        c.execute("SELECT COUNT(*) as fraudes FROM analyses WHERE verdict='falsifie'")
        fraudes = c.fetchone()['fraudes']

        c.execute('SELECT AVG(score) as moyenne FROM analyses')
        row = c.fetchone()
        precision = round(row['moyenne'] or 0, 1)

        c.execute('SELECT * FROM analyses ORDER BY id DESC LIMIT 5')
        recentes = []
        for row in c.fetchall():
            recentes.append({
                'ref': row['ref'], 'fichier': row['fichier'],
                'verdict': row['verdict'], 'score': row['score'],
                'date': row['date'], 'heure': row['heure']
            })
        conn.close()

        taux = round((fraudes / total * 100)) if total > 0 else 0
        return jsonify({
            'total': total, 'fraudes': fraudes,
            'precision': precision, 'taux_fraudes': taux,
            'recentes': recentes
        })
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500


@app.route('/rapport', methods=['POST'])
def generer_rapport():
    data = request.get_json()
    if not data:
        return jsonify({'erreur': 'Donnees manquantes'}), 400
    try:
        buf = generer_rapport_pdf(data)
        ref = data.get('ref', 'rapport')
        nom = f"SIDAD_Rapport_{ref.replace('-','_')}.pdf"
        return send_file(buf, mimetype='application/pdf',
                         as_attachment=True, download_name=nom)
    except Exception as e:
        return jsonify({'erreur': str(e)}), 500


if __name__ == '__main__':
    # Ouvre le navigateur automatiquement (une seule fois)
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        threading.Timer(1.5, lambda: webbrowser.open('http://127.0.0.1:5000')).start()
    print('\n  SIDAD est lance -> http://127.0.0.1:5000\n  (Ne fermez pas cette fenetre)\n')
    app.run(host='127.0.0.1', port=5000, debug=True)
