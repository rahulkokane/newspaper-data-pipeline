from playwright.sync_api import sync_playwright

CDP_URL = "http://127.0.0.1:9222"


def main():
    with sync_playwright() as p:
        print("[1] Connecting to Chrome...")

        browser = p.chromium.connect_over_cdp(CDP_URL)

        print("[OK] Connected")
        print("Contexts:", len(browser.contexts))

        for ci, context in enumerate(browser.contexts):
            print(f"\n{'=' * 70}")
            print(f"CONTEXT {ci}")
            print(f"{'=' * 70}")

            print("Pages:", len(context.pages))

            for pi, page in enumerate(context.pages):

                print(f"\n{'-' * 70}")
                print(f"PAGE {pi}")
                print(f"{'-' * 70}")

                print("URL:", page.url)

                try:
                    print("TITLE:", page.title())
                except Exception as e:
                    print("TITLE ERROR:", e)

                # Only inspect actual web pages, not DevTools
                if page.url.startswith("devtools://"):
                    print("[SKIP] DevTools page")
                    continue

                print("\n[EPAPER CHECK]")

                print(
                    "Contains epaper:",
                    "epaper.thehindu.com" in page.url
                )

                # Download navigation button
                button = page.locator("#nav-download-button")

                print("\n#nav-download-button")
                print("  exists:", button.count() > 0)

                if button.count():
                    print("  visible:", button.is_visible())
                    print("  enabled:", button.is_enabled())
                    print(
                        "  aria-hidden:",
                        button.get_attribute("aria-hidden")
                    )
                    print(
                        "  aria-disabled:",
                        button.get_attribute("aria-disabled")
                    )
                    print(
                        "  title:",
                        button.get_attribute("title")
                    )

                # Download dialog
                dialog = page.locator(".overview-modal-container")

                print("\n.overview-modal-container")
                print("  exists:", dialog.count() > 0)

                if dialog.count():
                    print("  visible:", dialog.is_visible())

                # Download button
                download = page.locator("#overview-download-button")

                print("\n#overview-download-button")
                print("  exists:", download.count() > 0)

                if download.count():
                    print("  visible:", download.is_visible())
                    print("  enabled:", download.is_enabled())
                    print(
                        "  title:",
                        download.get_attribute("title")
                    )

                # Print button
                print_button = page.locator("#overview-print-button")

                print("\n#overview-print-button")
                print("  exists:", print_button.count() > 0)

                if print_button.count():
                    print("  visible:", print_button.is_visible())
                    print("  enabled:", print_button.is_enabled())

                # Page thumbnails
                pages = page.locator(".overview-img-button")

                print("\n.overview-img-button")
                print("  count:", pages.count())

                for i in range(min(pages.count(), 5)):
                    item = pages.nth(i)

                    print(
                        f"  page {i + 1}:",
                        "label=",
                        item.get_attribute("aria-label"),
                        "checked=",
                        item.get_attribute("aria-checked"),
                        "visible=",
                        item.is_visible(),
                    )

                # Date picker
                datepicker = page.locator("#datepicker")

                print("\n#datepicker")
                print("  exists:", datepicker.count() > 0)

                if datepicker.count():
                    print("  visible:", datepicker.is_visible())

        print("\n" + "=" * 70)
        print("DONE")
        print("=" * 70)

        # Disconnect only.
        # DO NOT close the Chrome browser.
        p.stop()


if __name__ == "__main__":
    main()