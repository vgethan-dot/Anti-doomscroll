# AntiScroll

Anti-doomscroll pour toi et tes potes : PC (Ubuntu + Windows), Firefox et Android.
Rien sur un store, aucun serveur, aucun compte : **tout est stocké sur chaque appareil**.

| Dossier     | Ce que c'est |
|-------------|--------------|
| `pc/`       | App PC : écran noir, objectifs, alertes, surveillance des apps installées. |
| `firefox/`  | Extension : ton code est demandé **à chaque vidéo** (Shorts, Reels, TikTok, Spotlight, FB Reels). |
| `android/`  | App Android : pareil sur le téléphone, via le service d'accessibilité. |

## Comment ça marche

- **Code à chaque vidéo** : chaque nouvelle vidéo courte affiche un écran noir qui demande ton code. C'est fait exprès pour être chiant.
- **Écran noir sans arrêter les processus** : c'est juste une fenêtre noire au-dessus de tout. Rien n'est mis en veille, rien n'est tué : téléchargements, musique, compilations, jeux… tout continue derrière.
- **Objectifs** : par exemple « Réviser, 18:30, 60 min, lun-ven ». Tu reçois une alerte 10, 5 et 1 minute avant. Ensuite, ton PC et ton téléphone sont bloqués pendant 60 minutes, sauf si tu tapes ton code.
- **Actions protégées par le code** : supprimer un objectif, arrêter de surveiller une app, quitter l'app PC.
- **Pas de lien entre appareils** : chaque PC et chaque téléphone garde ses propres réglages. Pour copier les mêmes réglages ailleurs, utilise *Exporter / Importer la config* (voir plus bas).

---

## 1. Copier ta config sur un autre appareil

Il n'y a plus de compte ni de serveur. Pour avoir le même code et les mêmes objectifs partout :

1. Sur l'appareil déjà réglé : **Exporter la config** (onglet *Config* sur PC, section *Transférer la config* sur Android). Ça crée un fichier `antiscroll-config.json`.
2. Envoie ce fichier sur l'autre appareil (clé USB, mail, Drive, câble…).
3. Sur l'autre appareil : **Importer une config**, puis tape le code actuel de cet appareil (s'il en a un).

Le fichier contient ton code **chiffré** (jamais en clair), tes objectifs et les apps surveillées. Le format est le même sur PC et Android : un fichier exporté du PC s'importe sur le téléphone, et inversement.

Le code actuel est demandé avant d'importer : sinon n'importe qui pourrait importer une config sans code pour tout débloquer.

## 2. App PC

**Ubuntu :** `cd pc && ./lancer_linux.sh`
**Windows :** installe Python (python.org, coche *Add to PATH*), puis double-clique `pc\lancer_windows.bat`.

- Onglet *Code* : choisis ton code.
- Onglet *Apps PC* → *Lancer au démarrage du PC*.
- Bouton *Tester l'écran noir* : lance une vidéo ou une musique et vérifie qu'elle continue derrière.

Tes réglages sont enregistrés dans `~/.antiscroll/state.json` (sur Windows : `C:\Users\<toi>\.antiscroll\state.json`).

> Ubuntu avec Wayland : si l'écran noir ne reste pas au premier plan, choisis **« Ubuntu sur Xorg »** sur l'écran de connexion (roue dentée en bas à droite).

### Mode dev (onglet *Mode dev*)

Pour laisser le PC allumé pendant que Claude code dessus et que tu es sur ton téléphone.

- **Dev** : l'écran s'éteint vraiment (10 s après le clic), le PC ne se met jamais en veille, et AntiScroll se fait discret (priorité basse, fenêtre réduite, vérifications espacées).
- **Dev Roblox** : pareil, et en plus Roblox Studio, Claude et Blender sont ouverts puis relancés s'ils se ferment (vérification toutes les 30 s).
- Bouger la souris rallume l'écran. Après 2 min sans souris ni clavier (réglable), il se rééteint.
- Le blocage anti-scroll (objectifs, apps, extension) reste actif.
- Si le PC redémarre pendant un mode dev, il reprend tout seul (si AntiScroll se lance au démarrage).
- Si une app n'est pas trouvée, clique sur *Choisir…* à côté de son nom.

Linux : Roblox Studio passe par [Vinegar](https://vinegarhq.org) et Claude n'a pas d'app officielle, donc indique la commande toi-même si besoin. Pour que l'écran se rééteigne tout seul sous Xorg, installe `xprintidle` (`sudo apt install xprintidle`) ; sinon c'est Xorg qui l'éteint après le délai choisi.


## 3. Extension Firefox

Firefox refuse les extensions non signées. Deux options :

- **Pour tester :** `about:debugging` → *Ce Firefox* → *Charger un module temporaire* → choisis `firefox/manifest.json`. L'extension disparaît quand tu fermes Firefox.
- **Pour de bon (gratuit, rien de public) :**
  1. Zippe le contenu du dossier `firefox/`.
  2. Va sur addons.mozilla.org → *Developer Hub* → *Submit a New Add-on* → **« On your own »**.
  3. Mozilla te renvoie un `.xpi` signé, non listé dans le store. Glisse-le dans Firefox et envoie-le à tes potes.

L'extension récupère le code depuis l'app PC (qui doit tourner au moins une fois). Elle garde ensuite le dernier code connu.

## 4. App Android

**Obtenir l'APK sans rien installer : GitHub Actions**

1. Crée un dépôt GitHub (privé, c'est possible) et mets-y tout ce dossier.
2. Onglet **Actions** → *Construire AntiScroll* → **Run workflow**.
3. En bas de la page du build, dans *Artifacts* : `AntiScroll-android` (l'APK), `AntiScroll-Windows` (`.exe`), `AntiScroll-Linux` et `AntiScroll-firefox`.

Tu peux aussi ouvrir `android/` dans Android Studio et faire *Build → Build APK*.

**Installer l'APK**

1. Envoie l'APK sur le téléphone et ouvre-le. Autorise *Installer des applis inconnues*.
2. Ouvre AntiScroll → *Ouvrir les réglages d'accessibilité* → active **AntiScroll**.
3. Si Android affiche « paramètre restreint » : *Paramètres → Applis → AntiScroll → ⋮ → Autoriser les paramètres restreints*, puis réessaie.
4. Choisis ton code et ajoute tes objectifs, ou importe la config exportée depuis ton PC. L'app n'a même plus besoin d'Internet.

Pendant un objectif, le bouton **« Urgence : 2 min »** (3 fois maximum) laisse passer un appel ou un message important sans le code.

## Limites (à connaître)

- **Pas d'iPhone** : iOS interdit à une app de voir ce qui se passe dans TikTok ou Instagram.
- C'est une barrière anti-flemme, pas une prison. Quelqu'un de motivé peut tuer le processus ou désactiver l'accessibilité. Le but, c'est que ce soit assez chiant pour ne plus le faire par réflexe.
- La détection « nouvelle vidéo » se fait par heuristique : plein écran + changement d'élément dans le fil. Si TikTok, Insta ou YouTube changent leur appli ou leur site, il faudra peut-être ajuster :
  - `firefox/content.js` → `feedInfo()`
  - `GuardService.kt` → `onAccessibilityEvent`
- Le code Android n'a pas encore été compilé : l'environnement où il a été écrit n'avait pas accès aux outils Android. S'il y a une erreur au premier build, colle-la à Claude Code.

## Continuer avec Claude Code

```bash
cd antiscroll
claude
```

Ensuite, demande par exemple : « compile l'app Android et corrige les erreurs », ou « ajoute X.com à l'extension ».
