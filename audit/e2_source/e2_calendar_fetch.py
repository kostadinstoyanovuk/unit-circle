"""Guarded reading of the ONS release calendar for the E2 release-rule record.

Purpose: complete the "Submission record for the release rule" of prereg/E2.md from the ONS release
calendar only (dates and times; no bulletin, dataset, series or data page).

Safeguards (all enforced in this file):
  1. Only two kinds of address are ever requested, and every other address is refused before any
     network activity:
       (a) the release-calendar search page https://www.ons.gov.uk/releasecalendar with a query made
           only of the keys and values in LISTING_KEYS (a search of the calendar for the keywords
           "labour market overview", published or upcoming, sorted by date);
       (b) a release-calendar record https://www.ons.gov.uk/releases/labourmarket<letters and digits>
           (nothing else on the address).
     Addresses with any other query, with a fragment, on another host or scheme, or containing a
     bulletin, dataset, time-series, article, ad hoc, generator, download, data or file element are
     refused.
  2. Redirects are not followed; the status and Location are reported instead.
  3. The raw response bytes are saved under pages/, and the UTC time, HTTP status, byte count and
     SHA-256 are recorded in pages/requests.jsonl. A response whose Content-Type is not text/html, or
     which is sent as an attachment, is closed unread and nothing is saved.
  4. Only the visible text of a page is printed: script, style, noscript, template, svg, iframe, select
     and nav elements and every table element are removed. Every run of digits is replaced by [num]
     except calendar dates ("15 September 2026", "September 2026"), clock times ("7:00am", "07:00")
     and four-digit years from 2020 to 2039. Output is truncated to 6,000 characters per call. Raw HTML
     is never printed; saved files are read only through this filter.

Usage (Python standard library only):
  python -B -S e2_calendar_fetch.py selftest
  python -B -S e2_calendar_fetch.py check <url>
  python -B -S e2_calendar_fetch.py fetch <url> <purpose>
  python -B -S e2_calendar_fetch.py show  <saved-file-name> [offset]
  python -B -S e2_calendar_fetch.py links <saved-file-name> [offset]
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
LISTING_PATH = "/releasecalendar"
LISTING_KEYS = {
    "keywords": {"labour market overview"},
    "release-type": {"type-published", "type-upcoming"},
    "sort": {"date-newest", "date-oldest", "relevance"},
    "limit": {"10", "20", "50"},
    "page": {"1", "2", "3"},
    "highlight": {"true"},
}


def listing_query_ok(query):
    """Every key and value must be on the fixed lists above; no key twice; keywords required."""
    try:
        pairs = urllib.parse.parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return False
    seen = set()
    for k, v in pairs:
        if k in seen or k not in LISTING_KEYS or v not in LISTING_KEYS[k]:
            return False
        seen.add(k)
    return "keywords" in seen
RECORD_RE = re.compile(r"^/releases/labourmarket[a-z0-9]{1,80}$")
FORBIDDEN_SUBSTRINGS = ("/timeseries/", "/bulletins/", "/articles/", "/adhocs/", "/datasets/",
                        "/generator", "/file?uri=", "file?uri=", "/data/", "/employmentandlabourmarket/")
FORBIDDEN_ENDINGS = (".xls", ".xlsx", ".csv", ".zip", ".json", ".txt", ".dat", ".pdf", "/data")
FORBIDDEN_SEGMENTS = {"data", "previous", "timeseries", "bulletins", "articles", "adhocs",
                      "generator", "file", "datalist", "download", "datasets", "lms", "mgsx"}


def check_url(url):
    """Return (allowed, reason). No network activity."""
    low = url.lower()
    for s in FORBIDDEN_SUBSTRINGS:
        if s in low:
            return False, "forbidden substring %r" % s
    stripped = low.split("?")[0].rstrip("/")
    for e in FORBIDDEN_ENDINGS:
        if stripped.endswith(e):
            return False, "forbidden ending %r" % e
    if "#" in url:
        return False, "fragment not allowed"
    p = urllib.parse.urlsplit(url)
    if p.scheme != "https" or p.netloc != HOST:
        return False, "scheme or host not allowed"
    for seg in (s for s in p.path.split("/") if s):
        if seg.lower() in FORBIDDEN_SEGMENTS:
            return False, "forbidden path segment %r" % seg
    if p.path == LISTING_PATH:
        if listing_query_ok(p.query):
            return True, "release-calendar search page for labour market overview"
        return False, "query not on the allow-list"
    if p.query:
        return False, "query not allowed on a record"
    if RECORD_RE.match(p.path):
        return True, "release-calendar record"
    return False, "not on the allow-list"


# ----------------------------------------------------------------- redaction
_MON = ("January|February|March|April|May|June|July|August|September|October|"
        "November|December")
_KEEP = [
    re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:%s)\s+20[2-3]\d\b" % _MON),   # 15 September 2026
    re.compile(r"\b(?:%s)\s+20[2-3]\d\b" % _MON),                              # September 2026
    re.compile(r"\b(?:0?[1-9]|[12]\d|3[01])\s+(?:%s)\b" % _MON),               # 15 September
    re.compile(r"\b(?:1[0-2]|0?[1-9])[:.][0-5]\d\s?(?:am|pm)\b", re.I),        # 7:00am
    re.compile(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b"),                             # 07:00
    re.compile(r"\b20[2-3]\d\b"),                                              # 2026
]
_ANY_NUM = re.compile(r"\d[\d.,:]*\d|\d")
_ASCII = {"–": "-", "—": "--", "‘": "'", "’": "'", "“": '"',
          "”": '"', "…": "...", " ": " ", "−": "-", "•": "*",
          "£": "GBP"}


def redact(text):
    saved = []

    def protect(m):
        saved.append(m.group(0))
        return "\u0001" + chr(0xE000 + len(saved) - 1) + "\u0002"     # placeholder holds no digit

    for pat in _KEEP:
        text = pat.sub(protect, text)
    text = _ANY_NUM.sub("[num]", text)
    text = re.sub("\u0001(.)\u0002", lambda m: saved[ord(m.group(1)) - 0xE000], text)
    return "".join(_ASCII.get(ch, ch) for ch in text)


# ------------------------------------------------------- visible-text parser
SKIP = {"script", "style", "noscript", "template", "svg", "iframe", "object",
        "canvas", "select", "nav"}
VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
BLOCK = {"p", "div", "li", "ul", "ol", "dl", "dt", "dd", "h1", "h2", "h3", "h4", "h5",
         "h6", "section", "article", "header", "footer", "main", "aside", "br", "hr",
         "blockquote", "pre", "figure", "figcaption", "details", "summary", "title",
         "form", "fieldset", "legend", "label", "address"}


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.table = 0
        self.out = []
        self.links = []          # (href, text, hidden)
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
            self._a = [dict(attrs).get("href"), [], self.table > 0 or self.skip > 0]
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


def parse_saved(saved):
    with open(os.path.join(PAGES, saved), "rb") as fh:
        raw = fh.read()
    meta = find_record(saved) or {}
    parser = Visible()
    parser.feed(decode_body(raw, meta.get("content_encoding")))
    parser.close()
    return parser, meta


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
    status, headers, resp, error = None, None, None, None
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
    parser = Visible()
    parser.feed(decode_body(body, rec["content_encoding"]))
    parser.close()
    text = parser.text()
    emit("URL: %s\nRequest UTC: %s  Response UTC: %s\nHTTP: %s  Location: %s\n"
         "Content-Type: %s\nBytes: %d  SHA-256: %s\nSaved: pages/%s\n"
         "Visible text: %d characters after filtering"
         % (url, rec["utc_request"], rec["utc_response"], status, location, ctype,
            len(body), rec["sha256"], name, len(text)))
    emit("--- visible text, characters 0-%d ---" % min(LIMIT, len(text)))
    emit(text[:LIMIT])


def show(saved, offset):
    parser, _ = parse_saved(saved)
    text = parser.text()
    emit("--- %s: visible text, characters %d-%d of %d ---"
         % (saved, offset, min(offset + LIMIT, len(text)), len(text)))
    emit(text[offset:offset + LIMIT])


def links(saved, offset):
    parser, meta = parse_saved(saved)
    lines = []
    for href, text, hidden in parser.links:
        absu = urllib.parse.urljoin(meta.get("url", ""), href)
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


def selftest():
    cases = [
        ("https://www.ons.gov.uk/releasecalendar?keywords=labour+market+overview&release-type=type-published&sort=date-newest", True),
        ("https://www.ons.gov.uk/releasecalendar?keywords=labour%20market%20overview&release-type=type-upcoming&sort=date-oldest", True),
        ("https://www.ons.gov.uk/releasecalendar?keywords=labour+market+overview", True),
        ("https://www.ons.gov.uk/releasecalendar", False),
        ("https://www.ons.gov.uk/releasecalendar?keywords=unemployment&release-type=type-published", False),
        ("https://www.ons.gov.uk/releasecalendar?keywords=labour+market+overview&x=1", False),
        ("https://www.ons.gov.uk/releasecalendar?keywords=labour+market+overview&release-type=type-published&release-type=type-upcoming", False),
        ("https://www.ons.gov.uk/releasecalendar?release-type=type-published&sort=date-newest", False),
        ("https://www.ons.gov.uk/releasecalendar?query=labour+market+overview", False),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewukseptember2026", True),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewuk15september2026", True),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewukoctober2026/", False),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewukoctober2026?x=1", False),
        ("https://www.ons.gov.uk/releases/gdpquarterlynationalaccountsukapriltojune2026", False),
        ("https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms", False),
        ("https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/bulletins/uklabourmarket/september2026", False),
        ("https://www.ons.gov.uk/employmentandlabourmarket/peopleinwork/employmentandemployeetypes/datasets/labourmarketstatistics", False),
        ("https://www.ons.gov.uk/generator?format=csv&uri=/employmentandlabourmarket/peoplenotinwork/unemployment/timeseries/mgsx/lms", False),
        ("http://www.ons.gov.uk/releases/labourmarketoverviewukseptember2026", False),
        ("https://ons.gov.uk/releases/labourmarketoverviewukseptember2026", False),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewukseptember2026.csv", False),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewukseptember2026#x", False),
        ("https://www.ons.gov.uk/releases/labourmarket/data", False),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewuk/mgsx", False),
        ("https://www.ons.gov.uk/releases/labourmarketoverviewuk-september-2026", False),
        ("https://www.ons.gov.uk/releases/Labourmarketoverviewuk", False),
    ]
    bad = 0
    for u, want in cases:
        got = check_url(u)[0]
        bad += (got != want)
        emit("%s  %s  %s" % ("ok  " if got == want else "FAIL", "allow " if got else "refuse", u))
    t = ("Release date: 15 September 2026 7:00am. Next 20 October 2026 07:00. 4.7% and 5.1 and 1,234 "
         "and 1633 456780 and 2026 and September 2026 and 3 of 12 and 6.2 per cent and 1,5 and 0.5pp.")
    out = redact(t)
    emit("redaction sample: " + out)
    for must in ("15 September 2026 7:00am", "20 October 2026 07:00", "[num]% and [num] and [num] and [num] [num]"):
        if must not in out:
            bad += 1
            emit("FAIL redaction: missing %r" % must)
    if re.search(r"4\.7|5\.1|1,234|456780|6\.2", out):
        bad += 1
        emit("FAIL redaction: a number survived")
    return 1 if bad else 0


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
    elif mode == "links" and len(argv) >= 3:
        links(argv[2], int(argv[3]) if len(argv) > 3 else 0)
    elif mode == "check" and len(argv) >= 3:
        emit("%s -> %s" % (argv[2], check_url(argv[2])))
    elif mode == "selftest":
        return selftest()
    else:
        emit(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
