# nesus_ai

Routeur d’API IA extrêmement léger, générique et sans dépendance Python lourde.

Il utilise par défaut :

1. Cerebras
2. Groq
3. OpenRouter

À chaque tâche, il interroge automatiquement l’endpoint `/models` des fournisseurs configurés, filtre les modèles non conversationnels, classe les modèles disponibles selon le besoin, puis tente plusieurs routes en cas d’échec.

Google est volontairement verrouillé sur `gemini-3.5-flash-lite`.

Aucun daemon, aucun LLM local, aucune surveillance métier et aucun framework lourd.

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

## Découverte des modèles

Afficher les modèles réellement accessibles avec les clés configurées :

```bash
nesus_ai models
```

Forcer un rafraîchissement sans utiliser le cache de dix minutes :

```bash
nesus_ai models --refresh
```

Limiter l’affichage à un fournisseur :

```bash
nesus_ai models --provider groq --refresh
```

Le routeur sélectionne automatiquement les modèles selon la tâche :

- modèles rapides et économiques pour les demandes simples ;
- modèles orientés code pour le développement, le debug et les tests ;
- modèles plus puissants pour l’analyse, l’architecture, la sécurité et le raisonnement ;
- modèles avec grand contexte pour les longues entrées ;
- exclusion des modèles d’embedding, audio, transcription, modération et garde-fous spécialisés.

Le nombre de modèles essayés par fournisseur est contrôlé par `max_models_per_provider`.

## Utilisation

```bash
nesus_ai run "Analyse ce problème et propose une correction minimale"
```

Depuis stdin :

```bash
cat task.txt | nesus_ai run
```

Forcer seulement un fournisseur, tout en conservant la sélection automatique du modèle :

```bash
nesus_ai run --provider groq "Réponds uniquement OK"
```

Rafraîchir les modèles avant une tâche :

```bash
nesus_ai run --refresh-models "Audite ce projet Python"
```

## Ajouter Google ou un autre fournisseur

```bash
nesus_ai add-provider
```

Le programme propose :

- Google Gemini, toujours configuré avec `gemini-3.5-flash-lite` ;
- une API ou un proxy compatible OpenAI ;
- une API ou un proxy compatible Claude/Anthropic.

Pour un fournisseur personnalisé, utilise `auto` comme modèle afin que le routeur découvre et sélectionne seul les modèles. Un identifiant précis permet au contraire de verrouiller ce fournisseur sur un modèle fixe.

L’authentification Bearer est automatique. Pour un header personnalisé, indique par exemple `x-api-key`.

## Instructions globales

`instructions.md` est chargé au début de chaque requête et envoyé avec la tâche. Il reste générique et peut être modifié sans toucher au code :

```bash
nano ~/.config/nesus-ai/instructions.md
```

Le routeur limite le prompt total avec `max_prompt_chars` pour rester léger.

## Architecture

```text
nesus_ai.py          routeur et sélection autonome
instructions.md      règles globales
config.example.toml  fournisseurs et ordre de fallback
secrets.example.env  noms des clés
launch.py            raccourci vers le CLI
stop.py              confirme qu’aucun daemon ne tourne
install.sh
uninstall.sh
```
