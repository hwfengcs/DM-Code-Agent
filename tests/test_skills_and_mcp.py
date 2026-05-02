import json

from dm_agent.mcp.config import MCPConfig, MCPServerConfig
from dm_agent.skills import ConfigSkill, SkillManager
from dm_agent.skills.selector import SkillSelector


def test_skill_selector_uses_keywords_and_patterns():
    python_skill = ConfigSkill(
        {
            "name": "python_expert",
            "display_name": "Python Expert",
            "description": "Python help",
            "keywords": ["python", "pytest"],
            "patterns": [r"\.py\b"],
            "priority": 1,
        }
    )
    db_skill = ConfigSkill(
        {
            "name": "db_expert",
            "display_name": "DB Expert",
            "description": "Database help",
            "keywords": ["sql"],
            "priority": 5,
        }
    )

    selector = SkillSelector(max_active_skills=1, min_keyword_score=0.01)
    selected = selector.select(
        "write pytest coverage for app.py",
        {"python_expert": python_skill, "db_expert": db_skill},
    )

    assert selected == ["python_expert"]


def test_skill_manager_loads_custom_json(tmp_path):
    skill_file = tmp_path / "devops.json"
    skill_file.write_text(
        json.dumps(
            {
                "name": "devops_expert",
                "display_name": "DevOps Expert",
                "description": "Docker and CI guidance",
                "keywords": ["docker", "ci"],
                "prompt_addition": "Prefer reproducible deployment steps.",
            }
        ),
        encoding="utf-8",
    )

    manager = SkillManager()
    assert manager.load_custom_skills(tmp_path) == 1
    manager.activate_skills(["devops_expert"])

    assert "devops_expert" in manager.skills
    assert "reproducible deployment" in manager.get_active_prompt_additions()


def test_mcp_config_round_trip_and_enabled_filter():
    config = MCPConfig()
    config.add_server(MCPServerConfig("enabled", "npx", ["tool"], enabled=True))
    config.add_server(MCPServerConfig("disabled", "npx", ["tool"], enabled=False))

    data = config.to_dict()
    restored = MCPConfig.from_dict(data)

    assert set(restored.servers) == {"enabled", "disabled"}
    assert list(restored.get_enabled_servers()) == ["enabled"]
