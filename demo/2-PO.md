# Stories Panier — MVP

## Story 1 — Ajouter un article au panier

**En tant que** visiteur ou client connecté,
**je veux** ajouter un article à mon panier depuis la fiche produit,
**afin de** préparer mon achat.

### Critères d'acceptation

**CA1 — Ajout d'un article disponible**
- **Given** un article disponible avec un stock > 0
- **When** je clique sur "Ajouter au panier"
- **Then** l'article est ajouté au panier
- **And** le compteur d'articles en header s'incrémente de la quantité ajoutée
- **And** un message de confirmation s'affiche

**CA2 — Article déjà présent dans le panier**
- **Given** un article déjà présent dans mon panier
- **When** je clique sur "Ajouter au panier"
- **Then** la quantité de cet article est incrémentée (pas de doublon de ligne)
- **And** le compteur en header reflète la nouvelle quantité totale

**CA3 — Article indisponible**
- **Given** un article indisponible (stock = 0 ou supprimé)
- **When** j'affiche la fiche produit
- **Then** le bouton "Ajouter au panier" est désactivé
- **And** un message explicite indique l'indisponibilité

---

## Story 2 — Consulter et modifier le panier

**En tant que** visiteur ou client connecté,
**je veux** consulter mon panier, modifier les quantités et supprimer des articles,
**afin de** finaliser ma sélection avant l'achat.

### Critères d'acceptation

**CA1 — Accès et affichage du panier**
- **Given** un panier contenant au moins un article
- **When** je clique sur l'icône panier depuis n'importe quelle page
- **Then** je suis redirigé vers la page panier
- **And** chaque ligne affiche : nom, prix unitaire, quantité, sous-total ligne
- **And** le sous-total général du panier est affiché et correspond à la somme des lignes

**CA2 — Modification de quantité**
- **Given** un article à quantité 1 dans mon panier
- **When** je passe sa quantité à 3
- **Then** le sous-total de la ligne et le sous-total général sont recalculés
- **And** le compteur d'articles en header est mis à jour

**CA3 — Suppression d'un article**
- **Given** un panier contenant plusieurs articles
- **When** je supprime un article
- **Then** la ligne disparaît du panier
- **And** le sous-total général et le compteur en header sont recalculés

**CA4 — Suppression du dernier article**
- **Given** un panier contenant un seul article
- **When** je supprime cet article
- **Then** le panier affiche un état vide avec un message clair
- **And** le compteur d'articles en header affiche 0

---

## Story 3 — Persistance du panier et gestion des articles indisponibles

**En tant que** visiteur ou client connecté,
**je veux** retrouver mon panier lors d'une nouvelle session ou navigation,
**afin de** ne pas perdre ma sélection, tout en étant informé si un article n'est plus disponible.

### Critères d'acceptation

**CA1 — Persistance du panier**
- **Given** un panier contenant des articles
- **When** je quitte le site puis y reviens (même appareil/navigateur)
- **Then** mon panier est restauré à l'identique (articles, quantités, sous-total)
- **And** le compteur d'articles en header reflète le panier restauré

**CA2 — Article devenu indisponible entre deux sessions**
- **Given** un panier restauré contenant un article devenu indisponible ou supprimé
- **When** j'ouvre la page panier
- **Then** l'article concerné est signalé par un message clair (ex. "Article indisponible")
- **And** il est exclu du sous-total général
- **And** je peux le supprimer du panier

**CA3 — Article disponible mais quantité supérieure au stock**
- **Given** un panier restauré contenant un article dont le stock a diminué
- **When** j'ouvre la page panier
- **Then** un message indique que la quantité demandée dépasse le stock disponible
- **And** je peux ajuster la quantité dans la limite du stock