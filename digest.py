#!/usr/bin/env python3
"""Daily AI News Digest for Product Managers — Chinese Edition"""

import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args, **_kwargs):
        return False

load_dotenv(Path(__file__).parent / ".env")

OPENROUTER_API_KEY = os.environ["OPENROUTER_API_KEY"]
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "google/gemini-2.0-flash-exp:free")
DIGEST_TIMEZONE = os.getenv("DIGEST_TIMEZONE", "Asia/Singapore")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

OUTPUT_DIR = Path(__file__).parent / "docs"
SEEN_URLS_FILE = Path(__file__).parent / "seen_urls.json"
ARCHIVE_HIDE_ON_OR_BEFORE = "2026-05-15"
MAX_FOLLOW_BUILDERS_TWEETS = 8
MAX_FOLLOW_BUILDERS_PODCASTS = 3
MAX_FOLLOW_BUILDERS_BLOGS = 3

FOLLOW_BUILDERS_FEEDS = {
    "x": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-x.json",
    "podcasts": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-podcasts.json",
    "blogs": "https://raw.githubusercontent.com/zarazhangrui/follow-builders/main/feed-blogs.json",
}


def load_seen_urls():
    """Build seen URLs from article links in all published digest HTML files."""
    import re
    seen = set()
    for html_file in OUTPUT_DIR.glob("????-??-??.html"):
        content = html_file.read_text(encoding="utf-8")
        seen.update(re.findall(r'<a href="(https?://[^"]+)" class="card-link"', content))
    return seen


def save_seen_urls(seen_urls):
    SEEN_URLS_FILE.write_text(json.dumps(sorted(seen_urls), indent=2) + "\n")

def clean_text(text, limit=600):
    """Remove markup and collapse whitespace."""
    import re
    text = re.sub(r"<[^>]+>", " ", text or "")
    return " ".join(text.split())[:limit]


def parse_iso_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def fetch_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ai-digest/1.0 (+https://github.com/)"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def fetch_follow_builders_articles(seen_urls, cutoff):
    """Fetch curated builders, podcasts, and blog posts from follow-builders."""
    articles = []
    used_urls = set(seen_urls)

    def add_article(article):
        link = article["link"]
        if link in used_urls:
            return
        used_urls.add(link)
        articles.append(article)

    try:
        data = fetch_json(FOLLOW_BUILDERS_FEEDS["x"])
        tweets = []
        for builder in data.get("x", []):
            for tweet in builder.get("tweets", []):
                created_at = parse_iso_datetime(tweet.get("createdAt"))
                if created_at and created_at < cutoff:
                    continue
                text = clean_text(tweet.get("text", ""), 900)
                if not text:
                    continue
                tweets.append({
                    "builder": builder.get("name", "Unknown builder"),
                    "handle": builder.get("handle", ""),
                    "tweet": tweet,
                    "text": text,
                    "score": (
                        int(tweet.get("likes") or 0)
                        + int(tweet.get("retweets") or 0) * 4
                        + int(tweet.get("replies") or 0) * 2
                    ),
                })
        for item in sorted(tweets, key=lambda t: t["score"], reverse=True)[:MAX_FOLLOW_BUILDERS_TWEETS]:
            tweet = item["tweet"]
            handle = f"@{item['handle']}" if item["handle"] else item["builder"]
            add_article({
                "kind": "x",
                "source": f"Builder: {item['builder']}",
                "title": f"{handle} on AI building: {item['text'][:100]}",
                "description": (
                    f"X post from {item['builder']} ({handle}). "
                    f"Engagement: {tweet.get('likes', 0)} likes, "
                    f"{tweet.get('retweets', 0)} reposts. {item['text']}"
                )[:1200],
                "link": tweet.get("url", ""),
            })
        print(f"✓ Follow Builders X: {len(tweets)} available, using {min(len(tweets), MAX_FOLLOW_BUILDERS_TWEETS)}")
    except Exception as e:
        print(f"✗ Follow Builders X: {e}")

    try:
        data = fetch_json(FOLLOW_BUILDERS_FEEDS["podcasts"])
        podcasts = []
        for episode in data.get("podcasts", []):
            published_at = parse_iso_datetime(episode.get("publishedAt"))
            if published_at and published_at < cutoff:
                continue
            transcript = clean_text(episode.get("transcript", ""), 1400)
            title = clean_text(episode.get("title", ""), 180)
            if not title:
                continue
            podcasts.append({
                "episode": episode,
                "title": title,
                "transcript": transcript,
                "published_at": published_at or datetime.min.replace(tzinfo=timezone.utc),
            })
        podcasts.sort(key=lambda p: p["published_at"], reverse=True)
        for item in podcasts[:MAX_FOLLOW_BUILDERS_PODCASTS]:
            episode = item["episode"]
            add_article({
                "kind": "podcast",
                "source": f"Podcast: {episode.get('name', 'Follow Builders')}",
                "title": item["title"],
                "description": (
                    f"Recent AI builder podcast episode from {episode.get('name', 'Follow Builders')}. "
                    f"Transcript excerpt: {item['transcript']}"
                )[:1400],
                "link": episode.get("url", ""),
            })
        print(f"✓ Follow Builders Podcasts: {len(podcasts)} available, using {min(len(podcasts), MAX_FOLLOW_BUILDERS_PODCASTS)}")
    except Exception as e:
        print(f"✗ Follow Builders Podcasts: {e}")

    try:
        data = fetch_json(FOLLOW_BUILDERS_FEEDS["blogs"])
        blogs = []
        for post in data.get("blogs", []):
            published_at = parse_iso_datetime(post.get("publishedAt") or post.get("date"))
            if published_at and published_at < cutoff:
                continue
            title = clean_text(post.get("title", ""), 180)
            link = post.get("url") or post.get("link") or ""
            body = clean_text(
                post.get("summary") or post.get("description") or post.get("content") or post.get("text") or "",
                1000,
            )
            if not title or not link:
                continue
            blogs.append({
                "source": post.get("name") or post.get("source") or "Follow Builders Blog",
                "title": title,
                "description": body,
                "link": link,
                "published_at": published_at or datetime.min.replace(tzinfo=timezone.utc),
            })
        blogs.sort(key=lambda p: p["published_at"], reverse=True)
        for post in blogs[:MAX_FOLLOW_BUILDERS_BLOGS]:
            add_article({
                "kind": "blog",
                "source": f"Builder Blog: {post['source']}",
                "title": post["title"],
                "description": post["description"],
                "link": post["link"],
            })
        print(f"✓ Follow Builders Blogs: {len(blogs)} available, using {min(len(blogs), MAX_FOLLOW_BUILDERS_BLOGS)}")
    except Exception as e:
        print(f"✗ Follow Builders Blogs: {e}")

    return [article for article in articles if article["link"]]


def fetch_articles(seen_urls):
    from datetime import timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)
    articles = fetch_follow_builders_articles(seen_urls, cutoff)
    print(f"\nTotal article candidates: {len(articles)}")
    return articles


def strip_json_fences(text):
    text = text.strip()
    if "```" in text:
        text = text.split("```", 1)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.split("```", 1)[0]
    return text.strip()


def validate_digest(digest, known_urls):
    """Keep only section items that point back to fetched follow-builders URLs."""
    cleaned = {}
    for section in ("x", "blogs", "podcasts"):
        cleaned[section] = []
        for item in digest.get(section, []):
            url = item.get("url")
            if url not in known_urls:
                continue
            heading = clean_text(item.get("heading", ""), 160)
            summary = clean_text(item.get("summary", ""), 900)
            if heading and summary:
                cleaned[section].append({
                    "heading": heading,
                    "summary": summary,
                    "url": url,
                })
    return cleaned


def generate_digest(articles):
    articles_text = "\n\n".join([
        (
            f"[{i+1}] Type: {a['kind']}\n"
            f"Source: {a['source']}\n"
            f"Title: {a['title']}\n"
            f"Content: {a['description']}\n"
            f"URL: {a['link']}"
        )
        for i, a in enumerate(articles)
    ])

    prompt = f"""你正在生成一份中文 AI Builders Digest。内容只来自 follow-builders 的中央 feed。
请学习并遵守这个渲染结构：
- 先放 PODCASTS：播客单集的底线和关键洞察。
- 再放 OFFICIAL BLOGS：AI 公司或 builder blog 的文章。
- 最后放 X / TWITTER：每位 builder 的观点、产品发布、技术判断或行业洞察。

{articles_text}

请输出最值得产品经理和 AI builder 关注的内容：
- X / TWITTER 最多 5 条
- OFFICIAL BLOGS 最多 3 条
- PODCASTS 最多 2 条

绝对规则：
- 只能使用上面给出的内容，不要编造。
- 每一条都必须带原始 URL。
- 不要写 @handle，Telegram 会误识别；可以写“handle on X”。
- 跳过没有实质信息的帖子。
- 中文表达要短、清晰、适合手机阅读。

请只返回 JSON object，不要包含其他文字：
{{
  "x": [
    {{
      "heading": "作者/来源 + 一句话主题",
      "summary": "2-4 句中文摘要，强调为什么值得关注。",
      "url": "原始 URL"
    }}
  ],
  "blogs": [
    {{
      "heading": "Blog 名称或文章标题",
      "summary": "2-4 句中文摘要。",
      "url": "原始 URL"
    }}
  ],
  "podcasts": [
    {{
      "heading": "播客名 - 单集标题",
      "summary": "Bottom line + 2-3 个关键洞察，用中文自然表达。",
      "url": "原始 URL"
    }}
  ]
}}"""

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
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                result = json.loads(resp.read())
            break
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(f"API error {e.code}: {body}")
            raise
        except (TimeoutError, urllib.error.URLError, OSError) as e:
            if attempt == 2:
                raise
            wait = 2 ** attempt
            print(f"OpenRouter request failed ({e}); retrying in {wait}s...")
            time.sleep(wait)
    text = result["choices"][0]["message"]["content"].strip()

    digest = validate_digest(
        json.loads(strip_json_fences(text)),
        {article["link"] for article in articles},
    )
    if not any(digest.values()):
        raise ValueError("Model response did not include any known article URLs.")

    return digest


def render_section_html(title, items):
    if not items:
        return ""

    cards_html = f"""
        <section class="section">
            <h2 class="section-title">{escape(title)}</h2>"""
    for item in items:
        heading = escape(item["heading"])
        summary = escape(item["summary"])
        url = escape(item["url"], quote=True)
        cards_html += f"""
            <article class="card">
                <div class="card-content">
                    <h3 class="card-title-zh">{heading}</h3>
                    <p class="card-summary">{summary}</p>
                    <a href="{url}" class="card-link" target="_blank" rel="noopener">阅读原文 →</a>
                </div>
            </article>"""
    cards_html += """
        </section>"""
    return cards_html


def render_text_digest(digest, date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_en = date_obj.strftime("%B %d, %Y")
    lines = [
        f"AI Builders Digest — {date_en}",
        "",
    ]

    sections = [
        ("PODCASTS", digest.get("podcasts", [])),
        ("OFFICIAL BLOGS", digest.get("blogs", [])),
        ("X / TWITTER", digest.get("x", [])),
    ]
    for title, items in sections:
        if not items:
            continue
        lines.extend([title, ""])
        for item in items:
            lines.extend([
                item["heading"],
                item["summary"],
                item["url"],
                "",
            ])

    lines.append("Generated through the Follow Builders skill: https://github.com/zarazhangrui/follow-builders")
    return "\n".join(lines).strip() + "\n"


def generate_html(digest, date_str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")
    date_display = date_obj.strftime("%Y年%m月%d日")
    date_en = date_obj.strftime("%B %d, %Y")

    sections_html = "\n".join([
        render_section_html("PODCASTS", digest.get("podcasts", [])),
        render_section_html("OFFICIAL BLOGS", digest.get("blogs", [])),
        render_section_html("X / TWITTER", digest.get("x", [])),
    ])

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

        .section {{
            margin-bottom: 2.25rem;
        }}

        .section-title {{
            font-size: 0.85rem;
            letter-spacing: 0.1em;
            text-transform: uppercase;
            color: #8b949e;
            margin-bottom: 0.9rem;
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
            <div class="header-label">Follow Builders · AI Digest</div>
            <h1>AI Builders Digest</h1>
            <div class="header-date">{date_display} · {date_en}</div>
            <div class="header-sub">来自 follow-builders 的 builder 动态、官方博客与播客精读</div>
        </header>

        <main>{sections_html}
        </main>

        <footer>
            <p>Generated through the Follow Builders skill: https://github.com/zarazhangrui/follow-builders</p>
            <p style="margin-top:0.5rem;"><a href="index.html">← 查看往期日报</a></p>
        </footer>
    </div>
</body>
</html>"""


def update_index(entries):
    """Rebuild the index page listing all past digests."""
    entries_html = ""
    for date_str, filename in sorted(entries, reverse=True):
        if date_str <= ARCHIVE_HIDE_ON_OR_BEFORE:
            continue
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


def iter_digest_items(digest):
    for section in ("x", "blogs", "podcasts"):
        yield from digest.get(section, [])


def send_telegram_digest(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram delivery skipped: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is not set.")
        return

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= 4000:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, 4000)
        if split_at < 2000:
            split_at = 4000
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()

    for chunk in chunks:
        payload = json.dumps({
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "disable_web_page_preview": True,
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()
        if len(chunks) > 1:
            time.sleep(0.5)
    print(f"✓ Telegram digest sent in {len(chunks)} message(s)")


def main():
    today = datetime.now(ZoneInfo(DIGEST_TIMEZONE)).strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"{today}.html"

    print(f"=== AI Daily Digest · {today} ===\n")

    seen_urls = load_seen_urls()
    print(f"Fetching articles (skipping {len(seen_urls)} previously seen)...")
    articles = fetch_articles(seen_urls)

    if not articles:
        print("No new articles found. Exiting.")
        sys.exit(0)

    digest = generate_digest(articles)
    selected_count = sum(len(items) for items in digest.values())
    print(f"Selected {selected_count} items.\n")

    html = generate_html(digest, today)
    output_file.write_text(html, encoding="utf-8")
    print(f"✓ Digest saved: {output_file}")

    text_digest = render_text_digest(digest, today)
    send_telegram_digest(text_digest)

    # Record published URLs so they won't appear again
    seen_urls.update(item["url"] for item in iter_digest_items(digest))
    save_seen_urls(seen_urls)
    print(f"✓ Recorded {selected_count} URLs to seen list ({len(seen_urls)} total)")

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
