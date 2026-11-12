"""Test Playground logic: detect category, select projects, generate the reply."""

import re

import httpx

from ..config import settings
from ..models import Profile, Project
from .profile_names import is_valid_profile_name

class BotAuthError(RuntimeError):
    """Bot rejected the Hub key (bot HTTP 401): key mismatch."""


class BotNotConfiguredError(RuntimeError):
    """Bot has no BOT_API_KEY configured (bot HTTP 503)."""


class BotUnreachableError(RuntimeError):
    """Bot unreachable, timed out, or returned an unexpected error."""

_WORD = re.compile(r"[a-z0-9+#]+")


def detect_category(message: str, categories: list[str]) -> str | None:
    """Score known categories against the client message; best match wins.

    Hub categories are project labels, so a voice, store or dashboard post
    names no Hub category token. When no Hub category scores, fall back to
    the job's primary need so those posts still get an accurate category
    instead of a blank one. Need labels never collide with Hub category
    tokens, so project-pool filtering and scoring are unaffected.
    """
    text = (message or "").lower()
    words = set(_WORD.findall(text))
    best: str | None = None
    best_score = 0
    for raw in categories:
        cat = (raw or "").strip().lower()
        if not cat:
            continue
        score = sum(1 for tok in _WORD.findall(cat) if tok in words)
        if cat in text:
            score += 3
        if score > best_score:
            best, best_score = cat, score
    if best is not None:
        return best
    primary = analyze_job(message)["primary"]
    if primary is not None:
        return _NEED_CATEGORY.get(primary["key"])
    return None


# --- Job-requirement analysis -------------------------------------------------
# Deterministic reading of the client's post: what they need built, which
# technologies they name, and the content words that evidence must match.
# Nothing here invents facts: needs are matched on the client's own words,
# and technologies the client names are labelled "asks" — a proposal may
# only claim them when the freelancer's verified data supports them.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
    "we", "you", "our", "your", "need", "needs", "want", "looking", "build",
    "building", "built", "create", "develop", "developer", "hi", "hello",
    "i", "am", "is", "are", "that", "this", "it", "so", "can", "where",
    "style", "like", "online", "please", "us", "my", "me",
}
TECH_ALIASES: dict[str, list[str]] = {
    "ai": ["artificial intelligence", "machine learning", "openai", "llm", " ai "],
    "react": ["next.js", "nextjs", "reactjs", "react"],
    "vue": ["vuejs", "nuxt", "vue"],
    "python": ["python", "pandas", "django", "flask", "fastapi"],
    "shopify": ["shopify"],
    "backend": ["back-end", "back end", "backend", "rest api", "node.js", "nodejs", "express"],
    "frontend": ["front-end", "front end", "frontend", "angular"],
    "automation": ["automation", "automate", "automated"],
}
TECH_DISPLAY = {
    "ai": "AI", "react": "React", "vue": "Vue", "python": "Python",
    "shopify": "Shopify", "backend": "backend APIs", "frontend": "frontend",
    "automation": "automation",
}

# Ordered by specificity: the first matching need drives understanding and
# approach lines, so a voice-booking job reads as voice work, not generic AI.
# "proof" words are distinctive evidence: only they may support a
# "covers your ... need" claim. "weak" words show related experience only —
# a generic word such as "agent" or "AI" never proves voice calls, a store
# build, or any other specific capability.
NEED_SIGNALS: list[dict] = [
    {"key": "voice", "aliases": ["voice agent", "voice ai", "voice assistant", "phone call", "outbound calls", "inbound calls", "calls leads"],
     "label": "voice calls and booking",
     "understand": "you need a voice agent that talks to leads and books the meeting without your team chasing calls",
     "approach": "I would start with your call flow and booking rules and test real calls early so the tone and handoffs feel right",
     "proof": ["voice", "calls", "call", "calling", "phone", "telephony", "outbound", "inbound", "calendar", "booking", "whatsapp"],
     "weak": ["agent", "agents", "leads", "meetings"]},
    {"key": "docs", "aliases": ["documents", "manuals", "pdf", "knowledge base", "searching pdf", "our own docs"],
     "label": "answers from your documents",
     "understand": "you need quick answers from your own documents so your team stops hunting through files",
     "approach": "I would start with your real documents and the questions your team asks most and build the search around those first",
     "proof": ["documents", "document", "rag", "uploads", "questions", "answers", "manuals", "pdf"],
     "weak": []},
    {"key": "crm", "aliases": ["crm", "hubspot", "appointments", "front desk", "sales pipeline", "manage patient"],
     "label": "customer and booking flow",
     "understand": "you need one simple flow that keeps customers and bookings together instead of scattered follow ups",
     "approach": "I would start with your booking and follow up flow and keep it simple for the team that uses it daily",
     "proof": ["crm", "hospital", "appointments", "booking", "leads", "customers", "patient"],
     "weak": []},
    {"key": "store", "aliases": ["shopify", "store", "ecommerce", "e-commerce", "checkout", "cart", "pay online", "products"],
     "label": "store and checkout",
     "understand": "you need a store where customers can browse and pay without friction",
     "approach": "I would start with your product pages and checkout and get a live preview in front of you early",
     "proof": ["store", "shop", "shopify", "products", "checkout", "cart", "shoppers", "promotions", "ecommerce"],
     "weak": ["customers", "offers"]},
    {"key": "dashboard", "aliases": ["dashboard", "trading", "charts", "reporting", "admin panel", "analytics"],
     "label": "dashboard and live data",
     "understand": "you need a clear dashboard that shows live numbers and lets you act fast",
     "approach": "I would start with the main screen your team opens daily and wire the live data into that first",
     "proof": ["dashboard", "trading", "charts", "reporting", "analytics", "orders", "reports"],
     "weak": ["data", "platform", "live"]},
    {"key": "scraping", "aliases": ["scrap", "crawl", "extract data", "collect leads", "gather data"],
     "label": "data collection",
     "understand": "you need clean data collected on schedule without manual copying",
     "approach": "I would start with one source end to end and lock the output format before scaling to the rest",
     "proof": ["scrapes", "scraping", "extracts", "crawl", "crawls"],
     "weak": ["data", "websites", "pipeline"]},
    {"key": "automation", "aliases": ["automat", "whatsapp", "email sequence", "manual work", "manual steps", "manual process"],
     "label": "automation of manual work",
     "understand": "you need the slow manual steps taken off your team so follow ups happen on time every time",
     "approach": "I would map your current manual flow first and automate the slowest step first so you see value fast",
     "proof": ["automation", "automate", "automated", "workflow", "scheduling", "invoicing"],
     "weak": ["whatsapp", "email"]},
    {"key": "ai_agent", "aliases": ["ai agent", "chatbot", "ai assistant", "ai tool", "artificial intelligence", "agent that"],
     "label": "AI agent work",
     "understand": "you need an AI agent that does real work for customers instead of only answering chats",
     "approach": "I would start with the three jobs your agent must finish and build those end to end before adding extras",
     "proof": ["agent", "agents", "ai", "chatbot", "voice", "assistant", "automation"],
     "weak": []},
    {"key": "website", "aliases": ["website", "web app", "landing page", "web developer", "site for"],
     "label": "website build",
     "understand": "you need a clean website that explains your offer and turns visitors into enquiries",
     "approach": "I would start with your main page and enquiry flow and share a live preview in small steps",
     "proof": ["site", "website", "web", "pages", "login"],
     "weak": ["app"]},
]

# Primary need -> category label, used only when no Hub category matches.
_NEED_CATEGORY = {"voice": "voice", "store": "shopify", "dashboard": "dashboard"}


def canonical_techs(text: str) -> set[str]:
    lower = f" {(text or '').lower()} "
    return {
        canon
        for canon, aliases in TECH_ALIASES.items()
        if any(alias in lower for alias in aliases)
    }


def extract_client_name(message: str) -> str:
    """Client's first name when they introduce themselves, else ''."""
    match = re.search(
        r"(?:hi|hello|hey)[^.!\n]{0,30}?\bi(?:\s+am|'m)\s+([A-Za-z]{2,20})\b"
        r"|\bmy name is\s+([A-Za-z]{2,20})\b"
        r"|\bi(?:\s+am|'m)\s+([A-Za-z]{2,20})\b",
        message or "",
        flags=re.IGNORECASE,
    )
    if not match:
        return ""
    name = next(g for g in match.groups() if g)
    if name.lower() in _STOPWORDS or not is_valid_profile_name(name):
        return ""
    return name.capitalize()


def analyze_job(client_message: str, category: str | None = None) -> dict:
    """Read the job post: needs, named technologies, evidence words."""
    text = (client_message or "").lower()
    needs = [n for n in NEED_SIGNALS if any(a in text for a in n["aliases"])]
    words = {
        w for w in _WORD.findall(text) if len(w) > 2 and w not in _STOPWORDS
    }
    return {
        "needs": needs,
        "primary": needs[0] if needs else None,
        "tech_asks": canonical_techs(client_message or ""),
        "words": words,
        "client_name": extract_client_name(client_message or ""),
        "category": (category or "").strip().lower() or None,
    }


def verified_techs(profile: Profile, projects: list[Project]) -> list[str]:
    """Canonical technologies the freelancer's own data actually supports.

    Only profile skills and the selected projects' tech stacks count. Tech
    named solely in the client's post is never a freelancer skill.
    """
    found: list[str] = []

    def _add(canon: str) -> None:
        if canon not in found:
            found.append(canon)

    for skill in profile.skills or []:
        for canon in canonical_techs(str(skill)):
            _add(canon)
    for p in projects:
        stack = p.tech_stack if isinstance(p.tech_stack, list) else []
        for item in stack:
            for canon in canonical_techs(str(item)):
                _add(canon)
    return found


def _category_tokens(value: str | None) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", (value or "").lower()) if t}


def score_project(
    project: Project, analysis: dict, category: str | None
) -> tuple[int, list[str]]:
    """Relevance of one owned project to this job, with honest reasons."""
    score = 0
    reasons: list[str] = []
    proj_cat = (project.category or "").strip().lower()
    if category:
        if proj_cat == category:
            score += 4
            reasons.append(f"category match: '{category}'")
        elif _category_tokens(proj_cat) & _category_tokens(category):
            score += 2
            reasons.append(f"related category: '{proj_cat}'")
    public = public_proof_text(project)
    content = f"{project.title} {public} {project.description or ''}".lower()
    content_words = set(_WORD.findall(content))
    for need in analysis["needs"][:3]:
        hits = [w for w in need["proof"] if w in content_words]
        if hits:
            # Distinctive evidence only: this is the claim-eligible tier.
            score += 3
            reasons.append(f"covers your {need['label']} need")
        elif any(w in content_words for w in need.get("weak", [])):
            # Related experience: ranks below real proof, never claimed.
            score += 1
            reasons.append(f"related experience: {need['label']}")
    overlap = analysis["words"] & content_words
    if overlap:
        score += min(len(overlap), 4)
    stack_text = " ".join(
        str(s) for s in (project.tech_stack if isinstance(project.tech_stack, list) else [])
    )
    shared_tech = analysis["tech_asks"] & canonical_techs(stack_text)
    if shared_tech:
        score += 2 * len(shared_tech)
        reasons.append("uses tech you named: " + " and ".join(sorted(shared_tech)))
    if (project.live_url or "").strip():
        score += 1
    return score, reasons


def select_projects(
    projects: list[Project], category: str | None, limit: int,
    client_message: str = "",
) -> list[tuple[Project, str]]:
    """Pick the freelancer's most job-relevant projects, with reasons.

    Only the given (already profile-scoped) projects are ranked. When a
    category is known, projects sharing a category token form the pool;
    inside the pool, need/keyword/tech relevance beats recency, so the
    proof project is the closest match — not merely the newest.
    """
    analysis = analyze_job(client_message, category)
    pool = list(projects)
    related: list[Project] = []
    if category:
        related = [
            p for p in pool
            if _category_tokens(p.category) & _category_tokens(category)
        ]
        if related:
            pool = related
    scored = []
    for idx, p in enumerate(pool):
        score, reasons = score_project(p, analysis, category)
        # Relevance floor: a project with no relevance reasons at all is
        # not proposal proof, however recent or live it is. Returning []
        # gives the honest proof-free proposal instead of dressing up
        # unrelated work. The synthetic "no exact category match" note is
        # not a reason and never passes the floor on its own.
        if not reasons:
            continue
        if category and not related:
            reasons.insert(0, "no exact category match — closest relevant project")
        scored.append((score, idx, p, reasons))
    # Rank by relevance; recency (input order is newest-first) breaks ties.
    scored.sort(key=lambda item: (-item[0], item[1]))
    picked = []
    for _score, _idx, p, reasons in scored[:limit]:
        reason = "; ".join(dict.fromkeys(reasons)) or (
            "most relevant of your active projects"
        )
        picked.append((p, reason))
    return picked


def _project_brief(p: Project) -> str:
    # Live demos only: never put github_url in the LLM brief/reply text.
    link = (p.live_url or "").strip() or "no live demo link"
    parts = [f"- {p.title} ({link})"]
    if p.description:
        parts.append(f"  What it is: {p.description[:500]}")
    if p.tech_stack:
        tech = ", ".join(p.tech_stack) if isinstance(p.tech_stack, list) else p.tech_stack
        parts.append(f"  Tech: {tech}")
    public = public_proof_text(p)
    if public:
        parts.append(f"  Result: {public[:300]}")
    return "\n".join(parts)


# --- Proposal contract (same shape as the Real Bot) ---------------------------
# Simulated mode must produce the original Upwork Proposal Bot shape too:
# hey greeting / I am {Name} intro / recently + exact live_url / fit /
# "please review my portfolio: {link}" / fixed closing. Casual lowercase
# style, NO commas anywhere, no corporate cover-letter phrases. LLM output
# that fails validate_reply is replaced by the deterministic template.
PORTFOLIO_LINKS = {
    "aayush": "http://116.202.210.102:3700/portfolio/6943d95d20eafc5a71c0f96b",
    "atul": "http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff",
    "arun": "http://116.202.210.102:3700/portfolio/69492dc930db86ebbad04a03",
    "faisal": "http://116.202.210.102:3700/portfolio/695b83cff3cd570bc25c4db8",
    "mahima": "http://116.202.210.102:3700/portfolio/6949303130db86ebbad04a13",
    "kishan": "http://116.202.210.102:3700/portfolio/69492ffc30db86ebbad04a0f",
    "gopal": "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b",
    # Hub spells this freelancer "Gopalan"; the portfolio service identifies
    # the "gopal" ID above as Gopalan Prakash, so this is his verified link.
    "gopalan": "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b",
    "deepanshu": "http://116.202.210.102:3700/portfolio/69492f8e30db86ebbad04a07",
    "rahul": "http://116.202.210.102:3700/portfolio/69451bda999775a273ac7039",
    "yuvraj": "http://116.202.210.102:3700/portfolio/6944e7b2999775a273ac6ab6",
    "vikas kumar": "http://116.202.210.102:3700/portfolio/6949313330db86ebbad04a35",
    "vikas singh": "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17",
}
_PROFILE_ALIASES = {
    "faizal": "faisal",
    "faizal/lyt": "faisal",
    "faisal/lyt": "faisal",
    "faizal lyt": "faisal",
    "faisal lyt": "faisal",
    "lyt": "faisal",
    # Note: bare "Vikas" is deliberately NOT aliased to Vikas Singh. Singh is
    # credited only inside the verified combined profile (see
    # _COMBINED_COLLABORATORS below), never assigned to unrelated profiles.
}
_BANNED_PHRASES = [
    "thank you for reaching out",
    "i would love to help",
    "i'd love",
    "id love",
    "looking forward to connecting",
    "navigate and enhance",
    "seamless",
    "intricate codebases",
    "for your project",
]
_JOB_PHRASES = {
    "full stack": "I build complete web apps from the first screen to the live server",
    "AI": "I build AI tools that plug into real working products",
    "automation": "I automate slow manual work with clean scripts and pipelines",
    "Shopify": "I build stores that load fast and stay easy to manage",
    "Python": "I build backends and tools that stay simple to maintain",
    "web": "I build clean websites and web apps for real clients",
}
_CLOSING_CHECKPOINTS = {
    "voice": "You will hear test calls before the agent handles live leads.",
    "docs": "You will test answers from your real documents before a wider rollout.",
    "crm": "You will see one lead move through the full follow up flow before we widen it.",
    "store": "You will click through the buying flow before we polish the rest of the store.",
    "dashboard": "You will see the main screen running with live numbers before we add extra views.",
    "scraping": "You will check the first collected output before we add more sources.",
    "automation": "You will see the slowest manual step automated before we move to the next one.",
    "ai_agent": "You will try the first agent task yourself before we add more tasks.",
    "website": "You will review the main page live before we build the remaining pages.",
}


def _closing_lines(primary: dict | None, tier: str) -> list[str]:
    """Contextual closing: a job-specific first checkpoint plus one honest
    sentence about how the evidence supports that checkpoint."""
    key = primary["key"] if primary else ""
    first = _CLOSING_CHECKPOINTS.get(
        key, "You will see the smallest useful version working before we add more."
    )
    if tier == "COVER":
        second = "The project shown above gives that checkpoint a proven starting point."
    elif tier == "RELATED":
        second = (
            "The related work gives useful context and that checkpoint will "
            "prove the parts specific to your job."
        )
    else:
        second = "That checkpoint will prove the parts specific to your job before we expand the work."
    return [first, second]


def resolve_person(raw: str | None) -> tuple[str, str | None]:
    """Map a Hub profile name to (display name, portfolio URL or None)."""
    original = (raw or "").strip()
    if not is_valid_profile_name(original):
        # Placeholder bucket, never a display name ("I am Not ...").
        return "", None
    norm = re.sub(r"\s*[/,]\s*", "/", original.lower())
    norm = re.sub(r"\s+", " ", norm).strip()
    candidates = [norm, norm.split("/")[0].strip(), norm.split(" ")[0] if norm else ""]
    for cand in candidates:
        if not cand:
            continue
        canon = _PROFILE_ALIASES.get(cand, cand)
        if canon in PORTFOLIO_LINKS:
            # Verified freelancers sign with their full canonical name.
            full_name = " ".join(word.capitalize() for word in canon.split(" "))
            return full_name, PORTFOLIO_LINKS[canon]
    words = [w for w in re.split(r"[/,\s]+", original) if w]
    return (words[0].capitalize() if words else ""), None


# Explicit verified combined profiles -> credited collaborators. This is an
# allowlist, NOT people-list parsing: a name that merely contains "+", "/"
# or "," (e.g. "Kishan / Vikas", "Newdev + Vikas") earns no collaborator
# credit. Keys are separator-normalized ("gopalan+vikas"); values are
# (full name, portfolio) pairs verified against the Profile Manager and
# confirmed by the owner (Tellaigent: Gopalan Prakash + Vikas Singh).
_COMBINED_COLLABORATORS: dict[str, list[tuple[str, str]]] = {
    "gopalan+vikas": [("Vikas Singh", PORTFOLIO_LINKS["vikas singh"])],
    "gopalan+vikas singh": [("Vikas Singh", PORTFOLIO_LINKS["vikas singh"])],
    "gopal+vikas": [("Vikas Singh", PORTFOLIO_LINKS["vikas singh"])],
    "gopal+vikas singh": [("Vikas Singh", PORTFOLIO_LINKS["vikas singh"])],
}


def resolve_collaborators(raw: str | None) -> list[tuple[str, str]]:
    """Verified (full name, portfolio) collaborators for combined profiles.

    Only profiles listed in _COMBINED_COLLABORATORS get collaborator credit.
    The proposal still signs as the first contributor; people are never
    merged and each link stays attached to its verified owner.
    """
    original = (raw or "").strip()
    if not is_valid_profile_name(original):
        return []
    norm = re.sub(r"\s+", " ", original.lower())
    parts = [p.strip() for p in re.split(r"[+,/]", norm) if p.strip()]
    return list(_COMBINED_COLLABORATORS.get("+".join(parts), []))


def _clean_text(value, max_len: int = 160) -> str:
    text = str(value or "")
    text = re.sub(r"https?://\S+", " ", text)  # links come only from live_url
    text = re.sub(r"(?:www\.)?github\.com\S*", " ", text)
    text = text.replace(",", " ")  # proposals contain no commas
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].strip()
    return text


def _as_sentence(text) -> str:
    cleaned = _clean_text(text)
    return f"{cleaned.rstrip('.')}." if cleaned else ""


# --- Internal-notes guard -----------------------------------------------------
# Project `result` is imported from the Excel "Notes" column (and editable in
# the dashboard), so it mixes verified outcomes with operational remarks
# ("Git URL not given", "Team confirmed Active (Slack)", "Added from Google
# Sheet..."). Internal-tainted text must never reach a client proposal or an
# LLM prompt as project facts. A clean verified result wins; otherwise the
# public description; otherwise nothing (callers use a generic live line).
_INTERNAL_MARKERS = (
    "git url",
    "github",
    "slack",
    "google sheet",
    "spreadsheet",
    "excel",
    "added from",
    "imported from",
    "seeded",
    "linked to",
    "not given",
    "not provided",
    "team confirmed",
    "confirmed active",
    "internal note",
    # Status / collaboration boilerplate from the same Notes column: an
    # internal workflow state or a people note is never client proof.
    "doc status",
    "shared by",
    "live ip",
    "profile not",
    "not listed",
    "also listed",
    "listed twice",
    "counted once",
    "repo name",
    "on laptop",
    "cloudflare",
    "previous deployment",
    "saml login",
)


def _is_internal_note(text) -> bool:
    lower = str(text or "").lower()
    return any(marker in lower for marker in _INTERNAL_MARKERS)


def public_proof_text(project: Project) -> str:
    """The only project text a proposal or LLM prompt may present as fact."""
    result = (project.result or "").strip()
    description = (project.description or "").strip()
    if result and not _is_internal_note(result):
        return result
    if description and not _is_internal_note(description):
        return description
    # Fail closed: a tainted field is dropped whole, never sentence-mined.
    return ""


def cited_proof(projects: list[Project]) -> Project | None:
    """The project a proposal actually cites: first with a live link."""
    return next(
        (p for p in projects if (p.live_url or "").strip()),
        projects[0] if projects else None,
    )


def eligible_claim_labels(proof: Project | None, analysis: dict) -> set[str]:
    """Need labels the cited project may honestly claim to cover.

    Distinctive proof words only. A project matching nothing but a weak
    word (for example "agent" on a voice job) earns no coverage claim.
    """
    if proof is None:
        return set()
    content = (
        f"{proof.title} {public_proof_text(proof)} {proof.description or ''}"
    ).lower()
    content_words = set(_WORD.findall(content))
    return {
        need["label"]
        for need in analysis["needs"]
        if any(w in content_words for w in need["proof"])
    }


def need_tiers(
    proof: Project | None, analysis: dict, category: str | None
) -> dict[str, str]:
    """Per-need evidence tier of the cited project, keyed by need label.

    COVER: distinctive-evidence reason for that need ("covers your ...
    need"). RELATED: related reasons only. NONE: nothing. A claim about a
    need may never exceed that need's own tier — a project covering a
    secondary need does not earn coverage language for the primary need.
    """
    if proof is None:
        return {n["label"]: "NONE" for n in analysis["needs"]}
    _score, reasons = score_project(proof, analysis, category)
    tiers: dict[str, str] = {}
    for need in analysis["needs"]:
        label = need["label"]
        if f"covers your {label} need" in reasons:
            tiers[label] = "COVER"
        elif reasons:
            tiers[label] = "RELATED"
        else:
            tiers[label] = "NONE"
    return tiers


def claim_tier(
    proof: Project | None, analysis: dict, category: str | None
) -> str:
    """Evidence tier for the job's PRIMARY need (see need_tiers)."""
    primary = analysis.get("primary")
    if primary is None:
        if proof is None:
            return "NONE"
        _score, reasons = score_project(proof, analysis, category)
        if any(r.startswith("covers your") for r in reasons):
            return "COVER"
        return "RELATED" if reasons else "NONE"
    return need_tiers(proof, analysis, category).get(primary["label"], "NONE")


# Coverage-strength phrasing. At RELATED/NONE tier none of this may be said
# about the cited project: the scorer granted at most related experience.
_STRENGTH_PATTERNS = (
    r"covers your",
    r"directly related",
    r"closely aligns",
    r"aligns? with your",
    r"aligned with your",
    r"match(?:es)? your (?:needs|requirements)",
    r"perfect (?:fit|match)",
    r"ideal for your",
    r"same kind of",
    r"already built",
    r"exactly what you need",
)


def _exceeds_evidence(text: str) -> bool:
    lower = (text or "").lower()
    return any(re.search(p, lower) for p in _STRENGTH_PATTERNS)


def _role_for(category: str | None, projects: list[Project]) -> str:
    # Role describes the freelancer's own work: the top project's category
    # wins over the client's category, so a store job never relabels an
    # AI builder as "a Shopify dev".
    cat = ""
    if projects:
        cat = (projects[0].category or "").lower()
    if not cat:
        cat = (category or "").lower()
    if "full" in cat:
        return "full stack"
    if "shopify" in cat:
        return "Shopify"
    if "automation" in cat:
        return "automation"
    if "ai" in cat or "ml" in cat:
        return "AI"
    if "python" in cat:
        return "Python"
    return "web"


def template_reply(
    *,
    profile: Profile,
    projects: list[Project],
    client_message: str,
    category: str | None = None,
) -> str:
    """Deterministic contract proposal over the selected projects.

    Personalised greeting / verified intro / the client's problem in their
    terms / the most relevant proof project with its live link / a concrete
    first step for this job / fit lines / portfolio / fixed closing. Only
    verified skills are claimed; tech named solely in the job post is the
    client's ask, never the freelancer's experience.
    """
    name, portfolio = resolve_person(profile.name)
    portfolio = portfolio or (profile.portfolio_url or None)
    analysis = analyze_job(client_message, category)
    verified = verified_techs(profile, projects)
    ordered = [t for t in verified if t in analysis["tech_asks"]] + [
        t for t in verified if t not in analysis["tech_asks"]
    ]
    skills_phrase = " and ".join(TECH_DISPLAY.get(t, t) for t in ordered[:3])
    role = _role_for(category, projects)
    primary = analysis["primary"]

    client_name = analysis["client_name"]
    lines = [f"hey {client_name}" if client_name else "hey there", ""]
    intro = f"I am {name} a {role} dev" if name else f"I am a {role} dev"
    if skills_phrase:
        intro += f" I work with {skills_phrase}"
    lines.append(intro)
    lines.append(
        primary["understand"] if primary else _JOB_PHRASES.get(role, _JOB_PHRASES["web"])
    )

    proof = cited_proof(projects)
    if proof is not None:
        live = (proof.live_url or "").strip()
        lines.append("")
        lines.append(f"recently I worked on {_clean_text(proof.title, 80)}{f' {live}' if live else ''}")
        detail = _as_sentence(public_proof_text(proof))
        lines.append(
            detail
            or (
                "it is live right now and real users use it daily."
                if live
                else "the client still uses it in their daily work."
            )
        )
        _score, proof_reasons = score_project(proof, analysis, category)
        # The fit claim may cover only the PRIMARY need, and only at that
        # need's own COVER tier. Coverage of a secondary need is related
        # evidence for this job, never the headline claim.
        need_reason = next(
            (
                r
                for r in proof_reasons
                if primary is not None
                and r == f"covers your {primary['label']} need"
            ),
            None,
        )
        if need_reason:
            lines.append(f"I picked this one because it already {need_reason}.")
        elif primary is not None and any(
            r.startswith(("related experience", "covers your"))
            for r in proof_reasons
        ):
            # Related work only: never imply the specific capability.
            if primary["key"] == "voice":
                lines.append(
                    "I picked this one because it shows related AI agent work."
                )
            else:
                lines.append(
                    "I picked this one because it is my closest related work."
                )
        elif primary is not None:
            # No verified match for this need: show recent work honestly
            # instead of dressing it up as proof for their job.
            lines.append("I picked this one to show recent live work I shipped.")

    lines.append("")
    if primary:
        lines.append(primary["approach"])
    lines.extend(_closing_lines(primary, claim_tier(proof, analysis, category)))
    if portfolio:
        lines.append("")
        lines.append(f"please review my portfolio: {portfolio}")
    for collab_name, collab_url in resolve_collaborators(profile.name):
        lines.append(f"please review {collab_name}'s portfolio: {collab_url}")
    lines.append("")
    lines.append("Please let me know when we can proceed further.")
    lines.append("Best regards")
    if name:
        lines.append(name)
    return "\n".join(lines)


_CLAIM_PATTERNS = (
    r"i work with ([^\n.]*)",
    r"experience (?:in|with) ([^\n.]*)",
    r"speciali[sz]e in ([^\n.]*)",
    r"skilled in ([^\n.]*)",
)


def _claims_unverified_tech(text: str, verified: list[str]) -> bool:
    """True when a skill claim names technology with no verified source."""
    lower = (text or "").lower()
    for pattern in _CLAIM_PATTERNS:
        for match in re.finditer(pattern, lower):
            segment = f" {match.group(1)} "
            if any(
                canon not in verified
                and any(alias in segment for alias in aliases)
                for canon, aliases in TECH_ALIASES.items()
            ):
                return True
    return False


def validate_reply(
    text: str,
    *,
    portfolio: str | None,
    live_urls: list[str],
    collaborator_portfolios: list[str] | None = None,
    verified_techs_list: list[str] | None = None,
    unsupported_claim_labels: list[str] | None = None,
    claim_tier: str | None = None,
    need_tiers_map: dict[str, str] | None = None,
) -> bool:
    """True only if the text follows the proposal contract."""
    if not text:
        return False
    lower = text.lower()
    if "hey" not in lower or "recently" not in lower:
        return False
    if "," in text or "github.com" in lower:
        return False
    for label in unsupported_claim_labels or []:
        if f"covers your {label.lower()} need" in lower:
            return False  # coverage claim without distinctive evidence
    if claim_tier in ("RELATED", "NONE") and _exceeds_evidence(text):
        return False  # relevance language stronger than verified evidence
    for label, tier in (need_tiers_map or {}).items():
        if tier != "COVER" and f"covers your {label.lower()} need" in lower:
            return False  # this need's own tier does not support coverage
    if verified_techs_list is not None and _claims_unverified_tech(
        text, verified_techs_list
    ):
        return False  # skill claim with no verified source
    if any(phrase in lower for phrase in _BANNED_PHRASES):
        return False
    if portfolio and f"please review my portfolio: {portfolio}" not in text:
        return False
    for collab_url in collaborator_portfolios or []:
        if collab_url not in text:
            return False  # verified collaborator must be credited
    allowed = {u for u in [portfolio, *live_urls, *(collaborator_portfolios or [])] if u}
    for url in re.findall(r"https?://[^\s)]+", text):
        if url.rstrip(".") not in allowed:
            return False  # invented link
    if live_urls and live_urls[0] not in text:
        return False
    return True


async def generate_reply(
    *,
    profile: Profile,
    projects: list[Project],
    client_message: str,
    category: str | None = None,
) -> str:
    """Simulated mode: Hub LLM call held to the Real Bot proposal contract."""
    if not projects:
        # No eligible projects for this freelancer: never let the LLM invent
        # experience. The deterministic template omits the "recently" proof.
        return template_reply(
            profile=profile, projects=[], client_message=client_message, category=category
        )
    if not settings.openai_api_key:
        raise RuntimeError(
            "Simulated mode needs OPENAI_API_KEY (or LLM_API_KEY) in env"
        )
    name, portfolio = resolve_person(profile.name)
    portfolio = portfolio or (profile.portfolio_url or None)
    collaborators = resolve_collaborators(profile.name)
    collaborator_urls = [url for _n, url in collaborators]
    live_urls = [(p.live_url or "").strip() for p in projects if (p.live_url or "").strip()]
    analysis = analyze_job(client_message, category)
    verified = verified_techs(profile, projects)
    verified_label = (
        " and ".join(TECH_DISPLAY.get(t, t) for t in verified) or "none listed"
    )
    asks_label = (
        " and ".join(TECH_DISPLAY.get(t, t) for t in sorted(analysis["tech_asks"]))
        or "none named"
    )
    needs_label = "; ".join(n["label"] for n in analysis["needs"]) or "general build"

    def _fact(p: Project) -> str:
        _s, reasons = score_project(p, analysis, category)
        stack = ", ".join(
            str(s) for s in (p.tech_stack if isinstance(p.tech_stack, list) else [])
        )
        return (
            f"- title: {_clean_text(p.title, 80)}\n"
            f"  about: {_clean_text(public_proof_text(p), 200) or 'no notes'}\n"
            f"  category: {_clean_text(p.category, 40) or 'general'}"
            f"{f'  tech: {_clean_text(stack, 80)}' if stack else ''}\n"
            f"  why relevant: {'; '.join(reasons) or 'owned project'}\n"
            f"  live link: {(p.live_url or '').strip() or 'none'}"
        )

    facts = "\n".join(_fact(p) for p in projects) or "(no projects)"
    allowed_links = (
        " ".join(
            [*live_urls, portfolio, *collaborator_urls]
            if portfolio
            else [*live_urls, *collaborator_urls]
        )
        or "none"
    )
    system = (
        "You write Upwork proposals in the voice of one freelance developer. "
        "Open by mirroring the client problem in your own words so they feel "
        "understood. Then prove fit with the single most relevant real "
        "project and say why it matches this job. Then give one concrete "
        "first step for their job. Follow this exact shape: greeting line "
        "hey there (or hey {clientName} when the client gave a name); intro "
        "I am {Name} a {role} dev plus ONLY verified skills when listed; "
        "one understanding sentence about their actual problem; recently "
        "two short sentences about the given real project with its LIVE "
        "demo link pasted exactly; one sentence tying that project to "
        "their need; one concrete approach sentence for their job; two "
        "short closing sentences with one naming what the client will see "
        "or test at the first checkpoint for this job and one honest "
        "sentence about how the shown project supports that checkpoint; "
        + (
            f"one line exactly: please review my portfolio: {portfolio}; "
            if portfolio
            else ""
        )
        + "".join(
            f"one line exactly: please review {cname}'s portfolio: {curl}; "
            for cname, curl in collaborators
        )
        + "last lines exactly: Please let me know when we can proceed "
        "further. / Best regards / {Name}. Style: casual human slightly "
        "imperfect, mostly lowercase except the pronoun I and tech names, "
        "NO commas anywhere. Never use: thank you for reaching out, I would "
        "love to help, looking forward to connecting, seamless, intricate "
        "codebases. Accuracy is a hard rule: claim ONLY the verified skills "
        "listed in the brief. Technologies the client asks for are their "
        "wishlist — never present them as your experience unless they are "
        "also verified. Evidence tier rule: the brief marks the cited "
        "project COVER RELATED or NONE. COVER means you may say it covers "
        "the named need. RELATED means say only that it is your closest "
        "related work and never claim it covers aligns with matches or is "
        "directly related to their need. NONE means do not tie the project "
        "to their need at all and present it only as recent work. "
        "Share LIVE demo links only — never GitHub or "
        "repository links, never invent links results or experience. Use "
        f"ONLY these links exactly: {allowed_links}. Output only the "
        "proposal text."
    )
    tier = claim_tier(cited_proof(projects), analysis, category)
    user = (
        f"My name: {name or profile.name}\n"
        f"Detected category: {category or 'general'}\n"
        f"Client needs: {needs_label}\n"
        f"Evidence tier for the cited project: {tier}\n"
        f"Verified skills you may claim: {verified_label}\n"
        f"Client asks for (do not claim unless verified): {asks_label}\n"
        + (
            f"Client name: {analysis['client_name']}\n"
            if analysis["client_name"]
            else ""
        )
        + f"Real projects you may reference:\n{facts}\n\n"
        f"Client message:\n{client_message}\n\n"
        "Write the reply now in the exact shape. Start from their problem "
        "not from a generic introduction."
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                settings.openai_chat_url,
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "model": settings.LLM_MODEL,
                    "temperature": 0.9,
                    "max_tokens": 600,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                },
            )
            resp.raise_for_status()
            data = resp.json()
        text = str(data["choices"][0]["message"]["content"]).strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise RuntimeError(f"LLM request failed: {exc}")
    eligible = eligible_claim_labels(cited_proof(projects), analysis)
    unsupported = [
        n["label"] for n in analysis["needs"] if n["label"] not in eligible
    ]
    if validate_reply(
        text,
        portfolio=portfolio,
        live_urls=live_urls,
        collaborator_portfolios=collaborator_urls,
        verified_techs_list=verified,
        unsupported_claim_labels=unsupported,
        claim_tier=tier,
        need_tiers_map=need_tiers(cited_proof(projects), analysis, category),
    ):
        return text
    # Corporate or off-shape LLM output never ships: use the template.
    return template_reply(
        profile=profile, projects=projects, client_message=client_message, category=category
    )


async def call_real_bot(
    *,
    profile_name: str,
    client_message: str,
    category: str | None,
    projects: list[Project],
) -> str:
    """Real Bot mode: forward the same input to BOT_URL/generate."""
    base = (settings.BOT_URL or "").strip().rstrip("/")
    if not base:
        raise RuntimeError("Real Bot mode needs BOT_URL in env")
    payload = {
        "profile": profile_name,
        "client_message": client_message,
        "category": category,
        "projects": [
            {
                "id": p.id,
                "title": p.title,
                "category": p.category,
                "github_url": p.github_url,
                "live_url": p.live_url,
                "description": p.description,
                "result": p.result,
                "tech_stack": p.tech_stack,
                # Ownership travels with each project so the Bot can enforce
                # profile isolation even on its Hub-unreachable path.
                "profiles": [pr.name for pr in (p.profiles or [])],
            }
            for p in projects
        ],
    }
    headers: dict[str, str] = {}
    if settings.BOT_API_KEY:
        headers["X-API-Key"] = settings.BOT_API_KEY
    try:
        async with httpx.AsyncClient(timeout=90.0) as client:
            resp = await client.post(f"{base}/generate", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise BotUnreachableError(f"Bot unreachable: {exc}") from exc
    if resp.status_code == 401:
        raise BotAuthError(
            "Bot API key mismatch: bot returned 401. "
            "Check BOT_API_KEY matches on the Hub and the bot."
        )
    if resp.status_code == 503:
        raise BotNotConfiguredError(
            "Bot API key not configured: bot returned 503. "
            "Set BOT_API_KEY on the bot."
        )
    if resp.status_code >= 400:
        raise BotUnreachableError(
            f"Bot request failed with HTTP {resp.status_code}. Try again later."
        )
    try:
        data = resp.json()
    except ValueError:
        return resp.text.strip()
    if isinstance(data, dict) and data.get("reply"):
        return str(data["reply"]).strip()
    if isinstance(data, dict) and data.get("proposal"):
        return str(data["proposal"]).strip()
    return (resp.text or "").strip()
