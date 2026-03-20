# qBittorrent Manager

Une interface web Flask légère pour gérer une instance qBittorrent à distance.

## Fonctionnalités

- **Liste des torrents** — tableau paginé, triable et recherchable (DataTables côté serveur)
- **Actions sur les torrents** — pause, reprise, vérification, suppression (avec ou sans fichiers)
- **Vue des trackers** — liste de tous les trackers sur l'ensemble des torrents avec statut OK/erreur/en attente
- **Opérations en masse sur les trackers** — ajouter, remplacer ou supprimer une URL de tracker sur tous les torrents
- **Cache en arrière-plan** — la liste des torrents est mise en cache et rafraîchie automatiquement toutes les 30 secondes

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

```bash
python app.py
```

Ouvrir [http://localhost:5000](http://localhost:5000) dans le navigateur, puis saisir l'URL de l'interface Web qBittorrent et les identifiants.

## Configuration

Au premier lancement, une clé secrète unique est automatiquement générée et sauvegardée dans `~/.qbittorrent-manager/secret.key`. Aucune action requise.

| Variable d'environnement | Description |
|---|---|
| `SECRET_KEY` | Surcharge la clé générée automatiquement (usage serveur, Docker, etc.) |

## Notes

- Compatible avec qBittorrent v5+ (endpoints `/api/v2/torrents/stop` et `start`)
- L'application ne stocke aucun identifiant — le cookie SID de qBittorrent est conservé uniquement dans la session Flask
