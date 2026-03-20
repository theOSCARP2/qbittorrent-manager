# Changelog

Toutes les modifications notables de ce projet sont documentées ici.
Format basé sur [Keep a Changelog](https://keepachangelog.com/fr/1.0.0/).

---

## [1.4.0] - 2026-03-21

### Ajouté
- Interface multilingue FR/EN avec bouton de bascule dans la barre de navigation
- Préférence de langue sauvegardée dans le navigateur (localStorage)

### Modifié
- État `stalledUP` affiché en vert avec le label "Seed (inactif)" au lieu de "Bloqué" en jaune

---

## [1.3.0] - 2026-03-15

### Ajouté
- Panneau détail latéral : clic sur un torrent pour afficher toutes ses informations
- Champs supplémentaires dans le panneau : date d'ajout, date de complétion, créé par, créé le, répertoire de destination
- Colonne Ratio dans le tableau et dans le panneau détail
- Build macOS (binaire universel) dans la CI

### Modifié
- Les binaires Linux et macOS ont désormais des noms distincts (`qbittorrent-manager-linux`, `qbittorrent-manager-macos`)

---

## [1.2.0] - 2026-03-10

### Ajouté
- Serveur de production **Waitress** (remplace le serveur de développement Flask)
- Clé secrète auto-générée et persistée dans `~/.qbittorrent-manager/secret.key`
- Variable d'environnement `FLASK_DEBUG` pour le mode développement

### Modifié
- `FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: true` dans la CI pour supprimer les avertissements Node.js 20

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
- Builds automatiques Windows, Linux et macOS via GitHub Actions
