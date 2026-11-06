<!-- Add this section to AGENTS.md in your project, or to ~/.codex/AGENTS.md for all projects. -->

## Simplified Technical English (STE)

Write docs, prompts, skill files and agent instructions in Simplified Technical English (STE).

After you write or change a Markdown, text or reStructuredText file, do these steps:

1. Run `ste-check <files that you changed>`. If `ste-check` is not installed, run `python3 <path to ste-simplify>/skills/ste-simplify/scripts/ste_check.py <files>`.
2. Run `ste-fix --apply <files>` to apply the safe word replacements.
3. Run `ste-fix --format json <files>`. Write each sentence in the `rewrite` list again with the approved alternatives.
4. Run `ste-check` again. Do steps 3 and 4 again until the checker shows no errors.

Do not change code blocks, inline code, commands, paths, URLs, numbers or names. Keep text between quotation marks that users type. If the checker shows "No STE dictionary found", stop. Tell the user to run `ste-build-dictionary /path/to/ASD-STE100.pdf`.
