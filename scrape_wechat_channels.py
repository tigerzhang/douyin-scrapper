import os
import time
import json
import hashlib
import pytesseract
from PIL import Image, ImageEnhance, ImageOps
import io
import re
from datetime import datetime
from playwright.sync_api import sync_playwright

# Configuration
WECHAT_URL = "https://channels.weixin.qq.com/platform/interaction/comment"
USER_DATA_DIR = os.path.join(os.getcwd(), "wechat_user_data")
SCRAPED_DATA_DIR = os.path.join(os.getcwd(), "wechat_scraped_data")

if not os.path.exists(SCRAPED_DATA_DIR):
    os.makedirs(SCRAPED_DATA_DIR)

def extract_data_via_ocr(page, region, debug_name=None):
    """Captures a region, preprocesses it, and extracts text via OCR."""
    try:
        screenshot_bytes = page.screenshot(clip=region)
        img = Image.open(io.BytesIO(screenshot_bytes))
        
        # Original for debug
        if debug_name:
            img.save(os.path.join(SCRAPED_DATA_DIR, f"debug_ocr_{debug_name}_orig.png"))
        
        # Preprocessing: 
        # 1. Grayscale
        img = img.convert('L') 
        
        # 2. Upscale (3x is often the sweet spot for Tesseract)
        img = img.resize((img.width * 3, img.height * 3), Image.Resampling.LANCZOS)
        
        # 3. Denoising & Sharpening
        from PIL import ImageFilter
        img = img.filter(ImageFilter.MedianFilter(size=3))
        img = img.filter(ImageFilter.SHARPEN)
        
        # 4. Increase Contrast 
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(2.5)
        
        # 5. Auto-Contrast & Binary Thresholding
        img = ImageOps.autocontrast(img)
        img = img.point(lambda p: 255 if p > 165 else 0)
        
        if debug_name:
            img.save(os.path.join(SCRAPED_DATA_DIR, f"debug_ocr_{debug_name}_proc.png"))
            
        custom_config = r'--oem 3 --psm 6'
        text = pytesseract.image_to_string(img, lang='chi_sim+eng', config=custom_config)
        return text.strip()
    except Exception as e:
        print(f"   [OCR ERROR] {e}")
        return ""

def parse_ocr_text_to_comments(raw_text):
    """Structures raw OCR text into comments with better noise filtering."""
    comments = []
    if not raw_text: return comments
    
    # Noise patterns
    noise_patterns = [
        "视频号助手", "评论", "Tencent Inc", "All Rights Reserved", 
        "1998-2026", "问题咨询", "运营规范", "站内信", "首页"
    ]
    
    # Filter out pure symbols/gibberish nicknames
    def is_valid_nickname(name):
        if not name or name == "Unknown": return False
        # If it's just symbols or mostly symbols, reject
        alnum_count = sum(1 for c in name if c.isalnum() or '\u4e00' <= c <= '\u9fff')
        return alnum_count > 0

    lines = [l.strip() for l in raw_text.split('\n') if l.strip()]
    lines = [l for l in lines if not any(p in l for p in noise_patterns)]
    
    time_pattern = re.compile(r'(\d{4}[/\-]\d{1,2}[/\-]\d{1,2})|(\d{1,2}:\d{2})')
    current_comment = None
    
    for i, line in enumerate(lines):
        if time_pattern.search(line):
            if current_comment and current_comment["content"]: 
                comments.append(current_comment)
            
            # Use line before as nickname, but filter it
            nickname = lines[i-1] if i > 0 else "Unknown"
            if not is_valid_nickname(nickname): nickname = "Unknown"
            if len(nickname) > 50: nickname = "Unknown" 
            
            current_comment = {
                "nickname": nickname, 
                "timestamp": line, 
                "content": "", 
                "scrape_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
        elif current_comment:
            if current_comment["content"]:
                current_comment["content"] += " " + line
            else:
                current_comment["content"] = line
                
    if current_comment and current_comment["content"]: 
        comments.append(current_comment)
    return comments

def scrape_comments_pure_vision(page, video_index):
    """Pure vision-based comment extraction into Detail Panel."""
    print(f"\n[VISION] Scraping Video {video_index} detail panel...")
    
    # 1. OCR Video Title (Detail Panel Top)
    title_region = {'x': 850, 'y': 20, 'width': 580, 'height': 80}
    raw_title = extract_data_via_ocr(page, title_region, debug_name=f"v{video_index}_title")
    # Get first line of title
    video_title = raw_title.split('\n')[0] if raw_title else ""
    video_title = "".join([c for c in video_title if c.isalnum() or c in (' ', '_')]).strip()
    video_title = video_title[:30] or f"video_{video_index}"
    print(f"   [VISION] Parsed Title: {video_title}")

    all_comments = []
    seen_hashes = set()
    no_new_data_count = 0
    
    # 2. Extraction Loop (Scrolling)
    for scroll_idx in range(12): # Thorough scroll
        ocr_region = {'x': 850, 'y': 110, 'width': 580, 'height': 790}
        raw_text = extract_data_via_ocr(page, ocr_region, debug_name=f"v{video_index}_s{scroll_idx}" if scroll_idx == 0 else None)
        
        if raw_text:
            text_hash = hashlib.md5(raw_text.encode()).hexdigest()
            if text_hash not in seen_hashes:
                seen_hashes.add(text_hash)
                parsed = parse_ocr_text_to_comments(raw_text)
                
                new_added = 0
                for c in parsed:
                    sig = f"{c['nickname']}|{c['content']}"
                    if sig not in [f"{xc['nickname']}|{xc['content']}" for xc in all_comments]:
                        all_comments.append(c)
                        new_added += 1
                
                print(f"   [OCR] Scroll {scroll_idx}: +{new_added} new (Total: {len(all_comments)})")
                no_new_data_count = 0
            else:
                no_new_data_count += 1
        else:
            no_new_data_count += 1
        
        if no_new_data_count >= 3: break
        
        # Scroll right panel area
        page.mouse.move(1100, 500)
        page.mouse.wheel(0, 500)
        time.sleep(2)

    # 3. Save
    if all_comments:
        filename = f"wechat_comments_{video_title}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = os.path.join(SCRAPED_DATA_DIR, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(all_comments, f, ensure_ascii=False, indent=2)
        print(f"   [SUCCESS] Saved {len(all_comments)} comments.")
    else:
        print("   [INFO] No comments extracted.")

def run_scraper():
    with sync_playwright() as p:
        print(f"Launching browser: {USER_DATA_DIR}")
        browser = p.chromium.launch_persistent_context(
            USER_DATA_DIR, 
            headless=False, 
            viewport={'width': 1440, 'height': 900}
        )
        page = browser.pages[0]
        
        print(f"Navigating to {WECHAT_URL}...")
        page.goto(WECHAT_URL)
        time.sleep(12) 
        
        # Click Video Tab
        print("Clicking Video Tab (420, 110)...")
        page.mouse.click(420, 110) 
        time.sleep(5)
        
        # Sequentially click video items
        for i in range(10): 
            y_coord = 240 + (i * 90)
            print(f"\n--- [VIDEO {i}] Clicking List Item at (650, {y_coord}) ---")
            page.mouse.click(650, y_coord)
            time.sleep(6) # Give it time to load the detail panel
            
            scrape_comments_pure_vision(page, i)
            
            # Scroll the video list occasionally
            if i > 0 and i % 3 == 0:
                print("Scrolling Video List down...")
                page.mouse.move(600, 500)
                page.mouse.wheel(0, 300)
                time.sleep(2)

        print("\nAll tasks finished.")
        browser.close()

if __name__ == "__main__":
    run_scraper()
