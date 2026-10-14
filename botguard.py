"""Anti-scraping measures: AI crawler blocking, a logging honeypot, opt-out headers, and rate limits."""
import logging
import re
import sys
from datetime import datetime, timezone

from flask import request, abort
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Crawlers that identify themselves as AI/LLM data collectors. Disguised scrapers won't match.
AI_AGENTS = re.compile(
    r'GPTBot|ChatGPT-User|OAI-SearchBot|ClaudeBot|Claude-User|Claude-SearchBot|anthropic-ai'
    r'|CCBot|Bytespider|PerplexityBot|Perplexity-User|meta-externalagent|meta-externalfetcher'
    r'|FacebookBot|Amazonbot|Applebot|cohere-ai|cohere-training-data-crawler|Diffbot'
    r'|ImagesiftBot|Omgili|Timpibot|YouBot|AI2Bot|Ai2Bot-Dolma|PanguBot|Kangaroo Bot'
    r'|DuckAssistBot|MistralAI-User|img2dataset|Scrapy|PetalBot|SemrushBot|AhrefsBot',
    re.IGNORECASE,
)

# Linked invisibly from every page and disallowed in robots.txt: only rule-ignoring bots ever request it.
TRAP_PATH = '/archive/full-export'

UNGUARDED = {'robots'}                    # endpoints even blocked clients may fetch
UNLIMITED = {'static', 'article_image'}   # assets loaded alongside a page; don't count toward rate limits

banned_ips = {}   # ip -> ban time. Per process: clears on restart/redeploy.

log = logging.getLogger('craquelure.bots')
log.setLevel(logging.INFO)
log.propagate = False
_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter('%(asctime)s [bots] %(message)s'))
log.addHandler(_handler)

limiter = Limiter(get_remote_address, default_limits=['30 per minute', '300 per hour'],
                  storage_uri='memory://')


def _describe():
    return (f'ip={request.remote_addr} xff="{request.headers.get("X-Forwarded-For", "")}" '
            f'ua="{request.headers.get("User-Agent", "")}" path={request.full_path.rstrip("?")}')


def init_app(app):
    limiter.init_app(app)

    @limiter.request_filter
    def _exempt_assets():
        return request.endpoint in UNLIMITED

    @app.before_request
    def _guard():
        if request.endpoint in UNGUARDED:
            return
        if request.remote_addr in banned_ips:
            log.info(f'BANNED {_describe()}')
            abort(403)
        if AI_AGENTS.search(request.headers.get('User-Agent', '')):
            log.info(f'AI_AGENT {_describe()}')
            abort(403)

    @app.route(TRAP_PATH)
    @limiter.exempt
    def honeypot():
        banned_ips[request.remote_addr] = datetime.now(timezone.utc)
        log.warning(f'HONEYPOT {_describe()} -> banned ({len(banned_ips)} total)')
        abort(403)

    @app.after_request
    def _optout_headers(resp):
        resp.headers['X-Robots-Tag'] = 'noai, noimageai'
        resp.headers['TDM-Reservation'] = '1'
        return resp

    @app.errorhandler(429)
    def _rate_limited(e):
        log.info(f'RATE_LIMIT {_describe()} ({e.description})')
        return 'Too many requests. Slow down.\n', 429, {'Content-Type': 'text/plain'}
