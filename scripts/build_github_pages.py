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


_MD_STRIP_RE = re.compile(
    r'```.*?```'           # fenced code
    r'|`[^`]+`'            # inline code
    r'|^#{1,6}\s+'         # headings
    r'|^[-*_]{3,}\s*$'     # hr
    r'|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]'  # wikilinks
    r'|\[([^\]]+)\]\([^\)]*\)'            # md links
    r'|\*{1,3}([^*]*)\*{1,3}'            # bold/italic
    r'|^>\s*'              # blockquote
    r'|^-\s+카테고리:.*$'  # meta lines
    r'|^-\s+생성:.*$'
    r'|^-\s+최근.*$',
    re.MULTILINE | re.DOTALL,
)


def extract_excerpt(text: str, max_chars: int = 250) -> str:
    def _repl(m: re.Match[str]) -> str:
        return m.group(2) or m.group(1) or m.group(3) or m.group(4) or ' '
    cleaned = _MD_STRIP_RE.sub(_repl, text)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:max_chars]


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
    <link rel=\"preconnect\" href=\"https://cdn.jsdelivr.net\">
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
          </nav>
          <div class=\"search-wrap\">
            <input id=\"wiki-search\" class=\"search-input\" type=\"search\"
                   placeholder=\"검색…\" autocomplete=\"off\" aria-label=\"위키 검색\">
            <ul id=\"search-results\" class=\"search-results\" role=\"listbox\" hidden></ul>
          </div>{github_link}
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
    <script>
    (function(){{
      var SEARCH_URL='{{{{ "/assets/search.json" | relative_url }}}}';
      var idx=null,busy=false,timer;
      var inp=document.getElementById('wiki-search');
      var box=document.getElementById('search-results');
      if(!inp)return;
      function load(cb){{if(idx)return cb();if(busy)return;busy=true;fetch(SEARCH_URL).then(function(r){{return r.json();}}).then(function(d){{idx=d;cb();}}).catch(function(){{busy=false;}});}}
      function esc(s){{return String(s).replace(/[&<>"']/g,function(c){{return{{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c];}});}}
      function hi(t,q){{if(!q)return esc(t);var re=new RegExp('('+q.replace(/[.*+?^${{}}()|[\\]\\\\]/g,'\\\\$&')+')','gi');return esc(t).replace(re,'<mark>$1</mark>');}}
      function render(q){{
        var lq=q.trim().toLowerCase();
        if(!lq||!idx){{hide();return;}}
        var res=idx.map(function(p){{var ts=p.title.toLowerCase().indexOf(lq)>=0,es=p.excerpt.toLowerCase().indexOf(lq)>=0;return(ts||es)?{{p:p,sc:ts?2:1}}:null;}}).filter(Boolean).sort(function(a,b){{return b.sc-a.sc;}}).slice(0,8);
        if(!res.length){{hide();return;}}
        box.innerHTML=res.map(function(r){{var p=r.p,ex=p.excerpt?p.excerpt.slice(0,90)+'…':'';return'<li role="option" data-href="'+esc(p.url)+'" tabindex="-1"><span class="sr-title">'+hi(p.title,q.trim())+'</span><span class="sr-meta">'+esc(p.category)+'</span>'+(ex?'<span class="sr-excerpt">'+hi(ex,q.trim())+'</span>':'')+'</li>';}}).join('');
        box.removeAttribute('hidden');
      }}
      function hide(){{box.setAttribute('hidden','');box.innerHTML='';}}
      function cur(){{return box.querySelector('li.sr-active');}}
      inp.addEventListener('input',function(){{clearTimeout(timer);timer=setTimeout(function(){{load(function(){{render(inp.value);}});}},150);}});
      inp.addEventListener('focus',function(){{load(function(){{if(inp.value.trim())render(inp.value);}});}});
      inp.addEventListener('keydown',function(e){{
        var items=Array.from(box.querySelectorAll('li')),c=cur(),i=c?items.indexOf(c):-1;
        if(e.key==='ArrowDown'){{e.preventDefault();if(c)c.classList.remove('sr-active');var n=items[(i+1)%items.length];if(n)n.classList.add('sr-active');}}
        else if(e.key==='ArrowUp'){{e.preventDefault();if(c)c.classList.remove('sr-active');var p2=items[(i-1+items.length)%items.length];if(p2)p2.classList.add('sr-active');}}
        else if(e.key==='Enter'){{var go=c||items[0];if(go){{e.preventDefault();location.href=go.dataset.href;}}}}
        else if(e.key==='Escape'){{hide();inp.blur();}}
      }});
      box.addEventListener('click',function(e){{var li=e.target.closest('li[data-href]');if(li)location.href=li.dataset.href;}});
      document.addEventListener('click',function(e){{if(!inp.contains(e.target)&&!box.contains(e.target))hide();}});
    }})();
    </script>
  </body>
</html>
"""


def build_css() -> str:
    return """/* okdohyuk Design System — Criminology Wiki
 * Palette: Tailwind zinc (basic-*) + violet (point-*)
 * Font: Pretendard Variable (cdn.jsdelivr.net)
 */
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/packages/pretendard/dist/web/variable/pretendardvariable.css');

/* ── 토큰 (라이트 모드) ─────────────────────────── */
:root {
  --basic-0: #ffffff;
  --basic-1: #fafafa;
  --basic-2: #f4f4f5;
  --basic-3: #e4e4e7;
  --basic-4: #d4d4d8;
  --basic-5: #a1a1aa;

  --zinc-50:  #fafafa;
  --zinc-100: #f4f4f5;
  --zinc-200: #e4e4e7;
  --zinc-300: #d4d4d8;
  --zinc-400: #a1a1aa;
  --zinc-500: #71717a;
  --zinc-600: #52525b;
  --zinc-700: #3f3f46;
  --zinc-800: #27272a;
  --zinc-900: #18181b;

  --point-1: #6D28D9;
  --point-2: #7C3AED;
  --point-3: #8B5CF6;
  --point-4: #DDD6FE;
  --point-tint-soft: #EEEAFE;
  --point-800: #5B21B6;

  --accent-fg: var(--point-1);
  --accent-tint: rgba(124, 58, 237, 0.12);
  --accent-tint-soft: rgba(124, 58, 237, 0.06);

  --fg-1: var(--zinc-900);
  --fg-2: var(--zinc-800);
  --fg-3: var(--zinc-700);
  --fg-4: var(--zinc-600);
  --fg-5: var(--zinc-500);
  --fg-6: var(--zinc-400);

  --bg-canvas: var(--basic-1);
  --bg-surface: var(--basic-0);
  --bg-muted: var(--basic-2);
  --border-subtle: var(--basic-3);
  --border-default: var(--basic-4);

  --shadow-sm: 0 2px 6px 0 rgba(0,0,0,0.06);
  --shadow-md: 0 8px 20px 0 rgba(0,0,0,0.08);

  --radius-sm: 8px;
  --radius-md: 12px;
  --radius-xl: 16px;
  --radius-panel: 24px;

  --font-body: 'Pretendard Variable', 'Pretendard', -apple-system,
               BlinkMacSystemFont, system-ui, 'Apple SD Gothic Neo',
               'Noto Sans KR', 'Malgun Gothic', sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, monospace;

  --fs-t1: 36px;  --fs-t2: 30px;  --fs-t3: 24px;
  --fs-d1: 18px;  --fs-d2: 16px;  --fs-d3: 14px;  --fs-c1: 12px;
  --fw-regular: 400;  --fw-medium: 500;  --fw-semibold: 600;  --fw-bold: 700;
}

/* ── 토큰 (다크 모드) ──────────────────────────── */
@media (prefers-color-scheme: dark) {
  :root {
    --basic-0: #000000;  --basic-1: #18181b;  --basic-2: #27272a;
    --basic-3: #3f3f46;  --basic-4: #52525b;  --basic-5: #71717a;

    --fg-1: var(--zinc-50);   --fg-2: var(--zinc-100);  --fg-3: var(--zinc-200);
    --fg-4: var(--zinc-300);  --fg-5: var(--zinc-400);  --fg-6: var(--zinc-500);

    --bg-canvas: var(--basic-1);  --bg-surface: var(--basic-2);
    --bg-muted: var(--basic-3);
    --border-subtle: var(--basic-3);  --border-default: var(--basic-4);

    /* violet-300: 9.62:1 on #18181b (WCAG AAA) */
    --accent-fg: #C4B5FD;
    --accent-tint: rgba(196, 181, 253, 0.14);
    --accent-tint-soft: rgba(196, 181, 253, 0.06);

    --shadow-sm: 0 2px 6px 0 rgba(0,0,0,0.3);
    --shadow-md: 0 8px 20px 0 rgba(0,0,0,0.35);
  }
}

/* ── 리셋 & 베이스 ─────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; }
html { scroll-behavior: smooth; -webkit-text-size-adjust: 100%; }
body {
  margin: 0;
  font-family: var(--font-body);
  font-size: var(--fs-d2);
  line-height: 1.7;
  color: var(--fg-1);
  background: var(--bg-canvas);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

/* ── 링크 ─────────────────────────────────────── */
a { color: var(--accent-fg); text-decoration: none; transition: opacity 160ms ease; }
a:hover { text-decoration: underline; opacity: 0.85; }

/* ── 코드·모노 ────────────────────────────────── */
code, pre, kbd { font-family: var(--font-mono); font-size: 0.9em; }
code {
  background: var(--bg-muted);
  color: var(--fg-2);
  padding: 0.1rem 0.35rem;
  border-radius: 6px;
  border: 1px solid var(--border-subtle);
}
pre {
  overflow-x: auto;
  background: var(--zinc-900);
  color: #f4f4f5;
  padding: 1rem 1.25rem;
  border-radius: var(--radius-md);
  border: 1px solid var(--basic-3);
  margin: 1.25rem 0;
}
@media (prefers-color-scheme: dark) {
  pre { background: #09090b; }
}
pre code { background: transparent; border: none; padding: 0; color: inherit; font-size: 1em; }

/* ── 레이아웃 ──────────────────────────────────── */
.wrap { width: min(1060px, calc(100% - 2rem)); margin: 0 auto; }

/* ── 헤더 ─────────────────────────────────────── */
.site-header {
  position: sticky; top: 0; z-index: 100;
  background: rgba(250,250,250,0.88);
  border-bottom: 1px solid var(--border-subtle);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
@media (prefers-color-scheme: dark) {
  .site-header { background: rgba(24,24,27,0.88); }
}
.header-wrap {
  display: flex; align-items: center; justify-content: space-between;
  gap: 1rem; padding: 0.85rem 0;
}
.site-title {
  font-size: var(--fs-d1); font-weight: var(--fw-bold);
  color: var(--fg-1); letter-spacing: -0.01em; transition: color 160ms ease;
}
.site-title:hover { text-decoration: none; color: var(--accent-fg); opacity: 1; }
.header-actions { display: flex; align-items: center; gap: 0.75rem; }
.top-nav { display: flex; align-items: center; gap: 0.25rem; }
.top-nav a {
  font-size: var(--fs-d3); font-weight: var(--fw-semibold);
  color: var(--fg-4); padding: 4px 10px; border-radius: var(--radius-sm);
  transition: background 160ms ease, color 160ms ease;
}
.top-nav a:hover { background: var(--bg-muted); color: var(--fg-1); text-decoration: none; opacity: 1; }
.github-link {
  display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border-radius: var(--radius-sm);
  color: var(--fg-5); transition: background 160ms ease, color 160ms ease;
}
.github-link:hover { background: var(--bg-muted); color: var(--fg-2); text-decoration: none; opacity: 1; }
.github-link svg { width: 1.1rem; height: 1.1rem; fill: currentColor; }

/* ── 메인 컨텐츠 ───────────────────────────────── */
.content { padding: 2rem 0 4rem; }
article {
  background: var(--bg-surface);
  border: 1px solid var(--border-subtle);
  border-radius: var(--radius-panel);
  padding: 2rem 2.5rem;
  box-shadow: var(--shadow-md);
}
.source-note {
  display: inline-flex; align-items: center; gap: 0.35rem;
  font-size: var(--fs-c1); color: var(--fg-5);
  margin-bottom: 1.5rem; padding: 4px 10px;
  background: var(--bg-muted); border-radius: var(--radius-sm);
  border: 1px solid var(--border-subtle);
}
.source-note code { background: transparent; border: none; padding: 0; font-size: inherit; color: inherit; }

/* ── 아티클 내 타이포그래피 ───────────────────── */
article h1 {
  font-size: var(--fs-t1); font-weight: var(--fw-bold);
  color: var(--fg-1); line-height: 1.15; letter-spacing: -0.02em; margin: 0 0 1.5rem;
}
article h2 {
  font-size: var(--fs-t2); font-weight: var(--fw-bold);
  color: var(--fg-1); line-height: 1.2; letter-spacing: -0.015em;
  margin: 2.5rem 0 0.75rem; padding-bottom: 0.5rem; border-bottom: 1px solid var(--border-subtle);
}
article h3 {
  font-size: var(--fs-t3); font-weight: var(--fw-bold);
  color: var(--fg-1); line-height: 1.3; margin: 2rem 0 0.5rem;
}
article h4 {
  font-size: var(--fs-d1); font-weight: var(--fw-semibold);
  color: var(--fg-2); margin: 1.5rem 0 0.4rem;
}
article p { font-size: var(--fs-d2); color: var(--fg-3); line-height: 1.8; margin: 0 0 1rem; }
article ul, article ol { padding-left: 1.5rem; margin: 0.5rem 0 1rem; color: var(--fg-3); }
article li { font-size: var(--fs-d2); line-height: 1.75; margin-bottom: 0.2rem; }
article strong { font-weight: var(--fw-semibold); color: var(--fg-2); }
article em { font-style: italic; color: var(--fg-4); }

/* ── 학습 takeaway callout (blockquote) ───────── */
article blockquote {
  margin: 0 0 2rem;
  padding: 1rem 1.25rem 1rem 1.5rem;
  background: var(--accent-tint-soft);
  border-left: 3px solid var(--point-2);
  border-radius: 0 var(--radius-md) var(--radius-md) 0;
  font-size: var(--fs-d3);
  color: var(--fg-3);
  line-height: 1.75;
}
article blockquote strong { color: var(--accent-fg); font-weight: var(--fw-semibold); }
article blockquote p { font-size: inherit; color: inherit; margin: 0; line-height: inherit; }

/* ── hr ────────────────────────────────────────── */
article hr { border: none; border-top: 1px solid var(--border-subtle); margin: 2rem 0; }

/* ── 테이블 ────────────────────────────────────── */
article table {
  width: 100%; border-collapse: collapse; margin: 1.25rem 0 1.75rem;
  font-size: var(--fs-d3); background: var(--bg-surface);
  border-radius: var(--radius-md); overflow: hidden;
  border: 1px solid var(--border-subtle); box-shadow: var(--shadow-sm);
}
article th {
  background: var(--bg-muted); font-weight: var(--fw-semibold);
  color: var(--fg-2); padding: 0.6rem 0.9rem;
  text-align: left; border-bottom: 1px solid var(--border-default);
}
article td { padding: 0.6rem 0.9rem; color: var(--fg-3); vertical-align: top; border-bottom: 1px solid var(--border-subtle); }
article tr:last-child td { border-bottom: none; }
article tr:hover td { background: var(--bg-muted); }

/* ── 검색 ─────────────────────────────────────── */
.search-wrap { position: relative; flex: 0 0 auto; }
.search-input {
  width: 180px; height: 32px;
  padding: 0 10px 0 30px;
  font-family: var(--font-body); font-size: var(--fs-d3);
  color: var(--fg-1); background: var(--bg-muted);
  border: 1px solid var(--border-subtle); border-radius: var(--radius-md);
  outline: none; appearance: none; -webkit-appearance: none;
  transition: width 200ms ease, border-color 160ms ease, box-shadow 160ms ease, background 160ms ease;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%2371717a' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'%3E%3Ccircle cx='11' cy='11' r='8'/%3E%3Cpath d='m21 21-4.35-4.35'/%3E%3C/svg%3E");
  background-repeat: no-repeat; background-position: 8px center; background-size: 14px;
}
.search-input:focus {
  width: 240px; border-color: var(--point-3);
  box-shadow: 0 0 0 2px var(--accent-tint);
  background-color: var(--bg-surface); outline: none;
}
.search-input::-webkit-search-cancel-button { -webkit-appearance: none; }
.search-results {
  position: absolute; top: calc(100% + 6px); right: 0; width: 320px;
  background: var(--bg-surface); border: 1px solid var(--border-subtle);
  border-radius: var(--radius-xl); box-shadow: var(--shadow-lg);
  list-style: none; padding: 6px; margin: 0;
  z-index: 200; max-height: 400px; overflow-y: auto;
}
.search-results li {
  display: flex; flex-direction: column; gap: 2px;
  padding: 8px 10px; border-radius: var(--radius-sm);
  cursor: pointer; transition: background 120ms ease;
}
.search-results li:hover, .search-results li.sr-active { background: var(--bg-muted); }
.sr-title { font-size: var(--fs-d3); font-weight: var(--fw-semibold); color: var(--fg-1); line-height: 1.4; }
.sr-meta { font-size: var(--fs-c1); color: var(--accent-fg); font-weight: var(--fw-medium); }
.sr-excerpt { font-size: var(--fs-c1); color: var(--fg-5); line-height: 1.5; }
.search-results mark {
  background: var(--accent-tint); color: var(--accent-fg);
  border-radius: 2px; padding: 0 1px;
}

/* ── 반응형 ────────────────────────────────────── */
@media (max-width: 640px) {
  article { padding: 1.25rem 1.1rem; border-radius: var(--radius-xl); }
  .header-wrap { flex-direction: column; align-items: flex-start; gap: 0.5rem; }
  .header-actions { width: 100%; justify-content: space-between; }
  article h1 { font-size: var(--fs-t2); }
  article h2 { font-size: var(--fs-t3); }
  .search-input { width: 130px; }
  .search-input:focus { width: 160px; }
  .search-results { width: calc(100vw - 2rem); right: 0; }
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
    search_entries: list[dict[str, str]] = []

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
        search_entries.append({
            "slug": slug,
            "title": meta["title"],
            "url": f"/wiki/{slug}/",
            "category": meta["category"],
            "excerpt": extract_excerpt(text),
        })

    write_text(out_dir / "assets" / "search.json", json.dumps(search_entries, ensure_ascii=False, separators=(',', ':')))

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
