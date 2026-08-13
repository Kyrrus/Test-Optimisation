# Infrastructure Analyzer

Application Python qui analyse un historique de métriques techniques et utilise
un modèle local Ollama pour générer des recommandations d’optimisation.

## Prérequis

- Python 3.11 ou supérieur
- pip
- Ollama installé et démarré

## Création de l’environnement virtuel

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
ollama pull llama3.1:8b-instruct-q8_0
```

### Linux et macOS

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
ollama pull llama3.1:8b-instruct-q8_0
```

## Exécution

Dans l’environnement virtuel activé :

```bash
python main.py --input rapport.json --output output.json --model llama3.1:8b-instruct-q8_0
```

Les arguments sont facultatifs. Cette commande produit le même résultat :

```bash
python main.py
```

La génération peut prendre plusieurs dizaines de secondes selon la machine, car
le modèle Ollama est exécuté localement.

## Tests

```bash
python -m pytest -v
```

## Architecture

Le pipeline est composé de fonctions simples qui jouent le rôle des nœuds:

```text
rapport.json
    -> ingest_data
    -> compute_insights
    -> detect_anomalies
    -> summarize_services
    -> generate_recommendations avec Ollama
    -> output.json
```

- models.py décrit et valide les données avec Pydantic ;
- config.py contient les seuils d’anomalie ;
- pipeline.py contient les étapes d’analyse et l’appel à Ollama ;
- main.py lit les arguments de la ligne de commande et écrit le résultat ;
- tests/test_pipeline.py vérifie les comportements principaux.

Seul le nœud de recommandations utilise le LLM.

## Décisions fonctionnelles

Les conventions suivantes sont appliquées :

- timestamp correspond au relevé le plus récent ;
- average_latency_ms est la moyenne des latences ;
- max_cpu_usage et `max_memory_usage` sont les maxima observés ;
- error_rate est la moyenne des taux d’erreur ;
- uptime_seconds provient du relevé le plus récent ;
- service_status_summary décrit l’état du relevé le plus récent ;
- les incidents historiques sont utilisés pour créer les recommandations ;
- une seule anomalie agrégée est produite par métrique ;
- le nombre d’occurrences correspond au seuil de la sévérité affichée.

Les valeurs de config.py sont donc des seuils de démonstration (pas de suils fournis dans le sujet), regroupés dans un seul fichier
pour pouvoir être remplacés facilement. Dans un environnement réel, ils seraient
calibrés à partir de l’historique et des objectifs de service de l’infrastructure.

## Dépendances

Le projet utilise trois dépendances :

- pydantic pour valider les entrées et structurer la sortie ;
- pytest pour exécuter les tests ;
- ollama pour appeler le modèle local depuis Python.

Les calculs utilisent uniquement la bibliothèque standard Python (json,
statistics, pathlib et argparse). Pandas, LangChain et LangGraph ne sont pas
nécessaires : un appel direct à Ollama suffit.

## Génération des recommandations avec Ollama

Le modèle reçoit uniquement les indicateurs, les anomalies et les incidents déjà
calculés. Il ne reçoit pas les relevés bruts. Il peut proposer une action
d'optimisation raisonnable (ajustement des ressources, répartition de charge,
réplication, etc.) même si la cause exacte n'est pas connue. Les valeurs mesurées
restent distinguées des hypothèses. La réponse complète est validée par le schéma
Pydantic RecommendationResponse, avec une température de 0 pour limiter les
variations.

Cette validation garantit la structure JSON, mais pas la pertinence métier de
chaque proposition. Un modèle local peut encore suggérer une action insuffisamment
justifiée malgré le prompt. En production, une validation métier ou une revue
humaine serait ajoutée avant l'application des recommandations.

Si le modèle choisi n’est pas présent, il faut le
télécharger avant l’exécution :

```bash
ollama pull llama3.1:8b-instruct-q8_0
```

Les tests remplacent l’appel à Ollama par une réponse simulée. Ils vérifient ainsi
le pipeline et le format sans charger un modèle à chaque exécution.

## Structure du projet

```text
infrastructure_analyzer/
  __init__.py
  config.py
  models.py
  pipeline.py
tests/
  test_pipeline.py
main.py
requirements.txt
rapport.json
output.json
output.schema.json
```

## Schéma de sortie

Les modèles Pydantic valident le rapport avant son écriture. Le schéma
est également disponible dans output.schema.json.

## Choix techniques

### Python

Python a été choisi parce que le projet consiste principalement à lire des
données JSON, calculer des statistiques et appliquer des règles. Sa syntaxe
permet de conserver un pipeline court et facile à modifier.

### Pydantic

Pydantic valide les données externes dès leur ingestion et garantit également
la structure du rapport final. Cela évite d’écrire manuellement la validation
de chaque propriété.

### Ollama

Ollama permet d’exécuter le modèle localement, sans clé d’API ni transmission
des données à un service distant. Le LLM est utilisé uniquement pour générer
les recommandations. Les calculs et la détection d’anomalies restent
déterministes.

### Pytest

Pytest vérifie les calculs, la détection d’anomalies, les statuts de services
et le format des recommandations. L’appel Ollama est simulé dans les tests
pour garantir des résultats rapides et reproductibles.

### Absence de LangChain ou LangGraph

Le pipeline ne nécessite qu’un seul appel LLM. Un framework d’orchestration
supplémentaire ajouterait de la complexité sans apporter de bénéfice important
pour ce cas d’usage.
