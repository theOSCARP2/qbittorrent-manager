# Changelog

Toutes les modifications notables de ce projet sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

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
