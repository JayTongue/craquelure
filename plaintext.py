"""Render the site as plain text for terminal clients like curl and wget."""
import re
import textwrap
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin

from flask import request, Response

WIDTH = 78
TERMINAL_AGENTS = re.compile(r'^(curl|wget|httpie|xh|fetch|aria2)/', re.IGNORECASE)

BLOCK_TAGS = {'p', 'div', 'blockquote', 'ul', 'ol', 'li', 'table', 'tr',
              'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'iframe', 'section'}
SKIP_TAGS = {'script', 'style', 'head'}


def wants_text():
    """True for terminal HTTP clients, or anyone explicitly preferring text/plain."""
    if request.args.get('format') == 'txt':
        return True
    if TERMINAL_AGENTS.match(request.headers.get('User-Agent', '')):
        return True
    accept = request.accept_mimetypes
    return accept['text/plain'] > accept['text/html']


def text_response(body):
    resp = Response(body, mimetype='text/plain')
    resp.headers['Vary'] = 'User-Agent, Accept'
    return resp


class _Converter(HTMLParser):
    """Turns a chunk of article HTML into wrapped plain-text blocks plus link references."""

    def __init__(self, base_url, refs):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.refs = refs          # shared list of absolute URLs, numbered [1], [2], ...
        self.blocks = []          # (kind, text, depth)
        self.buf = []
        self.quote_depth = 0
        self.lists = []           # stack of ['ul'|'ol', counter]
        self.heading = None
        self.skip = 0
        self.link_href = None
        self.row = None
        self.cell = None
        self.table = None

    def _ref(self, url):
        url = urljoin(self.base_url, url)
        if url not in self.refs:
            self.refs.append(url)
        return self.refs.index(url) + 1

    def _flush(self, kind='p'):
        text = re.sub(r'\s+', ' ', ''.join(self.buf)).strip()
        self.buf = []
        if text:
            self.blocks.append((kind, text, self.quote_depth))

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in SKIP_TAGS:
            if tag == 'script' and 'plot.ly' in attrs.get('src', ''):
                self._flush()
                self.blocks.append(('p', f'[interactive chart: open in a browser][{self._ref(self.base_url)}]',
                                    self.quote_depth))
            self.skip += 1
            return
        if self.skip:
            return
        if self.cell is not None and tag not in ('td', 'th', 'tr'):
            if tag == 'br':
                self.cell.append(' ')
            return
        if tag in BLOCK_TAGS:
            self._flush()
        if tag == 'blockquote':
            self.quote_depth += 1
        elif tag in ('ul', 'ol'):
            self.lists.append([tag, 0])
        elif tag == 'li' and self.lists:
            self.lists[-1][1] += 1
            kind, n = self.lists[-1]
            self.buf.append('- ' if kind == 'ul' else f'{n}. ')
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self.heading = tag
        elif tag == 'br':
            self._flush()
        elif tag == 'a' and attrs.get('href'):
            self.link_href = attrs['href']
        elif tag == 'img':
            alt = attrs.get('alt', '').strip()
            label = f'image: {alt}' if alt else 'image'
            self.buf.append(f' [{label}][{self._ref(attrs.get("src", ""))}] ')
        elif tag == 'iframe':
            title = attrs.get('title', 'embedded content')
            self.blocks.append(('p', f'[{title}][{self._ref(attrs.get("src", ""))}]', self.quote_depth))
        elif tag == 'table':
            self.table = []
        elif tag == 'tr':
            self.row = []
        elif tag in ('td', 'th') and self.row is not None:
            self.cell = []
        elif tag == 'sup':
            self.buf.append('^')

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip = max(0, self.skip - 1)
            return
        if self.skip:
            return
        if tag in ('td', 'th') and self.cell is not None:
            self.row.append(re.sub(r'\s+', ' ', ''.join(self.cell)).strip())
            self.cell = None
        elif tag == 'tr' and self.row is not None:
            if self.table is not None:
                self.table.append(self.row)
            self.row = None
        elif tag == 'table' and self.table is not None:
            self.blocks.append(('table', self.table, self.quote_depth))
            self.table = None
        elif self.cell is not None:
            return
        elif tag == 'a' and self.link_href:
            self.buf.append(f'[{self._ref(self.link_href)}]')
            self.link_href = None
        elif tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
            self._flush(kind=self.heading or 'h3')
            self.heading = None
        elif tag in BLOCK_TAGS:
            self._flush()
            if tag == 'blockquote':
                self.quote_depth = max(0, self.quote_depth - 1)
            elif tag in ('ul', 'ol') and self.lists:
                self.lists.pop()

    def handle_data(self, data):
        if self.skip:
            return
        if self.cell is not None:
            self.cell.append(data)
        else:
            self.buf.append(data)

    def close(self):
        super().close()
        self._flush()


def _render_table(rows):
    if not rows:
        return []
    ncols = max(len(r) for r in rows)
    rows = [r + [''] * (ncols - len(r)) for r in rows]
    widths = [max(len(r[i]) for r in rows) for i in range(ncols)]
    if sum(widths) + 3 * (ncols - 1) > WIDTH and ncols == 2:
        # Too wide for a grid: render a key/value table as a definition list.
        out = []
        for key, value in rows:
            out += textwrap.wrap(value, WIDTH, initial_indent=f'{key}: ', subsequent_indent='    ') + ['']
        return out[:-1]
    if sum(widths) + 3 * (ncols - 1) > WIDTH:
        # Too wide for a grid: fall back to one "header: value" stanza per row.
        header, out = rows[0], []
        for r in rows[1:]:
            out += [f'{h}: {v}' for h, v in zip(header, r) if v] + ['']
        return out[:-1]
    lines = [' | '.join(c.ljust(w) for c, w in zip(r, widths)).rstrip() for r in rows]
    lines.insert(1, '-+-'.join('-' * w for w in widths))
    return lines


def html_to_text(html, base_url, refs):
    parser = _Converter(base_url, refs)
    parser.feed(html)
    parser.close()

    out = []
    for kind, content, depth in parser.blocks:
        prefix = '> ' * depth
        if kind == 'table':
            lines = _render_table(content)
        elif kind.startswith('h'):
            text = content.upper() if kind in ('h1', 'h2') else content
            lines = textwrap.wrap(text, WIDTH - len(prefix))
            lines.append(('=' if kind in ('h1', 'h2') else '-') * max(map(len, lines)))
        elif content.strip('-') == '':
            lines = ['* * *'.center(WIDTH - len(prefix)).rstrip()]
        else:
            indent = '   ' if re.match(r'^(- |\d+\. )', content) else ''
            lines = textwrap.wrap(content, WIDTH - len(prefix),
                                  subsequent_indent=indent, break_on_hyphens=False)
        text = '\n'.join(prefix + line for line in lines)
        if out and depth and out[-1][1] == depth:
            out[-1] = (out[-1][0] + '\n' + prefix.rstrip() + '\n' + text, depth)
        else:
            out.append((text, depth))
    return '\n\n'.join(text for text, _ in out)


def _header():
    title = 'CRAQUELURE DIGITAL GARDEN'
    return f'{title}\n{"=" * len(title)}\n{request.host_url}\n'


def _references(refs):
    if not refs:
        return ''
    width = len(str(len(refs)))
    lines = [f'[{i}]'.rjust(width + 2) + f' {url}' for i, url in enumerate(refs, 1)]
    return '\n\nReferences\n----------\n' + '\n'.join(lines)


def _footer():
    return '\n\n' + '-' * 21 + '\nJustin Tung (c) 2026\n'


def render_listing(articles, tag_filter=None):
    refs = []
    heading = f'TAG: "{tag_filter.replace("-", " ")}"' if tag_filter else 'ARTICLES'
    parts = [_header(), heading, '-' * len(heading), '']
    for a in articles:
        ref = len(refs) + 1
        refs.append(urljoin(request.host_url, f'article/{a["slug"]}'))
        parts.append(f'* {a["title"]} [{ref}]')
        if a['subtitle']:
            parts += textwrap.wrap(a['subtitle'], WIDTH, initial_indent='  ', subsequent_indent='  ')
        parts.append(f'  {a["created"]}  ·  {", ".join(a["tags"])}')
        parts.append('')
    return ''.join(['\n'.join(parts).rstrip(), _references(refs), _footer()])


def render_article(title, subtitle, created, edited, tags, html):
    refs = []
    heading = textwrap.wrap(title.upper(), WIDTH)
    parts = [_header()] + heading + ['=' * max(map(len, heading))]
    if subtitle:
        parts += textwrap.wrap(unescape(subtitle), WIDTH)
    parts += ['', f'Created:     {created}', f'Last Edited: {edited}',
              f'Tags:        {", ".join(tags)}', '', '-' * 23, '', '']
    body = html_to_text(html, request.url, refs)
    return ''.join(['\n'.join(parts), body, _references(refs), _footer()])
