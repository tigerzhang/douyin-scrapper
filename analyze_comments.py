import json
from collections import Counter
import os

def analyze_comments(file_path):
    if not os.path.exists(file_path):
        print(f"Error: {file_path} not found.")
        return

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            comments = json.load(f)
    except Exception as e:
        print(f"Error reading JSON: {e}")
        return

    # Heuristic list of negative/sarcastic keywords based on context
    NEGATIVE_KEYWORDS = [
        "基本盘", "信息茧房", "遥遥领先", "赢", "赢麻了", 
        "偷着乐", "下大棋", "感恩", "耗材", "人矿", "软肋", 
        "奴役", "失业", "骂", "脑子", "低保", "糖霜苹果", 
        "质疑", "无脑", "1450", "行走的50w", "润", 
        "回旋镖", "这就是中国", "偷国"
    ]

    negative_by_location = Counter()
    total_comments = len(comments)
    negative_count = 0

    print(f"Analyzing {total_comments} comments using Keyword Matching...\n")
    print(f"{'User':<20} | {'Sentiment':<10} | {'Location':<10} | {'Content'}")
    print("-" * 100)

    for comment in comments:
        content = comment.get('content', '')
        location = comment.get('location', 'Unknown')
        
        if not content.strip():
            continue
            
        is_negative = False
        matched_keyword = ""
        
        for kw in NEGATIVE_KEYWORDS:
            if kw in content:
                is_negative = True
                matched_keyword = kw
                break
        
        sentiment_str = "Neutral"
        if is_negative:
            sentiment_str = "Negative"
            negative_count += 1
            negative_by_location[location] += 1
            # Print negative comment details immediately or store for listing
            
        # Truncate content for table display
        display_content = (content[:30] + '..') if len(content) > 30 else content
        # print(f"{comment.get('user', 'Anon')[:20]:<20} | ...") # Commenting out table for now to focus on list
    
    print("\n" + "="*80)
    print(f"LIST OF NEGATIVE COMMENTS ({negative_count})")
    print("="*80)
    
    for comment in comments:
        content = comment.get('content', '')
        # Re-check logic for printing (inefficient but simple given script structure)
        for kw in NEGATIVE_KEYWORDS:
             if kw in content:
                 loc = comment.get('location', 'Unknown')
                 user = comment.get('user', 'Anon')
                 print(f"[{loc}] {user}: {content}")
                 print(f"   -> Matched: {kw}")
                 print("-" * 40)
                 break

    print("\n" + "="*40)
    print("NEGATIVE COMMENTS SUMMARY BY LOCATION")
    print("="*40)
    if negative_by_location:
        for loc, count in negative_by_location.most_common():
            # Calculate percentage
            print(f"{loc:<10}: {count} negative comments")
    else:
        print("No negative comments found based on keywords.")
    
    print(f"\nTotal Analyzed: {total_comments}")
    print(f"Total Negative: {negative_count} ({negative_count/total_comments*100:.1f}%)")
    print(f"Keywords Checked: {', '.join(NEGATIVE_KEYWORDS)}")

if __name__ == "__main__":
    analyze_comments("comments.json")
