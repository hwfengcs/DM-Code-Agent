# DM-Code-Agent

**Framework Python leger, extensible et testable pour creer un Code Agent.**

DM-Code-Agent implemente une boucle ReAct lisible et connecte plusieurs fournisseurs LLM,
un planificateur de taches, des outils locaux, MCP, un systeme de skills, la compression de
contexte et une interface CLI.

Documentation principale:

- [README chinois](README.md)
- [README anglais](README_EN.md)
- [Guide MCP](MCP_GUIDE.md)
- [Guide Skill](SKILL_GUIDE.md)
- [Evals](evals/README.md)

## Demarrage rapide

```bash
git clone https://github.com/hwfengcs/DM-Code-Agent.git
cd DM-Code-Agent
python -m venv .venv
pip install -e ".[dev]"
cp .env.example .env
dm-agent --help
```

Ajoutez une cle API dans `.env`, puis lancez:

```bash
dm-agent "Analyze the current project structure" --provider deepseek --show-steps
```

## Verification locale

```bash
python -m compileall dm_agent main.py tests
python -m pytest
python -m dm_agent.evals.cli --variant full --task direct_finish
python -m ruff check .
python -m black --check .
```

## Historique des versions

- **v1.5.0** — version initiale: boucle ReAct + planificateur + compression de contexte, 4 fournisseurs LLM, MCP, skills, traces JSONL, benchmarks et evals sans cle API.
- **v1.6.0** — gouvernance et lancement v2: CHANGELOG, journaux de recherche (`docs/research-log/`).
- **v1.7.x** — harnais SWE-bench Lite et premiere baseline Tier-1 publique (0.0% resolved / 72.0% patch-applied, hors classement officiel).
- **v2.0.0** — pile algorithmique: Reflexion, Critic, Self-Consistency, Adaptive Replanning (desactives par defaut); gel des scores reels non executes.
- **Apres v2.0** — retrait complet de la chaine RAG (remplacee par une memoire locale de style Mem0); garde-fous de contexte long, tolerance aux pannes (retry unifie, ecritures atomiques, checkpoint/resume) et boucle d'evaluation avec portes CI.

Details complets: [CHANGELOG.md](CHANGELOG.md).

Licence MIT. Voir [LICENSE](LICENSE).
