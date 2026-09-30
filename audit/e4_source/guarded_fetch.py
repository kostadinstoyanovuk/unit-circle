"""Guarded reading of ONS documentation pages for the E4 coverage record (E4-1).

Safeguards (all enforced in this file):
  1. Any URL not on the allow-list is refused before any network activity.
  2. Redirects are not followed; the status and Location are reported instead.
  3. The raw response bytes are saved under pages/, and the UTC time, HTTP
     status, byte count and SHA-256 are recorded in pages/requests.jsonl.
     A response whose Content-Type is not text/html, or which is sent as an
     attachment, is closed unread and nothing is saved.
  4. Only the visible text of a page is printed: script, style, noscript,
     template, svg, iframe, select and nav elements and every table element
     are removed, and decimal numbers, percentages, currency amounts,
     thousands-separated numbers and numbers of five or more digits are
     replaced by [num]. Output is truncated to 6,000 characters per call.
     Raw HTML is never printed; saved files are read only through this filter.

Usage (Python standard library only):
  python -B -S guarded_fetch.py fetch <url> <purpose>
  python -B -S guarded_fetch.py show  <saved-file-name> [offset]
  python -B -S guarded_fetch.py find  <saved-file-name> <keyword> [<keyword> ...]
  python -B -S guarded_fetch.py links <saved-file-name> [offset]
  python -B -S guarded_fetch.py check <url>
"""
import datetime
import gzip
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import zlib
from html.parser import HTMLParser

HERE = os.path.dirname(os.path.abspath(__file__))
PAGES = os.path.join(HERE, "pages")
LOG = os.path.join(PAGES, "requests.jsonl")
LIMIT = 6000
MAX_BYTES = 5 * 1024 * 1024
TIMEOUT = 30
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36")

# ---------------------------------------------------------------- allow-list
HOST = "www.ons.gov.uk"
ALLOWED_PATHS = {
    "/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi":
        "real-time database landing page",
    "/economy/grossdomesticproductgdp/datasets/revisionstrianglesforukgdpabmi":
        "revision triangles landing page",
    "/methodology/methodologytopicsandstatisticalconcepts/revisions/"
    "revisionspoliciesforeconomicstatistics/nationalaccountsrevisionspolicyupdateddecember2017":
        "National Accounts Revisions Policy",
    "/economy/grossdomesticproductgdp/methodologies/grossdomesticproductgdpqmi":
        "GDP Quality and Methodology Information",
    "/releases/gdpquarterlynationalaccountsukjanuarytomarch2026":
        "release calendar record",
}
# Edition pages of the real-time database only: one lower-case alphanumeric
# path segment after the landing page (no dot, query, fragment or sub-path).
EDITION_RE = re.compile(
    r"^/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi/([a-z0-9]+)$")
FORBIDDEN_SUBSTRINGS = ("/timeseries/", "/bulletins/", "/articles/", "/adhocs/",
                        "/generator", "/file?uri=", "file?uri=", "/data/")
FORBIDDEN_ENDINGS = (".xls", ".xlsx", ".csv", ".zip", ".json", ".txt", ".dat", ".pdf",
                     "/data")
FORBIDDEN_SEGMENTS = {"data", "previous", "timeseries", "bulletins", "articles",
                      "adhocs", "generator", "file", "datalist", "download"}


def check_url(url):
    """Return (allowed, reason). No network activity."""
    low = url.lower()
    for s in FORBIDDEN_SUBSTRINGS:
        if s in low:
            return False, "forbidden substring %r" % s
    stripped = low.rstrip("/")
    for e in FORBIDDEN_ENDINGS:
        if stripped.endswith(e):
            return False, "forbidden ending %r" % e
    if "?" in url or "#" in url:
        return False, "query or fragment not allowed"
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.netloc != HOST:
        return False, "scheme or host not allowed"
    for seg in (s for s in p.path.split("/") if s):
        if seg.lower() in FORBIDDEN_SEGMENTS:
            return False, "forbidden path segment %r" % seg
    if p.path in ALLOWED_PATHS:
        return True, ALLOWED_PATHS[p.path]
    if EDITION_RE.match(p.path):
        return True, "edition page of the real-time database (file listing)"
    return False, "not on the allow-list"


# ----------------------------------------------------------------- redaction
_SIGN = "[-+−]?"
_PATTERNS = [
    # currency amounts
    re.compile(r"(?:[£$€]|\bGBP\s?|\bUSD\s?|\bEUR\s?)\s?" + _SIGN +
               r"\d[\d,]*(?:\.\d+)?(?:\s?(?:bn|billion|m|million|k|thousand)\b)?", re.I),
    # percentages (percent sign; "per cent", "percent" and percentage points treated alike)
    re.compile(_SIGN + r"\d[\d,]*(?:\.\d+)?\s?(?:%|per\s?cent\b|percent\b|"
               r"percentage\s+points?\b|pp\b)", re.I),
    # thousands-separated numbers
    re.compile(r"(?<![\d.,])" + _SIGN + r"\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d])"),
    # decimal numbers
    re.compile(_SIGN + r"\d*\.\d+"),
    # five or more digits
    re.compile(r"\d{5,}"),
]
_ASCII = {"–": "-", "—": "--", "‘": "'", "’": "'", "“": '"',
          "”": '"', "…": "...", " ": " ", "−": "-", "•": "*",
          "£": "GBP"}


def redact(text):
    for pat in _PATTERNS:
        text = pat.sub("[num]", text)
    return "".join(_ASCII.get(ch, ch) for ch in text)


# ------------------------------------------------------- visible-text parser
SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object",
        "canvas", "select", "nav"}
TABLE = {"table", "thead", "tbody", "tfoot", "tr", "td", "th", "caption",
         "colgroup", "col"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5",
         "h6", "section", "article", "header", "footer", "main", "aside", "br", "hr",
         "blockquote", "pre", "figure", "figcaption", "details", "summary", "title",
         "form", "fieldset", "legend", "label", "address"}


class Visible(HTMLParser):
    def __init__(self, base_url):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.skip = 0
        self.table = 0
        self.out = []
        self.links = []          # (href, text, in_table)
        self._a = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag in VOID:
            if tag in BLOCK:
                self.out.append("\n")
            return
        if tag in SKIP:
            self.skip += 1
        if tag == "table":
            self.table += 1
        if tag == "a":
            href = dict(attrs).get("href")
            self._a = [href, [], self.table > 0 or self.skip > 0]
        if tag in BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in VOID:
            return
        if tag in SKIP and self.skip > 0:
            self.skip -= 1
        if tag == "table" and self.table > 0:
            self.table -= 1
        if tag == "a" and self._a is not None:
            href, parts, hidden = self._a
            if href:
                self.links.append((href, " ".join("".join(parts).split()), hidden))
            self._a = None
        if tag in BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if self.skip or self.table:
            return
        self.out.append(data)
        if self._a is not None:
            self._a[1].append(data)

    def text(self):
        raw = "".join(self.out)
        lines = [" ".join(line.split()) for line in raw.split("\n")]
        kept, blank = [], False
        for line in lines:
            if line:
                kept.append(line)
                blank = False
            elif not blank:
                kept.append("")
                blank = True
        return redact("\n".join(kept).strip())


def decode_body(raw, encoding_header):
    enc = (encoding_header or "").lower()
    try:
        if "gzip" in enc:
            raw = gzip.decompress(raw)
        elif "deflate" in enc:
            raw = zlib.decompress(raw)
    except Exception:
        pass
    return raw.decode("utf-8", errors="replace")


def page_text(path, base_url):
    with open(path, "rb") as fh:
        raw = fh.read()
    meta = find_record(os.path.basename(path)) or {}
    parser = Visible(base_url or meta.get("url", ""))
    parser.feed(decode_body(raw, meta.get("content_encoding")))
    parser.close()
    return parser


# ------------------------------------------------------------------ records
def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def records():
    if not os.path.exists(LOG):
        return []
    with open(LOG, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def find_record(saved_name):
    for rec in records():
        if rec.get("saved_file") == saved_name:
            return rec
    return None


def append_record(rec):
    os.makedirs(PAGES, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def emit(s):
    sys.stdout.write(s)
    if not s.endswith("\n"):
        sys.stdout.write("\n")


def fetch(url, purpose):
    seq = len(records()) + 1
    allowed, reason = check_url(url)
    rec = {"seq": seq, "url": url, "purpose": purpose, "allow_list": reason,
           "utc_request": utc_now()}
    if not allowed:
        rec.update({"outcome": "refused by the allow-list; no network activity"})
        append_record(rec)
        emit("REFUSED (no request made): %s -- %s" % (url, reason))
        return
    opener = urllib.request.build_opener(NoRedirect())
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "identity",
    })
    status, headers, body, error = None, None, None, None
    try:
        resp = opener.open(req, timeout=TIMEOUT)
        status, headers = resp.status, resp.headers
    except urllib.error.HTTPError as e:
        status, headers, resp = e.code, e.headers, e
    except Exception as e:  # network failure: nothing received
        error = "%s: %s" % (type(e).__name__, e)
        resp = None
    rec["utc_response"] = utc_now()
    if resp is None:
        rec.update({"outcome": "no response", "error": error})
        append_record(rec)
        emit("NO RESPONSE: %s -- %s" % (url, error))
        return
    ctype = (headers.get("Content-Type") or "") if headers else ""
    disp = (headers.get("Content-Disposition") or "") if headers else ""
    location = headers.get("Location") if headers else None
    rec.update({"status": status, "content_type": ctype, "location": location,
                "content_encoding": headers.get("Content-Encoding") if headers else None})
    if ("text/html" not in ctype.lower()) or ("attachment" in disp.lower()):
        try:
            resp.close()
        except Exception:
            pass
        rec.update({"outcome": "closed unread: not an HTML page (Content-Type %r, "
                               "Content-Disposition %r); nothing saved" % (ctype, disp)})
        append_record(rec)
        emit("CLOSED UNREAD: HTTP %s, Content-Type %r, Content-Disposition %r, Location %r"
             % (status, ctype, disp, location))
        return
    body = resp.read(MAX_BYTES + 1)
    truncated = len(body) > MAX_BYTES
    body = body[:MAX_BYTES]
    tail = [s for s in urllib.parse.urlsplit(url).path.split("/") if s][-1]
    stamp = rec["utc_response"].replace("-", "").replace(":", "")
    name = "%02d_%s_%s.html" % (seq, tail[:60], stamp)
    os.makedirs(PAGES, exist_ok=True)
    with open(os.path.join(PAGES, name), "wb") as fh:
        fh.write(body)
    rec.update({"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest(),
                "saved_file": name, "truncated_at_max_bytes": truncated,
                "outcome": "saved"})
    append_record(rec)
    parser = Visible(url)
    parser.feed(decode_body(body, rec["content_encoding"]))
    parser.close()
    text = parser.text()
    ok_links = [l for l in parser.links
                if check_url(urllib.parse.urljoin(url, l[0]))[0]]
    emit("URL: %s\nRequest UTC: %s  Response UTC: %s\nHTTP: %s  Location: %s\n"
         "Content-Type: %s\nBytes: %d  SHA-256: %s\nSaved: pages/%s\n"
         "Visible text: %d characters after filtering; allow-listed link targets: %d"
         % (url, rec["utc_request"], rec["utc_response"], status, location, ctype,
            len(body), rec["sha256"], name, len(text), len(ok_links)))
    emit("--- visible text, characters 0-%d ---" % min(LIMIT, len(text)))
    emit(text[:LIMIT])


def show(saved, offset):
    parser = page_text(os.path.join(PAGES, saved), None)
    text = parser.text()
    emit("--- %s: visible text, characters %d-%d of %d ---"
         % (saved, offset, min(offset + LIMIT, len(text)), len(text)))
    emit(text[offset:offset + LIMIT])


def find(saved, keywords):
    parser = page_text(os.path.join(PAGES, saved), None)
    text = parser.text()
    low = text.lower()
    hits = []
    for kw in keywords:
        start = 0
        while True:
            i = low.find(kw.lower(), start)
            if i < 0:
                break
            hits.append(i)
            start = i + 1
    hits = sorted(set(hits))
    out, last_end = [], -1
    for i in hits:
        a, b = max(0, i - 350), min(len(text), i + 350)
        if a <= last_end:
            a = last_end
        if b <= a:
            continue
        out.append("[@%d] ...%s..." % (a, text[a:b]))
        last_end = b
    body = "\n\n".join(out) if out else "(no match)"
    emit("--- %s: %d match positions for %r; context printed (limit %d characters) ---"
         % (saved, len(hits), keywords, LIMIT))
    emit(body[:LIMIT])


def links(saved, offset):
    rec = find_record(saved) or {}
    parser = page_text(os.path.join(PAGES, saved), rec.get("url"))
    lines = []
    for href, text, hidden in parser.links:
        absu = urllib.parse.urljoin(rec.get("url", ""), href)
        if check_url(absu)[0]:
            label = "(link text inside a removed element)" if hidden else redact(text)
            lines.append("%s | %s" % (absu, label))
    seen, uniq = set(), []
    for line in lines:
        if line not in seen:
            seen.add(line)
            uniq.append(line)
    body = "\n".join(uniq)
    emit("--- %s: %d allow-listed link targets; characters %d-%d of %d ---"
         % (saved, len(uniq), offset, min(offset + LIMIT, len(body)), len(body)))
    emit(body[offset:offset + LIMIT])


def main(argv):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    if len(argv) < 2:
        emit(__doc__)
        return 2
    mode = argv[1]
    if mode == "fetch" and len(argv) >= 4:
        fetch(argv[2], " ".join(argv[3:]))
    elif mode == "show" and len(argv) >= 3:
        show(argv[2], int(argv[3]) if len(argv) > 3 else 0)
    elif mode == "find" and len(argv) >= 4:
        find(argv[2], argv[3:])
    elif mode == "links" and len(argv) >= 3:
        links(argv[2], int(argv[3]) if len(argv) > 3 else 0)
    elif mode == "check" and len(argv) >= 3:
        emit("%s -> %s" % (argv[2], check_url(argv[2])))
    else:
        emit(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
