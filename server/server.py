#!/usr/bin/env python3
"""
AntiScroll - serveur de comptes.

Tourne sur TON PC. Les comptes et les réglages sont stockés dans des
fichiers JSON (dossier ./data à côté de ce fichier, ou --data DOSSIER).
Aucun service externe, aucune dépendance : Python 3.9+ suffit.

Lancement :  python3 server.py            (port 47800 par défaut)
             python3 server.py --port 47800 --data /chemin/vers/data
"""
import argparse
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 47800
PBKDF2_ITER = 150_000
USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,20}$")


# --------------------------------------------------------------------------- #
# Stockage fichier
# --------------------------------------------------------------------------- #
class Store:
    def __init__(self, data_dir):
        self.dir = data_dir
        os.makedirs(self.dir, exist_ok=True)
        self.path = os.path.join(self.dir, "users.json")
        self.lock = threading.Lock()
        self.db = {"users": {}, "tokens": {}}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                self.db = json.load(f)
            self.db.setdefault("users", {})
            self.db.setdefault("tokens", {})

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.db, f, indent=2, ensure_ascii=False)
        os.replace(tmp, self.path)  # écriture atomique


def hash_pw(password, salt=None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), PBKDF2_ITER)
    return {"salt": salt, "hash": h.hex(), "iter": PBKDF2_ITER}


def check_pw(password, rec):
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(rec["salt"]),
                            int(rec.get("iter", PBKDF2_ITER)))
    return hmac.compare_digest(h.hex(), rec["hash"])


def empty_config():
    return {"updated_at": 0, "unlock": None, "objectives": [],
            "settings": {"app_recheck_min": 3}}


# --------------------------------------------------------------------------- #
# HTTP
# --------------------------------------------------------------------------- #
def make_handler(store):
    class Handler(BaseHTTPRequestHandler):
        server_version = "AntiScroll/1.0"

        def log_message(self, fmt, *args):  # logs discrets
            print("[serveur]", self.address_string(), fmt % args)

        # -- utilitaires --
        def send_json(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > 1_000_000:
                raise ValueError("trop gros")
            raw = self.rfile.read(n) if n else b"{}"
            return json.loads(raw or b"{}")

        def auth_user(self):
            a = self.headers.get("Authorization", "")
            tok = a[7:] if a.startswith("Bearer ") else ""
            with store.lock:
                uid = store.db["tokens"].get(tok)
                if uid and uid in store.db["users"]:
                    return uid
            return None

        def new_token(self, uid):
            tok = secrets.token_hex(24)
            store.db["tokens"][tok] = uid
            return tok

        # -- routes --
        def do_GET(self):
            if self.path == "/ping":
                return self.send_json(200, {"ok": True, "app": "antiscroll"})
            if self.path == "/config":
                uid = self.auth_user()
                if not uid:
                    return self.send_json(401, {"error": "Non connecté"})
                with store.lock:
                    u = store.db["users"][uid]
                    return self.send_json(200, {"username": u["username"],
                                                "config": u["config"]})
            self.send_json(404, {"error": "Introuvable"})

        def do_PUT(self):
            if self.path != "/config":
                return self.send_json(404, {"error": "Introuvable"})
            uid = self.auth_user()
            if not uid:
                return self.send_json(401, {"error": "Non connecté"})
            try:
                cfg = self.body().get("config")
            except Exception:
                return self.send_json(400, {"error": "JSON invalide"})
            if not isinstance(cfg, dict):
                return self.send_json(400, {"error": "config manquante"})
            with store.lock:
                cur = store.db["users"][uid]["config"]
                # dernier qui écrit gagne, sauf si le serveur est plus récent
                if cfg.get("updated_at", 0) >= cur.get("updated_at", 0):
                    store.db["users"][uid]["config"] = cfg
                    store.save()
                return self.send_json(200, {"config": store.db["users"][uid]["config"]})

        def do_DELETE(self):
            if self.path != "/account":
                return self.send_json(404, {"error": "Introuvable"})
            uid = self.auth_user()
            if not uid:
                return self.send_json(401, {"error": "Non connecté"})
            try:
                d = self.body()
            except Exception:
                d = {}
            with store.lock:
                u = store.db["users"][uid]
                if not check_pw(d.get("password", ""), u["pw"]):
                    return self.send_json(403, {"error": "Mot de passe incorrect"})
                del store.db["users"][uid]
                store.db["tokens"] = {t: v for t, v in store.db["tokens"].items() if v != uid}
                store.save()
            self.send_json(200, {"ok": True})

        def do_POST(self):
            try:
                d = self.body()
            except Exception:
                return self.send_json(400, {"error": "JSON invalide"})

            if self.path == "/register":
                name = str(d.get("username", "")).strip()
                pw = str(d.get("password", ""))
                if not USERNAME_RE.match(name):
                    return self.send_json(400, {"error": "Pseudo : 3 à 20 caractères (lettres, chiffres, _ . -)"})
                if len(pw) < 6:
                    return self.send_json(400, {"error": "Mot de passe : 6 caractères minimum"})
                with store.lock:
                    if any(u["username"].lower() == name.lower() for u in store.db["users"].values()):
                        return self.send_json(409, {"error": "Ce pseudo est déjà pris"})
                    uid = secrets.token_hex(8)
                    store.db["users"][uid] = {"username": name, "pw": hash_pw(pw),
                                              "created": int(time.time()),
                                              "config": empty_config()}
                    tok = self.new_token(uid)
                    store.save()
                return self.send_json(200, {"token": tok, "username": name})

            if self.path == "/login":
                name = str(d.get("username", "")).strip().lower()
                pw = str(d.get("password", ""))
                with store.lock:
                    for uid, u in store.db["users"].items():
                        if u["username"].lower() == name and check_pw(pw, u["pw"]):
                            tok = self.new_token(uid)
                            store.save()
                            return self.send_json(200, {"token": tok, "username": u["username"]})
                time.sleep(0.8)  # ralentit les essais en boucle
                return self.send_json(403, {"error": "Pseudo ou mot de passe incorrect"})

            uid = self.auth_user()
            if not uid:
                return self.send_json(401, {"error": "Non connecté"})

            if self.path == "/logout":
                tok = self.headers.get("Authorization", "")[7:]
                with store.lock:
                    store.db["tokens"].pop(tok, None)
                    store.save()
                return self.send_json(200, {"ok": True})

            if self.path == "/account/password":
                with store.lock:
                    u = store.db["users"][uid]
                    if not check_pw(str(d.get("old", "")), u["pw"]):
                        return self.send_json(403, {"error": "Ancien mot de passe incorrect"})
                    new = str(d.get("new", ""))
                    if len(new) < 6:
                        return self.send_json(400, {"error": "Mot de passe : 6 caractères minimum"})
                    u["pw"] = hash_pw(new)
                    store.save()
                return self.send_json(200, {"ok": True})

            if self.path == "/account/username":
                new = str(d.get("username", "")).strip()
                if not USERNAME_RE.match(new):
                    return self.send_json(400, {"error": "Pseudo : 3 à 20 caractères (lettres, chiffres, _ . -)"})
                with store.lock:
                    if any(k != uid and u["username"].lower() == new.lower()
                           for k, u in store.db["users"].items()):
                        return self.send_json(409, {"error": "Ce pseudo est déjà pris"})
                    store.db["users"][uid]["username"] = new
                    store.save()
                return self.send_json(200, {"ok": True, "username": new})

            self.send_json(404, {"error": "Introuvable"})

    return Handler


def run(port=DEFAULT_PORT, data_dir=None, host="0.0.0.0"):
    data_dir = data_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
    store = Store(data_dir)
    httpd = ThreadingHTTPServer((host, port), make_handler(store))
    print(f"[serveur] AntiScroll écoute sur {host}:{port} - données dans {data_dir}")
    return httpd


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--data", default=None)
    ap.add_argument("--host", default="0.0.0.0")
    a = ap.parse_args()
    try:
        run(a.port, a.data, a.host).serve_forever()
    except KeyboardInterrupt:
        pass
