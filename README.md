# ste-simplify

Make the instructions for your AI agents clear and easy to read. This tool changes the text of your skills, agent files, rules, prompts and docs into Simplified Technical English (STE).

Use it on the text in your files. The script finds each word and each sentence that is not clear. It makes a plan for each change. You examine the plan. Then the model writes only the flagged sentences again. It operates in Claude Code, Codex, Cursor, pre-commit, GitHub Actions and a terminal.

STE is a controlled language. It has a dictionary of approved words and a set of writing rules. Each approved word has only one sense. The specification is ASD-STE100 from ASD (AeroSpace, Security and Defence Industries Association of Europe). This project is compatible with ASD-STE100 Issue 9. ASD did not make this project, and ASD does not endorse it.

## How STE helps agents

A model reads each word of an instruction. If a word has more than one sense, the model selects one sense. It can select the incorrect sense. For example, "meet the bar" or "use the house standard" do not give a clear rule. STE gives these results:

- Each word has one sense. The model cannot select the incorrect sense.
- Each sentence has one instruction, with a maximum of 20 words. Tests show that a model obeys a smaller number of conditions when one instruction has many conditions ([FollowBench, ACL 2024](https://arxiv.org/abs/2310.20410)).
- A smaller number of words with more than one sense. Tests show that requests that are not clear decrease the precision of models. Models also frequently continue and do not tell the user about the problem ([Clarify When Necessary, 2023](https://arxiv.org/abs/2311.09469)).
- The same words for the same items in all files. Thus, two skills or two rules do not give different data about one item.
- Persons can also read the text more easily. In a test at Boeing, persons made a smaller number of errors with long procedures in STE. Persons with a first language that is not English got the most help ([Shubert, 1995](https://doi.org/10.2190/WG69-D74B-4DLL-2WBK)).

No test that measures STE in agent instructions is available at this time. Thus, compare the results of your agents before and after the change. ASD also writes that AI tools can help with STE, but a person must examine the result ([ASD document about STE and AI, 2026](https://www.asd-ste100.org/assets/files/WhitePaper-ASD-STE100_and_AI.pdf)). Thus, `ste fix` has a review step.

## Legal use of the dictionary

ASD has the copyright of ASD-STE100 and its dictionary. You must have written permission from ASD to make a copy of the document or a part of it. You must also have it to publish the document. ASD does not give this permission to persons or companies. Thus, this project obeys these rules:

- This repository does not contain a part of the standard. It does not contain the PDF, the dictionary, word lists or example sentences. It contains only code and the public link to the PDF on the ASD web site.
- `ste prepare` gets the PDF directly from the ASD web site, on your computer. The PDF stays in a temporary folder. After the command changes the PDF into the dictionary, it deletes the PDF.
- Only you can use the dictionary. It stays on your computer: `~/.config/ste-simplify/dictionary.json.gz` (JSON with no spaces, in a gzip file of approximately 160 KB).
- Do not commit, publish, upload or share the dictionary or a part of it. For example, do not put it in a public repository, a package, a web service or a CI artifact.
- In CI, the runner makes a dictionary with `ste prepare` for each run. The runner deletes it at the end of the run.
- Do not use the name ASD-STE100 for your tool. Do not tell users that your tool has the approval of ASD.

Make your local dictionary one time:

```bash
ste prepare
```

If the download does not operate, request a free copy on https://www.asd-ste100.org/STE_downloads.html. Then run `ste prepare --pdf /path/to/ASD-STE100.pdf`. The `.gitignore` of this repository ignores the dictionary files and `*.pdf`.

This text is not legal advice. Read the copyright notice on the first pages of the PDF.

For Issue 9, the command finds 883 approved entries and 1320 entries that are not approved. The specification gives 875 approved words and 1274 words that are not approved. The numbers are different because some words have one entry for each part of speech.

## Install

Python 3.9 or a newer version is necessary. To make the dictionary, `pdftotext` from poppler is also necessary (`brew install poppler` or `apt install poppler-utils`). The scripts have no other dependencies.

```bash
pipx install git+https://github.com/rmarinsky/ste-simplify
ste prepare
```

This gives one command, `ste`, with three parts: `prepare`, `scan` and `fix`.

You can also run the scripts without an installation:

```bash
git clone https://github.com/rmarinsky/ste-simplify
python3 ste-simplify/skills/ste-simplify/scripts/ste.py prepare
python3 ste-simplify/skills/ste-simplify/scripts/ste.py scan docs/
```

## Start

```bash
ste prepare                              # one time: make the local dictionary
ste scan README.md docs/                 # report (exit code 1 when there are errors)
ste fix docs/                            # numbered safe replacements and sentences to write again
ste fix --html docs/                     # a short table here, and a full report in your browser
ste fix --apply --skip 2,5 docs/         # apply the safe replacements, but not numbers 2 and 5
printf '%s\n' "$TEXT" | ste scan -       # examine text that is not in a file
```

The procedure has a review step. `ste fix` does not change files. A person reads the plan and rejects the replacements that are not correct. The person also adds project words to the allow-list. Then `ste fix --apply` writes only the approved replacements. The model writes the other flagged sentences again, and `ste scan` makes sure that the result is correct.

## Use it in your project

1. Install the command one time:

   ```bash
   pipx install git+https://github.com/rmarinsky/ste-simplify
   ```

2. Make your local dictionary one time. The folder is not important:

   ```bash
   ste prepare
   ```

3. Go to your project. Examine the instruction files:

   ```bash
   cd ~/my-project
   ste scan --summary .claude .cursor AGENTS.md docs
   ste scan .claude/skills/my-skill/SKILL.md
   ```

   With `--summary`, the command gives one line for each file. Without `--summary`, it gives the full report.

4. Add the names of your project to `.ste-allow.txt` at the project root, one name on each line. Use the list "Not in the dictionary" in the report to find them. For example, add the names of your products, your systems and your ticket tools.

5. Make the plan for one file:

   ```bash
   ste fix .claude/skills/my-skill/SKILL.md
   ```

   Read the safe replacements. Write down the numbers of the replacements that are not correct.

6. Apply the other safe replacements:

   ```bash
   ste fix --apply --skip 2,5 .claude/skills/my-skill/SKILL.md
   ```

7. Write the sentences in the list "Sentences to write again" again. You can tell a model to do this with the `ste-simplify` skill.

8. Run `ste scan` again. Do steps 5 to 8 again until there are no errors.

For a large folder, start with the files that the models read most frequently. For example, start with `AGENTS.md`, `CLAUDE.md`, the rules and the skill descriptions.

## The report

`ste fix --html` and `ste scan --html` give two reports:

1. A short table in the terminal. It has one line for each file, with the errors, the warnings, the safe replacements and the sentences to write again.
2. A full HTML page. The command opens it in your default browser. The page shows:
   - Each safe replacement in its line, with the word that it removes and the word that it adds. To keep the word in the text, click its check box. The page then makes the `ste fix --apply --skip N,N` command. Click Copy to get it.
   - Each sentence to write again, with the problem words in a different color. Below the sentence, one short line gives each problem, for example `should → MUST, IF` or `27 words, max 20`. Put the mouse pointer on it to see the STE examples.
   - The words that are not in the dictionary. Select the technical names of your project. Then click Copy to get the lines for `.ste-allow.txt`.
   - Filters for each rule, for warnings and for file paths.

The page has no external files. The command writes it to `~/.cache/ste-simplify/reports/`, not into your project, because it contains parts of your local dictionary. Do not publish it. Use `--html-out FILE` for a different path, and `--no-open` if you do not want the browser.

## Before and after

Before:

```text
You should always choose the main color from the house palette. Avoid gradients, since they
often look wrong. In case the user wants a real demo, start recording the screen and check the result.
```

`ste scan` finds 10 errors and 1 warning. For each word that is not approved, the report shows the approved alternatives and an STE example sentence from your local dictionary. The report also shows the -ing form "recording", and two instructions in one sentence ("and check").

`ste fix` makes a plan. It gives three safe replacements with numbers, and a list of sentences that the model must write again. After `ste fix --apply` and the new sentences, `ste scan` shows no errors:

```text
Always select the primary color from the palette of the app. Do not use gradients, because they
frequently look incorrect. If the user wants a demo of the app, record the screen. Then examine the result.
```

A skill description, before:

```yaml
description: Use this whenever the user asks for a landing page review ("review my landing"). It's important
  that you catch anything that would look off against the house standard; flag it and suggest a fix.
```

After (no errors):

```yaml
description: Use this skill when the user wants a review of a landing page ("review my landing"). Compare the
  page with the rules in DESIGN.md. Make a list of each difference. For each difference, give one correction.
```

The trigger phrase in quotation marks stays the same. The checker does not examine text between quotation marks, because STE tells you to keep that text as it is.

## Checks

| Check | STE rule | Level |
|---|---|---|
| Words that are not approved, with alternatives, STE examples and help text | 1.1 | error |
| Approved words with a different part of speech, for example "Check the file" (CHECK is a noun in STE) | 1.2 | error |
| Forms that are not approved, for example "using" or "chose" | 1.4, 3.1 | error |
| The -ing form of a verb | 3.5 | error |
| Words that are not in the dictionary (possibly technical names) | 1.5, 1.12 | warning |
| An instruction with more than 20 words | 5.1 | error |
| A descriptive sentence with more than 25 words | 6.3 | error |
| A paragraph with more than six sentences | 6.6 | warning |
| Possible passive voice | 3.6 | warning |
| Possibly two instructions in one sentence | 5.2 | warning |
| Contractions | 4.2 | error |
| Semicolons | 8.1 | error |

The checker counts words as STE tells you. Text in parentheses is one word. A hyphenated word is one word. A number with its unit is one word. The checker also counts a phrase between quotation marks and an inline code span as one word.

The checker does not examine code blocks, inline code, URLs, email addresses, file paths, command flags, HTML tags or front matter keys. In YAML files and in front matter, it examines only the `description` values (change this with `--yaml-keys`). With `--comments`, it also examines comments in source code.

## ste scan options

| Option | Effect |
|---|---|
| `--format text\|json\|sarif` | Report format. SARIF is for code scanning in CI. |
| `-o FILE` | Write the report to a file. |
| `--fail-on error\|warning\|never` | Exit code 1 when the checker finds problems at this level (default `error`). Exit code 2 is a setup error. |
| `--allow FILE` | One more allow-list. You can use this option more than one time. |
| `--no-default-allow` | Do not load the default allow-list for software work. |
| `--no-unknown` | Do not show words that are not in the dictionary. |
| `--words-only`, `--rules-only` | Do only the word checks, or only the writing rule checks. |
| `--check-quotes` | Also examine words between quotation marks. |
| `--comments` | Also examine comments in source code. |
| `--dictionary FILE` | Use a different dictionary file. You can also set `STE_DICTIONARY`. |
| `--max-procedure`, `--max-descriptive`, `--max-paragraph` | Change the limits (20, 25 and 6). |
| `--summary` | One line for each file. |

## Technical names

STE lets you use technical nouns and technical verbs of your subject field (rules 1.5 and 1.12). The checker has a default allow-list for software, UI and agent work (`skills/ste-simplify/scripts/ste_simplify/data/software.allow`). For your project, put a `.ste-allow.txt` file at the project root, with one name or phrase on each line. The checker finds this file in the folder of the first path or in a parent folder.

To skip a line, put `<!-- ste-ignore -->` on the line before it. To skip a part of a file, put it between `<!-- ste-disable -->` and `<!-- ste-enable -->`.

## ste fix

`ste fix` makes a plan and does not change files. `ste fix --apply` applies only safe replacements. Use `--skip N,N` to keep some of them as they are, or `--only N,N` to apply only some of them. The numbers come from `ste fix`. They stay the same while the files do not change. A replacement is safe when all of these conditions are correct:

- The dictionary gives one alternative for the word.
- The alternative has the same part of speech.
- The word is in its base form.
- The position of the word agrees with its part of speech (for example, a verb after "to" or at the start of an instruction).

`ste fix --apply` also corrects "a" and "an" before the new word. It lists all other problems, sentence by sentence, with the alternatives and the STE examples. A person or a model must write those sentences again. Use `--format json` to give the list to a model.

## Claude Code

Install the plugin. It contains the `ste-simplify` skill and the script:

```text
/plugin marketplace add rmarinsky/ste-simplify
/plugin install ste-simplify@ste-simplify
```

Or put a copy of the files in your Claude folder:

```bash
cp -r skills/ste-simplify ~/.claude/skills/
```

The skill tells the model to run `ste fix` and to show the plan to you. After you give your approval, the model runs `ste fix --apply`, writes the flagged sentences again and runs `ste scan` until there are no errors. For skill files and agent files, the skill keeps the trigger phrases and the front matter keys.

To examine each Markdown file after Claude writes it, add the hook in `adapters/claude-code/settings.example.json` to your settings. The hook runs `ste_hook.py`. When the file has STE errors, the hook gives the report to Claude.

## Codex

Add the section in `adapters/codex/AGENTS.md` to the `AGENTS.md` file of your project, or to `~/.codex/AGENTS.md`. The section tells Codex to run `ste fix`, `ste fix --apply` and `ste scan` after it changes a document. If your Codex version can use skills, you can also put a copy of `skills/ste-simplify` in `~/.codex/skills/`.

## Cursor

Put a copy of `adapters/cursor/ste.mdc` in `.cursor/rules/` in your project. The rule tells the agent to run `ste fix`, `ste fix --apply` and `ste scan` in the terminal after it changes a Markdown file.

## Chat replies

Send the reply to the checker:

```bash
pbpaste | ste scan -
pbpaste | ste fix --apply - | pbcopy
```

## pre-commit

Use the example in `adapters/pre-commit-config.example.yaml`. The hook reads the dictionary from `~/.config/ste-simplify/dictionary.json.gz` or from `STE_DICTIONARY`.

## GitHub Actions

The repository is also a GitHub Action. Put a copy of `adapters/github/ste.yml` in `.github/workflows/`. On the runner, the action runs `ste prepare`. This command downloads the PDF from ASD and makes the dictionary for this run only. The workflow runs `ste scan` and sends a SARIF report to code scanning.

If the runner cannot get the PDF, give the dictionary in a repository secret. The `--lite` option removes the definitions and the examples. The result is smaller than the size limit of a secret:

```bash
ste prepare --lite -o ste-lite.json
gzip -9c ste-lite.json | base64 | gh secret set STE_DICTIONARY_B64
rm ste-lite.json
```

Then add `dictionary-b64: ${{ secrets.STE_DICTIONARY_B64 }}` to the `with` part of the workflow.

## Limits

The checker does not know the sense of a sentence. It finds the part of speech only from the word before. It cannot find an approved word with a sense that is not approved, for example "the house standard". The passive voice check and the instruction check can make errors. Thus, read the text after the checker shows no errors.

## Tests

```bash
cd tests && python3 -m unittest discover -s .
```

The tests use a small test dictionary (`tests/fixtures/mini-dictionary.json`). It is not from the STE specification. To do the builder test with the PDF from ASD, set `STE_PDF=/path/to/ASD-STE100.pdf`.

## License

The code has the MIT license. The STE dictionary and the ASD-STE100 specification are the property of ASD. ASD-STE100 is a trademark of ASD.
