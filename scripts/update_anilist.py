#!/usr/bin/env python3
"""Refresh the linked AniList dropdowns in README.md using AniList's public GraphQL API."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://graphql.anilist.co"
USERNAME = os.environ.get("ANILIST_USERNAME", "Leafieboy")
README = Path(__file__).resolve().parents[1] / "README.md"

USER_QUERY = """
query ($name: String) {
  User(name: $name) {
    id
    favourites {
      anime(page: 1, perPage: 9) {
        nodes { title { userPreferred } siteUrl }
      }
      characters(page: 1, perPage: 10) {
        nodes { name { full } siteUrl }
      }
    }
  }
}
"""

WATCHING_QUERY = """
query ($userId: Int) {
  Page(page: 1, perPage: 10) {
    mediaList(userId: $userId, type: ANIME, status: CURRENT, sort: UPDATED_TIME_DESC) {
      media { title { userPreferred } siteUrl }
    }
  }
}
"""


def graphql(query: str, variables: dict) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = Request(
        API_URL,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError) as error:
        raise RuntimeError(f"AniList request failed: {error}") from error
    if body.get("errors"):
        messages = "; ".join(item.get("message", "GraphQL error") for item in body["errors"])
        raise RuntimeError(f"AniList GraphQL error: {messages}")
    return body["data"]


def markdown_label(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().replace("\\", "\\\\").replace("[", "\\[").replace("]", "\\]")


def list_markup(summary: str, entries: list[tuple[str, str]]) -> str:
    lines = [f"<details>", f"<summary>{summary}</summary>", ""]
    if entries:
        lines.extend(f"- [{markdown_label(title)}]({url})" for title, url in entries)
    else:
        lines.append("- Nothing listed publicly on AniList right now.")
    lines.extend(["", "</details>"])
    return "\n".join(lines)


def entries(nodes: list[dict], name_path: tuple[str, ...]) -> list[tuple[str, str]]:
    result = []
    for node in nodes:
        value = node
        for key in name_path:
            value = value.get(key) if isinstance(value, dict) else None
        url = node.get("siteUrl", "")
        if value and url.startswith("https://anilist.co/"):
            result.append((str(value), url))
    return result


def replace_section(text: str, key: str, content: str) -> str:
    pattern = re.compile(
        rf"<!-- {key}_START -->.*?<!-- {key}_END -->",
        re.DOTALL,
    )
    replacement = f"<!-- {key}_START -->\n{content}\n<!-- {key}_END -->"
    updated, count = pattern.subn(lambda _: replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"README is missing markers for {key}")
    return updated


def main() -> None:
    user_data = graphql(USER_QUERY, {"name": USERNAME}).get("User")
    if not user_data:
        raise RuntimeError(f"AniList user {USERNAME!r} was not found or is not public")

    watching_data = graphql(WATCHING_QUERY, {"userId": user_data["id"]})
    watching_nodes = watching_data.get("Page", {}).get("mediaList", [])
    favourites = user_data.get("favourites", {})

    sections = {
        "ANILIST_WATCHING": list_markup(
            "Currently watching",
            entries([item.get("media", {}) for item in watching_nodes], ("title", "userPreferred")),
        ),
        "ANILIST_FAVORITES": list_markup(
            "Favorite series",
            entries(favourites.get("anime", {}).get("nodes", []), ("title", "userPreferred")),
        ),
        "ANILIST_CHARACTERS": list_markup(
            "Favorite characters",
            entries(favourites.get("characters", {}).get("nodes", []), ("name", "full")),
        ),
    }

    readme = README.read_text(encoding="utf-8")
    for key, content in sections.items():
        readme = replace_section(readme, key, content)
    README.write_text(readme, encoding="utf-8", newline="\n")
    print(f"Updated AniList sections for {USERNAME}.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(error, file=sys.stderr)
        raise SystemExit(1)
