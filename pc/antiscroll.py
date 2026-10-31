#!/usr/bin/env python3
"""
AntiScroll pour PC (Ubuntu + Windows).

- Écran noir par-dessus TOUT, sans mettre en pause ni tuer les programmes :
  c'est juste une fenêtre noire au premier plan, tes processus continuent.
- Objectifs à heure fixe : alertes 10 / 5 / 1 min avant, puis blocage
  pendant la durée prévue (déblocage avec ton code).
- Apps installées (TikTok, Instagram...) : écran noir + code, redemandé
  toutes les X minutes.
- Pont local pour l'extension Firefox (code à chaque vidéo).
- Comptes + synchro avec le serveur (qui peut tourner sur ce PC).
"""
import datetime as dt
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from tkinter import messagebox, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

import core  # noqa: E402

try:
    import psutil  # facultatif mais recommandé
except ImportError:
    psutil = None

IS_WIN = platform.system() == "Windows"
BRIDGE_PORT = 47811
DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


# --------------------------------------------------------------------------- #
# Écrans (multi-moniteurs)
# --------------------------------------------------------------------------- #
def list_monitors(root):
    """Liste de (x, y, largeur, hauteur) pour chaque écran."""
    try:
        from screeninfo import get_monitors
        mons = [(m.x, m.y, m.width, m.height) for m in get_monitors()]
        if mons:
            return mons
    except Exception:
        pass
    if IS_WIN:
        try:
            import ctypes
            from ctypes import wintypes
            mons = []
            CB = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                                    ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

            def cb(_h, _dc, rect, _lp):
                r = rect.contents
                mons.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
                return 1
            ctypes.windll.user32.EnumDisplayMonitors(0, 0, CB(cb), 0)
            if mons:
                return mons
        except Exception:
            pass
    elif shutil.which("xrandr"):
        try:
            out = subprocess.run(["xrandr", "--listmonitors"], capture_output=True,
                                 text=True, timeout=3).stdout
            mons = []
            for line in out.splitlines()[1:]:
                geo = line.split()[2]                     # 1920/344x1080/194+0+0
                wpart, rest = geo.split("x", 1)
                w = int(wpart.split("/")[0])
                hpart, x, y = rest.split("+")
                h = int(hpart.split("/")[0])
                mons.append((int(x), int(y), w, h))
            if mons:
                return mons
        except Exception:
            pass
    return [(0, 0, root.winfo_screenwidth(), root.winfo_screenheight())]


# --------------------------------------------------------------------------- #
# Écran noir
# --------------------------------------------------------------------------- #
class BlackScreen:
    """
    Fenêtres noires plein écran, toujours au-dessus, sur chaque moniteur.
    Aucun processus n'est suspendu : c'est seulement un affichage.
    """

    def __init__(self, app, title, subtitle, on_code, extra_button=None, countdown_to=None):
        self.app = app
        self.on_code = on_code            # fonction(code) -> True si débloqué
        self.countdown_to = countdown_to  # datetime de fin (affiche le temps restant)
        self.windows = []
        self.alive = True
        mons = list_monitors(app.root)

        for i, (x, y, w, h) in enumerate(mons):
            win = tk.Toplevel(app.root)
            win.configure(bg="black", cursor="arrow")
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.protocol("WM_DELETE_WINDOW", lambda: None)  # impossible de fermer
            if IS_WIN or i > 0:
                win.overrideredirect(True)
            win.attributes("-topmost", True)
            if not IS_WIN and i == 0:
                win.update_idletasks()
                try:
                    win.attributes("-fullscreen", True)
                except tk.TclError:
                    win.overrideredirect(True)
            self.windows.append(win)

        main = self.windows[0]
        box = tk.Frame(main, bg="black")
        box.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(box, text=title, fg="white", bg="black",
                 font=("Helvetica", 30, "bold")).pack(pady=(0, 10))
        tk.Label(box, text=subtitle, fg="#9a9a9a", bg="black", wraplength=700,
                 font=("Helvetica", 14), justify="center").pack(pady=(0, 20))
        self.timer_lbl = tk.Label(box, text="", fg="#7fb2ff", bg="black",
                                  font=("Helvetica", 20))
        self.timer_lbl.pack(pady=(0, 20))

        has_code = bool(app.state.config.get("unlock"))
        self.entry = tk.Entry(box, show="•", font=("Helvetica", 18), width=18,
                              justify="center", bg="#1b1b1b", fg="white",
                              insertbackground="white", relief="flat")
        self.msg = tk.Label(box, text="", fg="#ff6b6b", bg="black", font=("Helvetica", 12))
        if has_code:
            tk.Label(box, text="Code de déblocage", fg="#cfcfcf", bg="black",
                     font=("Helvetica", 12)).pack()
            self.entry.pack(ipady=6, pady=6)
            self.entry.bind("<Return>", lambda e: self.submit())
            tk.Button(box, text="Débloquer", command=self.submit, font=("Helvetica", 13),
                      bg="#2d2d2d", fg="white", activebackground="#444",
                      relief="flat", padx=18, pady=6).pack(pady=6)
        else:
            tk.Label(box, text="(Aucun code choisi : crée-en un dans l'app AntiScroll)",
                     fg="#cfcfcf", bg="black").pack()
            tk.Button(box, text="Continuer", command=self.submit, bg="#2d2d2d",
                      fg="white", relief="flat", padx=18, pady=6).pack(pady=6)
        self.msg.pack()
        if extra_button:
            label, fn = extra_button
            tk.Button(box, text=label, command=lambda: (fn(), self.close()),
                      bg="#141414", fg="#bbbbbb", relief="flat",
                      padx=14, pady=4).pack(pady=(18, 0))
        self._keep_on_top()

    def submit(self):
        code = self.entry.get()
        self.entry.delete(0, "end")
        if self.on_code(code):
            self.close()
        else:
            self.msg.config(text="Code incorrect")

    def _keep_on_top(self):
        if not self.alive:
            return
        for w in self.windows:
            try:
                w.lift()
                w.attributes("-topmost", True)
            except tk.TclError:
                pass
        try:
            focus = self.windows[0].focus_get()
            if focus is None:
                self.windows[0].focus_force()
                self.entry.focus_set()
        except (tk.TclError, KeyError):
            pass
        if self.countdown_to:
            left = int((self.countdown_to - dt.datetime.now()).total_seconds())
            if left <= 0:
                self.close()
                return
            self.timer_lbl.config(text=f"Fin dans {left // 60:02d}:{left % 60:02d}")
        self.windows[0].after(400, self._keep_on_top)

    def close(self):
        self.alive = False
        for w in self.windows:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.app.overlay_closed(self)


# --------------------------------------------------------------------------- #
# Petite notification en haut à droite
# --------------------------------------------------------------------------- #
def toast(root, title, text, seconds=10):
    if not IS_WIN and shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-u", "critical", title, text])
    t = tk.Toplevel(root)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    t.configure(bg="#202020")
    tk.Label(t, text=title, fg="white", bg="#202020",
             font=("Helvetica", 13, "bold")).pack(padx=16, pady=(12, 2), anchor="w")
    tk.Label(t, text=text, fg="#dddddd", bg="#202020", wraplength=320,
             justify="left").pack(padx=16, pady=(0, 12), anchor="w")
    t.update_idletasks()
    x = root.winfo_screenwidth() - t.winfo_width() - 24
    t.geometry(f"+{x}+40")
    t.bind("<Button-1>", lambda e: t.destroy())
    root.bell()
    t.after(seconds * 1000, lambda: t.winfo_exists() and t.destroy())


# --------------------------------------------------------------------------- #
# Pont local pour l'extension Firefox (127.0.0.1 uniquement)
# --------------------------------------------------------------------------- #
def start_bridge(app):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _ok_origin(self):
            # Les pages web ne doivent pas lire ces infos : seule l'extension passe.
            origin = self.headers.get("Origin", "")
            return origin == "" or origin.startswith("moz-extension://")

        def _json(self, code, obj):
            b = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self):
            if not self._ok_origin():
                return self._json(403, {})
            if self.path == "/status":
                return self._json(200, app.bridge_status())
            self._json(404, {})

        def do_POST(self):
            if not self._ok_origin():
                return self._json(403, {})
            if self.path == "/verify":
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    code = json.loads(self.rfile.read(n) or b"{}").get("code", "")
                except Exception:
                    code = ""
                return self._json(200, {"ok": core.check_unlock(code, app.state.config.get("unlock"))})
            self._json(404, {})

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), H)
    except OSError:
        return False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return True


# --------------------------------------------------------------------------- #
# Application
# --------------------------------------------------------------------------- #
class App:
    def __init__(self, minimized=False):
        self.state = core.State()
        self.api = core.Api(self.state)
        self.warn = core.WarningTracker()
        self.unlocked_blocks = set()    # occurrences d'objectifs débloquées avec le code
        self.app_ok_until = 0.0         # apps installées autorisées jusqu'à ce moment
        self.overlay = None
        self.overlay_kind = None
        self.events = queue.Queue()     # messages des threads vers l'interface
        self.server_httpd = None
        self.last_sync = 0

        self.root = tk.Tk()
        self.root.title("AntiScroll")
        self.root.geometry("640x520")
        self.root.protocol("WM_DELETE_WINDOW", self.root.iconify)  # fermer = réduire
        self.build_ui()

        if self.state.data.get("host_server"):
            self.start_server()
        self.bridge_ok = start_bridge(self)
        self.refresh_status()

        threading.Thread(target=self.watch_apps, daemon=True).start()
        self.root.after(1000, self.tick)
        self.root.after(200, self.pump_events)
        if minimized:
            self.root.iconify()

    # ----------------------------- interface ------------------------------ #
    def build_ui(self):
        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=8, pady=8)
        self.tab_objectives(nb)
        self.tab_code(nb)
        self.tab_account(nb)
        self.tab_apps(nb)

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=8, pady=(0, 8))
        self.status = ttk.Label(bar, text="")
        self.status.pack(side="left")
        ttk.Button(bar, text="Quitter", command=self.quit_app).pack(side="right")
        ttk.Button(bar, text="Tester l'écran noir", command=self.test_black).pack(side="right", padx=6)

    def tab_objectives(self, nb):
        f = ttk.Frame(nb, padding=10)
        nb.add(f, text="Objectifs")
        cols = ("titre", "heure", "duree", "jours")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=9)
        for c, t, w in zip(cols, ("Objectif", "Heure", "Durée", "Jours"), (220, 70, 80, 200)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)

        form = ttk.Frame(f)
        form.pack(fill="x", pady=8)
        ttk.Label(form, text="Objectif").grid(row=0, column=0, sticky="w")
        self.o_title = ttk.Entry(form, width=24)
        self.o_title.grid(row=0, column=1, sticky="w")
        ttk.Label(form, text="Heure (HH:MM)").grid(row=0, column=2, padx=(10, 0))
        self.o_start = ttk.Entry(form, width=7)
        self.o_start.grid(row=0, column=3)
        ttk.Label(form, text="Durée (min)").grid(row=0, column=4, padx=(10, 0))
        self.o_dur = ttk.Entry(form, width=6)
        self.o_dur.grid(row=0, column=5)
        days = ttk.Frame(form)
        days.grid(row=1, column=0, columnspan=6, sticky="w", pady=6)
        ttk.Label(days, text="Jours (aucun = tous) :").pack(side="left")
        self.o_days = []
        for d in DAYS:
            v = tk.BooleanVar()
            ttk.Checkbutton(days, text=d, variable=v).pack(side="left")
            self.o_days.append(v)

        btns = ttk.Frame(f)
        btns.pack(fill="x")
        ttk.Button(btns, text="Ajouter", command=self.add_objective).pack(side="left")
        ttk.Button(btns, text="Supprimer (code requis)", command=self.del_objective).pack(side="left", padx=6)
        self.refresh_objectives()

    def tab_code(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="Code")
        ttk.Label(f, text="Ce code est demandé à chaque vidéo (Shorts, Reels, TikTok...),\n"
                          "pour débloquer un objectif, supprimer un objectif ou quitter l'app.",
                  justify="left").pack(anchor="w", pady=(0, 12))
        self.code_info = ttk.Label(f, text="")
        self.code_info.pack(anchor="w", pady=(0, 8))
        ttk.Button(f, text="Choisir / changer le code", command=self.set_code).pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=16)
        ttk.Label(f, text="Redemander le code pour les apps PC toutes les (minutes) :").pack(anchor="w")
        self.recheck = ttk.Spinbox(f, from_=1, to=120, width=6)
        self.recheck.set(self.state.config.get("settings", {}).get("app_recheck_min", 3))
        self.recheck.pack(anchor="w", pady=4)
        ttk.Button(f, text="Enregistrer", command=self.save_recheck).pack(anchor="w")
        self.refresh_code_info()

    def tab_account(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="Compte")
        self.host_var = tk.BooleanVar(value=self.state.data.get("host_server", False))
        ttk.Checkbutton(f, text="Ce PC héberge le serveur (les comptes sont stockés ici)",
                        variable=self.host_var, command=self.toggle_host).pack(anchor="w")
        self.host_info = ttk.Label(f, text="", foreground="#666")
        self.host_info.pack(anchor="w", pady=(0, 10))

        ttk.Label(f, text="Adresse du serveur (ex. http://100.x.y.z:47800)").pack(anchor="w")
        self.srv = ttk.Entry(f, width=40)
        self.srv.insert(0, self.state.data.get("server_url", ""))
        self.srv.pack(anchor="w", pady=(0, 10))

        self.acc_box = ttk.Frame(f)
        self.acc_box.pack(fill="x")
        self.build_account_box()

    def build_account_box(self):
        for w in self.acc_box.winfo_children():
            w.destroy()
        f = self.acc_box
        if self.state.data.get("token"):
            ttk.Label(f, text=f"Connecté : {self.state.data['username']}",
                      font=("Helvetica", 12, "bold")).pack(anchor="w", pady=(0, 8))
            row = ttk.Frame(f)
            row.pack(anchor="w")
            ttk.Button(row, text="Synchroniser", command=self.sync_now).pack(side="left")
            ttk.Button(row, text="Changer de pseudo", command=self.change_username).pack(side="left", padx=4)
            ttk.Button(row, text="Changer le mot de passe", command=self.change_password).pack(side="left")
            row2 = ttk.Frame(f)
            row2.pack(anchor="w", pady=8)
            ttk.Button(row2, text="Se déconnecter", command=self.logout).pack(side="left")
            ttk.Button(row2, text="Supprimer le compte", command=self.delete_account).pack(side="left", padx=4)
        else:
            ttk.Label(f, text="Pseudo").pack(anchor="w")
            self.u = ttk.Entry(f, width=24)
            self.u.pack(anchor="w")
            ttk.Label(f, text="Mot de passe du compte").pack(anchor="w")
            self.p = ttk.Entry(f, width=24, show="•")
            self.p.pack(anchor="w")
            row = ttk.Frame(f)
            row.pack(anchor="w", pady=8)
            ttk.Button(row, text="Se connecter", command=lambda: self.auth("login")).pack(side="left")
            ttk.Button(row, text="Créer un compte", command=lambda: self.auth("register")).pack(side="left", padx=6)
            ttk.Label(f, text="Sans compte, l'app marche quand même (sans synchro).",
                      foreground="#666").pack(anchor="w")

    def tab_apps(self, nb):
        f = ttk.Frame(nb, padding=16)
        nb.add(f, text="Apps PC")
        ttk.Label(f, text="Noms de processus surveillés (un par ligne).\n"
                          "Quand l'un d'eux tourne : écran noir + code.").pack(anchor="w")
        self.apps_txt = tk.Text(f, height=12, width=40)
        self.apps_txt.insert("1.0", "\n".join(self.state.data.get("watched_apps", [])))
        self.apps_txt.pack(anchor="w", pady=6)
        ttk.Button(f, text="Enregistrer", command=self.save_apps).pack(anchor="w")
        ttk.Button(f, text="Lancer AntiScroll au démarrage du PC",
                   command=self.install_autostart).pack(anchor="w", pady=(16, 0))
        if psutil is None:
            ttk.Label(f, text="⚠ Installe psutil (pip install psutil) pour surveiller les apps.",
                      foreground="#b00").pack(anchor="w", pady=8)

    # ----------------------------- actions -------------------------------- #
    def ask_code(self, why):
        """Demande le code si un code existe. Renvoie True si OK."""
        rec = self.state.config.get("unlock")
        if not rec:
            return True
        code = simpledialog.askstring("Code requis", why, show="•", parent=self.root)
        if code is None:
            return False
        if core.check_unlock(code, rec):
            return True
        messagebox.showerror("AntiScroll", "Code incorrect", parent=self.root)
        return False

    def refresh_objectives(self):
        self.tree.delete(*self.tree.get_children())
        for o in self.state.config.get("objectives", []):
            days = ", ".join(DAYS[d] for d in o.get("days", [])) or "Tous les jours"
            self.tree.insert("", "end", iid=o["id"],
                             values=(o["title"], o["start"], f"{o['duration']} min", days))

    def add_objective(self):
        try:
            o = core.new_objective(self.o_title.get(), self.o_start.get(), self.o_dur.get() or 0,
                                   [i for i, v in enumerate(self.o_days) if v.get()])
        except ValueError as e:
            return messagebox.showerror("AntiScroll", str(e), parent=self.root)
        self.state.config.setdefault("objectives", []).append(o)
        self.state.touch_config()
        self.refresh_objectives()
        self.sync_bg()

    def del_objective(self):
        sel = self.tree.selection()
        if not sel or not self.ask_code("Code pour supprimer l'objectif :"):
            return
        self.state.config["objectives"] = [o for o in self.state.config["objectives"]
                                           if o["id"] not in sel]
        self.state.touch_config()
        self.refresh_objectives()
        self.sync_bg()

    def set_code(self):
        if not self.ask_code("Code actuel :"):
            return
        c1 = simpledialog.askstring("Nouveau code", "Nouveau code (4 caractères min.) :",
                                    show="•", parent=self.root)
        if c1 is None:
            return
        if len(c1) < 4:
            return messagebox.showerror("AntiScroll", "4 caractères minimum", parent=self.root)
        c2 = simpledialog.askstring("Nouveau code", "Répète le code :", show="•", parent=self.root)
        if c1 != c2:
            return messagebox.showerror("AntiScroll", "Les codes ne correspondent pas", parent=self.root)
        self.state.config["unlock"] = core.make_unlock(c1)
        self.state.touch_config()
        self.refresh_code_info()
        self.sync_bg()

    def refresh_code_info(self):
        self.code_info.config(text="Code : défini ✔" if self.state.config.get("unlock")
                              else "Code : pas encore défini")

    def save_recheck(self):
        try:
            v = max(1, min(120, int(self.recheck.get())))
        except ValueError:
            return
        self.state.config.setdefault("settings", {})["app_recheck_min"] = v
        self.state.touch_config()
        self.sync_bg()

    def save_apps(self):
        names = [l.strip().lower() for l in self.apps_txt.get("1.0", "end").splitlines() if l.strip()]
        with self.state.lock:
            self.state.data["watched_apps"] = names
            self.state.save()

    def toggle_host(self):
        on = self.host_var.get()
        with self.state.lock:
            self.state.data["host_server"] = on
            self.state.save()
        if on:
            self.start_server()
            if not self.srv.get().strip():
                self.srv.insert(0, "http://127.0.0.1:47800")
        elif self.server_httpd:
            self.server_httpd.shutdown()
            self.server_httpd = None
        self.refresh_status()

    def start_server(self):
        if self.server_httpd:
            return
        try:
            import server
            data = os.path.join(core.APP_DIR, "server_data")
            self.server_httpd = server.run(data_dir=data)
            threading.Thread(target=self.server_httpd.serve_forever, daemon=True).start()
            self.host_info.config(text=f"Serveur actif (port 47800) - comptes dans {data}")
        except Exception as e:
            self.host_info.config(text=f"Impossible de lancer le serveur : {e}")

    def save_server_url(self):
        url = self.srv.get().strip().rstrip("/")
        if url and not url.startswith("http"):
            url = "http://" + url
        with self.state.lock:
            self.state.data["server_url"] = url
            self.state.save()

    def auth(self, kind):
        self.save_server_url()
        try:
            (self.api.login if kind == "login" else self.api.register)(self.u.get(), self.p.get())
        except core.ApiError as e:
            return messagebox.showerror("AntiScroll", str(e), parent=self.root)
        self.after_sync()
        self.build_account_box()

    def sync_now(self):
        self.save_server_url()
        try:
            self.api.sync()
            self.after_sync()
            messagebox.showinfo("AntiScroll", "Synchronisé ✔", parent=self.root)
        except core.ApiError as e:
            messagebox.showerror("AntiScroll", str(e), parent=self.root)

    def sync_bg(self):
        def run():
            try:
                if self.api.sync():
                    self.events.put(("synced", None))
            except core.ApiError:
                pass
        self.last_sync = time.time()
        threading.Thread(target=run, daemon=True).start()

    def after_sync(self):
        self.refresh_objectives()
        self.refresh_code_info()
        self.refresh_status()

    def change_username(self):
        new = simpledialog.askstring("Pseudo", "Nouveau pseudo :", parent=self.root)
        if new:
            try:
                self.api.change_username(new)
                self.build_account_box()
            except core.ApiError as e:
                messagebox.showerror("AntiScroll", str(e), parent=self.root)

    def change_password(self):
        old = simpledialog.askstring("Mot de passe", "Mot de passe actuel :", show="•", parent=self.root)
        if old is None:
            return
        new = simpledialog.askstring("Mot de passe", "Nouveau mot de passe :", show="•", parent=self.root)
        if new:
            try:
                self.api.change_password(old, new)
                messagebox.showinfo("AntiScroll", "Mot de passe changé ✔", parent=self.root)
            except core.ApiError as e:
                messagebox.showerror("AntiScroll", str(e), parent=self.root)

    def logout(self):
        self.api.logout()
        self.build_account_box()
        self.refresh_status()

    def delete_account(self):
        pw = simpledialog.askstring("Supprimer le compte",
                                    "Mot de passe du compte (action définitive) :",
                                    show="•", parent=self.root)
        if pw:
            try:
                self.api.delete_account(pw)
                self.build_account_box()
            except core.ApiError as e:
                messagebox.showerror("AntiScroll", str(e), parent=self.root)

    def install_autostart(self):
        script = os.path.abspath(__file__)
        frozen = getattr(sys, "frozen", False)
        try:
            if IS_WIN:
                folder = os.path.join(os.environ["APPDATA"], r"Microsoft\Windows\Start Menu\Programs\Startup")
                exe = sys.executable.replace("python.exe", "pythonw.exe")
                cmd = f'"{sys.executable}" --minimized' if frozen else f'"{exe}" "{script}" --minimized'
                with open(os.path.join(folder, "AntiScroll.bat"), "w") as f:
                    f.write(f"@echo off\nstart \"\" {cmd}\n")
            else:
                folder = os.path.expanduser("~/.config/autostart")
                os.makedirs(folder, exist_ok=True)
                cmd = f'"{sys.executable}" --minimized' if frozen else f'"{sys.executable}" "{script}" --minimized'
                with open(os.path.join(folder, "antiscroll.desktop"), "w") as f:
                    f.write("[Desktop Entry]\nType=Application\nName=AntiScroll\n"
                            f"Exec={cmd}\nX-GNOME-Autostart-enabled=true\n")
            messagebox.showinfo("AntiScroll", "AntiScroll se lancera au démarrage ✔", parent=self.root)
        except Exception as e:
            messagebox.showerror("AntiScroll", f"Erreur : {e}", parent=self.root)

    def refresh_status(self):
        parts = ["Extension : pont actif ✔" if self.bridge_ok else "Pont extension : port occupé ✖"]
        parts.append(f"Compte : {self.state.data['username']}" if self.state.data.get("token")
                     else "Hors ligne (pas de compte)")
        if self.server_httpd:
            parts.append("Serveur ✔")
        self.status.config(text="  •  ".join(parts))

    def test_black(self):
        end = dt.datetime.now() + dt.timedelta(seconds=15)
        self.show_overlay("test", "Test de l'écran noir",
                          "Tes programmes continuent derrière. Disparaît dans 15 s ou avec ton code.",
                          lambda code: core.check_unlock(code, self.state.config.get("unlock")),
                          countdown_to=end)

    def quit_app(self):
        if self.ask_code("Code pour quitter AntiScroll :"):
            self.root.destroy()

    # --------------------------- écran noir ------------------------------- #
    def show_overlay(self, kind, title, subtitle, on_code, extra_button=None, countdown_to=None):
        if self.overlay:
            if self.overlay_kind == kind:
                return
            if kind != "block":       # un blocage d'objectif passe avant tout
                return
            self.overlay.close()
        self.overlay_kind = kind
        self.overlay = BlackScreen(self, title, subtitle, on_code, extra_button, countdown_to)

    def overlay_closed(self, ov):
        if self.overlay is ov:
            self.overlay = None
            self.overlay_kind = None

    # ------------------------- boucle principale -------------------------- #
    def tick(self):
        now = dt.datetime.now()
        objs = self.state.config.get("objectives", [])

        for o, mins in self.warn.due(objs, now):
            toast(self.root, "AntiScroll", f"« {o['title']} » commence dans {mins} min.\n"
                                           f"Ton PC sera bloqué pendant {o['duration']} min.")

        blk = core.active_block(objs, now)
        if blk and blk[2] not in self.unlocked_blocks:
            o, end, key = blk

            def unlock(code, key=key):
                if core.check_unlock(code, self.state.config.get("unlock")):
                    self.unlocked_blocks.add(key)
                    return True
                return False
            self.show_overlay("block", f"🎯 {o['title']}",
                              f"Temps bloqué jusqu'à {end:%H:%M}. Tes programmes tournent toujours derrière.",
                              unlock, countdown_to=end)

        if self.state.data.get("token") and time.time() - self.last_sync > 300:
            self.sync_bg()
        self.root.after(5000, self.tick)

    def pump_events(self):
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "synced":
                    self.after_sync()
                elif kind == "app":
                    self.app_detected(payload)
        except queue.Empty:
            pass
        self.root.after(300, self.pump_events)

    # ---------------------- apps installées (TikTok...) -------------------- #
    def watch_apps(self):
        while True:
            time.sleep(3)
            if psutil is None or time.time() < self.app_ok_until:
                continue
            watched = set(self.state.data.get("watched_apps", []))
            found = []
            try:
                for p in psutil.process_iter(["name"]):
                    n = (p.info.get("name") or "").lower()
                    if n in watched:
                        found.append(n)
            except Exception:
                continue
            if found:
                self.events.put(("app", sorted(set(found))))

    def app_detected(self, names):
        if time.time() < self.app_ok_until:
            return

        def unlock(code):
            if core.check_unlock(code, self.state.config.get("unlock")):
                mins = self.state.config.get("settings", {}).get("app_recheck_min", 3)
                self.app_ok_until = time.time() + mins * 60
                return True
            return False

        def kill():
            for p in psutil.process_iter(["name"]):
                if (p.info.get("name") or "").lower() in names:
                    try:
                        p.terminate()
                    except Exception:
                        pass
            self.app_ok_until = time.time() + 5
        mins = self.state.config.get("settings", {}).get("app_recheck_min", 3)
        self.show_overlay("app", "Doomscroll détecté",
                          f"{', '.join(names)} est ouvert. Entre ton code pour {mins} min de plus.",
                          unlock, extra_button=("Fermer l'app", kill))

    # ------------------------ pont pour l'extension ------------------------ #
    def bridge_status(self):
        now = dt.datetime.now()
        blk = core.active_block(self.state.config.get("objectives", []), now)
        blocked = bool(blk and blk[2] not in self.unlocked_blocks)
        return {"blocked": blocked,
                "title": blk[0]["title"] if blocked else "",
                "unlock": self.state.config.get("unlock")}

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App(minimized="--minimized" in sys.argv).run()
