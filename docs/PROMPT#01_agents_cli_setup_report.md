# PROMPT#01 Agents CLI Setup Report

## Summary

Google Agents CLI was installed and verified for `D:\gaps\Business_Intel` without creating or scaffolding the Business_Intel app. The official setup path from `https://github.com/google/agents-cli` was used. The CLI is available as `agents-cli`, and the Google agents-cli skills are installed globally for coding agents.

Final verdict: PASS.

## Commands Run

- `Get-Content C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-workflow\SKILL.md`
- `Select-String C:\Users\Nilhan.dev\.codex\memories\MEMORY.md ...`
- Opened official source: `https://github.com/google/agents-cli`
- `Get-Content D:\codex_skills\d-drive-skill-search\SKILL.md`
- `Get-Command es.exe, rg.exe, rga.exe, uv, uvx, python, node, npm, git, winget`
- `New-Item -ItemType Directory -Force Evidence, docs, tools, logs`
- `D:\codex_skills\d-drive-skill-search\scripts\scan-d-skill-roots.ps1 -DriveRoot D:\ -Top 30 -OutputDir D:\gaps\Business_Intel\Evidence\PROMPT#01_skill_scan`
- `python --version`
- `uv --version`
- `uvx --version`
- `node --version`
- `npm --version`
- `npx --version`
- `git --version`
- `winget --version`
- `uvx google-agents-cli setup`
- `$env:PYTHONIOENCODING='utf-8'; $env:PYTHONUTF8='1'; uvx google-agents-cli setup`
- `agents-cli --help`
- `agents-cli info`
- `agents-cli setup --help`
- `Get-Command agents-cli`
- `Get-ChildItem C:\Users\Nilhan.dev\.agents\skills -Recurse -Filter SKILL.md`

Full command evidence is in `D:\gaps\Business_Intel\logs\PROMPT#01_commands.log`.

## Versions Found

- OS: Microsoft Windows 11 Home 10.0.26200 Build 26200 64-bit
- PowerShell: 7.6.0
- Python: 3.12.10
- uv / uvx: 0.10.8
- Node.js: v22.15.0
- npm / npx: 10.9.2
- Git: 2.53.0.windows.2
- winget: v1.28.240
- agents-cli: 0.1.1

## Installed Components

- Google Agents CLI: `C:\Users\Nilhan.dev\.local\bin\agents-cli.exe`
- CLI package path: `C:\Users\Nilhan.dev\AppData\Roaming\uv\tools\google-agents-cli\Lib\site-packages\google\agents\cli`
- Global Google agents-cli skills installed under `C:\Users\Nilhan.dev\.agents\skills`
- Setup scope reported by installer: global
- No Business_Intel app scaffold was created.

## Skill Locations Discovered

Installed Google agents-cli skills:

- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-workflow\SKILL.md`
- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-adk-code\SKILL.md`
- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-scaffold\SKILL.md`
- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-eval\SKILL.md`
- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-deploy\SKILL.md`
- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-publish\SKILL.md`
- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-observability\SKILL.md`

D: skill/TAC discovery:

- D: scan used `rg`; `es.exe` and `rga.exe` were not found.
- Scan output: `D:\gaps\Business_Intel\Evidence\PROMPT#01_skill_scan`
- Total D: `SKILL.md` files found: 39,319
- Relevant D: skills/TAC discovered:
  - `D:\codex_skills\d-drive-skill-search\SKILL.md`
  - `D:\AI\GPT_Codex\Only to select skills\.agent\skills\tac-quicksearch\SKILL.md`
  - `D:\AI\GPT_Codex\Only to select skills\.agent\skills\find-skills\SKILL.md`
  - `D:\AI\GPT_Codex\Only to select skills\.agents\skills\d-drive-weapon-search\SKILL.md`
  - `D:\AI\GPT_Codex\Only to select skills\.agents\skills\git-repo-research-mcp-server\SKILL.md`
  - `D:\select_skills2\open-as-creator\SKILL.md`

## Chosen TAC/Skills/Weapons

- `C:\Users\Nilhan.dev\.agents\skills\google-agents-cli-workflow\SKILL.md` was used for official workflow and install guidance.
- `D:\codex_skills\d-drive-skill-search\SKILL.md` was used for fast Drive D skill/TAC inventory.
- Official Google agents-cli repository/docs were used for the current install command and command list: `https://github.com/google/agents-cli`.

## Missing Prerequisites Or Failures

No prerequisite was missing. Python 3.11+, uv, Node.js, npm/npx, and Git were all available.

Resolved issue: the first `uvx google-agents-cli setup` failed with `UnicodeEncodeError` while printing the setup logo in a non-UTF-8 Windows console. The same official setup command succeeded after setting `PYTHONIOENCODING=utf-8` and `PYTHONUTF8=1`.

`npx skills add google/agents-cli` was not run manually because the successful `uvx google-agents-cli setup` invoked the skills installer internally and installed all 7 expected Google agents-cli skills.

## Exact Next Recommended Prompt

Use the installed Google agents-cli skills to create a design/spec only for the Sri Lanka Public-Signal Lead Intelligence Engine. Do not scaffold or build the app yet. In `D:\gaps\Business_Intel`, search Drive D for relevant TAC/skills first, then create `DESIGN_SPEC.md` and a new evidence pack under `D:\gaps\Business_Intel\Evidence` for PROMPT#02. Exclude tender intelligence unless explicitly requested.

## Final Verdict

PASS.
