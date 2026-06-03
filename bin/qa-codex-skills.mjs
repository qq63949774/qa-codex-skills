#!/usr/bin/env node

import { access, cp, mkdir, readdir, readFile, rm, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import os from "node:os";

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const skillsRoot = path.join(repoRoot, "skills");

function usage() {
  console.log(`Usage:
  qa-codex-skills list
  qa-codex-skills check
  qa-codex-skills safety-scan
  qa-codex-skills install [--force] [--skills a,b,c]

Environment:
  CODEX_HOME  Defaults to ~/.codex
`);
}

function parseArgs(argv) {
  const args = { command: argv[2] || "help", force: false, skills: [] };
  for (let index = 3; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === "--force") {
      args.force = true;
    } else if (arg === "--skills") {
      const value = argv[index + 1] || "";
      args.skills = value.split(",").map((item) => item.trim()).filter(Boolean);
      index += 1;
    } else if (arg === "--help" || arg === "-h") {
      args.command = "help";
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }
  return args;
}

async function exists(filePath) {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function getSkillNames() {
  const entries = await readdir(skillsRoot, { withFileTypes: true });
  const names = [];
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const skillPath = path.join(skillsRoot, entry.name);
    if (await exists(path.join(skillPath, "SKILL.md"))) {
      names.push(entry.name);
    }
  }
  return names.sort();
}

function getCodexHome() {
  return process.env.CODEX_HOME
    ? path.resolve(process.env.CODEX_HOME)
    : path.join(os.homedir(), ".codex");
}

async function listSkills() {
  const names = await getSkillNames();
  names.forEach((name) => console.log(name));
}

function commandExists(command) {
  const result = spawnSync("sh", ["-lc", `command -v ${command}`], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return result.status === 0 ? result.stdout.trim() : "";
}

function runCheck(command) {
  const result = spawnSync("sh", ["-lc", command], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return {
    ok: result.status === 0,
    output: `${result.stdout || ""}${result.stderr || ""}`.trim(),
  };
}

async function checkEnvironment() {
  const codexHome = getCodexHome();
  const codexSkills = path.join(codexHome, "skills");
  const nodeBin = commandExists("node");
  const larkCliBin = commandExists("lark-cli");
  const gitBin = commandExists("git");
  const larkWhoami = larkCliBin ? runCheck("lark-cli auth status") : { ok: false, output: "lark-cli not found" };

  console.log(`Codex home: ${codexHome}`);
  console.log(`Codex skills dir: ${codexSkills}`);
  console.log(`Node: ${nodeBin || "missing"}`);
  console.log(`Git: ${gitBin || "missing"}`);
  console.log(`lark-cli: ${larkCliBin || "missing"}`);
  console.log(`lark-cli auth: ${larkWhoami.ok ? "ok" : "needs attention"}`);
  if (larkWhoami.output) {
    console.log(larkWhoami.output);
  }
}

function scanText(command) {
  const result = spawnSync("sh", ["-lc", command], {
    cwd: repoRoot,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  return {
    status: result.status ?? 1,
    output: `${result.stdout || ""}${result.stderr || ""}`.trim(),
  };
}

async function safetyScan() {
  const checks = [
    {
      name: "personal paths and fixed accounts",
      command:
        "rg -n --hidden --glob '!bin/qa-codex-skills.mjs' -S '(/Users/adin|/Users/pengyibin|Desktop/moby|Downloads/mixfun|192\\\\.168\\\\.|deltafun|qq63949774)' .",
      allowMatches: false,
    },
    {
      name: "real-looking secrets",
      command:
        "rg -n --hidden --glob '!bin/qa-codex-skills.mjs' -S '(BEGIN .*PRIVATE KEY|sk-[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{20,})' .",
      allowMatches: false,
    },
    {
      name: "generated caches",
      command: "find . \\( -name .DS_Store -o -name __pycache__ -o -name '*.pyc' \\) -print",
      allowMatches: false,
    },
    {
      name: "package files",
      command: "find . -maxdepth 2 \\( -name package-lock.json -o -name node_modules \\) -print",
      allowMatches: false,
    },
  ];

  let failed = false;
  for (const check of checks) {
    const result = scanText(check.command);
    const hasMatches = Boolean(result.output);
    const ok = check.allowMatches ? result.status === 0 : !hasMatches;
    console.log(`${ok ? "ok" : "fail"} - ${check.name}`);
    if (!ok && result.output) {
      console.log(result.output);
    }
    failed = failed || !ok;
  }

  if (failed) {
    throw new Error("safety-scan failed");
  }
}

async function validateSkill(skillName) {
  const skillPath = path.join(skillsRoot, skillName);
  const skillStat = await stat(skillPath).catch(() => null);
  if (!skillStat?.isDirectory()) {
    throw new Error(`Skill not found: ${skillName}`);
  }
  const skillFile = path.join(skillPath, "SKILL.md");
  const text = await readFile(skillFile, "utf8");
  if (!/^---[\s\S]*name:/m.test(text)) {
    throw new Error(`Invalid SKILL.md frontmatter: ${skillName}`);
  }
}

async function installSkills(options) {
  const allNames = await getSkillNames();
  const names = options.skills.length ? options.skills : allNames;
  for (const name of names) {
    await validateSkill(name);
  }

  const destinationRoot = path.join(getCodexHome(), "skills");
  await mkdir(destinationRoot, { recursive: true });

  for (const name of names) {
    const source = path.join(skillsRoot, name);
    const destination = path.join(destinationRoot, name);
    if (await exists(destination)) {
      if (!options.force) {
        console.log(`skip ${name}: already installed at ${destination}`);
        continue;
      }
      await rm(destination, { recursive: true, force: true });
    }
    await cp(source, destination, {
      recursive: true,
      filter: (src) => {
        const base = path.basename(src);
        return base !== ".DS_Store" && base !== "__pycache__" && !base.endsWith(".pyc");
      },
    });
    console.log(`installed ${name} -> ${destination}`);
  }

  console.log("Restart Codex to pick up new or updated skills.");
}

async function main() {
  const args = parseArgs(process.argv);
  if (args.command === "help") {
    usage();
  } else if (args.command === "list") {
    await listSkills();
  } else if (args.command === "check") {
    await checkEnvironment();
  } else if (args.command === "safety-scan") {
    await safetyScan();
  } else if (args.command === "install") {
    await installSkills(args);
  } else {
    throw new Error(`Unknown command: ${args.command}`);
  }
}

main().catch((error) => {
  console.error(error.message || error);
  process.exit(1);
});
