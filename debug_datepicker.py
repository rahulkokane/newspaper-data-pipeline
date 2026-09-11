from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"
READER_URL = "https://epaper.thehindu.com/reader"


def main():
    with sync_playwright() as p:
        print("[BOOT] Connecting to Chrome...")
        browser = p.chromium.connect_over_cdp(CDP_URL)

        context = browser.contexts[0]

        page = next(
            (pg for pg in context.pages if "epaper.thehindu.com/reader" in pg.url),
            None
        )

        if not page:
            raise RuntimeError("Could not find The Hindu reader page")

        print("[OK] Page:", page.url)
        print()

        # ---------------------------------------------------------
        # 1. Find all elements related to date/calendar
        # ---------------------------------------------------------

        print("=" * 70)
        print("DATE / CALENDAR RELATED ELEMENTS")
        print("=" * 70)

        elements = page.locator(
            "button, a, input, span, div, li"
        )

        count = min(elements.count(), 2000)

        for i in range(count):
            try:
                el = elements.nth(i)

                text = (el.inner_text(timeout=200) or "").strip()
                aria = el.get_attribute("aria-label") or ""
                title = el.get_attribute("title") or ""
                target = el.get_attribute("data-target") or ""
                bs_target = el.get_attribute("data-bs-target") or ""
                href = el.get_attribute("href") or ""
                cls = el.get_attribute("class") or ""
                ident = el.get_attribute("id") or ""

                combined = " ".join([
                    text,
                    aria,
                    title,
                    target,
                    bs_target,
                    href,
                    cls,
                    ident
                ]).lower()

                keywords = [
                    "date",
                    "calendar",
                    "datepicker",
                    "august",
                    "september",
                    "2026"
                ]

                if any(k in combined for k in keywords):
                    visible = el.is_visible()

                    print(
                        f"\n[{i}] visible={visible}"
                    )
                    print(" id       :", ident)
                    print(" text     :", repr(text[:150]))
                    print(" aria     :", repr(aria))
                    print(" title    :", repr(title))
                    print("target    :", repr(target))
                    print("bs-target :", repr(bs_target))
                    print("href     :", repr(href))
                    print("class    :", repr(cls[:200]))

            except Exception:
                pass

        # ---------------------------------------------------------
        # 2. Datepicker itself
        # ---------------------------------------------------------

        print()
        print("=" * 70)
        print("DATEPICKER")
        print("=" * 70)

        dp = page.locator("#datepicker")

        print("count   :", dp.count())

        if dp.count():
            print("visible :", dp.first.is_visible())

            print()
            print("HTML:")
            try:
                print(dp.first.evaluate(
                    "(el) => el.outerHTML"
                )[:10000])
            except Exception as e:
                print("Could not read HTML:", e)

        # ---------------------------------------------------------
        # 3. Print buttons only
        # ---------------------------------------------------------

        print()
        print("=" * 70)
        print("VISIBLE BUTTONS")
        print("=" * 70)

        buttons = page.locator("button")

        for i in range(buttons.count()):
            try:
                b = buttons.nth(i)

                if not b.is_visible():
                    continue

                print(
                    f"[{i}] "
                    f"text={repr((b.inner_text() or '').strip())} "
                    f"id={b.get_attribute('id')} "
                    f"aria={b.get_attribute('aria-label')} "
                    f"title={b.get_attribute('title')} "
                    f"class={b.get_attribute('class')}"
                )
            except Exception:
                pass

        print()
        print("[DONE]")
        print("Chrome will NOT be closed.")

        p.stop()


if __name__ == "__main__":
    main()