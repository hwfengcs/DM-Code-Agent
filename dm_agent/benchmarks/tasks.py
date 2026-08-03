"""Built-in L2 coding benchmark tasks."""

from __future__ import annotations

from collections.abc import Iterable

from .models import BenchmarkTask

COMMON_PROMPT_SUFFIX = (
    "\n\nYou are in a temporary benchmark workspace. Inspect the files, modify the "
    "implementation, and run the visible tests. Hidden tests will be added after "
    "you finish, so handle edge cases from the task description rather than hard-coding "
    "the visible tests. Finish only when the implementation is ready."
)


BUILTIN_CODING_TASKS: list[BenchmarkTask] = [
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
    BenchmarkTask(
        task_id="parse_duration",
        name="Human duration string parsing",
        prompt=(
            "Fix durations.parse_duration. It parses strings like '1h30m', '45s', "
            "'2d', '1h 30m 15s' into whole seconds. Units are d/h/m/s and may appear "
            "in any order but never repeat. Whitespace between parts is optional. "
            "A bare integer means seconds. Raise ValueError on an empty string, an "
            "unknown unit, a repeated unit, or a negative number." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "durations.py": (
                "UNITS = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}\n\n\n"
                "def parse_duration(text: str) -> int:\n"
                '    """Parse a human duration string into seconds."""\n'
                "    total = 0\n"
                "    number = ''\n"
                "    for char in text:\n"
                "        if char.isdigit():\n"
                "            number += char\n"
                "        elif char in UNITS:\n"
                "            total += int(number) * UNITS[char]\n"
                "            number = ''\n"
                "    return total\n"
            ),
            "tests/test_public_durations.py": (
                "from durations import parse_duration\n\n\n"
                "def test_single_unit():\n"
                '    assert parse_duration("45s") == 45\n'
                '    assert parse_duration("2d") == 172800\n\n\n'
                "def test_combined_units():\n"
                '    assert parse_duration("1h30m") == 5400\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_durations.py": (
                "import pytest\n\n"
                "from durations import parse_duration\n\n\n"
                "def test_spaces_and_three_parts():\n"
                '    assert parse_duration("1h 30m 15s") == 5415\n'
                '    assert parse_duration("  2m10s  ") == 130\n\n\n'
                "def test_bare_integer_is_seconds():\n"
                '    assert parse_duration("90") == 90\n\n\n'
                "def test_units_may_appear_in_any_order():\n"
                '    assert parse_duration("30m1h") == 5400\n\n\n'
                "def test_rejects_bad_input():\n"
                "    with pytest.raises(ValueError):\n"
                '        parse_duration("")\n'
                "    with pytest.raises(ValueError):\n"
                '        parse_duration("10x")\n'
                "    with pytest.raises(ValueError):\n"
                '        parse_duration("1h2h")\n'
                "    with pytest.raises(ValueError):\n"
                '        parse_duration("-5s")\n'
            )
        },
        max_steps=14,
        tags=["parsing", "string", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="merge_intervals",
        name="Interval merging with touching ranges",
        prompt=(
            "Fix intervals.merge. It takes a list of (start, end) tuples and returns a "
            "new sorted list where overlapping AND touching intervals are merged: "
            "(1, 3) and (3, 5) become (1, 5). The input may be unsorted and must not be "
            "mutated. An empty list returns an empty list. Raise ValueError if any "
            "interval has start > end." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "intervals.py": (
                "def merge(intervals):\n"
                '    """Merge overlapping intervals."""\n'
                "    if not intervals:\n"
                "        return []\n"
                "    intervals.sort()\n"
                "    merged = [intervals[0]]\n"
                "    for start, end in intervals[1:]:\n"
                "        last_start, last_end = merged[-1]\n"
                "        if start < last_end:\n"
                "            merged[-1] = (last_start, max(last_end, end))\n"
                "        else:\n"
                "            merged.append((start, end))\n"
                "    return merged\n"
            ),
            "tests/test_public_intervals.py": (
                "from intervals import merge\n\n\n"
                "def test_overlapping():\n"
                "    assert merge([(1, 4), (2, 6)]) == [(1, 6)]\n\n\n"
                "def test_disjoint():\n"
                "    assert merge([(1, 2), (5, 6)]) == [(1, 2), (5, 6)]\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_intervals.py": (
                "import pytest\n\n"
                "from intervals import merge\n\n\n"
                "def test_touching_intervals_are_merged():\n"
                "    assert merge([(1, 3), (3, 5)]) == [(1, 5)]\n\n\n"
                "def test_unsorted_input_is_handled():\n"
                "    assert merge([(5, 6), (1, 3), (2, 4)]) == [(1, 4), (5, 6)]\n\n\n"
                "def test_input_list_is_not_mutated():\n"
                "    data = [(5, 6), (1, 3)]\n"
                "    merge(data)\n"
                "    assert data == [(5, 6), (1, 3)]\n\n\n"
                "def test_fully_contained_interval():\n"
                "    assert merge([(1, 10), (2, 3)]) == [(1, 10)]\n\n\n"
                "def test_empty_and_invalid():\n"
                "    assert merge([]) == []\n"
                "    with pytest.raises(ValueError):\n"
                "        merge([(5, 1)])\n"
            )
        },
        max_steps=14,
        tags=["algorithm", "edge-cases", "hidden-tests"],
    ),
    BenchmarkTask(
        task_id="retry_backoff_schedule",
        name="Exponential backoff schedule",
        prompt=(
            "Fix backoff.schedule. Given attempts, base and cap it returns the delay "
            "list for each retry: base * 2**index, clamped at cap. attempts=0 returns "
            "an empty list. The cap applies per-entry, so once the value reaches cap "
            "every later entry is exactly cap. Raise ValueError for negative attempts, "
            "non-positive base, or cap < base." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "backoff.py": (
                "def schedule(attempts: int, base: float = 1.0, cap: float = 60.0):\n"
                '    """Return the backoff delay for each retry attempt."""\n'
                "    delays = []\n"
                "    for index in range(attempts):\n"
                "        delays.append(base * 2 ** index)\n"
                "    return delays\n"
            ),
            "tests/test_public_backoff.py": (
                "from backoff import schedule\n\n\n"
                "def test_growth():\n"
                "    assert schedule(3, base=1.0, cap=60.0) == [1.0, 2.0, 4.0]\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_backoff.py": (
                "import pytest\n\n"
                "from backoff import schedule\n\n\n"
                "def test_cap_is_applied():\n"
                "    assert schedule(6, base=1.0, cap=8.0) == [1.0, 2.0, 4.0, 8.0, 8.0, 8.0]\n\n\n"
                "def test_zero_attempts():\n"
                "    assert schedule(0) == []\n\n\n"
                "def test_base_equal_to_cap():\n"
                "    assert schedule(3, base=5.0, cap=5.0) == [5.0, 5.0, 5.0]\n\n\n"
                "def test_invalid_arguments():\n"
                "    with pytest.raises(ValueError):\n"
                "        schedule(-1)\n"
                "    with pytest.raises(ValueError):\n"
                "        schedule(3, base=0)\n"
                "    with pytest.raises(ValueError):\n"
                "        schedule(3, base=10.0, cap=5.0)\n"
            )
        },
        max_steps=14,
        tags=["algorithm", "resilience", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="csv_row_parser",
        name="CSV row parsing with quotes",
        prompt=(
            "Fix csv_row.parse_row. It splits one CSV line into fields: comma separated, "
            "a field may be wrapped in double quotes, a quoted field may contain commas, "
            "and a doubled quote inside a quoted field is one literal quote character. "
            "Unquoted fields keep their content as-is. An empty line yields ['']. "
            "Raise ValueError when a quoted field is never closed." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "csv_row.py": (
                "def parse_row(line: str):\n"
                '    """Split a single CSV line into fields."""\n'
                '    return line.split(",")\n'
            ),
            "tests/test_public_csv_row.py": (
                "from csv_row import parse_row\n\n\n"
                "def test_plain_fields():\n"
                '    assert parse_row("a,b,c") == ["a", "b", "c"]\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_csv_row.py": (
                "import pytest\n\n"
                "from csv_row import parse_row\n\n\n"
                "def test_quoted_field_with_comma():\n"
                '    assert parse_row(\'a,"b,c",d\') == ["a", "b,c", "d"]\n\n\n'
                "def test_escaped_quote_inside_quotes():\n"
                '    assert parse_row(\'"say ""hi""",x\') == [\'say "hi"\', "x"]\n\n\n'
                "def test_empty_fields_and_empty_line():\n"
                '    assert parse_row("a,,b") == ["a", "", "b"]\n'
                '    assert parse_row("") == [""]\n\n\n'
                "def test_unterminated_quote_is_rejected():\n"
                "    with pytest.raises(ValueError):\n"
                "        parse_row('a,\"unclosed')\n"
            )
        },
        max_steps=16,
        tags=["parsing", "string", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="paginate_cursor",
        name="Cursor pagination boundaries",
        prompt=(
            "Fix pagination.page. Given an ordered list of items, a cursor (an item id "
            "or None for the first page) and a page size, return "
            "(items_on_page, next_cursor). The cursor is exclusive: the page starts "
            "after that id. next_cursor is the id of the last returned item, or None "
            "when there is no further page. Raise ValueError for page_size < 1 or a "
            "cursor that is not in the list." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "pagination.py": (
                "def page(items, cursor=None, page_size=2):\n"
                '    """Return one page of items plus the cursor for the next page."""\n'
                "    ids = [item['id'] for item in items]\n"
                "    start = 0\n"
                "    if cursor is not None:\n"
                "        start = ids.index(cursor)\n"
                "    window = items[start:start + page_size]\n"
                "    return window, window[-1]['id']\n"
            ),
            "tests/test_public_pagination.py": (
                "from pagination import page\n\n\n"
                "ITEMS = [{'id': n} for n in range(1, 6)]\n\n\n"
                "def test_first_page():\n"
                "    window, cursor = page(ITEMS, None, 2)\n"
                "    assert [item['id'] for item in window] == [1, 2]\n"
                "    assert cursor == 2\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_pagination.py": (
                "import pytest\n\n"
                "from pagination import page\n\n\n"
                "ITEMS = [{'id': n} for n in range(1, 6)]\n\n\n"
                "def test_cursor_is_exclusive():\n"
                "    window, cursor = page(ITEMS, 2, 2)\n"
                "    assert [item['id'] for item in window] == [3, 4]\n"
                "    assert cursor == 4\n\n\n"
                "def test_last_page_reports_no_next_cursor():\n"
                "    window, cursor = page(ITEMS, 4, 2)\n"
                "    assert [item['id'] for item in window] == [5]\n"
                "    assert cursor is None\n\n\n"
                "def test_page_larger_than_remaining():\n"
                "    window, cursor = page(ITEMS, None, 99)\n"
                "    assert len(window) == 5\n"
                "    assert cursor is None\n\n\n"
                "def test_empty_items_and_bad_arguments():\n"
                "    assert page([], None, 2) == ([], None)\n"
                "    with pytest.raises(ValueError):\n"
                "        page(ITEMS, None, 0)\n"
                "    with pytest.raises(ValueError):\n"
                "        page(ITEMS, 99, 2)\n"
            )
        },
        max_steps=16,
        tags=["stateful", "pagination", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="semver_compare",
        name="Semantic version ordering",
        prompt=(
            "Fix semver.compare. It returns -1, 0 or 1 comparing two semantic versions "
            "like '1.2.3' or '1.2.3-alpha.1'. Numeric parts compare numerically, so "
            "1.10.0 is greater than 1.9.0. A version with a pre-release is LOWER than "
            "the same version without one. Pre-release identifiers compare part by part: "
            "numeric parts numerically, others lexically. Raise ValueError for a version "
            "that is not three dot-separated numbers." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "semver.py": (
                "def compare(left: str, right: str) -> int:\n"
                '    """Compare two semantic version strings."""\n'
                "    if left == right:\n"
                "        return 0\n"
                "    return -1 if left < right else 1\n"
            ),
            "tests/test_public_semver.py": (
                "from semver import compare\n\n\n"
                "def test_equal_versions():\n"
                '    assert compare("1.2.3", "1.2.3") == 0\n\n\n'
                "def test_patch_difference():\n"
                '    assert compare("1.2.3", "1.2.4") == -1\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_semver.py": (
                "import pytest\n\n"
                "from semver import compare\n\n\n"
                "def test_numeric_not_lexical():\n"
                '    assert compare("1.10.0", "1.9.0") == 1\n'
                '    assert compare("2.0.0", "10.0.0") == -1\n\n\n'
                "def test_prerelease_is_lower_than_release():\n"
                '    assert compare("1.0.0-alpha", "1.0.0") == -1\n'
                '    assert compare("1.0.0", "1.0.0-beta") == 1\n\n\n'
                "def test_prerelease_ordering():\n"
                '    assert compare("1.0.0-alpha.1", "1.0.0-alpha.2") == -1\n'
                '    assert compare("1.0.0-alpha", "1.0.0-beta") == -1\n\n\n'
                "def test_invalid_versions():\n"
                "    with pytest.raises(ValueError):\n"
                '        compare("1.2", "1.2.3")\n'
                "    with pytest.raises(ValueError):\n"
                '        compare("x.y.z", "1.2.3")\n'
            )
        },
        max_steps=16,
        tags=["algorithm", "ordering", "parsing"],
    ),
    BenchmarkTask(
        task_id="flatten_config",
        name="Nested config flattening",
        prompt=(
            "Fix flatten.flatten_config. It turns a nested dict into a flat dict whose "
            "keys are dot-joined paths: {'a': {'b': 1}} becomes {'a.b': 1}. Nesting can "
            "be any depth. An EMPTY nested dict is kept as a leaf with its own path and "
            "value {}. Lists are leaves and are not traversed. An empty input returns an "
            "empty dict. Raise ValueError if any key is not a string or contains a dot."
            + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "flatten.py": (
                "def flatten_config(data: dict, prefix: str = '') -> dict:\n"
                '    """Flatten a nested configuration dict into dotted keys."""\n'
                "    flat = {}\n"
                "    for key, value in data.items():\n"
                "        path = f'{prefix}.{key}' if prefix else key\n"
                "        if isinstance(value, dict):\n"
                "            flat.update(flatten_config(value, path))\n"
                "        else:\n"
                "            flat[path] = value\n"
                "    return flat\n"
            ),
            "tests/test_public_flatten.py": (
                "from flatten import flatten_config\n\n\n"
                "def test_nested():\n"
                '    assert flatten_config({"a": {"b": 1}}) == {"a.b": 1}\n\n\n'
                "def test_flat_input():\n"
                '    assert flatten_config({"a": 1}) == {"a": 1}\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_flatten.py": (
                "import pytest\n\n"
                "from flatten import flatten_config\n\n\n"
                "def test_empty_nested_dict_is_a_leaf():\n"
                '    assert flatten_config({"a": {}, "b": 1}) == {"a": {}, "b": 1}\n\n\n'
                "def test_deep_nesting():\n"
                '    data = {"a": {"b": {"c": {"d": 4}}}}\n'
                '    assert flatten_config(data) == {"a.b.c.d": 4}\n\n\n'
                "def test_lists_are_leaves():\n"
                '    data = {"a": [{"b": 1}]}\n'
                '    assert flatten_config(data) == {"a": [{"b": 1}]}\n\n\n'
                "def test_empty_input_and_invalid_keys():\n"
                "    assert flatten_config({}) == {}\n"
                "    with pytest.raises(ValueError):\n"
                '        flatten_config({"a.b": 1})\n'
                "    with pytest.raises(ValueError):\n"
                "        flatten_config({1: 2})\n"
            )
        },
        max_steps=16,
        tags=["recursion", "data-structure", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="rate_limiter_window",
        name="Sliding window rate limiter",
        prompt=(
            "Fix ratelimit.SlidingWindowLimiter. allow(key, now) returns True and records "
            "the call when the key has made fewer than limit calls within the last "
            "window_seconds, otherwise returns False and records nothing. The window is "
            "sliding and half-open: a call exactly window_seconds old has expired and no "
            "longer counts. Keys are independent. Expired timestamps must be discarded so "
            "memory does not grow without bound. Raise ValueError for limit < 1 or "
            "window_seconds <= 0." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "ratelimit.py": (
                "class SlidingWindowLimiter:\n"
                '    """Allow at most `limit` calls per key within a sliding window."""\n\n'
                "    def __init__(self, limit: int = 3, window_seconds: float = 60.0):\n"
                "        self.limit = limit\n"
                "        self.window_seconds = window_seconds\n"
                "        self.calls = []\n\n"
                "    def allow(self, key: str, now: float) -> bool:\n"
                "        if len(self.calls) >= self.limit:\n"
                "            return False\n"
                "        self.calls.append(now)\n"
                "        return True\n"
            ),
            "tests/test_public_ratelimit.py": (
                "from ratelimit import SlidingWindowLimiter\n\n\n"
                "def test_allows_up_to_limit():\n"
                "    limiter = SlidingWindowLimiter(limit=2, window_seconds=10)\n"
                '    assert limiter.allow("a", 0.0) is True\n'
                '    assert limiter.allow("a", 1.0) is True\n'
                '    assert limiter.allow("a", 2.0) is False\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_ratelimit.py": (
                "import pytest\n\n"
                "from ratelimit import SlidingWindowLimiter\n\n\n"
                "def test_keys_are_independent():\n"
                "    limiter = SlidingWindowLimiter(limit=1, window_seconds=10)\n"
                '    assert limiter.allow("a", 0.0) is True\n'
                '    assert limiter.allow("b", 0.0) is True\n'
                '    assert limiter.allow("a", 1.0) is False\n\n\n'
                "def test_window_slides_and_is_half_open():\n"
                "    limiter = SlidingWindowLimiter(limit=1, window_seconds=10)\n"
                '    assert limiter.allow("a", 0.0) is True\n'
                '    assert limiter.allow("a", 9.9) is False\n'
                '    assert limiter.allow("a", 10.0) is True\n\n\n'
                "def test_rejected_calls_are_not_recorded():\n"
                "    limiter = SlidingWindowLimiter(limit=1, window_seconds=10)\n"
                '    assert limiter.allow("a", 0.0) is True\n'
                '    assert limiter.allow("a", 5.0) is False\n'
                '    assert limiter.allow("a", 10.0) is True\n\n\n'
                "def test_expired_entries_are_discarded():\n"
                "    limiter = SlidingWindowLimiter(limit=2, window_seconds=10)\n"
                "    for step in range(50):\n"
                '        limiter.allow("a", float(step) * 10)\n'
                "    stored = sum(\n"
                "        len(value) if hasattr(value, '__len__') else 1\n"
                "        for value in vars(limiter).values()\n"
                "        if isinstance(value, (list, dict))\n"
                "    )\n"
                "    assert stored <= 10\n\n\n"
                "def test_invalid_configuration():\n"
                "    with pytest.raises(ValueError):\n"
                "        SlidingWindowLimiter(limit=0)\n"
                "    with pytest.raises(ValueError):\n"
                "        SlidingWindowLimiter(limit=1, window_seconds=0)\n"
            )
        },
        max_steps=18,
        tags=["stateful", "algorithm", "edge-cases"],
    ),
    BenchmarkTask(
        task_id="safe_int_parse",
        name="Strict integer coercion",
        prompt=(
            "Fix coercion.to_int. It converts a value to int for configuration loading. "
            "Accept int (returned as-is), and str with optional surrounding whitespace "
            "and an optional +/- sign. Reject bool entirely (True is not 1 here), reject "
            "float, reject strings that are empty, non-numeric, or contain a decimal "
            "point. On rejection return the `default` when one was given, otherwise raise "
            "ValueError." + COMMON_PROMPT_SUFFIX
        ),
        setup_files={
            "coercion.py": (
                "_MISSING = object()\n\n\n"
                "def to_int(value, default=_MISSING):\n"
                '    """Coerce a configuration value to int."""\n'
                "    try:\n"
                "        return int(value)\n"
                "    except (TypeError, ValueError):\n"
                "        if default is _MISSING:\n"
                "            raise ValueError(f'cannot coerce {value!r} to int')\n"
                "        return default\n"
            ),
            "tests/test_public_coercion.py": (
                "from coercion import to_int\n\n\n"
                "def test_plain_values():\n"
                '    assert to_int("42") == 42\n'
                "    assert to_int(7) == 7\n\n\n"
                "def test_default_on_bad_value():\n"
                '    assert to_int("abc", default=0) == 0\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_coercion.py": (
                "import pytest\n\n"
                "from coercion import to_int\n\n\n"
                "def test_bool_is_rejected():\n"
                "    assert to_int(True, default=-1) == -1\n"
                "    with pytest.raises(ValueError):\n"
                "        to_int(False)\n\n\n"
                "def test_float_and_decimal_string_are_rejected():\n"
                "    assert to_int(1.5, default=-1) == -1\n"
                '    assert to_int("1.0", default=-1) == -1\n\n\n'
                "def test_whitespace_and_sign_are_accepted():\n"
                '    assert to_int("  -42  ") == -42\n'
                '    assert to_int("+7") == 7\n\n\n'
                "def test_empty_and_none():\n"
                '    assert to_int("", default=3) == 3\n'
                "    assert to_int(None, default=3) == 3\n"
                "    with pytest.raises(ValueError):\n"
                '        to_int("   ")\n'
            )
        },
        max_steps=14,
        tags=["validation", "error-handling", "edge-cases"],
    ),
]

MAINTENANCE_PROMPT_SUFFIX = (
    "\n\nYou are in a temporary repository that mimics a real maintenance task. "
    "Inspect the files, make the smallest production-quality change, update tests when "
    "the task asks for a regression test, and run the visible tests. Hidden tests will "
    "be added after you finish, so preserve public behavior and handle edge cases."
)


BUILTIN_MAINTENANCE_TASKS: list[BenchmarkTask] = [
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
    BenchmarkTask(
        task_id="cli_config_docs_contract",
        name="CLI configuration docs contract",
        prompt=(
            "Fix the CLI configuration documentation flow across cli_docs.py, "
            "docs/configuration.md, and tests/test_public_cli_docs.py. "
            "render_config_table should include every CONFIG_OPTIONS entry, sorted by flag, "
            "with option/env/default values rendered as code. The docs page must embed the "
            "same generated table under the CONFIG_TABLE marker. Add regression coverage in "
            "tests/test_public_cli_docs.py so future config options cannot silently disappear."
            + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "cli_docs.py": (
                "CONFIG_OPTIONS = [\n"
                "    {\n"
                '        "flag": "--provider",\n'
                '        "env": "DM_PROVIDER",\n'
                '        "default": "deepseek",\n'
                '        "description": "LLM provider name.",\n'
                "    },\n"
                "    {\n"
                '        "flag": "--timeout",\n'
                '        "env": "DM_TIMEOUT",\n'
                '        "default": 120,\n'
                '        "description": "Provider request timeout in seconds.",\n'
                "    },\n"
                "    {\n"
                '        "flag": "--model",\n'
                '        "env": "DM_MODEL",\n'
                '        "default": "deepseek-chat",\n'
                '        "description": "Model identifier passed to the provider.",\n'
                "    },\n"
                "    {\n"
                '        "flag": "--retries",\n'
                '        "env": "DM_RETRIES",\n'
                '        "default": 2,\n'
                '        "description": "Retry count for transient provider failures.",\n'
                "    },\n"
                "]\n\n\n"
                "def render_config_table(options=None):\n"
                "    options = options or CONFIG_OPTIONS\n"
                "    visible = [item for item in options if item['flag'] in {'--provider', '--timeout'}]\n"
                "    lines = [\n"
                '        "| Option | Env | Default | Description |",\n'
                '        "| --- | --- | --- | --- |",\n'
                "    ]\n"
                "    for item in visible:\n"
                "        lines.append(\n"
                "            f\"| {item['flag']} | {item['env']} | {item['default']} | {item['description']} |\"\n"
                "        )\n"
                '    return "\\n".join(lines)\n'
            ),
            "docs/configuration.md": (
                "# Configuration\n\n"
                "DM-Code-Agent can be configured with CLI flags or environment variables.\n\n"
                "<!-- CONFIG_TABLE -->\n"
                "| Option | Env | Default | Description |\n"
                "| --- | --- | --- | --- |\n"
                "| --provider | DM_PROVIDER | deepseek | LLM provider name. |\n"
                "| --timeout | DM_TIMEOUT | 120 | Provider request timeout in seconds. |\n"
                "<!-- /CONFIG_TABLE -->\n"
            ),
            "tests/test_public_cli_docs.py": (
                "from cli_docs import render_config_table\n\n\n"
                "def test_config_table_mentions_provider_and_timeout():\n"
                "    table = render_config_table()\n"
                '    assert "--provider" in table\n'
                '    assert "--timeout" in table\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_cli_docs.py": (
                "from pathlib import Path\n\n"
                "from cli_docs import CONFIG_OPTIONS, render_config_table\n\n\n"
                "def _table_flags(table):\n"
                "    rows = [line for line in table.splitlines() if line.startswith('| `--')]\n"
                "    return [row.split('|')[1].strip().strip('`') for row in rows]\n\n\n"
                "def test_all_config_options_are_documented_and_sorted():\n"
                "    table = render_config_table()\n"
                "    expected_flags = sorted(item['flag'] for item in CONFIG_OPTIONS)\n"
                "    assert _table_flags(table) == expected_flags\n"
                "    for item in CONFIG_OPTIONS:\n"
                "        assert f\"`{item['flag']}`\" in table\n"
                "        assert f\"`{item['env']}`\" in table\n"
                "        assert f\"`{item['default']}`\" in table\n\n\n"
                "def test_docs_embed_generated_table_between_markers():\n"
                "    docs = Path('docs/configuration.md').read_text(encoding='utf-8')\n"
                "    expected = render_config_table()\n"
                "    assert '<!-- CONFIG_TABLE -->' in docs\n"
                "    assert '<!-- /CONFIG_TABLE -->' in docs\n"
                "    assert expected in docs\n"
                "    assert 'DM_RETRIES' in docs\n"
            )
        },
        max_steps=18,
        tags=["maintenance", "docs", "cli", "regression", "multi-file"],
        allowed_changed_files=[
            "cli_docs.py",
            "docs/configuration.md",
            "tests/test_public_cli_docs.py",
        ],
        required_changed_files=[
            "cli_docs.py",
            "docs/configuration.md",
            "tests/test_public_cli_docs.py",
        ],
    ),
    BenchmarkTask(
        task_id="packaging_ci_contract",
        name="Packaging metadata and CI contract repair",
        prompt=(
            "Fix the packaging and CI contract across packaging_contract.py, pyproject.toml, "
            ".github/workflows/ci.yml, and tests/test_public_packaging.py. The project must "
            "consistently support Python 3.10, 3.11, and 3.12; expose a >=3.10 "
            "requires-python floor; define a dev extra with pytest, ruff, and black; install "
            "that dev extra in CI; and run pytest, ruff, and black checks in CI. Add "
            "regression coverage in tests/test_public_packaging.py so future packaging or CI "
            "drift is caught." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "packaging_contract.py": (
                'SUPPORTED_PYTHON_VERSIONS = ["3.11", "3.12"]\n'
                'DEV_DEPENDENCIES = ["pytest>=8.0"]\n'
                'CI_CHECK_COMMANDS = ["python -m pytest"]\n\n\n'
                "def requires_python_specifier():\n"
                '    return ">=3.11"\n\n\n'
                "def ci_python_versions():\n"
                "    return list(SUPPORTED_PYTHON_VERSIONS)\n\n\n"
                "def dev_extra_dependencies():\n"
                "    return list(DEV_DEPENDENCIES)\n\n\n"
                "def ci_install_command():\n"
                '    return "python -m pip install -e ."\n\n\n'
                "def ci_check_commands():\n"
                "    return list(CI_CHECK_COMMANDS)\n"
            ),
            "pyproject.toml": (
                "[project]\n"
                'name = "demo-agent-plugin"\n'
                'version = "0.1.0"\n'
                'description = "Small package used by the maintenance benchmark."\n'
                'requires-python = ">=3.11"\n'
                'dependencies = ["click>=8.1"]\n'
                "classifiers = [\n"
                '    "Programming Language :: Python :: 3.11",\n'
                '    "Programming Language :: Python :: 3.12",\n'
                "]\n\n"
                "[project.optional-dependencies]\n"
                'dev = ["pytest>=8.0"]\n'
            ),
            ".github/workflows/ci.yml": (
                "name: CI\n\n"
                "on:\n"
                "  push:\n"
                "  pull_request:\n\n"
                "jobs:\n"
                "  test:\n"
                "    runs-on: ubuntu-latest\n"
                "    strategy:\n"
                "      matrix:\n"
                '        python-version: ["3.11", "3.12"]\n'
                "    steps:\n"
                "      - uses: actions/checkout@v4\n"
                "      - uses: actions/setup-python@v5\n"
                "        with:\n"
                "          python-version: ${{ matrix.python-version }}\n"
                "      - run: python -m pip install -e .\n"
                "      - run: python -m pytest\n"
            ),
            "tests/test_public_packaging.py": (
                "from packaging_contract import ci_check_commands, ci_python_versions\n\n\n"
                "def test_ci_runs_pytest():\n"
                '    assert "python -m pytest" in ci_check_commands()\n\n\n'
                "def test_ci_has_supported_python_versions():\n"
                '    assert "3.11" in ci_python_versions()\n'
            ),
        },
        hidden_files={
            "tests/test_hidden_packaging_ci.py": (
                "from pathlib import Path\n\n"
                "from packaging_contract import (\n"
                "    ci_check_commands,\n"
                "    ci_install_command,\n"
                "    ci_python_versions,\n"
                "    dev_extra_dependencies,\n"
                "    requires_python_specifier,\n"
                ")\n\n\n"
                "def _read(path):\n"
                "    return Path(path).read_text(encoding='utf-8')\n\n\n"
                "def test_packaging_contract_declares_python_310_floor():\n"
                '    assert requires_python_specifier() == ">=3.10"\n'
                '    assert ci_python_versions() == ["3.10", "3.11", "3.12"]\n'
                "    pyproject = _read('pyproject.toml')\n"
                "    assert 'requires-python = \">=3.10\"' in pyproject\n"
                '    assert "Programming Language :: Python :: 3.10" in pyproject\n'
                '    assert "Programming Language :: Python :: 3.11" in pyproject\n'
                '    assert "Programming Language :: Python :: 3.12" in pyproject\n\n\n'
                "def test_dev_extra_and_ci_install_are_consistent():\n"
                "    dependencies = dev_extra_dependencies()\n"
                "    for tool in ('pytest', 'ruff', 'black'):\n"
                "        assert any(dep == tool or dep.startswith(f'{tool}>') for dep in dependencies)\n"
                "    assert ci_install_command() == 'python -m pip install -e \".[dev]\"'\n"
                "    pyproject = _read('pyproject.toml')\n"
                "    for tool in ('pytest', 'ruff', 'black'):\n"
                "        assert tool in pyproject\n"
                "    workflow = _read('.github/workflows/ci.yml')\n"
                "    normalized = workflow.replace(\"'\", '\"')\n"
                "    assert 'python -m pip install -e \".[dev]\"' in normalized\n\n\n"
                "def test_ci_runs_all_keyless_checks_in_order():\n"
                "    expected = [\n"
                "        'python -m pytest',\n"
                "        'python -m ruff check dm_agent tests',\n"
                "        'python -m black --check .',\n"
                "    ]\n"
                "    assert ci_check_commands() == expected\n"
                "    workflow = _read('.github/workflows/ci.yml')\n"
                "    positions = [workflow.index(command) for command in expected]\n"
                "    assert positions == sorted(positions)\n"
                "    for version in ('3.10', '3.11', '3.12'):\n"
                "        assert version in workflow\n"
            )
        },
        max_steps=20,
        tags=["maintenance", "packaging", "ci", "regression", "multi-file"],
        allowed_changed_files=[
            "packaging_contract.py",
            "pyproject.toml",
            ".github/workflows/ci.yml",
            "tests/test_public_packaging.py",
        ],
        required_changed_files=[
            "packaging_contract.py",
            "pyproject.toml",
            ".github/workflows/ci.yml",
            "tests/test_public_packaging.py",
        ],
    ),
    BenchmarkTask(
        task_id="billing_period_boundary",
        name="Billing period boundary arithmetic",
        prompt=(
            "Fix billing.period_end. Given a start date and a month count it returns the "
            "last day of the billing period: the day BEFORE the same day-of-month N months "
            "later. When the target month is too short, clamp to that month's last day "
            "before subtracting one day — so 2024-01-31 plus 1 month ends on 2024-02-28. "
            "Leap years must be handled. Raise ValueError for months < 1."
            + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "billing.py": (
                "from datetime import date, timedelta\n\n\n"
                "def period_end(start: date, months: int = 1) -> date:\n"
                '    """Return the last day of a billing period."""\n'
                "    year = start.year + (start.month - 1 + months) // 12\n"
                "    month = (start.month - 1 + months) % 12 + 1\n"
                "    return date(year, month, start.day) - timedelta(days=1)\n"
            ),
            "tests/test_public_billing.py": (
                "from datetime import date\n\n"
                "from billing import period_end\n\n\n"
                "def test_simple_month():\n"
                "    assert period_end(date(2024, 3, 15), 1) == date(2024, 4, 14)\n\n\n"
                "def test_year_rollover():\n"
                "    assert period_end(date(2024, 12, 10), 1) == date(2025, 1, 9)\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_billing.py": (
                "import pytest\n\n"
                "from datetime import date\n\n"
                "from billing import period_end\n\n\n"
                "def test_short_target_month_is_clamped():\n"
                "    assert period_end(date(2024, 1, 31), 1) == date(2024, 2, 28)\n"
                "    assert period_end(date(2024, 3, 31), 1) == date(2024, 4, 29)\n\n\n"
                "def test_leap_year():\n"
                "    assert period_end(date(2024, 1, 29), 1) == date(2024, 2, 28)\n"
                "    assert period_end(date(2023, 1, 29), 1) == date(2023, 2, 27)\n\n\n"
                "def test_multi_month_periods():\n"
                "    assert period_end(date(2024, 1, 31), 12) == date(2025, 1, 30)\n"
                "    assert period_end(date(2024, 8, 31), 6) == date(2025, 2, 27)\n\n\n"
                "def test_invalid_month_count():\n"
                "    with pytest.raises(ValueError):\n"
                "        period_end(date(2024, 1, 1), 0)\n"
            )
        },
        max_steps=16,
        tags=["maintenance", "datetime", "edge-cases"],
        allowed_changed_files=["billing.py"],
    ),
    BenchmarkTask(
        task_id="sql_where_builder",
        name="Parameterised WHERE clause builder",
        prompt=(
            "Fix query.build_where. It turns a dict of filters into a parameterised SQL "
            "fragment and returns (clause, params). Values must NEVER be inlined into the "
            "SQL — always emit a '?' placeholder and put the value in params, in the same "
            "order as the placeholders. Keys are sorted for deterministic output. A None "
            "value becomes 'col IS NULL' with no parameter. A list/tuple value becomes "
            "'col IN (?, ?)' with one parameter per element; an empty list means the "
            "filter can never match, so emit '1 = 0' with no parameter for that key. An "
            "empty filter dict returns ('', []). Reject a column name that is not a valid "
            "identifier with ValueError." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "query.py": (
                "def build_where(filters: dict):\n"
                '    """Build a parameterised WHERE clause from a filter mapping."""\n'
                "    if not filters:\n"
                "        return '', []\n"
                "    parts = []\n"
                "    params = []\n"
                "    for column, value in filters.items():\n"
                "        parts.append(f\"{column} = '{value}'\")\n"
                "    return ' AND '.join(parts), params\n"
            ),
            "tests/test_public_query.py": (
                "from query import build_where\n\n\n"
                "def test_empty_filters():\n"
                "    assert build_where({}) == ('', [])\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_query.py": (
                "import pytest\n\n"
                "from query import build_where\n\n\n"
                "def test_values_are_parameterised_not_inlined():\n"
                "    clause, params = build_where({'name': \"O'Brien\"})\n"
                "    assert clause == 'name = ?'\n"
                '    assert params == ["O\'Brien"]\n\n\n'
                "def test_keys_are_sorted_and_params_follow_placeholder_order():\n"
                "    clause, params = build_where({'b': 2, 'a': 1})\n"
                "    assert clause == 'a = ? AND b = ?'\n"
                "    assert params == [1, 2]\n\n\n"
                "def test_none_becomes_is_null():\n"
                "    clause, params = build_where({'deleted_at': None})\n"
                "    assert clause == 'deleted_at IS NULL'\n"
                "    assert params == []\n\n\n"
                "def test_list_becomes_in_clause():\n"
                "    clause, params = build_where({'id': [1, 2, 3]})\n"
                "    assert clause == 'id IN (?, ?, ?)'\n"
                "    assert params == [1, 2, 3]\n\n\n"
                "def test_empty_list_never_matches():\n"
                "    clause, params = build_where({'id': []})\n"
                "    assert clause == '1 = 0'\n"
                "    assert params == []\n\n\n"
                "def test_invalid_column_name_is_rejected():\n"
                "    with pytest.raises(ValueError):\n"
                "        build_where({'id; DROP TABLE users': 1})\n"
            )
        },
        max_steps=18,
        tags=["maintenance", "security", "database"],
        allowed_changed_files=["query.py"],
    ),
    BenchmarkTask(
        task_id="idempotent_job_runner",
        name="Idempotent job execution",
        prompt=(
            "Fix jobs.JobRunner so submitting the same job key twice runs the work "
            "function only once and returns the first result both times. A job that "
            "raises must NOT be cached: the exception propagates and a later submit with "
            "the same key retries. Results are per-key. has_run(key) reports whether a "
            "successful result is cached. A falsy result (None, 0, '') still counts as a "
            "cached success." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "jobs.py": (
                "class JobRunner:\n"
                '    """Run keyed jobs at most once."""\n\n'
                "    def __init__(self):\n"
                "        self.results = {}\n\n"
                "    def submit(self, key: str, work):\n"
                "        if self.results.get(key):\n"
                "            return self.results[key]\n"
                "        result = work()\n"
                "        self.results[key] = result\n"
                "        return result\n\n"
                "    def has_run(self, key: str) -> bool:\n"
                "        return bool(self.results.get(key))\n"
            ),
            "tests/test_public_jobs.py": (
                "from jobs import JobRunner\n\n\n"
                "def test_runs_once():\n"
                "    runner = JobRunner()\n"
                "    calls = []\n"
                "    work = lambda: calls.append(1) or 'done'\n"
                "    assert runner.submit('a', work) == 'done'\n"
                "    assert runner.submit('a', work) == 'done'\n"
                "    assert len(calls) == 1\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_jobs.py": (
                "import pytest\n\n"
                "from jobs import JobRunner\n\n\n"
                "def test_falsy_results_are_still_cached():\n"
                "    runner = JobRunner()\n"
                "    calls = []\n\n"
                "    def work():\n"
                "        calls.append(1)\n"
                "        return None\n\n"
                "    assert runner.submit('a', work) is None\n"
                "    assert runner.submit('a', work) is None\n"
                "    assert len(calls) == 1\n"
                "    assert runner.has_run('a') is True\n\n\n"
                "def test_zero_and_empty_string_are_cached():\n"
                "    runner = JobRunner()\n"
                "    assert runner.submit('z', lambda: 0) == 0\n"
                "    assert runner.submit('z', lambda: 99) == 0\n"
                "    assert runner.submit('e', lambda: '') == ''\n"
                "    assert runner.submit('e', lambda: 'x') == ''\n\n\n"
                "def test_failure_is_not_cached_and_retries():\n"
                "    runner = JobRunner()\n"
                "    attempts = []\n\n"
                "    def flaky():\n"
                "        attempts.append(1)\n"
                "        if len(attempts) == 1:\n"
                "            raise RuntimeError('boom')\n"
                "        return 'ok'\n\n"
                "    with pytest.raises(RuntimeError):\n"
                "        runner.submit('f', flaky)\n"
                "    assert runner.has_run('f') is False\n"
                "    assert runner.submit('f', flaky) == 'ok'\n"
                "    assert len(attempts) == 2\n\n\n"
                "def test_keys_are_independent():\n"
                "    runner = JobRunner()\n"
                "    assert runner.submit('a', lambda: 1) == 1\n"
                "    assert runner.submit('b', lambda: 2) == 2\n"
                "    assert runner.has_run('c') is False\n"
            )
        },
        max_steps=16,
        tags=["maintenance", "stateful", "error-handling"],
        allowed_changed_files=["jobs.py"],
    ),
    BenchmarkTask(
        task_id="sort_stability_regression",
        name="Stable ranking regression",
        prompt=(
            "Fix ranking.rank_items. Items are sorted by score descending, and ties must "
            "preserve the original input order (a stable sort). The returned list is new; "
            "the input must not be mutated. Items missing a 'score' key are treated as "
            "score 0. Add a regression test to tests/test_ranking.py that would fail if "
            "someone reintroduces an unstable tie-break." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "ranking.py": (
                "def rank_items(items):\n"
                '    """Sort items by score, highest first."""\n'
                "    return sorted(items, key=lambda item: -item['score'])\n"
            ),
            "tests/test_ranking.py": (
                "from ranking import rank_items\n\n\n"
                "def test_orders_by_score():\n"
                "    items = [{'name': 'a', 'score': 1}, {'name': 'b', 'score': 3}]\n"
                "    assert [item['name'] for item in rank_items(items)] == ['b', 'a']\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_ranking.py": (
                "from ranking import rank_items\n\n\n"
                "def test_ties_keep_input_order():\n"
                "    items = [\n"
                "        {'name': 'first', 'score': 5},\n"
                "        {'name': 'second', 'score': 5},\n"
                "        {'name': 'third', 'score': 5},\n"
                "    ]\n"
                "    assert [item['name'] for item in rank_items(items)] == [\n"
                "        'first',\n"
                "        'second',\n"
                "        'third',\n"
                "    ]\n\n\n"
                "def test_missing_score_defaults_to_zero():\n"
                "    items = [{'name': 'a'}, {'name': 'b', 'score': 2}, {'name': 'c', 'score': -1}]\n"
                "    assert [item['name'] for item in rank_items(items)] == ['b', 'a', 'c']\n\n\n"
                "def test_input_is_not_mutated():\n"
                "    items = [{'name': 'a', 'score': 1}, {'name': 'b', 'score': 3}]\n"
                "    snapshot = [dict(item) for item in items]\n"
                "    rank_items(items)\n"
                "    assert items == snapshot\n\n\n"
                "def test_regression_test_was_added():\n"
                "    from pathlib import Path\n\n"
                "    source = Path('tests/test_ranking.py').read_text(encoding='utf-8')\n"
                "    assert source.count('def test_') >= 2\n"
            )
        },
        max_steps=16,
        tags=["maintenance", "algorithm", "regression", "tests"],
        allowed_changed_files=["ranking.py", "tests/test_ranking.py"],
        required_changed_files=["ranking.py", "tests/test_ranking.py"],
    ),
    BenchmarkTask(
        task_id="filename_sanitizer",
        name="Cross-platform filename sanitising",
        prompt=(
            "Fix filenames.sanitize. It makes an arbitrary string safe as a single file "
            'name: strip directory separators and the characters <>:"|?* , collapse runs '
            "of the replacement underscore, and trim leading/trailing dots, spaces and "
            "underscores. Preserve non-ASCII letters such as CJK. Reserved Windows device "
            "names (CON, PRN, AUX, NUL, COM1-9, LPT1-9, case-insensitive, with or without "
            "extension) get an underscore prefix. If nothing usable remains, return "
            "'untitled'. Cap the result at 100 characters." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "filenames.py": (
                "import re\n\n"
                "BAD = r'[/\\\\]'\n\n\n"
                "def sanitize(name: str) -> str:\n"
                '    """Return a safe single-segment file name."""\n'
                "    cleaned = re.sub(BAD, '_', name).strip()\n"
                "    return cleaned or 'untitled'\n"
            ),
            "tests/test_public_filenames.py": (
                "from filenames import sanitize\n\n\n"
                "def test_replaces_separators():\n"
                "    assert sanitize('a/b') == 'a_b'\n\n\n"
                "def test_empty_input():\n"
                "    assert sanitize('') == 'untitled'\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_filenames.py": (
                "from filenames import sanitize\n\n\n"
                "def test_windows_illegal_characters():\n"
                "    assert sanitize('re:port*v2?.txt') == 're_port_v2_.txt'\n\n\n"
                "def test_collapses_and_trims():\n"
                "    assert sanitize('a///b') == 'a_b'\n"
                "    assert sanitize('  ..name..  ') == 'name'\n"
                "    assert sanitize('___x___') == 'x'\n\n\n"
                "def test_unicode_is_preserved():\n"
                "    assert sanitize('报告-2024.txt') == '报告-2024.txt'\n\n\n"
                "def test_reserved_device_names():\n"
                "    assert sanitize('CON') == '_CON'\n"
                "    assert sanitize('nul.txt') == '_nul.txt'\n"
                "    assert sanitize('COM1') == '_COM1'\n"
                "    assert sanitize('CONFIG') == 'CONFIG'\n\n\n"
                "def test_only_bad_characters_and_length_cap():\n"
                "    assert sanitize('///') == 'untitled'\n"
                "    assert sanitize('...') == 'untitled'\n"
                "    assert len(sanitize('x' * 300)) == 100\n"
            )
        },
        max_steps=18,
        tags=["maintenance", "filesystem", "encoding", "edge-cases"],
        allowed_changed_files=["filenames.py"],
    ),
    BenchmarkTask(
        task_id="error_propagation_contract",
        name="Cross-file error translation contract",
        prompt=(
            "storage.py raises low-level StorageError. service.py must translate it into "
            "the public NotFound / Unavailable exceptions declared in errors.py, per the "
            "contract in errors.py: a missing key becomes NotFound, any other storage "
            "failure becomes Unavailable, and the original exception must be attached as "
            "__cause__ (raise ... from ...). Programming errors such as TypeError must "
            "NOT be swallowed. Fix service.py only." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "errors.py": (
                '"""Public error contract for the service layer.\n\n'
                "NotFound     -> the requested key does not exist\n"
                "Unavailable  -> the backend failed for any other reason\n\n"
                "Both must carry the original low-level exception as __cause__ so callers\n"
                "can log the root cause. Programming errors (TypeError, ValueError raised\n"
                'by our own code) must propagate unchanged.\n"""\n\n\n'
                "class ServiceError(Exception):\n"
                "    pass\n\n\n"
                "class NotFound(ServiceError):\n"
                "    pass\n\n\n"
                "class Unavailable(ServiceError):\n"
                "    pass\n"
            ),
            "storage.py": (
                "class StorageError(Exception):\n"
                "    def __init__(self, message: str, code: str = 'io'):\n"
                "        super().__init__(message)\n"
                "        self.code = code\n\n\n"
                "class Storage:\n"
                '    """Low-level storage. code is "missing" when the key is absent."""\n\n'
                "    def __init__(self, data=None, failure=None):\n"
                "        self.data = data or {}\n"
                "        self.failure = failure\n\n"
                "    def read(self, key):\n"
                "        if self.failure is not None:\n"
                "            raise self.failure\n"
                "        if key not in self.data:\n"
                "            raise StorageError(f'no such key: {key}', code='missing')\n"
                "        return self.data[key]\n"
            ),
            "service.py": (
                "from errors import ServiceError\n"
                "from storage import StorageError\n\n\n"
                "def fetch(storage, key):\n"
                '    """Read a key and translate storage failures to the public contract."""\n'
                "    try:\n"
                "        return storage.read(key)\n"
                "    except StorageError as exc:\n"
                "        raise ServiceError(str(exc))\n"
            ),
            "tests/test_public_service.py": (
                "from service import fetch\n"
                "from storage import Storage\n\n\n"
                "def test_reads_existing_key():\n"
                "    assert fetch(Storage({'a': 1}), 'a') == 1\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_service.py": (
                "import pytest\n\n"
                "from errors import NotFound, Unavailable\n"
                "from service import fetch\n"
                "from storage import Storage, StorageError\n\n\n"
                "def test_missing_key_becomes_not_found():\n"
                "    with pytest.raises(NotFound) as info:\n"
                "        fetch(Storage({'a': 1}), 'zzz')\n"
                "    assert isinstance(info.value.__cause__, StorageError)\n\n\n"
                "def test_other_storage_failure_becomes_unavailable():\n"
                "    broken = Storage(failure=StorageError('disk on fire', code='io'))\n"
                "    with pytest.raises(Unavailable) as info:\n"
                "        fetch(broken, 'a')\n"
                "    assert isinstance(info.value.__cause__, StorageError)\n\n\n"
                "def test_programming_errors_are_not_swallowed():\n"
                "    broken = Storage(failure=TypeError('bad call'))\n"
                "    with pytest.raises(TypeError):\n"
                "        fetch(broken, 'a')\n"
            )
        },
        max_steps=18,
        tags=["maintenance", "error-handling", "cross-file", "code-understanding"],
        allowed_changed_files=["service.py"],
        required_changed_files=["service.py"],
    ),
    BenchmarkTask(
        task_id="settings_env_precedence",
        name="Settings precedence across two modules",
        prompt=(
            "defaults.py holds the built-in defaults and the ENV_PREFIX. settings.py must "
            "resolve settings as defaults < environment < overrides. Environment variables "
            "are read as ENV_PREFIX + the UPPERCASED key. Only keys present in defaults are "
            "recognised; unknown environment variables with the prefix are ignored. Values "
            "coming from the environment must be coerced to the TYPE OF THE DEFAULT (int, "
            "float, bool, str); for bool accept 1/true/yes/on case-insensitively as True "
            "and 0/false/no/off as False. An env value that cannot be coerced raises "
            "ValueError naming the key. Fix settings.py only." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "defaults.py": (
                'ENV_PREFIX = "APP_"\n\n'
                "DEFAULTS = {\n"
                '    "host": "localhost",\n'
                '    "port": 8080,\n'
                '    "debug": False,\n'
                '    "timeout": 2.5,\n'
                "}\n"
            ),
            "settings.py": (
                "import os\n\n"
                "from defaults import DEFAULTS, ENV_PREFIX\n\n\n"
                "def resolve(env=None, overrides=None):\n"
                '    """Resolve settings from defaults, environment and explicit overrides."""\n'
                "    env = os.environ if env is None else env\n"
                "    settings = dict(DEFAULTS)\n"
                "    for key, value in env.items():\n"
                "        if key.startswith(ENV_PREFIX):\n"
                "            settings[key[len(ENV_PREFIX):].lower()] = value\n"
                "    settings.update(overrides or {})\n"
                "    return settings\n"
            ),
            "tests/test_public_settings.py": (
                "from settings import resolve\n\n\n"
                "def test_defaults_only():\n"
                "    assert resolve(env={})['host'] == 'localhost'\n\n\n"
                "def test_override_wins():\n"
                "    assert resolve(env={}, overrides={'port': 9})['port'] == 9\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_settings.py": (
                "import pytest\n\n"
                "from settings import resolve\n\n\n"
                "def test_env_values_are_coerced_to_default_type():\n"
                "    result = resolve(env={'APP_PORT': '9090', 'APP_TIMEOUT': '0.5'})\n"
                "    assert result['port'] == 9090\n"
                "    assert isinstance(result['port'], int)\n"
                "    assert result['timeout'] == 0.5\n\n\n"
                "def test_bool_env_forms():\n"
                "    for text in ('1', 'true', 'YES', 'On'):\n"
                "        assert resolve(env={'APP_DEBUG': text})['debug'] is True\n"
                "    for text in ('0', 'false', 'NO', 'Off'):\n"
                "        assert resolve(env={'APP_DEBUG': text})['debug'] is False\n\n\n"
                "def test_unknown_prefixed_vars_are_ignored():\n"
                "    result = resolve(env={'APP_MYSTERY': 'x'})\n"
                "    assert 'mystery' not in result\n"
                "    assert set(result) == {'host', 'port', 'debug', 'timeout'}\n\n\n"
                "def test_precedence_order():\n"
                "    result = resolve(env={'APP_PORT': '1'}, overrides={'port': 2})\n"
                "    assert result['port'] == 2\n\n\n"
                "def test_bad_env_value_names_the_key():\n"
                "    with pytest.raises(ValueError) as info:\n"
                "        resolve(env={'APP_PORT': 'not-a-number'})\n"
                "    assert 'port' in str(info.value)\n"
            )
        },
        max_steps=18,
        tags=["maintenance", "config", "cross-file", "code-understanding"],
        allowed_changed_files=["settings.py"],
        required_changed_files=["settings.py"],
    ),
    BenchmarkTask(
        task_id="log_redaction",
        name="Structured log secret redaction",
        prompt=(
            "Fix redact.redact_event. It scrubs a log event dict before it is written. Any "
            "key whose lowercased name contains password, secret, token, api_key or "
            "authorization has its value replaced with '***'. Redaction is recursive "
            "through nested dicts and through lists of dicts. The input event must NOT be "
            "mutated — return a new structure. Non-string values under a sensitive key are "
            "still replaced with '***'. A None value stays None (there is nothing to leak). "
            "Keys are matched case-insensitively." + MAINTENANCE_PROMPT_SUFFIX
        ),
        setup_files={
            "redact.py": (
                "SENSITIVE = ('password', 'secret', 'token', 'api_key', 'authorization')\n\n\n"
                "def redact_event(event: dict) -> dict:\n"
                '    """Replace sensitive values in a log event with a placeholder."""\n'
                "    for key in event:\n"
                "        if key in SENSITIVE:\n"
                "            event[key] = '***'\n"
                "    return event\n"
            ),
            "tests/test_public_redact.py": (
                "from redact import redact_event\n\n\n"
                "def test_top_level_secret():\n"
                "    assert redact_event({'password': 'hunter2'})['password'] == '***'\n"
            ),
        },
        hidden_files={
            "tests/test_hidden_redact.py": (
                "import copy\n\n"
                "from redact import redact_event\n\n\n"
                "def test_input_is_not_mutated():\n"
                "    event = {'password': 'hunter2'}\n"
                "    snapshot = copy.deepcopy(event)\n"
                "    redact_event(event)\n"
                "    assert event == snapshot\n\n\n"
                "def test_partial_and_case_insensitive_key_match():\n"
                "    event = {'user_PASSWORD': 'x', 'Api_Key': 'y', 'AUTHORIZATION': 'z'}\n"
                "    result = redact_event(event)\n"
                "    assert set(result.values()) == {'***'}\n\n\n"
                "def test_nested_dicts_and_lists():\n"
                "    event = {\n"
                "        'ctx': {'auth': {'token': 'abc'}},\n"
                "        'items': [{'secret': 1}, {'name': 'ok'}],\n"
                "    }\n"
                "    result = redact_event(event)\n"
                "    assert result['ctx']['auth']['token'] == '***'\n"
                "    assert result['items'][0]['secret'] == '***'\n"
                "    assert result['items'][1]['name'] == 'ok'\n\n\n"
                "def test_non_string_values_and_none():\n"
                "    result = redact_event({'token': 12345, 'secret': None, 'keep': 1})\n"
                "    assert result['token'] == '***'\n"
                "    assert result['secret'] is None\n"
                "    assert result['keep'] == 1\n"
            )
        },
        max_steps=16,
        tags=["maintenance", "security", "logging", "edge-cases"],
        allowed_changed_files=["redact.py"],
    ),
]

BENCHMARK_SUITES = {
    "coding": BUILTIN_CODING_TASKS,
    "maintenance": BUILTIN_MAINTENANCE_TASKS,
    # 记分牌：两个套件合起来跑一次，出一个 overall_pass_rate。
    # 想对照「改了策略有没有变好」就用这个，别分两次跑再心算。
    "all": BUILTIN_CODING_TASKS + BUILTIN_MAINTENANCE_TASKS,
}


def get_coding_tasks(task_ids: Iterable[str] | None = None) -> list[BenchmarkTask]:
    return get_benchmark_tasks("coding", task_ids)


def get_maintenance_tasks(task_ids: Iterable[str] | None = None) -> list[BenchmarkTask]:
    return get_benchmark_tasks("maintenance", task_ids)


def get_benchmark_tasks(
    suite: str = "coding", task_ids: Iterable[str] | None = None
) -> list[BenchmarkTask]:
    if suite not in BENCHMARK_SUITES:
        available = ", ".join(sorted(BENCHMARK_SUITES))
        raise ValueError(f"unknown benchmark suite: {suite}. Available suites: {available}")

    tasks = list(BENCHMARK_SUITES[suite])
    if task_ids:
        allowed = set(task_ids)
        tasks = [task for task in tasks if task.task_id in allowed]
    return tasks
