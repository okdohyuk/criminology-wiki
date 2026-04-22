#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIKI_DIR = ROOT / "wiki"
WIKILINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
TITLE_RE = re.compile(r"^#\s+(.+)$", re.MULTILINE)
CATEGORY_RE = re.compile(r"^-\s*카테고리:\s*(.+)$", re.MULTILINE)
LATEST_LOG_RE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)


class BuildError(RuntimeError):
    pass


def discover_repo_url() -> str | None:
    repo = os.getenv("GITHUB_REPOSITORY")
    if repo:
        return f"https://github.com/{repo}"

    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None

    https_match = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?$", remote)
    if https_match:
        owner, repo_name = https_match.groups()
        return f"https://github.com/{owner}/{repo_name}"
    return None


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def yaml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def extract_title(text: str, fallback: str) -> str:
    match = TITLE_RE.search(text)
    return match.group(1).strip() if match else fallback


def extract_category(text: str) -> str | None:
    match = CATEGORY_RE.search(text)
    return match.group(1).strip() if match else None


def liquid_url(path: str) -> str:
    return "{{ " + repr(path) + " | relative_url }}"


def clean_for_pages(text: str) -> str:
    text = text.replace(
        "자세한 운영 규칙은 [`../CLAUDE.md`](../CLAUDE.md) 참조.",
        "운영 규칙은 저장소의 `CLAUDE.md`를 참고.",
    )
    return text


def strip_fenced_code(text: str) -> str:
    return FENCED_CODE_RE.sub('', text)


def convert_wikilinks(text: str, *, known_pages: set[str]) -> tuple[str, list[str]]:
    unresolved: list[str] = []

    def repl(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        label = (match.group(2) or target).strip()

        if target == "위키링크":
            return match.group(0)
        if target == "index":
            return f"[{label}]({liquid_url('/')})"
        if target == "log":
            return f"[{label}]({liquid_url('/log/')})"
        if target in known_pages:
            return f"[{label}]({liquid_url(f'/wiki/{target}/')})"

        unresolved.append(target)
        return label

    return WIKILINK_RE.sub(repl, text), unresolved


def front_matter(*, title: str, permalink: str, source_path: str | None = None) -> str:
    lines = ["---", f"layout: default", f"title: {yaml_string(title)}", f"permalink: {permalink}"]
    if source_path:
        lines.append(f"source_path: {yaml_string(source_path)}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def build_layout(repo_url: str | None) -> str:
    github_link = ""
    if repo_url:
        github_link = f"""
          <a class=\"github-link\" href=\"{repo_url}\" target=\"_blank\" rel=\"noreferrer\" aria-label=\"GitHub 저장소\">
            <svg viewBox=\"0 0 16 16\" aria-hidden=\"true\">
              <path d=\"M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.5-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.5 7.5 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z\"></path>
            </svg>
          </a>"""

    return f"""<!doctype html>
<html lang=\"ko\">
  <head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <title>{{% if page.title and page.title != site.title %}}{{{{ page.title }}}} · {{% endif %}}{{{{ site.title }}}}</title>
    <meta name=\"description\" content=\"{{{{ site.description }}}}\">
    <link rel=\"stylesheet\" href=\"{{{{ '/assets/site.css' | relative_url }}}}\">
  </head>
  <body>
    <header class=\"site-header\">
      <div class=\"wrap header-wrap\">
        <a class=\"site-title\" href=\"{{{{ '/' | relative_url }}}}\">{{{{ site.title }}}}</a>
        <div class=\"header-actions\">
          <nav class=\"top-nav\">
            <a href=\"{{{{ '/' | relative_url }}}}\">전체 목차</a>
            <a href=\"{{{{ '/log/' | relative_url }}}}\">작업 이력</a>
          </nav>{github_link}
        </div>
      </div>
    </header>
    <main class=\"wrap content\">
      <article>
        {{% if page.source_path %}}
        <p class=\"source-note\">원본 마크다운: <code>{{{{ page.source_path }}}}</code></p>
        {{% endif %}}
        {{{{ content }}}}
      </article>
    </main>
  </body>
</html>
"""


def build_css() -> str:
    return """:root {
  color-scheme: light;
  --bg: #f7f7f9;
  --card: #ffffff;
  --text: #1f2328;
  --muted: #57606a;
  --line: #d0d7de;
  --accent: #0969da;
  --blockquote: #f6f8fa;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.7;
}

a { color: var(--accent); text-decoration: none; }
a:hover { text-decoration: underline; }
code, pre { font-family: "SFMono-Regular", Consolas, monospace; }
pre {
  overflow-x: auto;
  background: #111827;
  color: #f9fafb;
  padding: 1rem;
  border-radius: 12px;
}
code {
  background: #eef2f6;
  padding: 0.12rem 0.32rem;
  border-radius: 6px;
}
pre code {
  background: transparent;
  padding: 0;
}
blockquote {
  margin: 1.25rem 0;
  padding: 0.85rem 1rem;
  border-left: 4px solid var(--accent);
  background: var(--blockquote);
  border-radius: 0 12px 12px 0;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin: 1rem 0 1.5rem;
  background: var(--card);
}
th, td {
  border: 1px solid var(--line);
  padding: 0.7rem 0.8rem;
  text-align: left;
  vertical-align: top;
}
hr {
  border: 0;
  border-top: 1px solid var(--line);
  margin: 2rem 0;
}
.wrap {
  width: min(1180px, calc(100% - 2rem));
  margin: 0 auto;
}
.site-header {
  background: rgba(255,255,255,0.92);
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 0;
  z-index: 10;
  backdrop-filter: blur(8px);
}
.header-wrap {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.9rem 0;
}
.site-title {
  font-weight: 700;
  color: var(--text);
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}
.top-nav {
  display: flex;
  align-items: center;
  gap: 0.9rem;
}
.top-nav a {
  color: var(--muted);
  font-weight: 600;
}
.github-link {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: var(--muted);
}
.github-link svg {
  width: 1.1rem;
  height: 1.1rem;
  fill: currentColor;
}
.content {
  padding: 2rem 0 3rem;
}
article {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 1.5rem;
  box-shadow: 0 8px 24px rgba(31, 35, 40, 0.04);
}
.source-note {
  margin: 0 0 1.25rem;
  color: var(--muted);
  font-size: 0.95rem;
}
@media (max-width: 640px) {
  .header-wrap {
    flex-direction: column;
    align-items: flex-start;
  }
  .header-actions {
    width: 100%;
    justify-content: space-between;
  }
  .top-nav {
    flex-wrap: wrap;
  }
  article {
    padding: 1.1rem;
  }
}

"""


def build_config() -> str:
    return """title: Criminology Wiki
description: 나만의 범죄학 지식 위키 GitHub Pages 뷰
lang: ko
timezone: Asia/Seoul
markdown: kramdown
permalink: pretty
kramdown:
  input: GFM
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Build GitHub Pages source from wiki markdown")
    parser.add_argument("--output", default=str(ROOT / ".pages-src"), help="output directory")
    args = parser.parse_args()

    if not WIKI_DIR.exists():
        raise BuildError("wiki/ 디렉터리를 찾을 수 없습니다.")

    out_dir = Path(args.output)
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    page_paths = sorted(path for path in WIKI_DIR.glob("*.md") if path.name not in {"index.md", "log.md"})
    pages: dict[str, dict[str, str]] = {}
    for path in page_paths:
        text = read_text(path)
        pages[path.stem] = {
            "title": extract_title(text, path.stem),
            "category": extract_category(text) or "미분류",
            "source_path": str(path.relative_to(ROOT)),
        }

    known_pages = set(pages)
    unresolved_links: list[tuple[str, list[str]]] = []

    repo_url = discover_repo_url()

    # Static site scaffolding.
    write_text(out_dir / "_config.yml", build_config())
    write_text(out_dir / "_layouts" / "default.html", build_layout(repo_url))
    write_text(out_dir / "assets" / "site.css", build_css())
    log_text = clean_for_pages(read_text(WIKI_DIR / "log.md"))

    # Main wiki index.
    index_text = clean_for_pages(read_text(WIKI_DIR / "index.md"))
    converted_index, missing = convert_wikilinks(index_text, known_pages=known_pages)
    if missing:
        unresolved_links.append(("index", missing))
    index_title = extract_title(index_text, "Criminology Wiki — 전체 목차")
    index_rendered = front_matter(title=index_title, permalink="/", source_path="wiki/index.md") + converted_index
    write_text(out_dir / "index.md", index_rendered)
    write_text(
        out_dir / "wiki" / "index.md",
        front_matter(title=index_title, permalink="/wiki/", source_path="wiki/index.md") + converted_index,
    )

    # Log page.
    converted_log, missing = convert_wikilinks(log_text, known_pages=known_pages)
    if missing:
        unresolved_links.append(("log", missing))
    write_text(
        out_dir / "log" / "index.md",
        front_matter(title="작업 이력", permalink="/log/", source_path="wiki/log.md") + converted_log,
    )

    # Content pages.
    for slug, meta in pages.items():
        source_path = ROOT / meta["source_path"]
        text = clean_for_pages(read_text(source_path))
        converted, missing = convert_wikilinks(text, known_pages=known_pages)
        if missing:
            unresolved_links.append((slug, missing))
        write_text(
            out_dir / "wiki" / slug / "index.md",
            front_matter(title=meta["title"], permalink=f"/wiki/{slug}/", source_path=meta["source_path"]) + converted,
        )

    if unresolved_links:
        lines = []
        for slug, missing in unresolved_links:
            uniq = ", ".join(sorted(set(missing)))
            lines.append(f"- {slug}: {uniq}")
        raise BuildError("해결되지 않은 위키링크가 있습니다:\n" + "\n".join(lines))

    print(f"Built GitHub Pages source in {out_dir}")
    print(f"Generated pages: {len(pages)} wiki pages + root index + /wiki alias + log")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
