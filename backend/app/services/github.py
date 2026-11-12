"""Fetch public repo metadata from the GitHub API for form prefill."""

import re

import httpx

GITHUB_API = "https://api.github.com"

_PATTERNS = (
    r"github\.com/([^/\s?#]+)/([^/\s?#]+?)(?:\.git)?(?:[?#/]|$)",
    r"^([^/\s?#]+)/([^/\s?#]+)$",
)


def parse_repo_url(url: str) -> tuple[str, str] | None:
    text = (url or "").strip()
    for pattern in _PATTERNS:
        match = re.search(pattern, text)
        if match:
            owner, repo = match.group(1), match.group(2)
            if owner and repo:
                return owner, repo
    return None


async def fetch_repo_prefill(url: str, token: str | None = None) -> dict:
    parsed = parse_repo_url(url)
    if not parsed:
        raise ValueError("Could not parse a GitHub repository from that URL")
    owner, repo = parsed
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GITHUB_API}/repos/{owner}/{repo}", headers=headers)
        if resp.status_code == 404:
            raise LookupError("Repository not found on GitHub")
        if resp.status_code == 403:
            raise RuntimeError("GitHub API rate limit reached, try again later")
        resp.raise_for_status()
        data = resp.json()
        readme_text = ""
        try:
            readme_resp = await client.get(
                f"{GITHUB_API}/repos/{owner}/{repo}/readme",
                headers={**headers, "Accept": "application/vnd.github.raw"},
            )
            if readme_resp.status_code == 200:
                readme_text = readme_resp.text[:4000]
        except httpx.HTTPError:
            readme_text = ""

    tech_stack = [t for t in [data.get("language")] if t]
    tech_stack += [t for t in (data.get("topics") or []) if t and t not in tech_stack]
    return {
        "title": data.get("name") or repo,
        "description": data.get("description") or "",
        "github_url": data.get("html_url") or f"https://github.com/{owner}/{repo}",
        "live_url": (data.get("homepage") or "").strip() or None,
        "tech_stack": tech_stack[:10],
        "readme_excerpt": readme_text,
        "stars": data.get("stargazers_count", 0),
    }
