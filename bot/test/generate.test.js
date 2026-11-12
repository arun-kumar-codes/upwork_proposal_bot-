/** Bot tests: auth, live_url selection, hub vs fallback, no github.com. Run: npm test */
const { test, before, after } = require("node:test");
const assert = require("node:assert/strict");
const http = require("node:http");

const app = require("../index.js");
const { selectProjects, detectCategory, sanitizeProposal } = app._test;

let server;
let base;
let hubServer;
let hubBase;

const HUB_PROJECTS = [
  { id: 1, title: "Shop Demo", category: "web", status: "active", github_url: "https://github.com/demo/shop", live_url: "https://shop.example.com", tech_stack: ["nextjs"], profiles: [{ id: 1, name: "Web Dev" }] },
  { id: 2, title: "No Live App", category: "web", status: "active", github_url: "https://github.com/demo/nolive", live_url: null, tech_stack: ["nextjs"], profiles: [{ id: 1, name: "Web Dev" }] },
  { id: 3, title: "ML Tool", category: "ml", status: "active", github_url: "https://github.com/demo/ml", live_url: "https://ml.example.com", tech_stack: ["python"], profiles: [{ id: 2, name: "Data AI" }] },
  { id: 4, title: "Lovable Store Builder", category: "web", status: "active", github_url: "https://github.com/demo/lovable", live_url: "https://lovable.example.com", tech_stack: ["react"], description: "store builder made with React and Node", result: "client sales went up after launch", profiles: [{ id: 3, name: "Arun" }] },
];

before(async () => {
  hubServer = http.createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    if (req.url.startsWith("/api/categories")) return res.end(JSON.stringify(["ml", "web"]));
    if (req.url.startsWith("/api/projects")) return res.end(JSON.stringify(HUB_PROJECTS));
    res.statusCode = 404;
    return res.end("{}");
  });
  await new Promise((r) => hubServer.listen(0, "127.0.0.1", r));
  hubBase = `http://127.0.0.1:${hubServer.address().port}`;
  await new Promise((r) => {
    server = app.listen(0, "127.0.0.1", () => {
      base = `http://127.0.0.1:${server.address().port}`;
      r();
    });
  });
});

after(async () => {
  await new Promise((r) => server.close(r));
  await new Promise((r) => hubServer.close(r));
});

function generate(key, body, contentType = "application/json", raw) {
  const headers = { "Content-Type": contentType };
  if (key !== undefined) headers["X-API-Key"] = key;
  return fetch(`${base}/generate`, {
    method: "POST",
    headers,
    body: raw !== undefined ? raw : JSON.stringify(body),
  });
}

function useEnv(vars) {
  for (const [k, v] of Object.entries(vars)) {
    if (v === undefined) delete process.env[k];
    else process.env[k] = v;
  }
  app._test.resetHubCache();
}

test("selection prefers live_url and drops github_url", () => {
  const picked = selectProjects(HUB_PROJECTS, {
    profile: "Web Dev", category: "web", message: "Need a nextjs web store",
  });
  assert.equal(picked[0].title, "Shop Demo"); // profile+category+live wins
  assert.ok(picked.every((p) => !("github_url" in p)));
  const noLive = selectProjects([HUB_PROJECTS[1]], { profile: "", category: "web", message: "" });
  assert.equal(noLive[0].live_url, ""); // kept in ranking, filtered for proposal later
});

test("detection normalizes aliases onto Hub categories", () => {
  assert.equal(detectCategory({ message: "Build a React frontend", hubCategories: ["ml", "web"] }), "web");
  assert.equal(detectCategory({ message: "Train a machine learning model", hubCategories: ["ml", "web"] }), "ml");
  assert.equal(detectCategory({ explicit: "shopify", message: "", hubCategories: ["web"] }), "shopify");
  assert.equal(sanitizeProposal("See https://github.com/demo/x now"), "See now");
});

test("hub up -> source hub, proposal has live link and no github.com", async () => {
  useEnv({ BOT_API_KEY: "test-bot-key", HUB_URL: hubBase, HUB_API_KEY: "hub-key", OPENAI_API_KEY: undefined });
  const res = await generate("test-bot-key", {
    profile: "Web Dev", client_message: "We need a web developer for our store",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.success, true);
  assert.equal(data.source, "hub");
  assert.equal(data.mode, "stub"); // no OPENAI_API_KEY -> documented stub mode
  assert.match(data.proposal, /shop\.example\.com/);
  assert.doesNotMatch(data.proposal, /github\.com/);
  assert.equal(data.reply, data.proposal);
});

test("hub down -> source fallback, still no github.com", async () => {
  useEnv({ BOT_API_KEY: "test-bot-key", HUB_URL: "http://127.0.0.1:1", HUB_API_KEY: "hub-key", OPENAI_API_KEY: undefined });
  const res = await generate("test-bot-key", {
    profile: "Web Dev", client_message: "We need a web developer",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.source, "fallback");
  assert.deepEqual(data.projects, []);
  assert.doesNotMatch(data.proposal, /github\.com/);
});

const ARUN_PORTFOLIO = "http://116.202.210.102:3700/portfolio/69492dc930db86ebbad04a03";

test("portfolio links resolve names and aliases without merging people", () => {
  const { resolveProfile } = app._test;
  assert.equal(resolveProfile("Arun").portfolio, ARUN_PORTFOLIO);
  assert.equal(resolveProfile("Faizal / LYT").portfolio, "http://116.202.210.102:3700/portfolio/695b83cff3cd570bc25c4db8");
  assert.equal(resolveProfile("Faizal").name, "Faisal");
  // Combined Excel token: first person owns the proposal; people are not merged.
  assert.equal(resolveProfile("Gopal, Vikas").portfolio, "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b");
  assert.equal(resolveProfile("Vikas Singh").portfolio, "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17");
  assert.equal(resolveProfile("Web Dev").portfolio, null); // unknown -> never invent a link
});

test("template proposal matches the original bot shape (Arun)", () => {
  const { templateProposal, validateProposal } = app._test;
  const text = templateProposal({
    profile: "Arun",
    clientName: "Aparna",
    category: "web",
    clientMessage: "We need a Lovable style web app for our store",
    projects: [
      { title: "Lovable Store Builder", live_url: "https://lovable.example.com", description: "store builder made with React and Node", result: "client sales went up after launch" },
    ],
  });
  assert.match(text, /hey Aparna/);
  assert.match(text, /I am Arun/);
  assert.match(text, /recently/);
  assert.ok(text.includes(`please review my portfolio: ${ARUN_PORTFOLIO}`));
  assert.ok(text.includes("https://lovable.example.com")); // exact live_url, pasted as-is
  assert.doesNotMatch(text, /Thank you for reaching out|Looking forward to connecting/);
  assert.doesNotMatch(text, /github\.com/);
  assert.doesNotMatch(text, /,/, "no commas anywhere in the proposal body");
  assert.ok(text.trimEnd().endsWith("Arun"));
  assert.equal(validateProposal(text, { portfolio: ARUN_PORTFOLIO, liveUrls: ["https://lovable.example.com"] }), true);
});

test("validator rejects corporate phrases, commas and missing portfolio", () => {
  const { validateProposal } = app._test;
  const ctx = { portfolio: ARUN_PORTFOLIO, liveUrls: ["https://lovable.example.com"] };
  const corporate = "Hi Aparna, Thank you for reaching out! I would love to help. Looking forward to connecting. Best, Arun";
  assert.equal(validateProposal(corporate, ctx), false);
  const noPortfolio = "hey Aparna\nI am Arun a web dev\nrecently I worked on Lovable Store Builder https://lovable.example.com";
  assert.equal(validateProposal(noPortfolio, ctx), false);
  const inventedLink = `hey Aparna\nI am Arun a web dev\nrecently I worked on X https://invented.example.com\nplease review my portfolio: ${ARUN_PORTFOLIO}`;
  assert.equal(validateProposal(inventedLink, ctx), false);
});

test("Arun HTTP generate (stub mode) follows the original contract", async () => {
  useEnv({ BOT_API_KEY: "test-bot-key", HUB_URL: hubBase, HUB_API_KEY: "hub-key", OPENAI_API_KEY: undefined, LLM_API_KEY: undefined });
  const res = await generate("test-bot-key", {
    profile: "Arun", clientName: "Aparna",
    client_message: "We need a Lovable style web app for our store",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.match(data.proposal, /hey Aparna/);
  assert.match(data.proposal, /I am Arun/);
  assert.match(data.proposal, /recently/);
  assert.ok(data.proposal.includes(`please review my portfolio: ${ARUN_PORTFOLIO}`));
  assert.ok(data.proposal.includes("https://lovable.example.com"));
  assert.doesNotMatch(data.proposal, /Thank you for reaching out|Looking forward to connecting|github\.com/);
  assert.equal(data.mode, "stub"); // no key -> template, same structure
});

test("llm config falls back to LLM_API_KEY / LLM_BASE_URL", () => {
  useEnv({
    OPENAI_API_KEY: undefined, OPENAI_BASE_URL: undefined,
    LLM_API_KEY: "llm-key", LLM_BASE_URL: "https://api.openai.com/v1/",
  });
  const cfg = app._test.llmConfig();
  assert.equal(cfg.key, "llm-key");
  assert.equal(cfg.url, "https://api.openai.com/v1/chat/completions");
  useEnv({ LLM_API_KEY: undefined, LLM_BASE_URL: undefined });
});

test("auth still enforced: 401 wrong/missing, 503 unset, 400 non-JSON", async () => {
  useEnv({ BOT_API_KEY: "test-bot-key", HUB_URL: hubBase, OPENAI_API_KEY: undefined });
  const body = { profile: "Web Dev", client_message: "hi" };
  assert.equal((await generate("wrong", body)).status, 401);
  assert.equal((await generate(undefined, body)).status, 401);
  assert.equal((await generate("test-bot-key", null, "text/plain", "hello")).status, 400);
  useEnv({ BOT_API_KEY: undefined });
  assert.equal((await generate("anything", body)).status, 503);
});

// --- Profile isolation: never cite another freelancer's projects ------------
const ISO_PROJECTS = [
  { id: 11, title: "Atul AI Tool", category: "ai", status: "active", github_url: "https://github.com/demo/atul-ai", live_url: "https://atul.example.com", tech_stack: ["python"], description: "AI tool built for clients", result: "Live product. Git URL not given. Team confirmed Active (Slack).", profiles: [{ id: 1, name: "Atul" }] },
  { id: 12, title: "Atul Web Store", category: "web", status: "active", github_url: "https://github.com/demo/atul-store", live_url: "https://atul-store.example.com", tech_stack: ["react"], description: "store built for clients", result: "live for real clients", profiles: [{ id: 1, name: "Atul" }] },
  { id: 13, title: "Tellaigent", category: "ai", status: "active", github_url: "https://github.com/demo/tellaigent", live_url: "https://tellaigent.ai", tech_stack: [], description: "Platform for AI agents", result: "", profiles: [{ id: 5, name: "Gopalan + Vikas" }] },
];
const ISO_PROFILES = [{ name: "Atul" }, { name: "Deepanshu" }, { name: "Kishan" }, { name: "Not named" }, { name: "Gopalan" }, { name: "Gopalan + Vikas" }];
let isoServer;
let isoBase;

before(async () => {
  isoServer = http.createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    if (req.url.startsWith("/api/categories")) return res.end(JSON.stringify(["ai", "web"]));
    if (req.url.startsWith("/api/meta/profiles")) return res.end(JSON.stringify(ISO_PROFILES));
    if (req.url.startsWith("/api/projects")) return res.end(JSON.stringify(ISO_PROJECTS));
    res.statusCode = 404;
    return res.end("{}");
  });
  await new Promise((r) => isoServer.listen(0, "127.0.0.1", r));
  isoBase = `http://127.0.0.1:${isoServer.address().port}`;
});

after(async () => {
  await new Promise((r) => isoServer.close(r));
});

function useIsoEnv() {
  useEnv({ BOT_API_KEY: "test-bot-key", HUB_URL: isoBase, HUB_API_KEY: "hub-key", OPENAI_API_KEY: undefined, LLM_API_KEY: undefined });
}

test("isolation unit: profile filter excludes foreign projects entirely", () => {
  const { filterProjectsForProfile } = app._test;
  assert.deepEqual(filterProjectsForProfile(ISO_PROJECTS, "Deepanshu"), []);
  assert.deepEqual(filterProjectsForProfile(ISO_PROJECTS, "Kishan"), []);
  assert.equal(filterProjectsForProfile(ISO_PROJECTS, "Atul").length, 2);
  assert.equal(filterProjectsForProfile(ISO_PROJECTS, "atul").length, 2); // case-insensitive
});

test("isolation: Deepanshu (zero own projects) gets safe no-proof proposal, not Atul's", async () => {
  useIsoEnv();
  const res = await generate("test-bot-key", {
    profile: "Deepanshu", client_message: "We need an AI automation tool for WhatsApp follow ups",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.deepEqual(data.projects, []);
  assert.equal(data.source, "fallback");
  assert.doesNotMatch(data.proposal, /atul\.example\.com|atul-store\.example\.com|Atul AI Tool|Atul Web Store/);
  assert.doesNotMatch(data.proposal, /recently/); // no fabricated experience
  assert.ok(data.proposal.includes("please review my portfolio: http://116.202.210.102:3700/portfolio/69492f8e30db86ebbad04a07"));
  assert.doesNotMatch(data.proposal, /github\.com/);
});

test("isolation: Kishan (zero own projects) gets safe no-proof proposal, not Atul's", async () => {
  useIsoEnv();
  const res = await generate("test-bot-key", {
    profile: "Kishan", client_message: "We need an AI automation tool for WhatsApp follow ups",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.deepEqual(data.projects, []);
  assert.doesNotMatch(data.proposal, /atul\.example\.com|Atul AI Tool|recently/);
  assert.ok(data.proposal.includes("please review my portfolio: http://116.202.210.102:3700/portfolio/69492ffc30db86ebbad04a0f"));
});

test("isolation: Atul still gets his own projects and portfolio", async () => {
  useIsoEnv();
  const res = await generate("test-bot-key", {
    profile: "Atul", client_message: "We need an AI automation tool for WhatsApp follow ups",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.equal(data.source, "hub");
  assert.ok(data.projects.length >= 1);
  assert.ok(data.projects.every((p) => p.title.startsWith("Atul")));
  assert.match(data.proposal, /atul\.example\.com/);
  assert.ok(data.proposal.includes("please review my portfolio: http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff"));
  // The fixture project's Notes/result is internal: it must not leak, while
  // its legitimate description still powers the proposal.
  assert.doesNotMatch(data.proposal, /Git URL|Slack|Team confirmed/);
  assert.match(data.proposal, /AI tool built for clients/);
});

test("internal notes never leak: internal result yields to the public description", () => {
  const { templateProposal, publicProofText, isInternalNote } = app._test;
  assert.equal(isInternalNote("Live product. Git URL not given."), true);
  assert.equal(isInternalNote("Team confirmed Active (Slack)."), true);
  assert.equal(isInternalNote("Added from Google Sheet. Linked to the Atul profile."), true);
  assert.equal(isInternalNote("client sales went up after launch"), false);
  // Internal-tainted result -> clean description wins.
  assert.equal(
    publicProofText({ result: "Live product. Git URL not given.", description: "Sports prediction site for fans" }),
    "Sports prediction site for fans",
  );
  // Clean verified result is preserved (not stripped wholesale).
  assert.equal(
    publicProofText({ result: "client sales went up after launch", description: "store builder" }),
    "client sales went up after launch",
  );
  // Internal-only, no description -> nothing client-facing remains.
  assert.equal(publicProofText({ result: "Team confirmed Active (Slack).", description: "" }), "");

  const text = templateProposal({
    profile: "Atul",
    clientName: "Aparna",
    category: "ai",
    clientMessage: "We need an AI tool",
    projects: [
      { title: "Atul AI Tool", live_url: "https://atul.example.com", description: "AI tool built for clients", result: "Live product. Git URL not given. Team confirmed Active (Slack)." },
    ],
  });
  assert.doesNotMatch(text, /Git URL|Slack|Team confirmed/);
  assert.match(text, /AI tool built for clients\./); // legitimate description intact

  const noPublic = templateProposal({
    profile: "Atul",
    clientName: "Aparna",
    category: "ai",
    clientMessage: "We need an AI tool",
    projects: [
      { title: "Atul AI Tool", live_url: "https://atul.example.com", description: "", result: "Added from Google Sheet. Linked to the Atul profile." },
    ],
  });
  assert.doesNotMatch(noPublic, /Google Sheet|Linked to/);
  assert.match(noPublic, /it is live right now and real users use it daily\./);
});

test("portfolio: Gopalan maps to Gopalan Prakash's verified portfolio", () => {
  const { resolveProfile, templateProposal } = app._test;
  const GOPALAN_URL = "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b";
  const VIKAS_KUMAR_URL = "http://116.202.210.102:3700/portfolio/6949313330db86ebbad04a35";
  const VIKAS_SINGH_URL = "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17";
  // Portfolio service identifies this ID as "Gopalan Prakash": Hub "Gopalan" is him.
  assert.deepEqual(resolveProfile("Gopalan"), { name: "Gopalan", portfolio: GOPALAN_URL });
  // Combined token: first contributor owns the proposal (people never merged).
  assert.deepEqual(resolveProfile("Gopalan + Vikas"), { name: "Gopalan", portfolio: GOPALAN_URL });
  // Owner confirmed the Tellaigent collaborator is Vikas Singh (not Kumar).
  assert.deepEqual(resolveProfile("Vikas Singh"), { name: "Vikas Singh", portfolio: VIKAS_SINGH_URL });
  // Bare "Vikas" is NOT globally aliased to Singh: no silent assignment.
  assert.deepEqual(resolveProfile("Vikas"), { name: "Vikas", portfolio: null });
  // Vikas Kumar keeps his own separate mapping and full-name sign-off.
  assert.deepEqual(resolveProfile("Vikas Kumar"), { name: "Vikas Kumar", portfolio: VIKAS_KUMAR_URL });

  const text = templateProposal({
    profile: "Gopalan",
    clientName: "Aparna",
    category: "ai",
    clientMessage: "We need a voice AI agent",
    projects: [
      { title: "Sydon", live_url: "https://sydon.ai/", description: "Amazon seller account-health system", result: "" },
    ],
  });
  assert.ok(text.includes(`please review my portfolio: ${GOPALAN_URL}`));
  assert.ok(text.trimEnd().endsWith("Gopalan"));

  const combined = templateProposal({
    profile: "Gopalan + Vikas",
    clientName: "Aparna",
    category: "ai",
    clientMessage: "We need a voice AI agent",
    projects: [
      { title: "Tellaigent", live_url: "https://tellaigent.ai", description: "Platform for AI agents", result: "" },
    ],
  });
  // Both verified contributors are represented, each with their own link.
  assert.ok(combined.includes(`please review my portfolio: ${GOPALAN_URL}`));
  assert.ok(combined.includes(`please review Vikas Singh's portfolio: ${VIKAS_SINGH_URL}`));
  assert.ok(!combined.includes(VIKAS_KUMAR_URL)); // a different person, never substituted
  assert.ok(combined.trimEnd().endsWith("Gopalan")); // signed by the first contributor only

  const singh = templateProposal({
    profile: "Vikas Singh",
    clientName: "Aparna",
    category: "ai",
    clientMessage: "We need an AI agent",
    projects: [
      { title: "Tellaigent", live_url: "https://tellaigent.ai", description: "Platform for AI agents", result: "" },
    ],
  });
  assert.ok(singh.includes(`please review my portfolio: ${VIKAS_SINGH_URL}`));
  assert.ok(!singh.includes(VIKAS_KUMAR_URL) && !singh.includes(GOPALAN_URL));
  assert.ok(singh.trimEnd().endsWith("Vikas Singh")); // full verified sign-off
});

test("portfolio: people-list parsing is restricted to verified combined profiles", () => {
  const { resolveCollaborators, templateProposal } = app._test;
  const SINGH_URL = "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17";
  // Lookalike combined names must NOT inherit Vikas Singh's portfolio.
  assert.deepEqual(resolveCollaborators("Kishan / Vikas"), []);
  assert.deepEqual(resolveCollaborators("Newdev + Vikas"), []);
  assert.deepEqual(resolveCollaborators("Atul, Vikas"), []);
  for (const profile of ["Kishan / Vikas", "Newdev + Vikas"]) {
    const text = templateProposal({
      profile,
      clientName: "Aparna",
      category: "ai",
      clientMessage: "We need an AI agent",
      projects: [
        { title: "Demo", live_url: "https://demo.example.com", description: "demo app", result: "" },
      ],
    });
    assert.ok(!text.includes(SINGH_URL), profile);
  }
});

test("portfolio: validator requires collaborator links when present", () => {
  const { validateProposal, resolveCollaborators } = app._test;
  const GOPALAN_URL = "http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b";
  const SINGH_URL = "http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17";
  assert.deepEqual(resolveCollaborators("Gopalan + Vikas"), [{ name: "Vikas Singh", portfolio: SINGH_URL }]);
  assert.deepEqual(resolveCollaborators("Gopalan"), []);
  assert.deepEqual(resolveCollaborators("Faizal / LYT"), []); // same person, not a collaborator
  const ctx = { portfolio: GOPALAN_URL, liveUrls: ["https://tellaigent.ai"], collaboratorPortfolios: [SINGH_URL] };
  const missing = `hey there\nI am Gopalan a AI dev\nrecently I worked on Tellaigent https://tellaigent.ai\nplease review my portfolio: ${GOPALAN_URL}`;
  assert.equal(validateProposal(missing, ctx), false); // collaborator link required
  assert.equal(validateProposal(`${missing}\nplease review Vikas Singh's portfolio: ${SINGH_URL}`, ctx), true);
});

test("portfolio maps stay in sync with the Hub (single verified source)", () => {
  // The Hub map is authoritative; this Bot mirror must not drift from it.
  const fs = require("node:fs");
  const path = require("node:path");
  const hubSource = fs.readFileSync(
    path.join(__dirname, "../../backend/app/services/playground.py"),
    "utf8",
  );
  const hubLinks = {};
  for (const m of hubSource.matchAll(/"([a-z][a-z ]*)":\s*"(http:\/\/116\.202\.210\.102:3700\/portfolio\/[a-f0-9]+)"/g)) {
    hubLinks[m[1]] = m[2];
  }
  assert.deepEqual(app._test.PORTFOLIO_LINKS, hubLinks);
  const aliasBlock = hubSource.slice(
    hubSource.indexOf("_PROFILE_ALIASES = {"),
    hubSource.indexOf("}", hubSource.indexOf("_PROFILE_ALIASES = {")),
  );
  const hubAliases = {};
  for (const m of aliasBlock.matchAll(/"([a-z][a-z /]*)":\s*"([a-z][a-z ]*)"/g)) {
    hubAliases[m[1]] = m[2];
  }
  assert.deepEqual(app._test.PROFILE_ALIASES, hubAliases);
});

test("portfolio HTTP: combined profile proposal carries both verified links", async () => {
  useIsoEnv();
  const res = await generate("test-bot-key", {
    profile: "Gopalan + Vikas", client_message: "We need a voice AI agent that calls customers",
  });
  assert.equal(res.status, 200);
  const data = await res.json();
  assert.ok(data.proposal.includes("please review my portfolio: http://116.202.210.102:3700/portfolio/69492fd730db86ebbad04a0b"));
  assert.ok(data.proposal.includes("please review Vikas Singh's portfolio: http://116.202.210.102:3700/portfolio/6949306730db86ebbad04a17"));
  assert.ok(!data.proposal.includes("6949313330db86ebbad04a35")); // Vikas Kumar never substituted
});

test("identity: placeholder and missing names are rejected with 400", async () => {
  useIsoEnv();
  // "Not named" exists in the Hub fixture, so rejection must come from
  // identity validation, not from the unknown-profile check.
  for (const bad of ["Not named", "Not", "Unknown", "N/A", "   "]) {
    const res = await generate("test-bot-key", { profile: bad, client_message: "Need a web app" });
    assert.equal(res.status, 400, `profile ${JSON.stringify(bad)} must be rejected`);
    const data = await res.json();
    assert.equal(data.success, false);
  }
  const missing = await generate("test-bot-key", { client_message: "Need a web app" });
  assert.equal(missing.status, 400);
});

test("identity unit: resolver never derives a placeholder display name", () => {
  const { resolveProfile } = app._test;
  assert.equal(resolveProfile("Not named").name, "");
  assert.equal(resolveProfile("Not named").portfolio, null);
  assert.equal(resolveProfile("Unknown").name, "");
  assert.equal(resolveProfile("N/A").name, "");
  assert.equal(resolveProfile("Arun").name, "Arun"); // valid names unaffected
});

// --- Proposal quality: relevance, personalisation, accuracy -----------------
test("quality: relevant project beats a newer irrelevant one", () => {
  const { selectProjects } = app._test;
  const picked = selectProjects(
    [
      { title: "No Limit Gaming", category: "full stack", live_url: "https://gaming.example.com", description: "Sports prediction site with virtual chips", tech_stack: [], profiles: [{ name: "Arun" }] },
      { title: "AhorraTya", category: "full stack", live_url: "https://deals.example.com", description: "Deals site so shoppers can find store promotions and compare offers", tech_stack: [], profiles: [{ name: "Arun" }] },
    ],
    { profile: "Arun", category: "web", message: "Hi I am Aparna we need a web app for our store where customers can browse products and pay online" },
  );
  assert.equal(picked[0].title, "AhorraTya");
  assert.match(picked[0].reason, /store/);
});

test("quality: template adapts per job and never invents skills from the job post", () => {
  const { templateProposal, validateProposal } = app._test;
  const projects = [
    { title: "AhorraTya", live_url: "https://deals.example.com", description: "Deals site so shoppers can find store promotions", result: "", tech_stack: [] },
  ];
  const store = templateProposal({
    profile: "Arun", category: "web",
    clientMessage: "Hi I am Aparna we need a React web app for our store with checkout",
    projects,
  });
  assert.match(store, /hey Aparna/);
  assert.match(store, /store where customers can browse and pay/);
  assert.match(store, /product pages and checkout/);
  assert.doesNotMatch(store, /I work with React/); // React is the client's ask only
  assert.doesNotMatch(store, /modern web tools/);

  const hospital = templateProposal({
    profile: "Arun", category: "web",
    clientMessage: "We need a CRM for our hospital front desk to manage patient appointments",
    projects,
  });
  assert.match(hospital, /keeps customers and bookings together/);
  assert.notEqual(hospital, store);

  // A verified skill may be claimed, and only then.
  const skilled = templateProposal({
    profile: "Arun", category: "web", profileSkills: ["React"],
    clientMessage: "We need a React web app for our store",
    projects,
  });
  assert.match(skilled, /I work with React/);

  const ctx = { portfolio: ARUN_PORTFOLIO, liveUrls: ["https://deals.example.com"], verifiedTechsList: [] };
  const claim = `hey there\nI am Arun a web dev I work with React\nrecently I worked on AhorraTya https://deals.example.com\nplease review my portfolio: ${ARUN_PORTFOLIO}`;
  assert.equal(validateProposal(claim, ctx), false);
  assert.equal(validateProposal(claim, { ...ctx, verifiedTechsList: ["react"] }), true);
});

// --- Hardening: distinctive proof, internal text, honest relevance ----------
const VOICE_JOB_BOT = "Hi I am Sara we run a real estate agency and we need a voice agent that calls leads on the phone and books meetings on our calendar so our team stops chasing calls all day";

test("hardening: voice claim requires distinctive evidence (Atul x voice)", () => {
  const { templateProposal, selectProjects } = app._test;
  const cofounder = { title: "AI Cofounder", category: "ai + full stack", live_url: "https://agent.example.com", description: "AI Cofounder agent that helps entrepreneurs brainstorm ideas and market analysis", result: "", tech_stack: [], profiles: [{ name: "Atul" }] };
  const tara = { title: "Tara", category: "ai + full stack + automation", live_url: "https://tara.example.com", description: "Business automation through WhatsApp or voice. Connects tools for email and follow ups", result: "", tech_stack: [], profiles: [{ name: "Atul" }] };
  const picked = selectProjects([cofounder, tara], { profile: "Atul", category: null, message: VOICE_JOB_BOT });
  assert.equal(picked[0].title, "Tara");
  assert.match(picked[0].reason, /covers your voice calls and booking need/);

  const weak = templateProposal({ profile: "Atul", clientMessage: VOICE_JOB_BOT, category: null, projects: [cofounder] });
  assert.doesNotMatch(weak, /covers your voice calls and booking need/);
  // Secondary-need coverage is no longer the headline fit claim: the
  // primary need (voice) is only RELATED for this project, so the template
  // uses related wording (Atul secondary-need case).
  assert.doesNotMatch(weak, /covers your AI agent work need/);
  assert.match(weak, /shows related AI agent work/);

  const strong = templateProposal({ profile: "Atul", clientMessage: VOICE_JOB_BOT, category: null, projects: [tara] });
  assert.match(strong, /covers your voice calls and booking need/);
});

test("hardening: weak-only voice match gets related wording (Aayush x voice)", () => {
  const { templateProposal } = app._test;
  const text = templateProposal({
    profile: "Aayush",
    clientMessage: "We need a voice agent to answer our phone calls",
    category: null,
    projects: [{ title: "Lead Helper", category: "ai", live_url: "https://helper.example.com", description: "agent dashboard that helps teams track leads", result: "", tech_stack: [] }],
  });
  assert.doesNotMatch(text, /covers your voice/);
  assert.match(text, /shows related AI agent work/);
});

test("hardening: internal status and collaboration text never leaks", () => {
  const { publicProofText, templateProposal } = app._test;
  assert.equal(
    publicProofText({ result: "Doc status: In-Progress.", description: "Multi-tenant RAG assistant. Each tenant uploads documents and asks questions" }).startsWith("Multi-tenant RAG assistant"),
    true,
  );
  assert.match(
    publicProofText({ result: "Live IP app. Shared by Gopalan and Vikas.", description: "AI sales rep. Makes outbound calls and books Google Calendar meetings" }),
    /Makes outbound calls/,
  );
  // Legitimate public results are preserved, not stripped.
  assert.equal(
    publicProofText({ result: "Live phone agents are answering calls for the clinic", description: "phone agent for clinics" }),
    "Live phone agents are answering calls for the clinic",
  );
  const text = templateProposal({
    profile: "Atul", clientMessage: "Hi I am Sara we need an AI assistant that answers questions from our own documents and manuals", category: "ai",
    projects: [{ title: "Lomex AI", category: "ai + full stack", live_url: "https://lomex.ai", description: "Multi-tenant RAG assistant. Each tenant uploads documents and asks questions", result: "Doc status: In-Progress.", tech_stack: [] }],
  });
  assert.doesNotMatch(text, /Doc status|In-Progress/);
  assert.match(text, /uploads documents and asks questions/);
});

test("hardening: shopify claim requires real store evidence (Arun positive)", () => {
  const { templateProposal } = app._test;
  const job = "Hi I am Lena we need a Shopify store where customers can browse our products and pay online with a smooth checkout and cart";
  const positive = templateProposal({
    profile: "Arun", clientMessage: job, category: null,
    projects: [{ title: "AhorraTya", category: "full stack", live_url: "https://deals.example.com", description: "Deals site so shoppers can find store promotions and compare offers", result: "", tech_stack: [] }],
  });
  assert.match(positive, /covers your store and checkout need/);
  const negative = templateProposal({
    profile: "Atul", clientMessage: job, category: null,
    projects: [{ title: "AI Cofounder", category: "ai + full stack", live_url: "https://agent.example.com", description: "AI Cofounder agent that helps entrepreneurs brainstorm ideas and market analysis", result: "", tech_stack: [] }],
  });
  assert.doesNotMatch(negative, /covers your store and checkout need/);
  assert.match(negative, /recent live work I shipped/);
});

test("hardening: category detection covers voice, store and dashboard", () => {
  const cats = ["ai", "ai + full stack", "automation", "full stack"];
  assert.equal(detectCategory({ message: VOICE_JOB_BOT, hubCategories: cats }), "voice");
  assert.equal(detectCategory({ message: "Hi I am Lena we need a Shopify store where customers can browse products and pay online", hubCategories: cats }), "shopify");
  assert.equal(detectCategory({ message: "Hi I am Raj we need a dashboard with live trading charts and reporting", hubCategories: cats }), "dashboard");
  assert.equal(detectCategory({ message: "Build a React frontend", hubCategories: ["ml", "web"] }), "web");
});

test("hardening: validator rejects unsupported coverage claims", () => {
  const { validateProposal } = app._test;
  const claim = `hey Sara\nI am Atul a full stack dev\nrecently I worked on AI Cofounder https://agent.example.com\nI picked this one because it already covers your voice calls and booking need.\nplease review my portfolio: http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff`;
  const ctx = { portfolio: "http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff", liveUrls: ["https://agent.example.com"] };
  assert.equal(validateProposal(claim, { ...ctx, unsupportedClaimLabels: ["voice calls and booking"] }), false);
  assert.equal(validateProposal(claim, { ...ctx, unsupportedClaimLabels: [] }), true);
});

test("evidence tiers: strength language rejected below COVER, honest related passes", () => {
  const { validateProposal, claimTier, analyzeJob } = app._test;
  const ctx = { portfolio: "http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff", liveUrls: ["https://agent.example.com"] };
  const bridges = [
    "this experience is directly related to the automation of manual work.",
    "this project aligns with your need for automating manual work.",
    "this project can match your needs exactly.",
    "this project closely aligns with your requirements.",
  ];
  for (const s of bridges) {
    const text = `hey Sara\nI am Atul a full stack dev\nrecently I worked on AI Cofounder https://agent.example.com\n${s}\nplease review my portfolio: ${ctx.portfolio}`;
    assert.equal(validateProposal(text, { ...ctx, claimTier: "RELATED" }), false, s);
    assert.equal(validateProposal(text, { ...ctx, claimTier: "NONE" }), false, s);
    assert.equal(validateProposal(text, { ...ctx, claimTier: "COVER" }), true, s);
    assert.equal(validateProposal(text, ctx), true, s); // legacy callers unchanged
  }
  const honest = `hey Sara\nI am Atul a full stack dev\nrecently I worked on AI Cofounder https://agent.example.com\nI picked this one because it is my closest related work.\nplease review my portfolio: ${ctx.portfolio}`;
  assert.equal(validateProposal(honest, { ...ctx, claimTier: "RELATED" }), true);
  const analysis = analyzeJob("Hi I am Sara we need a voice agent that calls leads and books meetings", null);
  assert.equal(claimTier(null, analysis, null), "NONE");
  assert.equal(claimTier({ title: "Tara", category: "ai + automation", live_url: "https://tara.example.com", description: "Business automation through WhatsApp or voice calls and booking", result: "", tech_stack: [] }, analysis, null), "COVER");
});

test("evidence tiers: per-need enforcement (Atul secondary-need case)", () => {
  const { validateProposal, claimTier, needTiers, analyzeJob } = app._test;
  const ctx = { portfolio: "http://116.202.210.102:3700/portfolio/69492da930db86ebbad049ff", liveUrls: ["https://agent.example.com"] };
  const cofounder = { title: "AI Cofounder", category: "ai + full stack", live_url: "https://agent.example.com", description: "AI Cofounder agent that helps entrepreneurs brainstorm ideas and market analysis", result: "", tech_stack: [] };
  const analysis = analyzeJob(VOICE_JOB_BOT, null);
  const tiers = needTiers(cofounder, analysis, null);
  assert.equal(tiers["AI agent work"], "COVER");
  assert.equal(tiers["voice calls and booking"], "RELATED");
  assert.equal(claimTier(cofounder, analysis, null), "RELATED");
  assert.equal(claimTier(null, analysis, null), "NONE");
  const claim = `hey Sara\nI am Atul a full stack dev\nrecently I worked on AI Cofounder https://agent.example.com\nI picked this one because it already covers your website build need.\nplease review my portfolio: ${ctx.portfolio}`;
  assert.equal(validateProposal(claim, { ...ctx, needTiers: { "website build": "RELATED" } }), false);
  assert.equal(validateProposal(claim, { ...ctx, needTiers: { "website build": "COVER" } }), true);
  assert.equal(validateProposal(claim, { ...ctx, claimTier: "RELATED", needTiers: { "website build": "COVER" } }), false);
});

test("template closing is contextual by need and evidence tier", () => {
  const { templateProposal } = app._test;
  const cofounder = { title: "AI Cofounder", category: "ai + full stack", live_url: "https://agent.example.com", description: "AI Cofounder agent that helps entrepreneurs brainstorm ideas and market analysis", result: "", tech_stack: [] };
  const tara = { title: "Tara", category: "ai + full stack + automation", live_url: "https://tara.example.com", description: "Business automation through WhatsApp or voice. Connects tools for email and follow ups", result: "", tech_stack: [] };
  const cover = templateProposal({ profile: "Atul", clientMessage: VOICE_JOB_BOT, category: null, projects: [tara] });
  assert.match(cover, /You will hear test calls before the agent handles live leads\./);
  assert.match(cover, /The project shown above gives that checkpoint a proven starting point\./);
  const related = templateProposal({ profile: "Atul", clientMessage: VOICE_JOB_BOT, category: null, projects: [cofounder] });
  assert.match(related, /You will hear test calls before the agent handles live leads\./);
  assert.match(related, /The related work gives useful context/);
  assert.doesNotMatch(related, /proven starting point/);
  const none = templateProposal({ profile: "Deepanshu", clientMessage: VOICE_JOB_BOT, category: null, projects: [] });
  assert.match(none, /You will hear test calls before the agent handles live leads\./);
  assert.match(none, /That checkpoint will prove the parts specific to your job/);
  const docs = templateProposal({ profile: "Atul", clientMessage: "Hi I am Sara we need an AI assistant that answers questions from our own documents and manuals and should cite the source document", category: null, projects: [cofounder] });
  assert.match(docs, /You will test answers from your real documents before a wider rollout\./);
  assert.doesNotMatch(docs, /You will hear test calls/);
  for (const text of [cover, related, none, docs]) {
    assert.doesNotMatch(text, /I can start right away and I will share progress in small steps/);
    assert.doesNotMatch(text, /you will talk directly with the person writing the code/);
    assert.match(text, /Please let me know when we can proceed further\./);
  }
});

test("relevance floor: zero-reason projects are not proof (Arun cases)", () => {
  const { selectProjects } = app._test;
  const arunProjects = [
    { title: "No Limit Gaming", category: "ai + full stack", live_url: "https://nolimitgaming.bet/signin", description: "Sports prediction site. Users predict with virtual chips that have no cash value. Includes an AI advisory.", result: "", tech_stack: [], profiles: [{ name: "Arun" }] },
    { title: "InjuryConnect", category: "full stack", live_url: "https://injuryconnect.example.com", description: "Platform connecting injured workers with clinics and legal help.", result: "", tech_stack: [], profiles: [{ name: "Arun" }] },
    { title: "AhorraTya", category: "full stack", live_url: "https://ahorratya.example.com", description: "Savings and deals app for shoppers.", result: "", tech_stack: [], profiles: [{ name: "Arun" }] },
  ];
  const n8nJob = "Hi I am Jonas we need an n8n automation workflow that watches our CRM for new leads and sends personalised follow up emails automatically without anyone doing manual work";
  assert.deepEqual(selectProjects(arunProjects, { profile: "Arun", category: "automation", message: n8nJob }), []);
  const chatbotJob = "Hi I am Tom we need an AI agent chatbot on our website that answers customer questions and books appointments for our clinic without our front desk getting involved";
  const picked = selectProjects(arunProjects, { profile: "Arun", category: "ai", message: chatbotJob });
  assert.equal(picked[0].title, "No Limit Gaming");
  assert.match(picked[0].reason, /covers your AI agent work need/);
});

test("isolation: unknown freelancer is rejected, never signed for", async () => {
  useIsoEnv();
  const res = await generate("test-bot-key", {
    profile: "Zztop Unknown", client_message: "Need a web app",
  });
  assert.equal(res.status, 404);
  const data = await res.json();
  assert.equal(data.success, false);
});
