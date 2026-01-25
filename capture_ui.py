from playwright.sync_api import sync_playwright
import time
import os

USER_DATA_DIR = os.path.join(os.getcwd(), "wechat_user_data")
WECHAT_URL = "https://channels.weixin.qq.com/platform/interaction/comment"

def capture_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR, 
            headless=False, 
            viewport={'width': 1440, 'height': 900}
        )
        page = browser.pages[0]
        page.goto(WECHAT_URL)
        print("Waiting for page load...")
        time.sleep(8)
        
        # Take a full page screenshot
        screenshot_path = "debug_ui_full.png"
        page.screenshot(path=screenshot_path)
        print(f"Screenshot saved to {screenshot_path}")
        
        # Dump some OCR text from the left and right to see what's what
        # Video List area (approx)
        import pytesseract
        from PIL import Image
        
        img = Image.open(screenshot_path)
        # Left side list
        left_region = (0, 0, 450, 900)
        left_img = img.crop(left_region)
        left_text = pytesseract.image_to_string(left_img, lang='chi_sim+eng')
        print("\n--- LEFT SIDE OCR ---")
        print(left_text[:500])
        
        # Right side detail
        right_region = (450, 0, 1440, 900)
        right_img = img.crop(right_region)
        right_text = pytesseract.image_to_string(right_img, lang='chi_sim+eng')
        print("\n--- RIGHT SIDE OCR ---")
        print(right_text[:500])
        
        browser.close()

if __name__ == "__main__":
    capture_ui()
