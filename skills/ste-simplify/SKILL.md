---
name: ste-simplify
description: Change English text into Simplified Technical English (STE, compatible with ASD-STE100), and check it with a script. Use it for agent instructions, skills, prompts, specs, READMEs, docs and chat replies. Use it when the user writes "STE", "Simplified Technical English", "rewrite in STE", "make this simple English", "plain technical English", "check STE" or "ste-check". Also use it when a skill or an agent file must be clear for a model.
---

# Simplified Technical English

This skill changes English text into Simplified Technical English (STE). STE has a dictionary of approved words and a set of writing rules. Each approved word has only one sense. Thus, a model that reads STE text makes a smaller number of errors.

Scripts do the checks. You change only the sentences that the scripts show.

## Find the scripts

Use the first command that operates:

1. `ste-check` and `ste-fix` (installed with `pipx install git+https://github.com/rmarinsky/ste-simplify`).
2. `python3 <skill folder>/scripts/ste_check.py` and `python3 <skill folder>/scripts/ste_fix.py`. The skill folder is the folder of this file.

The scripts use a local dictionary. If a script shows "No STE dictionary found", stop. Tell the user to get the free STE PDF from https://www.asd-ste100.org. Then tell the user to run this command one time:

```bash
ste-build-dictionary /path/to/ASD-STE100.pdf
```

Do not write a word list. Do not get word lists from the web. The dictionary is the property of ASD.

## Procedure

1. Run the checker on the file or the folder:

   ```bash
   ste-check FILE
   ```

   For text that is not in a file, for example a chat reply, send the text to stdin:

   ```bash
   printf '%s\n' "$TEXT" | ste-check -
   ```

2. If the user lets you change the file, apply the safe replacements:

   ```bash
   ste-fix --apply FILE
   ```

   A safe replacement has one approved alternative with the same part of speech. The script does not change other words.

3. Get the list of sentences that you must write again:

   ```bash
   ste-fix --format json FILE
   ```

   Each item has the sentence, the problem words, the approved alternatives and an STE example sentence for each alternative.

4. Write each sentence in the list again. Use the alternatives and the rules in the table below. Do not change the information in the sentence. If an alternative changes the sense, use a different sentence construction.

5. Run `ste-check FILE` again. Do steps 3 to 5 again until the checker shows no errors.

6. Examine the warnings:
   - "Not in the dictionary": if the word is a technical name or a technical verb of the project, add it to `.ste-allow.txt` at the project root (one name on each line). If not, use an approved word.
   - "Possible passive voice": if you know who or which item does the step, write the sentence in the active voice.

7. Tell the user the changes that you made and the warnings that stay.

## Do not change these

- Code blocks, inline code, commands, flags, file paths, URLs and email addresses.
- Numbers, units, versions and dates.
- Names of products, persons, files and functions.
- Technical names and technical verbs from the allow-list.
- Text between quotation marks that a user types to start a skill (trigger phrases).
- Front matter keys, link targets and heading anchors that other files use.

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
| 5.3 | Write instructions as commands: "Run the checker." |
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
- Do not use words in a figurative sense. For example, do not write "the bar". Write the standard or the number.

To change many files, use the `ste-rewriter` agent if it is available.

## Limits of the scripts

The checker does not know the sense of a sentence. It cannot always find the part of speech. It also cannot find an approved word that has a sense that is not approved. Thus, read each sentence after the checker shows no errors.
