import json
import time
import random
import re
import os
import requests
import hashlib
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

# Load environment variables
load_dotenv()

def check_for_verification(page):
    """Checks for captcha or verification overlays and waits for manual resolution."""
    verification_selectors = [
        '.captcha-container',
        '#captcha_container',
        '.verify-board',
        '#captcha_container',
        '.vc-mask',
        '.captcha-modal',
        '[class*="captcha"]',
        '[class*="verify"]'
    ]
    
    found_any = False
    for selector in verification_selectors:
        try:
            el = page.query_selector(selector)
            if el and el.is_visible():
                found_any = True
                break
        except:
            continue
    
    # Check for captcha iframe if selectors didn't match
    if not found_any:
        try:
            iframes = page.query_selector_all('iframe')
            for iframe in iframes:
                src = iframe.get_attribute('src') or ""
                if "verifycenter/captcha" in src or "captcha" in src.lower():
                    found_any = True
                    break
        except:
             pass
            
    if found_any:
        print("\n!!! VERIFICATION DETECTED !!!")
        print("Please resolve the captcha/verification in the browser window.")
        print("Waiting for verification to be dismissed...")
        last_log = time.time()
        while True:
            still_visible = False
            for selector in verification_selectors:
                try:
                    el = page.query_selector(selector)
                    if el and el.is_visible():
                        still_visible = True
                        break
                except:
                    continue
            if not still_visible:
                print("Verification cleared. Resuming...\n")
                break
            if time.time() - last_log > 10:
                print("...Still waiting for verification...")
                last_log = time.time()
            time.sleep(2)
        return True
    return False

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

def self_extract_comment(item, image_dir=None):
    """Helper to extract data from a single comment/reply item."""
    try:
        # Nickname extraction
        user_el = item.query_selector('._uYOTNYZ')
        user_text = "Unknown"
        reply_to = None
        
        if user_el:
            # Check for "A reply to B" structure (multiple links)
            links = user_el.query_selector_all('a')
            if len(links) >= 2:
                # Format: User A -> User B
                user_text = links[0].inner_text().strip()
                reply_to = links[1].inner_text().strip()
                # print(f"DEBUG: Found reply-to: {user_text} -> {reply_to}")
            else:
                user_text = user_el.inner_text().strip()

            # Clean Author tag
            if "\n作者" in user_text:
                user_text = user_text.replace("\n作者", "").strip() + " [Author]"
            if reply_to and "\n作者" in reply_to:
                reply_to = reply_to.replace("\n作者", "").strip() + " [Author]"

        # Content extraction
        content_el = item.query_selector('.C7LroK_h')
        content_text = content_el.inner_text().strip() if content_el else "[No Content]"
        if content_text == "[No Content]": return None

        # Meta extraction
        msg_time = ""
        msg_location = ""
        try:
            meta_el = item.query_selector('.fJhvAqos')
            if not meta_el:
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
        except: pass

        # Image extraction
        image_path = None
        if image_dir:
            try:
                img_els = item.query_selector_all('img')
                for img in img_els:
                    width = img.evaluate("el => el.naturalWidth")
                    if width > 30: 
                        src = img.get_attribute('src')
                        if src and src.startswith('http'):
                            url_hash = hashlib.md5(src.encode()).hexdigest()
                            filename = f"{url_hash}.jpg"
                            local_path = os.path.join(image_dir, filename)
                            if not os.path.exists(local_path):
                                response = requests.get(src, timeout=10)
                                if response.status_code == 200:
                                    with open(local_path, 'wb') as img_f:
                                        img_f.write(response.content)
                            if os.path.exists(local_path):
                                image_path = os.path.join("images", filename)
                            break
            except: pass

        return {
            "user": user_text,
            "reply_to": reply_to,
            "content": content_text,
            "time": msg_time,
            "location": msg_location,
            "image_path": image_path,
            "scrape_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "replies_scraped": False,
            "replies": []
        }
    except:
        return None

def update_manifest(base_dir, url_id, url, title, count):
    """Updates the global manifest.json with the latest scrape info."""
    manifest_path = os.path.join(base_dir, "manifest.json")
    manifest = []
    
    if os.path.exists(manifest_path):
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest = json.load(f)
        except:
            pass
            
    # Update or add entry
    entry = {
        "id": url_id,
        "url": url,
        "title": title,
        "scrape_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "comment_count": count
    }
    
    # Remove existing entry for this ID if it exists
    manifest = [item for item in manifest if item["id"] != url_id]
    manifest.insert(0, entry) # Most recent first
    
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"Updated manifest: {manifest_path}")

def scrape_douyin_comments(url):
    print(f"Starting scrape_douyin_comments for {url}...")
    # Extract unique ID from URL for directory name
    parsed_url = urlparse(url)
    url_path = parsed_url.path.strip('/')
    url_id = url_path.split('/')[-1] if url_path else "default"
    
    # Define base and specific directories
    base_data_dir = os.path.join(os.getcwd(), "scraped_data")
    target_dir = os.path.join(base_data_dir, url_id)
    image_dir = os.path.join(target_dir, "images")
    user_data_dir = os.path.join(os.getcwd(), "douyin_user_data")
    
    if not os.path.exists(image_dir):
        os.makedirs(image_dir)
        print(f"Created directory: {image_dir}")
    
    p = sync_playwright().start()
    try:
        # Use persistent context to save login state
        print(f"Launching browser with user data dir: {user_data_dir}")
        is_headless = os.getenv("HEADLESS", "true").lower() == "true"
        print(f"Headless mode: {is_headless}")
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=user_data_dir,
            headless=is_headless,
            channel="chrome", 
            args=["--start-maximized", "--no-sandbox", "--disable-setuid-sandbox"],
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            no_viewport=True
        )
        
        page = context.pages[0] if context.pages else context.new_page()
        
        # Approximate maximization on Mac by matching available screen size
        try:
            screen_size = page.evaluate("() => ({ width: window.screen.availWidth, height: window.screen.availHeight })")
            if screen_size['width'] > 0 and screen_size['height'] > 0:
                print(f"Detected screen size: {screen_size['width']}x{screen_size['height']}")
                page.set_viewport_size(screen_size)
        except Exception as e:
            print(f"Viewport adjustment warning: {e}")

        print(f"Navigating to {url}...")
        try:
            page.goto(url, timeout=60000)
            page.wait_for_load_state("domcontentloaded")
        except Exception as e:
            print(f"Navigation warning: {e}")

        # Strict Login Verification
        verify_login_status(page)

        # Get Page Title for Manifest
        page_title = page.title()
        # Clean up Douyin title suffix if present
        if " - 抖音" in page_title:
            page_title = page_title.split(" - 抖音")[0]
        print(f"Page Title: {page_title}")
        
        # Try to extract total comment count from header for progress tracking
        expected_total = 0
        try:
            tab_text = page.query_selector('[data-e2e="comment-switch-tab"], .comment-tab-text').inner_text()
            # Extract number from "评论(1190)" or similar
            import re
            match = re.search(r'\((\d+)\)', tab_text) or re.search(r'(\d+)', tab_text)
            if match:
                expected_total = int(match.group(1))
                print(f"Targeting total comments: {expected_total}")
        except:
            pass

        # Force open comments if hidden
        print("Checking comment sidebar visibility...")
        
        # 1. Close any blocking modals first
        blocking_selectors = [
            '.login-mask', 
            '#login-full-panel', 
            '[data-e2e="login-close"]', 
            '.trust-login-dialog-mask',
            '.vc-mask'
        ]
        
        for _ in range(5): # Quick initial checks
            for selector in blocking_selectors:
                try:
                    modal = page.query_selector(selector)
                    if modal and modal.is_visible():
                        print(f"!!! BLOCKING MODAL DETECTED: {selector} !!!")
                        # Try to find a close button within or use escape key
                        close_btn = modal.query_selector('[class*="close"], [class*="Close"]')
                        if close_btn:
                            print("Attempting to click close button...")
                            close_btn.click()
                        else:
                            print("No clear close button. Pressing Escape...")
                            page.keyboard.press("Escape")
                        time.sleep(2)
                except: pass

        # 2. Attempt to click comment tab
        try:
            # We look for the tab multiple times
            for attempt in range(5):
                if page.is_visible('.comment-mainContent'):
                    print("Comments section is already visible.")
                    break
                    
                comment_tab = page.query_selector('[data-e2e="comment-switch-tab"]') or page.query_selector(r'text=/评论\(\d+\)/') 
                if comment_tab:
                    print(f"Attempt {attempt+1}: Clicking comment tab...")
                    # Use force=True because sometimes Douyin has invisible overlays even after modals are "gone"
                    comment_tab.click(force=True, timeout=5000)
                    time.sleep(3)
                    if page.is_visible('.comment-mainContent'):
                        print(">> SUCCESS: Comments tab opened.")
                        break
                else:
                    print(f"Attempt {attempt+1}: Comment tab not found in DOM yet. Waiting...")
                    time.sleep(2)
        except Exception as e:
            print(f"Tab click warning: {e}")
            print("Tip: If a login modal is still blocking, please resolve it manually.")
                
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
            
        def find_container(page):
            try:
                # Target the sidebar comment container specifically
                potential_containers = page.query_selector_all('.comment-mainContent, [data-e2e="comment-list"], .comment-list-container')
                vis_containers = []
                for c in potential_containers:
                    try:
                        if c.is_visible():
                            rect = c.bounding_box()
                            if rect and rect['width'] > 100 and rect['height'] > 100:
                                vis_containers.append((c, rect['height'], c.evaluate("el => el.scrollHeight")))
                    except: continue
                
                if vis_containers:
                    # Prefer the one with the largest scrollHeight
                    vis_containers.sort(key=lambda x: x[2], reverse=True)
                    winner = vis_containers[0]
                    print(f"  [DEBUG] Container Match: H={winner[1]}, ScrollH={winner[2]}")
                    return winner[0]
                else:
                    print("  [DEBUG] No visible comment container found matching criteria.")
            except Exception as e: 
                print(f"  [DEBUG] find_container error: {e}")
            return None

        def wait_for_loading_to_clear(page, timeout=10):
            """Wait for '加载中' or loading spinners to disappear."""
            start_time = time.time()
            # print(f"  [DEBUG] Waiting for loading to clear...")
            while time.time() - start_time < timeout:
                try:
                    # Check for common loading text or elements
                    loading = page.query_selector('div:has-text("加载中"), div:has-text("努力加载中"), .loading-icon')
                    if not loading or not loading.is_visible():
                        # Also check if the container scroll height stopped changing? Overkill for now.
                        return True
                    # print(f"  [DEBUG] Still loading... ({(time.time() - start_time):.1f}s)")
                    time.sleep(1.0)
                except:
                    return True
            return False

        # Load existing data if resuming
        result_file = os.path.join(target_dir, 'comments.json')
        comments_data = []
        seen_ids = set()
        if os.path.exists(result_file):
            try:
                with open(result_file, 'r', encoding='utf-8') as f:
                    comments_data = json.load(f)
                    for c in comments_data:
                        uid = f"{c['user']}_{c['content'][:20]}_{c['time']}"
                        seen_ids.add(uid)
                print(f"Resuming with {len(comments_data)} existing comments.")
            except: pass

        # --- Phase 1: Rapid Top-Level Comment Collection ---
        print("\n--- PHASE 1: Collecting Top-Level Comments ---")
        no_new_data_count = 0
        max_no_new_data = 15
        total_scrolls = 0
        
        while True:
            total_scrolls += 1
            check_for_verification(page)
            
            # Find main comments in current view
            all_items = page.query_selector_all('[data-e2e="comment-item"]')
            new_in_this_scroll = 0
            seen_in_this_scroll = 0
            
            for item in all_items:
                try:
                    # Check if it's a main comment
                    is_reply = item.evaluate("el => !!el.closest('.replyContainer')")
                    if is_reply: continue
                    
                    c_data = self_extract_comment(item, image_dir)
                    if not c_data: continue
                    
                    uid = f"{c_data['user']}_{c_data['content'][:20]}_{c_data['time']}"
                    if uid not in seen_ids:
                        seen_ids.add(uid)
                        comments_data.append(c_data)
                        new_in_this_scroll += 1
                    else:
                        seen_in_this_scroll += 1
                except: continue
            
            if new_in_this_scroll > 0:
                print(f"  Scroll #{total_scrolls}: Found {new_in_this_scroll} new comments. (Total: {len(comments_data)})")
                no_new_data_count = 0
                # Intermediate save
                with open(result_file, 'w', encoding='utf-8') as f:
                    json.dump(comments_data, f, ensure_ascii=False, indent=2)
            else:
                no_new_data_count += 1
                if seen_in_this_scroll > 0:
                    print(f"  Scroll #{total_scrolls}: Re-traversing {seen_in_this_scroll} known comments... ({no_new_data_count}/{max_no_new_data})")
                else:
                    print(f"  Scroll #{total_scrolls}: No items found in view. ({no_new_data_count}/{max_no_new_data})")
            
            if no_new_data_count >= max_no_new_data:
                print("Phase 1 Complete: No more new top-level comments found.")
                break

            # Scroll down
            scroll_container = find_container(page)
            if scroll_container:
                scroll_container.evaluate("el => el.scrollTop = el.scrollHeight")
            else:
                page.mouse.wheel(0, 3000)
            
            wait_for_loading_to_clear(page)
            time.sleep(random.uniform(1.0, 2.0))

        # --- Phase 2: Targeted Reply Expansion ---
        print("\n--- PHASE 2: Expanding Replies ---")
        
        # Scroll back to top to begin systematic expansion
        scroll_container = find_container(page)
        if scroll_container:
            print("Scrolling back to top for Phase 2...")
            scroll_container.evaluate("el => el.scrollTop = 0")
            time.sleep(2)

        for i, comment in enumerate(comments_data):
            if comment.get("replies_scraped"):
                continue
            
            print(f"  [{i+1}/{len(comments_data)}] Searching for: {comment['user']} - {comment['content'][:30]}...")
            
            # Find the comment element in the DOM
            target_uid = f"{comment['user']}_{comment['content'][:20]}_{comment['time']}"
            target_el = None
            
            # Re-scroll until found (since it's a virtualized list)
            max_re_scrolls = 20 # Reduced for debugging
            for rs in range(max_re_scrolls):
                try:
                    all_items = page.query_selector_all('[data-e2e="comment-item"]')
                    # print(f"    Scroll {rs}: {len(all_items)} items in DOM.")
                    for item in all_items:
                        try:
                            # Extract quick fingerprint
                            user_el = item.query_selector('._uYOTNYZ')
                            content_el = item.query_selector('.C7LroK_h')
                            if not user_el or not content_el: continue
                            
                            u_text = user_el.inner_text().strip()
                            if "\n作者" in u_text: u_text = u_text.replace("\n作者", "").strip() + " [Author]"
                            
                            # Match UID
                            if u_text == comment['user'] and comment['content'][:20] in content_el.inner_text():
                                target_el = item
                                break
                        except: continue
                    
                    if target_el: break
                    
                    # If not found, scroll down
                    if scroll_container:
                        scroll_container.evaluate("el => el.scrollTop += 500")
                    else:
                        page.mouse.wheel(0, 500)
                    time.sleep(0.3)
                except Exception as e:
                    print(f"    Error during re-scroll {rs}: {e}")
                    break
            
            if not target_el:
                print(f"    [-] Could not find in DOM after {max_re_scrolls} scrolls. (User: {comment['user']})")
                continue
            
            try:
                print(f"    [+] Found. Scrolling...")
                target_el.scroll_into_view_if_needed(timeout=5000)
                time.sleep(1)
            except Exception as e:
                print(f"    [-] Scroll failed: {e}. Moving to next thread.")
                continue
            
            # Robust Expansion Loop (inspired by debug_replies.py)
            expansion_passes = 0
            max_expansion_passes = 15
            any_expanded = False
            
            while expansion_passes < max_expansion_passes:
                clicked_any = False
                btns = target_el.query_selector_all('button, [role="button"], span, p')
                
                for btn in btns:
                    try:
                        if not btn.is_visible(): continue
                        text = btn.inner_text().strip()
                        if not text: continue
                        
                        is_expansion = False
                        if ("展开" in text or "更多" in text or "条回复" in text or "查看" in text) and "收起" not in text:
                            if any(x in text for x in ["回复", "分享", "赞"]):
                                import re
                                if re.search(r'展开\d+条回复|展开更多|更多回复', text):
                                    is_expansion = True
                                else: continue
                            else: is_expansion = True
                        
                        if is_expansion:
                            # print(f"      Clicking: {text}")
                            btn.click()
                            clicked_any = True
                            any_expanded = True
                            time.sleep(random.uniform(2.0, 3.5))
                            break # Re-scan DOM
                    except: continue
                
                if not clicked_any: break
                expansion_passes += 1
            
            # Extract replies
            replies = []
            reply_container = target_el.query_selector('.replyContainer')
            if reply_container:
                reply_items = reply_container.query_selector_all('[data-e2e="comment-item"]')
                for r_item in reply_items:
                    r_data = self_extract_comment(r_item, image_dir)
                    if r_data:
                        replies.append(r_data)
            
            comment["replies"] = replies
            comment["replies_scraped"] = True
            print(f"    Found {len(replies)} replies.")
            
            # Save progress after EACH thread for maximum stability
            with open(result_file, 'w', encoding='utf-8') as f:
                json.dump(comments_data, f, ensure_ascii=False, indent=2)

        print(f"\nScraping Complete. Final count: {len(comments_data)} threads.")
        update_manifest(base_data_dir, url_id, url, page_title, len(comments_data))
    
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
    target_url = "https://v.douyin.com/sUt6tM1Aaic/"
    scrape_douyin_comments(target_url)
