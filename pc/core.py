"""
AntiScroll PC - logique sans interface (testable) :
code de déblocage, planning des objectifs, état local, client du serveur.
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
import urllib.error
import urllib.request

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
        "server_url": "",          # ex. http://100.101.102.103:47800
        "token": "",
        "username": "",
        "host_server": False,      # ce PC fait tourner le serveur
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
# Client du serveur
# --------------------------------------------------------------------------- #
class ApiError(Exception):
    pass


class Api:
    def __init__(self, state):
        self.state = state

    def _req(self, method, path, body=None, auth=True, timeout=6):
        base = self.state.data.get("server_url", "").rstrip("/")
        if not base:
            raise ApiError("Adresse du serveur non configurée")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(base + path, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        if auth and self.state.data.get("token"):
            req.add_header("Authorization", "Bearer " + self.state.data["token"])
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                msg = json.loads(e.read()).get("error", str(e))
            except Exception:
                msg = str(e)
            raise ApiError(msg)
        except Exception as e:
            raise ApiError(f"Serveur injoignable ({e})")

    def register(self, username, password):
        r = self._req("POST", "/register", {"username": username, "password": password}, auth=False)
        self._logged_in(r)

    def login(self, username, password):
        r = self._req("POST", "/login", {"username": username, "password": password}, auth=False)
        self._logged_in(r)

    def _logged_in(self, r):
        with self.state.lock:
            self.state.data["token"] = r["token"]
            self.state.data["username"] = r["username"]
            self.state.save()
        self.sync(prefer_server_if_empty=True)

    def logout(self):
        try:
            self._req("POST", "/logout", {})
        except ApiError:
            pass
        with self.state.lock:
            self.state.data["token"] = ""
            self.state.data["username"] = ""
            self.state.save()

    def change_password(self, old, new):
        self._req("POST", "/account/password", {"old": old, "new": new})

    def change_username(self, new):
        r = self._req("POST", "/account/username", {"username": new})
        with self.state.lock:
            self.state.data["username"] = r["username"]
            self.state.save()

    def delete_account(self, password):
        self._req("DELETE", "/account", {"password": password})
        with self.state.lock:
            self.state.data["token"] = ""
            self.state.data["username"] = ""
            self.state.save()

    def sync(self, prefer_server_if_empty=False):
        """Synchronise la config (le plus récent gagne)."""
        if not self.state.data.get("token"):
            return False
        remote = self._req("GET", "/config")["config"]
        with self.state.lock:
            local = self.state.config
            r_t, l_t = remote.get("updated_at", 0), local.get("updated_at", 0)
            local_empty = not local.get("objectives") and not local.get("unlock")
            if r_t > l_t or (prefer_server_if_empty and local_empty and r_t > 0):
                self.state.data["config"] = remote
                self.state.save()
            elif l_t > r_t:
                pushed = self._req("PUT", "/config", {"config": local})["config"]
                self.state.data["config"] = pushed
                self.state.save()
        return True
