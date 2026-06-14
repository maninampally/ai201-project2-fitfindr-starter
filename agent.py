"""
agent.py

The FitFindr planning loop. Orchestrates the three tools in response to a
natural language user query, passing state between them via a session dict.

Usage (once implemented):
    from agent import run_agent
    from utils.data_loader import get_example_wardrobe

    result = run_agent(
        query="vintage graphic tee under $30, size M",
        wardrobe=get_example_wardrobe(),
    )
    print(result["fit_card"])
    print(result["error"])   # None on success
"""

import json
import os
import re

from dotenv import load_dotenv
from groq import Groq

from tools import search_listings, suggest_outfit, create_fit_card

load_dotenv()


# ── session state ─────────────────────────────────────────────────────────────

def _new_session(query: str, wardrobe: dict) -> dict:
    """Initialize and return a fresh session dict for one user interaction."""
    return {
        "query": query,
        "parsed": {},
        "search_results": [],
        "selected_item": None,
        "wardrobe": wardrobe,
        "outfit_suggestion": None,
        "fit_card": None,
        "error": None,
    }


# ── query parser ──────────────────────────────────────────────────────────────

def _parse_query(query: str) -> dict:
    """
    Extract description, size, and max_price from a natural language query.
    Uses the Groq LLM for extraction. Falls back to regex on exception.

    Returns:
        dict with keys: description (str), size (str|None), max_price (float|None)
    """
    try:
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise ValueError("No API key")

        client = Groq(api_key=api_key)
        prompt = f"""Extract search parameters from this thrift shopping query.

Query: "{query}"

Return a JSON object with exactly these fields:
- "description": the item type and style keywords (string, e.g. "vintage graphic tee")
- "size": the size if mentioned (string like "M", "S", "XL", "US 8", "W30") or null if not mentioned
- "max_price": the maximum price as a number if mentioned (e.g. 30.0) or null if not mentioned

Return only the JSON object, no explanation."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=100,
        )
        text = response.choices[0].message.content.strip()
        # Extract JSON from response (handle markdown code blocks)
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            parsed = json.loads(json_match.group())
            return {
                "description": str(parsed.get("description", query)),
                "size": parsed.get("size") or None,
                "max_price": float(parsed["max_price"]) if parsed.get("max_price") is not None else None,
            }
    except Exception:
        pass

    # Fallback: regex extraction
    size_match = re.search(
        r'\bsize\s+([A-Z0-9/]+)\b|\b(XS|S|M|L|XL|XXL|2XL|3XL)\b',
        query, re.IGNORECASE
    )
    price_match = re.search(r'\$\s*(\d+(?:\.\d+)?)', query)

    size = None
    if size_match:
        size = (size_match.group(1) or size_match.group(2)).upper()

    max_price = float(price_match.group(1)) if price_match else None

    # Strip size and price phrases from description
    description = re.sub(r'(size\s+\S+|\$\s*\d+(?:\.\d+)?|under\s+\S+|for\s+\$\S+)', '', query, flags=re.IGNORECASE)
    description = ' '.join(description.split())

    return {"description": description or query, "size": size, "max_price": max_price}


# ── planning loop ─────────────────────────────────────────────────────────────

def run_agent(query: str, wardrobe: dict) -> dict:
    """
    Main agent entry point. Runs the FitFindr planning loop for a single
    user interaction and returns the completed session dict.

    Args:
        query:    Natural language user request
        wardrobe: User's wardrobe dict

    Returns:
        Session dict. Check session["error"] first — if not None, interaction
        ended early and outfit_suggestion / fit_card will be None.
    """
    session = _new_session(query, wardrobe)

    # Step 2: Parse query into structured parameters
    session["parsed"] = _parse_query(query)
    parsed = session["parsed"]

    # Step 3: Search listings
    session["search_results"] = search_listings(
        parsed["description"],
        parsed.get("size"),
        parsed.get("max_price"),
    )

    # Branch A: no results — set error and return early
    if not session["search_results"]:
        context = ""
        if parsed.get("size"):
            context += f" in size {parsed['size']}"
        if parsed.get("max_price") is not None:
            context += f" under ${parsed['max_price']:.2f}"
        session["error"] = (
            f"No listings found for '{parsed['description']}'{context}. "
            "Try different keywords, remove the size filter, or raise your price limit."
        )
        return session

    # Branch B: results found — select top item and continue
    session["selected_item"] = session["search_results"][0]

    # Step 5: Suggest outfit
    session["outfit_suggestion"] = suggest_outfit(
        session["selected_item"],
        session["wardrobe"],
    )

    # Step 6: Create fit card
    session["fit_card"] = create_fit_card(
        session["outfit_suggestion"],
        session["selected_item"],
    )

    return session


# ── CLI test ──────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    from utils.data_loader import get_example_wardrobe, get_empty_wardrobe

    print("=== Happy path: graphic tee ===\n")
    session = run_agent(
        query="looking for a vintage graphic tee under $30",
        wardrobe=get_example_wardrobe(),
    )
    if session["error"]:
        print(f"Error: {session['error']}")
    else:
        print(f"Found: {session['selected_item']['title']}")
        print(f"\nOutfit: {session['outfit_suggestion']}")
        print(f"\nFit card: {session['fit_card']}".encode('ascii', errors='replace').decode('ascii'))

    print("\n\n=== No-results path ===\n")
    session2 = run_agent(
        query="designer ballgown size XXS under $5",
        wardrobe=get_example_wardrobe(),
    )
    print(f"Error message: {session2['error']}")
    print(f"fit_card is None: {session2['fit_card'] is None}")
    print(f"outfit_suggestion is None: {session2['outfit_suggestion'] is None}")
