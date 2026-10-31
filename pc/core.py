"""
AntiScroll PC - logique sans interface (testable) :
code de déblocage, planning des objectifs, état local, export/import de config.
Tout est stocké sur cet appareil : aucun serveur, aucun lien entre appareils.
"""
import datetime as dt
import hashlib
import hmac
import json
import math
import os
import secrets
import threading
import time

PBKDF2_ITER = 150_000          # mêmes réglages que l'extension et l'app Android
WARN_THRESHOLDS = (10, 5, 1)   # minutes avant le blocage
APP_DIR = os.path.join(os.path.expanduser("~"), ".antiscroll")
STATE_PATH = os.path.join(APP_DIR, "state.json")

# Apps installées surveillées sur PC (nom de processus en minuscules)
DEFAULT_WATCHED = [
    "tiktok.exe", "tiktok", "instagram.exe", "instagram",
    "snapchat.exe", "facebook.exe", "messenger.exe",
]


# --------------------------------------------------------------------------- #
# Code de déblocage (le "mdp" demandé à chaque vidéo / pour débloquer)
# --------------------------------------------------------------------------- #
def make_unlock(code):
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(salt), PBKDF2_ITER)
    return {"salt": salt, "hash": h.hex(), "iter": PBKDF2_ITER}


def check_unlock(code, rec):
    if not rec:
        return True  # aucun code choisi -> rien à vérifier
    h = hashlib.pbkdf2_hmac("sha256", code.encode(), bytes.fromhex(rec["salt"]),
                            int(rec.get("iter", PBKDF2_ITER)))
    return hmac.compare_digest(h.hex(), rec["hash"])


# --------------------------------------------------------------------------- #
# Objectifs
#   {"id": "...", "title": "Réviser", "start": "18:30", "duration": 60,
#    "days": [0,1,2,3,4]}   0 = lundi ... 6 = dimanche, [] = tous les jours
# --------------------------------------------------------------------------- #
def new_objective(title, start, duration, days):
    hh, mm = parse_hhmm(start)
    duration = int(duration)
    if duration <= 0 or duration > 24 * 60:
        raise ValueError("Durée entre 1 et 1440 minutes")
    return {"id": secrets.token_hex(6), "title": title.strip() or "Objectif",
            "start": f"{hh:02d}:{mm:02d}", "duration": duration,
            "days": sorted(set(int(d) for d in days))}


def parse_hhmm(s):
    try:
        hh, mm = s.strip().split(":")
        hh, mm = int(hh), int(mm)
        assert 0 <= hh < 24 and 0 <= mm < 60
        return hh, mm
    except Exception:
        raise ValueError("Heure au format HH:MM (ex. 18:30)")


def occurrences(obj, now):
    """Occurrences (début, fin, clé) d'hier, aujourd'hui et demain."""
    hh, mm = parse_hhmm(obj["start"])
    out = []
    for delta in (-1, 0, 1):
        day = (now + dt.timedelta(days=delta)).date()
        if obj.get("days") and day.weekday() not in obj["days"]:
            continue
        start = dt.datetime.combine(day, dt.time(hh, mm))
        end = start + dt.timedelta(minutes=int(obj["duration"]))
        out.append((start, end, f"{obj['id']}@{day.isoformat()}"))
    return out


def active_block(objectives, now):
    """Renvoie (objectif, fin, clé) si un objectif est en cours, sinon None."""
    for o in objectives:
        for start, end, key in occurrences(o, now):
            if start <= now < end:
                return o, end, key
    return None


def upcoming(objectives, now, within_min=10):
    """Liste (objectif, secondes restantes, clé) des objectifs qui démarrent bientôt."""
    res = []
    for o in objectives:
        for start, _end, key in occurrences(o, now):
            sec = (start - now).total_seconds()
            if 0 < sec <= within_min * 60:
                res.append((o, sec, key))
    return res


class WarningTracker:
    """Décide quand envoyer les alertes 10 / 5 / 1 minute (une seule fois chacune)."""

    def __init__(self):
        self.sent = set()

    def due(self, objectives, now):
        msgs = []
        for o, sec, key in upcoming(objectives, now, max(WARN_THRESHOLDS)):
            crossed = [t for t in WARN_THRESHOLDS if sec <= t * 60]
            new = [t for t in crossed if (key, t) not in self.sent]
            if new:
                for t in crossed:
                    self.sent.add((key, t))
                mins = max(1, math.ceil(sec / 60))
                msgs.append((o, mins))
        return msgs


# --------------------------------------------------------------------------- #
# État local (~/.antiscroll/state.json)
# --------------------------------------------------------------------------- #
def default_state():
    return {
        "watched_apps": list(DEFAULT_WATCHED),
        "config": {"updated_at": 0, "unlock": None, "objectives": [],
                   "settings": {"app_recheck_min": 3}},
    }


class State:
    def __init__(self, path=STATE_PATH):
        self.path = path
        self.lock = threading.RLock()
        self.data = default_state()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                self.data.update(loaded)
            except Exception:
                pass

    def save(self):
        with self.lock:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.path)

    @property
    def config(self):
        return self.data["config"]

    def touch_config(self):
        """À appeler après une modif locale de la config."""
        with self.lock:
            self.data["config"]["updated_at"] = int(time.time() * 1000)
            self.save()


# --------------------------------------------------------------------------- #
# Export / import de la config (fichier .json à transporter sur un autre appareil)
#   Le code n'est jamais écrit en clair : seulement son empreinte (sel + hash).
# --------------------------------------------------------------------------- #
EXPORT_APP = "antiscroll"
EXPORT_VERSION = 1


class ConfigFileError(ValueError):
    pass


def export_config(config, watched_apps=None):
    """Construit le contenu du fichier exporté (dict prêt pour json.dump)."""
    out = {
        "app": EXPORT_APP,
        "version": EXPORT_VERSION,
        "exported_at": int(time.time() * 1000),
        "config": {
            "unlock": config.get("unlock"),
            "objectives": list(config.get("objectives", [])),
            "settings": dict(config.get("settings", {})),
        },
    }
    if watched_apps is not None:
        out["watched_apps"] = list(watched_apps)
    return out


def _check_unlock_rec(rec):
    if rec is None:
        return None
    if not isinstance(rec, dict):
        raise ConfigFileError("Code invalide dans le fichier")
    try:
        bytes.fromhex(rec["salt"])
        bytes.fromhex(rec["hash"])
        it = int(rec.get("iter", PBKDF2_ITER))
    except Exception:
        raise ConfigFileError("Code invalide dans le fichier")
    if it < 1000:
        raise ConfigFileError("Code invalide dans le fichier")
    return {"salt": rec["salt"], "hash": rec["hash"], "iter": it}


def parse_import(text):
    """Lit un fichier exporté (texte JSON). Renvoie (config, watched_apps ou None)."""
    try:
        data = json.loads(text)
    except Exception:
        raise ConfigFileError("Ce fichier n'est pas une config AntiScroll")
    if not isinstance(data, dict) or data.get("app") != EXPORT_APP:
        raise ConfigFileError("Ce fichier n'est pas une config AntiScroll")
    if int(data.get("version", 0)) > EXPORT_VERSION:
        raise ConfigFileError("Config créée par une version plus récente d'AntiScroll")
    cfg = data.get("config")
    if not isinstance(cfg, dict):
        raise ConfigFileError("Config vide ou abîmée")
    objectives = []
    for o in cfg.get("objectives", []) or []:
        try:
            hh, mm = parse_hhmm(str(o["start"]))
            dur = int(o["duration"])
            assert 0 < dur <= 24 * 60
            days = sorted(set(int(d) for d in o.get("days", []) if 0 <= int(d) <= 6))
            objectives.append({"id": str(o.get("id") or secrets.token_hex(6)),
                               "title": str(o.get("title") or "Objectif"),
                               "start": f"{hh:02d}:{mm:02d}", "duration": dur, "days": days})
        except Exception:
            raise ConfigFileError("Un objectif du fichier est abîmé")
    settings = cfg.get("settings") if isinstance(cfg.get("settings"), dict) else {}
    try:
        recheck = max(1, min(120, int(settings.get("app_recheck_min", 3))))
    except Exception:
        recheck = 3
    config = {"updated_at": int(time.time() * 1000),
              "unlock": _check_unlock_rec(cfg.get("unlock")),
              "objectives": objectives,
              "settings": {"app_recheck_min": recheck}}
    watched = data.get("watched_apps")
    if isinstance(watched, list):
        watched = [str(n).strip().lower() for n in watched if str(n).strip()]
    else:
        watched = None
    return config, watched
