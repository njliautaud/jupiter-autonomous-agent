"""
mem_core — engine of the shared memory bus (one brain for every agent).

Store: $AGENT_HOME/memory/<slug>.md (frontmatter + body) plus MEMORY.md (index).
Every agent reaches the store ONLY through this module:
  - local sessions and subagents -> `mem` CLI (bin/mem)
  - remote agents                -> HTTP API  (bin/mem_server.py)

Guarantees:
  * concurrency-safe (flock) — parallel tabs/agents never clobber each other
  * every write is stamped with author + UTC time and mirrored into an append-only
    activity feed (_FEED.md) so no agent is surprised by another agent's work
  * the index is maintained ADDITIVELY (one bullet upserted in place) — never
    regenerated or re-sorted, so hand-curated ordering survives
  * search = SQLite FTS5 (porter stemming + prefix, BM25 with slug/name/description
    boosted over body), falling back to a substring scan if FTS5 is unavailable
"""
import os, re, sys, fcntl, glob, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentlib as A

MEM_DIR = A.MEMORY
INDEX = os.path.join(MEM_DIR, "MEMORY.md")
FEED = os.path.join(MEM_DIR, "_FEED.md")
LOCK = os.path.join(MEM_DIR, ".mem.lock")
BRIEF_DIR = os.path.join(MEM_DIR, "briefs")
FTS_DB = os.path.join(MEM_DIR, ".mem_fts.sqlite")
FTS_LOCK = os.path.join(MEM_DIR, ".mem_fts.lock")
VALID_TYPES = {"user", "feedback", "project", "reference"}
_W_SLUG, _W_NAME, _W_DESC, _W_BODY = 8.0, 6.0, 4.0, 1.0


def _now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class _Lock:
    """Cross-process advisory lock."""
    def __enter__(self):
        os.makedirs(MEM_DIR, exist_ok=True)
        self.fd = open(LOCK, "w")
        fcntl.flock(self.fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *a):
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        self.fd.close()


def clean_slug(slug):
    return re.sub(r"[^a-z0-9_-]", "-", (slug or "").lower()).strip("-")[:120]


def _slug_path(slug):
    slug = clean_slug(slug)
    if not slug:
        raise ValueError("empty slug")
    return slug, os.path.join(MEM_DIR, f"{slug}.md")


def is_memory_file(base):
    """Real entries only: not the index, not _FEED / _DREAM_* / _IDEAS system files."""
    return base.endswith(".md") and base != "MEMORY.md" and not base.startswith("_")


def parse(path):
    with open(path) as f:
        txt = f.read()
    fm, body = {}, txt
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", txt, re.S)
    if m:
        raw, body = m.group(1), m.group(2).lstrip("\n")
        for line in raw.splitlines():
            m2 = re.match(r"\s+type:\s*(.+)", line)
            if m2:
                fm["type"] = m2.group(1).strip()
            elif ":" in line and not line.startswith(" "):
                k, v = line.split(":", 1)
                v = v.strip()
                if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                    v = v[1:-1]
                fm[k.strip()] = v
    slug = os.path.splitext(os.path.basename(path))[0]
    if not fm.get("description"):
        h1 = re.match(r"#\s+(.+)", body.lstrip())
        if h1:
            fm["description"] = h1.group(1).strip()
    return {"slug": slug, "name": fm.get("name", slug), "description": fm.get("description", ""),
            "type": fm.get("type", ""), "author": fm.get("author", ""),
            "updated": fm.get("updated", ""), "body": body.strip()}


def read(slug):
    try:
        _, path = _slug_path(slug)
    except ValueError:
        return None
    return parse(path) if os.path.exists(path) else None


def list_all():
    out = []
    for p in sorted(glob.glob(os.path.join(MEM_DIR, "*.md"))):
        if not is_memory_file(os.path.basename(p)):
            continue
        try:
            d = parse(p)
            out.append({k: d[k] for k in ("slug", "name", "description", "type", "author", "updated")})
        except Exception:
            pass
    return out


# ------------------------------------------------------------------ search
def _search_scan(query, limit=12):
    terms = [t for t in re.split(r"\s+", query.lower()) if t]
    scored = []
    for p in sorted(glob.glob(os.path.join(MEM_DIR, "*.md"))):
        if not is_memory_file(os.path.basename(p)):
            continue
        try:
            d = parse(p)
        except Exception:
            continue
        hay = f"{d['name']} {d['description']} {d['body']}".lower()
        head = f"{d['name']} {d['slug']} {d['description']}".lower()
        score = sum(hay.count(t) + 4 * head.count(t) for t in terms)
        if score:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [{"slug": d["slug"], "name": d["name"], "description": d["description"],
             "type": d["type"], "score": s} for s, d in scored[:limit]]


def _fts_open():
    import sqlite3
    con = sqlite3.connect(FTS_DB, timeout=10)
    con.execute("CREATE TABLE IF NOT EXISTS docs(slug TEXT PRIMARY KEY, mtime REAL, size INT,"
                " name TEXT, description TEXT, type TEXT)")
    con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(slug, name, description, body,"
                " tokenize='porter unicode61', prefix='2 3 4')")
    return con


def _fts_sync(con):
    """Lazy sync by (mtime, size): hand edits, API writes and deletes are all picked up."""
    disk = {}
    for p in glob.glob(os.path.join(MEM_DIR, "*.md")):
        base = os.path.basename(p)
        if not is_memory_file(base):
            continue
        try:
            st = os.stat(p)
        except OSError:
            continue
        disk[base[:-3]] = (p, st.st_mtime, st.st_size)
    have = {r[0]: (r[1], r[2]) for r in con.execute("SELECT slug, mtime, size FROM docs")}
    stale = [s for s, (p, mt, sz) in disk.items() if have.get(s) != (mt, sz)]
    gone = [s for s in have if s not in disk]
    if not stale and not gone:
        return
    with open(FTS_LOCK, "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        with con:
            for s in gone + stale:
                row = con.execute("SELECT rowid FROM docs WHERE slug=?", (s,)).fetchone()
                if row:
                    con.execute("DELETE FROM fts WHERE rowid=?", (row[0],))
                    con.execute("DELETE FROM docs WHERE rowid=?", (row[0],))
            for s in stale:
                p, mt, sz = disk[s]
                try:
                    d = parse(p)
                except Exception:
                    continue
                cur = con.execute("INSERT INTO docs(slug, mtime, size, name, description, type) VALUES(?,?,?,?,?,?)",
                                  (s, mt, sz, d["name"], d["description"], d["type"]))
                con.execute("INSERT INTO fts(rowid, slug, name, description, body) VALUES(?,?,?,?,?)",
                            (cur.lastrowid, s.replace("-", " ").replace("_", " "),
                             d["name"].replace("-", " "), d["description"], d["body"]))


def _fts_query(con, terms, limit):
    if not terms:
        return []
    match = " OR ".join(f'"{t}"*' for t in terms)
    sql = (f"SELECT d.slug, d.name, d.description, d.type,"
           f" bm25(fts, {_W_SLUG}, {_W_NAME}, {_W_DESC}, {_W_BODY}) AS r"
           f" FROM fts JOIN docs d ON d.rowid = fts.rowid WHERE fts MATCH ? ORDER BY r LIMIT ?")
    return con.execute(sql, (match, limit)).fetchall()


def search(query, limit=12):
    """Ranked full-text search -> [{slug,name,description,type,score}] (higher = better)."""
    try:
        limit = max(1, int(limit))
        os.makedirs(MEM_DIR, exist_ok=True)
        con = _fts_open()
        try:
            _fts_sync(con)
            terms = [t for t in re.findall(r"[A-Za-z0-9_]+", query.lower()) if t]
            out, seen = [], set()
            for slug, name, desc, typ, r in _fts_query(con, terms, limit):
                seen.add(slug)
                out.append({"slug": slug, "name": name, "description": desc, "type": typ,
                            "score": max(1, int(round(-r * 10)))})
            if len(out) < limit:  # long words that missed retry as a short prefix, discounted
                short = sorted({t[:5] for t in terms if len(t) >= 7} - set(terms))
                for slug, name, desc, typ, r in _fts_query(con, short, limit * 2):
                    if slug in seen or len(out) >= limit:
                        continue
                    seen.add(slug)
                    out.append({"slug": slug, "name": name, "description": desc, "type": typ,
                                "score": max(1, int(round(-r * 4)))})
            return out
        finally:
            con.close()
    except Exception as e:
        try:
            os.remove(FTS_DB)
        except OSError:
            pass
        print(f"[mem] fts fallback: {e}", file=sys.stderr)
        return _search_scan(query, limit)


# ------------------------------------------------------------------ briefs
def brief(name=None):
    """Per-project brief text (built nightly by mem_dream.py); no name -> list of names."""
    names = sorted(os.path.basename(p)[:-3] for p in glob.glob(os.path.join(BRIEF_DIR, "*.md")))
    if not name:
        return names
    name = clean_slug(name)
    for n in [name] + [x for x in names if x.startswith(name)]:
        p = os.path.join(BRIEF_DIR, f"{n}.md")
        if os.path.exists(p):
            return open(p).read()
    return None


# ------------------------------------------------------------------ writes
def upsert_index(slug, description):
    line = f"- [{slug}]({slug}.md) — {description or '(no description)'}"
    lines = []
    if os.path.exists(INDEX):
        with open(INDEX) as f:
            lines = [l.rstrip("\n") for l in f]
    else:
        lines = ["# Memory index", "", "One line per memory. Maintained additively by mem / mem_server.", ""]
    pat = re.compile(rf"^- \[{re.escape(slug)}\]\(")
    for i, l in enumerate(lines):
        if pat.match(l):
            lines[i] = line
            break
    else:
        lines.append(line)
    with open(INDEX, "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def _remove_from_index(slug):
    if not os.path.exists(INDEX):
        return
    pat = re.compile(rf"^- \[{re.escape(slug)}\]\(")
    with open(INDEX) as f:
        lines = [l.rstrip("\n") for l in f if not pat.match(l)]
    with open(INDEX, "w") as f:
        f.write("\n".join(lines).rstrip() + "\n")


def _one_line(s):
    return re.sub(r"\s+", " ", s or "").strip()[:300]


def write(slug, description, body, mtype="project", author="agent"):
    slug, path = _slug_path(slug)
    description, author = _one_line(description), _one_line(author) or "agent"
    if mtype not in VALID_TYPES:
        mtype = "project"
    with _Lock():
        existed = os.path.exists(path)
        content = ("---\n"
                   f"name: {slug}\n"
                   f"description: {description}\n"
                   f"author: {author}\n"
                   f"updated: {_now()}\n"
                   "metadata:\n"
                   f"  type: {mtype}\n"
                   "---\n\n"
                   f"{(body or '').strip()}\n")
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            f.write(content)
        os.replace(tmp, path)
        upsert_index(slug, description)
        _feed(f"{'updated' if existed else 'created'} memory [{slug}] — {description}", author)
    return {"slug": slug, "path": path, "action": "updated" if existed else "created"}


def delete(slug, author="agent"):
    slug, path = _slug_path(slug)
    with _Lock():
        if os.path.exists(path):
            os.remove(path)
            _remove_from_index(slug)
            _feed(f"deleted memory [{slug}]", author)
            return True
    return False


def _feed(msg, author="agent"):
    os.makedirs(MEM_DIR, exist_ok=True)
    if not os.path.exists(FEED):
        with open(FEED, "w") as f:
            f.write("# Shared agent activity feed\n"
                    "Append-only. Every agent logs notable actions here. Newest at bottom.\n\n")
    with open(FEED, "a") as f:
        text = re.sub(r"\s+", " ", msg or "").strip()[:1000]
        f.write(f"- {_now()} · **{_one_line(author)}** · {text}\n")


def log(msg, author="agent"):
    with _Lock():
        _feed(msg, author)
    return True


def feed(n=25):
    if not os.path.exists(FEED):
        return []
    with open(FEED) as f:
        lines = [l.rstrip("\n") for l in f if l.startswith("- ")]
    return lines[-max(1, int(n)):]
