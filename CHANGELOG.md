# Changelog

Toutes les modifications notables de ce projet sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [1.18.0] - 2026-04-01

### Ajouté
- Ajout de torrents depuis l'interface : lien magnet, URL ou fichier `.torrent`, avec choix de la catégorie, du répertoire de destination et option "démarrer en pause"
- Notifications navigateur : bouton cloche 🔔 dans la navbar pour activer les alertes — une notification système s'affiche automatiquement quand un torrent atteint 100%

---

## [1.17.0] - 2026-03-22

### Amélioré
- Compatibilité mobile : l'interface est désormais utilisable sur smartphone
  - Tableaux responsifs (DataTables Responsive) : les colonnes moins importantes se masquent sur petit écran et sont accessibles via un clic sur la ligne
  - Torrents : priorité aux colonnes nom, progression, état, vitesse DL et actions
  - Trackers : priorité à l'URL, au statut et aux actions
  - Catégories : priorité au nom, nombre de torrents et actions
  - Navbar : boutons langue/thème/debug/déconnexion intégrés au menu hamburger sur mobile
  - Zones tactiles agrandies (min 44px) pour les boutons
  - Toasts pleine largeur sur mobile

---

## [1.16.0] - 2026-03-22

### Ajouté
- Image Docker publiée automatiquement sur GitHub Container Registry (`ghcr.io`) à chaque release
  - Tags : version exacte (`1.16.0`), mineur (`1.16`) et `latest`
  - `docker-compose.yml` fourni pour un démarrage rapide
  - Volume persistant pour la clé secrète de session

---

## [1.15.0] - 2026-03-22

### Ajouté
- Page Catégories : gestion complète des catégories qBittorrent
  - Tableau avec nom, chemin de sauvegarde, nombre de torrents et espace disque
  - Panneau détail : liste des torrents par catégorie avec actions (pause/reprise/vérifier/supprimer)
  - Créer une catégorie avec chemin de sauvegarde optionnel
  - Modifier : renommer et/ou changer le chemin d'une catégorie (les torrents sont migrés automatiquement)
  - Déplacer : déplacer tous les torrents d'une catégorie vers une autre (ou sans catégorie)
  - Supprimer : supprimer une catégorie (les torrents passent en "sans catégorie")
  - Lien dans la navbar entre Trackers et Logs

---

## [1.14.0] - 2026-03-22

### Ajouté
- Trackers : nouvel onglet "Cross-Seed" dans les opérations en masse
  - Ajouter un tracker à tous les torrents qui utilisent déjà un tracker source, sans supprimer le tracker source
  - Bouton rapide dans chaque ligne du tableau pour pré-remplir le tracker source

---

## [1.13.0] - 2026-03-22

### Ajouté
- Colonne ETA dans le tableau des torrents (temps estimé avant fin du téléchargement, triable)
- Page Logs : affichage des logs qBittorrent en temps réel avec mise à jour automatique toutes les 5 secondes
  - Filtres par niveau (Normal / Info / Avertissement / Critique)
  - Mode pause / reprise du rafraîchissement automatique
  - Auto-scroll vers le bas (désactivé si l'utilisateur remonte dans les logs)
  - Bouton pour effacer l'affichage local

---

## [1.12.0] - 2026-03-22

### Ajouté
- Priorité des fichiers dans le panneau détail : menu déroulant par fichier (Ne pas DL / Normal / Haute / Maximum) via `/api/v2/torrents/filePrio`
- Mode debug activable/désactivable depuis l'interface web (bouton 🐛 dans la navbar) sans redémarrer l'application

### Modifié
- Logs console plus lisibles pour l'utilisateur final (niveau INFO par défaut, format heure + niveau + message)
- Suppression du mode debug système (`FLASK_DEBUG`) — remplacé par le toggle in-app
- Message de démarrage amélioré avec version et URL

---

## [1.11.1] - 2026-03-21

### Corrigé
- Deux binaires macOS distincts : `macos-arm64` (Apple Silicon) et `macos-intel` (Intel x86_64 via Rosetta 2) — corrige l'erreur "Bad CPU type in executable"

---

## [1.11.0] - 2026-03-21

### Ajouté
- Basculement thème sombre / thème clair via un bouton soleil/lune dans la barre de navigation
- Préférence de thème sauvegardée dans le navigateur (localStorage)
- Variables CSS personnalisées (`--qbm-bg`, `--qbm-bg-card`, `--qbm-bg-input`, `--qbm-border`, `--qbm-text`, `--qbm-text-muted`, `--qbm-accent`, etc.) pour un theming cohérent
- Script anti-flash dans le `<head>` pour appliquer le thème avant le chargement du CSS
- Couleurs du graphique Chart.js mises à jour dynamiquement lors du changement de thème

---

## [1.10.0] - 2026-03-21

### Ajouté
- Numéro de version affiché dans la navbar
- Vérification automatique des mises à jour (via l'API GitHub Releases, cache 1h)
- Badge jaune cliquable dans la navbar si une nouvelle version est disponible

---

## [1.9.0] - 2026-03-21

### Ajouté
- Ajout de torrents depuis l'interface : lien magnet/URL ou fichier .torrent, avec options catégorie, répertoire et démarrage en pause
- Trackers dans le panneau détail avec icône de statut (actif / erreur / en attente)
- Filtres état et catégorie intégrés directement dans les en-têtes du tableau

### Modifié
- Filtres état et catégorie se mettent à jour à chaque rechargement (plus de garde au premier chargement uniquement)
- Panneau détail : rafraîchissement automatique toutes les 5 secondes quand il est ouvert

### Corrigé
- Filtre des états non actualisé après l'ajout d'un torrent
- Erreur `null` sur les filtres lors du premier appel ajax (avant `initComplete`)

---

## [1.8.0] - 2026-03-21

### Ajouté
- Changement de catégorie directement depuis le panneau détail d'un torrent
- Notifications navigateur quand un torrent atteint 100%
- Tri et filtres persistants (état, catégorie) sauvegardés dans le navigateur (localStorage)

---

## [1.7.0] - 2026-03-21

### Ajouté
- Liste des fichiers d'un torrent dans le panneau détail (nom, taille, barre de progression par fichier)
- Graphique d'évolution des vitesses DL/UP en temps réel sur le Dashboard (20 derniers points)
- Espace disque dans la stat card du Dashboard : utilisé par les torrents / total estimé avec barre de progression
- Répartition de l'espace disque par catégorie dans le Dashboard (onglet "Espace par catégorie")
- Support des états qBittorrent v5 `stoppedUP` et `stoppedDL`

---

## [1.6.0] - 2026-03-21

### Ajouté
- Page Dashboard : stats globales (total, vitesse DL/UP, taille), répartition par état et par catégorie, auto-refresh toutes les 15 secondes
- Filtre par état sur la page Torrents (Téléchargement, Seed, Pausé, Erreur…)
- Filtre par statut sur la page Trackers (OK / Erreur / En attente)

### Corrigé
- Les filtres état et catégorie ne se peuplaient pas au premier chargement (cache vide)

---

## [1.5.0] - 2026-03-21

### Ajouté
- Colonne Catégorie dans le tableau des torrents (triable)
- Filtre par catégorie via un menu déroulant dans la barre d'en-tête
- Commentaire du torrent affiché dans le panneau détail

---

## [1.4.0] - 2026-03-21

### Ajouté
- Interface multilingue FR/EN avec bouton de bascule dans la barre de navigation
- Préférence de langue sauvegardée dans le navigateur (localStorage)
- Fichier `CHANGELOG.md` et injection automatique dans les releases GitHub

### Modifié
- État `stalledUP` affiché en vert "Seed (inactif)" au lieu de jaune "Bloqué"

---

## [1.3.1] - 2026-03-14

### Corrigé
- Les binaires Linux et macOS avaient le même nom, ce qui empêchait l'affichage du binaire macOS dans les releases GitHub

---

## [1.3.0] - 2026-03-13

### Ajouté
- Serveur de production **Waitress** en remplacement du serveur de développement Flask
- Variable d'environnement `FLASK_DEBUG` pour activer le mode développement avec hot-reload

---

## [1.2.0] - 2026-03-10

### Ajouté
- Panneau détail latéral : clic sur un torrent pour afficher toutes ses informations (taille, vitesses, ratio, dates, répertoire, hash)
- Colonne Ratio dans le tableau des torrents
- Build macOS dans le pipeline CI

---

## [1.1.0] - 2026-03-08

### Ajouté
- Clé secrète Flask auto-générée et persistée dans `~/.qbittorrent-manager/secret.key`
- Variable d'environnement `SECRET_KEY` pour surcharger la clé (usage Docker/serveur)
- Migration Node.js 24 dans les actions GitHub (`FORCE_JAVASCRIPT_ACTIONS_TO_NODE24`)

---

## [1.0.2] - 2026-03-06

### Corrigé
- Le bouton "Supprimer sélectionnés" restait grisé après "Tout sélectionner" (correction complète)
- Erreur `invalid assignment left-hand side` empêchant le chargement de la page Trackers

---

## [1.0.1] - 2026-03-05

### Corrigé
- Le bouton "Supprimer sélectionnés" restait grisé après "Tout sélectionner" sur la page Trackers
- Erreur `can't access property 'checked'` causée par DataTables qui réécrit le contenu des `<th>`

---

## [1.0.0] - 2026-03-01

### Ajouté
- Liste des torrents paginée, triable et recherchable (DataTables côté serveur)
- Actions sur les torrents : pause, reprise, vérification, suppression (avec ou sans fichiers)
- Sélection multiple et actions groupées
- Vue des trackers avec statut OK / erreur / en attente
- Opérations en masse sur les trackers : ajouter, remplacer, supprimer
- Panneau de détail des torrents d'un tracker
- Cache en arrière-plan rafraîchi toutes les 30 secondes
- Pipeline CI GitHub Actions : builds automatiques Windows et Linux via PyInstaller
