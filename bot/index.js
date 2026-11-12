/**
 * Proposal Bot — Hub-backed proposal generator for Project Hub.
 *
 * POST /generate (requires X-API-Key == BOT_API_KEY)
 *   503 if BOT_API_KEY is not configured, 401 on wrong/missing key.
 *   Returns { success, proposal, reply, category, source, projects, mode }
 *   where `reply` mirrors `proposal` (Hub Playground reads `reply`).
 *
 * Flow: fetch Hub categories + active projects (30s cache), keep ONLY the
 * selected freelancer's projects (unknown profiles -> 404 when the Hub can
 * be checked), rank/select up to 3 of those, then generate in the original
 * Upwork Proposal Bot shape (hey greeting, I am {Name} intro, recently
 * project proof with exact live_url, portfolio line, fixed closing).
 * With an LLM key set the proposal comes from the LLM and must pass
 * validateProposal; without a key (or on any validation failure) the
 * deterministic template over the SAME selected projects is used
 * (documented stub mode — same structure, no invented claims).
 * Proposals share LIVE demo links only: github_url is dropped at
 * selection and stripped from generated text. Hub down / no matches
 * -> source "fallback" (still live-only, no invented links).
 */
const crypto = require("crypto");
const express = require("express");

const app = express();
app.use(express.json({ limit: "256kb" }));

app.get("/health", (_req, res) => res.json({ ok: true, service: "proposal-bot" }));
app.get("/", (_req, res) => res.json({ ok: true, service: "proposal-bot", docs: "POST /generate" }));

function keysMatch(provided, expected) {
  if (!provided || !expected) return false;
  const a = Buffer.from(String(provided));
  const b = Buffer.from(String(expected));
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}

// --- Technology / category detection --------------------------------------
// Canonical tech -> alias phrases (matched longest-first on lowercased text).
const TECH_ALIASES = {
  ai: ["artificial intelligence", "machine learning", "data science", "openai", "llm", " ml ", "ai"],
  frontend: ["front-end", "front end", "frontend", "user interface", " ui ", "angular"],
  backend: ["back-end", "back end", "backend", "rest api", "node.js", "nodejs", "express", "django", "flask", "fastapi"],
  fullstack: ["full-stack", "full stack", "fullstack", "mern", "mean stack"],
  react: ["next.js", "nextjs", "reactjs", "react"],
  vue: ["vuejs", "nuxt", "vue"],
  shopify: ["shopify", "e-commerce store", "ecommerce store"],
  devops: ["kubernetes", "devops", "docker", "aws", "ci/cd", "terraform"],
  python: ["python", "pandas", "django", "flask", "fastapi"],
  web: ["web app", "website", "web development", "e-commerce", "ecommerce", "online store", " web "],
};
// Hub category spellings that mean a canonical tech (Hub data is free-form).
const HUB_CATEGORY_CANONICAL = { ml: "ai", data: "ai", "web dev": "web", shopify: "shopify" };

function canonicalOf(raw) {
  const text = ` ${(raw || "").toString().toLowerCase().trim()} `;
  if (!text.trim()) return null;
  if (HUB_CATEGORY_CANONICAL[text.trim()]) return HUB_CATEGORY_CANONICAL[text.trim()];
  for (const [canon, aliases] of Object.entries(TECH_ALIASES)) {
    if (text.trim() === canon) return canon;
    for (const alias of aliases) {
      if (text.includes(alias)) return canon;
    }
  }
  return text.trim();
}

function detectCategory({ explicit, message, hubCategories = [] }) {
  const cats = (hubCategories || []).map((c) => (c || "").toString().toLowerCase().trim()).filter(Boolean);
  const WEB_FAMILY = new Set(["web", "frontend", "react", "vue", "fullstack"]);
  const pickHubSpelling = (canon) => {
    if (!canon) return null;
    for (const c of cats) {
      if (c === canon || canonicalOf(c) === canon) return c;
    }
    // Hub categories are coarse: frontend-family tech lands on "web".
    if (cats.includes("web") && WEB_FAMILY.has(canon)) return "web";
    return null;
  };
  if (explicit) {
    const canon = canonicalOf(explicit);
    return pickHubSpelling(canon) || canon || explicit.toString().toLowerCase().trim();
  }
  const text = ` ${(message || "").toLowerCase()} `;
  // Prefer a canonical that maps onto a real Hub category.
  const found = [];
  for (const [canon, aliases] of Object.entries(TECH_ALIASES)) {
    if (aliases.some((a) => text.includes(a))) found.push(canon);
  }
  for (const canon of found) {
    const hub = pickHubSpelling(canon);
    if (hub) return hub;
  }
  for (const c of cats) {
    if (c && text.includes(` ${c} `)) return c;
  }
  if (found.length) return found[0];
  if (cats.includes("web")) return "web";
  return cats[0] || null;
}

// --- Portfolio links (Profile Manager, same as the original bot) ------------
// Proposals must end with "please review my portfolio: <link>" for known
// people. Aliases resolve spelling variants; combined Excel tokens such as
// "Gopal, Vikas" belong to the first person only (people are never merged).
const PORTFOLIO_LINKS = {
  aayush: "http://116.202.210.102:3700/portfolio/6943d95d20eafc5a71c0f96b",
  atul: "http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff",
  arun: "http://116.202.210.102:3700/portfolio/69492dc930db86ebbad04a03",
  faisal: "http://116.202.210.102:3700/portfolio/695b83cff3cd570bc25c4db8",
  mahima: "http://116.202.210.102:3700/portfolio/6949303130db86ebbad04a13",
  kishan: "http://116.202.210.102:3700/portfolio/69492ffc30db86ebbad04a0f",
  gopal: "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b",
  // Hub spells this freelancer "Gopalan"; the portfolio service identifies
  // the "gopal" ID above as Gopalan Prakash, so this is his verified link.
  gopalan: "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b",
  deepanshu: "http://116.202.210.102:3700/portfolio/69492f8e30db86ebbad04a07",
  rahul: "http://116.202.210.102:3700/portfolio/69451bda999775a273ac7039",
  yuvraj: "http://116.202.210.102:3700/portfolio/6944e7b2999775a273ac6ab6",
  "vikas kumar": "http://116.202.210.102:3700/portfolio/6949313330db86ebbad04a35",
  "vikas singh": "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17",
};
const PROFILE_ALIASES = {
  faizal: "faisal",
  "faizal/lyt": "faisal",
  "faisal/lyt": "faisal",
  "faizal lyt": "faisal",
  "faisal lyt": "faisal",
  lyt: "faisal",
  // Note: bare "Vikas" is deliberately NOT aliased to Vikas Singh. Singh is
  // credited only inside the verified combined profile (see
  // COMBINED_COLLABORATORS below), never assigned to unrelated profiles.
};

// Placeholder buckets are not freelancers (same list as Hub profile_names.py):
// they must never be signed for or used as a display name ("I am Not ...").
const INVALID_PROFILE_NAMES = new Set([
  "", "-", "not", "not named", "unknown", "n/a", "na", "none", "null",
  "unnamed", "no name", "placeholder", "tbd", "anonymous", "not provided",
  "not specified", "missing",
]);

function isValidProfileName(raw) {
  const norm = (raw || "").toString().toLowerCase().trim().replace(/\s+/g, " ");
  return !INVALID_PROFILE_NAMES.has(norm);
}

function resolveProfile(raw) {
  const original = (raw || "").toString().trim();
  if (!isValidProfileName(original)) return { name: "", portfolio: null };
  const norm = original
    .toLowerCase()
    .replace(/\s*[/,]\s*/g, "/")
    .replace(/\s+/g, " ")
    .trim();
  const candidates = [norm, norm.split("/")[0].trim(), norm.split(" ")[0]].filter(Boolean);
  for (const cand of candidates) {
    const canon = PROFILE_ALIASES[cand] || cand;
    if (PORTFOLIO_LINKS[canon]) {
      // Verified freelancers sign with their full canonical name.
      const fullName = canon
        .split(" ")
        .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
        .join(" ");
      return { name: fullName, portfolio: PORTFOLIO_LINKS[canon] };
    }
  }
  const firstWord = original.split(/[/,\s]+/).filter(Boolean)[0] || "";
  return {
    name: firstWord ? firstWord.charAt(0).toUpperCase() + firstWord.slice(1) : "",
    portfolio: null, // unknown person: never invent a portfolio link
  };
}

// Explicit verified combined profiles -> credited collaborators. This is
// an allowlist, NOT people-list parsing: a name that merely contains "+",
// "/" or "," (e.g. "Kishan / Vikas", "Newdev + Vikas") earns no credit.
// Keys are separator-normalized ("gopalan+vikas"); values are verified
// against the Profile Manager and confirmed by the owner (Tellaigent:
// Gopalan Prakash + Vikas Singh). Mirror of Hub _COMBINED_COLLABORATORS.
const COMBINED_COLLABORATORS = {
  "gopalan+vikas": [{ name: "Vikas Singh", portfolio: PORTFOLIO_LINKS["vikas singh"] }],
  "gopalan+vikas singh": [{ name: "Vikas Singh", portfolio: PORTFOLIO_LINKS["vikas singh"] }],
  "gopal+vikas": [{ name: "Vikas Singh", portfolio: PORTFOLIO_LINKS["vikas singh"] }],
  "gopal+vikas singh": [{ name: "Vikas Singh", portfolio: PORTFOLIO_LINKS["vikas singh"] }],
};

function resolveCollaborators(raw) {
  const original = (raw || "").toString().trim();
  if (!isValidProfileName(original)) return [];
  const norm = original.toLowerCase().replace(/\s+/g, " ");
  const parts = norm
    .split(/[+,/]/)
    .map((p) => p.trim())
    .filter(Boolean);
  return (COMBINED_COLLABORATORS[parts.join("+")] || []).map((c) => ({ ...c }));
}

// --- Selection / ranking ----------------------------------------------------
function profileNamesOf(project) {
  const list = (project && project.profiles) || [];
  return list
    .map((p) => (typeof p === "string" ? p : p && p.name ? String(p.name) : ""))
    .map((s) => s.toLowerCase().trim())
    .filter(Boolean);
}

function normalizeName(value) {
  return (value || "").toString().toLowerCase().trim().replace(/\s+/g, " ");
}

// Profile isolation: ranking may only ever see the selected freelancer's own
// projects. Ownership comes from each project's Hub profile links; anything
// not linked to the selected profile is excluded before scoring, so a
// foreign project can never win on category/live_url/tech points.
function filterProjectsForProfile(projects, profile) {
  const prof = normalizeName(profile);
  if (!prof) return [];
  return (projects || []).filter((p) =>
    profileNamesOf(p).map(normalizeName).includes(prof),
  );
}

// Whether `profile` is a real Hub freelancer. Uses the Hub profile list when
// it could be fetched; falls back to names seen on Hub projects. Returns null
// when there is no Hub data to verify against (Hub down).
function isKnownProfile(hub, profile) {
  const prof = normalizeName(profile);
  if (!prof || !hub) return null;
  if (Array.isArray(hub.profiles)) {
    return hub.profiles.some(
      (p) => normalizeName(typeof p === "string" ? p : p && p.name) === prof,
    );
  }
  return hub.projects.some((p) =>
    profileNamesOf(p).map(normalizeName).includes(prof),
  );
}

function techTokens(text) {
  const canon = new Set();
  const lower = ` ${(text || "").toLowerCase()} `;
  for (const [c, aliases] of Object.entries(TECH_ALIASES)) {
    if (aliases.some((a) => lower.includes(a))) canon.add(c);
  }
  return canon;
}

// --- Job-requirement analysis (mirror of Hub playground.py) ------------------
// Deterministic reading of the client's post. Technologies the client names
// are "asks" — only verified freelancer data may turn an ask into a claim.
const STOPWORDS = new Set([
  "a", "an", "the", "and", "or", "for", "to", "of", "in", "on", "with",
  "we", "you", "our", "your", "need", "needs", "want", "looking", "build",
  "building", "built", "create", "develop", "developer", "hi", "hello",
  "i", "am", "is", "are", "that", "this", "it", "so", "can", "where",
  "style", "like", "online", "please", "us", "my", "me",
]);
const NEED_SIGNALS = [
  { key: "voice", aliases: ["voice agent", "voice ai", "voice assistant", "phone call", "outbound calls", "inbound calls", "calls leads"], label: "voice calls and booking", understand: "you need a voice agent that talks to leads and books the meeting without your team chasing calls", approach: "I would start with your call flow and booking rules and test real calls early so the tone and handoffs feel right", proof: ["voice", "calls", "call", "calling", "calendar", "booking", "leads", "meetings", "whatsapp", "agent"] },
  { key: "docs", aliases: ["documents", "manuals", "pdf", "knowledge base", "searching pdf", "our own docs"], label: "answers from your documents", understand: "you need quick answers from your own documents so your team stops hunting through files", approach: "I would start with your real documents and the questions your team asks most and build the search around those first", proof: ["documents", "document", "rag", "uploads", "questions", "answers", "manuals", "pdf"] },
  { key: "crm", aliases: ["crm", "hubspot", "appointments", "front desk", "sales pipeline", "manage patient"], label: "customer and booking flow", understand: "you need one simple flow that keeps customers and bookings together instead of scattered follow ups", approach: "I would start with your booking and follow up flow and keep it simple for the team that uses it daily", proof: ["crm", "hospital", "appointments", "booking", "leads", "customers", "patient"] },
  { key: "store", aliases: ["shopify", "store", "ecommerce", "e-commerce", "checkout", "cart", "pay online", "products"], label: "store and checkout", understand: "you need a store where customers can browse and pay without friction", approach: "I would start with your product pages and checkout and get a live preview in front of you early", proof: ["store", "shop", "products", "checkout", "shoppers", "promotions", "offers", "customers"] },
  { key: "dashboard", aliases: ["dashboard", "trading", "charts", "reporting", "admin panel", "analytics"], label: "dashboard and live data", understand: "you need a clear dashboard that shows live numbers and lets you act fast", approach: "I would start with the main screen your team opens daily and wire the live data into that first", proof: ["dashboard", "trading", "charts", "orders", "reports", "data", "platform", "live"] },
  { key: "scraping", aliases: ["scrap", "crawl", "extract data", "collect leads", "gather data"], label: "data collection", understand: "you need clean data collected on schedule without manual copying", approach: "I would start with one source end to end and lock the output format before scaling to the rest", proof: ["scrapes", "scraping", "extracts", "data", "websites", "pipeline"] },
  { key: "automation", aliases: ["automat", "whatsapp", "email sequence", "manual work", "manual steps", "manual process"], label: "automation of manual work", understand: "you need the slow manual steps taken off your team so follow ups happen on time every time", approach: "I would map your current manual flow first and automate the slowest step first so you see value fast", proof: ["automation", "automate", "whatsapp", "email", "scheduling", "invoicing", "workflow"] },
  { key: "ai_agent", aliases: ["ai agent", "chatbot", "ai assistant", "ai tool", "artificial intelligence", "agent that"], label: "AI agent work", understand: "you need an AI agent that does real work for customers instead of only answering chats", approach: "I would start with the three jobs your agent must finish and build those end to end before adding extras", proof: ["agent", "agents", "ai", "chatbot", "voice", "assistant", "automation"] },
  { key: "website", aliases: ["website", "web app", "landing page", "web developer", "site for"], label: "website build", understand: "you need a clean website that explains your offer and turns visitors into enquiries", approach: "I would start with your main page and enquiry flow and share a live preview in small steps", proof: ["site", "website", "web", "app", "pages", "login"] },
];

function extractClientName(message) {
  const m = (message || "").match(
    /(?:hi|hello|hey)[^.!\n]{0,30}?i(?:\s+am|'m)\s+([A-Za-z]{2,20})\b|my name is\s+([A-Za-z]{2,20})\b|i(?:\s+am|'m)\s+([A-Za-z]{2,20})\b/i,
  );
  if (!m) return "";
  const name = m[1] || m[2] || m[3] || "";
  if (!name || STOPWORDS.has(name.toLowerCase()) || !isValidProfileName(name)) return "";
  return name.charAt(0).toUpperCase() + name.slice(1).toLowerCase();
}

function analyzeJob(message, category) {
  const text = (message || "").toLowerCase();
  const needs = NEED_SIGNALS.filter((n) => n.aliases.some((a) => text.includes(a)));
  const words = new Set(
    (text.match(/[a-z0-9+#]+/g) || []).filter((w) => w.length > 2 && !STOPWORDS.has(w)),
  );
  return {
    needs,
    primary: needs[0] || null,
    techAsks: techTokens(message),
    words,
    clientName: extractClientName(message || ""),
    category: (category || "").toString().trim().toLowerCase() || null,
  };
}

function verifiedTechs(profileSkills, projects) {
  const found = [];
  const add = (canon) => {
    if (canon && TECH_DISPLAY[canon] && !found.includes(canon)) found.push(canon);
  };
  for (const skill of profileSkills || []) {
    for (const canon of techTokens(String(skill))) add(canon);
    add(canonicalOf(skill));
  }
  for (const p of projects || []) {
    for (const item of p.tech_stack || []) {
      for (const canon of techTokens(String(item))) add(canon);
      add(canonicalOf(item));
    }
  }
  return found;
}

function claimsUnverifiedTech(text, verified) {
  const lower = (text || "").toLowerCase();
  const patterns = [
    /i work with ([^\n.]*)/g,
    /experience (?:in|with) ([^\n.]*)/g,
    /speciali[sz]e in ([^\n.]*)/g,
    /skilled in ([^\n.]*)/g,
  ];
  for (const pattern of patterns) {
    for (const m of lower.matchAll(pattern)) {
      const segment = ` ${m[1]} `;
      const bad = Object.entries(TECH_ALIASES).some(
        ([canon, aliases]) => !verified.includes(canon) && aliases.some((a) => segment.includes(a)),
      );
      if (bad) return true;
    }
  }
  return false;
}

function scoreProject(p, analysis, category, profile) {
  let score = 0;
  const reasons = [];
  // Defence in depth: the caller already restricts the pool to the selected
  // freelancer, but an owned project still outranks any foreign one.
  if (profile && profileNamesOf(p).map(normalizeName).includes(normalizeName(profile))) {
    score += 3;
  }
  const projCat = (p.category || "").toString().toLowerCase().trim();
  const cat = (category || "").toString().toLowerCase().trim();
  if (cat) {
    if (projCat === cat) {
      score += 4;
      reasons.push(`category match: '${cat}'`);
    } else if (canonicalOf(projCat) && canonicalOf(projCat) === canonicalOf(cat)) {
      score += 3;
      reasons.push(`related category: '${projCat}'`);
    }
  }
  const content = `${p.title || ""} ${publicProofText(p)} ${p.description || ""}`.toLowerCase();
  const contentWords = new Set(content.match(/[a-z0-9+#]+/g) || []);
  for (const need of analysis.needs.slice(0, 3)) {
    if (need.proof.some((w) => contentWords.has(w))) {
      score += 2;
      reasons.push(`covers your ${need.label} need`);
    }
  }
  let overlap = 0;
  for (const w of analysis.words) if (contentWords.has(w)) overlap += 1;
  score += Math.min(overlap, 4);
  const stackCanons = new Set();
  for (const item of p.tech_stack || []) {
    for (const c of techTokens(String(item))) stackCanons.add(c);
    const co = canonicalOf(item);
    if (co && TECH_DISPLAY[co]) stackCanons.add(co);
  }
  for (const ask of analysis.techAsks) {
    if (stackCanons.has(ask)) {
      score += 2;
      reasons.push(`uses tech you named: ${ask}`);
    }
  }
  if (p.live_url && String(p.live_url).trim()) score += 1;
  return { score, reasons };
}

function selectProjects(projects, { profile, category, message, limit = 3 } = {}) {
  // The pool is already restricted to the selected freelancer by the caller
  // (profile isolation); ranking here is purely about job relevance, so the
  // proof project is the closest match — not merely the newest or live one.
  const analysis = analyzeJob(message, category);
  const scored = (projects || []).map((p, idx) => {
    const { score, reasons } = scoreProject(p, analysis, category, profile);
    return { p, score, idx, reasons };
  });
  scored.sort((a, b) => b.score - a.score || a.idx - b.idx);
  return scored.slice(0, limit).map(({ p, reasons }) => ({
    title: (p.title ? String(p.title) : "Project").trim() || "Project",
    category: p.category ? String(p.category) : "",
    live_url: p.live_url ? String(p.live_url).trim() : "",
    description: p.description ? String(p.description).trim() : "",
    result: p.result ? String(p.result).trim() : "",
    tech_stack: Array.isArray(p.tech_stack) ? p.tech_stack.map((s) => String(s)) : [],
    reason: reasons.join("; "),
  }));
}

function sanitizeProposal(text) {
  return (text || "")
    .replace(/https?:\/\/github\.com\/\S+/gi, "")
    .replace(/github\.com\/\S+/gi, "")
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

// --- Hub client (brief cache; failures -> fallback) -------------------------
const HUB_CACHE_MS = 30_000;
let hubCache = { key: "", at: 0, data: null };

function resetHubCache() {
  hubCache = { key: "", at: 0, data: null };
}

async function fetchHub() {
  const base = (process.env.HUB_URL || "").trim().replace(/\/$/, "");
  if (!base) return null;
  const key = `${base}|${process.env.HUB_API_KEY || ""}`;
  if (hubCache.data && hubCache.key === key && Date.now() - hubCache.at < HUB_CACHE_MS) {
    return hubCache.data;
  }
  const headers = {};
  if (process.env.HUB_API_KEY) headers["X-API-Key"] = process.env.HUB_API_KEY;
  const getJson = async (path) => {
    const resp = await fetch(`${base}${path}`, {
      headers,
      signal: AbortSignal.timeout(5000),
    });
    if (!resp.ok) throw new Error(`Hub HTTP ${resp.status}`);
    return resp.json();
  };
  const [categories, projects, profiles] = await Promise.all([
    getJson("/api/categories").catch(() => []),
    getJson("/api/projects?status=active&limit=100"),
    getJson("/api/meta/profiles").catch(() => null),
  ]);
  const data = {
    categories: Array.isArray(categories) ? categories : [],
    projects: Array.isArray(projects) ? projects : [],
    profiles: Array.isArray(profiles) ? profiles : null,
  };
  hubCache = { key, at: Date.now(), data };
  return data;
}

// --- Generation (original Upwork Proposal Bot contract) ----------------------
// Shape: "hey {clientName}" / "I am {Name} a {role} dev I work with {skills}"
// / "recently ..." with the exact live_url / fit / the exact portfolio line
// / fixed closing. Style: casual and mostly lowercase, NO commas anywhere,
// no corporate phrases. The validator enforces this on LLM output too; any
// failure falls back to the deterministic template over the same projects.
const BANNED_PHRASES = [
  "thank you for reaching out",
  "i would love to help",
  "i'd love",
  "id love",
  "looking forward to connecting",
  "navigate and enhance",
  "seamless",
  "intricate codebases",
  "for your project",
];

const TECH_DISPLAY = {
  ai: "AI",
  frontend: "frontend",
  backend: "backend APIs",
  fullstack: "full stack",
  react: "React",
  vue: "Vue",
  shopify: "Shopify",
  devops: "DevOps",
  python: "Python",
  web: "web",
};
const TECH_ORDER = ["react", "vue", "python", "ai", "shopify", "backend", "frontend", "fullstack", "devops", "web"];

function cleanText(value, max = 160) {
  let text = (value || "").toString();
  text = text.replace(/https?:\/\/\S+/gi, " "); // links come only from live_url fields
  text = text.replace(/(?:www\.)?github\.com\S*/gi, " ");
  text = text.replace(/,/g, " "); // proposals contain no commas
  text = text.replace(/\s+/g, " ").trim();
  if (text.length > max) text = text.slice(0, max).replace(/\s+\S*$/, "").trim();
  return text;
}

function asSentence(text) {
  const cleaned = cleanText(text);
  if (!cleaned) return "";
  return `${cleaned.replace(/\.+$/, "")}.`;
}

// --- Internal-notes guard -----------------------------------------------------
// Project `result` is imported from the Excel "Notes" column (and editable in
// the dashboard), so it mixes verified outcomes with operational remarks
// ("Git URL not given", "Team confirmed Active (Slack)", "Added from Google
// Sheet..."). Internal-tainted text must never reach a client proposal or an
// LLM prompt as project facts. A clean verified result wins; otherwise the
// public description; otherwise nothing (callers use a generic live line).
const INTERNAL_MARKERS = [
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
];

function isInternalNote(text) {
  const lower = (text || "").toString().toLowerCase();
  return INTERNAL_MARKERS.some((marker) => lower.includes(marker));
}

function publicProofText(project) {
  const result = (project && project.result ? String(project.result) : "").trim();
  const description = (project && project.description ? String(project.description) : "").trim();
  if (result && !isInternalNote(result)) return result;
  if (description && !isInternalNote(description)) return description;
  // Fail closed: a tainted field is dropped whole, never sentence-mined.
  return "";
}

function roleFor(category, canonSet) {
  const cat = (category || "").toLowerCase();
  if (cat.includes("full")) return "full stack";
  if (cat.includes("shopify")) return "Shopify";
  if (cat.includes("automation")) return "automation";
  if (canonSet.has("ai")) return "AI";
  if (canonSet.has("python")) return "Python";
  return "web";
}

const JOB_PHRASES = {
  "full stack": "I build complete web apps from the first screen to the live server",
  AI: "I build AI tools that plug into real working products",
  automation: "I automate slow manual work with clean scripts and pipelines",
  Shopify: "I build stores that load fast and stay easy to manage",
  Python: "I build backends and tools that stay simple to maintain",
  web: "I build clean websites and web apps for real clients",
};

const FIT_LINES = [
  "your requirement is clear to me and I already know how the full flow should work",
  "I can start right away and I will share progress in small steps",
  "you will talk directly with the person writing the code so nothing gets lost in between",
];

function templateProposal({ profile, clientName, category, clientMessage, projects = [], profileSkills = [], portfolioFallback = null }) {
  const resolved = resolveProfile(profile);
  const name = resolved.name;
  const portfolio = resolved.portfolio || portfolioFallback || null;
  const analysis = analyzeJob(clientMessage, category);
  const verified = verifiedTechs(profileSkills, projects);
  const ordered = [
    ...verified.filter((t) => analysis.techAsks.has(t)),
    ...verified.filter((t) => !analysis.techAsks.has(t)),
  ];
  const skillsPhrase = ordered.slice(0, 3).map((t) => TECH_DISPLAY[t]).join(" and ");
  // Role describes the freelancer's own work (top project first), never
  // the client's category: a store job must not relabel an AI builder.
  const roleSet = new Set(verified);
  const ownCategory = (projects[0] && projects[0].category) || category || "";
  const role = roleFor(ownCategory, roleSet);
  const primary = analysis.primary;
  const greetingName = clientName || analysis.clientName;

  const lines = [];
  lines.push(greetingName ? `hey ${greetingName}` : "hey there");
  lines.push("");
  let intro = name ? `I am ${name} a ${role} dev` : `I am a ${role} dev`;
  if (skillsPhrase) intro += ` I work with ${skillsPhrase}`;
  lines.push(intro);
  lines.push(primary ? primary.understand : JOB_PHRASES[role] || JOB_PHRASES.web);

  const proof = projects.find((p) => p.live_url) || projects[0];
  if (proof) {
    lines.push("");
    lines.push(`recently I worked on ${cleanText(proof.title, 80)}${proof.live_url ? ` ${proof.live_url}` : ""}`);
    const detail = asSentence(publicProofText(proof));
    lines.push(
      detail ||
        (proof.live_url
          ? "it is live right now and real users use it daily."
          : "the client still uses it in their daily work."),
    );
    const { reasons } = scoreProject(proof, analysis, category);
    const needReason = reasons.find((r) => r.startsWith("covers your"));
    if (needReason) lines.push(`I picked this one because it already ${needReason}.`);
  }

  lines.push("");
  if (primary) lines.push(primary.approach);
  lines.push(FIT_LINES[1]);
  lines.push(FIT_LINES[2]);

  if (portfolio) {
    lines.push("");
    lines.push(`please review my portfolio: ${portfolio}`);
  }
  for (const collab of resolveCollaborators(profile)) {
    lines.push(`please review ${collab.name}'s portfolio: ${collab.portfolio}`);
  }

  lines.push("");
  lines.push("Please let me know when we can proceed further.");
  lines.push("Best regards");
  if (name) lines.push(name);
  return lines.join("\n");
}

function validateProposal(text, { portfolio = null, liveUrls = [], collaboratorPortfolios = [], verifiedTechsList = null } = {}) {
  if (!text || typeof text !== "string") return false;
  const lower = text.toLowerCase();
  if (!lower.includes("hey")) return false;
  if (!lower.includes("recently")) return false;
  if (text.includes(",")) return false; // no commas anywhere in the body
  if (lower.includes("github.com")) return false;
  if (verifiedTechsList && claimsUnverifiedTech(text, verifiedTechsList)) return false;
  for (const phrase of BANNED_PHRASES) {
    if (lower.includes(phrase)) return false;
  }
  if (portfolio && !text.includes(`please review my portfolio: ${portfolio}`)) return false;
  for (const collabUrl of collaboratorPortfolios) {
    if (!text.includes(collabUrl)) return false; // verified collaborator must be credited
  }
  const allowed = new Set([portfolio, ...liveUrls, ...collaboratorPortfolios].filter(Boolean));
  const urls = text.match(/https?:\/\/[^\s)]+/g) || [];
  for (const url of urls) {
    if (!allowed.has(url.replace(/\.+$/, ""))) return false; // invented link
  }
  if (liveUrls.length && !text.includes(liveUrls[0])) return false;
  return true;
}

// OpenAI-compatible LLM config: OPENAI_* names win, LLM_* are accepted aliases.
function llmConfig() {
  const key = process.env.OPENAI_API_KEY || process.env.LLM_API_KEY || "";
  const base = (
    process.env.OPENAI_BASE_URL ||
    process.env.LLM_BASE_URL ||
    "https://api.openai.com/v1"
  ).replace(/\/+$/, "");
  const url = base.endsWith("/chat/completions") ? base : `${base}/chat/completions`;
  const model = process.env.OPENAI_MODEL || "gpt-4o";
  return { key, url, model };
}

async function generateProposal(ctx) {
  const { key, url, model } = llmConfig();
  const fallback = () => ({ text: templateProposal(ctx), mode: "stub" });
  if (!key) return fallback();
  // No eligible projects of this freelancer: never let the LLM invent
  // experience. The deterministic template omits the "recently" proof.
  if (!(ctx.projects || []).length) return fallback();
  const resolved = resolveProfile(ctx.profile);
  const name = resolved.name;
  const portfolio = resolved.portfolio || ctx.portfolioFallback || null;
  const collaborators = resolveCollaborators(ctx.profile);
  const collaboratorPortfolios = collaborators.map((c) => c.portfolio);
  const liveUrls = (ctx.projects || []).map((p) => p.live_url).filter(Boolean);
  const analysis = analyzeJob(ctx.clientMessage, ctx.category);
  const verified = verifiedTechs(ctx.profileSkills || [], ctx.projects || []);
  const verifiedLabel = verified.map((t) => TECH_DISPLAY[t]).join(" and ") || "none listed";
  const asksLabel = [...analysis.techAsks].map((t) => TECH_DISPLAY[t] || t).join(" and ") || "none named";
  const needsLabel = analysis.needs.map((n) => n.label).join("; ") || "general build";
  const projectFacts = (ctx.projects || [])
    .map((p) => {
      const { reasons } = scoreProject(p, analysis, ctx.category);
      const stack = (p.tech_stack || []).join(" ");
      return `- title: ${cleanText(p.title, 80)}\n  about: ${cleanText(publicProofText(p), 200) || "no notes"}\n  category: ${cleanText(p.category, 40) || "general"}${stack ? `\n  tech: ${cleanText(stack, 80)}` : ""}\n  why relevant: ${reasons.join("; ") || "owned project"}\n  live link: ${p.live_url || "none"}`;
    })
    .join("\n");
  const allowedLinks = [...liveUrls, portfolio, ...collaboratorPortfolios].filter(Boolean);
  try {
    const resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: `Bearer ${key}` },
      signal: AbortSignal.timeout(60000),
      body: JSON.stringify({
        model,
        temperature: 0.9,
        max_tokens: 600,
        messages: [
          {
            role: "system",
            content:
              "You write Upwork proposals in the voice of one freelance developer. Open by mirroring the client problem in your own words. Prove fit with the single most relevant real project and say why it matches this job. Give one concrete first step for their job. Follow this exact shape:\n" +
              "1) greeting line: hey {clientName} or hey there\n" +
              "2) intro: I am {Name} a {role} dev plus ONLY verified skills when listed\n" +
              "3) one understanding sentence about their actual problem\n" +
              "4) recently: two short sentences about the given real project and paste its live link exactly as given plus one sentence tying it to their need\n" +
              "5) one concrete approach sentence for their job plus two short casual fit sentences\n" +
              (portfolio ? `6) one line exactly: please review my portfolio: ${portfolio}\n` : "") +
              collaborators
                .map((c) => `one line exactly: please review ${c.name}'s portfolio: ${c.portfolio}\n`)
                .join("") +
              "last lines exactly:\nPlease let me know when we can proceed further.\nBest regards\n{Name}\n" +
              "Style rules: casual human slightly imperfect. mostly lowercase except the pronoun I and tech names. " +
              "NO commas anywhere. Never use these phrases: thank you for reaching out / I would love to help / " +
              "looking forward to connecting / seamless / intricate codebases. " +
              "Accuracy is a hard rule: claim ONLY the verified skills listed in the brief. Technologies the client asks for are their wishlist and never your experience unless also verified. " +
              `Use ONLY these links exactly as written and no others: ${allowedLinks.join(" ") || "none"}. ` +
              "Never paste github.com links. Never invent projects links results or experience. Output only the proposal text.",
          },
          {
            role: "user",
            content:
              `My name: ${name || ctx.profile || "freelancer"}\n` +
              `Detected category: ${ctx.category || "general"}\n` +
              `Client needs: ${needsLabel}\n` +
              `Verified skills you may claim: ${verifiedLabel}\n` +
              `Client asks for (do not claim unless verified): ${asksLabel}\n` +
              (ctx.clientName || analysis.clientName
                ? `Client name: ${ctx.clientName || analysis.clientName}\n`
                : "Client name: unknown\n") +
              `Real projects you may reference:\n${projectFacts || "(none)"}\n\n` +
              `Client job post:\n${(ctx.clientMessage || "").slice(0, 2000)}\n\nWrite the proposal now in the exact shape. Start from their problem not from a generic introduction.`,
          },
        ],
      }),
    });
    if (!resp.ok) throw new Error(`OpenAI HTTP ${resp.status}`);
    const data = await resp.json();
    const text = (data.choices?.[0]?.message?.content || "").trim();
    if (!text) throw new Error("OpenAI empty reply");
    // The validator is the contract: corporate or off-shape output never ships.
    if (!validateProposal(text, { portfolio, liveUrls, collaboratorPortfolios, verifiedTechsList: verified })) return fallback();
    return { text: sanitizeProposal(text), mode: "openai" };
  } catch {
    return fallback();
  }
}

app.post("/generate", async (req, res) => {
  const expected = process.env.BOT_API_KEY;
  if (!expected) {
    return res.status(503).json({ success: false, error: "BOT_API_KEY not configured" });
  }
  const provided = req.get("X-API-Key");
  if (!keysMatch(provided, expected)) {
    return res.status(401).json({ success: false, error: "Invalid API key" });
  }
  if (!req.is("application/json")) {
    return res.status(400).json({ success: false, error: "Expected application/json body" });
  }
  if (!req.body || typeof req.body !== "object" || Array.isArray(req.body)) {
    return res.status(400).json({ success: false, error: "Expected a JSON object body" });
  }
  const body = req.body;
  const profile = (body.profile || body.profileName || "").toString().trim();
  // Identity first: a missing or placeholder freelancer name ("Not named",
  // "Unknown", "N/A", blank) never reaches generation or gets signed for.
  if (!isValidProfileName(profile)) {
    return res.status(400).json({
      success: false,
      error: "Invalid freelancer profile: a real freelancer name is required",
    });
  }
  const clientName = (body.clientName || body.client_name || "").toString().trim();
  const clientMessage = (body.client_message || body.clientMessage || body.message || "").toString();
  const explicit = body.category || body.category_override || body.technology || null;

  let hub = null;
  try {
    hub = await fetchHub();
  } catch {
    hub = null; // Hub unreachable -> fallback path below.
  }
  const hubOk = Boolean(hub);
  // Unknown freelancer: never sign a proposal in an unverified name. The Hub
  // Playground already 404s unknown profiles; this guards direct Bot calls.
  if (hubOk && profile && isKnownProfile(hub, profile) === false) {
    return res.status(404).json({ success: false, error: "Profile not found" });
  }
  const payloadProjects = Array.isArray(body.projects) ? body.projects : [];
  // Profile isolation: the ranking pool contains ONLY the selected
  // freelancer's projects. Hub data is filtered by project profile links.
  // Caller-supplied projects (Hub unreachable) are filtered the same way
  // when they carry profile links; link-less payload items are kept because
  // the Hub Playground sends its own already profile-scoped selection.
  const pool = hubOk
    ? filterProjectsForProfile(hub.projects, profile)
    : payloadProjects.filter((p) => {
        const names = profileNamesOf(p).map(normalizeName);
        return names.length === 0 || names.includes(normalizeName(profile));
      });
  const category = detectCategory({
    explicit,
    message: clientMessage,
    hubCategories: hubOk ? hub.categories : pool.map((p) => p.category).filter(Boolean),
  });
  const selected = selectProjects(pool, { profile, category, message: clientMessage });
  const liveProjects = selected.filter((p) => p.live_url);
  const source = hubOk && liveProjects.length ? "hub" : "fallback";
  // Verified personalisation data from the Hub profile record (skills and
  // a dashboard-set portfolio fallback). The code portfolio map still wins.
  const metaProfile =
    hubOk && Array.isArray(hub.profiles)
      ? hub.profiles.find(
          (p) =>
            normalizeName(typeof p === "string" ? p : p && p.name) ===
            normalizeName(profile),
        )
      : null;
  const profileSkills = Array.isArray(metaProfile?.skills) ? metaProfile.skills : [];
  const portfolioFallback = metaProfile?.portfolio_url || null;

  const { text, mode } = await generateProposal({
    profile,
    clientName,
    category,
    clientMessage,
    projects: selected,
    profileSkills,
    portfolioFallback,
  });
  const proposal = sanitizeProposal(text) || text;
  return res.json({
    success: true,
    proposal,
    reply: proposal,
    category: category || null,
    source,
    projects: liveProjects.map((p) => ({ title: p.title, live_url: p.live_url })),
    mode,
  });
});

// JSON body parse errors -> 400 (not 500 HTML).
app.use((err, _req, res, _next) => {
  if (err && err.type === "entity.parse.failed") {
    return res.status(400).json({ success: false, error: "Invalid JSON body" });
  }
  return res.status(500).json({ success: false, error: "Internal error" });
});

if (require.main === module) {
  const port = Number(process.env.PORT || 9000);
  app.listen(port, "0.0.0.0", () => {
    // eslint-disable-next-line no-console
    console.log(`proposal-bot listening on 0.0.0.0:${port}`);
  });
}

module.exports = app;
module.exports._test = {
  detectCategory,
  selectProjects,
  sanitizeProposal,
  resetHubCache,
  llmConfig,
  resolveProfile,
  templateProposal,
  validateProposal,
  filterProjectsForProfile,
  isKnownProfile,
  isValidProfileName,
  resolveCollaborators,
  isInternalNote,
  publicProofText,
  analyzeJob,
  verifiedTechs,
  claimsUnverifiedTech,
  PORTFOLIO_LINKS,
  PROFILE_ALIASES,
};
