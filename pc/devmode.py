"""
Mode dev : laisser le PC allumé, écran ÉTEINT, au calme, pour que Claude
puisse continuer à travailler dessus pendant que tu es sur ton téléphone.

Deux modes :
- "dev"    : écran éteint + PC qui ne se met pas en veille + basse conso.
- "roblox" : pareil, et en plus Roblox Studio, Claude et Blender sont lancés
             puis relancés automatiquement s'ils se ferment.

Rien ici n'a besoin d'être admin. Tout est réversible (stop()).
"""
import glob
import os
import platform
import shlex
import shutil
import subprocess
import time

try:
    import psutil
except ImportError:
    psutil = None

IS_WIN = platform.system() == "Windows"
MODES = {"dev": "Dev", "roblox": "Dev Roblox"}


def _run(cmd, timeout=5):
    """Lance une commande courte. Renvoie (ok, sortie)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout or "") + (r.stderr or "")
    except Exception as e:
        return False, str(e)


def _desktop():
    return (os.environ.get("XDG_CURRENT_DESKTOP", "") + " "
            + os.environ.get("DESKTOP_SESSION", "")).lower()


def _wayland():
    return bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE", "").lower() == "wayland"


# --------------------------------------------------------------------------- #
# Écran : vraiment l'éteindre (pas juste une fenêtre noire)
# --------------------------------------------------------------------------- #
def screen_off():
    """Éteint l'écran. Le PC continue de tourner.
    L'écran se rallume tout seul dès que tu bouges la souris ou tapes une touche.
    Renvoie True si une méthode a marché, False sinon."""
    if IS_WIN:
        try:
            import ctypes
            # HWND_BROADCAST, WM_SYSCOMMAND, SC_MONITORPOWER, 2 = éteint
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, 2)
            return True
        except Exception:
            return False

    desk = _desktop()
    if _wayland():
        if "gnome" in desk or "ubuntu" in desk:
            ok, _ = _run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.DisplayConfig",
                          "--object-path", "/org/gnome/Mutter/DisplayConfig",
                          "--method", "org.freedesktop.DBus.Properties.Set",
                          "org.gnome.Mutter.DisplayConfig", "PowerSaveMode", "<int32 3>"])
            if ok:
                return True
        if shutil.which("kscreen-doctor"):
            ok, _ = _run(["kscreen-doctor", "--dpms", "off"])
            if ok:
                return True
        if shutil.which("wlopm"):
            ok, _ = _run(["wlopm", "--off", "*"])
            if ok:
                return True
    if shutil.which("xset") and os.environ.get("DISPLAY"):
        ok, _ = _run(["xset", "dpms", "force", "off"])
        if ok:
            return True
    return False


def screen_on():
    if IS_WIN:
        try:
            import ctypes
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x0112, 0xF170, -1)
            # petit mouvement de souris "virtuel" de 0 pixel pour être sûr
            ctypes.windll.user32.mouse_event(0x0001, 0, 0, 0, 0)
        except Exception:
            pass
        return
    if _wayland():
        _run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.DisplayConfig",
              "--object-path", "/org/gnome/Mutter/DisplayConfig",
              "--method", "org.freedesktop.DBus.Properties.Set",
              "org.gnome.Mutter.DisplayConfig", "PowerSaveMode", "<int32 0>"])
        if shutil.which("kscreen-doctor"):
            _run(["kscreen-doctor", "--dpms", "on"])
        if shutil.which("wlopm"):
            _run(["wlopm", "--on", "*"])
    if shutil.which("xset") and os.environ.get("DISPLAY"):
        _run(["xset", "dpms", "force", "on"])


def idle_seconds():
    """Depuis combien de secondes personne n'a touché souris/clavier.
    None si on ne sait pas le mesurer sur ce PC."""
    if IS_WIN:
        try:
            import ctypes
            from ctypes import wintypes

            class LASTINPUTINFO(ctypes.Structure):
                _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]
            li = LASTINPUTINFO()
            li.cbSize = ctypes.sizeof(li)
            if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(li)):
                now = ctypes.windll.kernel32.GetTickCount() & 0xFFFFFFFF
                return ((now - li.dwTime) & 0xFFFFFFFF) / 1000.0
        except Exception:
            pass
        return None
    if _wayland() and shutil.which("gdbus"):
        ok, out = _run(["gdbus", "call", "--session", "--dest", "org.gnome.Mutter.IdleMonitor",
                        "--object-path", "/org/gnome/Mutter/IdleMonitor/Core",
                        "--method", "org.gnome.Mutter.IdleMonitor.GetIdletime"])
        if ok:                                   # "(uint64 12345,)"
            try:
                return int(out.split()[1].rstrip(",)")) / 1000.0
            except (IndexError, ValueError):
                pass
    if shutil.which("xprintidle") and os.environ.get("DISPLAY"):
        ok, out = _run(["xprintidle"])
        if ok:
            try:
                return int(out.strip()) / 1000.0
            except ValueError:
                pass
    return None


class X11Dpms:
    """Sur X11 sans moyen de mesurer l'inactivité, on demande à X d'éteindre
    l'écran lui-même après N secondes, puis on remet les anciens réglages."""

    def __init__(self):
        self.saved = None

    def set_timeout(self, seconds):
        if IS_WIN or not shutil.which("xset") or not os.environ.get("DISPLAY"):
            return
        ok, out = _run(["xset", "q"])
        if ok and self.saved is None:
            enabled = "DPMS is Enabled" in out
            vals = [0, 0, 0]
            for line in out.splitlines():
                if "Standby:" in line and "Off:" in line:
                    try:
                        p = line.split()
                        vals = [int(p[1]), int(p[3]), int(p[5])]
                    except (IndexError, ValueError):
                        pass
            self.saved = (enabled, vals)
        s = str(int(seconds))
        _run(["xset", "+dpms"])
        _run(["xset", "dpms", s, s, s])

    def restore(self):
        if self.saved is None:
            return
        enabled, vals = self.saved
        _run(["xset", "dpms"] + [str(v) for v in vals])
        _run(["xset", "+dpms" if enabled else "-dpms"])
        self.saved = None


# --------------------------------------------------------------------------- #
# Empêcher la mise en veille / hibernation (l'écran, lui, peut s'éteindre)
# --------------------------------------------------------------------------- #
class SleepBlocker:
    ES_CONTINUOUS = 0x80000000
    ES_SYSTEM_REQUIRED = 0x00000001

    def __init__(self):
        self.procs = []
        self.active = False

    def start(self):
        """À appeler depuis le thread principal (Windows retient le thread)."""
        if self.active:
            return True
        ok = False
        if IS_WIN:
            try:
                import ctypes
                # Pas ES_DISPLAY_REQUIRED : on VEUT que l'écran puisse s'éteindre.
                ok = bool(ctypes.windll.kernel32.SetThreadExecutionState(
                    self.ES_CONTINUOUS | self.ES_SYSTEM_REQUIRED))
            except Exception:
                ok = False
        else:
            why = "AntiScroll mode dev : Claude travaille sur ce PC"
            if shutil.which("systemd-inhibit"):
                # sleep = veille + hibernation ; handle-lid-switch = rabattre
                # l'écran d'un portable ne le met pas en veille.
                for what in ("sleep:handle-lid-switch", "sleep"):
                    p = self._spawn(["systemd-inhibit", f"--what={what}", "--who=AntiScroll",
                                     f"--why={why}", "--mode=block", "cat"])
                    if p:
                        ok = True
                        break
            # GNOME : sa propre "mise en veille automatique"
            if shutil.which("gnome-session-inhibit"):
                p = self._spawn(["gnome-session-inhibit", "--inhibit", "suspend",
                                 "--reason", why, "cat"])
                ok = ok or bool(p)
        self.active = ok
        return ok

    def _spawn(self, cmd):
        # La commande finale est "cat" qui lit un tuyau ouvert par AntiScroll :
        # si AntiScroll s'arrête (même en plantant), le tuyau se ferme, cat
        # s'arrête et le PC retrouve sa veille normale. Pas de blocage oublié.
        try:
            p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 stdin=subprocess.PIPE)
        except Exception:
            return None
        time.sleep(0.3)
        if p.poll() is not None:     # refusé (ex. pas le droit pour le capot)
            return None
        self.procs.append(p)
        return p

    def stop(self):
        if IS_WIN:
            try:
                import ctypes
                ctypes.windll.kernel32.SetThreadExecutionState(self.ES_CONTINUOUS)
            except Exception:
                pass
        for p in self.procs:
            try:
                p.terminate()
            except Exception:
                pass
        self.procs = []
        self.active = False


# --------------------------------------------------------------------------- #
# Basse consommation pour AntiScroll lui-même
# --------------------------------------------------------------------------- #
def set_low_priority(low=True):
    if psutil is None:
        return
    try:
        me = psutil.Process()
        if IS_WIN:
            me.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if low else psutil.NORMAL_PRIORITY_CLASS)
        elif low:
            me.nice(10)          # remonter la priorité demande root : on ne le fait pas
    except Exception:
        pass


# --------------------------------------------------------------------------- #
# Apps du mode Dev Roblox : Roblox Studio, Claude, Blender
# --------------------------------------------------------------------------- #
def _newest(patterns):
    files = []
    for pat in patterns:
        files += glob.glob(os.path.expandvars(os.path.expanduser(pat)))
    files = [f for f in files if os.path.isfile(f)]
    return max(files, key=os.path.getmtime) if files else ""


def _flatpak_has(app_id):
    if not shutil.which("flatpak"):
        return False
    ok, out = _run(["flatpak", "info", app_id])
    return ok


DEV_APPS = [
    # key, nom affiché, morceaux de nom/chemin de processus qui prouvent qu'elle tourne
    ("roblox", "Roblox Studio", ["robloxstudio"]),
    ("claude", "Claude", ["anthropicclaude", "windowsapps\\claude_", "claude-desktop",
                          "/claude desktop"]),
    ("blender", "Blender", ["blender"]),
]


def default_command(key):
    """Commande trouvée automatiquement sur ce PC ("" si introuvable)."""
    if IS_WIN:
        if key == "roblox":
            return _newest([r"%LOCALAPPDATA%\Roblox\Versions\*\RobloxStudioBeta.exe",
                            r"%ProgramFiles(x86)%\Roblox\Versions\*\RobloxStudioBeta.exe",
                            r"%ProgramFiles%\Roblox\Versions\*\RobloxStudioBeta.exe"])
        if key == "claude":
            return _newest([r"%LOCALAPPDATA%\AnthropicClaude\claude.exe",
                            r"%LOCALAPPDATA%\Programs\Claude\Claude.exe"])
        if key == "blender":
            return _newest([r"%ProgramFiles%\Blender Foundation\*\blender.exe",
                            r"%ProgramFiles(x86)%\Steam\steamapps\common\Blender\blender.exe"])
        return ""
    # Linux
    if key == "roblox":
        # Roblox Studio n'existe pas sous Linux : on passe par Vinegar (flatpak)
        if _flatpak_has("org.vinegarhq.Vinegar"):
            return "flatpak run org.vinegarhq.Vinegar run"
        return "vinegar run" if shutil.which("vinegar") else ""
    if key == "claude":
        # Pas d'app Claude officielle sous Linux : version communautaire si installée
        return "claude-desktop" if shutil.which("claude-desktop") else ""
    if key == "blender":
        if shutil.which("blender"):
            return "blender"
        if _flatpak_has("org.blender.Blender"):
            return "flatpak run org.blender.Blender"
    return ""


def split_command(cmd):
    cmd = (cmd or "").strip()
    if not cmd:
        return []
    if IS_WIN:
        if os.path.isfile(cmd.strip('"')):
            return [cmd.strip('"')]
        return shlex.split(cmd, posix=False)
    if os.path.isfile(cmd):
        return [cmd]
    return shlex.split(cmd)


def match_patterns(key, cmd):
    pats = next(list(p) for k, _n, p in DEV_APPS if k == key)
    argv = split_command(cmd)
    if argv and os.path.isfile(argv[0].strip('"')):
        base = os.path.splitext(os.path.basename(argv[0].strip('"')))[0].lower()
        # "claude" tout court attraperait aussi Claude Code (le terminal) : on évite
        if base and base != "claude":
            pats.append(base)
    return pats


def running_apps(pattern_map):
    """{key: True/False} : quelles apps tournent en ce moment."""
    res = {k: False for k in pattern_map}
    if psutil is None:
        return res
    for p in psutil.process_iter(["name", "exe"]):
        try:
            text = ((p.info.get("name") or "") + " " + (p.info.get("exe") or "")).lower()
        except Exception:
            continue
        for k, pats in pattern_map.items():
            if not res[k] and any(s in text for s in pats):
                res[k] = True
    return res


def launch(cmd):
    """Lance une app détachée d'AntiScroll (elle survit si AntiScroll s'arrête)."""
    argv = split_command(cmd)
    if not argv:
        return False
    try:
        if IS_WIN:
            flags = 0x00000008 | 0x00000200      # DETACHED_PROCESS | NEW_PROCESS_GROUP
            subprocess.Popen(argv, creationflags=flags, close_fds=True,
                             cwd=os.path.dirname(argv[0].strip('"')) or None)
        else:
            subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:
        return False


class Watchdog:
    """Relance les apps fermées. Attend un peu après chaque lancement
    (Roblox Studio met du temps à apparaître) pour ne pas en ouvrir 10."""

    GRACE = 90   # secondes

    def __init__(self):
        self.last_launch = {}

    def check(self, commands):
        """commands = {key: commande}. Renvoie la liste des apps (re)lancées."""
        cmds = {k: c for k, c in commands.items() if (c or "").strip()}
        if not cmds:
            return []
        state = running_apps({k: match_patterns(k, c) for k, c in cmds.items()})
        now = time.time()
        started = []
        for k, c in cmds.items():
            if state.get(k):
                continue
            if now - self.last_launch.get(k, 0) < self.GRACE:
                continue
            self.last_launch[k] = now
            if launch(c):
                started.append(k)
        return started
