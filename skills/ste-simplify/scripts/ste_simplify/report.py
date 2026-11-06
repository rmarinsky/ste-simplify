"""The two-part report: a short table in the terminal, and a detailed HTML page.

The HTML page shows each safe replacement in its line (old word and new word),
each sentence to write again with the problem words marked, and the words that
are not in the dictionary. Check boxes make the `ste fix --apply` command and the
allow-list text. The page has no external files and no network access.

The page contains parts of your local dictionary. Thus it goes to the cache
folder (not into the project), and you must not publish it.
"""
import collections
import datetime
import html
import json
import os
import re
import shlex
import webbrowser


def cache_dir():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "ste-simplify")


WORD_RULES = ("not-approved", "wrong-pos", "wrong-form", "ing-form")
RULE_NAMES = {
    "not-approved": "Not approved", "wrong-pos": "Part of speech", "wrong-form": "Form",
    "ing-form": "-ing form", "sentence-length": "Sentence length", "paragraph-length": "Paragraph length",
    "passive-voice": "Passive voice", "one-instruction": "One instruction", "semicolon": "Semicolon",
    "contraction": "Contraction",
}


def esc(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def default_path():
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(cache_dir(), "reports", f"ste-report-{stamp}.html")


def summarize(results, plan):
    safe = collections.Counter(p["path"] for p in plan if p.get("replacement"))
    rows = []
    for path, fs in results:
        e = sum(f.severity == "error" for f in fs)
        w = sum(f.severity == "warning" for f in fs)
        sentences = {f.sentence or f"line {f.line}" for f in fs if f.rule != "unknown-word"}
        rows.append({"path": path, "errors": e, "warnings": w, "safe": safe[path], "sentences": len(sentences)})
    return rows


def table(rows, out, limit=40):
    """Print the short table for the terminal."""
    show = sorted(rows, key=lambda r: (-r["errors"], r["path"]))
    width = min(max([len(r["path"]) for r in show] + [4]), 70)
    head = f"{'File':<{width}}  {'Errors':>6}  {'Warnings':>8}  {'Safe':>4}  {'Sentences':>9}"
    out.write(head + "\n" + "-" * len(head) + "\n")
    for r in show[:limit]:
        p = r["path"] if len(r["path"]) <= width else "..." + r["path"][-(width - 3):]
        out.write(f"{p:<{width}}  {r['errors']:>6}  {r['warnings']:>8}  {r['safe']:>4}  {r['sentences']:>9}\n")
    if len(show) > limit:
        out.write(f"... {len(show) - limit} more files in the HTML report\n")
    t = {k: sum(r[k] for r in rows) for k in ("errors", "warnings", "safe", "sentences")}
    out.write("-" * len(head) + "\n")
    out.write(f"{'Total (' + str(len(rows)) + (' file)' if len(rows) == 1 else ' files)'):<{width}}  {t['errors']:>6}  {t['warnings']:>8}  "
              f"{t['safe']:>4}  {t['sentences']:>9}\n")


def mark_words(sentence, words):
    """Mark the problem words in a sentence. Each word gets the title text of its finding."""
    s = esc(sentence)
    for w, title, cls in words:
        if not w:
            continue
        pat = re.compile(r"(?<![\w-])(" + re.escape(esc(w)) + r")(?![\w-])")
        s = pat.sub(lambda m: f'<mark class="{cls}" title="{esc(title)}">{m.group(1)}</mark>', s, count=1)
    return s


def alt_html(data):
    parts = []
    for g in (data or {}).get("alternatives", [])[:4]:
        alt = ", ".join(a["text"] + (f" ({a['pos']})" if a.get("pos") else "") for a in g["alternatives"]) \
            or "No direct alternative"
        ex = g.get("ste_example")
        parts.append(f'<li><span class="alt">{esc(alt)}</span>'
                     + (f'<span class="ex">{esc(ex)}</span>' if ex else "") + "</li>")
    for h in (data or {}).get("help", []):
        parts.append(f'<li><span class="ex">Help: {esc(h)}</span></li>')
    return f'<ul class="alts">{"".join(parts)}</ul>' if parts else ""


def alt_title(f):
    d = f.data or {}
    alts = [a["text"] + (f" ({a['pos']})" if a.get("pos") else "") for g in d.get("alternatives", []) for a in g["alternatives"]]
    if alts:
        return "Use: " + ", ".join(dict.fromkeys(alts))
    if d.get("forms"):
        return "Approved forms: " + ", ".join(d["forms"])
    return f.message


def render(results, plan, rewrite, paths, texts, meta):
    rows = summarize(results, plan)
    tot = {k: sum(r[k] for r in rows) for k in ("errors", "warnings", "safe", "sentences")}
    by_file_safe = collections.defaultdict(list)
    for p in plan:
        if p.get("replacement"):
            by_file_safe[p["path"]].append(p)
    by_file_rw = collections.defaultdict(list)
    for g in rewrite:
        probs = [f for f in g["problems"] if f.rule != "unknown-word"]
        if probs:
            by_file_rw[g["path"]].append((g, probs))
    unknown = collections.defaultdict(collections.Counter)
    for path, fs in results:
        for f in fs:
            if f.rule == "unknown-word":
                unknown[path][f.key] += 1
    many = len(results) > 8
    body = []
    rows_sorted = sorted(rows, key=lambda r: (-r["errors"], r["path"]))
    body.append('<table class="files"><thead><tr><th>File</th><th class="n">Errors</th><th class="n">Warnings</th>'
                '<th class="n">Safe</th><th class="n">Sentences</th></tr></thead><tbody>')
    for i, r in enumerate(rows_sorted):
        body.append(f'<tr data-path="{esc(r["path"])}"><td><a href="#f{i}">{esc(r["path"])}</a></td>'
                    f'<td class="n">{r["errors"]}</td><td class="n">{r["warnings"]}</td>'
                    f'<td class="n">{r["safe"]}</td><td class="n">{r["sentences"]}</td></tr>')
    body.append("</tbody></table>")
    for i, r in enumerate(rows_sorted):
        path = r["path"]
        lines = texts.get(path, "").split("\n")
        open_attr = "" if many and i > 0 else " open"
        sec = [f'<details class="file" id="f{i}" data-path="{esc(path)}"{open_attr}><summary>'
               f'<span class="path">{esc(path)}</span>'
               f'<span class="sub">{r["errors"]} errors, {r["warnings"]} warnings</span></summary>']
        safe = sorted(by_file_safe.get(path, []), key=lambda p: p["id"])
        if safe:
            sec.append('<h3>Safe replacements</h3><p class="sub">Clear a check box to keep the old word. '
                       'The command at the top changes when you do this.</p>'
                       '<table class="safe"><thead><tr><th></th><th class="n">No.</th><th class="n">Line</th>'
                       '<th>Change</th></tr></thead><tbody>')
            for p in safe:
                ln = lines[p["line"] - 1] if 0 < p["line"] <= len(lines) else ""
                c = p["col"] - 1
                if ln[c:c + len(p["word"])] == p["word"]:
                    change = (esc(ln[:c].lstrip()[-80:]) + f'<del>{esc(p["word"])}</del><ins>{esc(p["replacement"])}</ins>'
                              + esc(ln[c + len(p["word"]):][:80]))
                else:
                    change = f'<del>{esc(p["word"])}</del><ins>{esc(p["replacement"])}</ins>'
                sec.append(f'<tr><td><input type="checkbox" class="keep" data-id="{p["id"]}" checked '
                           f'aria-label="Apply replacement {p["id"]}"></td><td class="n id">{p["id"]}</td>'
                           f'<td class="n">{p["line"]}</td><td class="change">{change}</td></tr>')
            sec.append("</tbody></table>")
        rw = by_file_rw.get(path, [])
        if rw:
            sec.append(f'<h3>Sentences to write again</h3>')
            for g, probs in sorted(rw, key=lambda x: x[0]["line"]):
                words = [(f.word, alt_title(f), "w-" + f.rule) for f in probs if f.word and f.rule in WORD_RULES]
                rules = " ".join(sorted({f.rule for f in probs}))
                sev = "error" if any(f.severity == "error" for f in probs) else "warning"
                text = g["sentence"] or (lines[g["line"] - 1].strip() if 0 < g["line"] <= len(lines) else "")
                sec.append(f'<div class="sent" data-rules="{rules}" data-sev="{sev}">'
                           f'<div class="line">Line {g["line"]}</div>'
                           f'<blockquote>{mark_words(text, words)}</blockquote><ul class="probs">')
                for f in probs:
                    head = RULE_NAMES.get(f.rule, f.rule)
                    sec.append(f'<li data-rule="{f.rule}" data-sev="{f.severity}"><span class="rule {f.severity}">'
                               f'{esc(head)}</span> {esc(f.message)}'
                               + (alt_html(f.data) if f.rule in ("not-approved", "wrong-pos") else "") + "</li>")
                sec.append("</ul></div>")
        unk = unknown.get(path)
        if unk:
            sec.append('<h3>Not in the dictionary</h3><p class="sub">Select the technical names of your project. '
                       'The allow-list at the top shows the selected words.</p><div class="unk">')
            for w, n in sorted(unk.items(), key=lambda x: (-x[1], x[0])):
                sec.append(f'<label><input type="checkbox" class="allow" value="{esc(w)}"> {esc(w)}'
                           + (f' <span class="sub">{n}</span>' if n > 1 else "") + "</label>")
            sec.append("</div>")
        if not (safe or rw or unk):
            sec.append('<p class="sub">No problems.</p>')
        sec.append("</details>")
        body.append("".join(sec))
    rule_opts = "".join(f'<option value="{k}">{esc(v)}</option>' for k, v in RULE_NAMES.items())
    cmd = {"paths": paths}
    return PAGE.format(
        title="STE report", when=esc(meta["when"]), files_text=f"{len(rows)} file" + ("" if len(rows) == 1 else "s"),
        errors=tot["errors"],
        warnings=tot["warnings"], safe=tot["safe"], sentences=tot["sentences"],
        dictionary=esc(meta.get("dictionary", "")), rule_opts=rule_opts, body="\n".join(body),
        cmd_json=json.dumps(cmd).replace("</", "<\\/"),
        cmd=esc("ste fix --apply " + " ".join(shlex.quote(p) for p in paths)))


def write(results, plan, rewrite, paths, texts, meta, out=None, open_it=True):
    out = out or default_path()
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(render(results, plan, rewrite, paths, texts, meta))
    if open_it:
        webbrowser.open(_uri(out))
    return out


def _uri(path):
    from pathlib import Path
    return Path(os.path.abspath(path)).as_uri()


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --text:#1c1c1e; --muted:#62636a; --bg:#ffffff; --surface:#f4f4f5; --line:#e2e2e5;
  --accent:#1f5f8b; --del:#b3261e; --del-bg:#fbe9e7; --ins:#1e6b3a; --ins-bg:#e6f4ea; --mark:#fff1c2; }}
@media (prefers-color-scheme: dark) {{ :root {{ --text:#ececee; --muted:#a1a1a8; --bg:#18181a; --surface:#232326;
  --line:#34343a; --accent:#7fb3d8; --del:#f2b8b5; --del-bg:#3b1f1d; --ins:#a8dab5; --ins-bg:#1d3324; --mark:#4a3f12; }} }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--bg); color:var(--text);
  font:15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:32px 24px 80px; }}
h1 {{ font-size:28px; font-weight:600; margin:0 0 4px; }}
h2 {{ font-size:20px; font-weight:600; margin:32px 0 8px; }}
h3 {{ font-size:15px; font-weight:600; margin:24px 0 4px; }}
p {{ margin:4px 0; }}
.sub, .line {{ color:var(--muted); font-size:13px; }}
a {{ color:var(--accent); }}
code, .cmd, .id {{ font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:13px; }}
.n {{ text-align:right; font-variant-numeric:tabular-nums; }}
.tools {{ display:grid; grid-template-columns:1fr 1fr; gap:24px; margin:24px 0; }}
.tools label {{ font-size:13px; color:var(--muted); display:block; margin-bottom:4px; }}
.cmd, textarea {{ width:100%; background:var(--surface); color:var(--text); border:0; border-radius:6px;
  padding:10px 12px; font-family:ui-monospace, SFMono-Regular, Menlo, monospace; font-size:13px; }}
.cmd {{ word-break:break-all; min-height:42px; }}
textarea {{ min-height:42px; resize:vertical; }}
button {{ margin-top:6px; font:inherit; font-size:13px; padding:4px 12px; border-radius:6px;
  border:1px solid var(--line); background:var(--bg); color:var(--text); cursor:pointer; }}
.filters {{ display:flex; flex-wrap:wrap; gap:16px; align-items:center; margin:8px 0 16px; font-size:13px; }}
select, input[type=search] {{ font:inherit; padding:4px 8px; border-radius:6px; border:1px solid var(--line);
  background:var(--bg); color:var(--text); }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th {{ text-align:left; font-weight:600; color:var(--muted); padding:6px 8px; border-bottom:1px solid var(--line); }}
td {{ padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }}
table.files td:first-child {{ word-break:break-all; }}
details.file {{ margin-top:28px; }}
details.file > summary {{ cursor:pointer; font-size:20px; font-weight:600; list-style-position:outside; }}
details.file > summary .path {{ word-break:break-all; }}
details.file > summary .sub {{ font-weight:400; margin-left:12px; }}
td.change {{ font-family:ui-monospace, SFMono-Regular, Menlo, monospace; white-space:pre-wrap; word-break:break-word; }}
del {{ color:var(--del); background:var(--del-bg); text-decoration:line-through; padding:0 2px; border-radius:3px; }}
ins {{ color:var(--ins); background:var(--ins-bg); text-decoration:none; padding:0 2px; border-radius:3px; }}
tr.off ins {{ display:none; }}
tr.off del {{ text-decoration:none; color:var(--text); background:none; }}
.sent {{ margin:16px 0 0; }}
blockquote {{ margin:2px 0 6px; padding:8px 12px; background:var(--surface); border-radius:6px; }}
mark {{ background:var(--mark); color:inherit; padding:0 2px; border-radius:3px; cursor:help; }}
ul.probs {{ margin:0; padding-left:18px; }}
ul.probs > li {{ margin:4px 0; }}
.rule {{ font-weight:600; }}
.rule.error {{ color:var(--del); }}
ul.alts {{ margin:2px 0 0; padding-left:16px; color:var(--muted); font-size:13px; }}
.alt {{ color:var(--text); font-weight:600; margin-right:8px; }}
.unk {{ display:flex; flex-wrap:wrap; gap:4px 20px; font-size:13px; }}
.hide {{ display:none !important; }}
footer {{ margin-top:48px; color:var(--muted); font-size:13px; }}
@media (max-width:720px) {{ .tools {{ grid-template-columns:1fr; }} main {{ padding:20px 16px 60px; }} }}
</style>
</head>
<body>
<main>
<h1>STE report</h1>
<p class="sub">{when}. Dictionary: {dictionary}</p>
<p>{files_text}: {errors} errors and {warnings} warnings. {safe} safe replacements and {sentences} sentences to write again.</p>

<div class="tools">
  <div>
    <label>Command to apply the selected safe replacements</label>
    <div class="cmd" id="cmd">{cmd}</div>
    <button type="button" data-copy="cmd">Copy</button>
  </div>
  <div>
    <label for="allow">Lines for .ste-allow.txt (select words in "Not in the dictionary")</label>
    <textarea id="allow" readonly placeholder="No words selected"></textarea>
    <button type="button" data-copy="allow">Copy</button>
  </div>
</div>

<h2>Files</h2>
<div class="filters">
  <label>Rule <select id="rule"><option value="">All rules</option>{rule_opts}</select></label>
  <label><input type="checkbox" id="warn" checked> Show warnings</label>
  <label>File <input type="search" id="q" placeholder="Part of a path"></label>
</div>
{body}
<footer>This page is on your computer only. It contains parts of your local ASD-STE100 dictionary. ASD has the copyright of the dictionary. Do not publish or share this page.</footer>
</main>
<script type="application/json" id="data">{cmd_json}</script>
<script>
(function () {{
  var data = JSON.parse(document.getElementById('data').textContent);
  function q(s) {{ return /^[\\w@%+=:,./-]+$/.test(s) ? s : "'" + s.replace(/'/g, "'\\\\''") + "'"; }}
  function update() {{
    var off = [], all = document.querySelectorAll('input.keep');
    all.forEach(function (b) {{ b.closest('tr').classList.toggle('off', !b.checked); if (!b.checked) off.push(b.dataset.id); }});
    var on = all.length - off.length, cmd = 'ste fix --apply ';
    if (off.length && on === 0) cmd = '# No replacements selected';
    else cmd += (off.length ? '--skip ' + off.join(',') + ' ' : '') + data.paths.map(q).join(' ');
    document.getElementById('cmd').textContent = cmd;
    var words = [];
    document.querySelectorAll('input.allow:checked').forEach(function (b) {{ if (words.indexOf(b.value) < 0) words.push(b.value); }});
    document.getElementById('allow').value = words.join('\\n');
  }}
  function filter() {{
    var rule = document.getElementById('rule').value, warn = document.getElementById('warn').checked,
        text = document.getElementById('q').value.toLowerCase();
    document.querySelectorAll('[data-path]').forEach(function (el) {{
      el.classList.toggle('hide', text !== '' && el.dataset.path.toLowerCase().indexOf(text) < 0);
    }});
    document.querySelectorAll('ul.probs > li').forEach(function (li) {{
      li.classList.toggle('hide', (rule && li.dataset.rule !== rule) || (!warn && li.dataset.sev === 'warning'));
    }});
    document.querySelectorAll('.sent').forEach(function (s) {{
      s.classList.toggle('hide', s.querySelectorAll('ul.probs > li:not(.hide)').length === 0);
    }});
    if (rule) document.querySelectorAll('details.file').forEach(function (d) {{ d.open = true; }});
  }}
  document.addEventListener('change', function (e) {{
    if (e.target.matches('input.keep, input.allow')) update();
    if (e.target.matches('#rule, #warn')) filter();
  }});
  document.getElementById('q').addEventListener('input', filter);
  function openTarget() {{ var d = document.getElementById(location.hash.slice(1)); if (d && d.tagName === 'DETAILS') d.open = true; }}
  window.addEventListener('hashchange', openTarget); openTarget();
  document.querySelectorAll('button[data-copy]').forEach(function (b) {{
    b.addEventListener('click', function () {{
      var el = document.getElementById(b.dataset.copy), t = el.value !== undefined ? el.value : el.textContent;
      navigator.clipboard.writeText(t).then(function () {{ b.textContent = 'Copied'; setTimeout(function () {{ b.textContent = 'Copy'; }}, 1200); }});
    }});
  }});
  update();
}})();
</script>
</body>
</html>
"""


def add_args(ap):
    ap.add_argument("--html", action="store_true",
                    help="print a short table and write a detailed HTML report, then open it in the browser")
    ap.add_argument("--html-out", metavar="FILE", help="where to write the HTML report (default: the cache folder)")
    ap.add_argument("--no-open", action="store_true", help="with --html: do not open the browser")


def emit(a, results, plan, rewrite, dict_path, stdin_text=None, out=None):
    """Print the table and write the HTML report. Return the report path."""
    import sys
    out = out or sys.stdout
    texts = {}
    for path, _ in results:
        if path == "-":
            texts[path] = stdin_text or ""
            continue
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                texts[path] = f.read()
        except OSError:
            texts[path] = ""
    table(summarize(results, plan), out)
    meta = {"when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "dictionary": dict_path or ""}
    path = write(results, plan, rewrite, list(a.paths), texts, meta, a.html_out, not a.no_open)
    out.write(f"\nHTML report: {_uri(path)}\n")
    out.write("The report contains parts of your local STE dictionary. Do not publish it.\n")
    return path
