from playwright.sync_api import sync_playwright
import sys

def test_launch():
    try:
        with sync_playwright() as p:
            print("Attempting to launch Chromium...")
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto("https://www.google.com")
            print(f"Success! Page title: {page.title()}")
            browser.close()
    except Exception as e:
        print(f"Launch failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_launch()
