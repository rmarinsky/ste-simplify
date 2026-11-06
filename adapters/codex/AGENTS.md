<!-- Add this section to AGENTS.md in your project, or to ~/.codex/AGENTS.md for all projects. -->

## Simplified Technical English (STE)

Write docs, prompts, skill files and agent instructions in Simplified Technical English (STE).

After you write or change a Markdown, text or reStructuredText file, do these steps:

1. Run `ste plan <files that you changed>`. If `ste` is not installed, run `python3 <path to ste-simplify>/skills/ste-simplify/scripts/ste.py plan <files>`.
2. Show the plan to the user. Show the safe replacements with their numbers, and a new sentence for each sentence in the list. Wait for the answer of the user.
3. Run `ste apply --skip <numbers that the user did not approve> <files>`.
4. Write the approved sentences into the files.
5. Run `ste check <files>`. If the check shows errors, do steps 1 to 5 again for these errors.

If the user tells you to do all of the changes without a review, do not stop at step 2.

Do not change code blocks, inline code, commands, paths, URLs, numbers or names. Keep text between quotation marks that users type. If the script shows "No STE dictionary found", stop. Tell the user to run `ste build-dictionary /path/to/ASD-STE100.pdf`.
