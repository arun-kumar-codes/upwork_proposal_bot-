#!/usr/bin/env python3
"""Read-only Hub <-> Bot handshake check. Stdlib only, no DB writes.

Usage:
    python scripts/check_handshake.py [--hub URL] [--bot URL]

Reads .env (repo root) plus environment: HUB_URL or NEXT_PUBLIC_API_URL,
BOT_URL, API_KEY or HUB_API_KEY, BOT_API_KEY. Bodies are truncated.
Exit 0 when hard checks pass (warnings allowed), 1 on failure.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 200


def load_dotenv() -> dict:
    values: dict[str, str] = {}
    env_file = REPO_ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")
    return values


def cfg(name: str, dotenv: dict, *fallbacks: str) -> str:
    for candidate in (os.environ.get(name), dotenv.get(name)):
        if candidate:
            return candidate.strip()
    for fallback in fallbacks:
        value = os.environ.get(fallback) or dotenv.get(fallback)
        if value:
            return value.strip()
    return ""


def truncate(text: str, limit: int = MAX_BODY) -> str:
    flat = " ".join((text or "").split())
    return flat if len(flat) <= limit else flat[:limit] + "...[truncated]"


def is_html_response(content_type: str, body: str) -> bool:
    head = (body or "").lstrip().lower()[:200]
    return "text/html" in (content_type or "").lower() or head.startswith(
        ("<!doctype html", "<html")
    )


def request(method: str, url: str, headers: dict | None = None, payload: dict | None = None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if payload is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read().decode(errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("Content-Type", "") if exc.headers else "", exc.read().decode(errors="replace")
    except Exception as exc:  # connection/timeout -> caller reports unreachable
        raise ConnectionError(str(exc)) from exc


class Report:
    def __init__(self) -> None:
        self.failures = 0

    def ok(self, msg: str) -> None:
        print(f"PASS  {msg}")

    def warn(self, msg: str) -> None:
        print(f"WARN  {msg}")

    def fail(self, msg: str) -> None:
        self.failures += 1
        print(f"FAIL  {msg}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check the Hub <-> Bot handshake (read-only).")
    parser.add_argument("--hub", help="Hub base URL (default: HUB_URL / NEXT_PUBLIC_API_URL)")
    parser.add_argument("--bot", help="Bot base URL (default: BOT_URL)")
    args = parser.parse_args(argv)

    dotenv = load_dotenv()
    hub = (args.hub or cfg("HUB_URL", dotenv, "NEXT_PUBLIC_API_URL")).rstrip("/")
    bot = (args.bot or cfg("BOT_URL", dotenv)).rstrip("/")
    hub_key = cfg("API_KEY", dotenv, "HUB_API_KEY")
    bot_key = cfg("BOT_API_KEY", dotenv)
    report = Report()

    if not hub:
        report.fail("No Hub URL: set HUB_URL (or NEXT_PUBLIC_API_URL) or pass --hub.")
    if not bot:
        report.fail("No bot URL: set BOT_URL or pass --bot.")
    if report.failures:
        return 1

    # Hub health (no auth) — also catches BOT_URL/HUB_URL mix-ups via bot checks.
    try:
        status, ctype, body = request("GET", f"{hub}/health")
        if status == 200 and not is_html_response(ctype, body):
            report.ok(f"Hub /health -> 200 {truncate(body)}")
        else:
            report.fail(f"Hub /health -> {status} (expected JSON 200): {truncate(body)}")
    except ConnectionError as exc:
        report.fail(f"Hub /health unreachable: {truncate(str(exc))}")

    # Playground status (auth) — bot_configured must reflect URL+key on the Hub.
    if hub_key:
        try:
            status, _c, body = request(
                "GET", f"{hub}/api/playground/status", headers={"X-API-Key": hub_key}
            )
            if status == 200:
                data = json.loads(body)
                report.ok(
                    "Hub /api/playground/status -> "
                    f"llm={data.get('llm_configured')} bot={data.get('bot_configured')} "
                    f"github={data.get('github_configured')} model={data.get('llm_model')}"
                )
                if not data.get("bot_configured"):
                    report.warn("Hub bot_configured is false: Real Bot needs BOT_URL + BOT_API_KEY on the Hub.")
            else:
                report.fail(f"Hub /api/playground/status -> {status}: {truncate(body)}")
        except ConnectionError as exc:
            report.fail(f"Hub /api/playground/status unreachable: {truncate(str(exc))}")
        except json.JSONDecodeError:
            report.fail(f"Hub /api/playground/status returned non-JSON: {truncate(body)}")
    else:
        report.warn("No API_KEY/HUB_API_KEY set: skipped authenticated Hub checks.")

    # Active projects live_url warnings (read-only).
    if hub_key:
        try:
            status, _c, body = request(
                "GET", f"{hub}/api/projects?status=active&limit=100",
                headers={"X-API-Key": hub_key},
            )
            if status == 200:
                projects = json.loads(body)
                missing = [p for p in projects if not (p.get("live_url") or "").strip()]
                if missing:
                    for p in missing[:10]:
                        report.warn(f"Active project without live_url: {truncate(str(p.get('title')), 80)}")
                    if len(missing) > 10:
                        report.warn(f"...and {len(missing) - 10} more without live_url.")
                else:
                    report.ok(f"All {len(projects)} active projects have live_url.")
        except (ConnectionError, json.JSONDecodeError):
            report.warn("Could not check active projects for live_url.")

    # Bot: frontend-HTML trap first, then health + auth paths.
    try:
        status, ctype, body = request("GET", f"{bot}/health")
        if is_html_response(ctype, body):
            report.fail(
                "BOT_URL points at Hub frontend HTML, not the bot. "
                f"Point BOT_URL at the bot service (got {status} HTML: {truncate(body, 120)})"
            )
        elif status == 200:
            report.ok(f"Bot /health -> 200 {truncate(body)}")
        else:
            report.fail(f"Bot /health -> {status}: {truncate(body)}")
    except ConnectionError as exc:
        report.fail(f"Bot /health unreachable: {truncate(str(exc))}")

    try:
        status, ctype, body = request(
            "POST", f"{bot}/generate",
            headers={"X-API-Key": "definitely-wrong-key"},
            payload={"profile": "check", "client_message": "handshake check"},
        )
        if is_html_response(ctype, body):
            report.fail("Bot /generate returned HTML: BOT_URL likely points at the frontend, not the bot.")
        elif status == 401:
            report.ok("Bot /generate wrong key -> 401 (auth enforced).")
        elif status == 503:
            report.warn("Bot /generate -> 503: BOT_API_KEY is not set on the bot.")
        else:
            report.fail(f"Bot /generate wrong key -> {status} (expected 401): {truncate(body)}")
    except ConnectionError as exc:
        report.fail(f"Bot /generate unreachable: {truncate(str(exc))}")

    if bot_key:
        # Probe with a real Hub freelancer: unknown profiles now correctly
        # get 404, so "check" would fail the happy path by design.
        probe_profile = ""
        if hub_key:
            try:
                pstatus, _pc, pbody = request(
                    "GET", f"{hub}/api/meta/profiles", headers={"X-API-Key": hub_key}
                )
                if pstatus == 200:
                    profiles = json.loads(pbody)
                    if profiles:
                        probe_profile = str(profiles[0].get("name") or "")
            except (ConnectionError, json.JSONDecodeError):
                probe_profile = ""
        try:
            status, _c, body = request(
                "POST", f"{bot}/generate",
                headers={"X-API-Key": bot_key},
                payload={"profile": probe_profile or "check", "client_message": "handshake check"},
            )
            if status == 200:
                report.ok(f"Bot /generate correct key -> 200 {truncate(body, 120)}")
            elif status == 404 and not probe_profile:
                report.ok("Bot /generate correct key -> 404 for unknown profile (isolation enforced; no Hub profile list available to probe with).")
            elif status == 503:
                report.warn("Bot /generate correct key -> 503: bot has no BOT_API_KEY (Hub key alone is not enough).")
            else:
                report.fail(f"Bot /generate correct key -> {status}: {truncate(body)}")
        except ConnectionError as exc:
            report.fail(f"Bot /generate unreachable: {truncate(str(exc))}")
    else:
        report.warn("No BOT_API_KEY set locally: skipped correct-key bot check.")

    print("RESULT: " + ("FAIL" if report.failures else "OK (warnings allowed)"))
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
