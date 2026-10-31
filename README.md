# AntiScroll

Anti-doomscroll pour toi et tes potes : PC (Ubuntu + Windows), Firefox et Android.
Rien sur un store, rien sur un serveur public : les comptes sont stockés sur **ton PC**.

| Dossier     | Ce que c'est |
|-------------|--------------|
| `server/`   | Serveur de comptes (pseudo unique + mot de passe, réglages synchronisés). Fichiers JSON. |
| `pc/`       | App PC : écran noir, objectifs, alertes, surveillance des apps installées. |
| `firefox/`  | Extension : ton code est demandé **à chaque vidéo** (Shorts, Reels, TikTok, Spotlight, FB Reels). |
| `android/`  | App Android : pareil sur le téléphone, via le service d'accessibilité. |

## Comment ça marche

- **Code à chaque vidéo** : chaque nouvelle vidéo courte affiche un écran noir qui demande ton code. C'est fait exprès pour être chiant.
- **Écran noir sans arrêter les processus** : c'est juste une fenêtre noire au-dessus de tout. Rien n'est mis en veille, rien n'est tué : téléchargements, musique, compilations, jeux… tout continue derrière.
- **Objectifs** : par exemple « Réviser, 18:30, 60 min, lun-ven ». Tu reçois une alerte 10, 5 et 1 minute avant. Ensuite, ton PC et ton téléphone sont bloqués pendant 60 minutes, sauf si tu tapes ton code.
- **Actions protégées par le code** : supprimer un objectif, arrêter de surveiller une app, quitter l'app PC.
- **Mot de passe du compte ≠ code de déblocage.** Le compte sert à se connecter, le code sert à débloquer.

---

## 1. Tailscale (une seule fois, toi + tes potes)

1. Installe Tailscale sur ton PC : `curl -fsSL https://tailscale.com/install.sh | sh` puis `sudo tailscale up`.
2. Note l'adresse de ton PC : `tailscale ip -4`. Ça donne quelque chose comme `100.101.102.103`.
3. Invite tes potes dans ton réseau Tailscale (console Tailscale → *Share* / *Invite*). Ils installent Tailscale sur leur PC ou téléphone.
4. Ouvre le port **seulement** pour Tailscale : `sudo ufw allow in on tailscale0 to any port 47800`.

L'adresse du serveur pour tout le monde sera donc : `http://100.101.102.103:47800`.

## 2. App PC

**Ubuntu :** `cd pc && ./lancer_linux.sh`
**Windows :** installe Python (python.org, coche *Add to PATH*), puis double-clique `pc\lancer_windows.bat`.

- Sur **ton** PC : onglet *Compte* → coche **« Ce PC héberge le serveur »**. Les comptes sont alors stockés dans `~/.antiscroll/server_data/users.json`.
- Sur les autres appareils : tape l'adresse Tailscale de ton PC, puis *Créer un compte* ou *Se connecter*.
- Onglet *Code* : choisis ton code.
- Onglet *Apps PC* → *Lancer au démarrage du PC*.
- Bouton *Tester l'écran noir* : lance une vidéo ou une musique et vérifie qu'elle continue derrière.

Ton PC doit être allumé pour que les autres se synchronisent. Hors ligne, chaque appareil continue de bloquer avec ses derniers réglages.

> Ubuntu avec Wayland : si l'écran noir ne reste pas au premier plan, choisis **« Ubuntu sur Xorg »** sur l'écran de connexion (roue dentée en bas à droite).

### Mode dev (onglet *Mode dev*)

Pour laisser le PC allumé pendant que Claude code dessus et que tu es sur ton téléphone.

- **Dev** : 10 s après le clic, tous les écrans deviennent 100 % noirs. Le PC ne se met jamais en veille, et AntiScroll se fait discret (priorité basse, fenêtre réduite, vérifications espacées).
- **Dev Roblox** : pareil, et en plus Roblox Studio, Claude et Blender sont ouverts puis relancés s'ils se ferment (vérification toutes les 20 s).
- Bouger la souris fait partir le noir, sans code (ce n'est pas un verrouillage). Après 2 min sans souris ni clavier (réglable), le noir revient.
- Le blocage anti-scroll (objectifs, apps, extension) reste actif.
- Si le PC redémarre pendant un mode dev, il reprend tout seul (si AntiScroll se lance au démarrage).
- Si une app n'est pas trouvée, clique sur *Choisir…* à côté de son nom.

Linux : Roblox Studio passe par [Vinegar](https://vinegarhq.org) et Claude n'a pas d'app officielle, donc indique la commande toi-même si besoin.


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
4. Choisis ton code, ajoute tes objectifs, connecte-toi au serveur. Il faut que Tailscale soit actif sur le téléphone.

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
