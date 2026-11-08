# -*- coding: utf-8 -*-
"""
ORT - Fabrique data/city-aliases.json
Pour CHAQUE lieu OneRoadTrip (villes, sites, monuments, nature...), ses noms dans
les langues du site (fr en es it pt ar nl de) et dans la langue du pays.
   "edimbourg" -> "edinburgh"      "chateau d edimbourg" -> "edinburgh castle"
   "londres"   -> "london"         "عين لندن"            -> "london eye"
Sert a la recherche de la page d'accueil et a Lilia.

Source des noms : GeoNames (gratuit). Rapprochement par position GPS + nom.
Premier lancement : telecharge environ 500 Mo (garde en cache, pas dans le site).

Usage :  python build-city-aliases.py                (site dans C:\\OneRoadTrip)
         python build-city-aliases.py D:\\autre\\dossier
         python build-city-aliases.py --liste=lieux.txt  (ajoute les lieux d'une liste
                  Excel "place_id <tab> name" absents des fichiers pays, sans GPS)
Aucun module a installer.
"""
import csv, io, json, math, os, re, sys, tempfile, unicodedata, urllib.request, zipfile, collections

ARGS = [a for a in sys.argv[1:] if not a.startswith('--liste=')]
LISTE = next((a.split('=', 1)[1] for a in sys.argv[1:] if a.startswith('--liste=')), None)
ROOT = ARGS[0] if ARGS else r"C:\OneRoadTrip"
COUNTRIES_DIR = os.path.join(ROOT, 'data', 'Roadtripsprefabriques', 'countries')
OUT = os.path.join(ROOT, 'data', 'city-aliases.json')
CACHE = os.path.join(tempfile.gettempdir(), 'ort-geonames')          # hors du site
REPORT = os.path.join(CACHE, 'lieux-sans-traduction.txt')
GN = 'https://download.geonames.org/export/dump/'
SITE_LANGS = {'fr', 'en', 'es', 'it', 'pt', 'ar', 'nl', 'de'}
CATALOG_FOLDERS = ['itineraires', 'itineraries', 'rutas', 'itinerari', 'roteiros', 'masar', 'routes', 'routen']

csv.field_size_limit(10_000_000)


def norm(s):
    """Minuscules, sans accents, mots separes par un espace (meme regle que la page et Lilia)."""
    s = unicodedata.normalize('NFD', str(s).lower())
    s = ''.join(ch for ch in s if not unicodedata.category(ch).startswith('M'))
    s = re.sub(r"[^\w]+", ' ', s).replace('_', ' ').strip()
    return re.sub(r'\s+', ' ', s)


def clean_place_name(name):
    """Retire les suffixes techniques ("Salzburg Lx" -> "salzburg", "New York, NY" -> "new york")."""
    name = re.sub(r',\s*[A-Z]{2}\s*$', '', str(name))
    return re.sub(r'\s+lx$', '', norm(name))


def script_ok(s):
    """Alphabet latin ou arabe uniquement (langues du site)."""
    for ch in s:
        if ch == ' ':
            continue
        if ch.isdigit():
            return False
        o = ord(ch)
        if not (o < 0x250 or 0x600 <= o <= 0x6ff or 0x1e00 <= o <= 0x1eff):
            return False
    return True


def km(a_lat, a_lon, b_lat, b_lon):
    r = math.radians
    d = math.sin(r(b_lat - a_lat) / 2) ** 2 + math.cos(r(a_lat)) * math.cos(r(b_lat)) * math.sin(r(b_lon - a_lon) / 2) ** 2
    return 2 * 6371 * math.asin(math.sqrt(d))


def fetch(rel):
    """Telecharge un fichier GeoNames une seule fois (cache)."""
    path = os.path.join(CACHE, *rel.split('/'))
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f"  telechargement {rel} ...")
    try:
        with urllib.request.urlopen(GN + rel, timeout=600) as r, open(path + '.part', 'wb') as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        os.replace(path + '.part', path)
        return path
    except Exception as e:
        print(f"  ECHEC {rel} : {e}")
        return None


def zip_lines(path):
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.endswith('.txt') and not n.lower().startswith('readme')][0]
        with z.open(name) as f:
            for line in io.TextIOWrapper(f, encoding='utf-8'):
                yield line.rstrip('\n').split('\t')


# ---------------------------------------------------------------------------
# 1) Les lieux OneRoadTrip (avec GPS) depuis les fichiers pays
# ---------------------------------------------------------------------------
if not os.path.isdir(COUNTRIES_DIR):
    sys.exit(f"Dossier introuvable : {COUNTRIES_DIR}\nIndique le dossier du site en argument.")
places = {}
for d in os.listdir(COUNTRIES_DIR):
    folder = os.path.join(COUNTRIES_DIR, d)
    if not os.path.isdir(folder):
        continue
    files = {f.lower(): f for f in os.listdir(folder)}
    for lang in ['en', 'fr']:
        f = files.get(f"{d.lower()}.places.master-{lang}.json")
        if f:
            for p in json.load(open(os.path.join(folder, f), encoding='utf-8')).get('places', []):
                pid = p.get('place_id')
                if pid and pid not in places:
                    places[pid] = p
            break

if LISTE:
    ajout = 0
    for line in open(LISTE, encoding='utf-8-sig'):
        cols = line.rstrip('\n').split('\t')
        if len(cols) >= 2 and '::' in cols[0] and cols[0] not in places:
            places[cols[0]] = {'place_id': cols[0], 'name': cols[1], 'cc': cols[0].split('::')[0]}
            ajout += 1
    print(f"Liste {LISTE} : {ajout} lieux ajoutes (absents des fichiers pays)")

# Lieux cites dans les itineraires (noms tels qu'ecrits dans les catalogues de recherche)
catalog_names = set()
for folder in CATALOG_FOLDERS:
    dd = os.path.join(ROOT, folder)
    if os.path.isdir(dd):
        for f in os.listdir(dd):
            if f.startswith('search-catalog-') and f.endswith('.json'):
                for r in json.load(open(os.path.join(dd, f), encoding='utf-8')):
                    for c in (r.get('cities') or []):
                        catalog_names.add(norm(c))

items = []   # un element par lieu : canon (nom nettoye), cc, lat, lon
for pid, p in places.items():
    cc = (p.get('cc') or pid.split('::')[0]).upper()
    lat, lon = p.get('lat'), p.get('lon')
    items.append({'id': pid, 'canon': clean_place_name(p.get('name') or pid.split('::')[-1].replace('-', ' ')),
                  'cc': cc, 'lat': lat if isinstance(lat, (int, float)) else None,
                  'lon': lon if isinstance(lon, (int, float)) else None})
all_canon = {it['canon'] for it in items} | catalog_names
by_cc = collections.defaultdict(list)
for it in items:
    by_cc[it['cc']].append(it)
print(f"Lieux OneRoadTrip : {len(items)} dans {len(by_cc)} pays  |  noms dans les itineraires : {len(catalog_names)}")

# Langues officielles de chaque pays (pour garder aussi "Praha", "Wien", "Munchen"...)
local_langs = collections.defaultdict(set)
ci = fetch('countryInfo.txt')
if ci:
    for line in open(ci, encoding='utf-8'):
        if line.startswith('#'):
            continue
        cols = line.rstrip('\n').split('\t')
        if len(cols) > 15:
            local_langs[cols[0]] = {x.split('-')[0] for x in cols[15].split(',') if x}

# ---------------------------------------------------------------------------
# 2) Rapprochement avec GeoNames, pays par pays
# ---------------------------------------------------------------------------
GENERIC = {'de', 'la', 'le', 'les', 'du', 'des', 'of', 'the', 'and', 'et', 'el', 'del', 'di', 'da', 'do', 'am', 'an', 'der', 'im', 'sur', 'en'}


def tokens(s):
    return {t for t in s.split(' ') if len(t) > 2 and t not in GENERIC}


match = {}          # place id -> (geonameid, population, classe)
gn_names = {}       # geonameid -> set(nom principal, nom ascii)
for cc, lst in sorted(by_cc.items()):
    zp = fetch(f'{cc}.zip')
    if not zp:
        continue
    # grille de 0.1 degre pour ne garder que les entrees proches de nos lieux
    grid = collections.defaultdict(list)
    for it in lst:
        if it['lat'] is not None:
            grid[(int(math.floor(it['lat'] * 10)), int(math.floor(it['lon'] * 10)))].append(it)
    by_name = collections.defaultdict(list)   # pour les lieux sans GPS
    no_gps = {it['canon'] for it in lst if it['lat'] is None}
    best = {}
    for c in zip_lines(zp):
        if len(c) < 15:
            continue
        gid, name, ascii_, alts, fclass = c[0], c[1], c[2], c[3], c[6]
        if fclass in ('R', 'U'):
            continue
        try:
            lat, lon, pop = float(c[4]), float(c[5]), int(c[14] or 0)
        except ValueError:
            continue
        main = norm(name)
        if no_gps:
            for n in {main, norm(ascii_)} & no_gps:
                by_name[n].append((gid, pop, fclass, main))
        gy, gx = int(math.floor(lat * 10)), int(math.floor(lon * 10))
        near = []
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                near.extend(grid.get((gy + dy, gx + dx), ()))
        if not near:
            continue
        names = {main, norm(ascii_)} | {norm(a) for a in alts.split(',') if a}
        names.discard('')
        for it in near:
            d = km(it['lat'], it['lon'], lat, lon)
            if d > 15:
                continue
            if it['canon'] in names:
                # meme nom : jusqu'a 15 km pour une ville, 5 km pour le reste
                if fclass not in ('P', 'A') and d > 5:
                    continue
                score = (0, d - (2 if fclass == 'P' else 0))
            elif fclass not in ('P', 'A') and d <= 3:
                # site ou nature au nom proche ("Alcazaba de la Alhambra" ~ "Alcazaba")
                a, b = tokens(it['canon']), tokens(main)
                if not a or not b or not (a <= b or b <= a) or max(len(t) for t in (a & b) or {''}) < 5:
                    continue
                score = (1, d)
            else:
                continue
            if it['id'] not in best or score < best[it['id']][0]:
                best[it['id']] = (score, gid, pop, fclass)
                gn_names[gid] = {name, ascii_}
    for it in lst:
        if it['id'] in best:
            _, gid, pop, fclass = best[it['id']]
            match[it['id']] = (gid, pop, fclass)
        elif it['lat'] is None and by_name.get(it['canon']):
            gid, pop, fclass, _ = sorted(by_name[it['canon']], key=lambda x: (x[3] != it['canon'], x[2] != 'P', -x[1]))[0]
            match[it['id']] = (gid, pop, fclass)
            gn_names.setdefault(gid, set())
    print(f"  {cc} : {sum(1 for it in lst if it['id'] in match)}/{len(lst)} lieux reconnus")

# ---------------------------------------------------------------------------
# 3) Noms dans les langues du site + langue du pays
# ---------------------------------------------------------------------------
wanted = collections.defaultdict(set)   # geonameid -> noms
gid_cc = {}
for it in items:
    if it['id'] in match:
        gid_cc[match[it['id']][0]] = it['cc']
for gid, nm in gn_names.items():
    if gid in gid_cc:
        wanted[gid] |= {n for n in nm if n}
SKIP_CODES = {'link', 'post', 'iata', 'icao', 'faac', 'wkdt', 'abbr', 'unlc', 'tcid', 'fr_1793', 'phon', 'piny'}
for cc in sorted({c for c in gid_cc.values()}):
    zp = fetch(f'alternatenames/{cc}.zip')
    if not zp:
        continue
    langs = SITE_LANGS | local_langs.get(cc, set()) | {''}
    for c in zip_lines(zp):
        if len(c) < 8 or c[1] not in gid_cc:
            continue
        lang, name = c[2], c[3]
        if lang in SKIP_CODES or lang not in langs:
            continue
        if c[6] == '1' or c[7] == '1':        # familier ou historique
            continue
        wanted[c[1]].add(name)

alias = collections.defaultdict(set)
for it in items:
    if it['id'] not in match:
        continue
    gid, pop, fclass = match[it['id']]
    for a in wanted.get(gid, ()):
        if not a or re.fullmatch(r'[A-Z]{3,4}', a) or not script_ok(a):
            continue
        n = clean_place_name(a)
        if len(n) < 4 or n == it['canon']:
            continue
        # alias qui est aussi un autre lieu ORT (Vienne FR / Wien AT) : seulement pour les grandes villes
        if n in all_canon and not (fclass == 'P' and pop >= 300000):
            continue
        alias[n].add(it['canon'])

# un alias qui designe plus de 5 lieux est trop vague
out = {k: sorted(v) for k, v in sorted(alias.items()) if len(v) <= 5}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, 'w', encoding='utf-8') as f:
    json.dump(out, f, ensure_ascii=False, separators=(',', ':'))

missing = sorted(it['id'] for it in items if it['id'] not in match)
with open(REPORT, 'w', encoding='utf-8') as f:
    f.write('\n'.join(missing))
print(f"\nLieux reconnus : {len(match)}/{len(items)}  |  noms ajoutes : {len(out)}")
print(f"Ecrit : {OUT}  ({os.path.getsize(OUT) // 1024} Ko)")
print(f"Lieux sans traduction trouvee ({len(missing)}) : {REPORT}")
for t in ['edimbourg', 'londres', 'venise', 'pekin', 'la haye', 'chateau d edimbourg', 'tour eiffel']:
    print(f"  test {t} -> {out.get(t)}")
