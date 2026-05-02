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


def get_coding_tasks(task_ids: Optional[Iterable[str]] = None) -> List[BenchmarkTask]:
    tasks = list(BUILTIN_CODING_TASKS)
    if task_ids:
        allowed = set(task_ids)
        tasks = [task for task in tasks if task.task_id in allowed]
    return tasks
