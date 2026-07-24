# nesus_ai

Routeur d’API IA extrêmement léger, générique et sans dépendance Python tierce.

Il utilise par défaut :

1. Cerebras
2. Groq
3. OpenRouter

En cas d’échec, il passe au fournisseur suivant. Aucun daemon, aucun LLM local, aucune surveillance métier et aucun framework lourd.

## Installation

```bash
git clone https://github.com/Nesus0/Multi_AI_Oechestrator.git
cd Multi_AI_Oechestrator
chmod +x install.sh uninstall.sh nesus_ai.py launch.py stop.py
./install.sh
```

Ajoute `~/.local/bin` au `PATH` si nécessaire :

```bash
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

## Configuration

Les fichiers sont installés dans :

```text
~/.config/nesus-ai/config.toml
~/.config/nesus-ai/secrets.env
~/.config/nesus-ai/instructions.md
```

Renseigne les clés :

```bash
nano ~/.config/nesus-ai/secrets.env
```

```bash
CEREBRAS_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...
```

Puis vérifie :

```bash
nesus_ai doctor
```

## Utilisation

```bash
nesus_ai run "Analyse ce problème et propose une correction minimale"
```

Depuis stdin :

```bash
cat task.txt | nesus_ai run
```

Forcer un fournisseur :

```bash
nesus_ai run --provider groq "Réponds uniquement OK"
```

## Ajouter Google ou un autre fournisseur

```bash
nesus_ai add-provider
```

Le programme propose :

- Google Gemini ;
- une API ou un proxy compatible OpenAI ;
- une API ou un proxy compatible Claude/Anthropic.

Pour un fournisseur personnalisé, il demande :

- le nom ;
- l’URL de base ;
- le modèle ;
- le mode d’authentification : Bearer, header personnalisé ou aucune authentification ;
- le nom de la variable contenant la clé.

L’authentification Bearer est automatique. Pour un header personnalisé, indique par exemple `x-api-key`.

## Instructions globales

`instructions.md` est chargé au début de chaque requête et envoyé avec la tâche. Il reste générique et peut être modifié sans toucher au code :

```bash
nano ~/.config/nesus-ai/instructions.md
```

Le routeur limite le prompt total avec `max_prompt_chars` pour rester léger.

## Architecture

```text
nesus_ai.py          routeur complet, bibliothèque standard uniquement
instructions.md      règles globales
config.example.toml  fournisseurs et ordre de fallback
secrets.example.env  noms des clés
launch.py            raccourci vers le CLI
stop.py              confirme qu’aucun daemon ne tourne
install.sh
uninstall.sh
```

## Principes

- aucune dépendance Python tierce ;
- aucun processus permanent ;
- aucun LLM local ;
- appels séquentiels uniquement ;
- timeouts et nombre d’essais bornés ;
- secrets séparés de la configuration ;
- compatible avec les endpoints OpenAI Chat Completions et Anthropic Messages.

## Mise à jour d’une ancienne installation

L’installateur conserve les fichiers existants. Pour repartir sur les nouveaux exemples :

```bash
cp ~/.config/nesus-ai/secrets.env ~/.config/nesus-ai/secrets.env.backup
nesus_ai init --force
```

Puis remets tes trois clés dans `secrets.env`.
