#!/usr/bin/env python3
"""Assemble src/ into a static dist/ directory. Pure function of src/ -> dist/,
no git or network side effects. Safe to re-run any time."""

import argparse
import datetime
import re
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = REPO_ROOT / "src"
PARTIALS_DIR = SRC_DIR / "partials"
PAGES_DIR = SRC_DIR / "pages"
POSTS_DIR = SRC_DIR / "blog" / "posts"
STATIC_DIR = SRC_DIR / "static"
DEFAULT_OUT_DIR = REPO_ROOT / "dist"

NAV_ITEMS = [
    ("home", "Welcome", "/"),
    ("cv", "CV", "/cv/"),
    ("writing", "Writing", "/writing/"),
    ("blog", "Blog", "/blog/"),
    ("systematic", "Systematic", "/systematic-how-systems-biology-is-transforming-modern-medicine/"),
    ("fun", "Fun", "/fun/"),
    ("contact", "Contact", "/contact/"),
]

WORD_LIMIT = 55

POST_FILENAME_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)\.html$")
_ATTR_RE = re.compile(r'\b(href|src|srcset)="([^"]*)"')
_TAG_RE = re.compile(r"<[^>]+>")


# ---------------------------------------------------------------------------
# Front matter
# ---------------------------------------------------------------------------

def parse_front_matter(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"{path}: missing front matter (must start with '---')")
    _, rest = text.split("---\n", 1)
    fm_block, body = rest.split("\n---\n", 1)
    meta = {}
    for line in fm_block.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    return meta, body.strip("\n")


# ---------------------------------------------------------------------------
# Templating
# ---------------------------------------------------------------------------

def load_partials() -> tuple[str, str, str]:
    head = (PARTIALS_DIR / "head.html").read_text(encoding="utf-8")
    header = (PARTIALS_DIR / "header.html").read_text(encoding="utf-8")
    footer = (PARTIALS_DIR / "footer.html").read_text(encoding="utf-8")
    return head, header, footer


def render_nav(active_key: str) -> str:
    lines = []
    for key, label, href in NAV_ITEMS:
        cls = "active" if key == active_key else ""
        lines.append(f'                    <li><a href="{href}" class="{cls}">{label}</a></li>')
    return "\n".join(lines)


def rewrite_paths(html_str: str, base_path: str) -> str:
    if not base_path:
        return html_str

    def _rewrite(url: str) -> str:
        if url.startswith("/") and not url.startswith("//"):
            return base_path + url
        return url

    def _sub(m: re.Match) -> str:
        attr, value = m.group(1), m.group(2)
        if attr == "srcset":
            parts = []
            for chunk in value.split(","):
                chunk = chunk.strip()
                if not chunk:
                    continue
                url, _, descriptor = chunk.partition(" ")
                parts.append(f"{_rewrite(url)} {descriptor}".strip())
            value = ", ".join(parts)
        else:
            value = _rewrite(value)
        return f'{attr}="{value}"'

    return _ATTR_RE.sub(_sub, html_str)


def render_page(templates, *, title, description, nav, main_class, content_html, base_path):
    head_tpl, header_tpl, footer_tpl = templates
    head = head_tpl.replace("[[TITLE]]", title).replace("[[DESCRIPTION]]", description)
    header = header_tpl.replace("[[NAV]]", render_nav(nav))
    main = f'    <main class="site-main {main_class}">\n{content_html}\n    </main>\n\n'
    page = head + header + main + footer_tpl
    return rewrite_paths(page, base_path)


# ---------------------------------------------------------------------------
# Output writing
# ---------------------------------------------------------------------------

def write_output(out_dir: Path, rel_path: Path, content: str, written: set):
    if rel_path in written:
        raise ValueError(f"Duplicate output path: {rel_path}")
    written.add(rel_path)
    dest = out_dir / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(content, encoding="utf-8")


def page_output_path(src_path: Path) -> Path:
    rel = src_path.relative_to(PAGES_DIR)
    if rel == Path("index.html"):
        return Path("index.html")
    return rel.with_suffix("") / "index.html"


# ---------------------------------------------------------------------------
# Site pages
# ---------------------------------------------------------------------------

def build_pages(templates, base_path: str, out_dir: Path, written: set, blog_list_html: str):
    for src_path in sorted(PAGES_DIR.rglob("*.html")):
        meta, body = parse_front_matter(src_path)
        content_html = body.replace("[[BLOG_LIST]]", blog_list_html)
        page_html = render_page(
            templates,
            title=meta["title"],
            description=meta["description"],
            nav=meta.get("nav", ""),
            main_class=meta["main_class"],
            content_html=content_html,
            base_path=base_path,
        )
        write_output(out_dir, page_output_path(src_path), page_html, written)


# ---------------------------------------------------------------------------
# Blog posts + index
# ---------------------------------------------------------------------------

def load_posts() -> list[dict]:
    posts = []
    for path in sorted(POSTS_DIR.glob("*.html")):
        m = POST_FILENAME_RE.match(path.name)
        if not m:
            raise ValueError(f"{path}: filename must match YYYY-MM-DD-slug.html")
        year, month, day, slug = m.groups()
        meta, body = parse_front_matter(path)
        posts.append({
            "date": datetime.date(int(year), int(month), int(day)),
            "year": year,
            "month": month,
            "day": day,
            "slug": slug,
            "url": f"/{year}/{month}/{day}/{slug}/",
            "title": meta["title"],
            "description": meta.get("description") or f"Blog post: {meta['title']}",
            "body_html": body,
            "excerpt_override": meta.get("excerpt"),
            # Tiebreaker for same-day posts (lower sorts first/newest); default 0.
            "order": int(meta.get("order", 0)),
        })
    posts.sort(key=lambda p: (p["date"], -p["order"]), reverse=True)
    return posts


def make_excerpt(post: dict) -> str:
    if post["excerpt_override"]:
        return post["excerpt_override"]
    # Mirrors WordPress's wp_trim_words(): strip tags with no inserted space
    # (an inline </a> against punctuation like "Vinome</a>." must stay
    # "Vinome.", not become "Vinome ."), collapse literal whitespace runs
    # only (not full \s -- HTML entities like &nbsp; are NOT decoded first,
    # so they stay glued to their neighboring word as WordPress's own
    # preg_split("/[\n\r\t ]+/") would treat them), then take the first 55
    # whitespace-delimited tokens as-is (still entity-encoded).
    text = _TAG_RE.sub("", post["body_html"])
    text = re.sub(r"[\n\r\t ]+", " ", text).strip()
    words = text.split(" ")
    if len(words) <= WORD_LIMIT:
        return text
    truncated = " ".join(words[:WORD_LIMIT])
    return (
        truncated + " &hellip; "
        + f'<a href="{post["url"]}" class="more-link">Continue reading'
        + f'<span class="screen-reader-text"> &#8220;{post["title"]}&#8221;</span></a>'
    )


def render_summary(post: dict) -> str:
    date_str = post["date"].strftime("%B %d, %Y")
    excerpt = make_excerpt(post)
    return f'''        <article class="blog-summary">
            <span class="post-meta">{date_str}</span>
            <h2><a href="{post["url"]}">{post["title"]}</a></h2>
            <div class="entry-summary">
                <p>{excerpt}</p>
            </div>
            <a href="{post["url"]}" class="read-more">Read More &rarr;</a>
        </article>'''


POST_ARTICLE = '''    <article class="container">
        <header class="post-header">
            <span class="post-meta">{date_str}</span>
            <h1>{title}</h1>
        </header>
        <div class="post-content">
{body}
        </div>
    </article>'''


def build_posts(templates, posts: list[dict], base_path: str, out_dir: Path, written: set):
    for post in posts:
        content_html = POST_ARTICLE.format(
            date_str=post["date"].strftime("%B %d, %Y"),
            title=post["title"],
            body=post["body_html"],
        )
        page_html = render_page(
            templates,
            title=post["title"],
            description=post["description"],
            nav="blog",
            main_class="blog-post",
            content_html=content_html,
            base_path=base_path,
        )
        out_rel = Path(post["year"]) / post["month"] / post["day"] / post["slug"] / "index.html"
        write_output(out_dir, out_rel, page_html, written)


# ---------------------------------------------------------------------------
# Static passthrough
# ---------------------------------------------------------------------------

def copy_static(out_dir: Path):
    for item in STATIC_DIR.iterdir():
        dest = out_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build_site(base_path: str = "", out_dir: Path = DEFAULT_OUT_DIR):
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True)

    templates = load_partials()
    written: set = set()

    posts = load_posts()
    blog_list_html = "\n        \n".join(render_summary(p) for p in posts)

    build_pages(templates, base_path, out_dir, written, blog_list_html)
    build_posts(templates, posts, base_path, out_dir, written)
    copy_static(out_dir)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-path", default="", help='Prefix for root-relative links, e.g. "/jamesvalcourt" (default: none, for local preview)')
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="Output directory (default: dist/)")
    args = parser.parse_args()
    build_site(base_path=args.base_path, out_dir=Path(args.out_dir))
    print(f"Built site into {args.out_dir} (base_path={args.base_path!r})")


if __name__ == "__main__":
    main()
