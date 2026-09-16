"""Smoke guide/weapons.html in a real browser and screenshot it.

The weapons guide is a self-contained page opened over ``file://``, and
its whole substance — ten stages of prose and code — lives inside a JS
array rather than in the markup. That is the failure mode this probe
exists for: a broken array renders a page that still *looks* fine, with
a nav bar, a hero and an empty panel where the teaching used to be.

It is not theoretical. The first version shipped with an unescaped
backtick inside one of the template literals, copied faithfully out of a
Python docstring that uses the RST ``like this`` convention. ``node
--check`` passed it, because a tagged template is perfectly good syntax.
Every stage was blank in the browser.

So the assertions here are deliberately about *substance*, not
existence: ten distinct titles, a code block on every stage, and enough
body text that a stage cannot quietly go empty.

Not a test — a dev probe, kept out of pytest with the rest of backstage.
Run it after touching guide/weapons.html.
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = Path("guide/weapons.html").resolve()
OUT = Path("reports/weapons-guide-probe")

#: Stages are the point of the page; a thin one is a broken one.
MIN_BODY_CHARS = 80
#: Links in the chain, tabs in the player, and panels behind them.
N_STAGES = 11


def main() -> int:
    if not PAGE.exists():
        print(f"no guide at {PAGE}", file=sys.stderr)
        return 2
    OUT.mkdir(parents=True, exist_ok=True)
    problems: list[str] = []

    def check(label: str, ok: bool, extra: str = "") -> None:
        print(f"  {'OK  ' if ok else 'FAIL'}  {label}{(' — ' + extra) if extra else ''}")
        if not ok:
            problems.append(label)

    with sync_playwright() as pw:
        br = pw.chromium.launch()
        pg = br.new_page(viewport={"width": 1280, "height": 1000})
        errors: list[str] = []
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errors.append(str(e)))

        pg.goto(PAGE.as_uri())
        pg.wait_for_timeout(700)

        check("no console / page errors", not errors, "; ".join(errors[:2])[:300])

        links = pg.locator(".wp-link")
        tabs = pg.locator(".wp-tab")
        check("chain built 11 links", links.count() == N_STAGES, f"got {links.count()}")
        check("chain built 4 acts", pg.locator(".wp-act").count() == 4)
        check("11 tabs", tabs.count() == N_STAGES, f"got {tabs.count()}")

        pg.screenshot(path=str(OUT / "01-hero.png"))
        pg.locator("#chain").scroll_into_view_if_needed()
        pg.wait_for_timeout(450)
        pg.screenshot(path=str(OUT / "02-chain.png"))

        # Every stage must carry its four sections AND real code. This is
        # the check that would have caught the backtick bug.
        pg.locator("#stages").scroll_into_view_if_needed()
        pg.wait_for_timeout(350)
        titles: set[str] = set()
        for i in range(tabs.count()):
            tabs.nth(i).click()
            pg.wait_for_timeout(110)
            title = pg.locator("#wp-title").inner_text().strip()
            body = pg.locator("#wp-body").inner_text()
            code = pg.locator("#wp-code .gd-term").count()
            write = pg.locator("#wp-write .gd-term").count()
            titles.add(title)
            if not title:
                problems.append(f"stage {i + 1}: no title")
            if code == 0:
                problems.append(f"stage {i + 1}: no in-the-tree code")
            if write == 0:
                problems.append(f"stage {i + 1}: no what-you-write example")
            if len(body) < MIN_BODY_CHARS:
                problems.append(f"stage {i + 1}: body only {len(body)} chars")
        check("11 distinct stage titles", len(titles) == N_STAGES, f"got {len(titles)}")

        # A chain link has to reach its stage, or the overview is a lie.
        pg.locator("#chain").scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        links.nth(9).click()
        pg.wait_for_timeout(450)
        check(
            "chain link 10 opens the execute stage",
            "execute" in pg.locator("#wp-status").inner_text().lower(),
        )

        for anchor, shot in (
            ("#stages", "03-stages.png"),
            ("#doctrine", "04-doctrine.png"),
            ("#economy", "05-economy.png"),
            ("#ladder", "06-ladder.png"),
            ("#map", "07-map.png"),
        ):
            pg.locator(anchor).scroll_into_view_if_needed()
            pg.wait_for_timeout(420)
            pg.screenshot(path=str(shot and OUT / shot))

        for w in (1280, 420):
            pg.set_viewport_size({"width": w, "height": 900})
            pg.wait_for_timeout(350)
            sw = pg.evaluate("document.documentElement.scrollWidth")
            cw = pg.evaluate("document.documentElement.clientWidth")
            # One px of rounding slop; anything more is a real overflow.
            check(f"no horizontal overflow @{w}", sw <= cw + 1, f"{sw} vs {cw}")
        pg.locator("#stages").scroll_into_view_if_needed()
        pg.wait_for_timeout(300)
        pg.screenshot(path=str(OUT / "08-narrow.png"))

        br.close()

    print()
    if problems:
        print(f"PROBLEMS ({len(problems)}):", file=sys.stderr)
        for p in problems:
            print("   -", p, file=sys.stderr)
        return 1
    print(f"clean · shots in {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
