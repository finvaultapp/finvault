"""AI helpers on top of the chat plumbing: category suggestions for unfamiliar merchants and plain-language search.

Both only run when ai.resolve() finds a model and the member has opted in (checked by the router). What goes to the
model is kept to the minimum each task needs; see build_suggest_payload() and build_search_payload().
"""
import json
import re
from datetime import date, timedelta
from decimal import Decimal

import httpx

from ..security import Throttle

# Model calls per member (cached answers don't count).
suggest_limit = Throttle(limit=12, window_seconds=10 * 60)
search_limit = Throttle(limit=30, window_seconds=10 * 60)

TIMEOUT = httpx.Timeout(60.0, connect=10.0)
MAX_MERCHANTS_PER_CALL = 25


class ModelError(RuntimeError):
    """The model couldn't be reached or its answer couldn't be used."""


# --- Talking to an OpenAI-compatible endpoint --------------------------------

def _content(data) -> str:
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ModelError("The model's reply had an unexpected shape.") from exc
    return msg.get("content") or ""


def complete(target: dict, system: str, user_content: str) -> str:
    """One non-streaming chat completion. Returns the raw text of the reply."""
    payload = {
        "model": target["model"],
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user_content}],
        "stream": False,
    }
    optional = {"response_format": {"type": "json_object"}}
    if target["provider"] == "server":
        optional["temperature"] = 0  # OpenAI reasoning models reject a custom temperature; only the household model gets one
    headers = {"Authorization": f"Bearer {target['key']}"} if target.get("key") else {}
    url = f"{target['base']}/chat/completions"
    try:
        r = httpx.post(url, json=payload | optional, headers=headers, timeout=TIMEOUT)
        if r.status_code == 400 and any(k in (r.text or "") for k in ("response_format", "temperature", "json_object")):
            # Some servers (older llama.cpp, LM Studio, a few reasoning models) reject these knobs. Ask plainly.
            r = httpx.post(url, json=payload, headers=headers, timeout=TIMEOUT)
    except httpx.HTTPError as exc:
        raise ModelError(f"Couldn't reach the model: {exc}") from exc
    if r.status_code >= 400:
        raise ModelError(f"The model server returned {r.status_code}: {(r.text or '')[:200]}")
    try:
        return _content(r.json())
    except ValueError as exc:
        raise ModelError("The model server didn't return JSON.") from exc


def parse_json(text: str):
    """Pull the first JSON object or array out of a reply, tolerating code fences and <think> blocks."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.S | re.I).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    dec = json.JSONDecoder()
    for i, ch in enumerate(text):
        if ch in "{[":
            try:
                return dec.raw_decode(text[i:])[0]
            except ValueError:
                continue
    raise ModelError("The model's answer wasn't valid JSON.")


# --- Category suggestions ----------------------------------------------------

SUGGEST_SYSTEM = (
    "You sort bank transactions into a household's own categories. For each item pick exactly one category name "
    "from the given list, or null when none fits or you don't recognise the merchant. Negative/out means money "
    "spent, in means money received. Reply with JSON only, no prose, in this shape: "
    '{"suggestions":[{"id":1,"category":"Groceries","confidence":0.8}]}. '
    "confidence is between 0 and 1. Use the category names exactly as given."
)


def scrub(description: str) -> str:
    """Drop long digit runs (card and account numbers, reference codes) before a description leaves the server."""
    text = re.sub(r"\d[\d\- ]{2,}\d", lambda m: "#" if sum(c.isdigit() for c in m.group()) >= 4 else m.group(), description)
    text = re.sub(r"#+", "#", text)
    return re.sub(r"\s+", " ", text).strip()[:120]


def build_suggest_payload(items: list[tuple[int, str, Decimal]], category_names: list[str]) -> dict:
    """items: (local id, description, signed amount). Nothing else about the member is included."""
    return {
        "categories": category_names,
        "items": [{"id": i, "description": scrub(desc), "direction": "in" if amt > 0 else "out",
                   "amount": float(abs(Decimal(amt)).quantize(Decimal("0.01")))} for i, desc, amt in items],
    }


def parse_suggestions(raw, valid_ids: set[int], names: dict[str, int]) -> dict[int, tuple[int, float]]:
    """Validate the model's answer. names maps lower-cased category name -> id. Unknown names and ids are dropped."""
    rows = raw.get("suggestions", raw.get("items")) if isinstance(raw, dict) else raw
    if not isinstance(rows, list):
        raise ModelError("The model's answer didn't contain a list of suggestions.")
    out: dict[int, tuple[int, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            rid = int(row.get("id"))
        except (TypeError, ValueError):
            continue
        cat = row.get("category")
        if rid not in valid_ids or not isinstance(cat, str):
            continue
        cat_id = names.get(cat.strip().lower())
        if cat_id is None:
            continue
        try:
            conf = float(row.get("confidence", 0.5))
        except (TypeError, ValueError):
            conf = 0.5
        out[rid] = (cat_id, min(1.0, max(0.0, conf)))
    return out


# --- Plain-language search ---------------------------------------------------

PERIODS = ("today", "yesterday", "this_week", "last_week", "this_month", "last_month", "this_quarter",
           "last_quarter", "this_year", "last_year", "year_to_date")
SEASONS = ("spring", "summer", "fall", "winter")

SEARCH_SYSTEM = (
    "You turn a question about a household's bank transactions into search filters. Reply with JSON only, "
    "no prose, using exactly these keys (use null or [] when not mentioned):\n"
    '{"period":null,"season":null,"month":null,"year":null,"which":null,"last_n_days":null,'
    '"date_from":null,"date_to":null,"categories":[],"accounts":[],"min_amount":null,"max_amount":null,'
    '"kind":null,"text":null}\n'
    f"- period: one of {', '.join(PERIODS)} for relative phrases like \"this year\" or \"last month\".\n"
    f"- season: one of {', '.join(SEASONS)}; month: 1-12. With them, year (e.g. 2025) or which (\"this\" or \"last\").\n"
    "- last_n_days: for \"past 3 weeks\" use 21.\n"
    "- date_from/date_to: YYYY-MM-DD, only for exact dates the question names. Prefer period/season/month.\n"
    "- categories and accounts: names copied exactly from the lists given; pick the closest category "
    "(\"restaurants\" -> a dining category). Never invent names.\n"
    "- min_amount/max_amount: positive numbers (\"over $50\" -> min_amount 50).\n"
    "- kind: \"expense\" for spending, \"income\" for money received, else null.\n"
    "- text: a merchant or word to search descriptions for (\"Costco\"), else null."
)


def build_search_payload(question: str, today: date, category_names: list[str], account_names: list[str]) -> dict:
    return {"today": today.isoformat(), "question": question, "categories": category_names, "accounts": account_names}


def _quarter_start(d: date) -> date:
    return date(d.year, 3 * ((d.month - 1) // 3) + 1, 1)


def _month_end(y: int, m: int) -> date:
    return (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)


def period_range(period: str, today: date) -> tuple[date, date]:
    """Relative periods. Weeks start on Sunday, as on Canadian calendars."""
    if period == "today":
        return today, today
    if period == "yesterday":
        y = today - timedelta(days=1)
        return y, y
    if period in ("this_week", "last_week"):
        start = today - timedelta(days=(today.weekday() + 1) % 7)
        if period == "last_week":
            start -= timedelta(days=7)
        return start, start + timedelta(days=6)
    if period == "this_month":
        return date(today.year, today.month, 1), _month_end(today.year, today.month)
    if period == "last_month":
        end = date(today.year, today.month, 1) - timedelta(days=1)
        return date(end.year, end.month, 1), end
    if period in ("this_quarter", "last_quarter"):
        start = _quarter_start(today)
        if period == "last_quarter":
            start = _quarter_start(start - timedelta(days=1))
        end_month = start.month + 2
        return start, _month_end(start.year, end_month)
    if period == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if period == "year_to_date":
        return date(today.year, 1, 1), today
    if period == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    raise ValueError(period)


def season_range(season: str, year: int) -> tuple[date, date]:
    """Canadian astronomical seasons (equinox/solstice dates, fixed to their usual day).

    Winter <year> starts in December of that year and runs into March of the next.
    """
    if season == "spring":
        return date(year, 3, 20), date(year, 6, 20)
    if season == "summer":
        return date(year, 6, 21), date(year, 9, 22)
    if season == "fall":
        return date(year, 9, 23), date(year, 12, 20)
    return date(year, 12, 21), date(year + 1, 3, 19)


def _occurrence(make, today: date, year: int | None, which: str | None) -> tuple[date, date]:
    """Pick the right year for a season or month named without one."""
    if year:
        return make(year)
    candidates = [make(y) for y in (today.year - 2, today.year - 1, today.year)]
    if which == "this":
        current = [c for c in candidates if c[0] <= today <= c[1]]
        return current[0] if current else make(today.year)
    started = [c for c in candidates if c[0] <= today]
    if which == "last":
        started = [c for c in started if c[1] < today] or started  # "last spring" while it's spring: the one before
    return started[-1]


def resolve_dates(spec: dict, today: date) -> tuple[date | None, date | None, str | None]:
    """Turn the model's date fields into (start, end, how). Relative phrases are resolved here, never by the model."""
    which = spec.get("which") if spec.get("which") in ("this", "last") else None
    year = spec.get("year")
    year = int(year) if isinstance(year, (int, float)) and 1990 <= int(year) <= today.year + 1 else None
    season = spec.get("season")
    if isinstance(season, str) and season.lower() in SEASONS + ("autumn",):
        s = "fall" if season.lower() == "autumn" else season.lower()
        return (*_occurrence(lambda y: season_range(s, y), today, year, which), f"season:{s}")
    month = spec.get("month")
    if isinstance(month, (int, float)) and 1 <= int(month) <= 12:
        m = int(month)
        return (*_occurrence(lambda y: (date(y, m, 1), _month_end(y, m)), today, year, which), f"month:{m}")
    period = spec.get("period")
    if isinstance(period, str) and period in PERIODS:
        return (*period_range(period, today), f"period:{period}")
    n = spec.get("last_n_days")
    if isinstance(n, (int, float)) and 1 <= int(n) <= 3660:
        return today - timedelta(days=int(n) - 1), today, "last_n_days"
    if year and not spec.get("date_from") and not spec.get("date_to"):
        return date(year, 1, 1), date(year, 12, 31), "year"

    def iso(v):
        try:
            return date.fromisoformat(v) if isinstance(v, str) and v else None
        except ValueError:
            return None
    start, end = iso(spec.get("date_from")), iso(spec.get("date_to"))
    if start and end and start > end:
        start, end = end, start
    return start, end, "explicit" if (start or end) else None


def _amount(v) -> float | None:
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, str):
        v = v.replace("$", "").replace(",", "").strip()
    try:
        f = abs(float(v))
    except (TypeError, ValueError):
        return None
    return round(f, 2) if f < 1e10 else None


def interpret_search(raw, today: date, categories: dict[str, int], accounts: dict[str, int]) -> dict:
    """Validate the model's filters. categories/accounts map lower-cased name -> id. Only known filters survive."""
    if not isinstance(raw, dict):
        raise ModelError("The model's answer wasn't a set of filters.")
    start, end, how = resolve_dates(raw, today)

    def names(key, lookup):
        vals = raw.get(key) or []
        if isinstance(vals, str):
            vals = [vals]
        ids, unknown = [], []
        for v in vals if isinstance(vals, list) else []:
            if not isinstance(v, str) or not v.strip():
                continue
            i = lookup.get(v.strip().lower())
            if i is None:
                unknown.append(v.strip()[:80])
            elif i not in ids:
                ids.append(i)
        return ids, unknown

    cat_ids, unknown_cats = names("categories", categories)
    acct_ids, unknown_accts = names("accounts", accounts)
    lo, hi = _amount(raw.get("min_amount")), _amount(raw.get("max_amount"))
    if lo is not None and hi is not None and lo > hi:
        lo, hi = hi, lo
    kind = raw.get("kind") if raw.get("kind") in ("income", "expense") else None
    text = raw.get("text")
    text = re.sub(r"\s+", " ", text).strip()[:100] if isinstance(text, str) else None
    filters = {"start": start.isoformat() if start else None, "end": end.isoformat() if end else None,
               "category_id": cat_ids, "account_id": acct_ids, "min_amount": lo, "max_amount": hi,
               "kind": kind, "q": text or None}
    return {"filters": filters, "dates_from": how,
            "unmatched": {"categories": unknown_cats, "accounts": unknown_accts}}
