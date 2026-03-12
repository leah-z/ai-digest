#!/usr/bin/env python3
"""Daily AI News Digest for Product Managers — Chinese Edition"""

import feedparser
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")

OUTPUT_DIR = Path(__file__).parent / "docs"
SEEN_URLS_FILE = Path(__file__).parent / "seen_urls.json"


def load_seen_urls():
    """Build seen URLs from article links in all published digest HTML files."""
    import re
    seen = set()
    for html_file in OUTPUT_DIR.glob("????-??-??.html"):
        content = html_file.read_text(encoding="utf-8")
        seen.update(re.findall(r'<a href="(https?://[^"]+)" class="card-link"', content))
    return seen


def save_seen_urls(seen_urls):
    SEEN_URLS_FILE.write_text(json.dumps(sorted(seen_urls), indent=2))

SOURCES = [
    {"name": "TechCrunch AI", "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"name": "The Verge AI", "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"name": "MIT Technology Review", "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"name": "Product Hunt AI", "url": "https://www.producthunt.com/feed?category=artificial-intelligence"},
    {"name": "Lenny's Newsletter", "url": "https://www.lennysnewsletter.com/feed"},
    {"name": "Import AI", "url": "https://importai.substack.com/feed"},
    {"name": "Sequoia Capital", "url": "https://www.sequoiacap.com/feed/"},
    {"name": "Stratechery", "url": "https://stratechery.com/feed/"},
    {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/technology-lab"},
    {"name": "Product Talk", "url": "https://www.producttalk.org/feed"},
    {"name": "Every.to", "url": "https://every.to/chain-of-thought/feed"},
]

# Domains known to paywall most content
PAYWALLED_DOMAINS = {
    "technologyreview.com",
    "stratechery.com",
    "wsj.com",
    "ft.com",
    "bloomberg.com",
    "theinformation.com",
    "economist.com",
    "theathletic.com",
}

AI_KEYWORDS = {
    "ai", "artificial intelligence", "machine learning", "deep learning",
    "llm", "large language model", "gpt", "claude", "gemini", "chatgpt",
    "copilot", "generative", "neural", "openai", "anthropic", "deepmind",
    "automation", "agent", "chatbot", "nlp", "natural language", "foundation model",
    "diffusion", "transformer", "mistral", "llama", "multimodal", "prompt",
    "ml model", "ai model", "ai tool", "ai feature", "ai product",
}

def is_ai_related(title, desc):
    """Return True if the article is related to AI."""
    text = (title + " " + desc).lower()
    return any(kw in text for kw in AI_KEYWORDS)

def is_paywalled(link, desc):
    """Return True if the article is likely behind a paywall."""
    for domain in PAYWALLED_DOMAINS:
        if domain in link:
            return True
    # Short description is a strong signal of a paywall teaser
    if len(desc) < 150:
        return True
    return False


def fetch_articles(seen_urls):
    import re
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    articles = []
    for source in SOURCES:
        try:
            feed = feedparser.parse(source["url"])
            added = 0
            for entry in feed.entries:
                if added >= 2:
                    break
                link = entry.get("link", "")
                if link in seen_urls:
                    continue
                # Skip articles older than 7 days if date is available
                published = entry.get("published_parsed")
                if published:
                    import calendar
                    pub_dt = datetime.fromtimestamp(calendar.timegm(published), tz=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                desc = entry.get("summary", entry.get("description", ""))
                desc = re.sub(r"<[^>]+>", " ", desc).strip()
                desc = " ".join(desc.split())[:600]
                if is_paywalled(link, desc):
                    continue
                if not is_ai_related(entry.get("title", ""), desc):
                    continue
                articles.append({
                    "source": source["name"],
                    "title": entry.get("title", "").strip(),
                    "description": desc,
                    "link": link,
                })
                added += 1
            used = min(2, len(feed.entries))
            status = f"{len(feed.entries)} available, using {used}" if feed.entries else "0 articles"
            print(f"✓ {source['name']}: {status}")
        except Exception as e:
            print(f"✗ {source['name']}: {e}")
    print(f"\nTotal articles (up to 2 per source): {len(articles)}")
    return articles


def generate_digest(articles):
    articles_text = "\n\n".join([
        f"[{i+1}] Source: {a['source']}\nTitle: {a['title']}\nSummary: {a['description']}\nURL: {a['link']}"
        for i, a in enumerate(articles)
    ])

    prompt = f"""你是一位专为产品经理策划AI资讯的编辑。以下是今日的AI新闻文章，来自多个不同媒体：

{articles_text}

请选出最值得产品经理关注的5篇文章（如不足5篇则全选）。
重要：每个来源（source）最多只能选1篇，确保来源多样性。

为每篇选中的文章提供：
1. original_title：原标题（保持原文语言）
2. chinese_title：中文标题翻译
3. source：来源名称
4. url：原文链接
5. chinese_summary：2-3句中文摘要，简明扼要地说明核心内容
6. pm_tip：一句话说明为什么这对产品经理重要，以"💡 PM视角："开头

请以JSON数组格式返回，不要包含其他文字：
[
  {{
    "original_title": "...",
    "chinese_title": "...",
    "source": "...",
    "url": "...",
    "chinese_summary": "...",
    "pm_tip": "..."
  }}
]"""

    print(f"\nGenerating digest via OpenRouter ({OPENROUTER_MODEL})...")
    payload = json.dumps({
        "model": OPENROUTER_MODEL,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"API error {e.code}: {body}")
        raise
    text = result["choices"][0]["message"]["content"].strip()

    # Strip markdown code fences if present
    if "```" in text:
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```")[0]

    return json.loads(text.strip())


def generate_html(items, date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_display = date_obj.strftime("%Y年%m月%d日")
    date_en = date_obj.strftime("%B %d, %Y")

    cards_html = ""
    for i, item in enumerate(items, 1):
        cards_html += f"""
        <article class="card">
            <div class="card-number">{i:02d}</div>
            <div class="card-content">
                <div class="card-source">{item['source']}</div>
                <h2 class="card-title-zh">{item['chinese_title']}</h2>
                <h3 class="card-title-en">{item['original_title']}</h3>
                <p class="card-summary">{item['chinese_summary']}</p>
                <p class="card-tip">{item['pm_tip']}</p>
                <a href="{item['url']}" class="card-link" target="_blank" rel="noopener">阅读原文 →</a>
            </div>
        </article>"""

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI日报 · {date_display}</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background: #0f1117;
            color: #e1e4e8;
            min-height: 100vh;
            padding: 2rem 1rem;
            line-height: 1.7;
        }}

        .container {{
            max-width: 800px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 3rem;
            padding-bottom: 2rem;
            border-bottom: 1px solid #21262d;
        }}

        .header-label {{
            font-size: 0.8rem;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            color: #58a6ff;
            margin-bottom: 0.75rem;
        }}

        header h1 {{
            font-size: 2.2rem;
            font-weight: 700;
            color: #f0f6fc;
            margin-bottom: 0.5rem;
        }}

        .header-date {{
            color: #8b949e;
            font-size: 0.95rem;
        }}

        .header-sub {{
            margin-top: 0.75rem;
            font-size: 0.9rem;
            color: #8b949e;
        }}

        .card {{
            display: flex;
            gap: 1.25rem;
            background: #161b22;
            border: 1px solid #21262d;
            border-radius: 12px;
            padding: 1.5rem;
            margin-bottom: 1.25rem;
            transition: border-color 0.2s;
        }}

        .card:hover {{
            border-color: #388bfd;
        }}

        .card-number {{
            font-size: 1.8rem;
            font-weight: 800;
            color: #21262d;
            min-width: 2.5rem;
            text-align: right;
            padding-top: 0.1rem;
            user-select: none;
        }}

        .card-content {{
            flex: 1;
            min-width: 0;
        }}

        .card-source {{
            font-size: 0.75rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            color: #58a6ff;
            margin-bottom: 0.4rem;
        }}

        .card-title-zh {{
            font-size: 1.15rem;
            font-weight: 600;
            color: #f0f6fc;
            margin-bottom: 0.25rem;
            line-height: 1.4;
        }}

        .card-title-en {{
            font-size: 0.82rem;
            color: #6e7681;
            font-weight: 400;
            margin-bottom: 0.9rem;
            line-height: 1.4;
        }}

        .card-summary {{
            font-size: 0.93rem;
            color: #c9d1d9;
            margin-bottom: 0.85rem;
            line-height: 1.75;
        }}

        .card-tip {{
            font-size: 0.88rem;
            color: #e3b341;
            background: rgba(227, 179, 65, 0.08);
            border-left: 3px solid #e3b341;
            padding: 0.6rem 0.85rem;
            border-radius: 0 6px 6px 0;
            margin-bottom: 1rem;
            line-height: 1.6;
        }}

        .card-link {{
            font-size: 0.83rem;
            color: #58a6ff;
            text-decoration: none;
            font-weight: 500;
        }}

        .card-link:hover {{
            text-decoration: underline;
        }}

        footer {{
            text-align: center;
            margin-top: 3rem;
            padding-top: 2rem;
            border-top: 1px solid #21262d;
            color: #6e7681;
            font-size: 0.82rem;
        }}

        footer a {{
            color: #58a6ff;
            text-decoration: none;
        }}

        @media (max-width: 500px) {{
            .card-number {{ display: none; }}
            header h1 {{ font-size: 1.6rem; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-label">AI Daily Digest · For Product Managers</div>
            <h1>AI 日报</h1>
            <div class="header-date">{date_display} · {date_en}</div>
            <div class="header-sub">今日精选 5 条 AI 资讯，专为产品经理策划</div>
        </header>

        <main>{cards_html}
        </main>

        <footer>
            <p>由 AI 自动生成 · 资讯来源：TechCrunch、The Verge、MIT Technology Review、Product Hunt、Lenny's Newsletter、Import AI、Sequoia Capital、Stratechery、Ars Technica、Product Talk、Every.to</p>
            <p style="margin-top:0.5rem;"><a href="index.html">← 查看往期日报</a></p>
        </footer>
    </div>
</body>
</html>"""


def update_index(entries):
    """Rebuild the index page listing all past digests."""
    entries_html = ""
    for date_str, filename in sorted(entries, reverse=True):
        date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        date_display = date_obj.strftime("%Y年%m月%d日")
        date_en = date_obj.strftime("%B %d, %Y")
        entries_html += f"""
        <a href="{filename}" class="entry">
            <span class="entry-date">{date_display}</span>
            <span class="entry-en">{date_en}</span>
            <span class="entry-arrow">→</span>
        </a>"""

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI日报 · 往期归档</title>
    <style>
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC",
                         "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
            background: #0f1117;
            color: #e1e4e8;
            min-height: 100vh;
            padding: 2rem 1rem;
        }}
        .container {{ max-width: 600px; margin: 0 auto; }}
        header {{ text-align: center; margin-bottom: 2.5rem; }}
        .header-label {{
            font-size: 0.8rem;
            letter-spacing: 0.15em;
            text-transform: uppercase;
            color: #58a6ff;
            margin-bottom: 0.75rem;
        }}
        header h1 {{ font-size: 2rem; font-weight: 700; color: #f0f6fc; }}
        .entry {{
            display: flex;
            align-items: center;
            background: #161b22;
            border: 1px solid #21262d;
            border-radius: 10px;
            padding: 1rem 1.25rem;
            margin-bottom: 0.75rem;
            text-decoration: none;
            color: inherit;
            transition: border-color 0.2s;
        }}
        .entry:hover {{ border-color: #388bfd; }}
        .entry-date {{ font-size: 1rem; font-weight: 600; color: #f0f6fc; flex: 1; }}
        .entry-en {{ font-size: 0.82rem; color: #6e7681; margin-right: 1rem; }}
        .entry-arrow {{ color: #58a6ff; font-size: 1rem; }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="header-label">AI Daily Digest · Archive</div>
            <h1>往期日报</h1>
        </header>
        <main>{entries_html}
        </main>
    </div>
</body>
</html>"""

    (OUTPUT_DIR / "index.html").write_text(html, encoding="utf-8")


def main():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"{today}.html"

    print(f"=== AI Daily Digest · {today} ===\n")

    seen_urls = load_seen_urls()
    print(f"Fetching articles (skipping {len(seen_urls)} previously seen)...")
    articles = fetch_articles(seen_urls)

    if not articles:
        print("No new articles found. Exiting.")
        sys.exit(1)

    items = generate_digest(articles)
    print(f"Selected {len(items)} articles.\n")

    html = generate_html(items, today)
    output_file.write_text(html, encoding="utf-8")
    print(f"✓ Digest saved: {output_file}")

    # Record published URLs so they won't appear again
    seen_urls.update(item["url"] for item in items)
    save_seen_urls(seen_urls)
    print(f"✓ Recorded {len(items)} URLs to seen list ({len(seen_urls)} total)")

    # Rebuild index
    entries = [
        (f.stem, f.name)
        for f in OUTPUT_DIR.glob("????-??-??.html")
    ]
    update_index(entries)
    print(f"✓ Index updated: {OUTPUT_DIR / 'index.html'}")
    print(f"\nOpen in browser: file://{output_file}")


if __name__ == "__main__":
    main()
