# QA Codex Skills

This repository distributes the QA Codex skills used by QA Proof Desk.

It contains only Codex skill instructions, scripts, references, and templates. It must not contain tested game project code, private repository checkouts, Feishu tokens, API keys, or local credential files.

## Install From GitHub

Teammates can install the skills with:

```bash
npx github:OWNER/REPO install
```

For a private repository, make sure GitHub SSH or HTTPS credentials are configured first.

Publishing this repository requires an explicitly chosen GitHub account and repository. Do not push it to whichever Git account happens to be logged in locally. Before pushing, set and verify the intended SSH remote:

```bash
git remote add origin git@github.com:OWNER/REPO.git
git remote -v
```

Install into a custom Codex home:

```bash
CODEX_HOME=~/.codex npx github:OWNER/REPO install
```

List bundled skills:

```bash
npx github:OWNER/REPO list
```

Check local prerequisites:

```bash
npx github:OWNER/REPO check
```

Restart Codex after installing or updating skills.

## Publish Gate

Before any commit or push, run:

```bash
npm run safety-scan
```

This repository is intended to contain skill instructions and helper scripts only. It must not contain game project source, personal absolute paths, real tokens, local credentials, generated caches, or accidental package installs.

## Local Development

From this repository:

```bash
npm run list
npm run check
npm run safety-scan
npm run install-skills
```

By default the installer copies skills into:

```text
~/.codex/skills
```

It refuses to overwrite existing skill folders unless `--force` is passed:

```bash
npm run install-skills -- --force
```

## Teammate Runtime Requirements

Each teammate runs the generated QA Proof Desk task package in their own Codex environment.

They need:

- Codex installed and restarted after skill installation.
- These skills installed under `~/.codex/skills`.
- `lark-cli` installed and authenticated with their own Feishu account.
- Access to the Feishu requirement, Bug List, and testcase Base.
- Access to the tested game project code path on their own machine.

The QA Proof Desk website shares workflow state and task packages. It does not centralize skill execution.

## Bundled Skills

- `imixsota-req-check`
- `mathsota-arithmetic-level-check`
- `mixword-level-legality-check`
- `mixword-version-config-diff`
- `multilang-ai-verify`
- `multilang-scan-qa`
- `pairmatch-level-solvability`
- `pairpop-backend-param-diff-testcase`
- `pairpop-crash-path-audit`
- `pairpop-level-legality`
- `qa-bug-driven-smoke-testcase`
- `qa-buglist-rc-risk`
- `qa-code-evidence-scan`
- `qa-req-code-scan`
- `qa-requirement-testcase-writer`
- `sotaten-level-legality`
- `tracking-testcase-writer`
- `wordtiles-level-scan`
