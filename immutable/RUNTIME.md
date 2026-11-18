# Running an immutable skill

Use the consumer repository as the working directory. The installed plugin supplies
the scripts, profiles, strings, starters and skill templates. Locate the actual
`SKILL.md` selected by the client. In Claude Code its directory is shown as the
skill's base directory. In Codex the available-skills entry supplies the file path.
Resolve any short path with the skill roots table supplied by the client.

For each shell invocation using bundled assets, set `IMMUTABLE_ROOT` in **that
invocation**. Substitute the selected file's absolute path as one quoted argument:

```sh
IMMUTABLE_ROOT="$(python3 -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).resolve(strict=True).parents[1])' '/absolute/path/to/selected/SKILL.md')" || exit 1
```

Claude Code can also use its supplied `CLAUDE_PLUGIN_ROOT` as `IMMUTABLE_ROOT`.
Resolve relative skill links against the physical skill directory. Expand plugin paths
in user-facing commands to quoted absolute paths usable from a fresh shell.
Run the workflow's Bash snippets with Bash.

| Operation in the shared procedure | Claude Code | Codex |
| --- | --- | --- |
| Invoke or suggest `/immutable:<name>` | Use the slash command | Mention `$immutable:<name>` or select it in `/skills`. Translate invocations in rendered catalog strings and handoffs too. |
| Ask or confirm, including `AskUserQuestion` | Use the question tool when available | Use the question tool offered in the current mode, e.g. `request_user_input` in Plan mode. |
| Glob, Grep | Use the named tools | List paths with `rg --files` (include hidden configuration when needed). Use `rg` for source searches. |
| Write, Edit | Use the named tools | Use the workspace editor or `apply_patch`. Verify the destination and existing text before editing. |
| Bash, WebFetch, WebSearch | Use the named tools when available | Use the shell or available web tools for the same operation. Follow the stage's fallback when a capability is unavailable. |

For an interview question or approval, present the same prompt, choices and recommendation
as the procedure. If the tool is absent, restricted, or unable to express the question,
ask it in conversation and end the turn. With an asynchronous question, wait for the
user's actual answer. A suggested default, lack of a reply, or a read-only planning
mode cannot authorize a write. Resume at the pending question. Run each required
review perspective and apply the configured gate before generating a document.

Both clients read the consumer's existing `.immutable-prd/` configuration and
share the working notes under `.claude/immutable/` and `.claude/sdd-mode` where the skill
uses them. Honor applicable repository instructions, including `AGENTS.md` in Codex.
