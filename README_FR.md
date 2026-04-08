````markdown
# Votre premier projet d’agent IA

<div align="center">

**Agent de code intelligent basé sur plusieurs API de LLM**

[![Python](https://img.shields.io/badge/Python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

[中文](README.md) | **Français**

</div>

## 📖 Présentation du projet

Si vous commencez tout juste à apprendre ce que sont les agents IA et que vous ne savez pas par où commencer, utilisez ce projet pour apprendre ou développer vos propres applications d’agent.

Ce projet fournit à tous les nouveaux développeurs d’agents IA un **Code Agent** extrêmement accessible mais puissant, basé sur l’architecture ReAct (Reasoning + Acting), prenant en charge plusieurs grands modèles de langage (DeepSeek, OpenAI, Claude, Gemini) pour le raisonnement, et centré sur le développement logiciel et les tâches liées au code. L’agent peut :

### 🎯 Capacités principales ⭐ v1.2.0 Nouveau
- 📋 **Planification des tâches** - Génère des plans structurés avant l’exécution, réduit les opérations inefficaces de 30 à 50 % (v1.1.0)
- 🧠 **Analyse de code** - Analyse l’AST, extrait les signatures de fonctions, analyse les dépendances (v1.1.0)
- 🗜️ **Compression du contexte** - Compresse automatiquement l’historique des conversations, prend en charge les longues conversations sans dépassement de tokens (v1.1.0)
- 🔌 **Prise en charge du protocole MCP** - Intègre n’importe quels outils MCP, extensibilité illimitée (v1.2.0)
- 🎯 **Système d’experts par compétences** - Active automatiquement des capacités expertes selon la tâche, injecte des prompts et outils spécialisés (v1.4.0) ⭐ Nouveau

### 🛠️ Capacités des outils
- 📝 **Édition de code** - Modifie précisément des lignes spécifiques d’un fichier avec insertion/remplacement/suppression
- 🔍 **Recherche de code** - Recherche par regex avec affichage du contexte
- 🧪 **Exécution de tests** - Lance des suites de tests pytest/unittest
- ✨ **Linting de code** - Exécute les outils pylint/flake8/mypy/black
- 📁 **Opérations sur les fichiers** - Crée, lit (avec plages de lignes), liste les fichiers et répertoires (avec filtrage récursif)
- 🐍 **Exécution Python** - Exécute du code et des scripts Python
- 💻 **Commandes Shell** - Exécute des commandes système
- 🎯 **Achèvement de tâche** - Marque intelligemment le statut d’achèvement de la tâche
- 🎨 **Interface interactive** - Expérience d’utilisation conviviale basée sur des menus

## ✨ Fonctionnalités clés

### 🎯 v1.1.0 Nouvelles fonctionnalités principales
#### 📋 Planificateur de tâches
- **Génération intelligente de plans** - Génère automatiquement des plans structurés en 3 à 8 étapes avant l’exécution
- **Suivi de progression en temps réel** - Marque les étapes terminées avec un affichage clair de l’avancement
- **Gain d’efficacité de 30 à 50 %** - Réduit les appels d’outils inefficaces et améliore le taux de réussite
- **Repli automatique** - Bascule automatiquement en mode normal si la génération du plan échoue

#### 🧠 Outils d’analyse de code
- **parse_ast** - Analyse l’AST d’un fichier Python et extrait la structure des fonctions, classes et imports
- **get_function_signature** - Récupère la signature complète d’une fonction avec annotations de type
- **find_dependencies** - Analyse les dépendances d’un fichier (stdlib, bibliothèques tierces, modules locaux)
- **get_code_metrics** - Compte les lignes de code, fonctions et classes

#### 🗜️ Compresseur de contexte
- **Compression automatique** - Compresse automatiquement l’historique toutes les 5 interactions, en conservant intactes les 3 plus récentes
- **Résumé intelligent** - Extrait les informations clés (chemins de fichiers, appels d’outils, erreurs, tâches terminées)
- **Économie de tokens** - Réduit la consommation de tokens de 20 à 30 %, prend en charge des conversations plus longues
- **Intégration transparente** - Entièrement automatique, sans intervention manuelle

#### 🔌 Intégration du protocole MCP (Model Context Protocol) ⭐ v1.2.0 Nouveau
- **Extension sans code** - Intègre n’importe quels outils MCP via un fichier de configuration, sans modifier le code
- **Playwright préinstallé** - Automatisation de navigateur intégrée (navigation, capture d’écran, clic, formulaires)
- **Context7 préinstallé** - Gestion intelligente du contexte et recherche sémantique
- **Interface d’outils unifiée** - Les outils MCP sont automatiquement encapsulés comme objets Tool standard
- **Gestion du cycle de vie** - Démarre et arrête automatiquement les processus serveur MCP
- **Prise en charge des MCP courants** - Playwright, Context7, Filesystem, SQLite, etc.
- **Documentation détaillée** - Voir [MCP_GUIDE.md](MCP_GUIDE.md) pour le guide d’intégration complet

#### 🎯 Système d’experts par compétences ⭐ v1.4.0 Nouveau
- **Activation automatique** - Sélectionne et active automatiquement les compétences expertes pertinentes selon la description de la tâche
- **3 experts intégrés** - Expert Python, Expert Base de données, Expert Développement Frontend, prêts à l’emploi
- **Injection d’outils spécialisés** - Chaque compétence peut embarquer des outils spécialisés (par ex. `python_best_practices`, `sql_review`)
- **Amélioration des prompts** - Les compétences activées injectent automatiquement les meilleures pratiques du domaine dans le prompt système
- **Compétences personnalisées** - Prend en charge les fichiers de configuration JSON pour créer rapidement des compétences personnalisées, sans code
- **Extension par classe Python** - Pour les scénarios complexes, définissez des compétences comme classes Python avec outils personnalisés
- **Documentation détaillée** - Voir [SKILL_GUIDE.md](SKILL_GUIDE.md) pour le guide complet

### 🤖 Prise en charge de plusieurs modèles
- **DeepSeek** - Modèle par défaut, économique
- **OpenAI** - Modèles des séries GPT-3.5/GPT-4
- **Claude** - Modèles de la série Claude 3.5 d’Anthropic
- **Gemini** - Modèles de la série Google Gemini
- Prise en charge d’une Base URL personnalisée et de paramètres de modèle

### 🚀 Interface CLI interactive
- **Système de menus convivial** - Pas besoin de mémoriser des commandes complexes
- **Configuration en temps réel** - Ajustez dynamiquement les paramètres d’exécution
- **Sortie en couleur** - Interface claire et esthétique (prise en charge de colorama)
- **Visualiseur de liste d’outils** - Consultez tous les outils disponibles en un clic

### 🛠️ Ensemble d’outils puissant pour Code Agent

**Outils MCP** ⭐ v1.2.0 Nouveau
- `mcp_playwright_*` - Outils d’automatisation du navigateur (navigation, capture d’écran, clic, formulaires)
- `mcp_context7_*` - Outils intelligents de gestion du contexte (stockage, récupération, recherche)
- Prise en charge du chargement dynamique de n’importe quels outils MCP

**Outils d’analyse de code** (v1.1.0)
- `parse_ast` - Analyse la structure AST d’un fichier Python
- `get_function_signature` - Extrait la signature de fonction et les types
- `find_dependencies` - Analyse les dépendances d’un fichier
- `get_code_metrics` - Récupère les métriques du code

**Outils d’édition de code**
- `edit_file` - Modifie précisément des lignes spécifiques d’un fichier (insertion/remplacement/suppression)
- `search_in_file` - Recherche par regex avec affichage du contexte

**Outils de test et de linting**
- `run_tests` - Exécute des suites de tests pytest/unittest
- `run_linter` - Exécute les linters pylint/flake8/mypy/black

**Outils d’opérations sur les fichiers**
- `list_directory` - Liste le contenu d’un répertoire (avec filtrage récursif et par type)
- `read_file` - Lit des fichiers texte (avec plages de numéros de ligne)
- `create_file` - Crée ou écrase des fichiers

**Outils d’exécution de code**
- `run_python` - Exécute du code Python
- `run_shell` - Exécute des commandes Shell
- `task_complete` - Marque une tâche comme terminée

### 🎯 Utilisation flexible
- **Mode interactif** - Utilisation basée sur des menus, adaptée aux tâches continues
- **Mode conversation multi-tour** - Dialogue continu avec historique complet ⭐ Nouveau
- **Mode ligne de commande** - Exécution rapide de tâches uniques
- **Mode batch** - Prise en charge de l’automatisation par script
- **Configuration persistante** - Les réglages personnalisés sont sauvegardés de façon permanente ⭐ Nouveau

## 📋 Prérequis

- **Python 3.7+** (Python 3.9 ou supérieur recommandé)
- **Clé API LLM** - Choisissez selon le modèle :
  - [Clé API DeepSeek](https://platform.deepseek.com/) (par défaut)
  - [Clé API OpenAI](https://platform.openai.com/)
  - [Clé API Claude](https://console.anthropic.com/)
  - [Clé API Gemini](https://makersuite.google.com/app/apikey)

## 🔧 Installation

### 1. Cloner le dépôt

```bash
git clone <repository-url>
cd dm-agent
````

### 2. Installer les dépendances

```bash
pip install -r requirements.txt
```

**Dépendances** :

* `requests` - Bibliothèque HTTP pour appeler l’API LLM
* `python-dotenv` - Gestion des variables d’environnement
* `colorama` - Sortie terminal colorée (optionnelle mais recommandée)
* `google-generativeai` - SDK officiel Google Gemini

### 3. Configurer la clé API

Copiez le fichier `.env.example`, renommez-le en `.env`, puis ajoutez votre véritable clé API :

```bash
# Copier le fichier d’exemple
cp .env.example .env

# Modifier le fichier .env et configurer la clé correspondante selon le modèle utilisé
# DeepSeek (par défaut)
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# OpenAI (optionnel)
OPENAI_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx

# Claude (optionnel)
CLAUDE_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx

# Gemini (optionnel)
GEMINI_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxx
```

**⚠️ Avis de sécurité** :

* Le fichier `.env` contient votre clé API privée et est configuré dans `.gitignore` afin d’éviter qu’il soit commité dans Git
* Ne partagez pas le fichier `.env` avec d’autres personnes et ne le téléversez pas dans des dépôts publics
* Seul le fichier `.env.example` sera commité dans le dépôt comme modèle de configuration

Ou définissez la variable d’environnement en ligne de commande :

**Windows (PowerShell)** :

```powershell
$env:DEEPSEEK_API_KEY="your_api_key_here"
```

**Linux/macOS** :

```bash
export DEEPSEEK_API_KEY="your_api_key_here"
```

## 🚀 Démarrage rapide

### Mode interactif (recommandé)

Lancez le programme directement pour entrer dans l’interface de menu conviviale :

```bash
python main.py
```

Vous verrez :

```
======================================================================
              DM-Agent System
======================================================================
Welcome to the Multi-Model ReAct Agent System!

Main Menu:
  1. Execute New Task
  2. Multi-turn Conversation Mode
  3. View Available Tools
  4. Configuration Settings
  5. View Available Skills
  6. Exit Program

Please select an option (1-6):
```

### Mode ligne de commande (exécution rapide)

Exécutez directement des tâches depuis la ligne de commande :

```bash
# Utilisation de base (avec DeepSeek par défaut)
python main.py "Create a hello.py file that prints hello world"

# Utiliser OpenAI
python main.py "Your task" --provider openai --model gpt-4

# Utiliser Claude
python main.py "Your task" --provider claude --model claude-3-5-sonnet-20241022

# Utiliser Gemini
python main.py "Your task" --provider gemini --model gemini-1.5-flash

# Afficher les étapes détaillées
python main.py "Calculate 123 + 456" --show-steps

# Configuration personnalisée
python main.py "Your task" --max-steps 50 --temperature 0.5
```

## 📚 Exemples d’utilisation

#### Exemple de planificateur de tâches

```bash
python main.py "Create a complete calculator program with add, subtract, multiply, divide functions and tests"
```

Vous verrez :

```
📋 Generated Execution Plan:
Plan Progress: 0/5 steps completed

○ Step 1: create_file - Create calculator main program file
○ Step 2: edit_file - Add calculation functions
○ Step 3: create_file - Create test file
○ Step 4: run_tests - Run tests for verification
○ Step 5: task_complete - Complete task
```

#### Exemple d’outils d’analyse de code

```bash
# Analyser la structure d’un fichier
python main.py "Analyze the code structure of main.py and list all functions and classes"

# Extraire la signature d’une fonction
python main.py "Get the complete signature of the calculate function in calculator.py"

# Analyser les dépendances
python main.py "Analyze what third-party libraries main.py depends on"

# Obtenir les métriques de code
python main.py "Count the number of code lines in all Python files in the src directory"
```

#### Exemple de compression du contexte

En mode conversation multi-tour, compression automatique toutes les 5 interactions :

```
🗜️ Compressing conversation history to save tokens...
   Compression ratio: 62.5%, saved 10 messages
```

### Exemple 0.5 : Utilisation des outils MCP ⭐ v1.2.0

#### Exemple MCP Playwright (automatisation du navigateur)

```bash
# Ouvrir une page Web et enregistrer une capture d’écran
python main.py "Open https://www.example.com and save screenshot as example.png"

# Automatiser le remplissage d’un formulaire
python main.py "Open https://example.com/login, enter 'testuser' in username field, 'password123' in password field, then click login"

# Extraire des données d’une page Web
python main.py "Visit https://news.ycombinator.com and extract the top 10 news headlines"
```

#### Exemple MCP Context7 (gestion du contexte)

```bash
# Stocker du contexte
python main.py "Store the current project architecture information in Context7"

# Recherche sémantique
python main.py "Search for database-related contexts in Context7"

# Contexte associé
python main.py "Get historical contexts related to the current task"
```

#### Intégrer de nouveaux outils MCP

Seulement 3 étapes, sans code :

1. Éditez `mcp_config.json` pour ajouter la configuration
2. Redémarrez le système
3. Les outils deviennent automatiquement disponibles

Voir : [MCP_GUIDE.md](MCP_GUIDE.md)

### Exemple 0.6 : Système d’experts par compétences ⭐ v1.4.0

L’agent active automatiquement les compétences pertinentes selon la tâche, sans configuration manuelle :

```bash
# Activation automatique de l’expert Python
python main.py "Write a Python script to parse CSV files with type hints"
# 🎯 Activated skills: Python Expert

# Activation automatique de l’expert Base de données + Python
python main.py "Optimize the SQL queries in my Django project"
# 🎯 Activated skills: Python Expert, Database Expert

# Activation automatique de l’expert Frontend
python main.py "Create a React component to display a user list"
# 🎯 Activated skills: Frontend Dev Expert
```

#### Créer des compétences personnalisées

Créez simplement un fichier JSON dans le répertoire `dm_agent/skills/custom/` :

```json
{
  "name": "devops_expert",
  "display_name": "DevOps Expert",
  "description": "Docker, K8s, CI/CD best practices guidance",
  "keywords": ["docker", "kubernetes", "ci/cd", "deploy"],
  "prompt_addition": "You now have DevOps expert capabilities..."
}
```

Voir : [SKILL_GUIDE.md](SKILL_GUIDE.md)

### Exemple 1 : Édition de code

```bash
# Insérer du code à une ligne spécifique
python main.py "Insert a print statement at line 10 in test.py"

# Remplacer du code sur une plage de lignes
python main.py "Replace lines 5-8 in main.py with a new function implementation"

# Rechercher et modifier du code
python main.py "Search for all code containing 'TODO' in the project and list them"
```

### Exemple 2 : Tests et linting de code ⭐ Nouvelle fonctionnalité

```bash
# Exécuter des tests
python main.py "Run all test cases in the tests directory"

# Linting de code
python main.py "Check code quality in the src directory with flake8"

# Vérification de formatage
python main.py "Check if main.py conforms to black code style"
```

### Exemple 3 : Opérations sur les fichiers (amélioré)

```bash
# Lire une plage de lignes spécifique
python main.py "Read lines 10-20 of config.py"

# Lister récursivement les fichiers Python
python main.py "List all .py files in the project"

# Créer un fichier
python main.py "Create a file named notes.txt with today's date"
```

### Exemple 4 : Calcul mathématique

```bash
python main.py "Calculate the result of (100 + 200) * 3" --show-steps
```

### Exemple 5 : Exécution de code

```bash
python main.py "Use Python to generate 10 random numbers and save them to random.txt"
```

### Exemple 6 : Tâche complexe

```bash
python main.py "Create a sort folder with 10 sorting algorithm implementations in both C++ and Python"
```

### Exemple 7 : Multi-tour ⭐ Nouveau

```bash
python main.py
# Sélectionnez l’option 2 : mode conversation multi-tour
# Conversation 1: "Create a test.py file"
# Conversation 2: "Write a function to print Hello in that file"
# Conversation 3: "Run that file"
# L’agent se souviendra du contexte de test.py
```

## ⚙️ Arguments en ligne de commande

```
python main.py [task] [options]

Arguments positionnels :
  task                  Description de la tâche à exécuter (optionnel)

Arguments optionnels :
  -h, --help           Afficher le message d’aide
  --api-key KEY        Clé API
  --provider PROVIDER  Fournisseur LLM (deepseek/openai/claude/gemini, par défaut : deepseek) ⭐ Nouveau
  --model MODEL        Nom du modèle (par défaut selon le fournisseur)
  --base-url URL       URL de base de l’API (optionnelle, utilise celle du fournisseur par défaut) ⭐ Nouveau
  --max-steps N        Nombre maximal d’étapes (par défaut : 100)
  --temperature T      Température 0.0-2.0 (par défaut : 0.7)
  --show-steps         Afficher les étapes d’exécution
  --interactive        Forcer le mode interactif
```

**Remarque** : Les valeurs par défaut peuvent être modifiées de façon permanente via `config.json`

## 🎨 Fonctionnalités du menu interactif

### 1️⃣ Exécuter une nouvelle tâche

Saisissez une description de tâche ; l’agent l’exécutera automatiquement et affichera le résultat. Chaque exécution correspond à une nouvelle conversation.

### 2️⃣ Mode conversation multi-tour ⭐ Nouveau

Entrez en mode conversation continue où l’agent mémorise tout l’historique de la conversation ainsi que les résultats d’exécution des outils :

* Tapez `exit` pour quitter le mode conversation
* Tapez `reset` pour effacer l’historique
* L’agent mémorise les noms de fichiers, variables et autres informations de contexte

### 3️⃣ Voir la liste des outils

Consultez tous les outils disponibles et la description de leurs fonctions.

### 4️⃣ Paramètres de configuration ⭐ Amélioré

Ajustez dynamiquement les paramètres d’exécution et enregistrez-les éventuellement de façon permanente :

* **Fournisseur LLM** (provider) : deepseek/openai/claude/gemini ⭐ Nouveau
* **Nom du modèle** (model) : choisir selon le fournisseur
* **Base URL** (base_url) : URL de base de l’API ⭐ Nouveau
* **Max Steps** (max_steps) : 1-200 (par défaut : 100)
* **Temperature** (temperature) : 0.0-2.0 (par défaut : 0.7)
* **Show Steps** (show_steps) : Oui/Non

Après modification, vous pouvez choisir `y` pour enregistrer la configuration de façon permanente.
Elle sera sauvegardée dans le fichier `config.json` et chargée automatiquement au prochain démarrage.

### 5️⃣ Voir la liste des compétences ⭐ v1.4.0 Nouveau

Consultez toutes les compétences expertes disponibles ainsi que leur statut :

* Affiche le nom de la compétence, sa description, ses mots-clés et le nombre d’outils spécialisés
* Distingue les compétences intégrées et personnalisées
* Affiche le statut d’activation actuel

### 6️⃣ Quitter le programme

Quittez l’application en toute sécurité.

## ⚙️ Gestion de la configuration

### Configuration par défaut

* **Fournisseur LLM** : deepseek
* **Modèle** : deepseek-chat
* **Base URL** : [https://api.deepseek.com](https://api.deepseek.com)
* **Max Steps** : 100
* **Température** : 0.7
* **Show Steps** : No

### Configuration persistante

1. Démarrez le programme et sélectionnez « Configuration Settings »
2. Modifiez les paramètres selon les invites (y compris le changement de fournisseur de modèle)
3. Choisissez `y` pour enregistrer comme configuration permanente
4. La configuration est enregistrée dans le fichier `config.json`

Exemple de fichier de configuration (`config.json.example`) :

```json
{
  "provider": "deepseek",
  "model": "deepseek-chat",
  "base_url": "https://api.deepseek.com",
  "max_steps": 100,
  "temperature": 0.7,
  "show_steps": false
}
```

**Remarque** :

* Gemini utilise le SDK officiel Google et n’a pas besoin de configuration `base_url`
* Les autres fournisseurs peuvent personnaliser `base_url` selon les besoins (par ex. en utilisant un proxy)

**Astuce** : `config.json` est ajouté à `.gitignore` et ne sera pas commité dans git

## 💡 Conseils et astuces

1. **Tâches continues** - Utilisez le mode interactif pour éviter de redémarrer le programme à chaque fois
2. **Tâches de débogage** - Utilisez `--show-steps` pour voir le processus d’exécution détaillé
3. **Tâches expérimentales** - Augmentez la température pour obtenir des résultats plus créatifs
4. **Tâches complexes** - Augmentez max-steps pour autoriser davantage d’étapes de raisonnement (la valeur par défaut est 100)
5. **Tests rapides** - Le mode ligne de commande convient aux scripts et à l’automatisation

## 🔄 Structure du projet

```
dm-code-agent/
├── main.py                         # Point d’entrée principal du programme (CLI interactive)
├── check_mcp_env.py                # Outil de vérification de l’environnement MCP (v1.2.0)
├── dm_agent/                       # Package cœur de l’agent
│   ├── __init__.py                # Initialisation du package et API publique
│   ├── core/                      # Implémentation du cœur de l’agent
│   │   ├── __init__.py
│   │   ├── agent.py              # Logique centrale de ReactAgent
│   │   └── planner.py            # Planificateur de tâches (v1.1.0)
│   ├── clients/                   # Clients LLM
│   │   ├── __init__.py
│   │   ├── base_client.py        # Classe de base du client
│   │   ├── deepseek_client.py    # Client DeepSeek
│   │   ├── openai_client.py      # Client OpenAI
│   │   ├── claude_client.py      # Client Claude
│   │   ├── gemini_client.py      # Client Gemini
│   │   └── llm_factory.py        # Fabrique de clients
│   ├── mcp/                       # Intégration MCP (v1.2.0)
│   │   ├── __init__.py
│   │   ├── client.py             # Client MCP
│   │   ├── config.py             # Gestion de la configuration MCP
│   │   └── manager.py            # Gestionnaire MCP
│   ├── skills/                    # Système d’experts par compétences (v1.4.0) ⭐ Nouveau
│   │   ├── __init__.py           # Exports du module
│   │   ├── base.py               # Classe de base des compétences et métadonnées
│   │   ├── selector.py           # Sélecteur automatique de compétences
│   │   ├── manager.py            # Gestionnaire de compétences
│   │   ├── builtin/              # Compétences intégrées
│   │   │   ├── __init__.py
│   │   │   ├── python_expert.py  # Expert Python
│   │   │   ├── db_expert.py      # Expert Base de données
│   │   │   └── frontend_dev.py   # Expert Développement Frontend
│   │   └── custom/               # Compétences personnalisées (fichiers JSON)
│   │       └── .gitkeep
│   ├── memory/                    # Mémoire et gestion du contexte (v1.1.0)
│   │   ├── __init__.py
│   │   └── context_compressor.py # Compresseur de contexte
│   ├── tools/                     # Ensemble d’outils
│   │   ├── __init__.py
│   │   ├── base.py               # Classe de base des outils
│   │   ├── file_tools.py         # Outils d’opérations sur les fichiers
│   │   ├── code_analysis_tools.py # Outils d’analyse de code (v1.1.0)
│   │   └── execution_tools.py    # Outils d’exécution de code
│   └── prompts/                   # Gestion des prompts
│       ├── __init__.py
│       ├── system_prompts.py     # Fonctions de construction des prompts
│       └── code_agent_prompt.md  # Modèle de prompt
├── requirements.txt               # Dépendances Python
├── .env.example                   # Modèle de configuration des variables d’environnement
├── config.json.example            # Exemple de fichier de configuration
├── mcp_config.json.example        # Exemple de configuration MCP (v1.2.0)
├── .gitignore                     # Règles d’exclusion Git
├── MCP_GUIDE.md                   # Guide d’intégration MCP (v1.2.0)
├── SKILL_GUIDE.md                 # Guide du système de compétences (v1.4.0) ⭐ Nouveau
├── README.md                      # Documentation en chinois
└── README_EN.md                   # Documentation en anglais
```

## 🤝 Contribution

Les issues et les Pull Requests sont les bienvenues !

## 📄 Licence

Ce projet est distribué sous licence MIT.

**Commencez à apprendre les agents IA !** 🚀

```
