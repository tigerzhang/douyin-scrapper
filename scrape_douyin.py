import json
import time
import random
import os
import requests
import hashlib
from datetime import datetime
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load environment variables
load_dotenv()

def verify_login_status(page):
    print("Verifying login status...")
    while True:
        # 1. Negative Check: "Login" button (Prioritized)
        # The Sidebar 'Me' link exists even for guests, so we CANNOT rely on it as a positive indicator alone.
        # We must first ensure there is NO 'Login' button.
        is_guest = False
        try:
             login_elements = page.query_selector_all('button, .login-button')
             for el in login_elements:
                 if el.is_visible() and ("登录" in el.inner_text() or "Login" in el.inner_text()):
                     print(f"   (Detected Login Button: '{el.inner_text().strip()}')")
                     is_guest = True
                     break
        except:
            pass
            
        if is_guest:
             print(">> NOT LOGGED IN. Please log in via the browser window.")
             print("   (Waiting for 'Login' button to disappear...)")
        else:
            # 2. Positive Check: NOW we can check for User Profile
            # But we must be careful. If we are here, at least the explicit "Login" button is gone.
            if page.query_selector('a[href*="//www.douyin.com/user/self"]'):
                print(">> SUCCESS: Login verified (No 'Login' button & Profile Link found).")
                return True
            else:
                # If neither login button nor profile link... maybe page loading?
                print("   (Page loading or indeterminate state...)")
             
        # Check for blocking modal
        if page.query_selector('.login-mask') or page.query_selector('#login-full-panel'):
             print("   (Login modal is visible - Please scan QR code)")
             
        time.sleep(3)

        # Check for blocking modal
        if page.query_selector('.login-mask') or page.query_selector('#login-full-panel'):
             print("   (Login modal is visible - Please scan QR code)")
             
        time.sleep(3)

def scrape_douyin_comments(url):
    user_data_dir = os.path.join(os.getcwd(), "douyin_user_data")
    image_dir = os.path.join(os.getcwd(), "comment_images")
    
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)
        print(f"Created image directory: {image_dir}")
    
    p = sync_playwright().start()
    try:
        # Use persistent context to save login state
        print(f"Launching browser with user data dir: {user_data_dir}")
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=False,
            channel="chrome", 
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        
        page = context.pages[0] if context.pages else context.new_page()

        print(f"Navigating to {url}...")
        try:
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            print(f"Navigation warning: {e}")

        except Exception as e:
            print(f"Navigation warning: {e}")

        # Strict Login Verification
        verify_login_status(page)

        # Force open comments if hidden
        print("Checking comment sidebar visibility...")
        if not page.is_visible('.comment-mainContent'):
            print("Sidebar hidden. Attempting to open...")
            
            # Check for blocking modal FIRST
            for _ in range(60): # Check for up to 30s
                modal = page.query_selector('.login-mask, #login-full-panel, [data-e2e="login-close"]')
                if modal and modal.is_visible():
                     print("!!! BLOCKING MODAL DETECTED !!!")
                     print("Please close the login/scan window to proceed.")
                     time.sleep(2)
                else:
                     break

            try:
                 comment_tab = page.query_selector('[data-e2e="comment-switch-tab"]') or page.query_selector('text=/评论\\(\\d+\\)/') 
                 if comment_tab:
                     print("Clicking comment tab...")
                     comment_tab.click()
                     time.sleep(3)
            except Exception as e:
                print(f"Tab click warning: {e}")
                print("Tip: If a login modal is blocking, please close it.")
                
        # Find the specific scrollable container
        print("Locating scrollable comment container...")


        
        # Find the specific scrollable container
        print("Locating scrollable comment container...")
        time.sleep(3) # Give it moments to settle
        scroll_container = None
        
        # Strategy: Analyze all candidates
        try:
            potential_containers = page.query_selector_all('.comment-mainContent')
            candidates = []
            for i, c in enumerate(potential_containers):
                # Log all
                h = c.evaluate("el => el.scrollHeight")
                vis = c.is_visible()
                attr = c.get_attribute("scrollable")
                print(f"Container {i}: visible={vis}, height={h}, scrollable={attr}")
                
                if vis:
                     candidates.append((i, c, h, attr))
            
            # Priority 1: scrollable="true"
            for _, c, h, attr in candidates:
                if attr == "true":
                    scroll_container = c
                    print(f"Selected container with scrollable='true' (height {h})")
                    break
            
            # Priority 2: Largest height if no scrollable attr
            if not scroll_container and candidates:
                # Sort by height desc
                candidates.sort(key=lambda x: x[2], reverse=True)
                scroll_container = candidates[0][1]
                print(f"Selected container with max height {candidates[0][2]}")
                
        except Exception as e:
            print(f"Container finding error: {e}")
            
        if not scroll_container:
            print("Warning: Specific container not found, will rely on WINDOW/MOUSE fallback.")

        comments_data = []
        seen_ids = set()
        no_new_data_count = 0
        max_no_new_data = 5 # If no new data 5 times in a row, stop
        
        # New loop logic based on stability
        total_scrolls = 0
        
        while True:
            total_scrolls += 1
            print(f"--- Scroll #{total_scrolls} ---")
            
            # 1. Extract Comments
            # Use data-e2e="comment-item" as primary selector as found by subagent
            comment_items = page.query_selector_all('[data-e2e="comment-item"]')
            print(f"Visible comment items: {len(comment_items)}")
            
            new_in_this_batch = 0
            
            for item in comment_items:
                try:
                    # Nickname extraction
                    user_el = item.query_selector('._uYOTNYZ')
                    user_text = user_el.inner_text() if user_el else "Unknown"

                    # Content extraction
                    content_el = item.query_selector('.C7LroK_h')
                    content_text = content_el.inner_text() if content_el else "[No Content]"

                    # Time/Location from span inside .fJhvAqos or similar
                    msg_time = ""
                    msg_location = ""
                    
                    try:
                        meta_el = item.query_selector('.fJhvAqos')
                        if not meta_el:
                             # Search all spans in this item
                             spans = item.query_selector_all('span')
                             for sp in spans:
                                 txt = sp.inner_text()
                                 if "·" in txt and ("前" in txt or "20" in txt):
                                     meta_el = sp
                                     break
                        
                        if meta_el:
                            meta_text = meta_el.inner_text()
                            if "·" in meta_text:
                                parts = meta_text.split("·")
                                msg_time = parts[0].strip()
                                msg_location = parts[1].strip() if len(parts) > 1 else ""
                            else:
                                msg_time = meta_text
                    except:
                        pass
                    
                    # Dedupe
                    unique_id = f"{user_text}_{content_text[:20]}_{msg_time}"
                    
                    if unique_id not in seen_ids and content_text != "[No Content]":
                        # --- New: Image Extraction ---
                        image_path = None
                        try:
                            # Look for img tags within the comment item
                            img_els = item.query_selector_all('img')
                            for img in img_els:
                                # Filter out small icons/emojis by naturalWidth if possible
                                # Or just skip known emoji classes if identifiable
                                width = img.evaluate("el => el.naturalWidth")
                                if width > 30: # Likely a real image, not an emoji
                                    src = img.get_attribute('src')
                                    if src and src.startswith('http'):
                                        # Create unique filename
                                        url_hash = hashlib.md5(src.encode()).hexdigest()
                                        filename = f"{url_hash}.jpg"
                                        local_path = os.path.join(image_dir, filename)
                                        
                                        # Download if not already saved
                                        if not os.path.exists(local_path):
                                            try:
                                                response = requests.get(src, timeout=10)
                                                if response.status_code == 200:
                                                    with open(local_path, 'wb') as img_f:
                                                        img_f.write(response.content)
                                                    print(f"  Saved comment image: {filename}")
                                            except Exception as img_err:
                                                print(f"  Image download failed: {img_err}")
                                        
                                        if os.path.exists(local_path):
                                            image_path = os.path.join("comment_images", filename)
                                        break # Take the first large image
                        except Exception as e:
                            print(f"  Image extraction error: {e}")

                        seen_ids.add(unique_id)
                        comments_data.append({
                            "user": user_text,
                            "content": content_text,
                            "time": msg_time,
                            "location": msg_location,
                            "image_path": image_path,
                            "scrape_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        })
                        new_in_this_batch += 1
                        
                except Exception as e:
                    continue

            if new_in_this_batch > 0:
                print(f"  -> Extracted {new_in_this_batch} new comments. Total: {len(comments_data)}")
                no_new_data_count = 0
            else:
                print("  -> No new comments extracted.")
                no_new_data_count += 1
            
            if no_new_data_count >= max_no_new_data:
                print("Stopping: No new data found for several scrolls.")
                break

            # 2. Scroll Logic
            scrolled = False
            
            # Method A: Targeted Container Scroll
            if scroll_container:
                try:
                    # Debug scroll position
                    # prev_top = scroll_container.evaluate("el => el.scrollTop")
                    
                    # JS Scroll
                    # scroll_container.evaluate("el => el.scrollTop = el.scrollHeight")
                    
                    # Mouse Wheel - Aggressive
                    box = scroll_container.bounding_box()
                    if box:
                        page.mouse.move(box['x'] + box['width']/2, box['y'] + box['height']/2)
                        for _ in range(3):
                            page.mouse.wheel(0, 1000)
                            time.sleep(0.3)
                    
                    scrolled = True
                except Exception as e:
                    print(f"Scroll error: {e}")
            
            if not scrolled:
                # Fallback: Blind Mouse Wheel at center of screen
                # This works if the comment modal is open in the center/sidebar
                print("Doing blind mouse value scroll (center of screen)...")
                try:
                    vp = page.viewport_size
                    if vp:
                        page.mouse.move(vp['width'] / 2, vp['height'] / 2)
                        for _ in range(3):
                            page.mouse.wheel(0, 1000)
                            time.sleep(0.3)
                except Exception as e:
                    print(f"Fallback scroll error: {e}")
            
            # Random wait
            time.sleep(random.uniform(2, 4))
            
            # Check login or verify slider
            if page.query_selector('.login-mask') or "登录" in page.title():
                 print("Login interruption detected. Please handle in browser.")
                 time.sleep(5)

        # Save
        with open('comments.json', 'w', encoding='utf-8') as f:
            json.dump(comments_data, f, ensure_ascii=False, indent=2)
            
        print(f"Done. Saved {len(comments_data)} comments.")
        
        # Keep open for a bit
        time.sleep(2)
    
    finally:
        # Critical: Close context to ensure cookies/local storage are saved to the persistent dir
        try:
            if 'context' in locals():
                context.close()
                print("Browser context closed and session saved.")
            p.stop()
        except Exception as e:
            print(f"Cleanup error: {e}")

if __name__ == "__main__":
    target_url = os.getenv("DOUYIN_TARGET_URL", "https://www.douyin.com/note/7595975674542054897")
    scrape_douyin_comments(target_url)
