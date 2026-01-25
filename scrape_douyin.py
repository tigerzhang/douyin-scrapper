import json
import time
import random
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
            "scrape_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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

        comments_data = []
        seen_ids = set()
        processed_threads = set() # Track threads that have been fully expanded
        no_new_data_count = 0
        max_no_new_data = 10 # Increased from 2 to allow more patience for lazy loading
        
        # New loop logic based on stability
        total_scrolls = 0
        
        while True:
            total_scrolls += 1
            print(f"--- Scroll #{total_scrolls} ---")
            
            # 1. Verification Check
            check_for_verification(page)

            # 2. Extract and Expand Comments Sequentially
            new_in_this_batch = 0
            try:
                # Find all comment items. We'll filter them to separate main comments from replies.
                all_items = page.query_selector_all('[data-e2e="comment-item"]')
                
                # Identify main comments: they are NOT inside a replyContainer
                main_comments = []
                for item in all_items:
                    is_reply = item.evaluate("el => !!el.closest('.replyContainer')")
                    if not is_reply:
                        main_comments.append(item)
                
                print(f"  -> Found {len(main_comments)} potential main threads in view.")
                
                for top_el in main_comments:
                    try:
                        # Quick ID to check if we processed this thread's expansion already
                        # We use a snippet of text + user to avoid full extraction cost here
                        try:
                            comment_item = top_el.query_selector('[data-e2e="comment-display-text"]')
                            tmp_user_el = top_el.query_selector('[data-e2e="comment-at"]')
                            tmp_user = tmp_user_el.inner_text().strip() if tmp_user_el else "Unknown"
                            tmp_text = comment_item.inner_text().strip()[:30] if comment_item else "NoText"
                            thread_fingerprint = f"{tmp_user}_{tmp_text}"
                        except Exception as e:
                            # print(f"Fingerprint error: {e}")
                            thread_fingerprint = None

                        if thread_fingerprint and thread_fingerprint in processed_threads:
                            # Skip heavy expansion logic if we've already done it for this thread
                            pass
                        else:
                            # --- LOCAL EXPANSION for this thread ---
                            local_expansion_pass = 0
                            max_local_passes = 15 # Reduced from 20 but made more robust
                            
                            while local_expansion_pass < max_local_passes:
                                # Target buttons more specifically
                                local_btns = top_el.query_selector_all('button, [role="button"], .reply-expand-btn, span, p')
                                expanded_in_this_pass = 0
                                
                                for btn in local_btns:
                                    try:
                                        if not btn.is_visible(): continue
                                        text = btn.inner_text().strip()
                                        if not text: continue
                                        
                                        is_expansion = False
                                        # Strict expansion logic
                                        if ("展开" in text or "更多" in text) and "收起" not in text:
                                            # Avoid clicking "Reply" or "Share" which might be caught by 'span' or 'p'
                                            if any(x in text for x in ["回复", "分享", "赞"]):
                                                # Use regex-like check: must have "展开" AND (digits or "回复")
                                                import re
                                                if re.search(r'展开\d+条回复|展开更多', text):
                                                    is_expansion = True
                                                else:
                                                    continue
                                            else:
                                                is_expansion = True
                                        elif "条回复" in text and any(char.isdigit() for char in text) and "收起" not in text:
                                            is_expansion = True
                                        elif "查看" in text and "回复" in text and "收起" not in text:
                                            is_expansion = True
                                            
                                        if is_expansion:
                                            if "评论(" in text: continue 
                                            h = btn.evaluate("el => el.offsetHeight")
                                            if h < 5: continue
                                            
                                            # print(f"    [DEBUG] Clicking expansion button: '{text}'")
                                            btn.click()
                                            expanded_in_this_pass += 1
                                            # Wait longer for expansion to happen
                                            time.sleep(random.uniform(2.0, 3.0)) 
                                            # Sometimes clicking one button expands others, so we re-scan
                                            break 
                                    except: continue
                                
                                if expanded_in_this_pass == 0: break
                                local_expansion_pass += 1
                                time.sleep(0.5)
                            
                            if thread_fingerprint:
                                processed_threads.add(thread_fingerprint)

                        # --- EXTRACTION for this thread ---
                        comment_data = self_extract_comment(top_el, image_dir)
                        if not comment_data: continue
                        
                        unique_id = f"{comment_data['user']}_{comment_data['content'][:20]}_{comment_data['time']}"
                        
                        # Find all replies nested INSIDE this main comment
                        replies = []
                        reply_container = top_el.query_selector('.replyContainer')
                        if reply_container:
                            reply_items = reply_container.query_selector_all('[data-e2e="comment-item"]')
                            for r_item in reply_items:
                                r_data = self_extract_comment(r_item, image_dir)
                                if r_data:
                                    replies.append(r_data)
                        
                        if unique_id not in seen_ids:
                            comment_data["replies"] = replies
                            seen_ids.add(unique_id)
                            comments_data.append(comment_data)
                            new_in_this_batch += 1
                        else:
                            # Main comment seen, check for new replies
                            existing_comment = next((c for c in comments_data if f"{c['user']}_{c['content'][:20]}_{c['time']}" == unique_id), None)
                            if existing_comment:
                                if "replies" not in existing_comment:
                                    existing_comment["replies"] = []
                                
                                for r in replies:
                                    r_uid = f"{r['user']}_{r['content'][:20]}_{r['time']}"
                                    if not any(f"{er['user']}_{er['content'][:20]}_{er['time']}" == r_uid for er in existing_comment["replies"]):
                                        existing_comment["replies"].append(r)
                                        new_in_this_batch += 1
                                        
                    except Exception as item_err:
                        # print(f"    Item Error: {item_err}")
                        continue
            except Exception as e:
                print(f"Extraction execution error: {e}")

            if new_in_this_batch > 0:
                # Count total items (including replies) for better progress logging
                total_items = len(comments_data) + sum(len(c.get("replies", [])) for c in comments_data)
                progress = f" (Progress: {total_items}/{expected_total})" if expected_total > 0 else ""
                print(f"  -> Extracted {new_in_this_batch} new comments{progress}. Unique Threads: {len(comments_data)}, Total Items: {total_items}")
                no_new_data_count = 0
            else:
                print(f"  -> No new comments extracted. (Attempt {no_new_data_count + 1}/{max_no_new_data})")
                no_new_data_count += 1
            
            if no_new_data_count >= max_no_new_data:
                print("Stopping: No new data found for several scrolls.")
                break

            # 2. Scroll Logic
            scrolled = False
            scroll_container = find_container(page)
            
            # Method A: Targeted Container Scroll
            if scroll_container:
                try:
                    # Attempt 1: Targeted scrollIntoView on the LAST comment
                    comment_items = scroll_container.query_selector_all('[data-e2e="comment-item"]')
                    if comment_items:
                        last_item = comment_items[-1]
                        print(f"  -> Scrolling to last comment in view...")
                        last_item.scroll_into_view_if_needed()
                        time.sleep(0.5)
                    
                    # Attempt 2: JS Direct Scroll with Event Dispatch
                    scroll_container.evaluate("""(el) => {
                        el.scrollTop = el.scrollHeight;
                        el.dispatchEvent(new Event('scroll', { bubbles: true }));
                        el.dispatchEvent(new Event('wheel', { bubbles: true }));
                    }""")
                    
                    # Attempt 3: Mouse Wheel on the right side
                    box = scroll_container.bounding_box()
                    if box:
                        target_x = box['x'] + box['width']/2
                        target_y = box['y'] + box['height']/2
                        page.mouse.move(target_x, target_y)
                        page.mouse.click(target_x, target_y) # Focus explicitly
                        for _ in range(5):
                            page.mouse.wheel(0, 1000)
                            time.sleep(0.1)
                    scrolled = True
                except Exception as e:
                    print(f"  [DEBUG] Scroll iteration error: {e}")
            
            if not scrolled:
                # Fallback for maximized windows: Target the right sidebar area
                print("Doing targeted sidebar scroll fallback...")
                try:
                    vp = page.viewport_size
                    if vp:
                        page.mouse.move(vp['width'] - 200, vp['height'] / 2)
                        for _ in range(5):
                            page.mouse.wheel(0, 1000)
                            time.sleep(0.1)
                except Exception as e:
                    print(f"Fallback scroll error: {e}")
            
            # 3. Targeted Wait for Loading to Clear
            print("Waiting for loading to clear...")
            wait_for_loading_to_clear(page)
            
            # Final slack wait
            time.sleep(random.uniform(1, 2))
            
            # Check login or verify slider
            if page.query_selector('.login-mask') or "登录" in page.title():
                 print("Login interruption detected. Please handle in browser.")
                 time.sleep(5)

        # Save
        result_file = os.path.join(target_dir, 'comments.json')
        with open(result_file, 'w', encoding='utf-8') as f:
            json.dump(comments_data, f, ensure_ascii=False, indent=2)
            
        print(f"Done. Saved {len(comments_data)} comments to {result_file}")
        
        # Update Manifest
        update_manifest(base_data_dir, url_id, url, page_title, len(comments_data))
        
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
