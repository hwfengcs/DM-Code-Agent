"""Built-in L2 coding benchmark tasks."""

from __future__ import annotations

from typing import Iterable, List, Optional

from .models import BenchmarkTask

COMMON_PROMPT_SUFFIX = (
    "\n\nYou are in a temporary benchmark workspace. Inspect the files, modify the "
    "implementation, and run the visible tests. Hidden tests will be added after "
    "you finish, so handle edge cases from the task description rather than hard-coding "
    "the visible tests. Finish only when the implementation is ready."
)


BUILTIN_CODING_TASKS: List[BenchmarkTask] = [
    BenchmarkTask(
        task_id="slugify_cleanup",
        name="Robust slugify cleanup",
        prompt=(
            "Fix text_utils.slugify. It should lowercase text, replace every run of "
            "non-alphanumeric characters with one hyphen, collapse repeated separators, "
            "and strip leading/trailing hyphens." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "text_utils.py": (
                "def slugify(value: str) -> str:\n"
                '    """Return a URL slug for the input text."""\n'
                '    return value.strip().lower().replace(" ", "-")\n'
            ),
            "tests/test_public_slugify.py": (
                "from text_utils import slugify\n\n\n"
                "def test_basic_words():\n"
                '    assert slugify("Hello World") == "hello-world"\n\n\n'
                "def test_trims_edges():\n"
                '    assert slugify("  Already Slug  ") == "already-slug"\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_slugify.py": (
                "from text_utils import slugify\n\n\n"
                "def test_punctuation_and_repeated_spaces():\n"
                '    assert slugify("Python & AI Agents!") == "python-ai-agents"\n'
                '    assert slugify("many     spaces") == "many-spaces"\n\n\n'
                "def test_strips_generated_separators():\n"
                '    assert slugify("--Hello__World--") == "hello-world"\n'
                '    assert slugify("!!!") == ""\n'
            )
        },
        max_steps=12,
        tags=["bugfix", "string", "hidden-tests"],
    ),
    BenchmarkTask(
        task_id="order_total_edges",
        name="Order total business rules",
        prompt=(
            "Fix orders.order_total and apply_discount. Discount is a percentage from "
            "0 to 100, applied before tax. Quantity defaults to 1. Return totals rounded "
            "to two decimals. Raise ValueError for invalid discount percentages."
            + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "orders.py": (
                "def apply_discount(subtotal: float, discount_percent: float) -> float:\n"
                "    return subtotal - discount_percent\n\n\n"
                "def order_total(items, discount_percent: float = 0, tax_rate: float = 0):\n"
                '    subtotal = sum(item["price"] * item.get("quantity", 1) for item in items)\n'
                "    discounted = apply_discount(subtotal, discount_percent)\n"
                "    return round(discounted * (1 + tax_rate), 2)\n"
            ),
            "tests/test_public_orders.py": (
                "import pytest\n\n"
                "from orders import order_total\n\n\n"
                "def test_total_without_discount():\n"
                '    items = [{"price": 10, "quantity": 2}, {"price": 5}]\n'
                "    assert order_total(items) == 25\n\n\n"
                "def test_percentage_discount():\n"
                '    assert order_total([{"price": 20}], discount_percent=10) == 18\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_orders.py": (
                "import pytest\n\n"
                "from orders import order_total\n\n\n"
                "def test_tax_after_discount():\n"
                '    assert order_total([{"price": 50, "quantity": 2}], 25, 0.10) == 82.5\n\n\n'
                "def test_invalid_discount_range():\n"
                "    with pytest.raises(ValueError):\n"
                '        order_total([{"price": 10}], -1)\n'
                "    with pytest.raises(ValueError):\n"
                '        order_total([{"price": 10}], 101)\n'
            )
        },
        max_steps=14,
        tags=["bugfix", "business-logic", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="ttl_cache_lru",
        name="TTL cache with LRU eviction",
        prompt=(
            "Complete TTLCache in cache.py. get should return the default for missing or "
            "expired keys. Entries older than ttl_seconds expire. When max_size is exceeded, "
            "evict the least recently used live entry. A successful get should update recency."
            + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "cache.py": (
                "import time\n\n\n"
                "class TTLCache:\n"
                "    def __init__(self, max_size: int = 128, ttl_seconds: float = 60, clock=None):\n"
                "        self.max_size = max_size\n"
                "        self.ttl_seconds = ttl_seconds\n"
                "        self.clock = clock or time.monotonic\n"
                "        self._data = {}\n\n"
                "    def set(self, key, value):\n"
                "        self._data[key] = (value, self.clock())\n\n"
                "    def get(self, key, default=None):\n"
                "        return self._data.get(key, (default, 0))[0]\n"
            ),
            "tests/test_public_cache.py": (
                "from cache import TTLCache\n\n\n"
                "class Clock:\n"
                "    def __init__(self):\n"
                "        self.now = 0\n"
                "    def __call__(self):\n"
                "        return self.now\n\n\n"
                "def test_get_set_returns_value():\n"
                "    clock = Clock()\n"
                "    cache = TTLCache(ttl_seconds=10, clock=clock)\n"
                '    cache.set("a", 1)\n'
                '    assert cache.get("a") == 1\n\n\n'
                "def test_expired_value_returns_default():\n"
                "    clock = Clock()\n"
                "    cache = TTLCache(ttl_seconds=5, clock=clock)\n"
                '    cache.set("a", 1)\n'
                "    clock.now = 6\n"
                '    assert cache.get("a", "missing") == "missing"\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_cache.py": (
                "from cache import TTLCache\n\n\n"
                "class Clock:\n"
                "    def __init__(self):\n"
                "        self.now = 0\n"
                "    def __call__(self):\n"
                "        return self.now\n\n\n"
                "def test_lru_eviction_uses_recent_gets():\n"
                "    clock = Clock()\n"
                "    cache = TTLCache(max_size=2, ttl_seconds=100, clock=clock)\n"
                '    cache.set("a", 1)\n'
                '    cache.set("b", 2)\n'
                '    assert cache.get("a") == 1\n'
                '    cache.set("c", 3)\n'
                '    assert cache.get("b") is None\n'
                '    assert cache.get("a") == 1\n'
                '    assert cache.get("c") == 3\n\n\n'
                "def test_expired_entries_are_removed_before_evicting_live_entries():\n"
                "    clock = Clock()\n"
                "    cache = TTLCache(max_size=2, ttl_seconds=5, clock=clock)\n"
                '    cache.set("old", 1)\n'
                "    clock.now = 6\n"
                '    cache.set("new", 2)\n'
                '    cache.set("third", 3)\n'
                '    assert cache.get("old") is None\n'
                '    assert cache.get("new") == 2\n'
                '    assert cache.get("third") == 3\n'
            )
        },
        max_steps=18,
        tags=["stateful", "algorithm", "hidden-tests"],
    ),
    BenchmarkTask(
        task_id="normalize_users",
        name="Normalize imported user records",
        prompt=(
            "Fix users.normalize_users. It should return active users only, skip rows with "
            "invalid emails, trim names, lowercase and trim emails, deduplicate by email "
            "keeping the first active record, and sort the result by email." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "users.py": (
                "def normalize_users(rows):\n"
                "    users = []\n"
                "    for row in rows:\n"
                "        users.append({\n"
                '            "email": row["email"],\n'
                '            "name": row.get("name", ""),\n'
                '            "active": row.get("active", True),\n'
                "        })\n"
                "    return users\n"
            ),
            "tests/test_public_users.py": (
                "from users import normalize_users\n\n\n"
                "def test_trims_and_lowercases_email_and_name():\n"
                '    rows = [{"email": "  Ada@Example.COM ", "name": " Ada "}]\n'
                "    assert normalize_users(rows) == [\n"
                '        {"email": "ada@example.com", "name": "Ada"}\n'
                "    ]\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_users.py": (
                "from users import normalize_users\n\n\n"
                "def test_filters_deduplicates_and_sorts():\n"
                "    rows = [\n"
                '        {"email": "b@example.com", "name": " Bea ", "active": True},\n'
                '        {"email": "invalid", "name": "Skip", "active": True},\n'
                '        {"email": "a@example.com", "name": "Ann", "active": False},\n'
                '        {"email": "A@Example.com", "name": "Ada", "active": True},\n'
                '        {"email": "b@example.com", "name": "Duplicate", "active": True},\n'
                "    ]\n"
                "    assert normalize_users(rows) == [\n"
                '        {"email": "a@example.com", "name": "Ada"},\n'
                '        {"email": "b@example.com", "name": "Bea"},\n'
                "    ]\n"
            )
        },
        max_steps=14,
        tags=["data-cleaning", "dedupe", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="stats_summary",
        name="Statistics summary edge cases",
        prompt=(
            "Fix stats.summarize. Return a dictionary with count, min, max, mean, and median. "
            "For an empty input, return count 0 and None for the numeric fields. Support odd "
            "and even sized inputs without mutating the caller's list." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "stats.py": (
                "def summarize(numbers):\n"
                "    return {\n"
                '        "count": len(numbers),\n'
                '        "min": min(numbers),\n'
                '        "max": max(numbers),\n'
                '        "mean": sum(numbers) / len(numbers),\n'
                "    }\n"
            ),
            "tests/test_public_stats.py": (
                "from stats import summarize\n\n\n"
                "def test_odd_count_summary():\n"
                "    assert summarize([3, 1, 2]) == {\n"
                '        "count": 3,\n'
                '        "min": 1,\n'
                '        "max": 3,\n'
                '        "mean": 2,\n'
                '        "median": 2,\n'
                "    }\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_stats.py": (
                "from stats import summarize\n\n\n"
                "def test_even_count_and_original_order_is_preserved():\n"
                "    data = [10, 2, 4, 8]\n"
                '    assert summarize(data)["median"] == 6\n'
                "    assert data == [10, 2, 4, 8]\n\n\n"
                "def test_empty_input():\n"
                "    assert summarize([]) == {\n"
                '        "count": 0,\n'
                '        "min": None,\n'
                '        "max": None,\n'
                '        "mean": None,\n'
                '        "median": None,\n'
                "    }\n"
            )
        },
        max_steps=14,
        tags=["algorithm", "edge-cases", "regression"],
    ),
    BenchmarkTask(
        task_id="inventory_reservations",
        name="Inventory reservation semantics",
        prompt=(
            "Fix inventory.Inventory. add should accumulate stock. reserve should return True "
            "and decrement stock when enough units exist, including exact matches. It should "
            "return False for unknown or insufficient stock. Negative quantities are invalid."
            + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "inventory.py": (
                "class Inventory:\n"
                "    def __init__(self):\n"
                "        self.stock = {}\n\n"
                "    def add(self, sku: str, quantity: int) -> None:\n"
                "        self.stock[sku] = quantity\n\n"
                "    def reserve(self, sku: str, quantity: int) -> bool:\n"
                "        if self.stock.get(sku, 0) <= quantity:\n"
                "            return False\n"
                "        self.stock[sku] -= quantity\n"
                "        return True\n"
            ),
            "tests/test_public_inventory.py": (
                "from inventory import Inventory\n\n\n"
                "def test_reserve_decrements_stock():\n"
                "    inv = Inventory()\n"
                '    inv.add("book", 3)\n'
                '    assert inv.reserve("book", 2) is True\n'
                '    assert inv.stock["book"] == 1\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_inventory.py": (
                "import pytest\n\n"
                "from inventory import Inventory\n\n\n"
                "def test_add_accumulates_and_exact_match_reserves():\n"
                "    inv = Inventory()\n"
                '    inv.add("pen", 2)\n'
                '    inv.add("pen", 3)\n'
                '    assert inv.reserve("pen", 5) is True\n'
                '    assert inv.stock["pen"] == 0\n\n\n'
                "def test_invalid_and_insufficient_quantities():\n"
                "    inv = Inventory()\n"
                '    inv.add("bag", 1)\n'
                '    assert inv.reserve("missing", 1) is False\n'
                '    assert inv.reserve("bag", 2) is False\n'
                "    with pytest.raises(ValueError):\n"
                '        inv.add("bag", -1)\n'
                "    with pytest.raises(ValueError):\n"
                '        inv.reserve("bag", -1)\n'
            )
        },
        max_steps=14,
        tags=["stateful", "business-logic", "edge-cases"],
    ),
]

MAINTENANCE_PROMPT_SUFFIX = (
    "\n\nYou are in a temporary repository that mimics a real maintenance task. "
    "Inspect the files, make the smallest production-quality change, update tests when "
    "the task asks for a regression test, and run the visible tests. Hidden tests will "
    "be added after you finish, so preserve public behavior and handle edge cases."
)


BUILTIN_MAINTENANCE_TASKS: List[BenchmarkTask] = [
    BenchmarkTask(
        task_id="config_precedence",
        name="Configuration precedence and type coercion",
        prompt=(
            "Fix config_loader.load_config. Configuration precedence must be defaults < "
            "file_config < environment variables < CLI args. Coerce timeout to int and "
            "debug to bool for values from env or CLI." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "config_loader.py": (
                "import os\n\n"
                'DEFAULTS = {"timeout": 30, "debug": False, "retries": 2}\n\n\n'
                "def load_config(file_config=None, env=None, cli_args=None):\n"
                "    env = env or os.environ\n"
                "    file_config = file_config or {}\n"
                "    cli_args = cli_args or {}\n"
                "    config = DEFAULTS.copy()\n"
                "    config.update(cli_args)\n"
                "    config.update(file_config)\n"
                '    if "DM_TIMEOUT" in env:\n'
                '        config["timeout"] = env["DM_TIMEOUT"]\n'
                '    if "DM_DEBUG" in env:\n'
                '        config["debug"] = env["DM_DEBUG"]\n'
                "    return config\n"
            ),
            "tests/test_public_config_loader.py": (
                "from config_loader import load_config\n\n\n"
                "def test_file_overrides_defaults():\n"
                '    assert load_config({"timeout": 10})["timeout"] == 10\n\n\n'
                "def test_env_overrides_file_and_coerces_timeout():\n"
                '    result = load_config({"timeout": 10}, env={"DM_TIMEOUT": "15"})\n'
                '    assert result["timeout"] == 15\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_config_loader.py": (
                "from config_loader import load_config\n\n\n"
                "def test_cli_overrides_env_and_file():\n"
                "    result = load_config(\n"
                '        {"timeout": 10, "debug": False},\n'
                '        env={"DM_TIMEOUT": "20", "DM_DEBUG": "false"},\n'
                '        cli_args={"timeout": "5", "debug": "true"},\n'
                "    )\n"
                '    assert result["timeout"] == 5\n'
                '    assert result["debug"] is True\n\n\n'
                "def test_defaults_are_not_mutated_between_runs():\n"
                '    load_config({"retries": 9})\n'
                '    assert load_config({})["retries"] == 2\n'
            )
        },
        max_steps=16,
        tags=["maintenance", "config", "regression"],
        allowed_changed_files=["config_loader.py"],
    ),
    BenchmarkTask(
        task_id="patch_summary_name_status",
        name="Git name-status patch summary",
        prompt=(
            "Fix patch_summary.summarize_name_status so it can be used in a run report. "
            "It should parse git diff --name-status style lines, group added/modified/"
            "deleted/renamed files, ignore blank lines, and keep deterministic ordering."
            + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "patch_summary.py": (
                "def summarize_name_status(lines):\n"
                '    summary = {"added": [], "modified": [], "deleted": [], "renamed": []}\n'
                "    for line in lines:\n"
                '        status, path = line.split("\\t")\n'
                '        if status == "A":\n'
                '            summary["added"].append(path)\n'
                '        elif status == "M":\n'
                '            summary["modified"].append(path)\n'
                '        elif status == "D":\n'
                '            summary["deleted"].append(path)\n'
                "    return summary\n"
            ),
            "tests/test_public_patch_summary.py": (
                "from patch_summary import summarize_name_status\n\n\n"
                "def test_basic_name_status_groups():\n"
                "    result = summarize_name_status([\n"
                '        "A\\tdocs/tracing.md",\n'
                '        "M\\tdm_agent/core/agent.py",\n'
                '        "D\\told.py",\n'
                "    ])\n"
                '    assert result["added"] == ["docs/tracing.md"]\n'
                '    assert result["modified"] == ["dm_agent/core/agent.py"]\n'
                '    assert result["deleted"] == ["old.py"]\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_patch_summary.py": (
                "from patch_summary import summarize_name_status\n\n\n"
                "def test_renames_and_blank_lines_are_supported():\n"
                "    result = summarize_name_status([\n"
                '        "",\n'
                '        "R100\\told_name.py\\tnew_name.py",\n'
                '        "M\\tz_last.py",\n'
                '        "M\\ta_first.py",\n'
                "    ])\n"
                '    assert result["renamed"] == [\n'
                '        {"from": "old_name.py", "to": "new_name.py"}\n'
                "    ]\n"
                '    assert result["modified"] == ["a_first.py", "z_last.py"]\n\n\n'
                "def test_unknown_status_is_reported():\n"
                '    result = summarize_name_status(["??\\tuntracked.txt"])\n'
                '    assert result["unknown"] == [{"status": "??", "path": "untracked.txt"}]\n'
            )
        },
        max_steps=16,
        tags=["maintenance", "git", "reporting"],
        allowed_changed_files=["patch_summary.py"],
    ),
    BenchmarkTask(
        task_id="retry_regression_tests",
        name="Retry policy fix with regression tests",
        prompt=(
            "Fix retry.should_retry and add regression coverage in tests/test_retry.py. "
            "Retry should be allowed for exceptions, HTTP 408, HTTP 429, and 5xx responses, "
            "but only while attempt < max_attempts. Do not retry ordinary 4xx responses."
            + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "retry.py": (
                "def should_retry(status_code=None, exception=None, attempt=1, max_attempts=3):\n"
                "    if attempt > max_attempts:\n"
                "        return False\n"
                "    if exception is not None:\n"
                "        return True\n"
                "    if status_code is None:\n"
                "        return False\n"
                "    return status_code >= 500\n"
            ),
            "tests/test_retry.py": (
                "from retry import should_retry\n\n\n"
                "def test_retries_server_errors():\n"
                "    assert should_retry(status_code=503, attempt=1, max_attempts=3) is True\n\n\n"
                "def test_does_not_retry_bad_request():\n"
                "    assert should_retry(status_code=400, attempt=1, max_attempts=3) is False\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_retry.py": (
                "from retry import should_retry\n\n\n"
                "def test_retry_policy_includes_timeout_and_rate_limit():\n"
                "    assert should_retry(status_code=408, attempt=1, max_attempts=3) is True\n"
                "    assert should_retry(status_code=429, attempt=2, max_attempts=3) is True\n\n\n"
                "def test_retry_budget_is_attempt_less_than_max_attempts():\n"
                "    assert should_retry(status_code=503, attempt=3, max_attempts=3) is False\n"
                '    assert should_retry(exception=RuntimeError("boom"), attempt=3, max_attempts=3) is False\n\n\n'
                "def test_exception_retries_before_budget_is_exhausted():\n"
                "    assert should_retry(exception=TimeoutError(), attempt=1, max_attempts=2) is True\n"
            )
        },
        max_steps=18,
        tags=["maintenance", "tests", "networking"],
        allowed_changed_files=["retry.py", "tests/test_retry.py"],
        required_changed_files=["retry.py", "tests/test_retry.py"],
    ),
    BenchmarkTask(
        task_id="safe_workspace_join",
        name="Workspace path traversal guard",
        prompt=(
            "Fix workspace.safe_join. It should resolve a user-supplied relative path inside "
            "the workspace root and raise ValueError for absolute paths or traversal outside "
            "the root. The implementation must work for sibling paths with similar prefixes."
            + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "workspace.py": (
                "from pathlib import Path\n\n\n"
                "def safe_join(root, requested):\n"
                "    root_path = Path(root).resolve()\n"
                '    candidate = Path(str(root_path) + "/" + requested).resolve()\n'
                "    if not str(candidate).startswith(str(root_path)):\n"
                '        raise ValueError("path escapes workspace")\n'
                "    return candidate\n"
            ),
            "tests/test_public_workspace.py": (
                "from pathlib import Path\n\n"
                "import pytest\n\n"
                "from workspace import safe_join\n\n\n"
                "def test_allows_nested_relative_path(tmp_path):\n"
                '    assert safe_join(tmp_path, "src/app.py") == tmp_path / "src" / "app.py"\n\n\n'
                "def test_blocks_parent_traversal(tmp_path):\n"
                "    with pytest.raises(ValueError):\n"
                '        safe_join(tmp_path, "../outside.txt")\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_workspace.py": (
                "from pathlib import Path\n\n"
                "import pytest\n\n"
                "from workspace import safe_join\n\n\n"
                "def test_blocks_absolute_path(tmp_path):\n"
                "    with pytest.raises(ValueError):\n"
                '        safe_join(tmp_path, str(tmp_path.parent / "outside.txt"))\n\n\n'
                "def test_blocks_sibling_prefix_escape(tmp_path):\n"
                '    root = tmp_path / "repo"\n'
                "    root.mkdir()\n"
                '    sibling = tmp_path / "repo-other" / "file.txt"\n'
                "    with pytest.raises(ValueError):\n"
                '        safe_join(root, "../repo-other/file.txt")\n\n\n'
                "def test_normalizes_dot_segments_inside_root(tmp_path):\n"
                '    assert safe_join(tmp_path, "src/../README.md") == tmp_path / "README.md"\n'
            )
        },
        max_steps=16,
        tags=["maintenance", "security", "filesystem"],
        allowed_changed_files=["workspace.py"],
    ),
    BenchmarkTask(
        task_id="cross_file_user_contract",
        name="Cross-file user serialization contract",
        prompt=(
            "Fix the user serialization flow across users.py and serializers.py. "
            "serialize_user should return id, display_name, and email. display_name should "
            "come from a User.display_name method that joins first and last names, trims "
            "extra whitespace, and falls back to email when both names are blank. Preserve "
            "the public output keys." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "users.py": (
                "class User:\n"
                "    def __init__(self, user_id, first_name, last_name, email):\n"
                "        self.user_id = user_id\n"
                "        self.first_name = first_name\n"
                "        self.last_name = last_name\n"
                "        self.email = email\n"
            ),
            "serializers.py": (
                "def serialize_user(user):\n"
                "    return {\n"
                '        "id": user.user_id,\n'
                '        "display_name": user.name,\n'
                '        "email": user.email,\n'
                "    }\n"
            ),
            "tests/test_public_user_serializers.py": (
                "from serializers import serialize_user\n"
                "from users import User\n\n\n"
                "def test_serialize_user_uses_full_name():\n"
                '    user = User(1, "Ada", "Lovelace", "ada@example.com")\n'
                "    assert serialize_user(user) == {\n"
                '        "id": 1,\n'
                '        "display_name": "Ada Lovelace",\n'
                '        "email": "ada@example.com",\n'
                "    }\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_user_serializers.py": (
                "from serializers import serialize_user\n"
                "from users import User\n\n\n"
                "def test_display_name_trims_missing_parts():\n"
                '    user = User(2, " Grace ", " ", "grace@example.com")\n'
                '    assert serialize_user(user)["display_name"] == "Grace"\n\n\n'
                "def test_display_name_falls_back_to_email():\n"
                '    user = User(3, " ", "", "missing@example.com")\n'
                '    assert serialize_user(user)["display_name"] == "missing@example.com"\n'
            )
        },
        max_steps=18,
        tags=["maintenance", "cross-file", "code-understanding"],
        allowed_changed_files=["users.py", "serializers.py"],
        required_changed_files=["users.py", "serializers.py"],
    ),
]

BENCHMARK_SUITES = {
    "coding": BUILTIN_CODING_TASKS,
    "maintenance": BUILTIN_MAINTENANCE_TASKS,
}


def get_coding_tasks(task_ids: Optional[Iterable[str]] = None) -> List[BenchmarkTask]:
    return get_benchmark_tasks("coding", task_ids)


def get_maintenance_tasks(task_ids: Optional[Iterable[str]] = None) -> List[BenchmarkTask]:
    return get_benchmark_tasks("maintenance", task_ids)


def get_benchmark_tasks(
    suite: str = "coding", task_ids: Optional[Iterable[str]] = None
) -> List[BenchmarkTask]:
    if suite not in BENCHMARK_SUITES:
        available = ", ".join(sorted(BENCHMARK_SUITES))
        raise ValueError(f"unknown benchmark suite: {suite}. Available suites: {available}")

    tasks = list(BENCHMARK_SUITES[suite])
    if task_ids:
        allowed = set(task_ids)
        tasks = [task for task in tasks if task.task_id in allowed]
    return tasks
