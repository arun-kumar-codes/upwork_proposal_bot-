"""Smoke test: is each proposal directed (tailored) or generic?

Runs the REAL Hub path for every valid profile x every job type:
detect_category -> analyze_job -> select_projects -> template_reply
(the deterministic proposal that ships in Simulated fallback and as the
Bot stub; LLM output is gated to this same shape by validate_reply).

Directed verdict per cell:
  DIRECTED  understand AND approach lines match the job's primary need,
            AND the top proof project hits that need or the category.
  PARTIAL   only one side is tailored (or no projects exist to prove it).
  GENERIC   neither: generic role phrase + unrelated proof project.

Run:  ../.venv/bin/python scripts/smoke_directed.py
Writes outputs/smoke-directed-report.md (full proposals + matrix).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from sqlalchemy.orm import selectinload

from app.db import SessionLocal
from app.models import Profile, Project
from app.services.playground import (
    analyze_job,
    detect_category,
    resolve_person,
    score_project,
    select_projects,
    template_reply,
)
from app.services.profile_names import is_valid_profile_name

JOBS = {
    "voice": (
        "Voice agent",
        "Hi I am Sara we run a real estate agency and we need a voice agent "
        "that calls leads on the phone and books meetings on our calendar so "
        "our team stops chasing calls all day",
    ),
    "automation": (
        "Automation (WhatsApp / email)",
        "Hi I am Mike our team wastes hours on manual steps copying orders "
        "between spreadsheets and sending WhatsApp follow ups and email "
        "sequences by hand and we need this automation done properly",
    ),
    "n8n": (
        "n8n automation",
        "Hi I am Jonas we need an n8n automation workflow that watches our "
        "CRM for new leads and sends personalised follow up emails "
        "automatically without anyone doing manual work",
    ),
    "fullstack": (
        "Full stack web app",
        "Hi I am Priya we need a full stack developer to build a web app "
        "where customers sign up and log in and manage their own accounts "
        "and subscriptions end to end",
    ),
    "docs": (
        "AI document Q&A",
        "Hi I am Sara we run a construction firm and we need an AI assistant "
        "that answers questions from our own documents and manuals so staff "
        "stop searching PDFs all day and it should cite the source document",
    ),
    "ai_agent": (
        "AI agent / chatbot",
        "Hi I am Tom we need an AI agent chatbot on our website that "
        "answers customer questions and books appointments for our clinic "
        "without our front desk getting involved",
    ),
    "store": (
        "Shopify store",
        "Hi I am Lena we need a Shopify store where customers can browse "
        "our products and pay online with a smooth checkout and cart",
    ),
    "dashboard": (
        "Dashboard / trading",
        "Hi I am Raj we need a dashboard with live trading charts and "
        "reporting so our team can watch numbers and act fast",
    ),
}


def main() -> None:
    db = SessionLocal()
    try:
        profiles = (
            db.query(Profile)
            .options(selectinload(Profile.projects))
            .order_by(Profile.name)
            .all()
        )
        profiles = [p for p in profiles if is_valid_profile_name(p.name)]
        categories = [
            r[0]
            for r in db.query(Project.category)
            .filter(Project.status == "active")
            .distinct()
            .all()
        ]

        rows = []  # (profile, jobkey, verdict, details, reply)
        for profile in profiles:
            active = sorted(
                (p for p in profile.projects if p.status == "active"),
                key=lambda p: (p.updated_at, p.id),
                reverse=True,
            )
            for jobkey, (_label, message) in JOBS.items():
                category = detect_category(message, categories)
                analysis = analyze_job(message, category)
                picked = select_projects(
                    active, category, 3, client_message=message
                )
                reply = template_reply(
                    profile=profile,
                    projects=[p for p, _ in picked],
                    client_message=message,
                    category=category,
                )
                primary = analysis["primary"]
                tailored = bool(
                    primary
                    and primary["understand"] in reply
                    and primary["approach"] in reply
                )
                relevant = False
                proof_title = "(no projects)"
                proof_reasons = ""
                if picked:
                    # The proposal cites the first picked project WITH a live
                    # link (template rule), which may differ from rank #1.
                    cited = next(
                        (p for p, _ in picked if (p.live_url or "").strip()),
                        picked[0][0],
                    )
                    top = cited
                    proof_title = top.title
                    _s, reasons = score_project(top, analysis, category)
                    proof_reasons = "; ".join(reasons)
                    relevant = any(
                        r.startswith("covers your")
                        or r.startswith("category match")
                        or r.startswith("related category")
                        for r in reasons
                    )
                    owned = top in active
                else:
                    owned = True
                if tailored and relevant:
                    verdict = "DIRECTED"
                elif tailored or relevant:
                    verdict = "PARTIAL"
                else:
                    verdict = "GENERIC"
                # contract checks
                name, portfolio = resolve_person(profile.name)
                contract_ok = (
                    "," not in reply
                    and "github.com" not in reply.lower()
                    and "Please let me know when we can proceed further." in reply
                    and (not name or reply.rstrip().endswith(name))
                    and (not portfolio or f"please review my portfolio: {portfolio}" in reply)
                )
                rows.append(
                    {
                        "profile": profile.name,
                        "job": jobkey,
                        "verdict": verdict,
                        "category": category,
                        "need": primary["key"] if primary else "none",
                        "proof": proof_title,
                        "reasons": proof_reasons,
                        "tailored": tailored,
                        "relevant": relevant,
                        "owned": owned,
                        "contract": contract_ok,
                        "reply": reply,
                    }
                )
    finally:
        db.close()

    # ---- summary matrix -------------------------------------------------
    jobkeys = list(JOBS)
    counts = {"DIRECTED": 0, "PARTIAL": 0, "GENERIC": 0}
    for r in rows:
        counts[r["verdict"]] += 1
    print(f"cells={len(rows)} " + " ".join(f"{k}={v}" for k, v in counts.items()))
    header = "| Profile | " + " | ".join(JOBS[k][0] for k in jobkeys) + " |"
    print(header)
    print("|" + "---|" * (len(jobkeys) + 1))
    for profile in sorted({r["profile"] for r in rows}):
        cells = []
        for k in jobkeys:
            r = next(x for x in rows if x["profile"] == profile and x["job"] == k)
            mark = {"DIRECTED": "✅", "PARTIAL": "⚠️", "GENERIC": "❌"}[r["verdict"]]
            cells.append(f"{mark} {r['proof'][:28]}")
        print(f"| {profile} | " + " | ".join(cells) + " |")
    bad = [r for r in rows if not r["contract"] or not r["owned"]]
    print(f"contract/isolation violations: {len(bad)}")
    for r in bad:
        print("  VIOLATION", r["profile"], r["job"], r["contract"], r["owned"])

    # ---- full report ------------------------------------------------------
    out = Path(__file__).resolve().parents[3] / "outputs" / "smoke-directed-report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Smoke test — directed vs generic proposals",
        "",
        "Path tested: Hub `detect_category -> analyze_job -> select_projects -> template_reply` "
        "on the live DB (the shape the LLM is gated to). Profiles: all valid freelancers. "
        "❌ Not named excluded (placeholder, correctly refused by the API).",
        "",
        f"**Totals: {counts['DIRECTED']} directed · {counts['PARTIAL']} partial · {counts['GENERIC']} generic "
        f"of {len(rows)} cells. Contract/isolation violations: {len(bad)}.**",
        "",
        header,
        "|" + "---|" * (len(jobkeys) + 1),
    ]
    for profile in sorted({r["profile"] for r in rows}):
        cells = []
        for k in jobkeys:
            r = next(x for x in rows if x["profile"] == profile and x["job"] == k)
            mark = {"DIRECTED": "✅", "PARTIAL": "⚠️", "GENERIC": "❌"}[r["verdict"]]
            cells.append(f"{mark} {r['proof']}")
        lines.append(f"| {profile} | " + " | ".join(cells) + " |")
    lines += ["", "## Full proposals", ""]
    for r in rows:
        lines += [
            f"### {r['profile']} × {JOBS[r['job']][0]} — {r['verdict']}",
            "",
            f"- detected category: `{r['category']}` · primary need: `{r['need']}` · "
            f"tailored text: {r['tailored']} · relevant proof: {r['relevant']} · "
            f"proof: **{r['proof']}** ({r['reasons'] or 'no relevance signal'})",
            "",
            "```",
            r["reply"],
            "```",
            "",
        ]
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
