from pathlib import Path
from datetime import datetime, timedelta
import argparse
import time

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


CDP_URL = "http://127.0.0.1:9222"
READER_URL = "https://epaper.thehindu.com/reader"

OUTPUT_DIR = Path("data/incoming")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# HELPERS
# ============================================================

def get_main_page(context):
    """
    Find the existing The Hindu reader tab.
    """
    for page in context.pages:
        if "epaper.thehindu.com/reader" in page.url:
            return page

    raise RuntimeError(
        "Could not find https://epaper.thehindu.com/reader in Chrome."
    )


def get_reader_frame(page):
    """
    Find the actual replica reader iframe.
    """
    for frame in page.frames:
        if "ccidist-replica-reader" in frame.url:
            return frame

    return None


def wait_for_reader(page, timeout=30):
    """
    Wait until the actual ePaper reader iframe appears.
    """
    deadline = time.time() + timeout

    while time.time() < deadline:
        frame = get_reader_frame(page)

        if frame:
            try:
                if frame.locator("#nav-download-button").count() > 0:
                    return frame
            except Exception:
                pass

        time.sleep(0.5)

    raise RuntimeError(
        "The ePaper reader iframe did not load."
    )


def find_frame_with_selector(context, selector):
    """
    Search every page/frame for a selector.

    The Hindu opens its download dialogs in the reader
    environment, so searching all frames is more reliable.
    """
    for page in context.pages:
        for frame in page.frames:
            try:
                locator = frame.locator(selector)

                if locator.count() > 0:
                    return page, frame, locator.first

            except Exception:
                pass

    return None, None, None


# ============================================================
# DATE SELECTION
# ============================================================

def open_date_picker(page):
    """
    Open The Hindu's date picker.

    #hideModal is present in the DOM but hidden in the current
    responsive layout, so use force=True.
    """

    opener = page.locator("#hideModal")

    if opener.count() == 0:
        raise RuntimeError(
            "Could not find #hideModal date-picker control."
        )

    # The element is hidden, so normal click() fails.
    opener.click(force=True)

    page.locator("#datepickermodal").wait_for(
        state="visible",
        timeout=10000
    )

    page.locator("#datepicker").wait_for(
        state="visible",
        timeout=10000
    )

    print("      Date picker opened.")

def select_date(page, target_date):
    """
    Select a date from The Hindu's date picker.

    target_date: datetime.date
    """

    print(f"      Target date: {target_date}")

    # --------------------------------------------------------
    # Open date picker
    # --------------------------------------------------------

    open_date_picker(page)

    datepicker = page.locator("#datepicker")

    # --------------------------------------------------------
    # Select year
    # --------------------------------------------------------

    year_select = datepicker.locator(
        "select.ui-datepicker-year"
    )

    year_select.select_option(
        str(target_date.year)
    )

    # --------------------------------------------------------
    # Select month
    #
    # jQuery UI uses:
    # January = 0
    # February = 1
    # ...
    # August = 7
    # September = 8
    # --------------------------------------------------------

    month_value = str(target_date.month - 1)

    month_select = datepicker.locator(
        "select.ui-datepicker-month"
    )

    month_select.select_option(month_value)

    # Give the datepicker time to redraw the calendar.
    page.wait_for_timeout(500)

    # --------------------------------------------------------
    # Select day
    # --------------------------------------------------------

    day = target_date.day

    day_selector = (
        f'td[data-handler="selectDay"]'
        f'[data-month="{month_value}"]'
        f'[data-year="{target_date.year}"]'
        f':has(a.ui-state-default)'
    )

    cells = datepicker.locator(day_selector)

    selected = None

    for i in range(cells.count()):
        cell = cells.nth(i)

        try:
            text = cell.inner_text().strip()

            if text == str(day):
                selected = cell
                break

        except Exception:
            pass

    if selected is None:
        raise RuntimeError(
            f"Could not find selectable day {day} "
            f"for {target_date}"
        )

    selected.locator("a").click()

    # --------------------------------------------------------
    # Date picker should close after selection.
    # --------------------------------------------------------

    try:
        page.locator("#datepickermodal").wait_for(
            state="hidden",
            timeout=5000
        )
    except Exception:
        # Some versions close it asynchronously.
        pass

    print("      Date selected.")


# ============================================================
# WAIT FOR CORRECT EDITION
# ============================================================

def wait_for_edition(page, target_date, timeout=30):
    """
    Wait for the reader to reload after changing date.

    We primarily wait for the download button to become
    enabled. We also inspect the iframe URL/body when possible.
    """

    expected = target_date.strftime("%d-%m-%Y")

    print("      Waiting for edition to load...")

    deadline = time.time() + timeout

    while time.time() < deadline:

        frame = get_reader_frame(page)

        if frame:
            try:
                download_button = frame.locator(
                    "#nav-download-button"
                )

                if download_button.count() > 0:

                    enabled = download_button.is_enabled()

                    if enabled:
                        print("      Reader ready.")
                        return frame

            except Exception:
                pass

        time.sleep(0.5)

    raise RuntimeError(
        f"Reader did not become ready for {target_date}"
    )


# ============================================================
# DOWNLOAD
# ============================================================

def download_current_edition(page, context, target_date):
    """
    Download the full edition using the already-tested flow.
    """

    frame = wait_for_edition(
        page,
        target_date
    )

    # --------------------------------------------------------
    # STEP 1
    # Reader download button
    # --------------------------------------------------------

    print("[3/4] Opening download dialog")

    nav_download = frame.locator(
        "#nav-download-button"
    )

    nav_download.wait_for(
        state="visible",
        timeout=10000
    )

    if not nav_download.is_enabled():
        raise RuntimeError(
            "Reader download button is still disabled."
        )

    nav_download.click()

    # --------------------------------------------------------
    # STEP 2
    # First download dialog
    # --------------------------------------------------------

    print("      Waiting for download-pages dialog...")

    deadline = time.time() + 15

    overview_page = None
    overview_frame = None
    overview_button = None

    while time.time() < deadline:

        (
            overview_page,
            overview_frame,
            overview_button
        ) = find_frame_with_selector(
            context,
            "#overview-download-button"
        )

        if overview_button:
            try:
                if overview_button.is_visible():
                    break
            except Exception:
                pass

        time.sleep(0.25)

    if overview_button is None:
        raise RuntimeError(
            "Could not find #overview-download-button."
        )

    print("      Clicking Download")

    overview_button.click()

    # --------------------------------------------------------
    # STEP 3
    # Consent dialog
    # --------------------------------------------------------

    print("      Waiting for consent dialog...")

    deadline = time.time() + 15

    consent_page = None
    consent_frame = None
    checkbox_container = None

    while time.time() < deadline:

        (
            consent_page,
            consent_frame,
            checkbox_container
        ) = find_frame_with_selector(
            context,
            ".download-consent-checkbox-group"
        )

        if checkbox_container:
            try:
                if checkbox_container.is_visible():
                    break
            except Exception:
                pass

        time.sleep(0.25)

    if checkbox_container is None:
        raise RuntimeError(
            "Could not find download consent dialog."
        )

    print("      Consent dialog found.")

    # --------------------------------------------------------
    # STEP 4
    # Check both boxes
    # --------------------------------------------------------

    checkboxes = consent_frame.locator(
        ".download-consent-checkbox-group "
        'input[type="checkbox"]'
    )

    count = checkboxes.count()

    if count < 2:
        raise RuntimeError(
            f"Expected 2 consent checkboxes, found {count}"
        )

    for i in range(count):
        checkbox = checkboxes.nth(i)

        if not checkbox.is_checked():
            checkbox.check()

    # --------------------------------------------------------
    # STEP 5
    # Yes, I'm sure
    # --------------------------------------------------------

    confirm = consent_frame.locator(
        ".download-consent-button-confirm"
    )

    confirm.wait_for(
        state="visible",
        timeout=5000
    )

    # The button becomes enabled after both boxes.
    deadline = time.time() + 10

    while time.time() < deadline:

        try:
            if confirm.is_enabled():
                break
        except Exception:
            pass

        time.sleep(0.25)

    if not confirm.is_enabled():
        raise RuntimeError(
            "'Yes, I'm sure' button did not become enabled."
        )

    print("      Confirming download...")

    output_file = (
        OUTPUT_DIR /
        f"the_hindu_{target_date.isoformat()}.pdf"
    )

    # --------------------------------------------------------
    # Capture the actual browser download.
    #
    # The working download_test used page.expect_download().
    # Keep that mechanism.
    # --------------------------------------------------------

    with consent_page.expect_download(
        timeout=60000
    ) as download_info:

        confirm.click()

    download = download_info.value

    download.save_as(str(output_file))

    print(
        f"      Download saved: {output_file}"
    )
    close_download_overview(context)

    return output_file


# ============================================================
# ONE DATE
# ============================================================

def scrape_date(page, context, target_date):
    print()
    print("=" * 55)
    print(f"DATE: {target_date}")
    print("=" * 55)

    output_file = (
        OUTPUT_DIR /
        f"the_hindu_{target_date.isoformat()}.pdf"
    )

    # Avoid downloading the same file twice.
    if output_file.exists() and output_file.stat().st_size > 0:
        print("[SKIP] File already exists:")
        print(f"       {output_file}")
        return True

    print("[1/4] Opening authenticated ePaper")

    # Make sure we're on the reader page.
    if page.url != READER_URL:
        page.goto(READER_URL)

    page.wait_for_timeout(1500)

    print("[2/4] Selecting date")

    select_date(
        page,
        target_date
    )

    # Give The Hindu time to start loading the new issue.
    page.wait_for_timeout(1500)

    # --------------------------------------------------------
    # Download
    # --------------------------------------------------------

    download_current_edition(
        page,
        context,
        target_date
    )

    print("[4/4] Complete")

    return True


# ============================================================
# DATE RANGE
# ============================================================

def date_range(start_date, end_date):
    """
    Inclusive date range.
    """

    current = start_date

    while current <= end_date:
        yield current
        current += timedelta(days=1)


# ============================================================
# MAIN
# ============================================================

def main():

    parser = argparse.ArgumentParser(
        description="Download The Hindu ePaper editions."
    )

    parser.add_argument(
        "--date",
        help="Single date: YYYY-MM-DD"
    )

    parser.add_argument(
        "--from",
        dest="date_from",
        help="Start date: YYYY-MM-DD"
    )

    parser.add_argument(
        "--to",
        dest="date_to",
        help="End date: YYYY-MM-DD"
    )

    parser.add_argument(
        "--delay",
        type=int,
        default=15,
        help="Delay between downloads in seconds (default: 15)"
    )

    args = parser.parse_args()

    # --------------------------------------------------------
    # Resolve requested dates
    # --------------------------------------------------------

    if args.date:

        start_date = datetime.strptime(
            args.date,
            "%Y-%m-%d"
        ).date()

        dates = [start_date]

    elif args.date_from and args.date_to:

        start_date = datetime.strptime(
            args.date_from,
            "%Y-%m-%d"
        ).date()

        end_date = datetime.strptime(
            args.date_to,
            "%Y-%m-%d"
        ).date()

        if end_date < start_date:
            raise SystemExit(
                "--to must be greater than or equal to --from"
            )

        dates = list(
            date_range(start_date, end_date)
        )

    else:

        raise SystemExit(
            "Use either:\n"
            "  --date YYYY-MM-DD\n"
            "or\n"
            "  --from YYYY-MM-DD --to YYYY-MM-DD"
        )

    # --------------------------------------------------------
    # Connect to existing Chrome
    # --------------------------------------------------------

    print("[BOOT] Connecting to existing Chrome...")
    print(f"[BOOT] CDP: {CDP_URL}")

    with sync_playwright() as p:

        browser = p.chromium.connect_over_cdp(
            CDP_URL
        )

        print("[BOOT] Connected successfully.")

        context = browser.contexts[0]

        page = get_main_page(context)

        print("[BOOT] Page:", page.url)
        print("[BOOT] Chrome will NOT be closed.")

        successful = 0
        failed = 0

        # ----------------------------------------------------
        # Process dates sequentially
        # ----------------------------------------------------

        for index, target_date in enumerate(dates):

            try:

                scrape_date(
                    page,
                    context,
                    target_date
                )

                successful += 1

            except Exception as e:

                failed += 1

                print()
                print(
                    f"[ERROR] {target_date}: "
                    f"{type(e).__name__}: {e}"
                )

            # ------------------------------------------------
            # Delay between editions
            # ------------------------------------------------

            if index < len(dates) - 1:

                print()
                print(
                    f"[WAIT] Waiting {args.delay} seconds "
                    f"before next date..."
                )

                time.sleep(args.delay)

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        print()
        print("=" * 55)
        print("SUMMARY")
        print("=" * 55)

        print(f"Requested: {len(dates)}")
        print(f"Successful: {successful}")
        print(f"Failed: {failed}")
        print(f"Incoming: {OUTPUT_DIR.resolve()}")

        # IMPORTANT:
        # Don't close browser/context because this is the
        # user's existing Chrome.
        p.stop()


def close_download_overview(context):
    """
    Close the first download/issue-overview window.

    The Hindu leaves this window open after the actual PDF
    download, so explicitly close it before processing another date.
    """

    print("      Closing download overview...")

    deadline = time.time() + 5

    while time.time() < deadline:

        for page in context.pages:

            for frame in page.frames:

                try:
                    close_button = frame.locator(
                        ".overview-close-button"
                    )

                    if close_button.count() == 0:
                        continue

                    if not close_button.is_visible():
                        continue

                    close_button.click()

                    print("      Download overview closed.")

                    # Give the UI time to disappear.
                    time.sleep(0.5)

                    return

                except Exception:
                    pass

        time.sleep(0.25)

    print("      Overview close button not found; continuing.")


if __name__ == "__main__":
    main()