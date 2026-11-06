from PIL import Image, ImageChops, ImageEnhance, ImageFilter
import numpy as np
import io
import fitz  # pymupdf


# ════════════════════════════════════════════════════════════
#  TECHNIQUE 1 — ELA (Error Level Analysis)
#  Détecte les zones retouchées par différence de compression
# ════════════════════════════════════════════════════════════
def analyser_ela_image(image, qualite=90):
    image = image.convert('RGB')

    buffer = io.BytesIO()
    image.save(buffer, 'JPEG', quality=qualite)
    buffer.seek(0)

    image_compressee = Image.open(buffer).convert('RGB')
    difference = ImageChops.difference(image, image_compressee)

    amplificateur = ImageEnhance.Brightness(difference)
    ela_image = amplificateur.enhance(10)

    ela_tableau = np.array(ela_image)
    return float(np.mean(ela_tableau))


# ════════════════════════════════════════════════════════════
#  TECHNIQUE 2 — ANALYSE DU BRUIT (Noise Inconsistency)
#  Une vraie photo a un bruit uniforme.
#  Une zone retouchée a un niveau de bruit différent.
#  NOTE : Les documents guinéens ont un fond guilloché très
#  texturé — ce bruit est naturel et uniforme, pas suspect.
# ════════════════════════════════════════════════════════════
def analyser_bruit(image):
    img_gris = np.array(image.convert('L')).astype(float)

    img_pil   = Image.fromarray(img_gris.astype(np.uint8))
    img_lisse = img_pil.filter(ImageFilter.GaussianBlur(radius=1))
    bruit     = np.abs(img_gris - np.array(img_lisse).astype(float))

    h, w   = bruit.shape
    taille = 8
    ecarts = []

    for i in range(0, h - taille, taille):
        for j in range(0, w - taille, taille):
            bloc = bruit[i:i+taille, j:j+taille]
            ecarts.append(np.std(bloc))

    if not ecarts:
        return 0.0

    ecarts  = np.array(ecarts)
    moyenne = np.mean(ecarts)
    mediane = np.median(ecarts)

    if mediane < 1e-6:
        return 0.0

    incoherence = abs(moyenne - mediane) / (mediane + 1e-6)
    return float(min(incoherence, 1.0))


# ════════════════════════════════════════════════════════════
#  TECHNIQUE 3 — DOUBLE COMPRESSION JPEG
# ════════════════════════════════════════════════════════════
def analyser_double_compression(image):
    img_rgb = image.convert('RGB')

    buf_haute = io.BytesIO()
    img_rgb.save(buf_haute, 'JPEG', quality=90)
    buf_haute.seek(0)

    buf_basse = io.BytesIO()
    img_rgb.save(buf_basse, 'JPEG', quality=70)
    buf_basse.seek(0)

    img_haute = Image.open(buf_haute).convert('RGB')
    img_basse = Image.open(buf_basse).convert('RGB')

    arr_original = np.array(img_rgb, dtype=float)
    arr_haute    = np.array(img_haute, dtype=float)
    arr_basse    = np.array(img_basse, dtype=float)

    diff_haute = np.mean(np.abs(arr_original - arr_haute))
    diff_basse = np.mean(np.abs(arr_original - arr_basse))

    if diff_basse < 1e-6:
        return 0.0

    ratio     = diff_haute / (diff_basse + 1e-6)
    suspicion = max(0.0, 1.0 - ratio * 2)
    return float(min(suspicion, 1.0))


# ════════════════════════════════════════════════════════════
#  TECHNIQUE 4 — ANALYSE DES MÉTADONNÉES EXIF
# ════════════════════════════════════════════════════════════
def analyser_metadata(fichier_bytes, nom_fichier):
    score_meta = 0.0
    details    = []

    try:
        img  = Image.open(io.BytesIO(fichier_bytes))
        exif = img._getexif() if hasattr(img, '_getexif') else None

        if exif is None:
            score_meta = 0.4
            details.append('Aucune metadonnee EXIF detectee')
            return score_meta, details

        TAG_SOFTWARE = 305
        TAG_MAKE     = 271
        TAG_MODEL    = 272

        logiciels_suspects = [
            'photoshop', 'gimp', 'lightroom', 'affinity',
            'pixelmator', 'paint.net', 'canva', 'snapseed',
            'facetune', 'meitu', 'adobe'
        ]

        software = str(exif.get(TAG_SOFTWARE, '')).lower()
        make     = str(exif.get(TAG_MAKE, ''))
        model    = str(exif.get(TAG_MODEL, ''))

        if any(s in software for s in logiciels_suspects):
            score_meta = 0.2
            details.append(f'Logiciel retouche detecte : {exif.get(TAG_SOFTWARE, "")}')
        elif software and software != 'none':
            score_meta = 0.6
            details.append(f'Logiciel : {exif.get(TAG_SOFTWARE, "")}')
        else:
            score_meta = 0.85

        if make and make.lower() not in ['none', '']:
            score_meta = min(1.0, score_meta + 0.15)
            details.append(f'Appareil : {make} {model}')

    except Exception:
        score_meta = 0.5
        details.append('Metadonnees illisibles')

    return float(score_meta), details


# ════════════════════════════════════════════════════════════
#  FONCTION PRINCIPALE — Score combiné
#  CALIBRÉ pour documents administratifs guinéens :
#  — fond guilloché naturellement texturé (bruit élevé normal)
#  — QR code + tampon + photo = zones à compression variable
#  — scan → compression naturelle (double compression normale)
# ════════════════════════════════════════════════════════════
def analyser_ela(fichier):
    nom           = fichier.filename.lower()
    fichier_bytes = fichier.read()

    scores_ela = []

    # ── PDF : analyser chaque page ──
    if nom.endswith('.pdf'):
        pdf = fitz.open(stream=fichier_bytes, filetype='pdf')
        for page in pdf:
            pixmap  = page.get_pixmap(dpi=150)
            img_data = pixmap.tobytes('jpeg')
            image   = Image.open(io.BytesIO(img_data))
            scores_ela.append(analyser_ela_image(image))

        score_ela = float(np.mean(scores_ela)) if scores_ela else 10.0

        premiere_page = pdf[0]
        pix   = premiere_page.get_pixmap(dpi=150)
        img   = Image.open(io.BytesIO(pix.tobytes('jpeg')))
        bruit = analyser_bruit(img)
        dc    = analyser_double_compression(img)
        meta_score, meta_details = 0.7, ['PDF — pas de metadonnees EXIF']

    # ── IMAGE ──
    else:
        image      = Image.open(io.BytesIO(fichier_bytes))
        score_ela  = analyser_ela_image(image)
        bruit      = analyser_bruit(image)
        dc         = analyser_double_compression(image)
        meta_score, meta_details = analyser_metadata(fichier_bytes, nom)

    # ════════════════════════════════════════════════════════
    #  SCORE COMBINÉ — Calibré pour docs guinéens
    #
    #  ELA norm    : seuil /40 (tolérant le guilloché + scan)
    #  Bruit adj   : seuil 0.50 — le guilloché crée un bruit
    #                naturel et UNIFORME, non suspect
    #  DC ajusté   : seuil 0.45 — scan → double compression
    #                naturelle, non suspect
    #  Métadonnées : 15% (EXIF souvent absent sur les scans)
    #
    #  Verdicts :
    #    ≥ 65%  → authentique
    #    40-64% → révision manuelle
    #    < 40%  → falsifié
    # ════════════════════════════════════════════════════════

    # ELA normalisé — seuil /40 pour tolérer les textures riches
    ela_norm = min(score_ela / 40.0, 1.0)

    # Bruit ajusté — le guilloché guinéen produit bruit naturel ~0.5-1.0
    # On ignore tout ce qui est en dessous de 0.50
    bruit_ajuste = max(0.0, bruit - 0.50) / 0.50 if bruit > 0.50 else bruit * 0.4

    # Double compression ajustée — seuil 0.45 pour scans naturels
    dc_ajuste = max(0.0, dc - 0.45) / 0.55 if dc > 0.45 else 0.0

    # Score de suspicion global (0 = authentique, 1 = falsifié)
    suspicion = (
        ela_norm            * 0.50 +
        bruit_ajuste        * 0.20 +
        dc_ajuste           * 0.15 +
        (1.0 - meta_score)  * 0.15
    )

    # Convertir en score d'authenticité 0..100
    score_final = round((1.0 - suspicion) * 100, 1)
    score_final = max(5.0, min(98.0, score_final))

    # Verdicts
    if score_final >= 65:
        verdict = 'authentique'
    elif score_final >= 40:
        verdict = 'revision'
    else:
        verdict = 'falsifie'

    return {
        'score_ela':          round(score_ela, 2),
        'score_bruit':        round(bruit, 3),
        'score_double_comp':  round(dc, 3),
        'score_meta':         round(meta_score, 3),
        'meta_details':       meta_details,
        'suspicion':          round(suspicion, 3),
        'score_final':        score_final,
        'verdict':            verdict,
    }
