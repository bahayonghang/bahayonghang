from __future__ import annotations

import json
import math
import os
import textwrap
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime
from html import escape
from pathlib import Path


API_ROOT = "https://api.github.com"
BACKGROUND = "#0D1117"
PANEL = "#161B22"
STROKE = "#30363D"
TEXT = "#C9D1D9"
MUTED = "#8B949E"
ACCENT = "#58A6FF"
ACCENT_ALT = "#7EE787"
ACCENT_WARM = "#F778BA"


def github_get(url: str, token: str | None) -> object:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "bahayonghang-profile-metrics",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch_paginated(url: str, token: str | None) -> list[dict]:
    items: list[dict] = []
    page = 1
    while True:
        separator = "&" if "?" in url else "?"
        batch = github_get(f"{url}{separator}per_page=100&page={page}", token)
        if not isinstance(batch, list):
            raise RuntimeError(f"Expected a list response from {url}")
        if not batch:
            return items
        items.extend(batch)
        if len(batch) < 100:
            return items
        page += 1


def format_number(value: int) -> str:
    return f"{value:,}"


def truncate(text: str | None, limit: int) -> str:
    if not text:
        return "No description provided."
    stripped = " ".join(text.split())
    if len(stripped) <= limit:
        return stripped
    return stripped[: limit - 1].rstrip() + "..."


def wrap_lines(text: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(text, width=width) or [text]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = truncate(lines[-1], max(4, width - 1))
    return lines


def language_palette(index: int, fallback: str | None) -> str:
    palette = [
        "#58A6FF",
        "#F778BA",
        "#7EE787",
        "#FF7B72",
        "#D2A8FF",
        "#FFA657",
        "#A5D6FF",
        "#56D364",
    ]
    return fallback or palette[index % len(palette)]


def build_overview_svg(user: dict, repos: list[dict], merged_prs: int, subtitle: str | None = None) -> str:
    public_repos = sum(1 for repo in repos if not repo.get("fork"))
    stars = sum(int(repo.get("stargazers_count", 0)) for repo in repos if not repo.get("fork"))
    forks = sum(int(repo.get("forks_count", 0)) for repo in repos if not repo.get("fork"))
    created_at = datetime.fromisoformat(str(user["created_at"]).replace("Z", "+00:00"))
    updated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    stats = [
        ("Followers", format_number(int(user.get("followers", 0))), ACCENT),
        ("Public Repos", format_number(public_repos), ACCENT_ALT),
        ("Stars Earned", format_number(stars), ACCENT_WARM),
        ("Merged PRs", format_number(merged_prs), "#D2A8FF"),
    ]

    stat_cards: list[str] = []
    positions = [(24, 72), (220, 72), (24, 124), (220, 124)]
    for (label, value, color), (x, y) in zip(stats, positions, strict=True):
        stat_cards.append(
            f"""
            <rect x="{x}" y="{y}" width="172" height="44" rx="12" fill="{PANEL}" stroke="{STROKE}" />
            <text x="{x + 16}" y="{y + 18}" fill="{MUTED}" font-size="11">{escape(label)}</text>
            <text x="{x + 16}" y="{y + 35}" fill="{color}" font-size="18" font-weight="700">{escape(value)}</text>
            """
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="180" viewBox="0 0 420 180" role="img" aria-labelledby="title desc">
  <title id="title">GitHub overview</title>
  <desc id="desc">Overview card for {escape(str(user.get("login", "")))} with repository and contribution summary.</desc>
  <style>
    text {{
      font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
  <rect width="420" height="180" rx="18" fill="{BACKGROUND}" />
  <text x="24" y="34" fill="{TEXT}" font-size="20" font-weight="700">Profile Overview</text>
  <text x="24" y="54" fill="{MUTED}" font-size="12">{escape(subtitle or f"Joined {created_at.strftime('%b %Y')} - {format_number(forks)} total forks across owned repositories")}</text>
  {''.join(stat_cards)}
  <text x="396" y="164" fill="{MUTED}" font-size="10" text-anchor="end">Updated {updated_at}</text>
</svg>
"""


def build_languages_svg(
    language_totals: dict[str, dict[str, int | str | None]],
    precise_breakdown: bool,
) -> str:
    entries = sorted(
        language_totals.items(),
        key=lambda item: int(item[1]["bytes"]),
        reverse=True,
    )[:5]
    total = sum(int(meta["bytes"]) for _, meta in entries) or 1

    if not entries:
        rows = [
            f"""
            <text x="24" y="96" fill="{TEXT}" font-size="13" font-weight="600">Metrics are waiting for the next successful refresh.</text>
            <text x="24" y="118" fill="{MUTED}" font-size="12">GitHub Actions will replace this fallback view with live language data.</text>
            """
        ]
        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="180" viewBox="0 0 420 180" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">Top languages across owned GitHub repositories.</desc>
  <style>
    text {{
      font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
  <rect width="420" height="180" rx="18" fill="{BACKGROUND}" />
  <text x="24" y="34" fill="{TEXT}" font-size="20" font-weight="700">Top Languages</text>
  <text x="24" y="54" fill="{MUTED}" font-size="12">Waiting for a live API refresh</text>
  {''.join(rows)}
</svg>
"""

    rows: list[str] = []
    y = 68
    for index, (name, meta) in enumerate(entries):
        bytes_used = int(meta["bytes"])
        percent = bytes_used / total * 100
        color = language_palette(index, str(meta.get("color") or ""))
        bar_width = max(8, math.floor((bytes_used / total) * 190))
        rows.append(
            f"""
            <circle cx="30" cy="{y - 4}" r="5" fill="{color}" />
            <text x="44" y="{y}" fill="{TEXT}" font-size="12" font-weight="600">{escape(name)}</text>
            <rect x="150" y="{y - 11}" width="190" height="10" rx="5" fill="{PANEL}" />
            <rect x="150" y="{y - 11}" width="{bar_width}" height="10" rx="5" fill="{color}" />
            <text x="390" y="{y}" fill="{MUTED}" font-size="12" text-anchor="end">{percent:.1f}%</text>
            """
        )
        y += 24

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="420" height="180" viewBox="0 0 420 180" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">Top languages across owned GitHub repositories.</desc>
  <style>
    text {{
      font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
  <rect width="420" height="180" rx="18" fill="{BACKGROUND}" />
  <text x="24" y="34" fill="{TEXT}" font-size="20" font-weight="700">Top Languages</text>
  <text x="24" y="54" fill="{MUTED}" font-size="12">{"Calculated from repository language byte sizes" if precise_breakdown else "Fallback view based on primary repository languages"}</text>
  {''.join(rows)}
</svg>
"""


def build_featured_svg(repos: list[dict]) -> str:
    featured = sorted(
        (repo for repo in repos if not repo.get("fork")),
        key=lambda repo: (
            int(repo.get("stargazers_count", 0)),
            int(repo.get("forks_count", 0)),
            str(repo.get("updated_at", "")),
        ),
        reverse=True,
    )[:3]

    if not featured:
        featured = [
            {
                "name": "No public repositories yet",
                "description": "Create a repository to populate this section.",
                "stargazers_count": 0,
                "forks_count": 0,
                "language": "GitHub",
            }
        ]

    cards: list[str] = []
    for index, repo in enumerate(featured):
        x = 24 + index * 284
        desc_lines = wrap_lines(truncate(str(repo.get("description") or ""), 88), width=26, max_lines=2)
        language = repo.get("language") or "Mixed"
        cards.append(
            f"""
            <rect x="{x}" y="56" width="260" height="88" rx="14" fill="{PANEL}" stroke="{STROKE}" />
            <text x="{x + 16}" y="82" fill="{TEXT}" font-size="15" font-weight="700">{escape(str(repo.get("name", "")))}</text>
            <text x="{x + 16}" y="104" fill="{MUTED}" font-size="11">{escape(desc_lines[0])}</text>
            {"".join(f'<text x="{x + 16}" y="{104 + (line_index + 1) * 14}" fill="' + MUTED + f'" font-size="11">{escape(line)}</text>' for line_index, line in enumerate(desc_lines[1:]))}
            <text x="{x + 16}" y="130" fill="{ACCENT}" font-size="11">Stars {format_number(int(repo.get("stargazers_count", 0)))}</text>
            <text x="{x + 84}" y="130" fill="{ACCENT_ALT}" font-size="11">Forks {format_number(int(repo.get("forks_count", 0)))}</text>
            <text x="{x + 244}" y="130" fill="{MUTED}" font-size="11" text-anchor="end">{escape(str(language))}</text>
            """
        )

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="900" height="160" viewBox="0 0 900 160" role="img" aria-labelledby="title desc">
  <title id="title">Featured repositories</title>
  <desc id="desc">Featured repositories based on stars and recent activity.</desc>
  <style>
    text {{
      font-family: 'Segoe UI', 'Helvetica Neue', Arial, sans-serif;
    }}
  </style>
  <rect width="900" height="160" rx="18" fill="{BACKGROUND}" />
  <text x="24" y="34" fill="{TEXT}" font-size="20" font-weight="700">Featured Projects</text>
  <text x="24" y="54" fill="{MUTED}" font-size="12">Pinned automatically from public repositories with the strongest signal</text>
  {''.join(cards)}
</svg>
"""


def main() -> None:
    username = os.environ.get("PROFILE_USERNAME", "bahayonghang")
    token = os.environ.get("GITHUB_TOKEN")
    fallback_mode = False

    try:
        user = github_get(f"{API_ROOT}/users/{urllib.parse.quote(username)}", token)
        if not isinstance(user, dict):
            raise RuntimeError("Expected user payload to be a dictionary")

        repos = fetch_paginated(f"{API_ROOT}/users/{urllib.parse.quote(username)}/repos?type=owner&sort=updated", token)
        merged_search = github_get(
            f"{API_ROOT}/search/issues?q={urllib.parse.quote(f'author:{username} type:pr is:merged')}&per_page=1",
            token,
        )
        if not isinstance(merged_search, dict):
            raise RuntimeError("Expected merged PR search payload to be a dictionary")
        merged_prs = int(merged_search.get("total_count", 0))
    except urllib.error.HTTPError as error:
        if error.code != 403 or token:
            raise
        fallback_mode = True
        user = {
            "login": username,
            "created_at": "2021-06-06T00:00:00Z",
            "followers": 0,
        }
        repos = [
            {
                "name": Path(__file__).resolve().parents[2].name,
                "description": "Profile metrics refresh automatically in GitHub Actions when the API is available.",
                "stargazers_count": 0,
                "forks_count": 0,
                "language": "README",
            }
        ]
        merged_prs = 0

    language_totals: dict[str, dict[str, int | str | None]] = {}
    precise_breakdown = True
    for repo in repos:
        if repo.get("fork"):
            continue
        try:
            languages = github_get(str(repo["languages_url"]), token)
        except urllib.error.HTTPError as error:
            if error.code == 403:
                precise_breakdown = False
                primary_language = repo.get("language") or "Other"
                existing = language_totals.setdefault(str(primary_language), {"bytes": 0, "color": None})
                existing["bytes"] = int(existing["bytes"]) + 1
                continue
            raise
        except KeyError:
            precise_breakdown = False
            primary_language = repo.get("language") or "Other"
            existing = language_totals.setdefault(str(primary_language), {"bytes": 0, "color": None})
            existing["bytes"] = int(existing["bytes"]) + 1
            continue
        if not isinstance(languages, dict):
            continue
        for language, byte_count in languages.items():
            existing = language_totals.setdefault(language, {"bytes": 0, "color": None})
            existing["bytes"] = int(existing["bytes"]) + int(byte_count)

    output_dir = Path(__file__).resolve().parents[2] / "assets" / "github-stats"
    output_dir.mkdir(parents=True, exist_ok=True)

    subtitle = None
    if fallback_mode:
        subtitle = "GitHub API rate-limited locally - the workflow will refresh live metrics automatically"

    (output_dir / "overview.svg").write_text(build_overview_svg(user, repos, merged_prs, subtitle), encoding="utf-8")
    (output_dir / "languages.svg").write_text(build_languages_svg(language_totals, precise_breakdown), encoding="utf-8")
    (output_dir / "featured.svg").write_text(build_featured_svg(repos), encoding="utf-8")

    print(f"Generated profile metrics in {output_dir}")


if __name__ == "__main__":
    main()
