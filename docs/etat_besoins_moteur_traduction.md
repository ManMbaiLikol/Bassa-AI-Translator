# État des besoins — Moteur de traduction BassaAI Translator

**Date :** 2 avril 2026  
**Projet :** BassaAI Translator — traduction automatique FR/EN → Bassa (Mbɛlɛ̂)  
**Moteurs :** Dictionnaire · ML (sentence-transformers) · LLM (Claude)

---

## Résumé exécutif

Le moteur de traduction repose sur trois composantes : un dictionnaire bilingue, un corpus de phrases parallèles, et un modèle IA (Claude). L'analyse de la base de données révèle que **la qualité des traductions est aujourd'hui limitée non par la technologie, mais par le volume et la diversité des données linguistiques disponibles**. Les actions prioritaires sont la vérification du corpus existant et l'ajout de paires dans des domaines de la vie quotidienne.

---

## 1. Corpus parallèle — Problème critique

### État actuel

| Indicateur | Valeur actuelle | Cible recommandée |
|---|---|---|
| Paires totales | 4 915 | 20 000+ |
| **Paires vérifiées (actives)** | **155 (3 %)** | **80 %+ (≥ 16 000)** |
| Paires en français (FR) | 4 915 | 15 000+ |
| **Paires en anglais (EN)** | **0** | **2 000+** |
| Domaines couverts | 1 (Bible) | 10+ |
| Longueur moyenne des phrases | 144 caractères | Mix 20–200 caractères |

### Pourquoi c'est bloquant

Le moteur ML (recherche sémantique) et le moteur LLM (contexte few-shot pour Claude) n'utilisent **que les paires vérifiées**. Avec 155 paires actives sur 4 915 :

- L'index ML couvre moins de 3 % du corpus disponible.
- Claude ne reçoit que des exemples de style biblique → il calque ses traductions sur ce registre unique, même pour des phrases du quotidien.
- L'anglais → Bassa fonctionne **uniquement avec le dictionnaire** : aucun exemple de traduction complète n'est disponible pour le ML ni pour Claude.

### Ce qu'il faut faire

1. **Vérifier les 4 760 paires non-vérifiées** : c'est du travail de relecture, pas de création. Un locuteur Bassa doit lire, corriger si nécessaire, et valider. Cette seule action multiplierait par 31 la taille de l'index ML.
2. **Créer des paires en anglais** : au moins 2 000 paires EN→Bassa couvrant les domaines prioritaires.

---

## 2. Diversité des domaines — Manque total

**100 % du corpus actuel provient de la Bible.** Le moteur excelle à traduire les textes religieux mais échoue sur le langage courant.

### Domaines prioritaires à couvrir

| Domaine | Priorité | Exemples de phrases types |
|---|---|---|
| **Vie quotidienne / famille** | Critique | Salutations, repas, maison, enfants, voisinage |
| **Santé / corps humain** | Critique | Maladie, médecin, symptômes, soins, maternité |
| **Agriculture / nature** | Haute | Cultures locales, saisons, animaux, forêt |
| **Commerce / échanges** | Haute | Marché, prix, argent, acheter/vendre |
| **Éducation / école** | Haute | Apprendre, compter, lire, enseignant, élève |
| **Administration / communauté** | Moyenne | Identité, village, chef, réunion, accord |
| **Émotions / états intérieurs** | Moyenne | Joie, peur, tristesse, faim, fatigue, amour |
| **Proverbes et expressions** | Moyenne | Sagesse populaire, idiomes Bassa, formules figées |
| **Tourisme / géographie** | Basse | Régions du Cameroun, routes, directions, lieux |
| **Droit / justice** | Basse | Loi coutumière, mariage, héritage, conflit |

### Volume indicatif cible par domaine

Pour un moteur ML efficace, chaque domaine a besoin d'au moins **200 paires vérifiées** (phrases complètes, pas uniquement des mots isolés).

---

## 3. Dictionnaire — Qualités et lacunes

### Ce qui est satisfaisant

- **32 130 entrées** au total — volume conséquent.
- **98 % vérifiées** (31 605 entrées) — fiabilité élevée.
- Bonne couverture FR : 16 480 entrées.

### Les lacunes identifiées

#### 3.1 Phonétique absente (critique pour les tons)

| Indicateur | Valeur |
|---|---|
| Entrées avec phonétique renseignée | 44 sur 32 130 **(0,1 %)** |
| Entrées sans information tonale | 32 086 **(99,9 %)** |

Le Bassa est une **langue tonale** : un même mot peut avoir des sens différents selon le ton (haut, moyen, bas). Sans les marques tonales, le LLM et les utilisateurs ne peuvent pas savoir quelle forme est correcte pour chaque entrée.

**Action requise :** enrichir progressivement les entrées avec leur phonétique/notation tonale, en commençant par les mots les plus fréquents.

#### 3.2 Couverture anglais insuffisante

| Langue | Entrées | % du total |
|---|---|---|
| Français (FR) | 16 480 | 51 % |
| Anglais (EN) | 7 437 | 23 % |
| Autres / non classé | ~8 213 | 26 % |

L'anglais dispose de moins de la moitié des entrées françaises. Pour un service bilingue, l'objectif devrait être une parité FR/EN.

#### 3.3 Incohérence des catégories grammaticales

| Code en base | Signification probable | Code interface admin |
|---|---|---|
| `s` | Substantif/nom | `noun` |
| `v` | Verbe | `verb` |
| `loc` | Locution | *(absent)* |
| `q` | Question/interrogatif | *(absent)* |
| `npro` | Nom propre | *(absent)* |
| `adv` | Adverbe | `adverb` |
| `ono` | Onomatopée | *(absent)* |

Les catégories historiques (abréviations) et les catégories de l'interface sont différentes. Les filtres de recherche par catégorie retournent des résultats incomplets. Une **migration de normalisation** est nécessaire.

#### 3.4 Exemples de phrases absents

Moins de 1 % des entrées possèdent un exemple d'usage en contexte. Sans exemples, le moteur ne peut pas enseigner à Claude comment le mot s'utilise dans une phrase réelle.

---

## 4. Règles grammaticales — Non renseignées

La fonctionnalité de règles grammaticales dynamiques (table `grammatical_rules`, éditables depuis l'interface admin) vient d'être créée. Elle contient actuellement **0 règle**, alors que c'est le levier le plus accessible pour améliorer le LLM sans toucher au code.

### Règles prioritaires à saisir

| Langue | Nom de la règle | Patron source | Transformation Bassa |
|---|---|---|---|
| FR | Négation ne…pas | `ne + verbe + pas` | `verbe + ɓé` |
| FR | Article défini/indéfini | `le / la / les / un / une` | Supprimer (pas d'article en Bassa) |
| FR | Adjectif épithète | `adj + nom` | `nom + adj` (ordre inversé) |
| FR | Possessif | `son/sa/mes + nom` | `nom + possessif` |
| FR | Pluriel nominal | `-s / -x` | Forme plurielle Bassa selon la classe nominale |
| EN | Négation (not / n't) | `verb + not` | `verbe + ɓé` |
| EN | Articles | `the / a / an` | Supprimer |
| EN | Progressif (-ing) | `is/are + verb-ing` | Préfixe `ŋ-` + verbe |
| EN | Passé simple | `verb-ed / irréguliers` | Préfixe `a-` + verbe |
| FR/EN | Salutation formelle | `bonjour / hello` | Forme Bassa contextuelle |
| FR/EN | Interrogation directe | `est-ce que / is/are` | Structure interrogative Bassa |

---

## 5. Données qualitatives — Rôle des locuteurs natifs

Les points suivants **ne peuvent pas être résolus par la technologie** : ils requièrent l'intervention de locuteurs natifs Bassa ou de linguistes spécialisés.

| Besoin | Description | Urgence |
|---|---|---|
| **Validation corpus** | Relecture et correction des 4 760 paires non-vérifiées | Critique |
| **Tons et diacritiques** | Ajout des marques tonales sur les entrées du dictionnaire | Haute |
| **Corpus quotidien** | Création de dialogues simples, conversations de la vie courante | Haute |
| **Correction LLM** | Identification des erreurs typiques de Claude sur le Bassa → ajout au corpus pour ancrer les bonnes formes | Haute |
| **Proverbes et oral** | Collecte d'expressions figées, proverbes, formules de politesse Bassa | Moyenne |
| **Validation finale** | Revue humaine systématique des traductions avant tout usage officiel | Continue |

---

## 6. Plan d'action — Résumé priorisé

### Priorité 1 — Critique (impact immédiat sur le moteur ML et LLM)

- [ ] Vérifier les 4 760 paires corpus existantes (interface Admin > Corpus)
- [ ] Créer un minimum de 500 paires EN→Bassa dans les domaines quotidien/santé/famille
- [ ] Saisir les 11 règles grammaticales prioritaires dans l'interface Admin > Règles

### Priorité 2 — Haute (améliore fortement la qualité Claude)

- [ ] Étendre le corpus FR avec des domaines hors Bible (agriculture, commerce, éducation)
- [ ] Compléter les phonétiques des 1 000 mots les plus fréquents du dictionnaire
- [ ] Ajouter des exemples de phrases aux entrées dictionnaire clés

### Priorité 3 — Moyenne (enrichissement continu)

- [ ] Normaliser les catégories grammaticales (`s` → `noun`, `v` → `verb`, etc.)
- [ ] Collecter des proverbes et expressions idiomatiques Bassa
- [ ] Atteindre la parité FR/EN dans le dictionnaire (objectif : 16 000 entrées EN)

### Priorité 4 — Continue

- [ ] Activer le mécanisme de feedback (👍/👎) pour alimenter le corpus via les utilisateurs
- [ ] Organiser des sessions de contribution communautaires avec des locuteurs natifs
- [ ] Mettre en place une revue trimestrielle de la qualité des traductions

---

## 7. Indicateurs de suivi

| Indicateur | Actuel | Objectif 3 mois | Objectif 1 an |
|---|---|---|---|
| Paires corpus vérifiées | 155 | 4 000 | 15 000 |
| Paires EN dans le corpus | 0 | 500 | 2 000 |
| Domaines couverts | 1 | 5 | 10+ |
| Règles grammaticales actives | 0 | 11 | 30+ |
| Entrées dictionnaire avec phonétique | 44 | 1 000 | 10 000 |
| Score confiance moyen moteur ML | ~30 % | ~60 % | ~80 % |

---

*Document généré le 2 avril 2026 — BassaAI Translator v2.0*  
*Pour toute question : contribuer via l'interface ou contacter l'équipe du projet.*
