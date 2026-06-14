"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.
    """
    try:
        listings = load_listings()
    except Exception:
        return []

    # Step 1: filter by price
    if max_price is not None:
        listings = [item for item in listings if item["price"] <= max_price]

    # Step 2: filter by size (case-insensitive substring match)
    if size is not None:
        size_lower = size.lower()
        listings = [
            item for item in listings
            if size_lower in item["size"].lower()
        ]

    # Step 3: score by keyword overlap with description
    keywords = set(description.lower().split())

    def score(item: dict) -> int:
        # Build a bag of words from searchable fields
        fields = [
            item.get("title", ""),
            item.get("description", ""),
            item.get("category", ""),
            item.get("brand", "") or "",
        ]
        text = " ".join(fields).lower()
        # Also include style_tags and colors as individual tokens
        for tag in item.get("style_tags", []):
            text += " " + tag.lower()
        for color in item.get("colors", []):
            text += " " + color.lower()

        tokens = set(text.split())
        return len(keywords & tokens)

    # Step 4: drop zero-score listings
    scored = [(score(item), item) for item in listings]
    scored = [(s, item) for s, item in scored if s > 0]

    # Step 5: sort by score descending, return dicts only
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offers general styling advice for the item.
    """
    try:
        client = _get_groq_client()

        item_title = new_item.get("title", "the item")
        item_category = new_item.get("category", "")
        item_colors = ", ".join(new_item.get("colors", []))
        item_tags = ", ".join(new_item.get("style_tags", []))
        item_description = new_item.get("description", "")

        wardrobe_items = wardrobe.get("items", [])

        if not wardrobe_items:
            # Empty wardrobe — give general styling advice
            prompt = f"""You are a thrift fashion stylist. A user just found this secondhand item:

Item: {item_title}
Category: {item_category}
Colors: {item_colors}
Style vibes: {item_tags}
Description: {item_description}

The user doesn't have their wardrobe set up yet. Give 1-2 specific outfit ideas for this item — what types of pieces would pair well with it (bottoms, shoes, outerwear, accessories). Mention specific colors, silhouettes, and vibes. Keep it casual and conversational, 3-5 sentences total."""

        else:
            # Build wardrobe summary
            wardrobe_lines = []
            for w in wardrobe_items:
                colors = ", ".join(w.get("colors", []))
                tags = ", ".join(w.get("style_tags", []))
                notes = w.get("notes", "")
                line = f"- {w['name']} ({colors}) [{tags}]"
                if notes:
                    line += f" — {notes}"
                wardrobe_lines.append(line)
            wardrobe_text = "\n".join(wardrobe_lines)

            prompt = f"""You are a thrift fashion stylist. A user just found this secondhand item:

Item: {item_title}
Category: {item_category}
Colors: {item_colors}
Style vibes: {item_tags}
Description: {item_description}

Their current wardrobe includes:
{wardrobe_text}

Suggest 1-2 complete outfit combinations using this new item with specific pieces from their wardrobe above. Name the wardrobe pieces directly (e.g., "your baggy dark wash jeans"). Describe the overall vibe. Keep it casual and specific, 3-5 sentences total."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        result = response.choices[0].message.content.strip()
        return result if result else f"Style tip: {item_title} would look great with neutral basics — dark jeans and clean sneakers are always a solid starting point."

    except Exception:
        title = new_item.get("title", "this item")
        return f"Couldn't generate outfit suggestions right now. The {title} would pair well with neutral basics — try dark jeans and clean sneakers as a starting point."


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, returns a descriptive error message string.
    """
    # Guard: empty outfit
    if not outfit or not outfit.strip():
        return "Cannot create a fit card without an outfit suggestion. Please make sure suggest_outfit ran successfully first."

    try:
        client = _get_groq_client()

        item_title = new_item.get("title", "this piece")
        item_price = new_item.get("price", "")
        item_platform = new_item.get("platform", "a thrift app")
        item_condition = new_item.get("condition", "")

        price_str = f"${item_price:.2f}" if isinstance(item_price, (int, float)) else str(item_price)

        prompt = f"""You are writing an Instagram/TikTok caption for a thrift outfit post.

The thrifted item: {item_title}
Price paid: {price_str}
Found on: {item_platform}
Condition: {item_condition}

The outfit: {outfit}

Write a 2-4 sentence caption that:
- Sounds like a real person posting an OOTD, not a product description
- Mentions the item name, price ({price_str}), and platform ({item_platform}) naturally — once each
- Captures the specific vibe of the outfit in casual language
- Can include 1-2 relevant emojis if it feels right
- Does NOT start with "I" or sound like an ad

Write only the caption text, nothing else."""

        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.9,
            max_tokens=150,
        )
        result = response.choices[0].message.content.strip()
        return result if result else f"Fit card generation failed. Here's the raw look: {outfit}"

    except Exception:
        return f"Fit card generation failed. Here's the raw look: {outfit}"
