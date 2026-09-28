#!/usr/bin/env python3
"""
mem_dream — nightly hygiene ("dreaming") for the shared memory store. Cron, ~03:00.

AUTO-APPLIES only safe, mechanical fixes:
  * feed rotation  — _FEED.md keeps the last KEEP_FEED entries; older lines are MOVED
                     to memory/archive/_FEED-archive-<YYYY>.md (never lost)
  * index sync     — memory files missing from MEMORY.md get an additive bullet;
                     bullets pointing at missing files are removed from the index and
                     listed verbatim in the proposals file
  * [[link]] fixes — a broken [[slug]] is rewritten only when exactly one existing
                     slug is a near-certain rename (similarity >= 0.9)

Everything else becomes a PROPOSAL in memory/_DREAM_PROPOSALS.md for a human (or a
reviewed agent session) to act on: near-duplicates, remaining broken links, stale
entries, relative dates ("yesterday"), missing frontmatter.

Then rebuilds per-project briefs memory/briefs/<project>.md (<= BRIEF_MAX lines).
Projects are defined in memory/_PROJECTS.json: {"project": ["keyword", ...], ...}.
Optional --llm: only when the usage tier is GREEN, a bounded `claude -p --model haiku`
summary is prepended to briefs whose content changed (at most LLM_MAX per night).

Usage: mem_dream.py [--dry-run] [--llm] [--no-briefs]
"""
import argparse, datetime, difflib, glob, hashlib, json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A
import mem_core as M

MEM = M.MEM_DIR
ARCHIVE = os.path.join(MEM, "archive")
PROPOSALS = os.path.join(MEM, "_DREAM_PROPOSALS.md")
PROJECTS = os.path.join(MEM, "_PROJECTS.json")
STATE = os.path.join(A.STATE, "mem_dream_state.json")
KEEP_FEED, ROTATE_AT = 500, 550
STALE_DAYS, BRIEF_MAX, LLM_MAX = 60, 60, 4
NOW = datetime.datetime.now(datetime.timezone.utc)
LINK = re.compile(r"\[\[([a-z0-9_-]+)\]\]")
BULLET = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)")
applied, props = [], {}


def P(section, line):
    props.setdefault(section, []).append(line)


def load():
    E = {}
    for p in sorted(glob.glob(os.path.join(MEM, "*.md"))):
        base = os.path.basename(p)
        if not M.is_memory_file(base):
            continue
        try:
            d = M.parse(p)
        except Exception as e:
            P("Unreadable files", f"- `{base}`: {e}")
            continue
        with open(p) as f:
            d["has_fm"] = f.read(4) == "---\n"
        d["path"] = p
        try:
            d["when"] = datetime.datetime.strptime(d["updated"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
        except ValueError:
            d["when"] = datetime.datetime.fromtimestamp(os.path.getmtime(p), datetime.timezone.utc)
        E[d["slug"]] = d
    return E


def rotate_feed(dry):
    if not os.path.exists(M.FEED):
        return
    with M._Lock():
        lines = open(M.FEED).read().splitlines()
        idx = [i for i, l in enumerate(lines) if l.startswith("- ")]
        if len(idx) <= ROTATE_AT:
            return
        cut = idx[-KEEP_FEED]
        head, old, keep = lines[:idx[0]], [l for l in lines[idx[0]:cut] if l.strip()], lines[cut:]
        if dry:
            applied.append(f"(dry) would archive {len(old)} feed lines")
            return
        os.makedirs(ARCHIVE, exist_ok=True)
        arc = os.path.join(ARCHIVE, f"_FEED-archive-{NOW:%Y}.md")
        with open(arc, "a") as f:
            f.write("\n".join(old) + "\n")
        tmp = M.FEED + ".tmp"
        with open(tmp, "w") as f:
            f.write("\n".join(head + keep).rstrip() + "\n")
        os.replace(tmp, M.FEED)
        applied.append(f"archived {len(old)} old feed lines (kept last {KEEP_FEED})")


def index_sync(E, dry):
    if not os.path.exists(M.INDEX):
        if not dry:
            with M._Lock():
                for s, d in E.items():
                    M.upsert_index(s, d["description"])
        applied.append(f"created index with {len(E)} entries")
        return
    with M._Lock():
        lines = open(M.INDEX).read().splitlines()
        keep, removed, linked = [], [], set()
        for l in lines:
            m = BULLET.match(l)
            if not m or m.group(2).startswith(("http", "../", "/")):
                keep.append(l)
                continue
            target = m.group(2)
            if os.path.exists(os.path.join(MEM, target)):
                linked.add(target[:-3] if target.endswith(".md") else target)
                keep.append(l)
            else:
                removed.append(l)
        for l in removed:
            P("Index: removed bullets whose file is missing (re-add if wanted)", f"    {l}")
        missing = [s for s in E if s not in linked]
        if dry:
            if removed or missing:
                applied.append(f"(dry) would drop {len(removed)} broken bullets, add {len(missing)} missing")
            return
        if removed:
            with open(M.INDEX, "w") as f:
                f.write("\n".join(keep).rstrip() + "\n")
            applied.append(f"removed {len(removed)} broken index bullet(s) (listed in proposals)")
        for s in missing:
            M.upsert_index(s, E[s]["description"])
        if missing:
            applied.append(f"added {len(missing)} missing index bullet(s): {', '.join(missing[:8])}")


def fix_links(E, dry):
    slugs = list(E)
    for s, d in E.items():
        body = open(d["path"]).read()
        new = body
        for target in sorted(set(LINK.findall(body))):
            if target in E:
                continue
            close = [c for c in slugs if difflib.SequenceMatcher(None, target, c).ratio() >= 0.9]
            if len(close) == 1:
                new = new.replace(f"[[{target}]]", f"[[{close[0]}]]")
                applied.append(f"{s}: [[{target}]] -> [[{close[0]}]]")
            else:
                P("Broken [[links]]", f"- `{s}` links to missing [[{target}]]")
        if new != body and not dry:
            with M._Lock():
                with open(d["path"], "w") as f:
                    f.write(new)


def toks(s):
    return {t for t in re.findall(r"[a-z0-9]{3,}", s.lower())}


def proposals(E):
    items = list(E.values())
    for i, a in enumerate(items):
        ta = toks(a["slug"] + " " + a["description"])
        for b in items[i + 1:]:
            tb = toks(b["slug"] + " " + b["description"])
            if ta and tb and len(ta & tb) / len(ta | tb) >= 0.6:
                P("Possible duplicates (merge?)", f"- `{a['slug']}` ~ `{b['slug']}`")
    for d in items:
        age = (NOW - d["when"]).days
        if age >= STALE_DAYS:
            P("Stale (review, update or archive)", f"- `{d['slug']}` last updated {age} days ago")
        if not d["has_fm"]:
            P("Missing frontmatter", f"- `{d['slug']}` (rewrite with `mem write`)")
        if re.search(r"\b(yesterday|today|tomorrow|last week|next week)\b", d["body"], re.I):
            P("Relative dates (convert to absolute)", f"- `{d['slug']}`")


def build_briefs(E, dry):
    try:
        cfg = json.load(open(PROJECTS))
        assert isinstance(cfg, dict)
    except Exception:
        return []
    written = []
    os.makedirs(M.BRIEF_DIR, exist_ok=True)
    for proj, kws in cfg.items():
        kws = [k.lower() for k in kws] or [proj.lower()]
        hits = [d for d in E.values()
                if any(k in f"{d['slug']} {d['description']}".lower() for k in kws)]
        hits.sort(key=lambda d: d["when"], reverse=True)
        lines = [f"# Brief: {proj}", f"_rebuilt {NOW:%Y-%m-%d} by mem_dream from {len(hits)} memories (newest first)_", ""]
        for d in hits[:BRIEF_MAX - 4]:
            lines.append(f"- **{d['slug']}** ({d['when']:%Y-%m-%d}) — {d['description']}")
        text = "\n".join(lines[:BRIEF_MAX]) + "\n"
        path = os.path.join(M.BRIEF_DIR, f"{M.clean_slug(proj)}.md")
        old = open(path).read() if os.path.exists(path) else ""
        if re.sub(r"_rebuilt.*_", "", old.split("\n## Summary")[0]) != re.sub(r"_rebuilt.*_", "", text):
            written.append((proj, path, hits))
        if not dry:
            with open(path, "w") as f:
                f.write(text)
    applied.append(f"rebuilt {len(cfg)} brief(s), {len(written)} changed")
    return written


def llm_pass(written, dry):
    try:
        tier = json.load(open(os.path.join(A.STATE, "usage_tier.json"))).get("tier")
    except Exception:
        tier = None
    if tier != "GREEN":
        applied.append(f"llm summaries skipped (tier {tier or 'unknown'})")
        return
    try:
        st = json.load(open(STATE))
    except Exception:
        st = {}
    done = 0
    for proj, path, hits in written:
        if done >= LLM_MAX:
            break
        src = "\n\n".join(f"## {d['slug']}\n{d['description']}\n{d['body'][:1200]}" for d in hits[:12])
        h = hashlib.sha1(src.encode()).hexdigest()
        if st.get(proj) == h or dry:
            continue
        prompt = ("Summarize the current state of this project for another AI agent in <= 8 plain bullet "
                  "points: what exists, what is live, open problems, traps. No preamble.\n\n" + src)
        try:
            r = subprocess.run(["claude", "-p", "--model", "haiku", "--max-turns", "1", "--tools", ""],
                               input=prompt, capture_output=True, text=True, timeout=180, cwd=A.STATE)
            if r.returncode == 0 and r.stdout.strip():
                with open(path) as f:
                    base = f.read()
                with open(path, "w") as f:
                    f.write(base.rstrip() + "\n\n## Summary (auto, haiku)\n" + r.stdout.strip() + "\n")
                st[proj] = h
                done += 1
        except Exception as e:
            P("LLM pass errors", f"- {proj}: {e}")
    A.atomic_json(STATE, st)
    applied.append(f"llm summaries written: {done}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--no-briefs", action="store_true")
    a = ap.parse_args()
    os.makedirs(MEM, exist_ok=True)
    rotate_feed(a.dry_run)
    E = load()
    index_sync(E, a.dry_run)
    fix_links(E, a.dry_run)
    E = load()
    proposals(E)
    if not a.no_briefs:
        written = build_briefs(E, a.dry_run)
        if a.llm and written:
            llm_pass(written, a.dry_run)
    out = [f"# Dream proposals — {NOW:%Y-%m-%d %H:%M} UTC", "",
           "Nothing here was changed automatically. Act on what is right; ignore the rest.", "",
           "## Applied automatically", *([f"- {x}" for x in applied] or ["- nothing"]), ""]
    for sec, ls in props.items():
        out += [f"## {sec}", *ls[:60], ""]
    if a.dry_run:
        print("\n".join(out))
    else:
        with open(PROPOSALS, "w") as f:
            f.write("\n".join(out))
        M.log(f"mem_dream: {len(applied)} auto-fixes, {sum(len(v) for v in props.values())} proposals", "mem-dream")
        print(f"dream done: {len(applied)} applied, {sum(len(v) for v in props.values())} proposals")


if __name__ == "__main__":
    main()
