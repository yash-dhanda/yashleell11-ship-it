#!/usr/bin/env python3
"""GitHub GraphQL -> four SVG graphics, in the portrait's visual language.

Standard library only. This runs in CI every night; a dependency here is a
dependency that can break the profile at 06:00 UTC with nobody watching.

Two determinism traps, both of which produce a nightly stream of meaningless
commits if you miss them:

  1. Pin the window to whole UTC days. Left alone, contributionsCollection
     measures "the past year" from the instant of the request, so two runs
     minutes apart bucket days into different weeks and shift the sparkline by
     a fraction of a pixel - enough to look changed every night.
  2. Ask for public repositories only. A personal token sees private repos and
     the workflow's GITHUB_TOKEN does not, so language percentages otherwise
     disagree depending on who ran the script.

Let the action own the generated files. Regenerating them locally as well
guarantees merge conflicts, because the two tokens bucket a day near a week
boundary differently and the output is never byte-identical.
"""

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
ASSETS = ROOT / "assets"

API = "https://api.github.com/graphql"

QUERY = """
query($login:String!, $from:DateTime!, $to:DateTime!) {
  user(login:$login) {
    contributionsCollection(from:$from, to:$to) {
      contributionCalendar {
        totalContributions
        weeks { contributionDays { date contributionCount } }
      }
    }
    repositories(first:100, privacy:PUBLIC, ownerAffiliations:OWNER, isFork:false) {
      nodes {
        name
        languages(first:10, orderBy:{field:SIZE, direction:DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""

# ---------------------------------------------------------------- palettes

THEMES = {
    "light": dict(ink="#1f2328", muted="#59636e", rule="#d1d9e0",
                  accent="#1a7f37", dim="#c9d1d9"),
    "dark":  dict(ink="#e6edf3", muted="#9198a1", rule="#3d444d",
                  accent="#3fb950", dim="#2a3038"),
}

RAMP = " .,:;=+*xo%#@"          # the portrait's ramp, reused for the year grid
FONT = "font-family:'JBM',ui-monospace,SFMono-Regular,monospace"


def font_face() -> str:
    b64 = base64.b64encode((ASSETS / "fonts" / "jbm-data.woff2").read_bytes()).decode()
    return ("@font-face{font-family:'JBM';font-style:normal;font-weight:400;"
            f"src:url(data:font/woff2;base64,{b64}) format('woff2');}}")


def esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def frame(w: int, h: int, label: str, body: str, t: dict) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" role="img" aria-label="{esc(label)}">'
        f"<style>{font_face()}"
        f"text{{{FONT};fill:{t['ink']}}}"
        f".m{{fill:{t['muted']}}}.a{{fill:{t['accent']}}}"
        f"</style>{body}</svg>"
    )


# ---------------------------------------------------------------- fetching

def fetch(login: str, token: str) -> dict:
    today = dt.datetime.now(dt.timezone.utc).date()
    frm = dt.datetime.combine(today - dt.timedelta(days=364), dt.time.min,
                              tzinfo=dt.timezone.utc)
    to = dt.datetime.combine(today, dt.time.max, tzinfo=dt.timezone.utc)
    payload = json.dumps({
        "query": QUERY,
        "variables": {
            "login": login,
            "from": frm.isoformat().replace("+00:00", "Z"),
            "to": to.isoformat().replace("+00:00", "Z"),
        },
    }).encode()
    req = urllib.request.Request(
        API, data=payload,
        headers={"Authorization": f"bearer {token}",
                 "Content-Type": "application/json",
                 "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        doc = json.loads(r.read())
    if "errors" in doc:
        raise SystemExit(f"GraphQL: {doc['errors']}")
    return doc["data"]["user"]


def from_fixture(path: pathlib.Path) -> dict:
    """Local verification path: the public calendar scraped to JSON."""
    raw = json.loads(path.read_text())
    days = [{"date": d, "contributionCount": v["count"]} for d, v in sorted(raw.items())]
    weeks = [{"contributionDays": days[i:i + 7]} for i in range(0, len(days), 7)]
    return {
        "contributionsCollection": {"contributionCalendar": {
            "totalContributions": sum(d["contributionCount"] for d in days),
            "weeks": weeks}},
        "repositories": {"nodes": [
            {"name": "ManhwaManiacs", "languages": {"edges": [
                {"size": 486000, "node": {"name": "Python"}},
                {"size": 205000, "node": {"name": "Dart"}},
                {"size": 41000, "node": {"name": "Shell"}}]}},
            {"name": "recall", "languages": {"edges": [
                {"size": 132000, "node": {"name": "Python"}},
                {"size": 9000, "node": {"name": "Shell"}}]}},
        ]},
    }


# ---------------------------------------------------------------- shaping

def flat_days(user: dict) -> list[tuple[str, int]]:
    cal = user["contributionsCollection"]["contributionCalendar"]
    out = []
    for wk in cal["weeks"]:
        for d in wk["contributionDays"]:
            out.append((d["date"], d["contributionCount"]))
    return out


def streaks(days: list[tuple[str, int]]) -> tuple[dict, dict]:
    best = cur = {"len": 0, "start": None, "end": None}
    run = 0
    start = None
    for date, n in days:
        if n > 0:
            run += 1
            start = start or date
            if run > best["len"]:
                best = {"len": run, "start": start, "end": date}
        else:
            run, start = 0, None
    # the current streak must run to the final day of the window
    run, start = 0, None
    for date, n in reversed(days):
        if n > 0:
            run += 1
            start = date
        else:
            break
    cur = {"len": run, "start": start, "end": days[-1][0] if run else None}
    return cur, best


def top_langs(user: dict, k: int = 5) -> list[tuple[str, int, int]]:
    by_size: dict[str, int] = {}
    by_repo: dict[str, int] = {}
    for repo in user["repositories"]["nodes"]:
        for e in repo["languages"]["edges"]:
            name = e["node"]["name"]
            by_size[name] = by_size.get(name, 0) + e["size"]
            by_repo[name] = by_repo.get(name, 0) + 1
    ranked = sorted(by_size.items(), key=lambda kv: -kv[1])[:k]
    return [(n, s, by_repo[n]) for n, s in ranked]


def pretty(d: str) -> str:
    y, m, day = (int(x) for x in d.split("-"))
    return f"{dt.date(y, m, day):%b %-d}".lower()


# ---------------------------------------------------------------- graphics

def hero(user: dict, t: dict) -> str:
    days = flat_days(user)
    total = user["contributionsCollection"]["contributionCalendar"]["totalContributions"]
    weeks = [sum(n for _, n in days[i:i + 7]) for i in range(0, len(days), 7)]
    W, H = 880, 132
    b = [f'<text x="0" y="20" font-size="11" class="m">contributions, last 365 days</text>',
         f'<text x="0" y="62" font-size="38">{total:,}</text>',
         f'<text x="0" y="88" font-size="11" class="m">across {sum(1 for _, n in days if n)} active days</text>']
    # weekly aggregate, so an area is defensible here; daily would need columns
    x0, y0, gw, gh = 300, 30, W - 300, 74
    peak = max(weeks) or 1
    step = gw / max(len(weeks) - 1, 1)
    pts = [(x0 + i * step, y0 + gh - (v / peak) * gh) for i, v in enumerate(weeks)]
    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    area = f"{x0},{y0 + gh} " + line + f" {x0 + gw},{y0 + gh}"
    b.append(f'<polygon points="{area}" fill="{t["accent"]}" opacity="0.16"/>')
    b.append(f'<polyline points="{line}" fill="none" stroke="{t["accent"]}" '
             f'stroke-width="1.5" stroke-linejoin="round"/>')
    b.append(f'<line x1="{x0}" y1="{y0 + gh + .5}" x2="{W}" y2="{y0 + gh + .5}" '
             f'stroke="{t["rule"]}"/>')
    b.append(f'<text x="{x0}" y="{y0 + gh + 18}" font-size="10" class="m">'
             f'{pretty(days[0][0])}</text>')
    b.append(f'<text x="{W}" y="{y0 + gh + 18}" font-size="10" class="m" '
             f'text-anchor="end">{pretty(days[-1][0])}</text>')
    return frame(W, H, f"{total} contributions in the last 365 days", "".join(b), t)


def streak_card(user: dict, t: dict) -> str:
    cur, best = streaks(flat_days(user))
    W, H = 428, 132
    b = []
    for i, (label, s) in enumerate((("current streak", cur), ("longest streak", best))):
        y = 20 + i * 58
        rng = f"{pretty(s['start'])} – {pretty(s['end'])}" if s["len"] else "none yet"
        b.append(f'<text x="0" y="{y}" font-size="11" class="m">{label}</text>')
        b.append(f'<text x="0" y="{y + 30}" font-size="26">{s["len"]}</text>')
        unit = "day" if s["len"] == 1 else "days"
        w = len(str(s["len"])) * 26 * 0.600 + 7        # 0.600em advance, then a gap
        b.append(f'<text x="{w:.1f}" y="{y + 30}" font-size="12" class="m">{unit}</text>')
        b.append(f'<text x="{W}" y="{y + 30}" font-size="11" class="m" '
                 f'text-anchor="end">{rng}</text>')
        if i == 0:
            b.append(f'<line x1="0" y1="{y + 44}" x2="{W}" y2="{y + 44}" stroke="{t["rule"]}"/>')
    return frame(W, H, f"current streak {cur['len']} days, longest {best['len']} days",
                 "".join(b), t)


def langs_card(user: dict, t: dict) -> str:
    langs = top_langs(user)
    total = sum(s for _, s, _ in langs) or 1
    W, H = 428, 132
    b = ['<text x="0" y="20" font-size="11" class="m">languages, public repos</text>']
    for i, (name, size, repos) in enumerate(langs[:4]):
        y = 44 + i * 22
        pct = size / total * 100
        bw = 150
        b.append(f'<text x="0" y="{y}" font-size="12">{esc(name)}</text>')
        b.append(f'<rect x="120" y="{y - 9}" width="{bw}" height="7" rx="3.5" fill="{t["dim"]}"/>')
        b.append(f'<rect x="120" y="{y - 9}" width="{max(bw * pct / 100, 2):.1f}" '
                 f'height="7" rx="3.5" fill="{t["accent"]}"/>')
        b.append(f'<text x="286" y="{y}" font-size="11" class="m">{pct:.0f}%</text>')
        b.append(f'<text x="{W}" y="{y}" font-size="11" class="m" text-anchor="end">'
                 f'{repos} repo{"" if repos == 1 else "s"}</text>')
    return frame(W, H, "top languages across public repositories", "".join(b), t)


def year_card(user: dict, t: dict) -> str:
    days = flat_days(user)
    peak = max((n for _, n in days), default=1) or 1
    # rank-based levels: a single 243-commit day would otherwise flatten the rest
    nz = sorted({n for _, n in days if n})
    def level(n: int) -> int:
        if not n:
            return 0
        return 1 + int(nz.index(n) / max(len(nz) - 1, 1) * (len(RAMP) - 2))
    cols = (len(days) + 6) // 7
    W, H = 880, 160
    cw = (W - 8) / cols                     # span the full card, whatever the year holds
    b = ['<text x="0" y="20" font-size="11" class="m">the year, one character per day</text>']
    grid = [[" "] * cols for _ in range(7)]
    for i, (_, n) in enumerate(days):
        grid[i % 7][i // 7] = RAMP[level(n)]
    # two layers: quiet days get a dim marker so 40 blank weeks read as
    # "nothing happened" rather than as a broken image
    for r, row in enumerate(grid):
        y = 42 + r * 14
        quiet = "".join("·" if c == " " else " " for c in row)
        live = "".join(c if c != " " else " " for c in row)
        common = (f'font-size="12" xml:space="preserve" '
                  f'letter-spacing="{cw - 7.2:.2f}"')
        b.append(f'<text x="0" y="{y}" {common} class="m" opacity="0.32">{esc(quiet)}</text>')
        b.append(f'<text x="0" y="{y}" {common} class="a">{esc(live)}</text>')
    foot = 42 + 7 * 14 + 8
    b.append(f'<text x="0" y="{foot}" font-size="10" class="m">{pretty(days[0][0])}</text>')
    b.append(f'<text x="{W}" y="{foot}" font-size="10" class="m" '
             f'text-anchor="end">{pretty(days[-1][0])} · peak {peak}/day</text>')
    return frame(W, H, "contribution calendar as characters", "".join(b), t)


# ---------------------------------------------------------------- driver

CARDS = {"hero": hero, "streak": streak_card, "langs": langs_card, "year": year_card}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--login", default="yashleell11-ship-it")
    ap.add_argument("--fixture", default="", help="local JSON instead of the API")
    args = ap.parse_args()

    if args.fixture:
        user = from_fixture(pathlib.Path(args.fixture))
        print(f"  fixture: {args.fixture}")
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise SystemExit("GITHUB_TOKEN not set")
        user = fetch(args.login, token)

    ASSETS.mkdir(parents=True, exist_ok=True)
    changed = []
    for name, fn in CARDS.items():
        for theme, pal in THEMES.items():
            dst = ASSETS / f"{name}-{theme}.svg"
            new = fn(user, pal)
            old = dst.read_text() if dst.exists() else None
            if old != new:
                dst.write_text(new)
                changed.append(dst.name)
    days = flat_days(user)
    cur, best = streaks(days)
    print(f"  {len(days)} days, {sum(n for _, n in days):,} contributions, "
          f"streak {cur['len']}/{best['len']}")
    print(f"  {len(changed)} file(s) changed" + (f": {', '.join(changed)}" if changed else ""))


if __name__ == "__main__":
    main()
