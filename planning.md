# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## Tools

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset for items matching a natural language description, optional size filter, and optional price ceiling. Scores each listing by keyword overlap against title, description, style_tags, category, colors, and brand — returns the ranked list, best match first.

**Input parameters:**
- `description` (str): Natural language keywords describing the item (e.g., "vintage graphic tee"). Tokenized and matched against multiple listing fields.
- `size` (str | None): Size string to filter by (e.g., "M", "US 7"), or None to skip. Case-insensitive substring match against listing's size field.
- `max_price` (float | None): Maximum price inclusive (e.g., 30.0), or None to skip price filtering.

**What it returns:**
A `list[dict]` — each dict is a full listing record with fields:
`id` (str), `title` (str), `description` (str), `category` (str), `style_tags` (list[str]), `size` (str), `condition` (str: "excellent"/"good"/"fair"), `price` (float), `colors` (list[str]), `brand` (str|None), `platform` (str: "depop"/"thredUp"/"poshmark").
Returns `[]` if nothing matches — never raises an exception.

**What happens if it fails or returns nothing:**
Agent sets `session["error"]` = `"No listings found for '[description]'[size/price context]. Try different keywords, remove the size filter, or raise your price limit."` Returns session immediately. Does NOT call suggest_outfit or create_fit_card.

---

### Tool 2: suggest_outfit

**What it does:**
Given a thrifted listing item and the user's wardrobe dict, calls the Groq LLM to suggest 1–2 complete outfit combinations using the new item. If the wardrobe is empty, gives general styling advice for the item instead of crashing.

**Input parameters:**
- `new_item` (dict): A listing dict from search_listings (has title, description, category, style_tags, colors, brand, platform, price).
- `wardrobe` (dict): A wardrobe dict with an `items` key — list of wardrobe item dicts, each with: `id` (str), `name` (str), `category` (str), `colors` (list[str]), `style_tags` (list[str]), `notes` (str|None). The `items` list may be empty.

**What it returns:**
A non-empty string with outfit suggestions. If wardrobe has items, names specific pieces (e.g., "your baggy dark wash jeans"). If wardrobe is empty, gives general advice based on the item's style_tags and colors.

**What happens if it fails or returns nothing:**
If wardrobe is empty: LLM prompt asks for general styling ideas — still returns a useful string. If LLM raises an exception: catches it and returns fallback string: `"Couldn't generate outfit suggestions right now. The [title] would pair well with neutral basics — try dark jeans and clean sneakers as a starting point."`

---

### Tool 3: create_fit_card

**What it does:**
Given an outfit suggestion string and the listing dict, calls the Groq LLM (temperature=0.9) to generate a 2–4 sentence casual OOTD-style caption. Output varies each run. Feels like something someone would actually post, not a product description.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from suggest_outfit. Must be non-empty.
- `new_item` (dict): The listing dict — used to pull title, price, and platform into the caption naturally.

**What it returns:**
A 2–4 sentence string. Mentions item name, price, and platform once each. Captures outfit vibe in specific terms. Sounds different each time for different inputs.

**What happens if it fails or returns nothing:**
If `outfit` is empty/whitespace: returns `"Cannot create a fit card without an outfit suggestion."` without calling the LLM. If LLM raises an exception: catches it and returns `"Fit card generation failed. Here's the raw look: [outfit]"` so user still sees something useful.

---

### Additional Tools (if any)

None — stretch feature is retry logic (not a new tool), described in Planning Loop below.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The loop in `run_agent()` uses these exact conditional branches:

1. **Parse query** — LLM extracts `description` (str), `size` (str|null), `max_price` (float|null) from the query. Store in `session["parsed"]`. On exception, fall back to `description=query, size=None, max_price=None`.

2. **Call search_listings** — `search_listings(parsed["description"], parsed["size"], parsed["max_price"])`. Store result in `session["search_results"]`.

3. **Branch on results (with retry logic — stretch feature):**
   - If `session["search_results"] == []` AND `parsed["size"]` was set: retry `search_listings(description, size=None, max_price)`. If retry returns results, store in `session["search_results"]`, set `session["retry_note"]` = "No results in size [X] — showing all sizes instead.", proceed to Step 4.
   - If `session["search_results"] == []` AND no size was set (or retry also empty): set `session["error"]` = descriptive message, **return session immediately**. suggest_outfit is NEVER called with empty input.
   - If non-empty: set `session["selected_item"] = session["search_results"][0]`, proceed to Step 4.

4. **Call suggest_outfit** — `suggest_outfit(session["selected_item"], session["wardrobe"])`. Store in `session["outfit_suggestion"]`.

5. **Call create_fit_card** — `create_fit_card(session["outfit_suggestion"], session["selected_item"])`. Store in `session["fit_card"]`.

6. **Return session.**

---

## State Management

**How does information from one tool get passed to the next?**

All state lives in a single `session` dict (initialized by `_new_session(query, wardrobe)`):

| Field | Set when | Passed to |
|-------|----------|-----------|
| `query` | init | LLM parser |
| `parsed` | after LLM parse | search_listings |
| `search_results` | after search_listings | branch check |
| `selected_item` | after branch B | suggest_outfit, create_fit_card |
| `wardrobe` | init | suggest_outfit |
| `outfit_suggestion` | after suggest_outfit | create_fit_card |
| `fit_card` | after create_fit_card | app.py panel 3 |
| `error` | on failure | app.py panel 1 |

No global variables. No re-prompting the user. `selected_item` is the exact dict from `search_results[0]` passed directly into suggest_outfit. `outfit_suggestion` is the exact string from suggest_outfit passed directly into create_fit_card.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match query | `session["error"]` = "No listings found for '[description]'[size/price context]. Try different keywords, remove the size filter, or raise your price limit." Session returned early. suggest_outfit and create_fit_card not called. |
| suggest_outfit | `wardrobe["items"]` is empty | LLM called with general styling prompt — returns useful advice string, no crash. |
| suggest_outfit | LLM call raises exception | Catches exception, returns: "Couldn't generate outfit suggestions right now. The [title] would pair well with neutral basics — try dark jeans and clean sneakers as a starting point." |
| create_fit_card | `outfit` is empty or whitespace | Returns error string immediately without LLM call: "Cannot create a fit card without an outfit suggestion." |
| create_fit_card | LLM call raises exception | Catches exception, returns: "Fit card generation failed. Here's the raw look: [outfit]" |

---

## Architecture

```
User query (natural language)
        │
        ▼
run_agent(query, wardrobe)
        │
        ├─► [Step 1] LLM parse query
        │       │ → session["parsed"] = {description, size, max_price}
        │       │   (fallback on exception: description=query, size=None, max_price=None)
        │       │
        ├─► [Step 2] search_listings(description, size, max_price)
        │       │ → session["search_results"] = [list of listing dicts]
        │       │
        │       ├── results == []  ──────────────────────────────────────────┐
        │       │       │                                                    │
        │       │       ▼                                                    │
        │       │   session["error"] = "No listings found..."               │
        │       │   return session  ◄──────── ERROR PATH (early exit) ───────┘
        │       │
        │       └── results != []
        │               │
        │               ▼
        │           session["selected_item"] = results[0]
        │               │
        ├─► [Step 3] suggest_outfit(selected_item, wardrobe)
        │       │
        │       ├── wardrobe["items"] == []
        │       │       └─► LLM: general styling advice for item
        │       │
        │       └── wardrobe["items"] != []
        │               └─► LLM: outfit combos using specific wardrobe pieces
        │       │
        │       ▼
        │   session["outfit_suggestion"] = "..."
        │       │
        └─► [Step 4] create_fit_card(outfit_suggestion, selected_item)
                │
                ├── outfit empty → return error string (no LLM call)
                │
                └── outfit non-empty → LLM (temp=0.9): OOTD caption
                │
                ▼
            session["fit_card"] = "..."
                │
                ▼
            return session
                │
                ▼
        app.py: handle_query() maps session → 3 Gradio output panels
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

**Tool 1 (search_listings):** Give Claude the Tool 1 spec block from this file (inputs, return value with all fields, failure mode). Ask it to implement `search_listings()` in tools.py using `load_listings()` from the data loader, scoring keyword overlap across title + description + style_tags + category + colors + brand. Verify before running: filters by both price AND size? Scores by keyword overlap? Returns `[]` not exception on no match? Test with 3 queries: "vintage graphic tee under $30" (expect results), "designer ballgown size XXS under $5" (expect []), "jacket under $10" (expect [], all jackets cost more).

**Tool 2 (suggest_outfit):** Give Claude the Tool 2 spec block plus the wardrobe schema from `data/wardrobe_schema.json`. Ask it to implement `suggest_outfit()` calling `llama-3.3-70b-versatile` via Groq. Verify before running: branches on `wardrobe["items"]`? Empty-wardrobe branch returns non-empty string? Catches LLM exceptions? Test manually with `get_empty_wardrobe()` and `get_example_wardrobe()`.

**Tool 3 (create_fit_card):** Give Claude the Tool 3 spec block. Ask it to implement with temperature=0.9 and a prompt emphasizing casual OOTD voice. Verify: guards against empty outfit? Mentions price/platform naturally? Run 3 times on same input — outputs must vary.

**Milestone 4 — Planning loop and state management:**

Give Claude the Architecture diagram above and the Planning Loop + State Management sections. Ask it to implement `run_agent()` in agent.py. Verify before running: branches on `search_results == []`? Does NOT call suggest_outfit when results are empty? Stores `selected_item = results[0]`? Then run `python agent.py` and check both test cases in `__main__`.

---

## A Complete Interaction (Step by Step)

FitFindr takes a natural language query, parses it into structured search parameters, searches the mock listings dataset, selects the top match, asks an LLM to suggest outfits using the user's wardrobe, and generates a shareable OOTD caption. If search returns nothing, the agent stops immediately and tells the user how to adjust their query rather than proceeding with empty data.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Parse query:**
LLM extracts: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`.
Stored in `session["parsed"] = {"description": "vintage graphic tee", "size": None, "max_price": 30.0}`.

**Step 2 — Call search_listings:**
`search_listings("vintage graphic tee", None, 30.0)` — filters listings by price ≤ $30, then scores by keyword overlap.
"Graphic Tee — 2003 Tour Bootleg Style" (lst_006, $24, style_tags: graphic tee, vintage, grunge) scores highest.
"Y2K Baby Tee — Butterfly Print" (lst_002, $18, style_tags: y2k, vintage, graphic tee) scores second.
Returns `[lst_006_dict, lst_002_dict]`.
`session["search_results"]` = that list. Non-empty → proceed.
`session["selected_item"]` = lst_006_dict.

**Step 3 — Call suggest_outfit:**
`suggest_outfit(lst_006_dict, example_wardrobe)` called.
Wardrobe has 10 items. LLM prompt includes item details (black graphic tee, grunge/streetwear vibe) and wardrobe list.
LLM returns: "Pair this faded bootleg tee with your baggy dark wash jeans and chunky white sneakers for a streetwear look. For a grungier take, swap the sneakers for your black combat boots and layer your vintage black denim jacket over it — front-tuck the tee slightly for shape."
`session["outfit_suggestion"]` = that string.

**Step 4 — Call create_fit_card:**
`create_fit_card(outfit_suggestion, lst_006_dict)` — LLM at temp=0.9.
Returns: "found this faded bootleg tee on depop for $24 and it already feels like it's been in my closet forever 🖤 baggy jeans, combat boots, denim jacket — that's the whole vibe. thrift wins again"
`session["fit_card"]` = that string.

**Final output to user:**
- Panel 1 (listing): "Graphic Tee — 2003 Tour Bootleg Style | $24.00 | depop | Size: L | Condition: good | Colors: black"
- Panel 2 (outfit idea): The suggest_outfit string.
- Panel 3 (fit card): The OOTD caption.

**Error path:**
Query: "designer ballgown size XXS under $5" → search returns [] → `session["error"]` set → panels 2 and 3 empty → panel 1 shows: "No listings found for 'designer ballgown' in size XXS under $5.00. Try different keywords, remove the size filter, or raise your price limit."
