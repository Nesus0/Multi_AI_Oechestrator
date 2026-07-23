# nesus_ai

Orchestrateur local léger pour **Codex CLI**, **Claude Code** et **Gemini CLI**.

Il choisit un moteur, un modèle, un niveau de raisonnement et une clé API, puis reprend automatiquement avec une autre route en cas de `401`, `403`, `429`, erreur serveur, timeout ou contexte trop volumineux.

## Principes

- un seul fichier principal Python ;
- aucune dépendance Python tierce ;
- plusieurs clés par fournisseur ;
- modèles et effort de raisonnement configurables ;
- circuit breakers et cooldowns séparés ;
- prompts et handoffs bornés ;
- Git local autorisé, publication distante bloquée ;
- LLM local facultatif et désactivé par défaut.

## Installation

```bash
git clone https://github.com/Nesus0/Multi_AI_Oechestrator.git
cd Multi_AI_Oechestrator
chmod +x install.sh uninstall.sh nesus_ai.py launch.py stop.py
./install.sh
```

Ajoute ensuite le dossier au `PATH` si nécessaire :

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Fichiers installés :

```text
~/.local/bin/nesus_ai
~/.local/bin/nesus-ai
~/.local/bin/nesus-ai-launch
~/.local/bin/nesus-ai-stop
~/.config/nesus-ai/config.toml
~/.config/nesus-ai/secrets.env
~/.config/nesus-ai/local.env
```

## Clés API

Édite :

```bash
nano ~/.config/nesus-ai/secrets.env
```

```bash
AIPRIMETECH_CODEX_KEY_1="..."
AIPRIMETECH_CODEX_KEY_2="..."
AIPRIMETECH_CLAUDE_KEY_1="..."
AIPRIMETECH_CLAUDE_KEY_2="..."
GEMINI_API_KEY_1="..."
GEMINI_API_KEY_2="..."
GEMINI_API_KEY_3="..."
```

Puis :

```bash
chmod 600 ~/.config/nesus-ai/secrets.env
nesus_ai doctor --probe
```

## Utilisation

```bash
nesus_ai -C /srv/projets/machin \
  "analyse le projet, corrige le bug, lance les tests et termine le travail"
```

Syntaxe naturelle :

```bash
nesus_ai fais le taff dans le dossier '/srv/projets/machin'
```

Afficher la route sans l’exécuter :

```bash
nesus_ai run --dry-plan -C /srv/projets/machin \
  "audite l’architecture et corrige les problèmes"
```

Forcer un moteur ou un modèle :

```bash
nesus_ai run --provider codex --model sol --thinking xhigh \
  -C /srv/projets/machin "corrige cette race condition"
```

Faire vérifier le résultat par un autre moteur :

```bash
nesus_ai run --verify -C /srv/projets/machin \
  "implémente et teste la fonctionnalité"
```

## Modèles configurés

Les identifiants restent modifiables dans `~/.config/nesus-ai/config.toml`.

| Moteur | Profils par défaut |
|---|---|
| Codex | Luna, Terra, Sol |
| Claude | Haiku, Sonnet, Opus, Fable |
| Gemini | Flash, Pro |

Lister la configuration :

```bash
nesus_ai models
```

## Rotation et reprise

Exemple :

```text
Codex / Luna / clé 1
  → 401
Codex / Luna / clé 2
  → contexte dépassé
Codex / Sol / clé 2
  → 503
Claude / Sonnet / clé 1
  → succès
```

Les changements déjà présents dans le dossier sont conservés. Le nouvel agent reçoit uniquement un handoff compact, le statut Git et les fichiers modifiés.

## Protection contre les payloads trop volumineux

Le superviseur limite :

- la tâche injectée directement ;
- le prompt total ;
- la sortie précédente ;
- le résumé Git ;
- le nombre de modèles et d’essais.

Après un `413` ou un dépassement de contexte, il relance une session neuve avec un handoff réduit, puis privilégie un modèle long contexte.

Documentation détaillée : [`docs/AI_PRIME_ROUTING_POLICY.md`](docs/AI_PRIME_ROUTING_POLICY.md).

## LLM local facultatif

`nesus_ai` reste un CLI à la demande : il n’a pas besoin d’un daemon.

`launch.py` et `stop.py` gèrent uniquement un éventuel serveur local `llama.cpp` :

```bash
nesus-ai-launch
nesus-ai-launch --status
nesus-ai-stop
```

Ou depuis le dépôt :

```bash
python3 launch.py
python3 launch.py --status
python3 stop.py
```

Le fallback local est désactivé par défaut. Configure-le dans :

```bash
nano ~/.config/nesus-ai/local.env
```

Exemple minimal pour une VM faible :

```bash
NESUS_LOCAL_LLM_ENABLED=1
NESUS_LOCAL_LLM_BIN=/usr/local/bin/llama-server
NESUS_LOCAL_MODEL_FILE=/srv/models/tiny-model-q4.gguf
NESUS_LOCAL_LLM_CONTEXT=1024
NESUS_LOCAL_LLM_THREADS=1
```

Aucun modèle n’est téléchargé automatiquement. Le serveur écoute sur `127.0.0.1` par défaut.

Sur une VM `e2-micro`, le LLM local doit servir surtout au triage, à la classification, à la compression de contexte et à la préparation d’un handoff. Il ne doit pas être présenté comme un remplaçant fiable de Sol, Opus ou Gemini sur des modifications complexes.

Documentation : [`docs/LIGHTWEIGHT_LOCAL_FALLBACK.md`](docs/LIGHTWEIGHT_LOCAL_FALLBACK.md).

## État et journaux

```bash
nesus_ai status
nesus_ai reset codex aiprimetech-codex-1
nesus_ai reset
```

```text
~/.local/state/nesus-ai/runs/
~/.local/state/nesus-ai/services.json
~/.local/state/nesus-ai/local-llm.log
```

## Sécurité locale

Dans les processus agents :

- `git push` est bloqué ;
- le CLI `gh` est bloqué ;
- aucune création de dépôt, pull request ou gist ;
- aucune modification des remotes ;
- les clés non sélectionnées sont retirées de l’environnement enfant.

## Tests

```bash
pytest -q
python3 -m py_compile nesus_ai.py launch.py stop.py
```

## Désinstallation

```bash
./uninstall.sh
```

La désinstallation retire les exécutables et conserve la configuration, les modèles locaux et les journaux.
