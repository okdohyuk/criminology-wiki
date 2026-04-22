#!/usr/bin/env python3
from __future__ import annotations

import argparse
import http.server
import os
import re
import shutil
import socketserver
import subprocess
from pathlib import Path

import yaml
from markdown import markdown

ROOT = Path(__file__).resolve().parents[1]
PAGES_SRC = ROOT / '.pages-src'
SITE_DIR = ROOT / '.site'
FRONT_MATTER_RE = re.compile(r'^---\n(.*?)\n---\n\n(.*)\Z', re.S)
RELATIVE_URL_RE = re.compile(r"\{\{\s*'([^']+)'\s*\|\s*relative_url\s*\}\}")


def run_build() -> None:
    subprocess.run(
        ['python3', str(ROOT / 'scripts' / 'build_github_pages.py'), '--output', str(PAGES_SRC)],
        check=True,
        cwd=ROOT,
    )


def load_markdown(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding='utf-8')
    m = FRONT_MATTER_RE.match(text)
    if not m:
        raise RuntimeError(f'front matter missing: {path}')
    meta = yaml.safe_load(m.group(1)) or {}
    body = m.group(2)
    return meta, body


def render_liquid(text: str) -> str:
    text = RELATIVE_URL_RE.sub(lambda m: m.group(1), text)
    text = text.replace('{{ site.title }}', 'Criminology Wiki')
    text = text.replace('{{ site.description }}', '나만의 범죄학 지식 위키 GitHub Pages 뷰')
    return text


def build_static_site() -> None:
    if SITE_DIR.exists():
        shutil.rmtree(SITE_DIR)
    SITE_DIR.mkdir(parents=True, exist_ok=True)

    assets_src = PAGES_SRC / 'assets'
    if assets_src.exists():
        shutil.copytree(assets_src, SITE_DIR / 'assets')

    layout = render_liquid((PAGES_SRC / '_layouts' / 'default.html').read_text(encoding='utf-8'))

    for md_path in PAGES_SRC.rglob('*.md'):
        rel_path = md_path.relative_to(PAGES_SRC)
        meta, body = load_markdown(md_path)
        body = render_liquid(body)
        html = markdown(body, extensions=['tables', 'fenced_code', 'sane_lists'])

        page = layout
        title = meta.get('title', 'Criminology Wiki')
        full_title = 'Criminology Wiki' if title == 'Criminology Wiki' else f'{title} · Criminology Wiki'
        page = re.sub(r'<title>.*?</title>', f'<title>{full_title}</title>', page, count=1, flags=re.S)
        source_note = ''
        if meta.get('source_path'):
            source_note = f'<p class="source-note">원본 마크다운: <code>{meta["source_path"]}</code></p>'
        page = re.sub(r'\{\% if page\.source_path \%\}\s*<p class="source-note">원본 마크다운: <code>\{\{ page\.source_path \}\}</code></p>\s*\{\% endif \%\}', source_note, page, count=1, flags=re.S)
        page = page.replace('{{ content }}', html)

        if rel_path.name == 'index.md':
            out_path = SITE_DIR / rel_path.parent / 'index.html'
        else:
            out_path = SITE_DIR / rel_path.with_suffix('.html')
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(page, encoding='utf-8')


class ReusableTCPServer(socketserver.TCPServer):
    allow_reuse_address = True


def main() -> int:
    parser = argparse.ArgumentParser(description='Serve a local preview of the GitHub Pages site')
    parser.add_argument('--port', type=int, default=4010)
    args = parser.parse_args()

    run_build()
    build_static_site()

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(SITE_DIR), **kw)
    with ReusableTCPServer(('127.0.0.1', args.port), handler) as httpd:
        print(f'Local preview: http://127.0.0.1:{args.port}/')
        httpd.serve_forever()


if __name__ == '__main__':
    raise SystemExit(main())
