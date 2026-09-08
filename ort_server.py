#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OneRoadTrip Development Server
------------------------------
Serveur de développement local avec endpoint pour sauvegarder les itinéraires.

Usage:
    python ort_server.py [port]
    
Par défaut, port 8030.
"""

import http.server
import socketserver
import io
import json
import os
import shutil
import time
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import sys
import re
import threading
import unicodedata

# Un verrou par fichier pays. Voir handle_save_itinerary : sans lui, deux
# enregistrements simultanes dans le meme fichier en perdent un.
SAVE_VERROUS = {}
SAVE_VERROUS_LOCK = threading.Lock()


def ecrire_json_atomique(chemin, donnees):
    """Ecrit un JSON sans jamais laisser le fichier a moitie ecrit.

    On ecrit dans un fichier temporaire du meme dossier, on force le vidage
    sur disque, puis on remplace l original d un seul coup. os.replace est
    atomique sur Windows comme sur Linux. Un lecteur simultane voit donc
    toujours un fichier complet, ancien ou nouveau, jamais un tronc.
    """
    dossier = os.path.dirname(os.path.abspath(chemin)) or '.'
    provisoire = os.path.join(dossier, '.tmp_%d_%s' % (os.getpid(), os.path.basename(chemin)))
    try:
        with open(provisoire, 'w', encoding='utf-8', newline='\n') as f:
            json.dump(donnees, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(provisoire, chemin)
    except Exception:
        try:
            if os.path.exists(provisoire):
                os.remove(provisoire)
        except Exception:
            pass
        raise


def backup_unique(chemin):
    """Copie de secours a nom GARANTI unique. Renvoie le chemin du backup.

    Avant, le nom etait fabrique a la seconde pres, sans suffixe. Deux
    enregistrements dans la meme seconde produisaient le meme nom et le
    second ecrasait le premier : la version d origine etait perdue, et le
    scan des accents finissait par comparer un fichier a un backup deja
    abime. Le defaut avait deja ete corrige pour input/ dans _trad_backup,
    la correction n avait jamais ete reportee sur les fichiers pays.
    """
    base = '%s.backup_%s' % (chemin, datetime.now().strftime('%Y%m%d_%H%M%S'))
    dest = base
    n = 1
    while os.path.exists(dest):
        dest = '%s-%d' % (base, n)
        n += 1
    shutil.copy2(chemin, dest)
    return dest


# Lecture tolérante des réponses d'audit (doit être dans le même dossier).
# Le serveur continue de tourner sans, mais la réinjection redevient fragile.
try:
    from ort_audit_lecture import lire_reponse as audit_lire_reponse
    AUDIT_LECTURE_OK = True
except Exception as _e:
    AUDIT_LECTURE_OK = False
    print("[claude-audit] ort_audit_lecture.py absent, lecture des reponses degradee: %r" % (_e,))

    def audit_lire_reponse(texte, cles=None, langues=None, racine=None):
        return {'ok': False, 'blocs': [], 'anomalies': ['module de lecture absent'],
                'erreur': 'ort_audit_lecture.py introuvable', 'source': 'direct',
                'fichier': '', 'verdict': '', 'motif': '', 'langue': '', 'inconnues': []}

# Module photos (doit être dans le même dossier)
try:
    from ort_photos_api import (
        handle_search, handle_select, handle_get_places,
        handle_mark_done, handle_get_done, handle_get_new_places,
        handle_delete_photo, handle_list_r2_photos,
        handle_viewer_seen_add, handle_viewer_seen_get, handle_viewer_seen_reset,
        handle_couples_list, handle_couples_get, handle_couples_save, handle_couples_refresh,
        handle_couples_by_place,
        handle_couples_remove_photo, handle_couples_clear_pool,
        handle_couples_precache_start, handle_couples_precache_progress, handle_couples_precache_stop,
        handle_itins_list, handle_itin_places,
        handle_upload_file
    )
    PHOTOS_API_AVAILABLE = True
    print("[PHOTOS] Module photos chargé ✅")
except ImportError as e:
    PHOTOS_API_AVAILABLE = False
    print(f"[PHOTOS] Module photos non disponible: {e}")

# Module Google Places (optionnel)
try:
    from ort_google_places import (
        handle_gplaces_start, handle_gplaces_progress, handle_gplaces_stop,
        handle_gplaces_pending, handle_gplaces_pending_photos,
        handle_gplaces_validate, handle_gplaces_upload_r2,
        handle_pending_file,
        handle_gplaces_search_merged, handle_gplaces_mark_revisit,
        handle_gplaces_list_revisit, handle_gplaces_unmark_revisit,
        handle_gplaces_cleanup_pending, handle_gplaces_fetch_keyword,
    )
    GPLACES_API_AVAILABLE = True
    print("[GPLACES] Module Google Places chargé ✅")
except ImportError as e:
    GPLACES_API_AVAILABLE = False
    print(f"[GPLACES] Module Google Places non disponible: {e}")

# Module Wiki cache (optionnel)
try:
    from ort_wiki_cache_api import (
        handle_wcache_start, handle_wcache_stop, handle_wcache_progress,
    )
    WCACHE_API_AVAILABLE = True
    print("[WCACHE] Module Wiki cache chargé ✅")
except ImportError as e:
    WCACHE_API_AVAILABLE = False
    print(f"[WCACHE] Module Wiki cache non disponible: {e}")

# Module Hôtels (sélection manuelle + photo vitrine)
try:
    from ort_hotels_api import (
        handle_hotels_places, handle_hotels_fetch_gallery,
        handle_hotels_set_cover, handle_hotels_remove_hotel,
        handle_hotels_remove_photo, handle_hotels_set_slot,
        handle_hotels_set_photos, handle_hotels_set_elite,
        handle_hotels_set_super_elite,
        handle_hotels_itins,
        handle_hotels_itin_prepare, handle_hotels_itin_autofill,
        handle_hotels_search_place,
        handle_hotels_propose, handle_hotels_apply,
        handle_hotels_add_from_booking, handle_hotels_add_prepared,
        handle_hotels_resolve_booking, handle_hotels_set_hotel_meta,
        handle_hotels_sync_super_elites,
        handle_hotels_set_place_flag, handle_hotels_verify_broken,
        handle_hotels_picks_for_booking,
        handle_hotels_fix_broken,
        handle_hotels_remove_hotel_everywhere,
        handle_hotels_mark_done,
        handle_hotels_get_done, handle_hotels_diag,
        handle_hotels_scrape_hotel, handle_hotels_scrape_country,
        handle_hotels_scrape_status, handle_hotels_scrape_stop,
        handle_hotels_img_proxy,
        handle_hotels_clean_broken,
        handle_hotels_clean_status,
        handle_hotels_clear_cache,
    )
    HOTELS_API_AVAILABLE = True
    print("[HOTELS] Module hôtels chargé ✅")
except ImportError as e:
    HOTELS_API_AVAILABLE = False
    print(f"[HOTELS] Module hôtels non disponible: {e}")

try:
    import ort_viator_api
    VIATOR_API_AVAILABLE = True
    print("[VIATOR] Module Viator chargé ✅")
except ImportError as e:
    VIATOR_API_AVAILABLE = False
    print(f"[VIATOR] Module Viator non disponible: {e}")

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8030


def fix_double_utf8(text):
    """
    Corrige le double encodage UTF-8 (UTF-8 encodé en Latin-1 puis ré-encodé).
    Exemple: "ChÃ¢teau" → "Château"
    """
    if not isinstance(text, str):
        return text
    
    # Méthode robuste : tenter de décoder le double encodage
    try:
        # Si le texte contient des séquences UTF-8 mal interprétées
        fixed = text.encode('latin-1').decode('utf-8')
        return fixed
    except (UnicodeDecodeError, UnicodeEncodeError):
        pass
    
    # Fallback : remplacements manuels des patterns courants
    replacements = [
        ('Ã©', 'é'), ('Ã¨', 'è'), ('Ãª', 'ê'), ('Ã«', 'ë'),
        ('Ã ', 'à'), ('Ã¢', 'â'), ('Ã¤', 'ä'),
        ('Ã¯', 'ï'), ('Ã®', 'î'), ('Ã¬', 'ì'),
        ('Ã´', 'ô'), ('Ã¶', 'ö'), ('Ã²', 'ò'),
        ('Ã¹', 'ù'), ('Ã»', 'û'), ('Ã¼', 'ü'),
        ('Ã§', 'ç'), ('Ã±', 'ñ'),
        ('Ã‰', 'É'), ('Ã€', 'À'), ('Ã‚', 'Â'),
        ('Ã"', 'Ô'), ('Ã›', 'Û'), ('Ã‡', 'Ç'),
    ]
    
    result = text
    # Apostrophe typographique
    result = result.replace('\xe2\x80\x99', "'")
    result = result.replace('â€™', "'")
    # Tirets
    result = result.replace('â€"', '–')
    result = result.replace('â€"', '—')
    # Guillemets
    result = result.replace('â€œ', '"')
    result = result.replace('â€', '"')
    
    for bad, good in replacements:
        result = result.replace(bad, good)
    
    return result


def fix_encoding_recursive(obj):
    """
    Applique la correction d'encodage récursivement sur un objet JSON.
    """
    if isinstance(obj, str):
        return fix_double_utf8(obj)
    elif isinstance(obj, dict):
        return {k: fix_encoding_recursive(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [fix_encoding_recursive(item) for item in obj]
    else:
        return obj

ITINS_BASE_DIR = "data/Roadtripsprefabriques/countries"


def detect_languages(country_code=None):
    """
    Liste les langues réellement présentes sur le disque.
    Lit les noms de fichiers <CC>.itins.modules-<lang>.json.
    Aucune liste codée en dur : ajouter un fichier suffit.
    """
    langs = set()
    if not os.path.exists(ITINS_BASE_DIR):
        return []

    folders = []
    for name in os.listdir(ITINS_BASE_DIR):
        full = os.path.join(ITINS_BASE_DIR, name)
        if not os.path.isdir(full):
            continue
        if country_code and name.upper() != country_code.upper():
            continue
        folders.append(full)

    for folder in folders:
        try:
            for fname in os.listdir(folder):
                m = re.search(r'\.itins\.modules-([a-z]{2,3})\.json$', fname, re.IGNORECASE)
                if m:
                    langs.add(m.group(1).lower())
        except Exception:
            continue

    ordered = sorted(langs)
    # 'fr' en tête si présent, le reste par ordre alphabétique
    if 'fr' in ordered:
        ordered.remove('fr')
        ordered.insert(0, 'fr')
    return ordered


class ORTRequestHandler(http.server.SimpleHTTPRequestHandler):
    """Handler HTTP avec support des API OneRoadTrip."""
    
    def do_OPTIONS(self):
        """Gérer les requêtes CORS preflight."""
        self.send_response(200)
        # Note: Access-Control-Allow-Origin ajouté automatiquement par end_headers()
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
    
    def do_POST(self):
        """Gérer les requêtes POST (API)."""
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/trad-input/save':
            self.handle_trad_input_save()
        elif parsed.path == '/api/trad-input/valides':
            self.handle_trad_input_valides_set()
        elif parsed.path == '/api/trad-input/restore':
            self.handle_trad_input_restore()
        elif parsed.path == '/api/trad-input/delete':
            self.handle_trad_input_delete()
        elif parsed.path == '/api/trad-input/integre':
            self.handle_trad_input_integre()
        elif parsed.path == '/api/claude-audit':
            self.handle_claude_audit()
        elif parsed.path == '/api/audit-lire':
            self.handle_audit_lire()
        elif parsed.path == '/api/suivi-audits/set':
            self.handle_suivi_set()
        elif parsed.path == '/api/suivi-audits/importer':
            self.handle_suivi_importer()
        elif parsed.path == '/api/controles/ajouter':
            self.handle_controle_ajouter()
        elif parsed.path == '/api/mots-repares':
            self.handle_mots_repares()
        elif parsed.path == '/api/accents-refuses/action':
            self.handle_prison_action()
        elif parsed.path == '/api/audits-attente/action':
            self.handle_spool_action()
        elif parsed.path == '/api/save-itinerary':
            self.handle_save_itinerary()
        elif parsed.path == '/api/save-help':
            self.handle_save_help()
        elif parsed.path == '/api/save-verifications':
            self.handle_save_verifications()
        elif parsed.path == '/api/save-validations':
            self.handle_save_validations()
        elif parsed.path == '/api/delete-itinerary':
            self.handle_delete_itinerary()
        elif parsed.path == '/api/stats/cache':
            self.handle_stats_cache_post()
        elif parsed.path.startswith('/api/photos/') and PHOTOS_API_AVAILABLE:
            self.handle_photos_post(parsed.path)
        elif parsed.path.startswith('/api/gplaces/') and GPLACES_API_AVAILABLE:
            self.handle_gplaces_post(parsed.path)
        elif parsed.path.startswith('/api/wcache/') and WCACHE_API_AVAILABLE:
            self.handle_wcache_post(parsed.path)
        elif parsed.path.startswith('/api/hotels/') and HOTELS_API_AVAILABLE:
            self.handle_hotels_post(parsed.path)
        elif parsed.path.startswith('/api/viator/') and VIATOR_API_AVAILABLE:
            self.handle_viator_post(parsed.path)
        else:
            self.send_error(404, f"Endpoint not found: {parsed.path}")
    
    def do_GET(self):
        """Gérer les requêtes GET (fichiers statiques + API photos)."""
        parsed = urlparse(self.path)
        
        if parsed.path == '/api/languages':
            self.handle_languages(parse_qs(parsed.query))
        elif parsed.path == '/api/suivi-audits':
            self.handle_suivi_get()
        elif parsed.path == '/api/verifier-accents':
            self.handle_verifier_accents(parse_qs(parsed.query))
        elif parsed.path == '/api/accents-refuses':
            self.handle_prison_get()
        elif parsed.path == '/api/audits-attente':
            self.handle_spool_get()
        elif parsed.path == '/api/mots-repares':
            self.handle_mots_repares_get()
        elif parsed.path == '/api/controles':
            self.handle_controles_get(parse_qs(parsed.query))
        elif parsed.path == '/api/trad-input/list':
            self.handle_trad_input_list()
        elif parsed.path == '/api/trad-input/get':
            self.handle_trad_input_get(parse_qs(parsed.query))
        elif parsed.path == '/api/trad-input/backups':
            self.handle_trad_input_backups(parse_qs(parsed.query))
        elif parsed.path == '/api/trad-input/valides':
            self.handle_trad_input_valides_get()
        elif parsed.path == '/api/stats/cache':
            self.handle_stats_cache_get()
        elif parsed.path.startswith('/api/photos/') and PHOTOS_API_AVAILABLE:
            self.handle_photos_get(parsed.path, parse_qs(parsed.query))
        elif parsed.path.startswith('/api/gplaces/') and GPLACES_API_AVAILABLE:
            self.handle_gplaces_get(parsed.path, parse_qs(parsed.query))
        elif parsed.path.startswith('/api/wcache/') and WCACHE_API_AVAILABLE:
            self.handle_wcache_get(parsed.path)
        elif parsed.path.startswith('/api/hotels/') and HOTELS_API_AVAILABLE:
            self.handle_hotels_get(parsed.path, parse_qs(parsed.query))
        elif parsed.path.startswith('/api/viator/') and VIATOR_API_AVAILABLE:
            self.handle_viator_get(parsed.path, parse_qs(parsed.query))
        elif parsed.path.startswith('/pending-files/') and GPLACES_API_AVAILABLE:
            self.handle_pending_file_get(parsed.path)
        else:
            # Servir les fichiers statiques normalement
            super().do_GET()
    
    def handle_viator_get(self, path, qs):
        """Router les GET /api/viator/*."""
        try:
            country = (qs.get('country', [''])[0] or '')
            if path == '/api/viator/status':
                self.send_json_response(200, ort_viator_api.status(country))
            elif path == '/api/viator/cache':
                self.send_json_response(200, ort_viator_api.get_cache(country))
            elif path == '/api/viator/countries':
                self.send_json_response(200, {'success': True, 'countries': ort_viator_api._list_countries()})
            elif path == '/api/viator/progress':
                self.send_json_response(200, ort_viator_api.progress())
            else:
                self.send_error(404, f"Viator endpoint not found: {path}")
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_viator_post(self, path):
        """Router les POST /api/viator/*."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            raw = self.rfile.read(length) if length else b'{}'
            body = json.loads(raw.decode('utf-8') or '{}')
            if path == '/api/viator/save':
                self.send_json_response(200, ort_viator_api.save_valid(body))
            elif path == '/api/viator/build':
                self.send_json_response(200, ort_viator_api.build(body))
            else:
                self.send_error(404, f"Viator endpoint not found: {path}")
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_photos_post(self, path):
        """Router les POST /api/photos/*."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8')) if body else {}
            
            if path == '/api/photos/search':
                status, result = handle_search(data)
            elif path == '/api/photos/select':
                status, result = handle_select(data)
            elif path == '/api/photos/upload-file':
                status, result = handle_upload_file(data)
            elif path == '/api/photos/mark-done':
                status, result = handle_mark_done(data)
            elif path == '/api/photos/delete':
                status, result = handle_delete_photo(data)
            elif path == '/api/photos/viewer-seen':
                status, result = handle_viewer_seen_add(data)
            elif path == '/api/photos/viewer-reset':
                status, result = handle_viewer_seen_reset()
            elif path == '/api/photos/couples/save':
                status, result = handle_couples_save(data)
            elif path == '/api/photos/couples/refresh':
                status, result = handle_couples_refresh(data)
            elif path == '/api/photos/couples/remove-photo':
                status, result = handle_couples_remove_photo(data)
            elif path == '/api/photos/couples/clear-pool':
                status, result = handle_couples_clear_pool(data)
            elif path == '/api/photos/couples/precache/start':
                status, result = handle_couples_precache_start(data)
            elif path == '/api/photos/couples/precache/stop':
                status, result = handle_couples_precache_stop(data)
            else:
                status, result = 404, {"error": f"Unknown: {path}"}
            
            self.send_json_response(status, result)
        except Exception as e:
            print(f"[PHOTOS ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response(500, {"error": str(e)})
    
    def handle_photos_get(self, path, query_params):
        """Router les GET /api/photos/*."""
        try:
            if path == '/api/photos/places':
                status, result = handle_get_places(query_params)
            elif path == '/api/photos/done':
                status, result = handle_get_done()
            elif path == '/api/photos/new-places':
                status, result = handle_get_new_places(query_params)
            elif path == '/api/photos/r2-list':
                status, result = handle_list_r2_photos(query_params)
            elif path == '/api/photos/viewer-seen':
                status, result = handle_viewer_seen_get()
            elif path == '/api/photos/couples/list':
                status, result = handle_couples_list(query_params)
            elif path == '/api/photos/couples/get':
                status, result = handle_couples_get(query_params)
            elif path == '/api/photos/couples/by-place':
                status, result = handle_couples_by_place(query_params)
            elif path == '/api/photos/couples/precache/progress':
                status, result = handle_couples_precache_progress()
            elif path == '/api/photos/itins/list':
                status, result = handle_itins_list(query_params)
            elif path == '/api/photos/itins/places':
                status, result = handle_itin_places(query_params)
            else:
                status, result = 404, {"error": f"Unknown: {path}"}
            
            self.send_json_response(status, result)
        except Exception as e:
            print(f"[PHOTOS ERROR] {e}")
            self.send_json_response(500, {"error": str(e)})

    def handle_hotels_post(self, path):
        """Router les POST /api/hotels/*."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8')) if body else {}

            if path == '/api/hotels/fetch-gallery':
                status, result = handle_hotels_fetch_gallery(data)
            elif path == '/api/hotels/set-cover':
                status, result = handle_hotels_set_cover(data)
            elif path == '/api/hotels/set-slot':
                status, result = handle_hotels_set_slot(data)
            elif path == '/api/hotels/set-photos':
                status, result = handle_hotels_set_photos(data)
            elif path == '/api/hotels/set-elite':
                status, result = handle_hotels_set_elite(data)
            elif path == '/api/hotels/set-super-elite':
                status, result = handle_hotels_set_super_elite(data)
            elif path == '/api/hotels/itin-prepare':
                status, result = handle_hotels_itin_prepare(data)
            elif path == '/api/hotels/itin-autofill':
                status, result = handle_hotels_itin_autofill(data)
            elif path == '/api/hotels/remove-hotel':
                status, result = handle_hotels_remove_hotel(data)
            elif path == '/api/hotels/remove-photo':
                status, result = handle_hotels_remove_photo(data)
            elif path == '/api/hotels/scrape-hotel':
                status, result = handle_hotels_scrape_hotel(data)
            elif path == '/api/hotels/scrape-country':
                status, result = handle_hotels_scrape_country(data)
            elif path == '/api/hotels/search-place':
                status, result = handle_hotels_search_place(data)
            elif path == '/api/hotels/propose':
                status, result = handle_hotels_propose(data)
            elif path == '/api/hotels/apply':
                status, result = handle_hotels_apply(data)
            elif path == '/api/hotels/scrape-stop':
                status, result = handle_hotels_scrape_stop()
            elif path == '/api/hotels/clean-broken':
                status, result = handle_hotels_clean_broken(data)
            elif path == '/api/hotels/clear-cache':
                status, result = handle_hotels_clear_cache()
            elif path == '/api/hotels/add-from-booking':
                status, result = handle_hotels_add_from_booking(data)
            elif path == '/api/hotels/add-prepared':
                status, result = handle_hotels_add_prepared(data)
            elif path == '/api/hotels/resolve-booking':
                status, result = handle_hotels_resolve_booking(data)
            elif path == '/api/hotels/sync-super-elites':
                status, result = handle_hotels_sync_super_elites(data)
            elif path == '/api/hotels/set-hotel-meta':
                status, result = handle_hotels_set_hotel_meta(data)
            elif path == '/api/hotels/set-place-flag':
                status, result = handle_hotels_set_place_flag(data)
            elif path == '/api/hotels/verify-broken':
                status, result = handle_hotels_verify_broken(data)
            elif path == '/api/hotels/picks-for-booking':
                status, result = handle_hotels_picks_for_booking(data)
            elif path == '/api/hotels/fix-broken':
                status, result = handle_hotels_fix_broken(data)
            elif path == '/api/hotels/remove-hotel-everywhere':
                status, result = handle_hotels_remove_hotel_everywhere(data)
            elif path == '/api/hotels/mark-done':
                status, result = handle_hotels_mark_done(data)
            else:
                status, result = 404, {"error": f"Unknown: {path}"}

            self.send_json_response(status, result)
        except Exception as e:
            print(f"[HOTELS ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response(500, {"error": str(e)})

    def handle_hotels_get(self, path, query_params):
        """Router les GET /api/hotels/*."""
        # Relais d'image (réponse binaire, pas JSON).
        if path == '/api/hotels/img-proxy':
            try:
                status, data, ctype = handle_hotels_img_proxy(query_params)
                if status == 200 and data:
                    self.send_response(200)
                    self.send_header('Content-Type', ctype or 'image/jpeg')
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self.send_error(status or 404)
            except Exception as e:
                print(f"[IMG PROXY ERROR] {e}")
                self.send_error(500, str(e))
            return
        try:
            if path == '/api/hotels/places':
                status, result = handle_hotels_places(query_params)
            elif path == '/api/hotels/diag':
                status, result = handle_hotels_diag(query_params)
            elif path == '/api/hotels/scrape-status':
                status, result = handle_hotels_scrape_status()
            elif path == '/api/hotels/clean-status':
                status, result = handle_hotels_clean_status()
            elif path == '/api/hotels/done':
                status, result = handle_hotels_get_done()
            elif path == '/api/hotels/itins':
                status, result = handle_hotels_itins(query_params)
            else:
                status, result = 404, {"error": f"Unknown: {path}"}

            self.send_json_response(status, result)
        except Exception as e:
            print(f"[HOTELS ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response(500, {"error": str(e)})

    def handle_gplaces_post(self, path):
        """Router les POST /api/gplaces/*."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8')) if body else {}

            if path == '/api/gplaces/start':
                status, result = handle_gplaces_start(data)
            elif path == '/api/gplaces/stop':
                status, result = handle_gplaces_stop()
            elif path == '/api/gplaces/validate':
                status, result = handle_gplaces_validate(data)
            elif path == '/api/gplaces/upload-r2':
                status, result = handle_gplaces_upload_r2(data)
            elif path == '/api/gplaces/search-merged':
                status, result = handle_gplaces_search_merged(data)
            elif path == '/api/gplaces/mark-revisit':
                status, result = handle_gplaces_mark_revisit(data)
            elif path == '/api/gplaces/unmark-revisit':
                status, result = handle_gplaces_unmark_revisit(data)
            elif path == '/api/gplaces/cleanup-pending':
                status, result = handle_gplaces_cleanup_pending(data)
            elif path == '/api/gplaces/fetch-keyword':
                status, result = handle_gplaces_fetch_keyword(data)
            else:
                status, result = 404, {"error": f"Unknown: {path}"}

            self.send_json_response(status, result)
        except Exception as e:
            print(f"[GPLACES ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response(500, {"error": str(e)})

    def handle_gplaces_get(self, path, query_params):
        """Router les GET /api/gplaces/*."""
        try:
            if path == '/api/gplaces/progress':
                status, result = handle_gplaces_progress()
            elif path == '/api/gplaces/pending':
                status, result = handle_gplaces_pending(query_params)
            elif path == '/api/gplaces/pending-photos':
                status, result = handle_gplaces_pending_photos(query_params)
            elif path == '/api/gplaces/revisit':
                status, result = handle_gplaces_list_revisit()
            else:
                status, result = 404, {"error": f"Unknown: {path}"}

            self.send_json_response(status, result)
        except Exception as e:
            print(f"[GPLACES ERROR] {e}")
            self.send_json_response(500, {"error": str(e)})

    def handle_pending_file_get(self, path):
        """Servir un fichier local depuis data/photos-pending/ pour la visionneuse."""
        try:
            status, data, ctype = handle_pending_file(path)
            if status == 200 and data:
                self.send_response(200)
                self.send_header('Content-Type', ctype or 'image/jpeg')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_error(status or 404)
        except Exception as e:
            print(f"[PENDING FILE ERROR] {e}")
            self.send_error(500, str(e))

    def handle_wcache_post(self, path):
        """Router POST /api/wcache/*."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8')) if body else {}

            if path == '/api/wcache/start':
                status, result = handle_wcache_start(data)
            elif path == '/api/wcache/stop':
                status, result = handle_wcache_stop()
            else:
                status, result = 404, {"error": f"Unknown: {path}"}

            self.send_json_response(status, result)
        except Exception as e:
            print(f"[WCACHE ERROR] {e}")
            import traceback
            traceback.print_exc()
            self.send_json_response(500, {"error": str(e)})

    def handle_wcache_get(self, path):
        """Router GET /api/wcache/*."""
        try:
            if path == '/api/wcache/progress':
                status, result = handle_wcache_progress()
            else:
                status, result = 404, {"error": f"Unknown: {path}"}
            self.send_json_response(status, result)
        except Exception as e:
            print(f"[WCACHE ERROR] {e}")
            self.send_json_response(500, {"error": str(e)})
    
    # ------------------------------------------------------------------
    # Cache des statistiques : data/stats-cache.json
    # Lu au chargement de admin-hub.html, reecrit apres chaque synchro.
    # Survit a la navigation privee et au changement de navigateur.
    # ------------------------------------------------------------------
    STATS_CACHE_PATH = 'data/stats-cache.json'

    def handle_stats_cache_get(self):
        """Renvoyer le cache des mesures deja lues."""
        try:
            path = ORTRequestHandler.STATS_CACHE_PATH
            if not os.path.exists(path):
                self.send_json_response(200, {'success': True, 'events': [], 'lastTs': None})
                return
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            events = data.get('events', [])
            last_ts = data.get('lastTs')
            print(f"[STATS] Cache lu: {len(events)} mesures")
            self.send_json_response(200, {'success': True, 'events': events, 'lastTs': last_ts})
        except Exception as e:
            print(f"[STATS ERROR] Lecture: {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_stats_cache_post(self):
        """Ecrire le cache des mesures sur disque (ecriture atomique)."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            data = json.loads(body.decode('utf-8'))
            events = data.get('events')
            if not isinstance(events, list):
                self.send_json_response(400, {'success': False, 'error': 'Missing events'})
                return
            payload = {
                'lastTs': data.get('lastTs'),
                'savedAt': int(time.time() * 1000),
                'count': len(events),
                'events': events,
            }
            path = ORTRequestHandler.STATS_CACHE_PATH
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + '.tmp'
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            os.replace(tmp, path)
            print(f"[STATS] Cache ecrit: {len(events)} mesures -> {path}")
            self.send_json_response(200, {'success': True, 'count': len(events), 'path': path})
        except Exception as e:
            print(f"[STATS ERROR] Ecriture: {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_languages(self, query_params):
        """Renvoyer les langues présentes sur le disque (pays précis ou toutes)."""
        try:
            country = (query_params.get('country', [''])[0] or '').strip()
            langs = detect_languages(country if country else None)
            self.send_json_response(200, {
                'success': True,
                'country': country.upper() if country else None,
                'languages': langs
            })
        except Exception as e:
            print(f"[LANGS ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e), 'languages': []})

    def handle_save_help(self):
        """Sauvegarder un article d'aide dans data/help/<slug>.json."""
        try:
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            article = json.loads(body.decode('utf-8'))
            slug = article.get('slug', '').strip()
            if not slug:
                self.send_json_response(400, {'success': False, 'error': 'Missing slug'})
                return
            safe = ''.join(c for c in slug if c.isalnum() or c in '-_')
            os.makedirs('data/help', exist_ok=True)
            path = f"data/help/{safe}.json"
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(article, f, ensure_ascii=False, indent=2)
            print(f"[HELP] Article sauvegarde: {path}")
            self.send_json_response(200, {'success': True, 'path': path})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def _audit_repondre(self, code, data):
        """Repond au navigateur sans planter s il a deja raccroche.

        Un audit dure une a deux minutes. Pendant ce temps l onglet peut etre
        ferme ou recharge, et Edge annule parfois une requete dupliquee. Sans
        ce garde-fou, l ecriture sur une socket morte remontait en exception
        non rattrapee et noyait la console du serveur.
        """
        try:
            self.send_json_response(code, data)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, OSError):
            print("[claude-audit] client deconnecte, reponse non remise")

    def handle_claude_audit(self):
        """Envoie un lot d audit a Claude Code et renvoie sa reponse.

        Passe par la ligne de commande `claude -p`, donc par l abonnement Max :
        aucune cle API, aucune facturation separee. Les consignes voyagent sur
        l entree standard parce que la ligne de commande Windows est limitee a
        environ 8000 caracteres et qu un lot d audit la depasse largement.
        Le serveur ne fait que transporter : il ne relit pas, ne corrige pas.
        """
        import subprocess

        def trace(msg):
            # Python ne journalise la requete qu une fois TERMINEE. Un audit
            # durant une a deux minutes, le log restait muet pendant tout ce
            # temps et on ne savait pas si quelque chose etait parti.
            print('[claude-audit] ' + msg, flush=True)

        trace('requete recue')
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            if longueur <= 0 or longueur > 20 * 1024 * 1024:
                self._audit_repondre(400, {'success': False, 'error': 'Corps de requete vide ou trop gros'})
                return
            data = json.loads(self.rfile.read(longueur).decode('utf-8'))
            charge = data.get('payload')
            if not charge:
                self._audit_repondre(400, {'success': False, 'error': 'Champ payload manquant'})
                return
            if not isinstance(charge, str):
                charge = json.dumps(charge, ensure_ascii=False)
            modele = str(data.get('model') or 'sonnet')
            if modele not in ('sonnet', 'opus', 'haiku'):
                modele = 'sonnet'

            # Les cles attendues, envoyees par le navigateur. C est le signal le
            # plus fort dont dispose le lecteur: meme si le modele traduit TOUS
            # les noms de champs, un bloc reste reconnaissable a sa cle.
            cles = data.get('cles') or []
            if not isinstance(cles, list):
                cles = []
            cles = [str(c) for c in cles if isinstance(c, str)]
            langues = data.get('langues') or []
            if not isinstance(langues, list):
                langues = []

            claude = 'claude.cmd' if os.name == 'nt' else 'claude'
            amorce = ("Tes instructions et tes donnees sont sur l entree standard. "
                      "Lis tout, applique la consigne, et reponds UNIQUEMENT par le JSON demande, "
                      "sans texte avant ni apres. N ecris AUCUN fichier sur le disque.")

            # DOSSIER DE TRAVAIL DEDIE. Claude Code ecrit parfois sa reponse dans
            # un fichier (audit_XX_....json) au lieu de la renvoyer, et il le fait
            # dans son dossier courant : la racine du site se retrouvait polluee.
            # On le lance donc dans un dossier a lui, et on liste apres coup ce
            # qu il y a cree pour le voir dans le log.
            dossier_travail = os.path.join(os.getcwd(), 'data', 'traductions-itineraires',
                                           'audits-claude', 'travail-claude-code')
            if not os.path.isdir(dossier_travail):
                os.makedirs(dossier_travail)
            avant_fichiers = set(os.listdir(dossier_travail))
            args = [claude, '-p', '--model', modele, '--output-format', 'text',
                    '--dangerously-skip-permissions', amorce]

            # PAS de bridage ici, contrairement a translate.js. Traduire ne
            # demande aucun raisonnement, auditer si : il faut comparer chaque
            # bloc a son original et juger. Brider le modele sur cette tache
            # donnait des reponses en 17 secondes pour 45 blocs, ce qui est
            # trop rapide pour etre serieux. On laisse donc les reglages par
            # defaut de Claude Code, quitte a payer quelques tokens de plus.
            env = dict(os.environ)
            env.pop('MAX_THINKING_TOKENS', None)
            env.pop('CLAUDE_CODE_EFFORT_LEVEL', None)

            trace('lot de %d octets, modele %s, lancement de %s' % (len(charge.encode('utf-8')), modele, claude))
            debut = time.time()
            proc = subprocess.run(args, input=charge.encode('utf-8'),
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=900, shell=(os.name == 'nt'), env=env,
                                  cwd=dossier_travail)
            secondes = round(time.time() - debut)
            try:
                nouveaux = sorted(set(os.listdir(dossier_travail)) - avant_fichiers)
                if nouveaux:
                    trace('ATTENTION: Claude Code a cree %d fichier(s) dans %s : %s'
                          % (len(nouveaux), dossier_travail, ', '.join(nouveaux)))
            except Exception as e:
                trace('liste du dossier de travail impossible: ' + repr(e))
            sortie = proc.stdout.decode('utf-8', errors='replace').strip()
            erreur = proc.stderr.decode('utf-8', errors='replace').strip()
            trace('reponse en %ss, code %s, %d octets recus%s'
                  % (secondes, proc.returncode, len(sortie), (', stderr: ' + erreur[:120]) if erreur else ''))

            bas = (sortie + ' ' + erreur).lower()
            if not sortie:
                if '401' in bas or 'unauthorized' in bas or 'authenticate' in bas or 'token has expired' in bas:
                    trace('ECHEC: connexion refusee par Claude Code')
                    self._audit_repondre(200, {'success': False, 'code': 'auth',
                        'error': "Claude Code refuse la connexion. Lance `claude` puis /login dans un terminal.",
                        'detail': erreur[:400]})
                    return
                if 'rate limit' in bas or '429' in bas or 'usage limit' in bas or 'overloaded' in bas:
                    trace('ECHEC: plafond atteint')
                    self._audit_repondre(200, {'success': False, 'code': 'quota',
                        'error': "Plafond atteint. Reessaie plus tard.", 'detail': erreur[:400]})
                    return
                trace('ECHEC: reponse vide')
                self._audit_repondre(200, {'success': False, 'code': 'vide',
                    'error': "Claude Code n a rien renvoye.", 'detail': erreur[:400]})
                return

            # Trace disque: la fenetre du navigateur peut etre fermee, le log
            # de la console defile. Ce fichier reste, et c est lui qu on relit
            # quand une reponse s avere illisible.
            try:
                dossier = os.path.join(os.getcwd(), 'data', 'traductions-itineraires', 'audits-claude')
                if not os.path.isdir(dossier):
                    os.makedirs(dossier)
                horo = datetime.now().strftime('%Y%m%d_%H%M%S%f')
                # NOM PARLANT. Le fichier s appelait seulement <horodatage>_reponse.txt :
                # la reponse etait bien sur le disque, mais rien ne disait a quel
                # itineraire ni a quelle langue elle appartenait, donc une passe
                # ratee etait irrecuperable en pratique. La reference vient du
                # navigateur et sert aussi a rejouer la reponse sans rappeler
                # le modele.
                ref = str(data.get('ref') or '')
                sur = re.sub(r'[^A-Za-z0-9_.-]+', '_', ref)[:90]
                nomf = horo + ('__' + sur if sur else '') + '_reponse.txt'
                with io.open(os.path.join(dossier, nomf), 'w', encoding='utf-8') as fh:
                    fh.write(sortie)
                trace('reponse aussi ecrite dans data/traductions-itineraires/audits-claude/' + nomf)
                if ref:
                    self._spool_ajouter(horo, ref, nomf, sortie)
            except Exception as e:
                trace('trace disque impossible: ' + repr(e))

            # Lecture tolerante. Le navigateur ne devine plus rien: il recoit
            # une liste de blocs deja normalisee, plus la reponse brute au cas ou.
            lecture = audit_lire_reponse(sortie, cles=cles, langues=langues,
                                         racine=dossier_travail)
            trace('lecture: %d bloc(s), source %s%s%s'
                  % (len(lecture.get('blocs') or []), lecture.get('source'),
                     (', erreur: ' + lecture['erreur']) if lecture.get('erreur') else '',
                     (', rattrapages: ' + ' | '.join(lecture.get('anomalies') or []))
                     if lecture.get('anomalies') else ''))

            trace('OK, reponse remise au navigateur')
            self._audit_repondre(200, {'success': True, 'texte': sortie,
                                       'secondes': secondes, 'modele': modele,
                                       'lecture': lecture})

        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            # Le navigateur a raccroche pendant l audit (onglet ferme, rechargement,
            # requete dupliquee annulee par Edge). Il n y a plus personne au bout
            # du fil: on ne tente pas de repondre, sinon la pile explose.
            print("[claude-audit] client deconnecte avant la reponse, requete abandonnee")
        except subprocess.TimeoutExpired:
            trace('ECHEC: pas de reponse en 15 minutes')
            self._audit_repondre(200, {'success': False, 'code': 'timeout',
                'error': "Claude Code n a pas repondu en 15 minutes."})
        except FileNotFoundError:
            trace('ECHEC: claude introuvable dans le PATH')
            self._audit_repondre(200, {'success': False, 'code': 'absent',
                'error': "Claude Code est introuvable. Installe-le avec: npm install -g @anthropic-ai/claude-code"})
        except Exception as e:
            trace('ECHEC inattendu: ' + repr(e))
            self._audit_repondre(500, {'success': False, 'error': str(e)})

    def handle_audit_lire(self):
        """Lit un texte colle a la main avec le meme lecteur que l envoi automatique.

        Une seule implementation pour les deux chemins: ce qui est rattrape
        pour un envoi automatique l est aussi pour un copier-coller, et
        inversement. Ce point d entree n ecrit rien, il ne fait que lire.
        """
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            if longueur <= 0 or longueur > 20 * 1024 * 1024:
                self.send_json_response(400, {'success': False, 'error': 'Corps vide ou trop gros'})
                return
            data = json.loads(self.rfile.read(longueur).decode('utf-8'))
            texte = data.get('texte') or ''
            if not isinstance(texte, str) or not texte.strip():
                self.send_json_response(400, {'success': False, 'error': 'Champ texte manquant'})
                return
            cles = data.get('cles') or []
            cles = [str(c) for c in cles if isinstance(c, str)] if isinstance(cles, list) else []
            langues = data.get('langues') or []
            if not isinstance(langues, list):
                langues = []
            lecture = audit_lire_reponse(texte, cles=cles, langues=langues, racine=os.getcwd())
            print('[audit-lire] %d bloc(s), source %s%s'
                  % (len(lecture.get('blocs') or []), lecture.get('source'),
                     (', ' + lecture['erreur']) if lecture.get('erreur') else ''), flush=True)
            self.send_json_response(200, {'success': True, 'lecture': lecture})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── Suivi des audits : qui a ete verifie, et QUAND ────────────────────
    #
    # Des DATES, pas des cases a cocher. Une case dit "cette langue a ete
    # auditee" mais pas "avant ou apres la derniere correction du francais".
    # Avec des dates, la question devient triviale : une langue est a refaire
    # si le francais a bouge apres son dernier audit. C est ce qui permet de
    # relancer la masse dix fois sans jamais refaire deux fois le meme travail.
    SUIVI_FICHIER = os.path.join('data', 'traductions-itineraires', 'suivi-audits.json')
    SUIVI_LOCK = threading.Lock()

    def _suivi_lire(self):
        try:
            if os.path.isfile(self.SUIVI_FICHIER):
                with io.open(self.SUIVI_FICHIER, 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                    if isinstance(d, dict):
                        return d.get('itineraires') or {}
        except Exception as e:
            print('[suivi] lecture impossible: %r' % (e,))
        return {}

    def handle_suivi_get(self):
        self.send_json_response(200, {'success': True, 'itineraires': self._suivi_lire()})

    def handle_suivi_set(self):
        """Pose une date sur un itineraire : francais valide, ou langue auditee.

        Ecriture en lecture-modification-ecriture sous verrou : l audit en
        masse ecrit ici depuis plusieurs taches a la fois, et ce fichier est
        unique pour tout le projet.
        """
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(longueur).decode('utf-8')) if longueur > 0 else {}
            iid = str(data.get('itineraire') or '').strip()
            if not iid:
                self.send_json_response(400, {'success': False, 'error': 'itineraire manquant'})
                return
            quoi = str(data.get('quoi') or '').strip()      # 'fr' ou un code langue
            if not quoi:
                self.send_json_response(400, {'success': False, 'error': 'champ quoi manquant'})
                return
            effacer = bool(data.get('effacer'))
            horo = datetime.now().isoformat(timespec='seconds')
            with self.SUIVI_LOCK:
                tout = self._suivi_lire()
                fiche = tout.get(iid) or {'fr_valide': '', 'langues': {}}
                if not isinstance(fiche.get('langues'), dict):
                    fiche['langues'] = {}
                if quoi == 'fr':
                    fiche['fr_valide'] = '' if effacer else horo
                else:
                    if effacer:
                        fiche['langues'].pop(quoi, None)
                    else:
                        fiche['langues'][quoi] = horo
                if not fiche.get('fr_valide') and not fiche['langues']:
                    tout.pop(iid, None)
                else:
                    tout[iid] = fiche
                dossier = os.path.dirname(self.SUIVI_FICHIER)
                if dossier and not os.path.isdir(dossier):
                    os.makedirs(dossier)
                ecrire_json_atomique(self.SUIVI_FICHIER,
                                     {'maj': horo, 'itineraires': tout})
            self.send_json_response(200, {'success': True, 'date': ('' if effacer else horo),
                                          'itineraires': tout})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_suivi_importer(self):
        """Pose en masse des dates de validation du francais, sans rien ecraser.

        Sert a amorcer le suivi a partir du journal de traduction. Deux regles
        de prudence :
        - une date DEJA POSEE et plus recente n est jamais remplacee, sinon un
          francais corrige aujourd hui se retrouverait date du mois dernier et
          ses traductions passeraient pour a jour ;
        - une date de LANGUE n est posee que si l appelant affirme cette langue
          relue. Le journal de traduction ne le sait pas et n en envoie pas ;
          verifications-trad.json le sait et en envoie. Marquer relue une
          langue qui ne l a pas ete lui ferait sauter tous les controles.
        Une entree sans 'fr' vrai ne pose aucune date sur le francais : ses
        langues sont enregistrees, mais rien n affirme que le francais a ete
        relu, donc rien ne sera declare perime tant que tu ne l auras pas dit.
        """
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(longueur).decode('utf-8')) if longueur > 0 else {}
            entrees = data.get('entrees')
            if not isinstance(entrees, list) or not entrees:
                self.send_json_response(400, {'success': False, 'error': 'aucune entree a importer'})
                return
            horo_max = datetime.now().isoformat(timespec='seconds')
            poses, ignores, refuses, sans_fr = [], [], [], []
            nb_langues = [0]
            with self.SUIVI_LOCK:
                tout = self._suivi_lire()
                for e in entrees:
                    if not isinstance(e, dict):
                        continue
                    iid = str(e.get('itineraire') or '').strip()
                    date = str(e.get('date') or '').strip()
                    if not iid or not date:
                        continue
                    # Une date de fichier dans le futur (horloge decalee,
                    # fichier copie d une autre machine) rendrait toutes les
                    # langues eternellement a jour. On la ramene a maintenant.
                    if date > horo_max:
                        date = horo_max
                    fiche = tout.get(iid) or {'fr_valide': '', 'langues': {}}
                    if not isinstance(fiche.get('langues'), dict):
                        fiche['langues'] = {}
                    # REGLE : un import ne touche JAMAIS a une fiche deja
                    # renseignee. Une date posee a la main, ou par une
                    # reinjection, est une CONSTATATION. Une date importee est
                    # une presomption datee par la date d un fichier. Une
                    # presomption n ecrase pas une constatation, ni dans un
                    # sens ni dans l autre.
                    #
                    # Concretement : tu corriges un francais a 10h44, tu
                    # enregistres verifications-trad.json a 12h12. Sans cette
                    # regle, l import avancerait le francais a 12h12 et
                    # declarerait ses langues relues apres lui : elles
                    # sauteraient l audit alors qu elles sont perimees.
                    if fiche.get('fr_valide'):
                        refuses.append(iid)
                        tout[iid] = fiche
                        continue

                    if not e.get('fr'):
                        # Rien n affirme que le francais a ete relu. On note
                        # les langues pour memoire, mais sans date de
                        # francais rien ne sera declare perime de toute facon.
                        sans_fr.append(iid)
                    else:
                        fiche['fr_valide'] = date
                        fiche['origine'] = str(e.get('origine') or 'import')
                        poses.append(iid)

                    # Langues DEJA RELUES. Le journal de traduction ne le sait
                    # pas et n en envoie pas ; verifications-trad.json le sait.
                    # Une langue relue dans la meme campagne que le francais
                    # n a pas a repartir a l audit.
                    langues = e.get('langues')
                    if isinstance(langues, list):
                        for lg in langues:
                            lg = str(lg or '').strip().lower()
                            if not lg or lg == 'fr':
                                continue
                            if (fiche['langues'].get(lg) or '') < date:
                                fiche['langues'][lg] = date
                                nb_langues[0] += 1
                    tout[iid] = fiche
                dossier = os.path.dirname(self.SUIVI_FICHIER)
                if dossier and not os.path.isdir(dossier):
                    os.makedirs(dossier)
                ecrire_json_atomique(self.SUIVI_FICHIER,
                                     {'maj': datetime.now().isoformat(timespec='seconds'),
                                      'itineraires': tout})
            print('[suivi] import : %d FR pose(s), %d remplacee(s), %d conservee(s), '
                  '%d date(s) de langue, %d sans FR'
                  % (len(poses), len(ignores), len(refuses), nb_langues[0], len(sans_fr)), flush=True)
            self.send_json_response(200, {'success': True, 'poses': len(poses),
                                          'remplacees': len(ignores), 'conservees': len(refuses),
                                          'langues': nb_langues[0], 'sans_fr': len(sans_fr),
                                          'itineraires': tout})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── Verification des accents ──────────────────────────────────────────
    #
    # Un modele qui recoit une consigne ecrite sans accents finit par imiter
    # la consigne, malgre l avertissement. Le degat est massif et silencieux :
    # le texte reste lisible, la structure est intacte, rien ne signale que le
    # portugais a perdu ses cedilles. Le seul controle fiable est mecanique et
    # retrospectif : comparer chaque fichier a son plus ancien backup et
    # compter les signes diacritiques.

    @staticmethod
    def _compte_accents(valeur, acc):
        """Additionne les signes diacritiques de toutes les chaines d une structure."""
        if isinstance(valeur, str):
            d = unicodedata.normalize('NFD', valeur)
            acc[0] += sum(1 for c in d if unicodedata.combining(c))
            acc[1] += len(valeur)
        elif isinstance(valeur, dict):
            for v in valeur.values():
                ORTRequestHandler._compte_accents(v, acc)
        elif isinstance(valeur, list):
            for v in valeur:
                ORTRequestHandler._compte_accents(v, acc)

    # Formes DESACCENTUEES de mots courants. Chacune est choisie pour ne pas
    # exister telle quelle dans la langue : "regiao" n est pas un mot
    # portugais, c est "regiao" ampute de son tilde. Les mots ambigus sont
    # volontairement absents ("mas" existe en espagnol a cote de "mas",
    # "schon" existe en allemand a cote de "schoen").
    # Formes DESACCENTUEES de mots courants. CHAQUE ENTREE DOIT ETRE UN MOT
    # QUI N EXISTE PAS DANS LA LANGUE. Une premiere version de cette liste
    # contenait "montanha" (portugais correct), "historia" et "antiguo"
    # (espagnol corrects), "meta" (italien correct), "cote" (francais
    # correct), "schonen" et "flusse" (allemands corrects) : elle a lever
    # 1952 alertes sur 5187 itineraires, presque toutes fausses.
    # Avant d ajouter un mot ici, verifier qu il est REELLEMENT impossible
    # dans la langue, pas seulement qu il ressemble a une version amputee.
    # Formes DESACCENTUEES de mots courants. Chaque entree a ete VALIDEE
    # contre les fichiers reels du projet : un mot dont les occurrences
    # apparaissent dans des textes par ailleurs bien accentues est un mot
    # legitime, pas une forme amputee, et il est retire. Cette validation a
    # elimine "antigo" (505 occurrences portugaises correctes), "perche",
    # "stadte", "dorfer", "hugel", "martedi", apres une premiere version qui
    # levait des milliers de fausses alertes.
    # Pour ajouter un mot : verifier d abord qu il n apparait PAS dans des
    # blocs correctement accentues.
        # Formes DESACCENTUEES, chacune VALIDEE contre les fichiers reels : un
    # mot qui apparait dans un bloc correctement accentue est un mot
    # legitime et il est ecarte. Ce controle a rejete "esta" (present dans
    # 360 blocs portugais corrects), "franca", "media", "faca", "piu" et
    # "martedi". Sans lui, la premiere version levait 1952 fausses alertes.
    # Les ajouts viennent des reparations reelles, via mots-manquants.json.
    MOTS_SANS_ACCENT = {
        'fr': [
               'etape', 'riviere', 'eglise', 'chateau', 'foret', 'apres',
               'tres', 'deja', 'journee', 'matinee', 'soiree', 'arrivee',
               'entree', 'musee', 'vallee', 'plutot', 'hotel', 'theatre',
               'siecle', 'premiere', 'derniere', 'traversee', 'montee',
               'degustation', 'itineraire', 'randonnee'],
        'es': [
               'aereo', 'asi', 'automovil', 'basilica', 'despues', 'dificil',
               'duracion', 'estacion', 'facil', 'informacion', 'kilometro',
               'panoramico', 'pequena', 'proxima', 'proximo', 'rapido',
               'region', 'situacion', 'tambien', 'turistico', 'ultima',
               'ultimo'],
        'it': [
               'antichita', 'attivita', 'chatre', 'citta', 'cosi',
               'curiosita', 'diversita', 'eglises', 'gia', 'liberta',
               'lunedi', 'martedi', 'novita', 'piu', 'possibilita', 'puo',
               'qualita', 'realta', 'specialita', 'universita', 'venerdi'],
        'pt': [
               'acessivel', 'almoco', 'apos', 'arqueologico', 'artesaos',
               'ate', 'atencao', 'atras', 'atraves', 'automovel', 'baia',
               'basilica', 'batisterio', 'cafes', 'camara', 'campanario',
               'caracteristica', 'cemiterio', 'cenario', 'centenarios',
               'chambery', 'chateau', 'classica', 'colecao', 'colecoes',
               'compoem', 'construcao', 'construida', 'construidas',
               'construido', 'coracao', 'cotes', 'cupulas', 'desca',
               'desnivel', 'destrocos', 'dificil', 'duracao', 'edificio',
               'egipcia', 'egipcio', 'epoca', 'escavacoes', 'especies',
               'espetaculo', 'estacao', 'estacoes', 'estao', 'estatuas',
               'esterel', 'excursoes', 'expoe', 'expoem', 'exposicoes',
               'facil', 'falesia', 'falesias', 'faviere', 'fortificacoes',
               'francois', 'fundacao', 'gotica', 'gotico', 'grao',
               'habitacoes', 'historia', 'historico', 'hyeres', 'informacao',
               'macico', 'manha', 'mediterraneo', 'mediterranico', 'memoria',
               'nao', 'nivel', 'notavel', 'onibus', 'orgao', 'orientacao',
               'ostas', 'panoramica', 'patrimonio', 'periodo', 'piramides',
               'possiveis', 'possivel', 'praca', 'pre', 'propoem',
               'provenca', 'provencal', 'proxima', 'proximo', 'publico',
               'quilometro', 'quilometros', 'rapido', 'reconstruida',
               'regiao', 'relogio', 'residencia', 'reune', 'romanica',
               'romanico', 'saida', 'sao', 'seculo', 'seculos', 'servico',
               'sitio', 'situacao', 'sultao', 'templarios', 'temporarias',
               'terca', 'tercas', 'terracos', 'tradicao', 'tres', 'tumulos',
               'turistico', 'ultima', 'ultimo', 'unico', 'varias', 'varios',
               'verao', 'vestigios', 'vitivinicolas', 'voce'],
        'de': [
               'beruhmt', 'fur', 'gebaude', 'grosste', 'konnen', 'moglich',
               'mussen', 'nachsten', 'nachster', 'naturlich', 'ostlich',
               'schonste', 'spater', 'sudlich', 'uberall', 'zuruck'],
        'nl': [
               'abbaye', 'ardeche', 'belgie', 'bourgondie', 'cathedrale',
               'chateau', 'citadelle', 'cite', 'cote', 'eglise', 'epoque',
               'eveques', 'feeenschoorstenen', 'financiele', 'foret',
               'geinstalleerd', 'geisoleerd', 'ideeen', 'ile', 'italie',
               'kopieen', 'materiele', 'musee', 'nimes', 'officiele',
               'provencal', 'reunie', 'rhone', 'riviere', 'ruines',
               'senanque', 'vallee', 'vezelay', 'zeeen'],
    }

    @staticmethod
    def _blocs_de(it):
        """Les blocs d un itineraire, avec leur cle, comme cote navigateur.

        AUCUNE hypothese sur la forme du fichier. Un seul itineraire ou `seo`
        est une chaine au lieu d un dictionnaire, ou un jour qui n en est pas
        un, faisait remonter une erreur jusqu au try global du scan et
        renvoyait une 500 pour les 215 pays d un coup.
        """
        out = []
        if not isinstance(it, dict):
            return out
        for k, n in (('title', 'titre'), ('subtitle', 'sous-titre'), ('notes', 'notes'),
                     ('climate', 'climat')):
            if isinstance(it.get(k), str):
                out.append((n, it[k]))
        # Points forts : traduits, affiches, et jusqu ici hors de tout controle.
        # practical_context n a pas toujours la meme forme : dictionnaire dans
        # la plupart des fichiers, mais aussi absent, ou carrement une chaine
        # de texte dans quelques itineraires. On ne suppose rien.
        pc = it.get('practical_context')
        if isinstance(pc, dict):
            hl = pc.get('highlights')
            if isinstance(hl, list):
                for i, x in enumerate(hl):
                    if isinstance(x, str):
                        out.append(('atout%d' % i, x))
        elif isinstance(pc, str) and pc.strip():
            # Forme degradee : le contexte tient dans un seul texte libre.
            out.append(('pratique', pc))
        seo = it.get('seo')
        if not isinstance(seo, dict):
            seo = {}
        for k, n in (('h1_title', 'seo.h1'), ('intro_paragraph', 'seo.intro'),
                     ('seo_hook', 'seo.accroche')):
            if isinstance(seo.get(k), str):
                out.append((n, seo[k]))
        fl = seo.get('featured_list')
        if isinstance(fl, list):
            for i, x in enumerate(fl):
                if isinstance(x, str):
                    out.append(('seo.point%d' % i, x))
        # Accroches de lieu. Le navigateur les fabrique depuis toujours
        # (seo.tagline.<lieu>), ce cote-ci ne les voyait pas : elles etaient
        # hors du scan des accents comme le climat l etait avant elles.
        tg = seo.get('places_taglines')
        if isinstance(tg, dict):
            for k in sorted(tg.keys()):
                if isinstance(tg[k], str):
                    out.append(('seo.tagline.' + k, tg[k]))
        dp = it.get('days_plan')
        if isinstance(dp, list):
            for i, d in enumerate(dp):
                if not isinstance(d, dict):
                    continue
                vs = d.get('visits')
                if isinstance(vs, list):
                    for j, v in enumerate(vs):
                        if isinstance(v, dict) and isinstance(v.get('text'), str):
                            out.append(('j%d.visite%d' % (i, j), v['text']))
                acts = d.get('activities')
                if isinstance(acts, list):
                    for j, act in enumerate(acts):
                        if isinstance(act, dict) and isinstance(act.get('text'), str):
                            out.append(('j%d.activite%d' % (i, j), act['text']))
        return out

    @staticmethod
    def _ecrire_bloc(it, cle, val):
        """Ecrit un bloc a sa place. Miroir exact de qcEcrireBloc du navigateur.

        Sert au garde-fou : quand un bloc est refuse, on remet a sa place le
        texte d origine relu sur le disque. Renvoie True si l ecriture a eu
        lieu. N invente jamais un emplacement qui n existe pas.
        """
        if not isinstance(it, dict):
            return False
        val = '' if val is None else str(val)
        simples = {'titre': 'title', 'sous-titre': 'subtitle',
                   'notes': 'notes', 'climat': 'climate'}
        if cle in simples:
            it[simples[cle]] = val
            return True
        if cle == 'pratique':
            if not isinstance(it.get('practical_context'), str):
                return False
            it['practical_context'] = val
            return True
        m = re.match(r'^atout(\d+)$', cle)
        if m:
            pc = it.get('practical_context')
            if not isinstance(pc, dict) or not isinstance(pc.get('highlights'), list):
                return False
            i = int(m.group(1))
            if i < 0 or i >= len(pc['highlights']):
                return False
            pc['highlights'][i] = val
            return True
        if cle.startswith('seo.'):
            if not isinstance(it.get('seo'), dict):
                return False
            seo = it['seo']
            if cle == 'seo.h1':
                seo['h1_title'] = val
                return True
            if cle == 'seo.intro':
                seo['intro_paragraph'] = val
                return True
            if cle == 'seo.accroche':
                seo['seo_hook'] = val
                return True
            m = re.match(r'^seo\.point(\d+)$', cle)
            if m:
                fl = seo.get('featured_list')
                if not isinstance(fl, list):
                    return False
                i = int(m.group(1))
                if i < 0 or i >= len(fl):
                    return False
                fl[i] = val
                return True
            m = re.match(r'^seo\.tagline\.(.+)$', cle)
            if m:
                tg = seo.get('places_taglines')
                if not isinstance(tg, dict):
                    return False
                tg[m.group(1)] = val
                return True
            return False
        m = re.match(r'^j(\d+)\.(visite|activite)(\d+)$', cle)
        if m:
            dp = it.get('days_plan')
            if not isinstance(dp, list):
                return False
            i = int(m.group(1))
            if i < 0 or i >= len(dp) or not isinstance(dp[i], dict):
                return False
            arr = dp[i].get('visits' if m.group(2) == 'visite' else 'activities')
            j = int(m.group(3))
            if not isinstance(arr, list) or j < 0 or j >= len(arr):
                return False
            if not isinstance(arr[j], dict):
                return False
            arr[j]['text'] = val
            return True
        return False

    # ── Garde-fou accents, cote SERVEUR ───────────────────────────────────
    #
    # Le controle existait uniquement dans le navigateur, et seulement sur
    # l audit en masse. Quatre autres chemins ecrivaient sans rien verifier :
    # la retraduction en lot, le collage manuel d une reponse d audit,
    # l integration d une traduction venue de input/, et l application d une
    # proposition de rapport. Le serveur, lui, acceptait n importe quoi.
    # Le controle est donc descendu ici : c est le seul point par lequel
    # TOUTES les ecritures passent, quel que soit le bouton d origine.

    @staticmethod
    def _densite_accents(t):
        d = unicodedata.normalize('NFD', t or '')
        return sum(1 for c in d if unicodedata.combining(c))

    @staticmethod
    def _accents_perdus(avant, apres, langue=''):
        """Raison du refus, ou '' si le bloc peut etre ecrit.

        SEUILS. Sur un petit nombre d accents, le rapport ne veut rien dire.
        Un bloc court qui en portait quatre et n en porte plus que deux n a
        rien prouve : il suffit qu une correction legitime ait supprime le
        seul nom propre accentue de la phrase. C est exactement ce qui s est
        passe sur un seo.accroche portugais ou le modele devait retirer
        « les neuf eglises du Vale de Boi », deux des quatre accents du bloc.
        La correction etait bonne, elle a ete refusee.

        Il faut donc une base assez large pour que le calcul ait un sens :
          - moins de 5 accents au depart, on ne juge pas ;
          - a partir de 5, un bloc qui tombe a ZERO est refuse ;
          - la comparaison de densite ne s applique qu a partir de 8, ou un
            effondrement ne peut plus s expliquer par un mot supprime.
        Un vrai bloc desaccentue en portugais, italien ou francais en perd
        vingt d un coup : il reste attrape sans difficulte.

        On compare la DENSITE, pas le nombre brut : une correction peut
        raccourcir un texte, elle perd alors des accents en proportion et un
        comptage brut la refuserait a tort.
        """
        avant = avant if isinstance(avant, str) else ''
        apres = apres if isinstance(apres, str) else ''
        # PREUVE DIRECTE, avant tout calcul de proportion : un mot de la liste
        # validee qui APPARAIT dans le nouveau texte sans etre dans l ancien.
        # Ces formes n existent pas dans la langue, en voir surgir une est une
        # preuve et non un indice. C est indispensable pour l italien et
        # l espagnol, qui portent naturellement peu d accents : sur eux la
        # comparaison de densite ne dit rien, et relever les seuils les
        # laissait sans aucune protection.
        if langue:
            try:
                neufs = [m for m in ORTRequestHandler._mots_du_bloc(apres, langue)
                         if m not in set(ORTRequestHandler._mots_du_bloc(avant, langue))]
            except Exception:
                neufs = []
            if neufs:
                return 'mot(s) prives de leur accent : ' + ', '.join(neufs[:6])
        a = ORTRequestHandler._densite_accents(avant)
        b = ORTRequestHandler._densite_accents(apres)
        la, lb = len(avant), len(apres)
        if la < 40 or a < 5:
            return ''
        if b == 0:
            return 'tous les accents perdus (%d -> 0)' % a
        if a < 8 or lb < 1:
            return ''
        da, db = a / float(la), b / float(lb)
        if db < da * 0.5:
            return 'accents perdus (%d -> %d, densite divisee par %.1f)' % (a, b, da / db)
        return ''

    @staticmethod
    def _ancres(t):
        """Les reperes concrets d un bloc : nombres et noms propres.

        Ce sont eux qui disent DE QUOI parle le bloc. Deux textes qui traitent
        du meme sujet les partagent, meme reformules d un bout a l autre.
        """
        out = set(re.findall(r'\d+', t or ''))
        for m in re.findall(r'\b[A-Z\u00c0-\u00dd][^\W\d_]{2,}', t or '', re.UNICODE):
            out.add(m.lower())
        return out

    @staticmethod
    def _blocs_fr_de(chemin, itin_id):
        """Les blocs FRANCAIS de cet itineraire, lus dans le fichier -fr voisin.

        POURQUOI LE FRANCAIS ET PAS L ANCIENNE TRADUCTION. Une premiere
        version comparait la nouvelle traduction a la precedente. C etait
        faux : quand le francais est corrige, la traduction DOIT changer,
        et une comparaison a l ancienne version aurait refuse tout le
        rattrapage. Cas reel, GR::dodecanese-2 j4.activite1 : le francais
        est passe des bains de Loutra a une promenade dans Mandraki, EN, ES
        et IT avaient deja suivi, seul le portugais retardait. La bonne
        traduction a ete prise pour une invention.

        La seule reference valable est donc le francais du moment.
        """
        chemin = (chemin or '').replace('\\', '/')
        m = re.search(r'^(.*)-([a-z]{2})\.json$', chemin)
        if not m or m.group(2) == 'fr':
            return None
        chemin_fr = m.group(1) + '-fr.json'
        if not os.path.exists(chemin_fr):
            return None
        try:
            with io.open(chemin_fr, 'r', encoding='utf-8') as fh:
                doc = json.load(fh)
        except Exception:
            return None
        for it in (doc.get('itineraries') or []):
            if not isinstance(it, dict):
                continue
            if (it.get('id') or it.get('itin_id')) == itin_id:
                try:
                    return dict(ORTRequestHandler._blocs_de(it))
                except Exception:
                    return None
        return None

    @staticmethod
    def _hors_sujet(fr, neuf):
        """Un bloc qui ne parle pas de la meme chose que le francais.

        Les reperes concrets d un bloc, ses chiffres et ses noms propres,
        traversent les langues sans changer. Une traduction fidele les porte
        tous. Un texte invente n en porte aucun.

        DEUX SIGNAUX EXIGES ENSEMBLE pour ne pas gener une traduction
        legitimement plus courte : la plupart des reperes du francais sont
        absents ET le texte est nettement plus court que le francais.
        """
        fr = fr or ''
        neuf = neuf or ''
        if len(fr) < 120:
            return ''
        a = ORTRequestHandler._ancres(fr)
        if len(a) < 4:
            return ''
        b = ORTRequestHandler._ancres(neuf)
        gardes = a & b
        part = len(gardes) / float(len(a))
        rapport = len(neuf) / float(len(fr))
        if part > 0.4 or rapport > 0.6:
            return ''
        absents = sorted(a - b)[:6]
        return ('ne suit pas le francais : %d repere(s) sur %d absents (%s), '
                'texte a %d%% de la longueur du francais'
                % (len(a) - len(gardes), len(a), ', '.join(absents),
                   int(round(100 * rapport))))

    def _filtrer_accents(self, ancien, nouveau, langue='', blocs_fr=None):
        """Remet le texte d origine dans tout bloc qui a perdu ses accents.

        `nouveau` est modifie sur place. Renvoie la liste des blocs refuses.
        Un bloc absent de l ancienne version n est pas comparable, il passe.
        """
        refuses = []
        if not isinstance(ancien, dict) or not isinstance(nouveau, dict):
            return refuses
        try:
            avant = dict(self._blocs_de(ancien))
            apres = self._blocs_de(nouveau)
        except Exception:
            return refuses
        for cle, txt in apres:
            vieux = avant.get(cle)
            if vieux is None:
                continue
            raison = (self._accents_perdus(vieux, txt, langue)
                      or (self._hors_sujet(blocs_fr.get(cle), txt) if blocs_fr else ''))
            if not raison:
                continue
            if self._ecrire_bloc(nouveau, cle, vieux):
                # On garde les deux textes ENTIERS. Ils etaient coupes a 400
                # caracteres, et comme relacher un bloc reecrit ce champ tel
                # quel dans le fichier pays, chaque bloc relache repartait
                # ampute sur le disque, sans aucun avertissement. Les
                # extraits ne servent qu a l affichage et au journal : ils
                # sont fabriques au moment de montrer, pas au moment de
                # stocker.
                refuses.append({'cle': cle, 'raison': raison,
                                'refuse': (txt or ''),
                                'conserve': (vieux or '')})
        return refuses

    @staticmethod
    def _mots_du_bloc(texte, langue):
        """Formes amputees presentes dans UN bloc.

        Recherche SENSIBLE A LA CASSE, volontairement. "Grand Hotel" est un
        nom d etablissement parfaitement ecrit ; "hotel" en minuscule au
        milieu d une phrase francaise est une faute. Chercher sans tenir
        compte de la casse confondait les deux et signalait des textes sains.
        On perd les mots en debut de phrase, mais un bloc reellement
        desaccentue en contient toujours d autres.
        """
        mots = ORTRequestHandler.MOTS_SANS_ACCENT.get(langue) or []
        out = []
        for m in mots:
            # RECHERCHE STRICTE, y compris en allemand. La recherche en
            # sous-chaine, imaginee pour attraper "Steindoerfern", matchait
            # "Nordlichter", "Schaffhauser", "Greifswalder", "bewahrenden" :
            # des mots parfaitement corrects. Elle produisait beaucoup plus
            # de bruit que de signal et a ete retiree.
            if re.search(r'\b' + re.escape(m) + r'\b', texte):
                out.append(m)
        return out

    # _mots_amputes a ete SUPPRIMEE : elle n etait appelee nulle part.
    # C est _mots_du_bloc qui fait le travail, bloc par bloc. La fonction
    # morte portait pourtant la seule logique ecrite pour les mots composes
    # allemands, ce qui laissait croire a une couverture qui n existait pas.

    # Blocs toujours examines, quelle que soit leur longueur. Le plancher de
    # 60 caracteres ecarte les textes trop courts pour etre juges, mais un
    # titre ou un sous-titre passe presque toujours sous ce plancher : une
    # desaccentuation de titre n etait donc JAMAIS vue par le signal des mots.
    BLOCS_COURTS_EXAMINES = ('titre', 'sous-titre')

    @staticmethod
    def _motifs_accents(itA, itB, langue, a, dens, mediane):
        """Les trois signaux, pour UN itineraire.

        Renvoie (motifs, blocs_casses, trouves, accents_du_backup).
        UN SEUL SIGNAL SUFFIT a lever une alerte. Le commentaire d origine
        annoncait deux signaux concordants, le code n en a jamais exige
        qu un : la liste de mots a ete validee contre les fichiers reels,
        chaque forme retenue n existe pas dans la langue, donc en trouver une
        est une preuve directe et non un indice a confirmer.
        """
        motifs = []
        # 1. comparaison au backup, quand il y en a un
        avant = None
        if itB is not None:
            b = [0, 0]
            ORTRequestHandler._compte_accents(itB, b)
            if b[0] >= 10 and a[0] < b[0] * 0.6:
                motifs.append('perte de %d%% par rapport au backup'
                              % round(100.0 * (b[0] - a[0]) / b[0]))
            avant = b[0]
        # 2. comparaison aux autres itineraires du meme fichier
        if mediane > 0.01 and a[1] > 200 and dens < mediane * 0.35:
            motifs.append('densite %.2f%% contre %.2f%% pour les autres itineraires du fichier'
                          % (dens * 100, mediane * 100))
        # 3. mots visiblement amputes, releves BLOC PAR BLOC. C est la maille
        #    qui compte : une correction ne touche que quelques blocs, et trois
        #    blocs abimes sur cinquante ne deplacent pas la moyenne de
        #    l itineraire. En comptant par itineraire, 138 blocs reellement
        #    casses n en faisaient ressortir que cinq.
        trouves = {}
        blocs_casses = []
        for cle, texte in ORTRequestHandler._blocs_de(itA):
            if len(texte) < 60 and cle not in ORTRequestHandler.BLOCS_COURTS_EXAMINES:
                continue
            mm = ORTRequestHandler._mots_du_bloc(texte, langue)
            if not mm:
                continue
            # On garde l EXTRAIT AUTOUR du mot fautif, pas le debut du bloc :
            # sinon on affiche 160 caracteres qui ne montrent pas le probleme
            # et on ne peut pas juger si l alerte est fondee.
            pos = texte.find(mm[0])
            if pos < 0:
                pos = texte.lower().find(mm[0])
            if pos < 0:
                pos = 0
            d0 = max(0, pos - 70)
            extrait = texte[d0:pos + 110]
            if d0 > 0:
                extrait = '...' + extrait
            blocs_casses.append({'cle': cle, 'mots': mm, 'extrait': extrait})
            for m in mm:
                trouves[m] = trouves.get(m, 0) + 1
        if blocs_casses:
            top = sorted(trouves.items(), key=lambda x: -x[1])[:6]
            motifs.append('%d bloc(s) contiennent des mots sans accent : %s'
                          % (len(blocs_casses),
                             ', '.join('%s x%d' % (m, n) for m, n in top)))
        return motifs, blocs_casses, trouves, avant

    def handle_verifier_accents(self, qs):
        """Compare chaque fichier de langue a son plus ancien backup.

        Renvoie, itineraire par itineraire, le nombre de signes diacritiques
        avant et apres. Une chute franche signe une desaccentuation.
        """
        try:
            cc = (qs.get('cc', [''])[0] or '').strip().upper()
            # Filtre par langue. Sans lui, verifier une seule langue obligeait
            # a relire les huit fichiers de chaque pays.
            seule = (qs.get('lang', [''])[0] or '').strip().lower()
            base = os.path.join('data', 'Roadtripsprefabriques', 'countries')
            pays = [cc] if cc else sorted(
                d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
            alertes, examines, ignores = [], 0, 0
            for p in pays:
                dossier = os.path.join(base, p)
                if not os.path.isdir(dossier):
                    continue
                # UN SEUL listdir par dossier. Avant, le dossier etait relu en
                # entier pour chercher les backups de chaque fichier, soit huit
                # fois par pays sur des dossiers qui grossissent a chaque audit.
                contenu = sorted(os.listdir(dossier))
                for nom in contenu:
                    m = re.match(r'^(.+)\.itins\.modules-([a-z]{2})\.json$', nom)
                    if not m:
                        continue
                    langue = m.group(2)
                    if seule and langue != seule:
                        continue
                    chemin = os.path.join(dossier, nom)
                    # le plus ancien backup disponible fait foi comme reference
                    # Le backup n est plus obligatoire : sans lui on garde les
                    # deux autres signaux. Un fichier jamais sauvegarde, ou dont
                    # le plus vieux backup est deja abime, restait invisible.
                    backups = [x for x in contenu if x.startswith(nom + '.backup_')]
                    anc = {}
                    try:
                        with io.open(chemin, 'r', encoding='utf-8') as fh:
                            act = json.load(fh)
                        if backups:
                            with io.open(os.path.join(dossier, backups[0]), 'r', encoding='utf-8') as fh:
                                anc = json.load(fh)
                    except Exception:
                        continue
                    # Ne garder que des dictionnaires. Un element qui n en est
                    # pas un plantait tout le reste du parcours.
                    par_id_act = {(x.get('id') or x.get('itin_id')): x
                                  for x in (act.get('itineraries') or [])
                                  if isinstance(x, dict)}
                    par_id_anc = {(x.get('id') or x.get('itin_id')): x
                                  for x in (anc.get('itineraries') or [])
                                  if isinstance(x, dict)}

                    # Densite d accents de chaque itineraire du fichier. Elle
                    # sert de reference INTERNE : dans un meme fichier
                    # portugais, tous les itineraires doivent se ressembler.
                    # Celui qui tombe a zero quand les autres sont a 4 % est
                    # casse, et on le sait sans avoir besoin d un backup.
                    densites = []
                    for x in par_id_act.values():
                        c = [0, 0]
                        self._compte_accents(x, c)
                        if c[1] > 200:
                            densites.append(c[0] / float(c[1]))
                    mediane = 0.0
                    if densites:
                        d = sorted(densites)
                        mediane = d[len(d) // 2]

                    for iid, itA in par_id_act.items():
                        if not iid:
                            continue
                        examines += 1
                        # REPRISE PAR ITINERAIRE. Avant, la moindre structure
                        # inhabituelle remontait jusqu au try global et rendait
                        # une erreur 500 pour les 215 pays d un seul coup. Un
                        # itineraire illisible est maintenant compte a part et
                        # le scan continue.
                        try:
                            a = [0, 0]
                            self._compte_accents(itA, a)
                            dens = (a[0] / float(a[1])) if a[1] else 0.0
                            motifs = self._motifs_accents(
                                itA, par_id_anc.get(iid), langue, a, dens, mediane)
                        except Exception as err_it:
                            ignores += 1
                            print('[accents] %s / %s ignore : %s' % (nom, iid, err_it),
                                  flush=True)
                            continue
                        motifs, blocs_casses, trouves, avant = motifs
                        if not motifs:
                            continue
                        alertes.append({
                            'pays': p, 'langue': langue, 'itineraire': iid,
                            'signaux': len(motifs),
                            'blocs': [b['cle'] for b in blocs_casses],
                            'nb_blocs': len(blocs_casses),
                            # Le detail COMPLET, pas seulement trois exemples :
                            # c est ce qui permet de verifier une alerte a un
                            # seul bloc, la plus susceptible d etre fausse.
                            'detail': blocs_casses[:40],
                            'exemples': blocs_casses[:3],
                            'fichier': chemin.replace('\\', '/'),
                            'accents_avant': avant, 'accents_apres': a[0],
                            'perte_pct': (round(100.0 * (avant - a[0]) / avant, 1)
                                          if avant else None),
                            'densite_pct': round(dens * 100, 2),
                            'densite_fichier_pct': round(mediane * 100, 2),
                            'motifs': motifs,
                            'backup': backups[0] if backups else '',
                            'backups_dispo': len(backups),
                        })
            alertes.sort(key=lambda x: -x.get('nb_blocs', 0))
            nb_blocs = sum(x.get('nb_blocs', 0) for x in alertes)
            print('[accents] %d itineraire(s) examine(s), %d alerte(s), %d bloc(s) a reecrire'
                  ', %d ignore(s)' % (examines, len(alertes), nb_blocs, ignores), flush=True)
            self.send_json_response(200, {'success': True, 'examines': examines,
                                          'ignores': ignores,
                                          'blocs_casses': nb_blocs, 'alertes': alertes})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── Apprentissage : les mots que la detection a rates ─────────────────
    #
    # Chaque bloc repare que la liste n avait PAS repere contient forcement
    # une forme desaccentuee inconnue d elle. On l extrait en comparant
    # l avant et l apres : ce sont les mots qui ont gagne un accent. Ces
    # formes s accumulent ici avec un compteur, et deviennent des candidats
    # a l entree dans la liste de detection.
    MOTS_APPRIS_FICHIER = os.path.join('data', 'traductions-itineraires', 'mots-manquants.json')
    MOTS_APPRIS_LOCK = threading.Lock()

    def _mots_appris_lire(self):
        try:
            if os.path.isfile(self.MOTS_APPRIS_FICHIER):
                with io.open(self.MOTS_APPRIS_FICHIER, 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                    if isinstance(d, dict):
                        return d.get('langues') or {}
        except Exception as e:
            print('[mots] lecture impossible: %r' % (e,))
        return {}

    def handle_mots_repares_get(self):
        appris = self._mots_appris_lire()
        connus = {l: sorted(v) for l, v in self.MOTS_SANS_ACCENT.items()}
        # Un candidat n entre pas tout seul dans la liste : il faut qu il soit
        # apparu plusieurs fois. C est ce garde-fou qui manquait quand la
        # premiere version a lance des milliers de fausses alertes.
        prets = {}
        for l, mots in appris.items():
            p = [m for m, n in mots.items()
                 if n >= 3 and m not in (self.MOTS_SANS_ACCENT.get(l) or [])]
            if p:
                prets[l] = sorted(p, key=lambda m: -mots[m])
        self.send_json_response(200, {'success': True, 'langues': appris,
                                      'prets': prets, 'connus': connus})

    @staticmethod
    def _mots_gagnants(avant, apres):
        """Mots qui ont gagne un accent entre les deux versions.

        On aligne mot a mot sur les squelettes, qui sont identiques puisque
        seuls les accents changent. La forme AVANT est celle qui manquait a
        la detection.
        """
        def nu(t):
            return ''.join(c for c in unicodedata.normalize('NFD', t)
                           if not unicodedata.combining(c))
        ma = re.findall(r"[^\W\d_]{3,}", avant, re.UNICODE)
        mb = re.findall(r"[^\W\d_]{3,}", apres, re.UNICODE)
        if len(ma) != len(mb):
            return []
        out = []
        for x, y in zip(ma, mb):
            if nu(x).lower() != nu(y).lower():
                continue                      # mots differents, on ne conclut pas
            if x == y:
                continue                      # inchange
            if nu(y) != y and nu(x) == x:     # y a gagne un accent, x n en avait pas
                out.append(x.lower())
        return out

    def handle_mots_repares(self):
        """Enregistre les formes rattrapees lors d une reaccentuation."""
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(longueur).decode('utf-8')) if longueur > 0 else {}
            langue = str(data.get('langue') or '').strip().lower()
            paires = data.get('paires')
            if not langue or not isinstance(paires, list):
                self.send_json_response(400, {'success': False, 'error': 'langue ou paires manquantes'})
                return
            nouveaux = {}
            for p in paires:
                if not isinstance(p, dict):
                    continue
                av, ap = str(p.get('avant') or ''), str(p.get('apres') or '')
                if not av or not ap:
                    continue
                for m in self._mots_gagnants(av, ap):
                    nouveaux[m] = nouveaux.get(m, 0) + 1
            if not nouveaux:
                self.send_json_response(200, {'success': True, 'nouveaux': 0, 'mots': {}})
                return
            with self.MOTS_APPRIS_LOCK:
                tout = self._mots_appris_lire()
                cur = tout.get(langue) or {}
                for m, n in nouveaux.items():
                    cur[m] = cur.get(m, 0) + n
                tout[langue] = cur
                dossier = os.path.dirname(self.MOTS_APPRIS_FICHIER)
                if dossier and not os.path.isdir(dossier):
                    os.makedirs(dossier)
                ecrire_json_atomique(self.MOTS_APPRIS_FICHIER,
                                     {'maj': datetime.now().isoformat(timespec='seconds'),
                                      'langues': tout})
            connus = set(self.MOTS_SANS_ACCENT.get(langue) or [])
            inedits = sorted(m for m in nouveaux if m not in connus)
            print('[mots] %s : %d forme(s) rattrapee(s), %d inedite(s) : %s'
                  % (langue, len(nouveaux), len(inedits), ', '.join(inedits[:8])), flush=True)
            self.send_json_response(200, {'success': True, 'nouveaux': len(nouveaux),
                                          'inedits': inedits, 'mots': nouveaux})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── Rapports de controle ──────────────────────────────────────────────
    CONTROLES_FICHIER = os.path.join('data', 'traductions-itineraires', 'controles.json')
    CONTROLES_LOCK = threading.Lock()

    def _controles_lire(self):
        try:
            if os.path.isfile(self.CONTROLES_FICHIER):
                with io.open(self.CONTROLES_FICHIER, 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                    if isinstance(d, dict) and isinstance(d.get('rapports'), list):
                        return d['rapports']
        except Exception as e:
            print('[controles] lecture impossible: %r' % (e,))
        return []

    def handle_controles_get(self, qs):
        rapports = self._controles_lire()
        etat = (qs.get('etat', [''])[0] or '').strip()
        if etat:
            rapports = [r for r in rapports if str(r.get('etat') or '') == etat]
        self.send_json_response(200, {'success': True, 'rapports': rapports})

    def handle_controle_ajouter(self):
        """Ajoute ou met a jour un rapport de controle.

        Les rapports s empilent : on garde l historique, un meme couple
        itineraire+langue peut etre controle plusieurs fois. Seul le champ
        'etat' bouge quand tu traites une ligne depuis l onglet Rapports.
        """
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(longueur).decode('utf-8')) if longueur > 0 else {}
            with self.CONTROLES_LOCK:
                rapports = self._controles_lire()
                if data.get('maj_id'):
                    trouve = False
                    for r in rapports:
                        if r.get('id') == data['maj_id']:
                            if 'etat' in data:
                                r['etat'] = str(data['etat'])
                            if 'note' in data:
                                r['note'] = str(data['note'])
                            trouve = True
                            break
                    if not trouve:
                        self.send_json_response(404, {'success': False, 'error': 'rapport introuvable'})
                        return
                elif data.get('supprimer_tout'):
                    rapports = []
                else:
                    r = data.get('rapport')
                    if not isinstance(r, dict):
                        self.send_json_response(400, {'success': False, 'error': 'rapport manquant'})
                        return
                    r.setdefault('id', datetime.now().strftime('%Y%m%d%H%M%S%f'))
                    r.setdefault('date', datetime.now().isoformat(timespec='seconds'))
                    r.setdefault('etat', 'nouveau')
                    rapports.append(r)
                    rapports = rapports[-500:]      # on ne garde pas l historique a l infini
                dossier = os.path.dirname(self.CONTROLES_FICHIER)
                if dossier and not os.path.isdir(dossier):
                    os.makedirs(dossier)
                ecrire_json_atomique(self.CONTROLES_FICHIER,
                                     {'maj': datetime.now().isoformat(timespec='seconds'),
                                      'rapports': rapports})
            self.send_json_response(200, {'success': True, 'rapports': rapports})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── Le spool : les reponses du modele non encore appliquees ───────────
    #
    # La reponse brute etait deja ecrite sur le disque, mais sous un nom qui
    # ne disait ni l itineraire ni la langue, et rien ne notait si elle avait
    # fini par etre ecrite dans le fichier pays. Une passe qui echouait apres
    # coup, ecriture refusee, onglet ferme, reponse illisible, laissait donc
    # un travail entierement paye et introuvable. Ce registre garde chaque
    # reponse jusqu a ce qu elle soit appliquee pour de bon.

    SPOOL_FICHIER = os.path.join('data', 'traductions-itineraires', 'audits-claude', 'registre.json')
    SPOOL_LOCK = threading.Lock()

    @classmethod
    def _spool_lire(cls):
        try:
            with io.open(cls.SPOOL_FICHIER, 'r', encoding='utf-8') as fh:
                d = json.load(fh)
            e = d.get('entrees')
            return e if isinstance(e, list) else []
        except Exception:
            return []

    @classmethod
    def _spool_ecrire(cls, entrees):
        dossier = os.path.dirname(cls.SPOOL_FICHIER)
        if dossier and not os.path.isdir(dossier):
            os.makedirs(dossier)
        ecrire_json_atomique(cls.SPOOL_FICHIER,
                             {'maj': datetime.now().isoformat(timespec='seconds'),
                              'entrees': entrees})

    @classmethod
    def _spool_ajouter(cls, horo, ref, nomf, sortie):
        parts = str(ref).split('|')
        with cls.SPOOL_LOCK:
            e = cls._spool_lire()
            # Une reference renvoyee une seconde fois remplace la precedente :
            # c est la derniere reponse qui vaut, pas l historique.
            e = [x for x in e if not (x.get('ref') == ref and x.get('etat') == 'en_attente')]
            e.append({'id': horo, 'ref': ref,
                      'itineraire': parts[0] if parts else '',
                      'langue': parts[1] if len(parts) > 1 else '',
                      'date': datetime.now().isoformat(timespec='seconds'),
                      'fichier': nomf, 'taille': len(sortie or ''),
                      'etat': 'en_attente'})
            cls._spool_ecrire(e[-600:])

    def handle_spool_get(self):
        e = [x for x in self._spool_lire() if x.get('etat') == 'en_attente']
        self.send_json_response(200, {'success': True, 'entrees': e})

    def handle_spool_action(self):
        """Marquer appliquee, oublier, ou RELIRE une reponse gardee.

        Body : { "action": "applique" | "oublier" | "relire" | "vider", "ids": [...] }

        « relire » ne rappelle pas le modele : elle relit le texte garde sur
        le disque et renvoie la meme lecture normalisee que lors de la passe
        d origine. C est ce qui permet de rejouer une passe ratee sans
        repayer une seconde d audit.
        """
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(longueur).decode('utf-8')) if longueur > 0 else {}
            action = str(data.get('action') or '')
            ids = data.get('ids')
            ids = [str(x) for x in ids] if isinstance(ids, list) else []

            if action == 'vider':
                with self.SPOOL_LOCK:
                    self._spool_ecrire([])
                self.send_json_response(200, {'success': True, 'entrees': []})
                return

            if action == 'relire':
                if len(ids) != 1:
                    self.send_json_response(400, {'success': False, 'error': 'un seul id attendu'})
                    return
                cible = None
                for x in self._spool_lire():
                    if x.get('id') == ids[0]:
                        cible = x
                        break
                if cible is None:
                    self.send_json_response(404, {'success': False, 'error': 'entree introuvable'})
                    return
                nomf = os.path.basename(cible.get('fichier') or '')
                chemin = os.path.join(os.path.dirname(self.SPOOL_FICHIER), nomf)
                if not nomf or not os.path.isfile(chemin):
                    self.send_json_response(404, {'success': False,
                                                  'error': 'reponse absente du disque'})
                    return
                with io.open(chemin, 'r', encoding='utf-8') as fh:
                    sortie = fh.read()
                lecture = audit_lire_reponse(sortie,
                                             cles=data.get('cles') or None,
                                             langues=data.get('langues') or None,
                                             racine=os.getcwd())
                self.send_json_response(200, {'success': True, 'texte': sortie,
                                              'lecture': lecture, 'entree': cible})
                return

            if action not in ('applique', 'oublier') or not ids:
                self.send_json_response(400, {'success': False, 'error': 'action ou ids manquants'})
                return
            with self.SPOOL_LOCK:
                e = self._spool_lire()
                for x in e:
                    if x.get('id') in ids:
                        x['etat'] = 'applique' if action == 'applique' else 'oublie'
                restants = [x for x in e if x.get('etat') == 'en_attente']
                self._spool_ecrire(restants)
            self.send_json_response(200, {'success': True, 'entrees': restants})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    # ── La prison : les blocs refuses par le garde-fou ────────────────────
    #
    # Un bloc refuse etait perdu. On ne pouvait ni juger si le refus etait
    # fonde, ni recuperer le texte quand il l etait pas. Il est maintenant
    # garde sur le disque avec les deux versions, relisible depuis l onglet
    # Rapports, et relachable un par un.

    PRISON_FICHIER = os.path.join('data', 'traductions-itineraires', 'accents-refuses.json')
    PRISON_LOCK = threading.Lock()

    @classmethod
    def _prison_lire(cls):
        try:
            with io.open(cls.PRISON_FICHIER, 'r', encoding='utf-8') as fh:
                d = json.load(fh)
            b = d.get('blocs')
            return b if isinstance(b, list) else []
        except Exception:
            return []

    @classmethod
    def _prison_ecrire(cls, blocs):
        dossier = os.path.dirname(cls.PRISON_FICHIER)
        if dossier and not os.path.isdir(dossier):
            os.makedirs(dossier)
        ecrire_json_atomique(cls.PRISON_FICHIER,
                             {'maj': datetime.now().isoformat(timespec='seconds'),
                              'blocs': blocs})

    @classmethod
    def _prison_ajouter(cls, chemin, itin_id, refuses):
        """Enferme les blocs refuses. Un meme bloc refuse deux fois n entre
        qu une fois : c est le dernier etat qui compte."""
        m = re.search(r'-([a-z]{2})\.json$', (chemin or '').replace('\\', '/'))
        langue = m.group(1) if m else ''
        with cls.PRISON_LOCK:
            blocs = cls._prison_lire()
            for r in refuses:
                sig = '%s|%s|%s' % (itin_id, langue, r['cle'])
                blocs = [b for b in blocs if b.get('sig') != sig]
                blocs.append({
                    'id': datetime.now().strftime('%Y%m%d%H%M%S%f'),
                    'sig': sig,
                    'date': datetime.now().isoformat(timespec='seconds'),
                    'fichier': (chemin or '').replace('\\', '/'),
                    'itineraire': itin_id, 'langue': langue,
                    'cle': r['cle'], 'raison': r['raison'],
                    'conserve': r.get('conserve', ''),
                    'refuse': r.get('refuse', ''),
                    'etat': 'en_attente',
                })
            blocs = blocs[-800:]
            cls._prison_ecrire(blocs)

    JOURNAL_FICHIER = os.path.join('data', 'traductions-itineraires', 'journal-blocs.json')
    JOURNAL_LOCK = threading.Lock()

    @classmethod
    def _journal_blocs(cls, chemin, itin_id, langue, ancien, nouveau):
        """Note les blocs modifies par un enregistrement.

        Textes ENTIERS des deux cotes, jamais coupes : c est la seule trace
        de ce qui a change, et une trace amputee ne prouve rien.
        """
        avant = dict(cls._blocs_de(ancien))
        apres = cls._blocs_de(nouveau)
        lignes = []
        quand = datetime.now().isoformat(timespec='seconds')
        for cle, txt in apres:
            vieux = avant.get(cle)
            if vieux == txt:
                continue
            lignes.append({'date': quand, 'fichier': (chemin or '').replace('\\', '/'),
                           'itineraire': itin_id, 'langue': langue, 'cle': cle,
                           'avant': vieux, 'apres': txt,
                           'etat': 'ajoute' if vieux is None else 'modifie'})
        if not lignes:
            return
        with cls.JOURNAL_LOCK:
            try:
                with io.open(cls.JOURNAL_FICHIER, 'r', encoding='utf-8') as fh:
                    d = json.load(fh)
                vieux_j = d.get('blocs') if isinstance(d, dict) else None
                if not isinstance(vieux_j, list):
                    vieux_j = []
            except Exception:
                vieux_j = []
            dossier = os.path.dirname(cls.JOURNAL_FICHIER)
            if dossier and not os.path.isdir(dossier):
                os.makedirs(dossier)
            ecrire_json_atomique(cls.JOURNAL_FICHIER,
                                 {'maj': quand, 'blocs': (vieux_j + lignes)[-3000:]})
        print('[JOURNAL] %s / %s / %s : %d bloc(s) modifie(s)'
              % (itin_id, langue.upper(), os.path.basename(chemin or ''), len(lignes)),
              flush=True)

    def handle_prison_get(self):
        """Les blocs en attente, avec un drapeau sur les anciens tronques.

        Les blocs enfermes avant le 31/08/2026 ne portent que les 400
        premiers caracteres du texte refuse : le reste n a jamais ete
        ecrit nulle part, il est perdu. On ne peut pas les reparer, on peut
        seulement les marquer pour qu ils ne soient pas relaches.
        """
        blocs = []
        for b in self._prison_lire():
            b = dict(b)
            if len(b.get('refuse') or '') == 400 or len(b.get('conserve') or '') == 400:
                b['tronque'] = True
                b['raison'] = (b.get('raison') or '') + \
                    ' [BLOC TRONQUE A 400 CARACTERES, texte complet perdu : a ecarter]'
            blocs.append(b)
        self.send_json_response(200, {'success': True, 'blocs': blocs})

    def handle_prison_action(self):
        """Relacher ou ecarter des blocs refuses.

        Body : { "action": "liberer" | "ecarter" | "vider", "ids": [...] }

        Relacher ecrit le texte refuse dans le fichier pays, EN CONTOURNANT
        le garde-fou. C est le seul endroit du programme qui a ce droit, et
        il ne s exerce que sur un bloc que tu as regarde et valide toi meme.
        """
        try:
            longueur = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(longueur).decode('utf-8')) if longueur > 0 else {}
            action = str(data.get('action') or '')
            ids = data.get('ids')
            ids = [str(x) for x in ids] if isinstance(ids, list) else []

            if action == 'vider':
                with self.PRISON_LOCK:
                    self._prison_ecrire([])
                self.send_json_response(200, {'success': True, 'blocs': []})
                return
            if action not in ('liberer', 'ecarter') or not ids:
                self.send_json_response(400, {'success': False, 'error': 'action ou ids manquants'})
                return

            blocs = self._prison_lire()
            vises = [b for b in blocs if b.get('id') in ids]
            if not vises:
                self.send_json_response(404, {'success': False, 'error': 'aucun bloc trouve'})
                return

            # Un avis d arbitrage peut porter une REECRITURE : c est le cas le
            # plus frequent, la version refusee est bonne sur le fond et il ne
            # lui manque que ses accents. On ecrit alors ce texte-la.
            textes = data.get('textes')
            textes = textes if isinstance(textes, dict) else {}

            faits, erreurs = [], []
            if action == 'liberer':
                for b in vises:
                    try:
                        # Bloc d avant la correction du 31/08/2026 : son texte
                        # n a ete garde qu a 400 caracteres. L ecrire amputerait
                        # le fichier pays. Une reecriture ne sauve rien non plus,
                        # elle est faite sur la meme vue tronquee.
                        if len(b.get('refuse') or '') == 400:
                            raise ValueError(
                                'bloc tronque a 400 caracteres, texte complet perdu. '
                                'Ecarte-le et refais passer la correction.')
                        t = textes.get(b['id'])
                        if isinstance(t, str) and t.strip():
                            b = dict(b)
                            b['refuse'] = t
                        self._liberer_un(b)
                        faits.append(b['id'])
                    except Exception as e:
                        erreurs.append('%s / %s : %s' % (b.get('itineraire'), b.get('cle'), e))
            else:
                faits = [b['id'] for b in vises]

            with self.PRISON_LOCK:
                blocs = self._prison_lire()
                for b in blocs:
                    if b.get('id') in faits:
                        b['etat'] = 'libere' if action == 'liberer' else 'ecarte'
                restants = [b for b in blocs if b.get('etat') == 'en_attente']
                self._prison_ecrire(restants)

            self.send_json_response(200, {'success': not erreurs, 'traites': len(faits),
                                          'erreurs': erreurs, 'blocs': restants})
        except Exception as e:
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def _liberer_un(self, b):
        """Ecrit le texte refuse a sa place, avec backup et verrou de fichier."""
        chemin = b.get('fichier') or ''
        if not chemin.startswith('data/') or '..' in chemin:
            raise ValueError('chemin refuse')
        chemin = chemin.replace('/', os.sep)
        if not os.path.isfile(chemin):
            raise ValueError('fichier introuvable')
        cle_verrou = os.path.normcase(os.path.normpath(chemin))
        with SAVE_VERROUS_LOCK:
            verrou = SAVE_VERROUS.setdefault(cle_verrou, threading.Lock())
        if not verrou.acquire(timeout=60):
            raise ValueError('fichier occupe')
        try:
            with io.open(chemin, 'r', encoding='utf-8') as fh:
                doc = json.load(fh)
            liste = doc.get('itineraries') if isinstance(doc, dict) else doc
            if not isinstance(liste, list):
                raise ValueError('format de fichier inattendu')
            cible = None
            for x in liste:
                if isinstance(x, dict) and (x.get('id') or x.get('itin_id')) == b.get('itineraire'):
                    cible = x
                    break
            if cible is None:
                raise ValueError('itineraire absent du fichier')
            if not self._ecrire_bloc(cible, b.get('cle'), b.get('refuse')):
                raise ValueError('emplacement introuvable : ' + str(b.get('cle')))
            backup_unique(chemin)
            ecrire_json_atomique(chemin, doc)
            print('[ACCENTS] LIBERE %s / %s / %s' % (chemin, b.get('itineraire'), b.get('cle')),
                  flush=True)
        finally:
            verrou.release()

    def handle_save_itinerary(self):
        """Sauvegarder un itinéraire dans un fichier JSON (format ORT avec itineraries[]).

        VERROU PAR FICHIER. Un fichier pays contient plusieurs itineraires (18
        pour BR-es). Cette fonction lit le fichier, remplace UN itineraire et
        reecrit le tout. Deux enregistrements simultanes sur le meme fichier
        se marchent dessus : le second repart d une lecture faite avant
        l ecriture du premier, et l ecrase. Avec l audit en masse, ce cas
        n est plus theorique. Le verrou serialise les ecritures par fichier ;
        il protege aussi contre plusieurs onglets d admin ouverts en meme temps.
        """
        chemin_demande = ''
        verrou = None
        try:
            longueur_pic = int(self.headers.get('Content-Length', 0))
            corps_brut = self.rfile.read(longueur_pic) if longueur_pic > 0 else b'{}'
            apercu = json.loads(corps_brut.decode('utf-8')) if corps_brut else {}
            chemin_demande = str(apercu.get('path') or '')
        except Exception:
            apercu, corps_brut = {}, b'{}'
        cle_verrou = os.path.normcase(os.path.normpath(chemin_demande)) if chemin_demande else '?'
        with SAVE_VERROUS_LOCK:
            verrou = SAVE_VERROUS.get(cle_verrou)
            if verrou is None:
                verrou = threading.Lock()
                SAVE_VERROUS[cle_verrou] = verrou
        if not verrou.acquire(timeout=120):
            self.send_json_response(503, {'success': False,
                'error': 'Fichier occupe par un autre enregistrement, reessaie.'})
            return
        try:
            self._save_itinerary_corps(apercu)
        finally:
            verrou.release()

    def _save_itinerary_corps(self, data):
        """Corps reel de l enregistrement. Le corps HTTP est deja lu et decode."""
        try:
            file_path = data.get('path')
            itinerary = data.get('data')
            country_code = data.get('country', '').upper()
            
            # Garde-fou : retirer 'country' du corps de l'itinéraire si client buggé l'a injecté
            # (le pays est porté au niveau racine du fichier, pas dans chaque itin)
            if isinstance(itinerary, dict):
                itinerary.pop('country', None)
            
            if not file_path or not itinerary:
                self.send_json_response(400, {'success': False, 'error': 'Missing path or data'})
                return
            
            # Sécurité : vérifier que le chemin est dans data/
            if not file_path.startswith('data/') or '..' in file_path:
                self.send_json_response(403, {'success': False, 'error': 'Invalid path'})
                return
            
            # Recherche insensible à la casse du dossier et fichier
            actual_path = self.find_case_insensitive_path(file_path, country_code)
            if actual_path:
                file_path = actual_path
                print(f"[PATH] Fichier existant trouvé: {file_path}")
            else:
                # Créer le dossier si nécessaire
                dir_path = os.path.dirname(file_path)
                if dir_path and not os.path.exists(dir_path):
                    os.makedirs(dir_path)
                print(f"[PATH] Nouveau fichier sera créé: {file_path}")
            
            # Backup si le fichier existe
            backup_path = None
            existing_data = None
            if os.path.exists(file_path):
                backup_path = backup_unique(file_path)
                print(f"[BACKUP] {file_path} -> {backup_path}")
                
                # Lire le contenu existant
                with open(file_path, 'r', encoding='utf-8') as f:
                    existing_data = json.load(f)
            
            # Déterminer le format et mettre à jour
            itin_id = itinerary.get('id') or itinerary.get('itin_id')
            final_data = None
            updated_index = -1

            # GARDE-FOU ACCENTS. Il tourne ici, sur le seul passage obligatoire
            # de toutes les ecritures, quel que soit le bouton d origine. Un
            # bloc qui perd ses signes diacritiques n est pas ecrit : le texte
            # relu sur le disque est remis a sa place et le refus remonte dans
            # la reponse. Un fichier neuf n a pas de version anterieure, il n y
            # a donc rien a comparer et rien a refuser.
            refuses_accents = []
            if existing_data is not None and isinstance(itinerary, dict):
                ancien_itin = None
                liste_anc = (existing_data.get('itineraries')
                             if isinstance(existing_data, dict) else existing_data)
                if isinstance(liste_anc, list):
                    for x in liste_anc:
                        if isinstance(x, dict) and (x.get('id') or x.get('itin_id')) == itin_id:
                            ancien_itin = x
                            break
                elif isinstance(existing_data, dict):
                    ancien_itin = existing_data
                if ancien_itin is not None:
                    m_lang = re.search(r'-([a-z]{2})\.json$', (file_path or '').replace('\\', '/'))
                    refuses_accents = self._filtrer_accents(
                        ancien_itin, itinerary, m_lang.group(1) if m_lang else '',
                        self._blocs_fr_de(file_path, itin_id))
                    if refuses_accents:
                        print('[ACCENTS] %s / %s : %d bloc(s) REFUSES, texte d origine conserve : %s'
                              % (file_path, itin_id, len(refuses_accents),
                                 ', '.join(r['cle'] for r in refuses_accents[:8])), flush=True)
                        # Les deux versions cote a cote. C est le seul endroit
                        # ou l on peut encore juger si le refus etait fonde.
                        for r in refuses_accents[:5]:
                            print('  [%s] %s' % (r['cle'], r['raison']), flush=True)
                            print('    conserve : %s' % r.get('conserve', '')[:200], flush=True)
                            print('    refuse   : %s' % r.get('refuse', '')[:200], flush=True)
                        try:
                            self._prison_ajouter(file_path, itin_id, refuses_accents)
                        except Exception as e_p:
                            print('[ACCENTS] mise en attente impossible : %s' % e_p, flush=True)
                    # Trace des blocs qui changent VRAIMENT. Le journal d ecran
                    # annonce "integree" sans jamais relire le disque, et
                    # traites/ ne garde que les traductions venues de input :
                    # une correction faite sur un fichier deja en place ne
                    # laissait aucune trace de ce qu elle avait touche. On
                    # compare donc ici, APRES le garde-fou accents, donc sur ce
                    # qui va reellement etre ecrit.
                    try:
                        self._journal_blocs(file_path, itin_id,
                                            m_lang.group(1) if m_lang else '',
                                            ancien_itin, itinerary)
                    except Exception as e_j:
                        print('[JOURNAL] trace impossible : %s' % e_j, flush=True)

            if existing_data is None:
                # Nouveau fichier - créer structure ORT
                country = itinerary.get('country', 'XX')
                final_data = {
                    "version": "v1",
                    "country": country,
                    "itineraries": [itinerary]
                }
                updated_index = 0
                print(f"[SAVE] Nouveau fichier créé avec structure ORT")
                
            elif isinstance(existing_data, dict) and 'itineraries' in existing_data:
                # Format ORT standard : { itineraries: [...] }
                final_data = existing_data
                itins = final_data['itineraries']
                found = False
                
                for i, itin in enumerate(itins):
                    existing_id = itin.get('id') or itin.get('itin_id')
                    if existing_id == itin_id:
                        # Fusionner : garder les champs existants, mettre à jour avec les nouveaux
                        merged = {**itin}
                        # Mettre à jour TOUS les champs fournis (y compris seo, meta, etc.)
                        # 'climate' MANQUAIT dans cette liste. Le paragraphe meteo
                        # est traduit, audite et corrige par l interface, mais la
                        # fusion ne le recopiait pas : le serveur repondait
                        # "reussi" et gardait l ancienne valeur du disque. Toute
                        # correction de climat faite jusqu ici a ete perdue en
                        # silence. Meme chose pour 'best_months', volontairement
                        # hors du circuit d audit mais qui doit rester
                        # enregistrable depuis l editeur.
                        for key in ['title', 'estimated_days_base', 'days_plan', 'pacing_rules',
                                    'seo', 'meta', 'segments', 'variants', 'regions',
                                    'nearby_itins', 'merge_suggestions', 'notes', 'specialties',
                                    'dept_code', 'dept_name', 'source_url', 'created_at',
                                    'subtitle', 'seo_keywords', 'practical_context',
                                    'essential_tips', 'summary', 'climate', 'best_months']:
                            if key in itinerary:
                                merged[key] = itinerary[key]
                        itins[i] = merged
                        found = True
                        updated_index = i
                        print(f"[SAVE] Itinéraire '{itin_id}' mis à jour à l'index {i}")
                        break
                
                if not found:
                    itins.append(itinerary)
                    updated_index = len(itins) - 1
                    print(f"[SAVE] Itinéraire '{itin_id}' ajouté (nouveau)")
                    
            elif isinstance(existing_data, list):
                # Format tableau simple : [...]
                final_data = existing_data
                found = False
                for i, itin in enumerate(final_data):
                    existing_id = itin.get('id') or itin.get('itin_id')
                    if existing_id == itin_id:
                        final_data[i] = {**itin, **itinerary}
                        found = True
                        updated_index = i
                        print(f"[SAVE] Itinéraire '{itin_id}' remplacé à l'index {i}")
                        break
                
                if not found:
                    final_data.append(itinerary)
                    updated_index = len(final_data) - 1
                    print(f"[SAVE] Itinéraire '{itin_id}' ajouté")
            else:
                # Format objet simple
                final_data = {**existing_data, **itinerary}
                print(f"[SAVE] Objet fusionné")
            
            # Corriger le double encodage UTF-8 avant l'écriture
            final_data = fix_encoding_recursive(final_data)
            print(f"[ENCODING] Correction UTF-8 appliquée")
            
            # Écriture ATOMIQUE. Avant, le fichier etait ouvert en 'w' puis
            # rempli progressivement : pendant ces quelques millisecondes, une
            # lecture du navigateur recevait un JSON coupe en deux et plantait.
            # Avec l audit en masse, qui relit chaque fichier juste avant
            # d ecrire, ce cas se produisait pour de vrai. On ecrit donc a
            # cote, puis on remplace d un coup : un lecteur voit soit
            # l ancienne version entiere, soit la nouvelle, jamais un morceau.
            ecrire_json_atomique(file_path, final_data)
            
            steps_count = len(itinerary.get('days_plan', itinerary.get('steps', [])))
            if isinstance(final_data, dict) and 'itineraries' in final_data:
                total_itins = len(final_data['itineraries'])
            elif isinstance(final_data, list):
                total_itins = len(final_data)
            else:
                total_itins = 1
            
            print(f"[SAVE] ✅ {file_path} ({steps_count} jours, {total_itins} itinéraire(s))")
            
            response = {
                'success': True,
                'message': f"Sauvegardé: {itin_id} ({steps_count} jours)",
                'path': file_path,
                'backup': backup_path,
                'steps_count': steps_count,
                'total_itineraries': total_itins,
                'updated_index': updated_index,
                # Blocs ecartes par le garde-fou. L enregistrement reste un
                # succes : tout le reste a bien ete ecrit, seuls ces blocs ont
                # garde leur texte d origine.
                'accents_refuses': refuses_accents
            }
            if refuses_accents:
                response['message'] += (' - %d bloc(s) refuses, accents perdus'
                                        % len(refuses_accents))
            self.send_json_response(200, response)
            
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'Invalid JSON: {str(e)}'})
        except Exception as e:
            print(f"[ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})
    
    # ==================================================================
    # TRADUCTIONS EN ATTENTE : data/traductions-itineraires/input
    # Lecture, comparaison avec la source, reecriture sur place.
    # ==================================================================

    TRAD_INPUT_DIR = os.path.join('data', 'traductions-itineraires', 'input')
    TRAD_OUTPUT_DIR = os.path.join('data', 'traductions-itineraires', 'output')

    def _trad_nom_sur(self, nom):
        """Refuse tout ce qui n'est pas un simple nom de fichier .json."""
        if not nom or not nom.endswith('.json'):
            return None
        if '/' in nom or '\\' in nom or '..' in nom:
            return None
        return nom

    def _trad_itin_de(self, obj):
        """Extrait l'itineraire, quel que soit l'emballage du fichier."""
        if isinstance(obj, list):
            return obj[0] if obj else None
        if isinstance(obj, dict):
            if isinstance(obj.get('itinerary'), dict):
                return obj['itinerary']
            if isinstance(obj.get('itins'), list) and obj['itins']:
                return obj['itins'][0]
        return obj

    def _trad_source(self, nom):
        """Retrouve le JSON francais d'origine dans le prompt de output/."""
        base = nom[:-len('-response.json')] if nom.endswith('-response.json') else nom[:-5]
        for cand in (base + '.json', nom.replace('-response', '')):
            chemin = os.path.join(self.TRAD_OUTPUT_DIR, cand)
            if not os.path.exists(chemin):
                continue
            try:
                with open(chemin, 'r', encoding='utf-8') as f:
                    prompt = json.load(f)
            except Exception:
                continue
            texte = prompt.get('prompt_for_ai') or ''
            i = texte.find('{\n  "itin_id"')
            if i < 0:
                continue
            try:
                return json.loads(texte[i:]), cand
            except Exception:
                continue
        return None, None

    def _trad_backup(self, chemin):
        """Copie de secours a nom garanti unique.

        Deux ecritures dans la meme seconde donnaient le meme nom et la seconde
        ecrasait la premiere : la version d origine etait alors perdue.
        """
        base = f"{chemin}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        dest = base
        n = 1
        while os.path.exists(dest):
            dest = f"{base}-{n}"
            n += 1
        shutil.copy2(chemin, dest)
        return dest

    def handle_trad_input_list(self):
        """Liste les fichiers en attente d'integration."""
        try:
            if not os.path.isdir(self.TRAD_INPUT_DIR):
                self.send_json_response(200, {'success': True, 'dir': self.TRAD_INPUT_DIR, 'files': []})
                return
            out = []
            for nom in sorted(os.listdir(self.TRAD_INPUT_DIR)):
                if not nom.endswith('.json'):
                    continue
                if not os.path.isfile(os.path.join(self.TRAD_INPUT_DIR, nom)):
                    continue
                chemin = os.path.join(self.TRAD_INPUT_DIR, nom)
                itin_id, langue = None, None
                try:
                    with open(chemin, 'r', encoding='utf-8') as f:
                        it = self._trad_itin_de(json.load(f))
                    if isinstance(it, dict):
                        itin_id = it.get('itin_id') or it.get('id')
                        langue = it.get('language')
                except Exception:
                    pass
                src, _ = self._trad_source(nom)
                out.append({
                    'name': nom,
                    'size': os.path.getsize(chemin),
                    'itin_id': itin_id,
                    'lang': langue,
                    'has_source': src is not None
                })
            self.send_json_response(200, {'success': True, 'dir': self.TRAD_INPUT_DIR, 'files': out})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_get(self, query_params):
        """Renvoie une traduction et sa source francaise."""
        try:
            nom = self._trad_nom_sur((query_params.get('f') or [''])[0])
            if not nom:
                self.send_json_response(400, {'success': False, 'error': 'Nom de fichier invalide'})
                return
            chemin = os.path.join(self.TRAD_INPUT_DIR, nom)
            if not os.path.exists(chemin):
                self.send_json_response(404, {'success': False, 'error': 'Fichier introuvable'})
                return
            with open(chemin, 'r', encoding='utf-8') as f:
                brut = json.load(f)
            src, srcfile = self._trad_source(nom)
            self.send_json_response(200, {
                'success': True,
                'name': nom,
                'traduction': self._trad_itin_de(brut),
                'enveloppe': 'liste' if isinstance(brut, list) else (
                    'itinerary' if isinstance(brut, dict) and isinstance(brut.get('itinerary'), dict) else (
                        'itins' if isinstance(brut, dict) and isinstance(brut.get('itins'), list) else 'direct')),
                'source': src,
                'source_file': srcfile
            })
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'JSON illisible: {str(e)}'})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_save(self):
        """Reecrit un fichier de input/ apres edition dans l'admin."""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            nom = self._trad_nom_sur(data.get('name'))
            itin = data.get('data')
            enveloppe = data.get('enveloppe') or 'direct'
            if not nom or not isinstance(itin, dict):
                self.send_json_response(400, {'success': False, 'error': 'Nom ou contenu invalide'})
                return

            chemin = os.path.join(self.TRAD_INPUT_DIR, nom)
            if not os.path.isdir(self.TRAD_INPUT_DIR):
                os.makedirs(self.TRAD_INPUT_DIR)

            if os.path.exists(chemin):
                self._trad_backup(chemin)

            if enveloppe == 'liste':
                final = [itin]
            elif enveloppe == 'itinerary':
                final = {'itinerary': itin}
            elif enveloppe == 'itins':
                final = {'itins': [itin]}
            else:
                final = itin

            with open(chemin, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(final, f, ensure_ascii=False, indent=2)

            print(f"[TRAD] {chemin} reecrit")
            self.send_json_response(200, {'success': True, 'path': chemin})
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'JSON illisible: {str(e)}'})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_backups(self, query_params):
        """Lister les sauvegardes d un fichier, la plus recente en premier."""
        try:
            nom = self._trad_nom_sur((query_params.get('f') or [''])[0])
            if not nom:
                self.send_json_response(400, {'success': False, 'error': 'Nom de fichier invalide'})
                return
            prefixe = nom + '.backup_'
            out = []
            if os.path.isdir(self.TRAD_INPUT_DIR):
                for f in os.listdir(self.TRAD_INPUT_DIR):
                    if f.startswith(prefixe):
                        plein = os.path.join(self.TRAD_INPUT_DIR, f)
                        out.append({
                            'name': f,
                            'horodatage': f[len(prefixe):],
                            'size': os.path.getsize(plein),
                            'mtime': datetime.fromtimestamp(os.path.getmtime(plein)).isoformat(timespec='seconds')
                        })
            out.sort(key=lambda x: x['horodatage'], reverse=True)
            self.send_json_response(200, {'success': True, 'file': nom, 'backups': out})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_restore(self):
        """Remettre en place une sauvegarde.

        Le fichier courant est lui meme sauvegarde avant d etre remplace :
        une restauration reste annulable.
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            nom = self._trad_nom_sur(data.get('name'))
            backup = data.get('backup') or ''
            if not nom:
                self.send_json_response(400, {'success': False, 'error': 'Nom de fichier invalide'})
                return

            prefixe = nom + '.backup_'
            if not backup:
                dispo = sorted([f for f in os.listdir(self.TRAD_INPUT_DIR) if f.startswith(prefixe)], reverse=True)
                if not dispo:
                    self.send_json_response(404, {'success': False, 'error': 'Aucune sauvegarde pour ce fichier'})
                    return
                backup = dispo[0]

            if not backup.startswith(prefixe) or '/' in backup or '\\' in backup or '..' in backup:
                self.send_json_response(403, {'success': False, 'error': 'Sauvegarde invalide'})
                return

            src = os.path.join(self.TRAD_INPUT_DIR, backup)
            dst = os.path.join(self.TRAD_INPUT_DIR, nom)
            if not os.path.exists(src):
                self.send_json_response(404, {'success': False, 'error': 'Sauvegarde introuvable'})
                return

            if os.path.exists(dst):
                self._trad_backup(dst)

            shutil.copy2(src, dst)
            print(f"[TRAD] {nom} restaure depuis {backup}")
            self.send_json_response(200, {'success': True, 'file': nom, 'backup': backup})
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'JSON illisible: {str(e)}'})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    TRAD_VALIDES = os.path.join('data', 'traductions-itineraires', 'valides-input.json')

    def _trad_valides_lire(self):
        try:
            with open(self.TRAD_VALIDES, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d.get('valides', {}) if isinstance(d, dict) else {}
        except Exception:
            return {}

    def handle_trad_input_valides_get(self):
        """Fichiers marques comme relus, pour l affichage de l admin."""
        try:
            self.send_json_response(200, {'success': True, 'valides': self._trad_valides_lire()})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_valides_set(self):
        """Marquer ou demarquer un fichier comme relu.

        Body : { "name": "...", "valide": true|false, "source": "audit"|"manuel" }
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            nom = self._trad_nom_sur(data.get('name'))
            if not nom:
                self.send_json_response(400, {'success': False, 'error': 'Nom de fichier invalide'})
                return

            valides = self._trad_valides_lire()
            if data.get('valide'):
                valides[nom] = {
                    'le': datetime.now().isoformat(timespec='seconds'),
                    'par': data.get('source') or 'manuel'
                }
            else:
                valides.pop(nom, None)

            dossier = os.path.dirname(self.TRAD_VALIDES)
            if dossier and not os.path.exists(dossier):
                os.makedirs(dossier)
            with open(self.TRAD_VALIDES, 'w', encoding='utf-8', newline='\n') as f:
                json.dump({'updated_at': datetime.now().isoformat(timespec='seconds'),
                           'valides': valides}, f, ensure_ascii=False, indent=2)

            self.send_json_response(200, {'success': True, 'valides': valides})
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'JSON illisible: {str(e)}'})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_delete(self):
        """Ecarter une traduction jugee irrecuperable.

        Le fichier n est pas efface : il est deplace dans input/rejete/ avec
        un horodatage, pour pouvoir etre relu ou remis en place plus tard.
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            nom = self._trad_nom_sur(data.get('name'))
            if not nom:
                self.send_json_response(400, {'success': False, 'error': 'Nom de fichier invalide'})
                return

            chemin = os.path.join(self.TRAD_INPUT_DIR, nom)
            if not os.path.exists(chemin):
                self.send_json_response(404, {'success': False, 'error': 'Fichier introuvable'})
                return

            rejete = os.path.join(self.TRAD_INPUT_DIR, 'rejete')
            if not os.path.isdir(rejete):
                os.makedirs(rejete)

            horo = datetime.now().strftime('%Y%m%d_%H%M%S')
            dest = os.path.join(rejete, horo + '_' + nom)
            shutil.move(chemin, dest)

            print(f"[TRAD] {nom} ecarte vers {dest}")
            self.send_json_response(200, {'success': True, 'path': dest})
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'JSON illisible: {str(e)}'})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_trad_input_integre(self):
        """Archiver un fichier de input/ APRES son integration dans le fichier pays.

        Reproduit exactement le rangement de translate-itineraires.mjs --import :
        - input/<nom>            -> traites/<horodatage>_<nom>
        - input/<rapport .md>    -> rapports/
        - output/<prompt .json>  -> supprime
        - output/<prompt .txt>   -> supprime
        Sans ce menage, translate.js retraduirait le prompt reste dans output/
        et un --import ulterieur ecraserait la version relue.
        L ecriture dans le fichier pays n est PAS faite ici : c est
        /api/save-itinerary qui s en charge, avec son backup.
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            data = json.loads(self.rfile.read(content_length).decode('utf-8'))

            nom = self._trad_nom_sur(data.get('name'))
            if not nom:
                self.send_json_response(400, {'success': False, 'error': 'Nom de fichier invalide'})
                return

            chemin = os.path.join(self.TRAD_INPUT_DIR, nom)
            if not os.path.exists(chemin):
                self.send_json_response(404, {'success': False, 'error': 'Fichier introuvable dans input'})
                return

            base_dir = os.path.dirname(self.TRAD_INPUT_DIR)
            traites = os.path.join(base_dir, 'traites')
            rapports = os.path.join(base_dir, 'rapports')
            for d in (traites, rapports):
                if not os.path.isdir(d):
                    os.makedirs(d)

            # Meme horodatage que le --import du .mjs (ISO, ':' et '.' remplaces)
            horo = datetime.now().isoformat()[:19].replace(':', '-').replace('.', '-')
            dest = os.path.join(traites, horo + '_' + nom)
            shutil.move(chemin, dest)

            deplace_rapport = None
            rapport = nom.replace('-response.json', '-rapport.md')
            if rapport == nom:
                rapport = nom[:-len('.json')] + '-rapport.md'
            src_rapport = os.path.join(self.TRAD_INPUT_DIR, rapport)
            if os.path.exists(src_rapport):
                deplace_rapport = os.path.join(rapports, rapport)
                shutil.move(src_rapport, deplace_rapport)

            # Prompts dans output/ : memes candidats que _trad_source
            base = nom[:-len('-response.json')] if nom.endswith('-response.json') else nom[:-5]
            supprimes = []
            for cand in (base + '.json', nom.replace('-response', '')):
                pj = os.path.join(self.TRAD_OUTPUT_DIR, cand)
                if os.path.exists(pj):
                    os.remove(pj)
                    supprimes.append(cand)
                pt = os.path.join(self.TRAD_OUTPUT_DIR, cand[:-len('.json')] + '.txt')
                if os.path.exists(pt):
                    os.remove(pt)
                    supprimes.append(cand[:-len('.json')] + '.txt')

            # Trace "relu" dans valides-input.json, meme si le fichier a quitte input/
            valides = self._trad_valides_lire()
            valides[nom] = {'le': datetime.now().isoformat(timespec='seconds'), 'par': 'revision'}
            dossier = os.path.dirname(self.TRAD_VALIDES)
            if dossier and not os.path.exists(dossier):
                os.makedirs(dossier)
            with open(self.TRAD_VALIDES, 'w', encoding='utf-8', newline='\n') as f:
                json.dump({'updated_at': datetime.now().isoformat(timespec='seconds'),
                           'valides': valides}, f, ensure_ascii=False, indent=2)

            print(f"[TRAD] {nom} integre : archive vers {dest}, prompts supprimes: {supprimes}")
            self.send_json_response(200, {'success': True, 'archive': dest,
                                          'rapport': deplace_rapport, 'prompts_supprimes': supprimes})
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'JSON illisible: {str(e)}'})
        except Exception as e:
            print(f"[TRAD ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_save_verifications(self):
        """Ecrire data/Roadtripsprefabriques/verifications-trad.json.

        Body attendu : { "verifications": { "<itin_id>": ["fr","en"], ... } }
        Ce fichier sert uniquement au marquage "traduction relue" dans l'editeur.
        Les JSON d'itineraires ne sont pas touches.
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            verifications = data.get('verifications')
            if not isinstance(verifications, dict):
                self.send_json_response(400, {'success': False, 'error': 'Missing or invalid "verifications" object'})
                return

            file_path = 'data/Roadtripsprefabriques/verifications-trad.json'

            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)

            # Une seule copie de secours, pas d'historique : ce fichier change souvent.
            if os.path.exists(file_path):
                shutil.copy2(file_path, file_path + '.bak')

            final_data = {
                "updated_at": datetime.now().isoformat(timespec='seconds'),
                "verifications": verifications
            }

            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)

            count = len(verifications)
            print(f"[VERIF] {file_path} ({count} itineraire(s) marque(s))")

            self.send_json_response(200, {'success': True, 'path': file_path, 'count': count})

        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'Invalid JSON: {str(e)}'})
        except Exception as e:
            print(f"[ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})

    def handle_save_validations(self):
        """Écrire le fichier data/Roadtripsprefabriques/validations.json.

        Body attendu : { "validations": { "<itin_id>": { "validated_at": "...", "by": "..." }, ... } }
        Le chemin de destination est fixe (sécurité : pas de chemin libre depuis le client).
        """
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))

            validations = data.get('validations')
            if not isinstance(validations, dict):
                self.send_json_response(400, {'success': False, 'error': 'Missing or invalid "validations" object'})
                return

            file_path = 'data/Roadtripsprefabriques/validations.json'

            # Créer le dossier si besoin
            dir_path = os.path.dirname(file_path)
            if dir_path and not os.path.exists(dir_path):
                os.makedirs(dir_path)

            # Backup si le fichier existe
            backup_path = None
            if os.path.exists(file_path):
                backup_path = backup_unique(file_path)
                print(f"[BACKUP] {file_path} -> {backup_path}")

            final_data = {
                "updated_at": datetime.now().isoformat(timespec='seconds'),
                "validations": validations
            }

            with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                json.dump(final_data, f, ensure_ascii=False, indent=2)

            count = len(validations)
            print(f"[SAVE] ✅ {file_path} ({count} validation(s))")

            self.send_json_response(200, {
                'success': True,
                'path': file_path,
                'backup': backup_path,
                'count': count
            })

        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'Invalid JSON: {str(e)}'})
        except Exception as e:
            print(f"[ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})
    
    def handle_delete_itinerary(self):
        """Supprimer un itinéraire de tous les fichiers JSON (toutes langues)."""
        try:
            # Lire le body
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode('utf-8'))
            
            # Accepter les deux formats de paramètres
            itin_id = data.get('itinId') or data.get('itin_id')
            country_code = data.get('country', '').upper()
            all_languages = data.get('allLanguages', False)
            specific_languages = data.get('languages', None)  # Liste explicite: ['en', 'es', ...]
            
            if not itin_id:
                self.send_json_response(400, {'success': False, 'error': 'Missing itinId'})
                return
            
            if not country_code:
                # Extraire le country code de l'itin_id (format: CC::region::slug)
                parts = itin_id.split('::')
                if parts:
                    country_code = parts[0].upper()
            
            if not country_code:
                self.send_json_response(400, {'success': False, 'error': 'Missing country code'})
                return
            
            # Trouver le dossier du pays
            base_dir = "data/Roadtripsprefabriques/countries"
            country_folder = None
            
            if os.path.exists(base_dir):
                for folder in os.listdir(base_dir):
                    if folder.upper() == country_code:
                        country_folder = os.path.join(base_dir, folder)
                        break
            
            if not country_folder or not os.path.exists(country_folder):
                self.send_json_response(404, {'success': False, 'error': f'Dossier pays non trouvé: {country_code}'})
                return
            
            # Liste des langues à traiter (priorité: languages > allLanguages > défaut fr)
            if specific_languages and isinstance(specific_languages, list):
                languages = [lang.lower() for lang in specific_languages]
                print(f"[DELETE] Langues spécifiques: {languages}")
            elif all_languages:
                languages = detect_languages(country_code)
                print(f"[DELETE] Toutes langues détectées: {languages}")
            else:
                languages = ['fr']
            deleted_from = []
            errors = []
            
            for lang in languages:
                # Chercher le fichier pour cette langue
                patterns = [
                    f"{country_code}.itins.modules-{lang}.json",
                    f"{country_code.lower()}.itins.modules-{lang}.json",
                    f"{country_code.upper()}.itins.modules-{lang}.json",
                ]
                
                file_path = None
                for existing_file in os.listdir(country_folder):
                    for pattern in patterns:
                        if existing_file.lower() == pattern.lower():
                            file_path = os.path.join(country_folder, existing_file)
                            break
                    if file_path:
                        break
                
                if not file_path or not os.path.exists(file_path):
                    continue  # Fichier de cette langue n'existe pas, passer au suivant
                
                try:
                    # Backup avant modification
                    backup_path = backup_unique(file_path)
                    
                    # Lire le fichier
                    with open(file_path, 'r', encoding='utf-8') as f:
                        existing_data = json.load(f)
                    
                    # Trouver et supprimer l'itinéraire
                    deleted = False
                    
                    if isinstance(existing_data, dict) and 'itineraries' in existing_data:
                        itins = existing_data['itineraries']
                        for i, itin in enumerate(itins):
                            existing_id = itin.get('id') or itin.get('itin_id')
                            if existing_id == itin_id:
                                itins.pop(i)
                                deleted = True
                                break
                                
                    elif isinstance(existing_data, list):
                        for i, itin in enumerate(existing_data):
                            existing_id = itin.get('id') or itin.get('itin_id')
                            if existing_id == itin_id:
                                existing_data.pop(i)
                                deleted = True
                                break
                    
                    if deleted:
                        # Écrire le fichier mis à jour
                        with open(file_path, 'w', encoding='utf-8', newline='\n') as f:
                            json.dump(existing_data, f, ensure_ascii=False, indent=2)
                        deleted_from.append(lang.upper())
                        print(f"[DELETE] ✅ Supprimé de {file_path}")
                    
                except Exception as e:
                    errors.append(f"{lang}: {str(e)}")
                    print(f"[DELETE ERROR] {lang}: {e}")
            
            if deleted_from:
                response = {
                    'success': True,
                    'message': f"Itinéraire '{itin_id}' supprimé",
                    'deletedFrom': ', '.join(deleted_from),
                    'languages': deleted_from
                }
                if errors:
                    response['warnings'] = errors
                print(f"[DELETE] ✅ Supprimé de: {', '.join(deleted_from)}")
                self.send_json_response(200, response)
            else:
                self.send_json_response(404, {
                    'success': False, 
                    'error': f"Itinéraire '{itin_id}' non trouvé dans aucun fichier",
                    'errors': errors if errors else None
                })
            
        except json.JSONDecodeError as e:
            self.send_json_response(400, {'success': False, 'error': f'Invalid JSON: {str(e)}'})
        except Exception as e:
            print(f"[DELETE ERROR] {e}")
            self.send_json_response(500, {'success': False, 'error': str(e)})
    
    def send_json_response(self, status, data):
        """Envoyer une réponse JSON."""
        response_body = json.dumps(data, ensure_ascii=False)
        # Nettoyer les surrogates unicode qui font crasher encode()
        response_body = response_body.encode('utf-8', errors='replace').decode('utf-8')
        body_bytes = response_body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body_bytes)))
        # Note: Access-Control-Allow-Origin ajouté automatiquement par end_headers()
        self.end_headers()
        self.wfile.write(body_bytes)
        try:
            self.wfile.flush()
        except Exception:
            pass
    
    def find_case_insensitive_path(self, requested_path, country_code):
        """
        Cherche un fichier existant avec insensibilité à la casse.
        Gère les variations: BB, bb, Bb pour dossier et fichier.
        Supporte les suffixes de langue: -fr.json, -en.json, etc.
        """
        import glob
        
        # Extraire le répertoire de base et le pattern du fichier
        base_dir = "data/Roadtripsprefabriques/countries"
        
        if not os.path.exists(base_dir):
            return None
        
        # Chercher le dossier du pays (insensible à la casse)
        country_folders = glob.glob(os.path.join(base_dir, '*'))
        country_folder = None
        for folder in country_folders:
            if os.path.basename(folder).upper() == country_code.upper():
                country_folder = folder
                break
        
        if not country_folder:
            return None
        
        # Extraire le nom du fichier demandé
        requested_filename = os.path.basename(requested_path)
        
        # Détecter le suffixe de langue (-fr, -en, etc.)
        lang_match = re.search(r'-([a-z]{2,3})\.json$', requested_filename, re.IGNORECASE)
        lang_suffix = ""
        if lang_match:
            lang_suffix = f"-{lang_match.group(1).lower()}"
        
        # Construire les patterns de recherche
        if lang_suffix:
            # Avec suffixe de langue
            patterns = [
                f"{country_code}.itins.modules{lang_suffix}.json",
                f"{country_code.lower()}.itins.modules{lang_suffix}.json",
                f"{country_code.upper()}.itins.modules{lang_suffix}.json",
            ]
        else:
            # Sans suffixe de langue (ancien format)
            patterns = [
                f"{country_code}.itins.modules.json",
                f"{country_code.lower()}.itins.modules.json",
                f"{country_code.upper()}.itins.modules.json",
                f"{country_code}_itins_modules.json",
                f"{country_code.lower()}_itins_modules.json",
                f"{country_code.upper()}_itins_modules.json",
            ]
        
        # Chercher dans le dossier
        existing_files = os.listdir(country_folder)
        for existing_file in existing_files:
            existing_lower = existing_file.lower()
            for pattern in patterns:
                if existing_lower == pattern.lower():
                    return os.path.join(country_folder, existing_file)
        
        # Pas trouvé - retourner None pour créer un nouveau fichier
        return None
    
    def end_headers(self):
        """Ajouter les headers CORS."""
        self.send_header('Access-Control-Allow-Origin', '*')
        super().end_headers()


def run_server():
    """Lancer le serveur."""
    # ThreadingTCPServer : traite plusieurs requêtes en parallèle
    # (sinon le précache Wiki bloque tout le reste)
    class _Srv(socketserver.ThreadingTCPServer):
        allow_reuse_address = True
        daemon_threads = True
        # File d attente des connexions. La valeur par defaut est 5 : au dela,
        # le systeme REFUSE la connexion et le navigateur recoit une coupure
        # seche, sans que le serveur ait rien vu. L audit en masse ouvre
        # facilement une dizaine de requetes en meme temps, et chaque ecriture
        # perdue ainsi est une correction qui disparait sans laisser de trace.
        request_queue_size = 128
    with _Srv(("", PORT), ORTRequestHandler) as httpd:
        print(f"""
╔═══════════════════════════════════════════════════════════════╗
║                  OneRoadTrip Dev Server                       ║
╠═══════════════════════════════════════════════════════════════╣
║  🌐 http://127.0.0.1:{PORT:<5}                                   ║
║  📂 Serving: {os.getcwd()[:45]:<45} ║
║  🔴 POST /api/save-itinerary - Écrire source                  ║
║  🈯 GET/POST /api/trad-input/* - Traductions en attente        ║
║  ✅ POST /api/save-validations - Écrire validations.json      ║
║  🗑️  POST /api/delete-itinerary - Supprimer RT                 ║
║  📸 POST /api/photos/search - Chercher candidates              ║
║  📸 POST /api/photos/select - Uploader sur R2                  ║
║  📸 GET  /api/photos/places - Lister lieux + statut            ║
║  🏨 GET  /api/hotels/places - Hôtels par pays + statut         ║
║  🏨 POST /api/hotels/set-cover - Photo vitrine d'un hôtel      ║
╠═══════════════════════════════════════════════════════════════╣
║  Ctrl+C pour arrêter                                          ║
╚═══════════════════════════════════════════════════════════════╝
""")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n[SERVER] Arrêt...")
            httpd.shutdown()


if __name__ == '__main__':
    run_server()