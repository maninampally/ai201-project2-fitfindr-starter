# FitFindr

## Demo Video

[Watch the demo on Loom](https://www.loom.com/share/199a1f57b50c46b7ad4a3161a1501188)

A multi-tool AI agent that helps users find secondhand clothing and figure out how to wear it. Given a natural language query, FitFindr searches mock thrift listings, suggests outfit combinations using the user's existing wardrobe, and generates a shareable OOTD caption — handling failures gracefully at every step.

## Setup

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Mac/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

Create a `.env` file in the repo root (never commit this):
```
GROQ_API_KEY=your_key_here
```

Run the app:
```bash
python app.py
```

Open the URL shown in the terminal (usually `http://localhost:7860`).

Run tests:
```bash
pytest tests/
```

---

## Tool Inventory

### `search_listings(description, size, max_price)`

| | |
|---|---|
| **Purpose** | Searches the mock listings dataset for items matching a natural language description, with optional size and price filters. |
| **Inputs** | `description` (str) — keywords describing the item (e.g. "vintage graphic tee") |
| | `size` (str \| None) — size to filter by (e.g. "M", "US 7"), or None to skip |
| | `max_price` (float \| None) — price ceiling inclusive (e.g. 30.0), or None to skip |
| **Output** | `list[dict]` — matching listing records sorted by relevance score (best match first). Each dict has: `id`, `title`, `description`, `category`, `style_tags` (list), `size`, `condition`, `price` (float), `colors` (list), `brand` (str\|None), `platform`. Returns `[]` if nothing matches — never raises. |

**Scoring:** each listing is scored by counting how many description keywords appear across its title, description, style_tags, category, colors, and brand fields. Listings with score 0 are dropped.

---

### `suggest_outfit(new_item, wardrobe)`

| | |
|---|---|
| **Purpose** | Given a thrifted listing and the user's wardrobe, uses the Groq LLM to suggest 1–2 complete outfit combinations. If the wardrobe is empty, gives general styling advice instead. |
| **Inputs** | `new_item` (dict) — a listing dict from `search_listings` |
| | `wardrobe` (dict) — wardrobe dict with an `items` key (list of wardrobe item dicts with `id`, `name`, `category`, `colors`, `style_tags`, `notes`). May be empty. |
| **Output** | str — non-empty outfit suggestion string. If wardrobe has items, names specific pieces by name (e.g. "your baggy dark wash jeans"). If empty, gives general advice based on the item's style and colors. |

---

### `create_fit_card(outfit, new_item)`

| | |
|---|---|
| **Purpose** | Generates a 2–4 sentence casual OOTD-style caption for the thrifted find. Designed to sound like a real person posting, not a product description. Uses temperature 0.9 so output varies each call. |
| **Inputs** | `outfit` (str) — outfit suggestion from `suggest_outfit`. Must be non-empty. |
| | `new_item` (dict) — listing dict, used to pull title, price, and platform into the caption. |
| **Output** | str — casual caption mentioning the item name, price, and platform once each. Returns an error string (not an exception) if `outfit` is empty. |

---

## How the Planning Loop Works

`run_agent(query, wardrobe)` in [agent.py](agent.py) follows these conditional branches:

```
1. Parse query → LLM extracts description, size, max_price
                 (regex fallback if LLM fails)

2. Call search_listings(description, size, max_price)
        │
        ├── results == []
        │       → set session["error"] = "No listings found..."
        │         return session EARLY — suggest_outfit never called
        │
        └── results != []
                → session["selected_item"] = results[0]

3. Call suggest_outfit(selected_item, wardrobe)
        → session["outfit_suggestion"] = "..."

4. Call create_fit_card(outfit_suggestion, selected_item)
        → session["fit_card"] = "..."

5. Return session
```

The agent does **not** call all tools in a fixed sequence regardless of context. If `search_listings` returns nothing, it stops immediately and returns the error — `suggest_outfit` is never called with empty input.

---

## State Management

All state lives in a single `session` dict initialized at the start of each `run_agent()` call. No globals, no re-prompting the user between steps.

| Field | Set when | Used by |
|-------|----------|---------|
| `query` | init | LLM parser |
| `parsed` | after LLM parse | `search_listings` call |
| `search_results` | after search | branch check |
| `selected_item` | after branch B | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | init | `suggest_outfit` |
| `outfit_suggestion` | after `suggest_outfit` | `create_fit_card` |
| `fit_card` | after `create_fit_card` | app.py panel 3 |
| `error` | on any failure | app.py panel 1 |

`selected_item` is the exact dict from `search_results[0]` — passed directly into `suggest_outfit` and `create_fit_card` without modification. `outfit_suggestion` is the exact string from `suggest_outfit` — passed directly into `create_fit_card`.

---

## Error Handling

| Tool | Failure mode | What the agent does |
|------|-------------|---------------------|
| `search_listings` | No results match query | Sets `session["error"]` = "No listings found for '[description]' [size/price context]. Try different keywords, remove the size filter, or raise your price limit." Returns session immediately — `suggest_outfit` and `create_fit_card` are never called. |
| `suggest_outfit` | `wardrobe["items"]` is empty | Calls LLM with a general styling prompt instead of a wardrobe-specific one. Still returns a useful non-empty string. Example: "The Y2K Baby Tee would look great with high-waisted wide-leg jeans in a dark wash — the fitted crop length will balance the volume nicely. Add chunky platform sneakers to lean into the early-2000s vibe." |
| `suggest_outfit` | LLM call raises exception | Catches exception, returns fallback: "Couldn't generate outfit suggestions right now. The [title] would pair well with neutral basics — try dark jeans and clean sneakers as a starting point." |
| `create_fit_card` | `outfit` is empty or whitespace | Returns immediately without LLM call: "Cannot create a fit card without an outfit suggestion. Please make sure suggest_outfit ran successfully first." |
| `create_fit_card` | LLM call raises exception | Catches exception, returns: "Fit card generation failed. Here's the raw look: [outfit]" so the user still sees the outfit suggestion. |

**Concrete test example — no results:**
```
Query: "designer ballgown size XXS under $5"
search_listings("designer ballgown", "XXS", 5.0) → []
session["error"] = "No listings found for 'designer ballgown' in size XXS under $5.00. Try different keywords, remove the size filter, or raise your price limit."
session["outfit_suggestion"] = None   ← never called
session["fit_card"] = None            ← never called
```

**Concrete test example — empty wardrobe:**
```
Query: "vintage graphic tee"
wardrobe = get_empty_wardrobe()   # items = []
suggest_outfit(item, empty_wardrobe) → general advice string (non-empty)
# No exception raised, no empty string returned
```

---

## Spec Reflection

**One way the spec helped:** Defining the exact failure mode behavior before implementation — specifically "return `[]`, never raise" for `search_listings` and "return error string, never raise" for `create_fit_card` — made the error handling code straightforward to write. Having the contract written down meant I knew exactly what to test.

**One way implementation diverged from the spec:** The spec described using the Groq LLM to parse the user's query into structured parameters. In practice, the LLM parser works well for queries like "track jacket size M under $45" but the regex fallback turned out to be necessary more often than expected because the `$30` in a query like "tee under $30" was being mistakenly parsed as a size ("30") by the initial regex. Fixed by restricting the regex size pattern to named size tokens (XS, S, M, L, XL, etc.) instead of any number.

---

## AI Usage

**Instance 1 — `suggest_outfit` and `create_fit_card` prompts:**
I gave Claude (this session) the Tool 2 and Tool 3 spec blocks from `planning.md` — specifically the inputs, return value description, empty-wardrobe failure mode, and the note that `create_fit_card` should "feel casual and authentic, not a product description." Claude generated both LLM prompt strings inside the functions. I revised the `create_fit_card` prompt to explicitly say "Does NOT start with 'I'" after the first draft produced captions that all began with "I scored this..." — too uniform. I also bumped temperature from 0.7 to 0.9 after running the function three times and getting nearly identical outputs.

**Instance 2 — `run_agent()` planning loop:**
I gave Claude the ASCII architecture diagram from `planning.md` and the Planning Loop section describing the exact conditional branches. Claude generated the `run_agent()` skeleton. I reviewed it against the diagram before running and caught that the generated code was using `if len(results) == 0` instead of `if not session["search_results"]` — a minor style difference but more Pythonic with the session dict. I also added the regex fallback in `_parse_query()` after the LLM-only version failed on queries where the API key typo (`GROK_API_KEY` vs `GROQ_API_KEY`) caused all LLM calls to silently fall back.
