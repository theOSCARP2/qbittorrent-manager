# qBittorrent Manager

Une interface web Flask légère pour gérer une instance qBittorrent à distance.

> 🇬🇧 [English version](README.en.md)

## Aperçu

![Tableau des torrents](docs/torrents.png)
![Gestion des trackers](docs/trackers.png)

## Fonctionnalités

- **Liste des torrents** — tableau paginé, triable et recherchable (DataTables côté serveur)
- **Actions sur les torrents** — pause, reprise, vérification, suppression (avec ou sans fichiers)
- **Vue des trackers** — liste de tous les trackers sur l'ensemble des torrents avec statut OK/erreur/en attente
- **Opérations en masse sur les trackers** — ajouter, remplacer, supprimer ou copier une URL de tracker sur tous les torrents (dont l'ajout d'un tracker à tous les torrents d'un tracker source)
- **Cache en arrière-plan** — la liste des torrents est mise en cache et rafraîchie automatiquement toutes les 30 secondes
- **Panneau détail** — clic sur un torrent pour afficher toutes ses informations dans un panneau latéral
- **Interface multilingue** — français par défaut, anglais disponible via le bouton FR/EN dans la barre de navigation (préférence sauvegardée dans le navigateur)
- **Dashboard** — vue d'ensemble avec vitesses globales, espace disque utilisé/disponible, graphique de vitesse en temps réel, répartition des torrents par état et par catégorie (nombre et espace disque)
- **Filtres persistants** — filtrer les torrents par état et par catégorie, filtrer les trackers par statut (OK / erreur / en attente) ; tri et filtres mémorisés dans le navigateur
- **Thème sombre / clair** — basculement via le bouton soleil/lune dans la navbar, préférence sauvegardée dans le navigateur
- **Priorité des fichiers** — menu déroulant par fichier dans le panneau détail (Ne pas télécharger / Normal / Haute / Maximum)
- **Mode debug** — activable depuis l'interface web (bouton 🐛 dans la navbar), affiche les logs détaillés dans la console sans redémarrer
- **Ajout de torrents** — ajouter un torrent via lien magnet/URL ou fichier .torrent, avec options catégorie, répertoire et démarrage en pause
- **Création de torrents** — créer un fichier `.torrent` depuis des fichiers locaux (upload navigateur) ou un chemin sur le serveur, avec options trackers, taille des pièces, privé, commentaire et ajout automatique à qBittorrent
- **Changement de catégorie** — modifier la catégorie d'un torrent directement depuis le panneau détail
- **Trackers dans le panneau détail** — liste des trackers avec icône de statut (actif / erreur / en attente)
- **Filtres intégrés au tableau** — filtres état et catégorie directement dans les en-têtes de colonnes
- **Vérification des mises à jour** — badge dans la navbar si une nouvelle version est disponible sur GitHub
- **Notifications navigateur** — alerte automatique quand un torrent atteint 100%
- **Liste des fichiers** — détail des fichiers d'un torrent avec taille et progression individuelle dans le panneau latéral
- **Colonne ETA** — temps estimé avant fin du téléchargement dans le tableau des torrents (triable)
- **Page Catégories** — gestion complète des catégories : créer, renommer, changer le chemin, déplacer les torrents entre catégories, supprimer
- **Page Logs** — logs qBittorrent en temps réel avec filtre par niveau (Normal / Info / Avertissement / Critique), pause et auto-scroll
- **Limite de vitesse par torrent** — définir la vitesse max DL/UP directement depuis le panneau détail (0 = illimité)
- **Répertoire de sauvegarde modifiable** — changer le dossier de destination d'un torrent depuis le panneau détail (qBittorrent déplace les fichiers automatiquement)
- **Sécurité renforcée** — protection CSRF, cookies sécurisés (HttpOnly, SameSite), Content Security Policy, rate limiting sur le login et les opérations en masse, validation des entrées (hashes, chemins)

## Prérequis

- Python 3.10+
- Une instance qBittorrent avec l'interface Web activée

## Installation

```bash
git clone https://github.com/theOSCARP2/qbittorrent-manager.git
cd qbittorrent-manager
python -m venv .venv
source .venv/bin/activate  # Windows : .venv\Scripts\activate
pip install -r requirements.txt
```

## Utilisation

### Depuis les binaires (recommandé)

Télécharger le binaire correspondant à votre système depuis la page [Releases](https://github.com/theOSCARP2/qbittorrent-manager/releases) :

| Système | Fichier |
|---|---|
| Windows | `qbittorrent-manager.exe` |
| Linux | `qbittorrent-manager-linux` |
| macOS (Apple Silicon M1/M2/M3) | `qbittorrent-manager-macos-arm64` |
| macOS (Intel) | `qbittorrent-manager-macos-intel` |

**Windows** — double-cliquer sur le `.exe` ou l'exécuter depuis un terminal :
```bat
qbittorrent-manager.exe
```

**Linux / macOS** — rendre le fichier exécutable puis le lancer :
```bash
chmod +x qbittorrent-manager-linux  # ou qbittorrent-manager-macos-arm64 / qbittorrent-manager-macos-intel
./qbittorrent-manager-linux
```

### Via Docker (recommandé pour NAS / serveur)

```bash
docker run -d \
  --name qbittorrent-manager \
  --restart unless-stopped \
  -p 5000:5000 \
  -v qbm-data:/root/.qbittorrent-manager \
  ghcr.io/theoscarp2/qbittorrent-manager:latest
```

Ou avec Docker Compose :

```bash
docker compose up -d
```

### Depuis les sources

```bash
python app.py
```

Ouvrir [http://localhost:5000](http://localhost:5000) dans le navigateur, puis saisir l'URL de l'interface Web qBittorrent et les identifiants.

## Configuration

Au premier lancement, une clé secrète unique est automatiquement générée et sauvegardée dans `~/.qbittorrent-manager/secret.key`. Aucune action requise.

| Variable d'environnement | Description |
|---|---|
| `SECRET_KEY` | Surcharge la clé générée automatiquement (usage serveur, Docker, etc.) |

L'application utilise **Waitress** comme serveur de production (pas de warning de développement Flask).

## Crédits

Développé avec l'aide de [Claude](https://claude.ai) (Anthropic).

## Notes

- Compatible avec qBittorrent v5+ (endpoints `/api/v2/torrents/stop` et `start`, états `stoppedUP`/`stoppedDL` en remplacement de `pausedUP`/`pausedDL`)
- L'application ne stocke aucun identifiant — le cookie SID de qBittorrent est conservé uniquement dans la session Flask
