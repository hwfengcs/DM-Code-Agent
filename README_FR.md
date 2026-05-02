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

Licence MIT. Voir [LICENSE](LICENSE).
