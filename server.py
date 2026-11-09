#!/usr/bin/env python3
"""BrandCheck — local fashion brand name vetting tool.

Run locally:  python3 server.py   then open http://localhost:8765
In the cloud it reads PORT from the environment and listens on all interfaces.
No third-party packages required.
"""
import json
import os
import threading
from collections import deque
import socket
import time
import re
import ssl
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs, quote

from vetting import vet_name

PORT = int(os.environ.get("PORT", "8765"))
HOST = "0.0.0.0" if "PORT" in os.environ else "127.0.0.1"
RATE_LIMIT = int(os.environ.get("RATE_LIMIT", "20"))    # checks per visitor...
RATE_WINDOW = int(os.environ.get("RATE_WINDOW", "600"))  # ...per this many seconds
CACHE_TTL = 900  # seconds a result is reused for identical searches
ROOT = Path(__file__).parent
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130 Safari/537.36")
TIMEOUT = 10

try:
    import certifi  # optional
    SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except Exception:
    SSL_CTX = ssl.create_default_context()

POOL = ThreadPoolExecutor(max_workers=24)


def fetch(url, read_body=False, headers=None):
    """Return (status, body_text_or_None). Status -1 means network error."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=SSL_CTX) as r:
            body = r.read(3_000_000).decode("utf-8", "replace") if read_body else None
            return r.status, body
    except urllib.error.HTTPError as e:
        return e.code, None
    except Exception:
        return -1, None


# ---------------------------------------------------------------- domains
def _dns_exists(domain):
    try:
        socket.getaddrinfo(domain, None)
        return True
    except Exception:
        return False


def check_domain(domain):
    status = -1
    for attempt in range(2):
        status, _ = fetch(f"https://rdap.org/domain/{domain}",
                          headers={"Accept": "application/rdap+json"})
        if status != 429:
            break
        time.sleep(1.5)
    if status == 404:
        state = "available"
    elif status == 200:
        state = "taken"
    else:  # registry didn't answer — fall back to DNS
        state = "taken" if _dns_exists(domain) else "likely"
    return {
        "domain": domain,
        "status": state,
        "buy": f"https://www.namecheap.com/domains/registration/results/?domain={domain}",
        "whois": f"https://lookup.icann.org/en/lookup?name={domain}",
    }


# ---------------------------------------------------------------- handles
def _tiktok(h):
    s, body = fetch(f"https://www.tiktok.com/@{h}", read_body=True)
    if body:
        m = re.search(r'"statusCode":(\d+)', body)
        if m:
            return "taken" if m.group(1) == "0" else "available"
    return "unknown"


def _youtube(h):
    s, _ = fetch(f"https://www.youtube.com/@{h}")
    return {200: "taken", 404: "available"}.get(s, "unknown")


def _pinterest(h):
    s, body = fetch(f"https://www.pinterest.com/{h}/", read_body=True)
    if s == 404:
        return "available"
    if body:
        if re.search(r"<title[^>]*>[^<]*Profile \| Pinterest", body):
            return "taken"
        if re.search(r"<title[^>]*>\s*</title>", body):
            return "available"
    return "unknown"


def _x(h):
    s, _ = fetch(f"https://x.com/{h}")
    return {200: "taken", 404: "available"}.get(s, "unknown")


def _manual(_h):
    return "manual"


PLATFORMS = [
    ("Instagram", "https://www.instagram.com/{h}/", _manual),
    ("TikTok", "https://www.tiktok.com/@{h}", _tiktok),
    ("Threads", "https://www.threads.net/@{h}", _manual),
    ("Pinterest", "https://www.pinterest.com/{h}/", _pinterest),
    ("YouTube", "https://www.youtube.com/@{h}", _youtube),
    ("X", "https://x.com/{h}", _x),
]


def check_handle(platform, url_tpl, fn, handle):
    try:
        status = fn(handle)
    except Exception:
        status = "unknown"
    return {"platform": platform, "handle": handle, "status": status,
            "url": url_tpl.format(h=handle)}


# ---------------------------------------------------------------- trademark links
def trademark_links(name):
    q = quote(name)
    return [
        {"label": "USPTO Trademark Search (US)",
         "url": f"https://tmsearch.uspto.gov/search/search-results?query={q}&section=default"},
        {"label": "WIPO Global Brand Database",
         "url": f"https://branddb.wipo.int/en/quicksearch?by=brandName&v={q}&rows=30&sort=score%20desc&start=0&_=1"},
        {"label": "EUIPO eSearch (EU)",
         "url": f"https://euipo.europa.eu/eSearch/#basic/1+1+1+1/100+100+100+100/{q}"},
        {"label": "UK IPO",
         "url": f"https://trademarks.ipo.gov.uk/ipo-tmtext?searchType=searchByText&text={q}"},
        {"label": "Google: common-law use",
         "url": "https://www.google.com/search?q=" + quote(f'"{name}" clothing OR apparel OR fashion OR brand')},
        {"label": "Etsy / Amazon sellers",
         "url": "https://www.etsy.com/search?q=" + q},
    ]


# ---------------------------------------------------------------- orchestration
def slug(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def domain_list(s, tlds, variants):
    doms = [f"{s}.{t}" for t in tlds]
    if variants:
        doms += [f"{p}{s}.com" for p in ("shop", "wear", "get")]
        doms += [f"{s}{x}.com" for x in ("studio", "official", "brand", "clothing")]
    return doms


def check_all(name, tlds, variants, handle_override=None):
    s = slug(name)
    if not s:
        return {"error": "Name must contain letters or numbers."}
    handle = (handle_override or s).lower()
    dom_futs = [POOL.submit(check_domain, d) for d in domain_list(s, tlds, variants)]
    h_futs = [POOL.submit(check_handle, p, u, f, handle) for p, u, f in PLATFORMS]
    vet = vet_name(name)
    return {
        "name": name,
        "slug": s,
        "vetting": vet,
        "domains": [f.result() for f in dom_futs],
        "handles": [f.result() for f in h_futs],
        "trademark_links": trademark_links(name),
    }


_lock = threading.Lock()
_hits = {}    # ip -> deque of request timestamps
_cache = {}   # key -> (timestamp, result)


def allow(ip):
    now = time.time()
    with _lock:
        q = _hits.setdefault(ip, deque())
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return False
        q.append(now)
        if len(_hits) > 10000:  # drop idle visitors
            for k in [k for k, v in _hits.items() if not v]:
                del _hits[k]
        return True


def cached_check(name, tlds, variants, handle):
    key = (name.lower(), tuple(tlds), variants, handle)
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1], True
    result = check_all(name, tlds, variants, handle)
    with _lock:
        if len(_cache) > 500:
            for k in sorted(_cache, key=lambda k: _cache[k][0])[:100]:
                del _cache[k]
        _cache[key] = (now, result)
    return result, False


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=str(ROOT / "static"), **kw)

    def log_message(self, fmt, *args):
        pass

    def do_GET(self):
        u = urlparse(self.path)
        if u.path == "/api/check":
            q = parse_qs(u.query)
            name = (q.get("name") or [""])[0].strip()[:60]
            tlds = [t for t in (q.get("tlds") or ["com,co,shop"])[0].split(",")
                    if re.fullmatch(r"[a-z]{2,20}", t)][:12]
            variants = (q.get("variants") or ["0"])[0] == "1"
            handle = (q.get("handle") or [""])[0].strip()
            handle = re.sub(r"[^a-zA-Z0-9._]", "", handle)[:30] or None
            fwd = self.headers.get("X-Forwarded-For", "")
            ip = fwd.split(",")[0].strip() or self.client_address[0]
            key = (name.lower(), tuple(tlds), variants, handle)
            if key in _cache and time.time() - _cache[key][0] < CACHE_TTL:
                result, status = _cache[key][1], 200  # cached answers are free
            elif not allow(ip):
                result, status = {"error": "You've run a lot of checks — please wait a few minutes and try again."}, 429
            else:
                result, status = cached_check(name, tlds, variants, handle)[0], 200
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()


if __name__ == "__main__":
    print(f"BrandCheck running → http://localhost:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
