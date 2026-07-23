# Politique de routage, coût, contexte et retries

Cette politique est la traduction opérationnelle, pour `nesus_ai`, des quatre guides AiPrimeTech suivants :

- https://aiprimetech.io/blog/agent-cost-control/
- https://aiprimetech.io/blog/rate-limits-and-retries/
- https://aiprimetech.io/blog/choosing-the-right-model-cost/
- https://aiprimetech.io/blog/reduce-llm-token-usage/

Elle ne recopie pas les articles. Elle transforme leurs recommandations en règles exécutables.

## 1. Compétence bornée plutôt que boucle infinie

- Nombre total d'essais plafonné.
- Nombre de modèles testés par provider plafonné.
- Nombre de tours Claude borné par profil.
- Un agent doit arrêter dès que l'objectif est implémenté et validé.
- Un échec déterministe ne doit pas déclencher une répétition identique.
- Une répétition n'est autorisée que si le payload, le modèle, la clé ou l'état du dépôt a réellement changé.

## 2. État compact, pas transcript complet

L'agent suivant reçoit seulement :

- l'objectif utilisateur ou un chemin vers son fichier complet ;
- le type d'échec précédent ;
- un court extrait de sortie ;
- le modèle et l'effort précédents ;
- le statut et les statistiques Git ;
- les fichiers réellement modifiés, visibles dans le dossier.

Les longues réflexions, anciens tool calls et logs complets restent dans les archives JSONL, jamais dans le nouveau prompt.

## 3. Budget de contexte

- Prompt superviseur plafonné en caractères et estimé en tokens.
- Tâche trop longue déplacée dans un fichier local protégé.
- Recherche ciblée avant lecture.
- Lecture par plages pour les fichiers volumineux.
- Sorties shell bornées.
- Répertoires générés, dépendances et binaires exclus par défaut.
- Handoff, Git et sorties précédentes ont chacun un budget indépendant.

## 4. Modèle le moins cher suffisamment capable

- Luna, Haiku ou Flash pour une tâche étroite, courte et mécaniquement vérifiable.
- Terra, Sonnet ou modèle intermédiaire pour le code et les outils ordinaires.
- Sol ou Opus lorsque l'ambiguïté, le risque, l'architecture, la sécurité ou la concurrence augmentent.
- Fable ou Gemini long contexte seulement lorsque les faits nécessaires sont dispersés ou que la récupération ciblée est incertaine.
- Une sortie invalide, un blocage réel ou un échec de validation est un signal d'escalade.

## 5. Rate limits et retries

- `401/403` : aucun retry identique ; désactivation temporaire de la clé.
- `429` : rotation de clé et cooldown, avec respect d'un éventuel `Retry-After`.
- `5xx/529` : retry limité avec backoff exponentiel et jitter.
- Contexte dépassé : aucun backoff ; compactage ou modèle à contexte supérieur.
- Modèle inconnu : aucun retry sur le même identifiant ; profil suivant.
- Cooldowns séparés par compte et par modèle.

## 6. Mesure par tâche réussie

Le journal conserve, lorsque disponibles :

- modèle et effort ;
- taille du prompt ;
- estimation de tokens ;
- tokens d'entrée/sortie exposés par le CLI ;
- nombre d'essais ;
- durée ;
- raison d'arrêt ;
- provider et compte ayant terminé.

La métrique utile est le coût et le volume de tokens par tâche réussie, pas uniquement le coût d'un appel isolé.

## 7. Payload too large

Lorsqu'une erreur de taille apparaît :

1. terminer le processus fautif ;
2. créer une nouvelle session sans historique ;
3. supprimer du prompt les détails non indispensables ;
4. conserver seulement l'objectif, les contraintes, les faits et l'état Git ;
5. réessayer une fois en mode compact ;
6. privilégier un modèle long contexte ;
7. changer de provider si le problème persiste.

La taille théorique du contexte d'un modèle ne remplace pas les limites du gateway, du client, du transport HTTP ou de l'agent CLI.
