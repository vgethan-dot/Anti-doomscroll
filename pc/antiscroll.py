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
- Mode dev (Dev / Dev Roblox) : écran vraiment éteint, PC qui ne se met pas
  en veille, pour que Claude puisse continuer à bosser dessus.
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
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "server"))

import core  # noqa: E402
import devmode  # noqa: E402

try:
    import psutil  # facultatif mais recommandé
except ImportError:
    psutil = None

IS_WIN = platform.system() == "Windows"
BRIDGE_PORT = 47811
DAYS = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]


# --------------------------------------------------------------------------- #
# Thème moderne : blanc + bleu cyan
# --------------------------------------------------------------------------- #
C = {
    "bg": "#f4f9fb",         # fond de la fenêtre
    "card": "#ffffff",       # cartes / champs
    "text": "#0f172a",       # texte principal
    "muted": "#64748b",      # texte secondaire
    "border": "#dbe7ec",     # bordures
    "cyan": "#06b6d4",       # couleur principale
    "cyan_dark": "#0891b2",  # survol / appui
    "cyan_soft": "#e0f7fb",  # fond léger cyan
    "red": "#ef4444",
    "green": "#10b981",
}
FONT = "Segoe UI" if IS_WIN else "Helvetica"


def apply_theme(root):
    """Applique le thème blanc + cyan à toute l'app (widgets ttk)."""
    global FONT
    import tkinter.font as tkfont
    fams = set(tkfont.families(root))
    for fam in ("Segoe UI", "Inter", "Ubuntu", "Cantarell", "Noto Sans", "DejaVu Sans"):
        if fam in fams:
            FONT = fam
            break
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
        try:
            tkfont.nametofont(name).configure(family=FONT, size=10)
        except tk.TclError:
            pass

    root.configure(bg=C["bg"])
    st = ttk.Style(root)
    st.theme_use("clam")
    st.configure(".", background=C["bg"], foreground=C["text"], font=(FONT, 10),
                 bordercolor=C["border"], lightcolor=C["border"], darkcolor=C["border"],
                 troughcolor=C["cyan_soft"], focuscolor=C["cyan"],
                 selectbackground=C["cyan"], selectforeground="white")
    st.configure("TFrame", background=C["bg"])
    st.configure("Card.TFrame", background=C["card"])
    st.configure("Header.TFrame", background=C["cyan"])
    st.configure("TLabel", background=C["bg"], foreground=C["text"])
    st.configure("Card.TLabel", background=C["card"])
    st.configure("Muted.TLabel", foreground=C["muted"])
    st.configure("CardTitle.TLabel", background=C["card"], font=(FONT, 12, "bold"))
    st.configure("Header.TLabel", background=C["cyan"], foreground="white",
                 font=(FONT, 17, "bold"))
    st.configure("HeaderSub.TLabel", background=C["cyan"], foreground="#e6fbff",
                 font=(FONT, 10))

    # Boutons : blancs avec bordure, et "Accent" = cyan plein
    st.configure("TButton", background=C["cyan_soft"], foreground=C["cyan_dark"],
                 bordercolor=C["cyan_soft"], lightcolor=C["cyan_soft"], darkcolor=C["cyan_soft"],
                 padding=(14, 7), relief="flat", borderwidth=1, focusthickness=0,
                 font=(FONT, 10, "bold"))
    st.map("TButton",
           background=[("pressed", "#c6eef6"), ("active", "#c6eef6")],
           bordercolor=[("active", "#c6eef6"), ("focus", C["cyan"])],
           foreground=[("disabled", C["muted"])])
    st.configure("Accent.TButton", background=C["cyan"], foreground="white",
                 bordercolor=C["cyan"], lightcolor=C["cyan"], darkcolor=C["cyan"],
                 font=(FONT, 10, "bold"))
    st.map("Accent.TButton",
           background=[("pressed", C["cyan_dark"]), ("active", C["cyan_dark"])],
           bordercolor=[("active", C["cyan_dark"])],
           lightcolor=[("active", C["cyan_dark"])], darkcolor=[("active", C["cyan_dark"])])
    st.configure("Danger.TButton", foreground=C["red"], background="#fdecec",
                 bordercolor="#fdecec", lightcolor="#fdecec", darkcolor="#fdecec")
    st.map("Danger.TButton", background=[("pressed", "#fbd5d5"), ("active", "#fbd5d5")],
           bordercolor=[("active", "#fbd5d5")])

    # Onglets
    st.configure("TNotebook", background=C["bg"], borderwidth=0, tabmargins=(0, 6, 0, 0))
    st.configure("TNotebook.Tab", background=C["bg"], foreground=C["muted"],
                 padding=(16, 8), borderwidth=0, font=(FONT, 10, "bold"))
    st.map("TNotebook.Tab",
           background=[("selected", C["card"]), ("active", C["cyan_soft"])],
           foreground=[("selected", C["cyan_dark"]), ("active", C["text"])],
           lightcolor=[("selected", C["cyan"])])

    # Champs
    for w in ("TEntry", "TSpinbox"):
        st.configure(w, fieldbackground=C["card"], foreground=C["text"], padding=6,
                     insertcolor=C["text"], arrowcolor=C["cyan_dark"])
        st.map(w, bordercolor=[("focus", C["cyan"])], lightcolor=[("focus", C["cyan"])])
    st.configure("TCheckbutton", background=C["bg"], indicatorbackground=C["card"],
                 indicatorforeground="white")
    st.map("TCheckbutton",
           indicatorbackground=[("selected", C["cyan"]), ("active", C["cyan_soft"])],
           background=[("active", C["bg"])])
    st.configure("Card.TCheckbutton", background=C["card"])
    st.map("Card.TCheckbutton", background=[("active", C["card"])])
    st.configure("TSeparator", background=C["border"])

    # Tableau des objectifs
    st.configure("Treeview", background=C["card"], fieldbackground=C["card"],
                 foreground=C["text"], rowheight=30, borderwidth=0)
    st.map("Treeview", background=[("selected", C["cyan_soft"])],
           foreground=[("selected", C["cyan_dark"])])
    st.configure("Treeview.Heading", background=C["card"], foreground=C["muted"],
                 font=(FONT, 9, "bold"), relief="flat", padding=(8, 6))
    st.map("Treeview.Heading", background=[("active", C["cyan_soft"])])


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
        # Fond noir opaque (fonctionnel), carte blanche au centre pour le code
        box = tk.Frame(main, bg=C["card"], padx=44, pady=34,
                       highlightthickness=3, highlightbackground=C["cyan"])
        box.place(relx=0.5, rely=0.45, anchor="center")
        tk.Label(box, text="AntiScroll", fg=C["cyan_dark"], bg=C["card"],
                 font=(FONT, 11, "bold")).pack(pady=(0, 6))
        tk.Label(box, text=title, fg=C["text"], bg=C["card"],
                 font=(FONT, 26, "bold")).pack(pady=(0, 8))
        tk.Label(box, text=subtitle, fg=C["muted"], bg=C["card"], wraplength=560,
                 font=(FONT, 13), justify="center").pack(pady=(0, 16))
        self.timer_lbl = tk.Label(box, text="", fg=C["cyan_dark"], bg=C["card"],
                                  font=(FONT, 20, "bold"))
        if countdown_to:
            self.timer_lbl.pack(pady=(0, 12))

        has_code = bool(app.state.config.get("unlock"))
        self.entry = tk.Entry(box, show="•", font=(FONT, 18), width=16,
                              justify="center", bg=C["bg"], fg=C["text"],
                              insertbackground=C["text"], relief="flat",
                              highlightthickness=2, highlightbackground=C["border"],
                              highlightcolor=C["cyan"])
        self.msg = tk.Label(box, text="", fg=C["red"], bg=C["card"], font=(FONT, 11))

        def cyan_button(text):
            return tk.Button(box, text=text, command=self.submit, font=(FONT, 13, "bold"),
                             bg=C["cyan"], fg="white", activebackground=C["cyan_dark"],
                             activeforeground="white", relief="flat", bd=0,
                             cursor="hand2", padx=28, pady=9)

        if has_code:
            tk.Label(box, text="Code de déblocage", fg=C["muted"], bg=C["card"],
                     font=(FONT, 11)).pack()
            self.entry.pack(ipady=8, pady=8)
            self.entry.bind("<Return>", lambda e: self.submit())
            cyan_button("Débloquer").pack(pady=(6, 4))
        else:
            tk.Label(box, text="(Aucun code choisi : crée-en un dans l'app AntiScroll)",
                     fg=C["muted"], bg=C["card"], font=(FONT, 11)).pack()
            cyan_button("Continuer").pack(pady=(10, 4))
        self.msg.pack()
        if extra_button:
            label, fn = extra_button
            tk.Button(box, text=label, command=lambda: (fn(), self.close()),
                      bg=C["card"], fg=C["muted"], activebackground=C["bg"],
                      activeforeground=C["text"], relief="flat", bd=0, cursor="hand2",
                      highlightthickness=0, font=(FONT, 10, "underline"),
                      padx=14, pady=4).pack(pady=(14, 0))
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


class PlainBlack:
    """Secours si le PC refuse d'éteindre l'écran : du noir pur, sans rien
    dessus (sur un écran OLED, un pixel noir est vraiment éteint).
    Un clic ou une touche le fait disparaître."""

    def __init__(self, app):
        self.windows = []
        for x, y, w, h in list_monitors(app.root):
            win = tk.Toplevel(app.root)
            win.configure(bg="black", cursor="none")
            win.geometry(f"{w}x{h}+{x}+{y}")
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            for ev in ("<Button>", "<Key>", "<Motion>"):
                win.bind(ev, lambda e: self.close())
            self.windows.append(win)
        if self.windows:
            self.windows[0].focus_force()

    def close(self):
        for w in self.windows:
            try:
                w.destroy()
            except tk.TclError:
                pass
        self.windows = []


# --------------------------------------------------------------------------- #
# Petite notification en haut à droite
# --------------------------------------------------------------------------- #
def toast(root, title, text, seconds=10):
    if not IS_WIN and shutil.which("notify-send"):
        subprocess.Popen(["notify-send", "-u", "critical", title, text])
    t = tk.Toplevel(root)
    t.overrideredirect(True)
    t.attributes("-topmost", True)
    t.configure(bg=C["card"], highlightthickness=1, highlightbackground=C["border"])
    tk.Frame(t, bg=C["cyan"], width=6).pack(side="left", fill="y")
    tk.Label(t, text=title, fg=C["text"], bg=C["card"],
             font=(FONT, 13, "bold")).pack(padx=16, pady=(12, 2), anchor="w")
    tk.Label(t, text=text, fg=C["muted"], bg=C["card"], wraplength=320, font=(FONT, 10),
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
        # Mode dev
        self.dev_mode = None            # None, "dev" ou "roblox"
        self.dev_sleep = devmode.SleepBlocker()
        self.dev_dpms = devmode.X11Dpms()
        self.dev_watchdog = devmode.Watchdog()
        self.dev_screen_off = False     # écran déjà éteint depuis la dernière activité
        self.dev_black = None
        self.dev_job = None
        self.dev_busy = False

        self.root = tk.Tk()
        self.root.title("AntiScroll")
        self.root.geometry("760x680")
        self.root.minsize(640, 520)
        apply_theme(self.root)
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
        # Le PC a redémarré pendant un mode dev (ex. mise à jour) : on reprend.
        if self.state.data.get("dev_mode") in devmode.MODES:
            self.root.after(20000, lambda: self.start_dev(self.state.data["dev_mode"], resumed=True))

    # ----------------------------- interface ------------------------------ #
    def build_ui(self):
        head = ttk.Frame(self.root, style="Header.TFrame", padding=(20, 14))
        head.pack(fill="x")
        ttk.Label(head, text="AntiScroll", style="Header.TLabel").pack(anchor="w")
        ttk.Label(head, text="Moins de scroll, plus de temps pour toi.",
                  style="HeaderSub.TLabel").pack(anchor="w")

        nb = ttk.Notebook(self.root)
        nb.pack(fill="both", expand=True, padx=14, pady=(8, 8))
        self.tab_objectives(nb)
        self.tab_code(nb)
        self.tab_account(nb)
        self.tab_apps(nb)
        self.tab_dev(nb)

        bar = ttk.Frame(self.root)
        bar.pack(fill="x", padx=14, pady=(0, 12))
        self.status = ttk.Label(bar, text="", style="Muted.TLabel")
        self.status.pack(side="left")
        ttk.Button(bar, text="Quitter", command=self.quit_app).pack(side="right")
        ttk.Button(bar, text="Tester l'écran noir", style="Accent.TButton",
                   command=self.test_black).pack(side="right", padx=6)

    def tab_objectives(self, nb):
        f = ttk.Frame(nb, padding=18, style="Card.TFrame")
        nb.add(f, text="Objectifs")
        cols = ("titre", "heure", "duree", "jours")
        self.tree = ttk.Treeview(f, columns=cols, show="headings", height=8)
        for c, t, w in zip(cols, ("Objectif", "Heure", "Durée", "Jours"), (220, 70, 80, 200)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.pack(fill="both", expand=True)

        form = ttk.Frame(f, style="Card.TFrame")
        form.pack(fill="x", pady=8)
        ttk.Label(form, style="Card.TLabel", text="Objectif").grid(row=0, column=0, sticky="w")
        self.o_title = ttk.Entry(form, width=24)
        self.o_title.grid(row=0, column=1, sticky="w")
        ttk.Label(form, style="Card.TLabel", text="Heure (HH:MM)").grid(row=0, column=2, padx=(10, 0))
        self.o_start = ttk.Entry(form, width=7)
        self.o_start.grid(row=0, column=3)
        ttk.Label(form, style="Card.TLabel", text="Durée (min)").grid(row=0, column=4, padx=(10, 0))
        self.o_dur = ttk.Entry(form, width=6)
        self.o_dur.grid(row=0, column=5)
        days = ttk.Frame(form, style="Card.TFrame")
        days.grid(row=1, column=0, columnspan=6, sticky="w", pady=6)
        ttk.Label(days, style="Card.TLabel", text="Jours (aucun = tous) :").pack(side="left")
        self.o_days = []
        for d in DAYS:
            v = tk.BooleanVar()
            ttk.Checkbutton(days, style="Card.TCheckbutton", text=d, variable=v).pack(side="left")
            self.o_days.append(v)

        btns = ttk.Frame(f, style="Card.TFrame")
        btns.pack(fill="x")
        ttk.Button(btns, text="Ajouter", style="Accent.TButton", command=self.add_objective).pack(side="left")
        ttk.Button(btns, text="Supprimer (code requis)", style="Danger.TButton", command=self.del_objective).pack(side="left", padx=6)
        self.refresh_objectives()

    def tab_code(self, nb):
        f = ttk.Frame(nb, padding=18, style="Card.TFrame")
        nb.add(f, text="Code")
        ttk.Label(f, style="Card.TLabel", text="Ce code est demandé à chaque vidéo (Shorts, Reels, TikTok...),\n"
                          "pour débloquer un objectif, supprimer un objectif ou quitter l'app.",
                  justify="left").pack(anchor="w", pady=(0, 12))
        self.code_info = ttk.Label(f, style="Card.TLabel", text="")
        self.code_info.pack(anchor="w", pady=(0, 8))
        ttk.Button(f, text="Choisir / changer le code", style="Accent.TButton", command=self.set_code).pack(anchor="w")
        ttk.Separator(f).pack(fill="x", pady=16)
        ttk.Label(f, style="Card.TLabel", text="Redemander le code pour les apps PC toutes les (minutes) :").pack(anchor="w")
        self.recheck = ttk.Spinbox(f, from_=1, to=120, width=6)
        self.recheck.set(self.state.config.get("settings", {}).get("app_recheck_min", 3))
        self.recheck.pack(anchor="w", pady=4)
        ttk.Button(f, text="Enregistrer", style="Accent.TButton", command=self.save_recheck).pack(anchor="w")
        self.refresh_code_info()

    def tab_account(self, nb):
        f = ttk.Frame(nb, padding=18, style="Card.TFrame")
        nb.add(f, text="Compte")
        self.host_var = tk.BooleanVar(value=self.state.data.get("host_server", False))
        ttk.Checkbutton(f, style="Card.TCheckbutton", text="Ce PC héberge le serveur (les comptes sont stockés ici)",
                        variable=self.host_var, command=self.toggle_host).pack(anchor="w")
        self.host_info = ttk.Label(f, style="Card.TLabel", text="", foreground=C["muted"])
        self.host_info.pack(anchor="w", pady=(0, 10))

        ttk.Label(f, style="Card.TLabel", text="Adresse du serveur (ex. http://100.x.y.z:47800)").pack(anchor="w")
        self.srv = ttk.Entry(f, width=40)
        self.srv.insert(0, self.state.data.get("server_url", ""))
        self.srv.pack(anchor="w", pady=(0, 10))

        self.acc_box = ttk.Frame(f, style="Card.TFrame")
        self.acc_box.pack(fill="x")
        self.build_account_box()

    def build_account_box(self):
        for w in self.acc_box.winfo_children():
            w.destroy()
        f = self.acc_box
        if self.state.data.get("token"):
            ttk.Label(f, style="CardTitle.TLabel",
                      text=f"Connecté : {self.state.data['username']}").pack(anchor="w", pady=(0, 8))
            row = ttk.Frame(f, style="Card.TFrame")
            row.pack(anchor="w")
            ttk.Button(row, text="Synchroniser", style="Accent.TButton", command=self.sync_now).pack(side="left")
            ttk.Button(row, text="Changer de pseudo", command=self.change_username).pack(side="left", padx=4)
            ttk.Button(row, text="Changer le mot de passe", command=self.change_password).pack(side="left")
            row2 = ttk.Frame(f, style="Card.TFrame")
            row2.pack(anchor="w", pady=8)
            ttk.Button(row2, text="Se déconnecter", command=self.logout).pack(side="left")
            ttk.Button(row2, text="Supprimer le compte", style="Danger.TButton", command=self.delete_account).pack(side="left", padx=4)
        else:
            ttk.Label(f, style="Card.TLabel", text="Pseudo").pack(anchor="w")
            self.u = ttk.Entry(f, width=24)
            self.u.pack(anchor="w")
            ttk.Label(f, style="Card.TLabel", text="Mot de passe du compte").pack(anchor="w")
            self.p = ttk.Entry(f, width=24, show="•")
            self.p.pack(anchor="w")
            row = ttk.Frame(f, style="Card.TFrame")
            row.pack(anchor="w", pady=8)
            ttk.Button(row, text="Se connecter", style="Accent.TButton", command=lambda: self.auth("login")).pack(side="left")
            ttk.Button(row, text="Créer un compte", command=lambda: self.auth("register")).pack(side="left", padx=6)
            ttk.Label(f, style="Card.TLabel", text="Sans compte, l'app marche quand même (sans synchro).",
                      foreground=C["muted"]).pack(anchor="w")

    def tab_apps(self, nb):
        f = ttk.Frame(nb, padding=18, style="Card.TFrame")
        nb.add(f, text="Apps PC")
        ttk.Label(f, style="Card.TLabel", text="Noms de processus surveillés (un par ligne).\n"
                          "Quand l'un d'eux tourne : écran noir + code.").pack(anchor="w")
        self.apps_txt = tk.Text(f, height=12, width=40, bg=C["bg"], fg=C["text"],
                                insertbackground=C["text"], relief="flat", font=(FONT, 10),
                                highlightthickness=1, highlightbackground=C["border"],
                                highlightcolor=C["cyan"], padx=8, pady=6)
        self.apps_txt.insert("1.0", "\n".join(self.state.data.get("watched_apps", [])))
        self.apps_txt.pack(anchor="w", pady=6)
        ttk.Button(f, text="Enregistrer", style="Accent.TButton", command=self.save_apps).pack(anchor="w")
        ttk.Button(f, text="Lancer AntiScroll au démarrage du PC",
                   command=self.install_autostart).pack(anchor="w", pady=(16, 0))
        if psutil is None:
            ttk.Label(f, style="Card.TLabel", text="⚠ Installe psutil (pip install psutil) pour surveiller les apps.",
                      foreground=C["red"]).pack(anchor="w", pady=8)

    def tab_dev(self, nb):
        f = ttk.Frame(nb, padding=18, style="Card.TFrame")
        nb.add(f, text="Mode dev")
        ttk.Label(f, style="CardTitle.TLabel", text="Laisse ton PC travailler pendant que tu n'es pas là").pack(anchor="w")
        ttk.Label(f, style="Card.TLabel", foreground=C["muted"], justify="left", text=(
            "L'écran s'éteint vraiment, le PC ne se met jamais en veille et reste au calme.\n"
            "Claude peut continuer à coder dessus quand tu lui écris depuis ton téléphone.\n"
            "Bouge la souris pour rallumer l'écran. Le blocage anti-scroll reste actif.")
        ).pack(anchor="w", pady=(4, 12))

        row = ttk.Frame(f, style="Card.TFrame")
        row.pack(anchor="w")
        ttk.Button(row, text="Lancer « Dev »", style="Accent.TButton",
                   command=lambda: self.start_dev("dev")).pack(side="left")
        ttk.Button(row, text="Lancer « Dev Roblox »", style="Accent.TButton",
                   command=lambda: self.start_dev("roblox")).pack(side="left", padx=6)
        ttk.Button(row, text="Arrêter", command=self.stop_dev).pack(side="left")
        self.dev_info = ttk.Label(f, style="Card.TLabel", text="Mode dev : arrêté", foreground=C["muted"])
        self.dev_info.pack(anchor="w", pady=(8, 0))

        ttk.Separator(f).pack(fill="x", pady=14)
        ttk.Label(f, style="Card.TLabel", text="Rééteindre l'écran après (minutes sans souris ni clavier) :").pack(anchor="w")
        self.dev_idle = ttk.Spinbox(f, from_=1, to=60, width=6, command=self.save_dev_settings)
        self.dev_idle.set(self.state.data.get("dev_idle_min", 2))
        self.dev_idle.pack(anchor="w", pady=4)

        ttk.Label(f, style="CardTitle.TLabel", text="Apps du mode Dev Roblox (relancées si elles se ferment)").pack(anchor="w", pady=(12, 4))
        saved = self.state.data.get("dev_apps", {})
        self.dev_cmd = {}
        grid = ttk.Frame(f, style="Card.TFrame")
        grid.pack(fill="x")
        for i, (key, name, _p) in enumerate(devmode.DEV_APPS):
            ttk.Label(grid, style="Card.TLabel", text=name).grid(row=i, column=0, sticky="w", padx=(0, 8))
            e = ttk.Entry(grid, width=46)
            e.insert(0, saved.get(key) or devmode.default_command(key))
            e.grid(row=i, column=1, sticky="we", pady=2)
            ttk.Button(grid, text="Choisir…",
                       command=lambda k=key: self.pick_dev_app(k)).grid(row=i, column=2, padx=(6, 0))
            self.dev_cmd[key] = e
        grid.columnconfigure(1, weight=1)
        ttk.Button(f, text="Enregistrer", style="Accent.TButton",
                   command=self.save_dev_settings).pack(anchor="w", pady=(8, 0))
        if psutil is None:
            ttk.Label(f, style="Card.TLabel", foreground=C["red"],
                      text="⚠ Installe psutil (pip install psutil) pour relancer les apps.").pack(anchor="w", pady=6)

    def pick_dev_app(self, key):
        path = filedialog.askopenfilename(parent=self.root, title="Choisis le programme")
        if path:
            e = self.dev_cmd[key]
            e.delete(0, "end")
            e.insert(0, f'"{path}"' if " " in path and not IS_WIN else path)
            self.save_dev_settings()

    def save_dev_settings(self):
        try:
            idle = max(1, min(60, int(self.dev_idle.get())))
        except ValueError:
            idle = 2
        with self.state.lock:
            self.state.data["dev_idle_min"] = idle
            self.state.data["dev_apps"] = {k: e.get().strip() for k, e in self.dev_cmd.items()}
            self.state.save()

    # ------------------------------ mode dev ------------------------------ #
    def start_dev(self, mode, resumed=False):
        if mode not in devmode.MODES:
            return
        self.save_dev_settings()
        if mode == "roblox":
            missing = [n for k, n, _p in devmode.DEV_APPS if not self.dev_cmd[k].get().strip()]
            if missing and not resumed:
                messagebox.showwarning("AntiScroll", "Je n'ai pas trouvé : " + ", ".join(missing)
                                       + ".\nClique sur « Choisir… » pour les indiquer. "
                                       "Le mode démarre quand même avec les autres.", parent=self.root)
        was_on = self.dev_mode is not None
        self.dev_mode = mode
        with self.state.lock:
            self.state.data["dev_mode"] = mode
            self.state.save()

        ok_sleep = self.dev_sleep.start()
        devmode.set_low_priority(True)
        # X11 sans mesure d'inactivité : X éteint l'écran tout seul après N min
        if devmode.idle_seconds() is None:
            self.dev_dpms.set_timeout(self.state.data.get("dev_idle_min", 2) * 60)
        self.dev_watchdog = devmode.Watchdog()

        msg = f"Mode {devmode.MODES[mode]} actif"
        if not ok_sleep:
            msg += " (⚠ impossible d'empêcher la veille : règle la veille sur « Jamais »)"
        self.dev_info.config(text=msg + ". L'écran s'éteint dans 10 s…", foreground=C["cyan_dark"])
        self.refresh_status()
        if self.dev_job is None:
            self.dev_job = self.root.after(3000, self.dev_tick)
        if not was_on or resumed:
            self.root.after(10000, self.dev_turn_screen_off)
        self.root.after(1500, self.root.iconify)    # fenêtre réduite = rien à dessiner

    def stop_dev(self):
        if self.dev_mode is None:
            return
        self.dev_mode = None
        with self.state.lock:
            self.state.data["dev_mode"] = None
            self.state.save()
        if self.dev_job is not None:
            self.root.after_cancel(self.dev_job)
            self.dev_job = None
        self.dev_sleep.stop()
        self.dev_dpms.restore()
        devmode.set_low_priority(False)
        if self.dev_black:
            self.dev_black.close()
            self.dev_black = None
        devmode.screen_on()
        self.dev_info.config(text="Mode dev : arrêté (les apps lancées restent ouvertes)",
                             foreground=C["muted"])
        self.refresh_status()

    def dev_turn_screen_off(self):
        if self.dev_mode is None:
            return
        self.dev_screen_off = True
        self.dev_info.config(text=f"Mode {devmode.MODES[self.dev_mode]} actif, écran éteint.",
                             foreground=C["cyan_dark"])
        if not devmode.screen_off() and not (self.dev_black and self.dev_black.windows):
            self.dev_black = PlainBlack(self)

    def dev_tick(self):
        """Toutes les 30 s seulement : presque rien à faire, donc presque rien consommé."""
        self.dev_job = None
        if self.dev_mode is None:
            return
        idle = devmode.idle_seconds()
        if idle is not None:
            if idle < 30:
                self.dev_screen_off = False          # quelqu'un utilise le PC
            elif not self.dev_screen_off and idle >= self.state.data.get("dev_idle_min", 2) * 60:
                self.dev_turn_screen_off()
        if self.dev_mode == "roblox" and not self.dev_busy:
            cmds = self.state.data.get("dev_apps", {})

            def run():
                try:
                    started = self.dev_watchdog.check(cmds)
                    if started:
                        self.events.put(("dev_started", started))
                finally:
                    self.dev_busy = False
            self.dev_busy = True
            threading.Thread(target=run, daemon=True).start()
        self.dev_job = self.root.after(30000, self.dev_tick)

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
        if self.dev_mode:
            parts.append(f"Mode {devmode.MODES[self.dev_mode]} ✔")
        self.status.config(text="  •  ".join(parts))

    def test_black(self):
        end = dt.datetime.now() + dt.timedelta(seconds=15)
        self.show_overlay("test", "Test de l'écran noir",
                          "Tes programmes continuent derrière. Disparaît dans 15 s ou avec ton code.",
                          lambda code: core.check_unlock(code, self.state.config.get("unlock")),
                          countdown_to=end)

    def quit_app(self):
        if self.ask_code("Code pour quitter AntiScroll :"):
            self.stop_dev()        # rend la veille normale au PC
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
                elif kind == "dev_started":
                    names = {k: n for k, n, _p in devmode.DEV_APPS}
                    self.dev_info.config(text="Relancé : " + ", ".join(names[k] for k in payload)
                                         + f" ({time.strftime('%H:%M')})")
        except queue.Empty:
            pass
        self.root.after(300, self.pump_events)

    # ---------------------- apps installées (TikTok...) -------------------- #
    def watch_apps(self):
        while True:
            time.sleep(10 if self.dev_mode else 3)   # plus calme en mode dev
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
