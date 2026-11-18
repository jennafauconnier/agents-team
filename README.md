# agents-team

Une équipe produit d'agents LLM (PM, PO, Tech Lead, dev front, dev back, QA) qui transforme une demande en code testé. Environ 200 lignes de Python, sans dépendance.

```
Demande → PM → PO → Tech Lead ─┬→ Dev front ─┐
          cadrage  stories  plan+API └→ Dev back ─┴→ tests exécutés → QA ── OK ──→ livré
                                                                        └ KO ──→ retour aux devs (max 5 fois)
```

**Présentation interactive : [`docs/index.html`](docs/index.html)** (ouvre le fichier dans un navigateur, ou active GitHub Pages sur le dossier `/docs`).

## Ce qui est particulier

- **Un modèle par rôle, choisi selon le prix.** Un modèle peu cher cadre et code, un modèle plus fort conçoit et vérifie, là où une erreur se propage. Après un KO du QA, le dev monte d'un cran dans l'échelle de prix.
- **Le QA ne se fie pas à sa lecture.** Le code du back est écrit sur disque et ses tests `unittest` sont exécutés dans un environnement sans clé d'API. Des tests rouges priment sur le verdict du QA.
- **Des garde-fous de coût.** Budget plafonné à 0,50 $ par run, 5 corrections au maximum, repli sur un autre modèle quand une réponse est vide.

## Lancer

Python 3.9+, bibliothèque standard uniquement.

```bash
python3 test_team.py                  # test hors-ligne avec de faux modèles, sans clé ni coût

export OPENROUTER_API_KEY=sk-or-...
python3 team.py "Ajouter un panier à une boutique en ligne"
```

Les livrables de chaque étape et le code généré sont écrits dans `out/<horodatage>/`, avec un `run.json` (tours, verdicts, modèles utilisés, coût).

Si `OPENAI_API_KEY` est aussi définie dans ton shell, `bench.py` l'utilise en priorité : lance alors `env -u OPENAI_API_KEY -u OPENAI_BASE_URL python3 team.py ...`.

## Modèles

Définis dans `models.team.openrouter.json` (ids OpenRouter et prix en $ par million de tokens, relevés le 18 novembre 2026, à vérifier avant de t'y fier).

| Rôle | Modèle |
|---|---|
| PM, PO, devs | `deepseek/deepseek-v4.1-flash-1017` |
| Devs après un KO | `xiaomi/mimo-v2.6-pro` |
| Tech Lead, QA | `tencent/hy4` |

Le choix suit la règle : modèle fort pour l'architecture et les tâches complexes, modèle peu cher pour l'exécution.

## Exemple de run

Le dossier [`demo/`](demo) contient un run complet pour la demande « Ajouter un panier à une boutique en ligne » : cadrage, stories, plan, code généré dans `demo/work/` et verdict du QA. Le verdict est **OK** et les 29 tests générés passent :

```bash
cd demo/work && python3 -m unittest discover -v
```

Ce code a été entièrement écrit par des LLM. Il illustre le pipeline, ce n'est pas du code de production.

## Régénérer la page de présentation

```bash
python3 build_presentation.py demo      # écrit docs/index.html
```

## Ce que j'ai appris en le construisant

1. **Un QA qui relit se laisse convaincre.** Il faut exécuter les tests.
2. **Un test peut avoir tort.** Un test attendait 5 € de livraison sur 55 € HT alors que la règle donnait 0 €. Le QA doit recalculer à la main et dire si le code ou le test est faux, et le dev doit pouvoir corriger le test.
3. **Les modèles à raisonnement renvoient des réponses vides** quand ils épuisent leurs tokens. Le raisonnement est coupé côté OpenRouter et l'équipe passe au modèle suivant.
4. **Le périmètre dérive.** Le PO est limité à 3 stories et le QA ne bloque que sur un critère clairement non rempli.

## Limites

- L'équipe travaille dans un dossier vide : elle ne modifie pas un projet existant.
- Pas encore de pause humaine après le PO, ni de lien avec des tickets ou des MR.
- Le QA peut rester pointilleux sur les grosses demandes : découper en incréments aide.
