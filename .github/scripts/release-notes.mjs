// Generates a Fern changelog entry for a confident-client SDK release.
//
// confident-client is a monorepo with two independently-versioned SDKs:
//   - python/       tagged  python-v*
//   - typescript/   tagged  typescript-v*
//
// On each tag push the release workflow resolves the SDK and the previous
// release tag, collects the commit subjects in that range that touched the
// SDK's directory, and hands them to this script. The script:
//   1. Summarizes + categorizes the raw commit subjects with an OpenAI
//      structured-output call (strict JSON schema, so the result parses
//      deterministically).
//   2. Renders a Fern changelog card (`## <SDK> vX.Y.Z` + sections).
//   3. Writes it into the date-keyed .mdx file, prepending if the file
//      already exists (newest first) and merging the SDK's frontmatter tag.
//
// Consumed by the `changelog` job in .github/workflows/release.yml.
// Node 20+ (uses global fetch). No dependencies.

import fs from "node:fs";
import path from "node:path";

const {
  SDK,
  TAG,
  DISPLAY_VERSION,
  PREV_TAG,
  RELEASE_DATE,
  RAW_NOTES_FILE,
  OPENAI_API_KEY,
  OPENAI_MODEL = "gpt-5.4-mini",
  CHANGELOG_DIR,
} = process.env;

function requireEnv(name, value) {
  if (!value) {
    console.error(`release-notes: missing required env var ${name}`);
    process.exit(1);
  }
  return value;
}

requireEnv("SDK", SDK);
requireEnv("TAG", TAG);
requireEnv("DISPLAY_VERSION", DISPLAY_VERSION);
requireEnv("RELEASE_DATE", RELEASE_DATE);
requireEnv("OPENAI_API_KEY", OPENAI_API_KEY);
requireEnv("CHANGELOG_DIR", CHANGELOG_DIR);

const SDK_LABELS = {
  python: "Python SDK",
  typescript: "TypeScript SDK",
};

const SDK_LABEL = SDK_LABELS[SDK];
if (!SDK_LABEL) {
  console.error(`release-notes: unknown SDK "${SDK}" (expected python | typescript)`);
  process.exit(1);
}

function readRawNotes() {
  if (!RAW_NOTES_FILE || !fs.existsSync(RAW_NOTES_FILE)) return "";
  return fs.readFileSync(RAW_NOTES_FILE, "utf8").trim();
}

const ITEM_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    title: {
      type: "string",
      description: "Short capitalized name of the change.",
    },
    description: {
      type: "string",
      description: "One-sentence, factual description.",
    },
  },
  required: ["title", "description"],
};

const RESPONSE_SCHEMA = {
  type: "object",
  additionalProperties: false,
  properties: {
    summary: {
      type: "string",
      description: "1-2 sentence factual overview of the release.",
    },
    features: { type: "array", items: ITEM_SCHEMA },
    improvements: { type: "array", items: ITEM_SCHEMA },
    fixes: { type: "array", items: ITEM_SCHEMA },
    breaking_changes: {
      type: "array",
      items: {
        type: "object",
        additionalProperties: false,
        properties: {
          title: { type: "string" },
          description: { type: "string" },
          migration: {
            type: ["string", "null"],
            description: "Concrete migration step for SDK consumers, or null if none.",
          },
        },
        required: ["title", "description", "migration"],
      },
    },
  },
  required: ["summary", "features", "improvements", "fixes", "breaking_changes"],
};

const SYSTEM_PROMPT = [
  `You are the release-notes editor for the Confident AI ${SDK_LABEL} (an open-source client library for the Confident AI platform management API).`,
  "Your audience is developers who install and upgrade this SDK.",
  "Tone: professional, factual, concise. No marketing fluff, no jokes, no emoji.",
  "From the raw commit subjects, produce categorized, user-facing release notes.",
  "Rules:",
  "- Omit internal-only noise: CI, chores, tests, refactors, dependency bumps, lint/format fixes, and docs, unless they change public SDK behavior.",
  "- Only describe changes to THIS SDK; ignore anything about the other SDK or unrelated subsystems.",
  "- If a category has nothing user-facing, return an empty array for it.",
  "- Flag anything that changes public method signatures, return shapes, imports, or supported runtimes as a breaking change with a concrete migration step.",
  "- Keep each item to a single sentence. Do not invent changes that are not in the input.",
].join("\n");

async function summarize(rawNotes) {
  const res = await fetch("https://api.openai.com/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENAI_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      model: OPENAI_MODEL,
      messages: [
        { role: "system", content: SYSTEM_PROMPT },
        {
          role: "user",
          content: `${SDK_LABEL} release ${DISPLAY_VERSION} (previous release: ${PREV_TAG || "none — first release"}).\n\nRaw commit subjects in this range (already filtered to the ${SDK}/ directory):\n\n${rawNotes || "(no changes detected)"}`,
        },
      ],
      response_format: {
        type: "json_schema",
        json_schema: {
          name: "sdk_release_notes",
          strict: true,
          schema: RESPONSE_SCHEMA,
        },
      },
    }),
  });
  if (!res.ok) throw new Error(`OpenAI ${res.status}: ${await res.text()}`);
  const json = await res.json();
  return JSON.parse(json.choices[0].message.content);
}

function renderCard(data) {
  const out = [`## ${SDK_LABEL} ${DISPLAY_VERSION}`, ""];
  if (data.summary) out.push(data.summary, "");

  const section = (heading, items) => {
    if (!items?.length) return;
    out.push(`### ${heading}`);
    for (const it of items) out.push(`- **${it.title}** — ${it.description}`);
    out.push("");
  };
  section("New Features", data.features);
  section("Improvements", data.improvements);
  section("Fixes", data.fixes);

  if (data.breaking_changes?.length) {
    out.push("<Warning>", "**Breaking changes**", "");
    for (const b of data.breaking_changes) {
      let line = `- **${b.title}** — ${b.description}`;
      if (b.migration) line += ` _Migration:_ ${b.migration}`;
      out.push(line);
    }
    out.push("</Warning>", "");
  }

  return out.join("\n").trimEnd() + "\n";
}

function buildFrontmatter(tags) {
  const list = tags.map((t) => `"${t}"`).join(", ");
  return `---\ntags: [${list}]\n---\n`;
}

function escapeRegExp(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// Merge SDK_LABEL into an existing frontmatter `tags: [...]` list, preserving order.
function mergeTags(frontmatter) {
  const match = frontmatter.match(/tags:\s*\[([^\]]*)\]/);
  const existing = match
    ? [...match[1].matchAll(/"([^"]*)"/g)].map((m) => m[1])
    : [];
  if (!existing.includes(SDK_LABEL)) existing.push(SDK_LABEL);
  return buildFrontmatter(existing);
}

function writeEntry(card) {
  fs.mkdirSync(CHANGELOG_DIR, { recursive: true });
  const file = path.join(CHANGELOG_DIR, `${RELEASE_DATE}.mdx`);

  if (!fs.existsSync(file)) {
    fs.writeFileSync(file, `${buildFrontmatter([SDK_LABEL])}\n${card}`);
    console.log(`release-notes: wrote ${file}`);
    return;
  }

  const content = fs.readFileSync(file, "utf8");
  // Idempotent: re-running the workflow for the same SDK + version is a no-op.
  const marker = new RegExp(
    `^##\\s+${escapeRegExp(`${SDK_LABEL} ${DISPLAY_VERSION}`)}\\s*$`,
    "m",
  );
  if (marker.test(content)) {
    console.log(
      `release-notes: entry for ${SDK_LABEL} ${DISPLAY_VERSION} already present in ${file}; nothing to do.`,
    );
    return;
  }

  // Prepend the new card after the frontmatter block (newest first), merging tags.
  const fm = content.match(/^---\n[\s\S]*?\n---\n/);
  const next = fm
    ? `${mergeTags(fm[0])}\n${card}\n${content.slice(fm[0].length).replace(/^\n+/, "")}`
    : `${buildFrontmatter([SDK_LABEL])}\n${card}\n${content}`;
  fs.writeFileSync(file, next);
  console.log(`release-notes: prepended ${SDK_LABEL} ${DISPLAY_VERSION} into ${file}`);
}

const rawNotes = readRawNotes();
const data = await summarize(rawNotes);
writeEntry(renderCard(data));
