---
name: ste-simplify
description: Change English text into Simplified Technical English (STE, compatible with ASD-STE100), and check it with a script. Use it for skills, agent files, prompts, specs, READMEs, docs and chat replies. Use it when the user writes "STE", "Simplified Technical English", "rewrite in STE", "simplify this", "make this simple English", "check STE" or "ste scan". Also use it when a skill or an agent file must be clear for a model.
---

# Simplified Technical English

This skill changes English text into Simplified Technical English (STE). STE has a dictionary of approved words and a set of writing rules. Each approved word has only one sense. Thus, a model that reads STE text makes a smaller number of errors.

The script finds the problems and makes a plan. The user examines the plan. You change only the sentences that the script shows.

## Find the script

Use the first command that operates:

1. `ste` (installed with `pipx install git+https://github.com/rmarinsky/ste-simplify`).
2. `python3 <skill folder>/scripts/ste.py`. The skill folder is the folder of this file.

The script uses a local dictionary. If the script shows "No STE dictionary found", tell the user that you will make it. Then run this command one time:

```bash
ste prepare
```

The command downloads the PDF from the ASD web site to the computer of the user, and makes the dictionary from it. If the command does not operate, tell the user to request a free copy on https://www.asd-ste100.org/STE_downloads.html, and to run `ste prepare --pdf /path/to/the.pdf`.

Do not write a word list. Do not get word lists from the web. The dictionary is the property of ASD.

## Procedure

1. Make the plan:

   ```bash
   ste fix FILE
   ```

   For text that is not in a file, for example a chat reply, send the text to stdin: `printf '%s\n' "$TEXT" | ste fix -`.

   The plan has two parts:
   - Safe replacements, with numbers. A safe replacement has one approved alternative with the same part of speech.
   - Sentences to write again, with the problem words, the approved alternatives and an STE example for each alternative.

2. Show the plan to the user. Show the safe replacements and, for each sentence, the new sentence that you write. Then stop and wait for the answer of the user.

3. Use the answer of the user:
   - For safe replacements that the user does not want, write their numbers in `--skip`.
   - If the user tells you that a word is a technical name of the project, add it to `.ste-allow.txt`. Put this file at the project root, with one name on each line.
   - If the user changes one of your sentences, use the sentence of the user.

4. Apply the safe replacements that the user approved:

   ```bash
   ste fix --apply --skip 2,5 FILE
   ```

   If the user approved all of them, do not use `--skip`. If the user approved only some of them, use `--only 1,3`.

5. Write the approved sentences into the file. Do not change other text.

6. Examine the result:

   ```bash
   ste scan FILE
   ```

   If the check shows errors, do steps 1 to 6 again for these errors only.

7. Tell the user the changes that you made and the warnings that stay.

If the user tells you to do all of the changes without a review, do not stop at step 2.

## Do not change these

- Code blocks, inline code, commands, flags, file paths, URLs and email addresses.
- Numbers, units, versions and dates.
- Names of products, persons, skills, agents, tools, files and functions.
- Technical names and technical verbs from the allow-list.
- Text between quotation marks that a user types to start a skill (trigger phrases).
- Front matter keys, the `name` value, the `tools` value, link targets and heading anchors that other files use.

## Writing rules

| Rule | Do this |
|---|---|
| 1.1 to 1.4 | Use only approved words. Use each word only with its approved sense, part of speech and forms. |
| 1.5, 1.12 | You can use technical names and technical verbs of your project. |
| 3.5 | Do not use the -ing form of a verb. You can use it only in a technical name. |
| 3.6 | Use the active voice. |
| 4.2 | Do not use contractions. Do not remove words to make a sentence shorter. |
| 5.1 | An instruction has a maximum of 20 words. |
| 5.2 | Write one instruction in each sentence, unless the steps occur at the same time. |
| 5.3 | Write instructions as commands: "Run the check." |
| 5.4 | Put a condition first: "If the test fails, do the steps again." |
| 6.3 | A descriptive sentence has a maximum of 25 words. |
| 6.6 | A paragraph has a maximum of six sentences. |
| 8.1 | Do not use a semicolon. |

Text in parentheses counts as one word. A hyphenated word counts as one word. A number with its unit counts as one word.

## Skill and agent files

For `SKILL.md` files, agent files and other instructions for models:

- Write the `description` value in the front matter again. Keep its trigger phrases.
- Write each instruction as a command, with one instruction in each sentence.
- Use one word for one item. Do not use different words for the same item.
- Do not use words in a figurative sense, for example "the bar" or "the house standard". Write the standard, the number or the file name.
- Write "must" for a rule. Do not write "should".
- Keep the sequence of the steps.
- After the check, read the full file again. Make sure that each instruction has the same result as before.

For many files, show one plan for all of the files in step 2. Then do steps 4 to 6 for each file.

## Limits of the script

The script does not know the sense of a sentence. It cannot always find the part of speech. It also cannot find an approved word that has a sense that is not approved. Thus, read each sentence after the check shows no errors.
