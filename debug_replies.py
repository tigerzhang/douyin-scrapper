import os
import time
from playwright.sync_api import sync_playwright
from dotenv import load_dotenv

load_dotenv()

def debug_replies(url, target_user=None, target_content=None):
    user_data_dir = os.path.join(os.getcwd(), "douyin_user_data")
    p = sync_playwright().start()
    
    print(f"Launching browser with user data dir: {user_data_dir}")
    context = p.chromium.launch_persistent_context(
        user_data_dir=user_data_dir,
        headless=False,  # Show browser for debugging
        channel="chrome",
        args=["--start-maximized"],
        no_viewport=True
    )
    
    page = context.pages[0] if context.pages else context.new_page()
    
    print(f"Navigating to {url}...")
    page.goto(url, timeout=60000)
    
    # Wait for page to load
    time.sleep(5)
    
    # Open comments if hidden
    print("Checking comment sidebar visibility...")
    if not page.is_visible('.comment-mainContent'):
        print("Sidebar hidden. Attempting to open...")
        try:
            # Try multiple selectors for the comment tab/button
            comment_tab = page.query_selector('[data-e2e="comment-switch-tab"]') or \
                          page.query_selector(r'text=/评论\(\d+\)/') or \
                          page.query_selector('.comment-tab-text')
            
            if comment_tab:
                print(f"Clicking comment tab: {comment_tab.inner_text()}")
                comment_tab.click()
                time.sleep(5)
            else:
                # If no tab, maybe it's a "Click to view comments" button
                print("No standard tab found, looking for alternative buttons...")
                alt_btn = page.query_selector('text="评论"')
                if alt_btn:
                    alt_btn.click()
                    time.sleep(5)
        except Exception as e:
            print(f"Tab click warning: {e}")
    
    # Find the specific comment
    search_desc = f"user='{target_user}'" if target_user else ""
    if target_content:
        search_desc += f" content='{target_content}'"
    print(f"Searching for comment: {search_desc}...")
    
    def find_container(page):
        potential_containers = page.query_selector_all('.comment-mainContent, [data-e2e="comment-list"], .comment-list-container')
        for c in potential_containers:
            if c.is_visible():
                return c
        return None

    # Scroll a bit to find it if it's not in view
    found = False
    for i in range(50): # Increased to 50 scrolls
        items = page.query_selector_all('[data-e2e="comment-item"]')
        print(f"Scroll {i}: {len(items)} total items in DOM.")
        
        # Log first and last comment in DOM for context
        if items:
            try:
                first_text = items[0].query_selector('.C7LroK_h').inner_text()[:30] if items[0].query_selector('.C7LroK_h') else "N/A"
                last_text = items[-1].query_selector('.C7LroK_h').inner_text()[:30] if items[-1].query_selector('.C7LroK_h') else "N/A"
                print(f"  DOM Range: '{first_text}' ... '{last_text}'")
            except: pass

        for item in items:
            try:
                content_el = item.query_selector('.C7LroK_h')
                user_el = item.query_selector('._uYOTNYZ')
                
                match = True
                if target_content and (not content_el or target_content not in content_el.inner_text()):
                    match = False
                if target_user and (not user_el or target_user not in user_el.inner_text()):
                    match = False

                if match and (content_el or user_el):
                    print(f"FOUND TARGET COMMENT!")
                    item.scroll_into_view_if_needed()
                    print(f"Full Text: {item.inner_text()}")
                    
                    # Multi-pass expansion to handle "Expand more" nested buttons
                    print("Starting multi-pass expansion...")
                    for pass_num in range(10):
                        btns = item.query_selector_all('button, [role="button"], span, p')
                        clicked_any = False
                        for btn in btns:
                            try:
                                if not btn.is_visible(): continue
                                text = btn.inner_text().strip()
                                if not text: continue
                                
                                is_expansion = False
                                if ("展开" in text or "更多" in text) and "收起" not in text:
                                    if any(x in text for x in ["回复", "分享", "赞"]):
                                        import re
                                        # Match "展开X条回复" or "展开更多" or "更多回复"
                                        if re.search(r'展开\d+条回复|展开更多|更多回复', text):
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
                                    print(f"  [Pass {pass_num}] Clicking expansion button: '{text}'")
                                    btn.click()
                                    time.sleep(3)
                                    clicked_any = True
                                    break # Re-scan DOM after click
                            except: pass
                        if not clicked_any:
                            print("  No more expansion buttons found.")
                            break
                    
                    # Check and print replies
                    reply_container = item.query_selector('.replyContainer')
                    if reply_container:
                        print("\n--- Extracted Replies ---")
                        replies = reply_container.query_selector_all('[data-e2e="comment-item"]')
                        for idx, r in enumerate(replies):
                            try:
                                user_el = r.query_selector('._uYOTNYZ')
                                r_user = "Unknown"
                                r_reply_to = None
                                if user_el:
                                    links = user_el.query_selector_all('a')
                                    if len(links) >= 2:
                                        r_user = links[0].inner_text().strip()
                                        r_reply_to = links[1].inner_text().strip()
                                    else:
                                        r_user = user_el.inner_text().strip()
                                
                                # Clean up author tag
                                if "\n作者" in r_user: 
                                    r_user = r_user.replace("\n作者", "").strip() + " [Author]"
                                
                                display_name = r_user
                                if r_reply_to:
                                    if "\n作者" in r_reply_to: 
                                        r_reply_to = r_reply_to.replace("\n作者", "").strip() + " [Author]"
                                    display_name = f"{r_user} ▶ {r_reply_to}"

                                r_content = r.query_selector('.C7LroK_h').inner_text().strip() if r.query_selector('.C7LroK_h') else "[No Content]"
                                print(f"  {idx+1}. {display_name}: {r_content}")
                            except: pass
                        print(f"Total visible replies: {len(replies)}\n")
                    else:
                        print("No .replyContainer found after expansion.")

                    # Capture result
                    item.screenshot(path="debug_comment.png")
                    found = True
                    break
            except: pass
        
        if found: break
        
        # Scroll logic
        container = find_container(page)
        if container:
            container.evaluate("el => el.scrollTop = el.scrollHeight")
        else:
            page.mouse.wheel(0, 3000)
        time.sleep(2)
        
        # Check for verification
        if page.query_selector('.captcha-container'):
            print("Verification detected! Please resolve it.")
            time.sleep(10)
    
    if not found:
        print(f"Could not find comment by {target_user}")
        page.screenshot(path="debug_full_page.png")

    print("Finished debugging. Keeping browser open for 10 seconds...")
    time.sleep(10)
    context.close()
    p.stop()

if __name__ == "__main__":
    target_url = "https://v.douyin.com/sUt6tM1Aaic/"
    debug_replies(
        target_url, 
        target_user="MicroCloud", 
        target_content="穷的只能靠精神安慰了，你就放过他们吧，让他们自生自灭"
    )
