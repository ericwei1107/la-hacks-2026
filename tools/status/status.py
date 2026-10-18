import argparse
import fnmatch
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MILESTONES = json.loads((Path(__file__).parent / "milestones.json").read_text())
CHECKS_PATH = "tools/status/checks.json"
BASE = "origin/main"
ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0", "GIT_SSH_COMMAND": "ssh -o BatchMode=yes -o ConnectTimeout=8"}


def git(*args, check=False, timeout=60):
    try:
        r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True, env=ENV, timeout=timeout)
    except subprocess.TimeoutExpired:
        r = subprocess.CompletedProcess(args, 124, "", "timed out")
    if check and r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    return r


def out(*args):
    return git(*args).stdout.strip()


def https_url(url):
    if url.startswith("git@github.com:"):
        return "https://github.com/" + url.split(":", 1)[1]
    if url.startswith("ssh://git@github.com/"):
        return "https://github.com/" + url.split("github.com/", 1)[1]
    return url


def fetch():
    r = git("fetch", "--prune", "origin", timeout=30)
    if r.returncode == 0:
        return True, []
    url = https_url(out("remote", "get-url", "origin"))
    r2 = git("fetch", "--prune", url, "+refs/heads/*:refs/remotes/origin/*", timeout=30)
    if r2.returncode == 0:
        return True, ["via HTTPS"]
    errs = [l for l in (r.stderr + r2.stderr).strip().splitlines() if l.strip()]
    return False, errs[:1]


def load_checks(refs):
    local = ROOT / CHECKS_PATH
    edited = local.exists() and (
        git("diff", "--quiet", "HEAD", "--", CHECKS_PATH).returncode != 0
        or git("ls-files", "--error-unmatch", CHECKS_PATH).returncode != 0
    )
    text, src = (local.read_text(), "working tree") if edited else (None, None)
    if text is None:
        best = None
        for ref in [BASE] + refs:
            if git("cat-file", "-e", f"{ref}:{CHECKS_PATH}").returncode != 0:
                continue
            ts = int(out("log", "-1", "--format=%ct", ref, "--", CHECKS_PATH) or 0)
            if best is None or ts > best[0]:
                best = (ts, ref)
        if best:
            text, src = out("show", f"{best[1]}:{CHECKS_PATH}"), best[1]
        elif local.exists():
            text, src = local.read_text(), "working tree"
    data = json.loads(text) if text else {}
    return {k: [{**c, "source": src} for c in v] for k, v in data.items()}


def whoami():
    ids = {out("config", "user.name").lower(), out("config", "user.email").lower()} - {""}
    for key, t in MILESTONES["tracks"].items():
        if ids & {a.lower() for a in t.get("aliases", []) + [t["owner"]]}:
            return key
    return None


def branches():
    refs = out("for-each-ref", "--format=%(refname:short)", "refs/remotes/origin").splitlines()
    remote = [r for r in refs if r not in ("origin", "origin/HEAD", BASE)]
    current = out("rev-parse", "--abbrev-ref", "HEAD")
    pushed = {r.removeprefix("origin/") for r in remote}
    local = [current] if current not in pushed and current not in ("main", "HEAD") else []
    return remote + local


def owner_of(path):
    for key, t in MILESTONES["tracks"].items():
        for f in t["folders"]:
            if path == f or path.startswith(f + "/"):
                return key
    for s in MILESTONES["shared"]:
        if path == s or path.startswith(s + "/"):
            return "shared"
    return "other"


def tree(ref):
    return out("ls-tree", "-r", "--name-only", ref).splitlines()


def matches(files, pattern):
    if "**" in pattern:
        head, tail = pattern.split("**", 1)
        tail = tail.lstrip("/")
        return any(f.startswith(head) and fnmatch.fnmatch(Path(f).name, tail) for f in files)
    return any(fnmatch.fnmatch(f, pattern) for f in files)


def iso(ts):
    return datetime.fromtimestamp(int(ts), timezone.utc).astimezone().strftime("%H:%M %a")


def branch_info(b):
    ahead, behind = (out("rev-list", "--left-right", "--count", f"{b}...{BASE}") or "0 0").split()
    last = out("log", "-1", "--format=%ct%x09%an%x09%s", b).split("\t")
    changed = [l for l in out("diff", "--name-only", f"{BASE}...{b}").splitlines() if l]
    touched = sorted({owner_of(p) for p in changed})
    commits = []
    for line in out("log", "--format=%ct%x09%an%x09%s", f"{BASE}..{b}", "-n", "15").splitlines():
        ts, an, s = line.split("\t", 2)
        commits.append({"time": iso(ts), "author": an, "subject": s})
    flags = []
    contract_changes = [p for p in changed if p.startswith("contracts/")]
    if contract_changes:
        flags.append({"level": "BLOCK", "msg": f"edits frozen contracts: {', '.join(contract_changes)}"})
    bad_data = [p for p in changed if p.startswith("data/") and not p.startswith("data/samples/")]
    if bad_data:
        flags.append({"level": "BLOCK", "msg": f"commits data outside data/samples: {', '.join(bad_data[:5])}"})
    secrets = [p for p in changed if Path(p).name.startswith(".env") or p.endswith(".key")]
    if secrets:
        flags.append({"level": "BLOCK", "msg": f"commits secrets: {', '.join(secrets)}"})
    tracks = [t for t in touched if t in MILESTONES["tracks"]]
    if len(tracks) > 1:
        flags.append({"level": "WARN", "msg": f"touches several tracks' folders: {', '.join(tracks)}"})
    return {
        "branch": b,
        "ahead": int(ahead),
        "behind": int(behind),
        "last_commit": {"time": iso(last[0]), "author": last[1], "subject": last[2]} if len(last) == 3 else None,
        "touched": touched,
        "changed_files": len(changed),
        "commits": commits,
        "flags": flags,
    }


def conflicts(names):
    result = []
    refs = [BASE] + names
    for a, b in combinations(refs, 2):
        r = git("merge-tree", "--write-tree", "--name-only", "--no-messages", a, b)
        if r.returncode == 1:
            files = [l for l in r.stdout.splitlines()[1:] if l]
            result.append({"a": a, "b": b, "files": files})
    return result


def track_progress(refs):
    trees = {r: tree(r) for r in [BASE] + refs}
    report = {}
    for key, t in MILESTONES["tracks"].items():
        per_ref = {}
        for r, files in trees.items():
            own = [f for f in files if owner_of(f) == key and not f.endswith(".gitkeep")]
            if own:
                per_ref[r] = len(own)
        union = sorted({f for files in trees.values() for f in files})
        on_main = trees[BASE]
        ms = []
        for m in t["milestones"]:
            sig = m["signals"]
            if not sig:
                state = "unknown"
            elif all(matches(on_main, p) for p in sig):
                state = "on_main"
            elif all(matches(union, p) for p in sig):
                state = "on_branch"
            else:
                state = "missing"
            ms.append({**m, "signal_state": state})
        report[key] = {"owner": t["owner"], "folders": t["folders"], "files_by_ref": per_ref, "milestones": ms}
    return report


def standing_checks(refs, checks_by_track):
    res = {}
    for key, checks in checks_by_track.items():
        items = []
        for c in checks:
            if key == "runtime" or not c.get("grep"):
                items.append({**c, "state": "manual", "where": []})
                continue
            where = [r for r in [BASE] + refs if git("grep", "-q", "-E", c["grep"], r, "--", *c["paths"]).returncode == 0]
            state = "on_main" if BASE in where else "on_branch" if where else "pending"
            items.append({**c, "state": state, "where": where})
        res[key] = items
    return res


def health():
    res = {}
    for key, t in MILESTONES["tracks"].items():
        s = t["service"]
        if not s:
            continue
        url = os.environ.get(s["env"], f"http://localhost:{s['port']}").rstrip("/") + "/health"
        try:
            with urllib.request.urlopen(url, timeout=1.5) as r:
                body = json.loads(r.read().decode() or "{}")
            res[s["name"]] = {"url": url, "up": True, "body": body}
        except Exception as e:
            res[s["name"]] = {"url": url, "up": False, "error": type(e).__name__}
    return res


def validate(refs):
    try:
        import jsonschema
    except ImportError:
        return {"skipped": "jsonschema not installed in this Python"}
    res = {}
    r = subprocess.run([sys.executable, str(ROOT / "contracts/validate.py")], capture_output=True, text=True)
    res["contracts_examples"] = "PASS" if r.returncode == 0 else r.stdout.strip().splitlines()[-5:]
    samples = {}
    with tempfile.TemporaryDirectory() as d:
        for ref in [BASE] + refs:
            for f in tree(ref):
                if f.startswith("data/samples/") and f.endswith(".jsonl"):
                    key = f"{ref}:{f}"
                    if any(k.endswith(":" + f) and samples[k] == "PASS" for k in samples):
                        continue
                    p = Path(d) / f"{len(samples)}.jsonl"
                    p.write_text(out("show", f"{ref}:{f}") + "\n")
                    r = subprocess.run([sys.executable, str(ROOT / "contracts/validate.py"), str(p)], capture_output=True, text=True)
                    samples[key] = "PASS" if r.returncode == 0 else r.stdout.strip().splitlines()[-4:]
    res["samples"] = samples
    return res


def to_markdown(s):
    lines = [f"# Kumite status · {s['generated_at']}", ""]
    lines.append(f"Fetch: {'ok' if s['fetch']['ok'] else 'FAILED, using last fetched refs ' + ' '.join(s['fetch']['error'])}")
    lines.append(f"main: {s['main']}")
    lines += ["", "## Branches", ""]
    for b in s["branches"]:
        lc = b["last_commit"] or {}
        lines.append(f"### {b['branch']}  (+{b['ahead']} / -{b['behind']} vs main, {b['changed_files']} files, touches: {', '.join(b['touched']) or 'nothing'})")
        lines.append(f"last: {lc.get('time')} {lc.get('author')}: {lc.get('subject')}")
        for f in b["flags"]:
            lines.append(f"- **{f['level']}** {f['msg']}")
        for c in b["commits"]:
            lines.append(f"- {c['time']} {c['author']}: {c['subject']}")
        lines.append("")
    lines += ["## Merge conflicts between branches", ""]
    lines += [f"- {c['a']} × {c['b']}: {', '.join(c['files'])}" for c in s["conflicts"]] or ["none"]
    lines += ["", "## Tracks", ""]
    for k, t in s["tracks"].items():
        lines.append(f"### {k} · {t['owner']} ({', '.join(t['folders'])})")
        lines.append("files: " + (", ".join(f"{r}={n}" for r, n in t["files_by_ref"].items()) or "none yet"))
        for m in t["milestones"]:
            lines.append(f"- [{m['signal_state']}] h{m['hours']}: {m['goal']}")
        lines.append("")
    lines += ["## Standing checks", ""]
    for k, items in s["checks"].items():
        who = MILESTONES["tracks"][k]["owner"] if k in MILESTONES["tracks"] else "team"
        lines.append(f"### {k} · {who}")
        for c in items:
            where = f" ({', '.join(c['where'])})" if c["where"] and c["state"] != "on_main" else ""
            frm = f" (from {c['from']})" if c.get("from") else ""
            doc = f" → {c['doc']}" if c.get("doc") else ""
            lines.append(f"- [{c['state']}{where}] h{c['due']} {c['id']}{frm}: {c['todo']}{doc}")
        lines.append("")
    lines += ["## Services", ""]
    for n, h in s["health"].items():
        lines.append(f"- {n} {h['url']}: {'UP ' + json.dumps(h['body']) if h['up'] else 'down (' + h['error'] + ')'}")
    lines += ["", "## Contract validation", "", "```", json.dumps(s["validation"], indent=2), "```"]
    return "\n".join(lines)


def doc_location(path, refs):
    if not path or (ROOT / path).exists():
        return path
    for ref in [BASE] + refs:
        if git("cat-file", "-e", f"{ref}:{path}").returncode == 0:
            return f"`git show {ref}:{path}`"
    return path


def inbox(me, refs, checks):
    owner = MILESTONES["tracks"][me]["owner"] if me else None
    open_states = ("pending", "manual")
    lines = [f"# Kumite inbox for {owner or 'unknown teammate'} · {datetime.now().astimezone().strftime('%H:%M')}", ""]
    if not me:
        name, email = out("config", "user.name"), out("config", "user.email")
        lines.append(f"Couldn't match git identity '{name} <{email}>' to a track. Add it to `aliases` in tools/status/milestones.json.")
        return "\n".join(lines)
    mine = [c for c in checks.get(me, []) if c["state"] in open_states or c["state"].startswith("on_branch")]
    asks = [c for c in mine if c.get("from") and c["from"] != owner]
    own = [c for c in mine if not c.get("from") or c["from"] == owner]
    sent = []
    for key, items in checks.items():
        if key in MILESTONES["tracks"] and key != me:
            for c in items:
                if c.get("from") == owner and c["state"] in open_states:
                    sent.append((MILESTONES["tracks"][key]["owner"], c))
    def row(c):
        state = c["state"] if c["state"] != "on_branch" else f"done on {', '.join(c['where'])}, not merged"
        frm = f" (from {c['from']})" if c.get("from") else ""
        doc = f" → instructions: {doc_location(c.get('doc'), refs)}" if c.get("doc") else ""
        return f"- [{state}] due h{c['due']} · {c['todo']}{frm}{doc}"
    lines.append(f"## Requests for you ({len(asks)} open)")
    lines += [row(c) for c in asks] or ["none"]
    lines += ["", f"## Your own open items ({len(own)})"]
    lines += [row(c) for c in own] or ["none"]
    lines += ["", f"## Your requests to others still open ({len(sent)})"]
    lines += [f"- {who}: {c['todo']} [{c['state']}]" for who, c in sent] or ["none"]
    if asks:
        lines += ["", "Agent: at the start of your first reply in this session, tell the user in one or two lines which requests are open for them and who asked, then offer to work on them. Each request's instructions are in the linked file. Run /team-status for the full picture."]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-fetch", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--inbox", action="store_true")
    a = ap.parse_args()
    ok, err = (True, []) if a.no_fetch else fetch()
    refs = branches()
    checks = standing_checks(refs, load_checks(refs))
    if a.inbox:
        print(inbox(whoami(), refs, checks))
        return
    s = {
        "generated_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
        "fetch": {"ok": ok, "error": err},
        "main": out("log", "-1", "--format=%h %an: %s", BASE),
        "branches": [branch_info(b) for b in refs],
        "conflicts": conflicts(refs),
        "tracks": track_progress(refs),
        "checks": checks,
        "health": health(),
        "validation": validate(refs),
    }
    print(json.dumps(s, indent=2) if a.json else to_markdown(s))


if __name__ == "__main__":
    main()
