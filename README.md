# nesus_ai v0.3.1-local

Superviseur autonome **strictement local à l’exécution** pour **Codex CLI**, **Claude Code** et **Gemini CLI**. Le code source est conservé dans ce dépôt privé, tandis que le programme, les clés, les projets et les journaux restent sur ta VM.

Fonctions :

- plusieurs clés API par moteur ;
- plusieurs modèles par moteur ;
- choix automatique du modèle et de l'effort de raisonnement ;
- rotation de clé, cooldown et failover ;
- prévention des erreurs `payload too large` / contexte dépassé ;
- reprise du travail via les fichiers et Git local ;
- interdiction de `git push` et du CLI `gh` dans les processus agents ;
- aucune création, publication ou synchronisation de dépôt distant par les agents ;
- retries bornés avec backoff exponentiel et jitter ;
- journaux JSONL avec métriques de tokens lorsqu'elles sont émises par le CLI.

## Mode strictement local

Le programme, sa configuration, ses secrets et ses journaux restent sur la VM :

```text
Programme : ~/.local/bin/nesus_ai
Configuration : ~/.config/nesus-ai/config.toml
Secrets : ~/.config/nesus-ai/secrets.env
État et journaux : ~/.local/state/nesus-ai/
Projets : les dossiers locaux que tu indiques avec -C
```

Le dépôt GitHub sert uniquement à stocker et versionner le code source de `nesus_ai`. Son exécution ne dépend pas de GitHub. Le superviseur autorise Git uniquement comme outil local (`status`, `diff`, `log`, `add`, `commit`, etc.). Dans les sous-processus Codex, Claude et Gemini :

- `git push` est bloqué techniquement ;
- le CLI `gh` est bloqué ;
- les agents reçoivent l’interdiction de créer ou modifier des remotes, publier un dépôt, une pull request ou un gist ;
- les agents travaillent directement dans le dossier local et laissent le résultat sur le disque de la VM.

Réglages associés :

```toml
local_only = true
block_git_push = true
block_github_cli = true
```

Le programme doit encore joindre les API AiPrimeTech et Google pour exécuter les modèles ; « local » signifie ici que le superviseur, le code produit, l’état et les secrets restent sur ta VM, sans publication automatique vers une forge Git.

## Cascade possible

```text
Codex / gpt-5.6-luna / low / clé 1
  → 401
Codex / gpt-5.6-luna / low / clé 2
  → agent bloqué sur une difficulté réelle
Codex / gpt-5.6-sol / high / clé 2
  → payload/context error
Claude / claude-fable-5 / high / clé 1
  → succès
Gemini n'est pas appelé
```

Une erreur de clé ne condamne pas le modèle. Une erreur de modèle ne condamne pas la clé.

## Installation depuis ce dépôt privé

```bash
git clone https://github.com/Nesus0/Multi_AI_Oechestrator.git
cd Multi_AI_Oechestrator
chmod +x install.sh uninstall.sh nesus_ai.py
./install.sh
export PATH="$HOME/.local/bin:$PATH"
```

Pour rendre le `PATH` permanent :

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

Pour une ancienne configuration v0.1 ou v0.2 :

```bash
nesus_ai init --force
```

La configuration précédente est sauvegardée sous `config.toml.bak-<date>`.
Le fichier `secrets.env` existant n'est pas écrasé.

## Clés API

Édite :

```bash
nano ~/.config/nesus-ai/secrets.env
```

```bash
AIPRIMETECH_CODEX_KEY_1="clé_codex_1"
AIPRIMETECH_CODEX_KEY_2="clé_codex_2"
AIPRIMETECH_CLAUDE_KEY_1="clé_claude_1"
AIPRIMETECH_CLAUDE_KEY_2="clé_claude_2"
GEMINI_API_KEY_1="clé_google_1"
GEMINI_API_KEY_2="clé_google_2"
GEMINI_API_KEY_3="clé_google_3"
```

```bash
chmod 600 ~/.config/nesus-ai/secrets.env
nesus_ai doctor --probe
```

Le processus enfant ne reçoit que la clé sélectionnée. Les autres clés du pool sont retirées de son environnement.

## Utilisation

```bash
nesus_ai -C /srv/projets/machin \
  "analyse le projet, corrige le bug, lance les tests et termine le travail"
```

Syntaxe naturelle :

```bash
nesus_ai fais le taff dans le dossier '/srv/projets/machin'
```

Afficher la route sans exécuter :

```bash
nesus_ai run --dry-plan -C /srv/projets/machin \
  "audite l'architecture et corrige les risques de concurrence"
```

Lister les modèles configurés :

```bash
nesus_ai models
```

Forcer un moteur :

```bash
nesus_ai run --provider codex -C /srv/projets/machin "termine le travail"
```

Forcer un profil logique :

```bash
nesus_ai run --provider codex --model sol --thinking xhigh \
  -C /srv/projets/machin "corrige cette race condition de production"
```

Forcer un identifiant exact :

```bash
nesus_ai run --model claude-opus-4-8 --thinking xhigh \
  -C /srv/projets/machin "révise la migration de données"
```

Forcer une clé :

```bash
nesus_ai run --provider gemini --account google-gemini-2 \
  -C /srv/projets/machin "analyse le dépôt"
```

Faire vérifier et réparer par un autre moteur :

```bash
nesus_ai run --verify -C /srv/projets/machin "implémente et teste la fonctionnalité"
```

## Routeur de modèles

Le score de complexité est calculé sur 100 à partir de :

- la forme de la demande ;
- architecture, sécurité, migration, concurrence ou production ;
- débogage et tests ;
- demande de lecture globale ;
- taille approximative du dépôt, sans charger son contenu dans le prompt.

Route par défaut :

| Moteur | Profil | Modèle | Effort | Usage principal |
|---|---|---|---|---|
| Codex | `luna` | `gpt-5.6-luna` | `low` | tâches ciblées, tests, petits changements |
| Codex | `terra` | `gpt-5.6-terra` | `medium` | débogage et travail intermédiaire |
| Codex | `sol` | `gpt-5.6-sol` | `high` | code complexe, sécurité, architecture |
| Claude | `haiku` | `claude-haiku-4-5` | `low` | tâches simples et revues courtes |
| Claude | `sonnet` | `claude-sonnet-4-6` | `high` | agent généraliste et code courant |
| Claude | `opus` | `claude-opus-4-8` | `xhigh` | raisonnement profond et erreurs coûteuses |
| Claude | `fable` | `claude-fable-5` | `high` | gros contexte et dépôt transversal |
| Gemini | `flash` | `flash` | défaut | rapide, économique, long contexte |
| Gemini | `pro` | `pro` | élevé | analyse complexe et long contexte |

Tous ces identifiants sont modifiables dans `~/.config/nesus-ai/config.toml`. Le nom exact accepté par ton compte et ton endpoint reste la source de vérité.

## Prévention des payloads trop volumineux

### Avant l'appel

- le prompt du superviseur est plafonné par `max_prompt_chars` ;
- un long texte utilisateur est écrit dans un fichier de tâche `0600`, puis l'agent reçoit seulement le chemin et le hash ;
- le handoff précédent est limité à un extrait compact ;
- le résumé Git est borné ;
- le contenu du dépôt n'est jamais préchargé dans le prompt ;
- l'agent reçoit des règles pour rechercher avant de lire, inspecter des plages et borner les sorties shell.

### Pendant la reprise

Sur `413`, `payload too large`, `input too long` ou dépassement de contexte :

1. aucun retry aveugle du même payload ;
2. nouvelle session CLI sans historique persistant ;
3. handoff et Git fortement compressés ;
4. une seule tentative compacte ;
5. escalade vers un profil long contexte comme Fable ou Gemini ;
6. passage au moteur suivant si nécessaire.

Réglages principaux :

```toml
max_prompt_chars = 28000
max_inline_task_chars = 10000
max_handoff_chars = 5000
max_git_summary_chars = 6000
payload_compact_retry = true
max_total_attempts = 14
max_models_per_provider = 4
```

## Retries et cooldowns

| Erreur | Comportement |
|---|---|
| `401` / `403` | clé suspendue, rotation vers la clé suivante |
| `429` | clé suspendue ; prise en compte d'un éventuel `Retry-After` |
| `500` / `502` / `503` / `504` / `529` | retry limité avec backoff exponentiel et jitter, puis rotation |
| modèle inconnu ou effort non supporté | cooldown du profil, modèle suivant |
| contexte / `413` | compactage puis modèle long contexte |
| agent bloqué, timeout, stall ou échec de processus | modèle plus capable, puis autre moteur |

Les retries ne sont pas appliqués aux erreurs déterministes de contexte, d'authentification ou de modèle.

## Contrôle des coûts

Le routeur suit une stratégie **cheap-first avec escalade** :

- petit modèle pour une tâche étroite et vérifiable ;
- modèle intermédiaire pour outils, code et débogage normal ;
- Sol ou Opus lorsque les contraintes interagissent ou que l'erreur serait coûteuse ;
- Fable seulement lorsque la difficulté vient réellement de la dispersion du contexte ;
- nombre de modèles, tentatives et tours borné ;
- arrêt demandé dès que le résultat est implémenté et validé ;
- tokens d'entrée/sortie enregistrés lorsque les événements JSON du CLI les exposent.

Les profils possèdent un `cost_rank`, une plage `min_complexity/max_complexity` et des capacités. Tu peux créer autant de profils que nécessaire.

## État et journaux

```bash
nesus_ai status
nesus_ai reset codex aiprimetech-codex-1
nesus_ai reset claude
nesus_ai reset
```

Journaux :

```text
~/.local/state/nesus-ai/runs/<run-id>.json
~/.local/state/nesus-ai/runs/<run-id>.jsonl
```

Le manifeste inclut provider, compte logique, modèle, effort, taille du prompt, estimation de tokens, tokens observés, type d'échec et mode compact.

## Configuration Codex AiPrimeTech

Le profil passe explicitement :

```text
--model <identifiant>
-c model_reasoning_effort="<niveau>"
```

Ton `~/.codex/config.toml` doit déjà définir le provider AiPrimeTech et lire la variable cible configurée à gauche de `env_from`, par défaut `OPENAI_API_KEY`.

## Configuration Claude AiPrimeTech

Le profil passe explicitement :

```text
--model <identifiant>
--effort <niveau>
--max-turns <limite>
```

Et fournit :

```text
ANTHROPIC_BASE_URL=https://aiprimetech.io
ANTHROPIC_AUTH_TOKEN=<clé sélectionnée>
```

## Références intégrées à la politique

Les règles de `docs/AI_PRIME_ROUTING_POLICY.md` synthétisent les principes de ces guides :

- https://aiprimetech.io/blog/agent-cost-control/
- https://aiprimetech.io/blog/rate-limits-and-retries/
- https://aiprimetech.io/blog/choosing-the-right-model-cost/
- https://aiprimetech.io/blog/reduce-llm-token-usage/

## Tests

```bash
pytest -q
```

La version publiée passe **14 tests**, couvrant notamment la rotation de clés, le choix Luna/Sol, l'escalade Fable, l'offload des tâches longues, le bornage du prompt, la classification des erreurs, le scénario `413 → retry compact → modèle supérieur` et le blocage local de `git push`/`gh`.
