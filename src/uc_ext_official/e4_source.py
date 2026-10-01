"""E4 X.2: one edition of the ONS real-time database, acquired once and mapped by headers and availability.

prereg/E4.md section 4 and Annex B step 2, as stages that fail closed. The readings taken where the
registered text is silent are listed in docs/E4_X2_READINGS.md (R-X2.1 onwards) and cited below.

list      Reads saved ONS pages only (the dataset page, edition pages, release-calendar records): the list
          of editions, each edition's release date and time where official metadata establish them, and the
          release rule applied to the verified public-registration timestamp. Writes nothing.
select    The same evaluation, with G4 for E4; writes audit/e4_source/edition.json once. It refuses while
          the evidence cannot exclude a later edition released before registration, unless the operator
          records that the missing evidence cannot be obtained (R-X2.5).
acquire   G4 for E4 and the committed edition record. Stores the selected edition's workbook once,
          read-only, at a git-ignored path under data/raw/, with audit/E4_ACQUISITION.json and a
          DATA_MANIFEST.csv row. Only the selected edition's file URL and only an xlsx package are
          accepted. The X.3 record is not required (Annex B: the download precedes X.3).
map       G4, the committed acquisition record, the workbook's hash and read-only state. Section 4,
          "Structure mapping at X.2", steps 1 to 5, from headers and cell types only: no numeric value is
          read. Every stop is recorded with its step and reason and ends the stage.
levels    `read_level_tables`, for the registered run only: G4, the X.3 record, the frozen code and the
          committed records; builds the level table from the recorded mapping and returns counts and
          hashes for printing, never a level.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import urllib.parse
from collections import defaultdict
from html.parser import HTMLParser
from zoneinfo import ZoneInfo

import numpy as np

from uc_e4.table import (KINDS, ErrorValue, RawPart, Stop, availability_report, build_tables, mask_digits,
                         parse_quarter, parse_release_month)

from . import gates, records
from .workbook import Workbook, WorkbookError, column_letter, serial_to_date

LONDON = ZoneInfo("Europe/London")
UTC = _dt.timezone.utc
HOST = "www.ons.gov.uk"
DATASET_PATH = "/economy/grossdomesticproductgdp/datasets/realtimedatabaseforukgdpabmi"
TRIANGLES_PATH = "/economy/grossdomesticproductgdp/datasets/revisionstrianglesforukgdpabmi"
DATASET_URL = f"https://{HOST}{DATASET_PATH}"
SOURCE_TITLE = "ONS, GDP in chained volume measures - real-time database (ABMI)"
REGISTRATION_RECORD = "audit/E4_REGISTRATION.json"
SOURCE_DIR = "audit/e4_source"
EDITION_RECORD = f"{SOURCE_DIR}/edition.json"
ACQUISITION_RECORD = "audit/E4_ACQUISITION.json"
RAW_PREFIX = "data/raw/E4_ABMI_realtime_"
ATTEMPTS_LOG = f"{SOURCE_DIR}/structure-attempts.jsonl"
MAPPING_JSON = f"{SOURCE_DIR}/structure-mapping.json"
MAPPING_TEXT = f"{SOURCE_DIR}/structure-mapping.txt"
# The manifest note that marks a row whose file is kept out of git (tools/check_data.py uses the same words).
NOT_DISTRIBUTED = "Not distributed in this repository"
EDITION_SUFFIX = re.compile(r"\s*edition of this dataset\s*$", re.IGNORECASE)


class SourceStop(Stop):
    """A stop under section 4 outside steps 1 to 5 (the release rule: the edition cannot be obtained or
    identified, or the workbook's title, cover or notes name another edition or release date). Section 13:
    the amendment then states which file is used."""

    def __init__(self, step, reason, detail=None):
        Exception.__init__(self, f"E4 section 4, {step}: {reason}")
        self.step, self.reason, self.detail = step, reason, detail


# ------------------------------------------------------------------ blanking (Annex C filter, ported)

_SIGN = "[-+−]?"
_BLANKED = [
    re.compile(r"(?:[£$€]|\bGBP\s?|\bUSD\s?|\bEUR\s?)\s?" + _SIGN +
               r"\d[\d,]*(?:\.\d+)?(?:\s?(?:bn|billion|m|million|k|thousand)\b)?", re.I),
    re.compile(_SIGN + r"\d[\d,]*(?:\.\d+)?\s?(?:%|per\s?cent\b|percent\b|percentage\s+points?\b|pp\b)", re.I),
    re.compile(r"(?<![\d.,])" + _SIGN + r"\d{1,3}(?:,\d{3})+(?:\.\d+)?(?![\d])"),
    re.compile(_SIGN + r"\d*\.\d+"),
    re.compile(r"\d{5,}"),
]
_ASCII = {"–": "-", "—": "--", "‘": "'", "’": "'", "“": '"', "”": '"',
          "…": "...", " ": " ", "−": "-", "•": "*", "£": "GBP"}


def blank_numbers(text) -> str:
    """Decimal numbers, percentages, currency amounts, thousands-separated numbers and numbers of five or
    more digits replaced by [num], as the Annex C script did (audit/e4_source/guarded_fetch.py, `redact`)."""
    text = "" if text is None else str(text)
    for pattern in _BLANKED:
        text = pattern.sub("[num]", text)
    return "".join(_ASCII.get(ch, ch) for ch in text)


# ----------------------------------------------------------------------------- page parsing

_VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source",
         "track", "wbr"}
_HIDDEN = {"script", "style", "noscript", "template", "svg"}


class _Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.children, self.parent = tag, attrs, [], parent

    def iter(self):
        yield self
        for child in self.children:
            if isinstance(child, _Node):
                yield from child.iter()

    def text(self) -> str:
        parts = []
        for child in self.children:
            if isinstance(child, str):
                parts.append(child)
            elif child.tag not in _HIDDEN:
                parts.append(" " + child.text() + " ")
        return " ".join("".join(parts).split())

    def classes(self):
        return set((self.attrs.get("class") or "").split())


class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = _Node("#root", {}, None)
        self.current = self.root

    def handle_starttag(self, tag, attrs):
        node = _Node(tag, {key: value or "" for key, value in attrs}, self.current)
        self.current.children.append(node)
        if tag not in _VOID:
            self.current = node

    def handle_startendtag(self, tag, attrs):
        self.current.children.append(_Node(tag, {key: value or "" for key, value in attrs}, self.current))

    def handle_endtag(self, tag):
        node = self.current
        while node is not self.root and node.tag != tag:
            node = node.parent
        if node is not self.root:
            self.current = node.parent

    def handle_data(self, data):
        self.current.children.append(data)


def _tree(content) -> _Node:
    text = content.decode("utf-8", errors="replace") if isinstance(content, (bytes, bytearray)) else str(content)
    parser = _Tree()
    parser.feed(text)
    parser.close()
    return parser.root


_MONTH_NAMES = {name: number for number, names in enumerate(
    [("jan", "january"), ("feb", "february"), ("mar", "march"), ("apr", "april"), ("may",), ("jun", "june"),
     ("jul", "july"), ("aug", "august"), ("sep", "sept", "september"), ("oct", "october"), ("nov", "november"),
     ("dec", "december")], start=1) for name in names}
_DATE_TEXT = re.compile(r"\b(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})\b")
_TIME_TEXT = re.compile(r"\b(\d{1,2})[:.](\d{2})\s*(am|pm|a\.m\.|p\.m\.)?", re.IGNORECASE)


def parse_day(text):
    """A date written as '13 August 2026' (day, month name, four-digit year), or None."""
    match = _DATE_TEXT.search(text or "")
    if not match or match.group(2).lower() not in _MONTH_NAMES:
        return None
    try:
        return _dt.date(int(match.group(3)), _MONTH_NAMES[match.group(2).lower()], int(match.group(1)))
    except ValueError:
        return None


def parse_time_of_day(text):
    """A time of day written as '7:00am', '9:30 am', '12:00pm' or '07:00', or None."""
    match = _TIME_TEXT.search(text or "")
    if not match:
        return None
    hour, minute, meridiem = int(match.group(1)), int(match.group(2)), (match.group(3) or "").lower().replace(".", "")
    if meridiem:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if meridiem == "pm" else 0)
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return _dt.time(hour, minute)


def _after_label(text, label):
    """The text that follows `label` (for example 'Release date:') up to the next label, each occurrence."""
    found = []
    for match in re.finditer(re.escape(label), text, re.IGNORECASE):
        rest = text[match.end():match.end() + 80]
        rest = re.split(r"(?:Next release|Release date|Released|Contact)\s*:", rest, maxsplit=1)[0]
        found.append(" ".join(rest.split()))
    return found


def _one_date(values):
    """The single date stated by one or more occurrences of a label; None when absent or inconsistent."""
    days = {parse_day(value) for value in values}
    days.discard(None)
    return days.pop() if len(days) == 1 else None


def _absolute(href):
    return urllib.parse.urljoin(f"https://{HOST}/", href or "")


def _path_of(url):
    return urllib.parse.urlsplit(url).path.rstrip("/")


def parse_dataset_page(content) -> dict:
    """The dataset landing page: title, release date, next release and the editions in page order.

    Each edition: label (the heading without 'edition of this dataset'), the file links of its entry (URL,
    file type and size text) and the edition page linked from the entry ('Previous versions'), if any.
    """
    root = _tree(content)
    body = next((node for node in root.iter() if node.tag == "body"), root)
    text = body.text()
    editions = []
    for node in root.iter():
        if node.tag != "div" or not {"show-hide", "js-show-hide"} <= node.classes():
            continue
        heading = next((child for child in node.iter() if child.tag == "h3"), None)
        if heading is None or not EDITION_SUFFIX.search(heading.text()):
            continue
        files, pages = [], []
        for link in node.iter():
            if link.tag != "a" or not link.attrs.get("href"):
                continue
            url = _absolute(link.attrs["href"])
            if "file?uri=" in url:
                span = " ".join(link.text().split())
                kind = re.match(r"\s*([A-Za-z0-9]+)\s*\(([^)]*)\)", span)
                files.append(dict(url=url, file_type=kind.group(1).lower() if kind else None,
                                  size_text=kind.group(2) if kind else None, text=span))
            elif re.fullmatch(re.escape(DATASET_PATH) + r"/[a-z0-9]+", _path_of(url)) and urllib.parse.urlsplit(
                    url).netloc == HOST:
                pages.append(url)
        editions.append(dict(position=len(editions), label=" ".join(EDITION_SUFFIX.sub("", heading.text()).split()),
                             files=files, edition_page_url=pages[0] if len(set(pages)) == 1 else None))
    title = next((" ".join(node.text().split()) for node in root.iter() if node.tag == "title"), "")
    return dict(kind="dataset", title=title, release_date=_one_date(_after_label(text, "Release date:")),
                next_release=_one_date(_after_label(text, "Next release:")),
                next_release_text=(_after_label(text, "Next release:") or [None])[0], editions=editions)


def parse_edition_page(content) -> dict:
    """An edition page: its release date and next release as the page states them, and its file links."""
    root = _tree(content)
    body = next((node for node in root.iter() if node.tag == "body"), root)
    text = body.text()
    files = sorted({_absolute(node.attrs["href"]) for node in root.iter()
                    if node.tag == "a" and "file?uri=" in (node.attrs.get("href") or "")})
    title = next((" ".join(node.text().split()) for node in root.iter() if node.tag == "title"), "")
    return dict(kind="edition", title=title, release_date=_one_date(_after_label(text, "Release date:")),
                next_release=_one_date(_after_label(text, "Next release:")), files=files)


def parse_release_calendar(content) -> dict:
    """A release-calendar record: title, status, the stated release date and time of day (UK local time),
    the same in UTC, the next release, and whether the record lists the real-time database among its data."""
    root = _tree(content)
    body = next((node for node in root.iter() if node.tag == "body"), root)
    text = body.text()
    status = {node.attrs.get("data-gtm-release-status") for node in root.iter()
              if "data-gtm-release-status" in node.attrs}
    stated = _after_label(text, "Released:")
    days = {parse_day(value) for value in stated} - {None}
    times = {parse_time_of_day(value) for value in stated} - {None}
    day = days.pop() if len(days) == 1 else None
    time = times.pop() if len(times) == 1 and day is not None else None
    lists_dataset = any(node.tag == "a" and _path_of(_absolute(node.attrs.get("href"))) == DATASET_PATH
                        and urllib.parse.urlsplit(_absolute(node.attrs.get("href"))).netloc == HOST
                        for node in root.iter())
    heading = next((" ".join(node.text().split()) for node in root.iter() if node.tag == "h1"), "")
    return dict(kind="calendar", title=heading, status=status.pop() if len(status) == 1 else None,
                release_date=day, release_time=time,
                release_utc=None if day is None or time is None else local_to_utc(day, time),
                next_release=_one_date(_after_label(text, "Next release:")), lists_dataset=lists_dataset,
                released_text=stated)


PARSERS = dict(dataset=parse_dataset_page, edition=parse_edition_page, calendar=parse_release_calendar)


def load_page(kind, content: bytes, *, source, url=None, retrieved_utc=None) -> dict:
    """A saved page with its identity (bytes, SHA-256, source, URL and retrieval time where known)."""
    if kind not in PARSERS:
        raise ValueError(f"Unknown page kind {kind!r}")
    return dict(kind=kind, source=str(source), url=url, retrieved_utc=retrieved_utc, bytes=len(content),
                sha256=gates.sha256_bytes(content), parsed=PARSERS[kind](content))


# ---------------------------------------------------------------------------- release rule

def local_to_utc(day: _dt.date, time: _dt.time) -> _dt.datetime:
    """A UK local date and time (Europe/London) as UTC."""
    return _dt.datetime.combine(day, time, tzinfo=LONDON).astimezone(UTC)


def day_bounds_utc(day: _dt.date):
    """[start, end) of a UK local calendar day, in UTC."""
    return local_to_utc(day, _dt.time(0, 0)), local_to_utc(day + _dt.timedelta(days=1), _dt.time(0, 0))


def registration_timestamp(root) -> _dt.datetime:
    """The verified public-registration timestamp of E4 (audit/E4_REGISTRATION.json, fixed as in D-017)."""
    record = records.read_json(Path(root) / REGISTRATION_RECORD)
    return gates.utc(record["public_registration_timestamp_utc"])


def _norm(label):
    return " ".join(str(label).split()).lower()


def evaluate_editions(pages, registration_utc) -> dict:
    """The release rule of section 4 over saved pages; a pure function of the page texts and the timestamp.

    R-X2.1: an edition's release date is established from the dataset page for the edition listed first on
    that page (the page's own release date), and from nothing else; the time of day comes from a published
    release-calendar record of the same date that lists this dataset. R-X2.2: eligibility; R-X2.3: the
    latest eligible edition; R-X2.4: whether the saved pages exclude a later edition released before the
    registration (else the missing evidence is named).
    """
    registration = gates.utc(registration_utc) if isinstance(registration_utc, str) else registration_utc
    registration_day = registration.astimezone(LONDON).date()
    datasets = [p for p in pages if p["kind"] == "dataset"]
    calendars = [p for p in pages if p["kind"] == "calendar"]
    if not datasets:
        raise SourceStop("release rule", "no dataset page was given, so no edition can be identified")
    reference = max(datasets, key=lambda p: (p["parsed"]["release_date"] or _dt.date.min, p["retrieved_utc"] or ""))
    editions, order = {}, []
    for page in [reference] + [p for p in datasets if p is not reference]:
        for entry in page["parsed"]["editions"]:
            key = _norm(entry["label"])
            if key not in editions:
                editions[key] = dict(label=entry["label"], files=entry["files"],
                                     edition_page_url=entry["edition_page_url"],
                                     listed_on=[], dates=[], times=[], evidence=[])
                order.append(key)
            editions[key]["listed_on"].append(dict(page=page["source"], position=entry["position"]))
    for page in datasets:
        listed = page["parsed"]["editions"]
        if listed and page["parsed"]["release_date"]:
            first = editions[_norm(listed[0]["label"])]
            first["dates"].append(page["parsed"]["release_date"])
            first["evidence"].append(f"dataset page {page['source']} (SHA-256 {page['sha256'][:12]}...): release "
                                     f"date {page['parsed']['release_date'].isoformat()}, edition listed first")
    for key in order:
        edition = editions[key]
        dates = sorted(set(edition["dates"]))
        edition["release_date"] = dates[0] if len(dates) == 1 else None
        if len(dates) > 1:
            edition["evidence"].append("conflicting release dates on the saved pages: "
                                       + ", ".join(d.isoformat() for d in dates))
        for page in calendars:
            parsed = page["parsed"]
            if (edition["release_date"] is not None and parsed["release_date"] == edition["release_date"]
                    and parsed["lists_dataset"] and parsed["status"] == "published" and parsed["release_time"]):
                edition["times"].append(parsed["release_time"])
                edition["evidence"].append(f"release-calendar record {page['source']} (SHA-256 "
                                           f"{page['sha256'][:12]}...): '{parsed['title']}', released "
                                           f"{parsed['release_date'].isoformat()} {parsed['release_time']:%H:%M} UK time, "
                                           "lists this dataset")
        times = sorted(set(edition["times"]))
        edition["release_time"] = times[0] if len(times) == 1 else None
        if len(times) > 1:
            edition["evidence"].append("conflicting release times: " + ", ".join(f"{t:%H:%M}" for t in times))
        edition["eligible"], edition["reason"], edition["missing"] = _eligibility(edition, registration,
                                                                                registration_day)
    listing = [editions[_norm(entry["label"])] for entry in reference["parsed"]["editions"]]
    eligible = [editions[key] for key in order if editions[key]["eligible"]]
    selected, stop = None, None
    if not eligible:
        stop = "no edition on the saved pages can be established as released before the registration"
    else:
        latest = max(eligible, key=lambda e: e["release_date"])
        ties = [e for e in eligible if e["release_date"] == latest["release_date"]]
        if len(ties) > 1:
            stop = ("several eligible editions share the release date " + latest["release_date"].isoformat()
                    + ", so the latest cannot be identified")
        elif len(latest["files"]) != 1:
            stop = f"the entry of the edition '{latest['label']}' does not link exactly one file"
        else:
            selected = latest
    missing, complete = [], False
    if selected is not None:
        complete, missing = _completeness(selected, listing, datasets, registration, registration_day)
    rows = []
    for key in order:
        e = editions[key]
        rows.append(dict(label=e["label"], listed_on=e["listed_on"],
                         file_url=e["files"][0]["url"] if len(e["files"]) == 1 else None,
                         file_type=e["files"][0]["file_type"] if len(e["files"]) == 1 else None,
                         size_text=e["files"][0]["size_text"] if len(e["files"]) == 1 else None,
                         files=len(e["files"]), edition_page_url=e["edition_page_url"],
                         release_date=e["release_date"].isoformat() if e["release_date"] else None,
                         release_time_uk=f"{e['release_time']:%H:%M}" if e["release_time"] else None,
                         release_utc=(local_to_utc(e["release_date"], e["release_time"]).isoformat()
                                      if e["release_date"] and e["release_time"] else None),
                         eligible=e["eligible"], reason=e["reason"], missing_evidence=e["missing"],
                         evidence=e["evidence"]))
    chosen = None
    if selected is not None:
        chosen = next(row for row in rows if row["label"] == selected["label"])
    return dict(registration_utc=registration.isoformat(), registration_day_uk=registration_day.isoformat(),
                reference_page=reference["source"], editions=rows, selected=chosen, stop=stop,
                complete=complete, missing_evidence=missing)


def _eligibility(edition, registration, registration_day):
    day, time = edition["release_date"], edition["release_time"]
    if day is None:
        return False, "the release date is not established from the saved ONS metadata (R-X2.1)", [
            f"a saved copy of the dataset page on which '{edition['label']}' is listed first, which states its "
            "release date"]
    start, end = day_bounds_utc(day)
    if time is not None:
        # R-X2.2: a time stated to the minute is the minute [t, t + 1 min); it establishes a release before the
        # registration only when the whole minute ends no later than the registration instant.
        instant = local_to_utc(day, time)
        if instant + _dt.timedelta(minutes=1) <= registration:
            return True, f"released in the minute from {instant.isoformat()} (UTC), before the registration", []
        if instant >= registration:
            return False, f"released {instant.isoformat()} (UTC), not before the registration", []
        return False, (f"released in the minute from {instant.isoformat()} (UTC), which contains the registration "
                       "instant"), ["a release time stated to the second"]
    if end <= registration:
        return True, f"released on {day.isoformat()} (UK), a day that ended before the registration", []
    if start >= registration:
        return False, f"released on {day.isoformat()} (UK), after the registration", []
    return False, (f"released on {day.isoformat()} (UK), the day of the registration, and the time of day is not "
                   "established"), [f"the time of day of the release on {day.isoformat()}: the ONS release-calendar "
                                    "record of that release, retrieved after publication, listing this dataset"]


def _after_registration(edition, registration, registration_day):
    day, time = edition["release_date"], edition["release_time"]
    if day is None:
        return False
    if time is not None:
        return local_to_utc(day, time) >= registration
    return day_bounds_utc(day)[0] >= registration


def _completeness(selected, listing, datasets, registration, registration_day):
    """R-X2.4: the saved pages exclude a later edition released before the registration when (a) a dataset
    page lists the selected edition first and announces its next release for a later day than the
    registration, or (b) the edition listed immediately above it on the reference page is established as
    released after the registration. Otherwise the evidence that is missing is named."""
    for page in datasets:
        listed = page["parsed"]["editions"]
        nxt = page["parsed"]["next_release"]
        if listed and _norm(listed[0]["label"]) == _norm(selected["label"]) and nxt is not None:
            if day_bounds_utc(nxt)[0] >= registration:
                return True, []
    index = next((i for i, e in enumerate(listing) if _norm(e["label"]) == _norm(selected["label"])), None)
    if index is not None and index > 0 and _after_registration(listing[index - 1], registration, registration_day):
        return True, []
    missing = []
    if index is not None:
        for above in listing[:index]:
            missing += [f"'{above['label']}': {item}" for item in above["missing"]]
    if not missing:
        announced = sorted({p["parsed"]["next_release"].isoformat() for p in datasets
                            if p["parsed"]["next_release"] and p["parsed"]["editions"]
                            and _norm(p["parsed"]["editions"][0]["label"]) == _norm(selected["label"])})
        missing.append("a saved copy of the dataset page retrieved after the registration, showing the editions "
                       "released after '" + selected["label"] + "'"
                       + (f" (its page announces the next release for {', '.join(announced)})" if announced else ""))
    return False, missing


# ------------------------------------------------------------------------- guarded page fetch

FORBIDDEN_SUBSTRINGS = ("/timeseries/", "/bulletins/", "/articles/", "/adhocs/", "/generator", "file?uri=",
                        "/file", "/data/")
FORBIDDEN_ENDINGS = (".xls", ".xlsx", ".xlsm", ".csv", ".zip", ".json", ".txt", ".dat", ".pdf", ".ods", "/data")
FORBIDDEN_SEGMENTS = {"data", "previous", "timeseries", "bulletins", "articles", "adhocs", "generator", "file",
                      "datalist", "download"}
EDITION_PAGE = re.compile(r"^" + re.escape(DATASET_PATH) + r"/([a-z0-9]+)$")
CALENDAR_PAGE = re.compile(r"^/releases/([a-z0-9]+)$")


def page_url_allowed(url) -> tuple[bool, str]:
    """R-X2.6: the listing step may request only the two dataset landing pages, edition pages of the
    real-time database and release-calendar records; never a data file or a file?uri= address."""
    low = str(url).lower()
    for part in FORBIDDEN_SUBSTRINGS:
        if part in low:
            return False, f"forbidden substring {part!r}"
    if low.rstrip("/").endswith(FORBIDDEN_ENDINGS):
        return False, "forbidden ending"
    if "?" in url or "#" in url:
        return False, "query or fragment not allowed"
    parts = urllib.parse.urlsplit(url)
    if parts.scheme != "https" or parts.netloc != HOST:
        return False, "scheme or host not allowed"
    if any(segment.lower() in FORBIDDEN_SEGMENTS for segment in parts.path.split("/") if segment):
        return False, "forbidden path segment"
    path = parts.path.rstrip("/")
    if path in (DATASET_PATH, TRIANGLES_PATH):
        return True, "dataset landing page"
    if EDITION_PAGE.match(path):
        return True, "edition page of the real-time database"
    if CALENDAR_PAGE.match(path):
        return True, "release-calendar record"
    return False, "not on the allow-list"


def page_kind(url) -> str:
    path = urllib.parse.urlsplit(url).path.rstrip("/")
    if path in (DATASET_PATH, TRIANGLES_PATH):
        return "dataset"
    return "edition" if EDITION_PAGE.match(path) else "calendar"


def fetch_pages(urls, fetch, directory) -> list[dict]:
    """Request each allowed page through `fetch(url) -> (content, info)` (injected; no redirects followed by
    the caller's implementation), save it under `directory` with a request log, and return the pages.
    A refused address makes no request; a response that is not an HTML page is not saved."""
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    log = directory / "requests.jsonl"
    pages = []
    for url in urls:
        allowed, reason = page_url_allowed(url)
        entry = dict(url=url, allow_list=reason, utc_request=gates.now_utc())
        if not allowed:
            with log.open("a", encoding="utf-8", newline="\n") as output:
                output.write(json.dumps(dict(entry, outcome="refused; no request made")) + "\n")
            raise ValueError(f"Refused before any request: {url} ({reason})")
        content, info = fetch(url)
        info = info or {}
        content_type = str(info.get("content_type") or "").lower()
        if "text/html" not in content_type or "attachment" in str(info.get("content_disposition") or "").lower():
            with log.open("a", encoding="utf-8", newline="\n") as output:
                output.write(json.dumps(dict(entry, outcome="not an HTML page; nothing saved",
                                             content_type=content_type)) + "\n")
            raise ValueError(f"{url} did not return an HTML page; nothing was saved")
        retrieved = info.get("retrieved_utc") or gates.now_utc()
        name = f"{len(pages) + 1:02d}_{page_kind(url)}_{gates.sha256_bytes(content)[:12]}.html"
        (directory / name).write_bytes(content)
        with log.open("a", encoding="utf-8", newline="\n") as output:
            output.write(json.dumps(dict(entry, outcome="saved", saved_file=name, status=info.get("status"),
                                         retrieved_utc=retrieved, bytes=len(content),
                                         sha256=gates.sha256_bytes(content))) + "\n")
        pages.append(load_page(page_kind(url), content, source=name, url=url, retrieved_utc=retrieved))
    return pages


# ------------------------------------------------------------------------------ edition record

def _registration_gate(root) -> dict:
    """G4 for E4 through the E4 runner (gates.check_registration); a runner without the gate is closed."""
    try:
        return gates.check_registration(root, "e4")
    except AttributeError as error:
        raise gates.GateClosed(f"{gates.runner_path('e4')} does not offer the registration gate "
                               f"(verify_extension_gate, gate_record): {error}") from None


def _json_value(value):
    if isinstance(value, (_dt.date, _dt.datetime, _dt.time)):
        return value.isoformat()
    raise TypeError(type(value).__name__)


def _pretty(value) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False, default=_json_value) + "\n").encode("utf-8")


def format_evaluation(result) -> str:
    lines = ["E4 release rule (prereg/E4.md section 4): the latest edition released strictly before the verified "
             f"public-registration timestamp {result['registration_utc']} (UK day {result['registration_day_uk']}).",
             f"Reference listing: {result['reference_page']}", ""]
    for row in result["editions"]:
        mark = "eligible" if row["eligible"] else "not eligible"
        lines.append(f"  {row['label']} [{row['file_type'] or '?'} {row['size_text'] or ''}] {mark}: {row['reason']}")
        lines += [f"      missing: {item}" for item in row["missing_evidence"]]
    lines.append("")
    if result["selected"] is None:
        lines.append(f"No edition selected: {result['stop']}")
    else:
        lines.append(f"Selected: {result['selected']['label']} ({result['selected']['file_url']})")
        lines.append("Evidence complete: " + ("yes" if result["complete"] else "no; missing: "
                                             + "; ".join(result["missing_evidence"])))
    return "\n".join(lines) + "\n"


def list_editions(root, pages) -> dict:
    """The release rule over saved pages, without any record (the listing step)."""
    return evaluate_editions(pages, registration_timestamp(root))


def select_edition(root, pages, *, accept_missing_evidence=False) -> dict:
    """G4 for E4; the release rule; audit/e4_source/edition.json written once (R-X2.5)."""
    root = Path(root)
    gate = _registration_gate(root)
    if (root / EDITION_RECORD).exists():
        raise records.RecordExists(f"{EDITION_RECORD} already exists; the edition is selected once")
    result = evaluate_editions(pages, registration_timestamp(root))
    if result["selected"] is None:
        raise SourceStop("release rule", f"the edition cannot be identified: {result['stop']}", result)
    if not result["complete"] and not accept_missing_evidence:
        raise SourceStop("release rule", "the saved pages do not exclude a later edition released before the "
                         "registration; missing evidence: " + "; ".join(result["missing_evidence"]), result)
    record = dict(record_type="E4 edition selected under the release rule (prereg/E4.md section 4; Annex B step 2)",
                  registration=dict(record=REGISTRATION_RECORD, sha256=gates.sha256_file(root / REGISTRATION_RECORD),
                                    registration_id=gate.get("registration_id"),
                                    public_registration_timestamp_utc=result["registration_utc"]),
                  pages=[dict(kind=p["kind"], source=p["source"], url=p["url"], retrieved_utc=p["retrieved_utc"],
                              bytes=p["bytes"], sha256=p["sha256"]) for p in pages],
                  readings="docs/E4_X2_READINGS.md R-X2.1 to R-X2.5", **result,
                  accepted_missing_evidence=bool(accept_missing_evidence and not result["complete"]),
                  selected_utc=gates.now_utc())
    records.write_once(root / EDITION_RECORD, _pretty(record))
    return record


def load_edition(root) -> dict:
    path = Path(root) / EDITION_RECORD
    if not path.is_file():
        raise gates.GateClosed(f"No E4 edition record ({EDITION_RECORD}): run the selection first")
    return records.read_json(path)


# ---------------------------------------------------------------------------------- acquisition

def raw_path(edition: dict) -> str:
    """data/raw/E4_ABMI_realtime_<edition directory>.xlsx, from the selected edition's file URL."""
    uri = urllib.parse.parse_qs(urllib.parse.urlsplit(edition["file_url"]).query).get("uri", [""])[0]
    parts = [p for p in uri.split("/") if p]
    slug = re.sub(r"[^a-z0-9]", "", parts[-2].lower()) if len(parts) >= 2 else "edition"
    return f"{RAW_PREFIX}{slug or 'edition'}.xlsx"


def response_is_workbook(content: bytes) -> Workbook:
    try:
        return Workbook(content)
    except WorkbookError as error:
        raise SourceStop("release rule", f"the download is not an xlsx workbook ({error}); it is not the "
                         "selected edition's file and nothing was recorded") from None


def acquire(root, content: bytes, *, source_url: str, retrieved_utc: str, method: str, response: dict | None,
            licence: str, licence_url: str) -> dict:
    """Store the selected edition's workbook once, read-only and git-ignored, with its records."""
    root = Path(root)
    gate = _registration_gate(root)
    gates.check_committed(root, EDITION_RECORD)
    edition = load_edition(root)
    selected = edition["selected"]
    raw = raw_path(selected)
    if (root / raw).exists() or (root / ACQUISITION_RECORD).exists() or records.manifest_row(root, raw) is not None:
        raise records.RecordExists("An E4 workbook, acquisition record or manifest row already exists; the "
                                   "edition is acquired once")
    if source_url != selected["file_url"]:
        raise gates.GateClosed(f"{source_url} is not the file URL of the selected edition ({selected['file_url']})")
    if subprocess.run(["git", "check-ignore", "-q", ACQUISITION_RECORD], cwd=root).returncode == 0:
        raise gates.GateClosed(f"{ACQUISITION_RECORD} would be ignored by git; it must be committed")
    if subprocess.run(["git", "check-ignore", "-q", raw], cwd=root).returncode != 0:
        raise gates.GateClosed(f"{raw} would not be ignored by git; the workbook is kept out of the repository "
                               "(as D-041 for E1), so its path must be git-ignored before it is written")
    retrieved = gates.utc(retrieved_utc)
    if not retrieved > gates.utc(gate["public_first_verified_at_utc"]):
        raise gates.GateClosed("The retrieval is not after the verified public registration of E4 "
                               f"({gate['public_first_verified_at_utc']})")
    if not licence or not licence_url:
        raise ValueError("State the licence and the page it is taken from")
    response_is_workbook(content)
    path = root / raw
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as output:
        output.write(content)
    os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)
    release = selected["release_date"] + (f" {selected['release_time_uk']} UK time ({selected['release_utc']})"
                                          if selected.get("release_time_uk") else "")
    record = dict(record_type="E4 source acquisition (prereg/E4.md section 4; Annex B step 2)",
                  file=raw, source=SOURCE_TITLE, edition_label=selected["label"], release=release,
                  release_date=selected["release_date"], release_utc=selected.get("release_utc"),
                  source_url=selected["file_url"], landing_url=DATASET_URL, retrieval_method=method,
                  retrieved_utc=retrieved.isoformat(), http=response, bytes=len(content),
                  sha256=gates.sha256_bytes(content), licence=licence, licence_url=licence_url, read_only=True,
                  repository_copy=f"{NOT_DISTRIBUTED} (git-ignored); the SHA-256 identifies it",
                  edition_record=EDITION_RECORD, edition_record_sha256=gates.sha256_file(root / EDITION_RECORD),
                  registration=gate)
    records.write_once(root / ACQUISITION_RECORD, records.pretty(record))
    records.append_manifest_row(root, dict(
        file=raw, source_url=selected["file_url"], series_id=f"{SOURCE_TITLE}: edition {selected['label']}",
        retrieved_utc=record["retrieved_utc"], sha256=record["sha256"], licence=licence,
        notes=(f"{NOT_DISTRIBUTED}: obtain it from the source URL and check the SHA-256. Edition "
               f"'{selected['label']}', released {release}; landing page {DATASET_URL}; {len(content)} bytes; "
               f"record {ACQUISITION_RECORD}; E4 X.2 structure mapping pending ({SOURCE_DIR}/)")))
    return record


def load_acquisition(root) -> dict:
    path = Path(root) / ACQUISITION_RECORD
    if not path.is_file():
        raise gates.GateClosed("No E4 acquisition record: the edition has not been acquired")
    return records.read_json(path)


def _raw(root, acquisition) -> bytes:
    """The workbook's bytes: present, untracked, read-only and identical to the committed record."""
    root = Path(root)
    path = root / acquisition["file"]
    if not path.is_file():
        raise gates.GateClosed(f"{acquisition['file']} is missing: restore the file with SHA-256 "
                               f"{acquisition['sha256']} from {acquisition['source_url']}")
    try:
        gates.git(root, "ls-files", "--error-unmatch", acquisition["file"])
    except subprocess.CalledProcessError:
        pass
    else:
        raise gates.GateClosed(f"{acquisition['file']} is tracked by git; the E4 workbook is kept out of the "
                               "repository")
    if stat.S_IMODE(path.stat().st_mode) & 0o222:
        raise gates.GateClosed(f"{acquisition['file']} is not read-only")
    content = path.read_bytes()
    if gates.sha256_bytes(content) != acquisition["sha256"] or len(content) != acquisition["bytes"]:
        raise gates.GateClosed("The workbook's bytes differ from its acquisition record")
    return content


# ----------------------------------------------------------------------- structure mapping (text)

class _Placeholder:
    """A cell content that is not read: its kind is decided by type, and it prints as its description."""
    __slots__ = ("description",)

    def __init__(self, description):
        self.description = description

    def __str__(self):
        return self.description

    __repr__ = __str__


NUMBER_LABEL = _Placeholder("(number, not a date by its format)")
DATE_CELL = _Placeholder("(date)")


def _is_quarter(cell) -> bool:
    if cell is None or cell.kind != "text":
        return False
    try:
        parse_quarter(cell.text)
        return True
    except ValueError:
        return False


def _is_vintage(cell) -> bool:
    if cell is None:
        return False
    if cell.kind == "date":
        return True
    if cell.kind != "text":
        return False
    try:
        parse_release_month(cell.text)
        return True
    except ValueError:
        return False


def _body_value(cell):
    """The model value of a table cell, read by type only (R-X2.9): a numeric cell's value is never read."""
    if cell is None:
        return None
    if cell.kind == "number":
        return float("nan")
    if cell.kind == "text":
        return cell.text
    if cell.kind == "boolean":
        return cell.text not in ("0", "false", "FALSE")
    if cell.kind == "error":
        return ErrorValue(cell.text or "#ERROR")
    return DATE_CELL


def _label_value(cell, date1904, serials):
    """A vintage label (R-X2.8): text as given; a date by type or by the workbook's own number format as a
    date; any other number is not a date and does not parse."""
    if cell is None:
        return None
    if cell.kind == "text":
        return cell.text
    if cell.kind == "date":
        raw = serials.get((cell.row, cell.column)) or cell.text or ""
        try:
            return _dt.date.fromisoformat(raw[:10]) if re.match(r"\d{4}-\d{2}-\d{2}", raw) else serial_to_date(
                raw, date1904)
        except ValueError:
            return DATE_CELL
    if cell.kind == "number":
        return NUMBER_LABEL
    return _Placeholder(f"({cell.kind})")


def _quarter_label(cell):
    if cell is None:
        return None
    return cell.text if cell.kind == "text" else _Placeholder(f"({cell.kind})")


def find_blocks(by_row, sheet_name) -> list[dict]:
    """R-X2.7: candidate vintage-by-quarter tables on one sheet, from labels and cell types only.

    A label column holds at least two reference-quarter labels (runs split where a row of vintage labels
    intervenes); its header row is the nearest row above the first of them with a vintage label to the right
    of the label column. The table's columns run from the first to the last non-empty cell of the header row
    right of the label column; its rows from the first to the last reference-quarter label of the run.
    """
    quarters = defaultdict(list)
    for row, cells in by_row.items():
        for column, cell in cells.items():
            if _is_quarter(cell):
                quarters[column].append(row)
    blocks = []
    for column, rows in sorted(quarters.items()):
        rows.sort()
        runs, current = [], [rows[0]]
        for a, b in zip(rows, rows[1:]):
            if any(_is_vintage(cell) for r in range(a + 1, b) for c, cell in by_row.get(r, {}).items() if c > column):
                runs.append(current)
                current = [b]
            else:
                current.append(b)
        runs.append(current)
        for run in runs:
            if len(run) < 2:
                continue
            header = next((r for r in range(run[0] - 1, 0, -1)
                           if any(_is_vintage(cell) for c, cell in by_row.get(r, {}).items() if c > column)), None)
            blocks.append(dict(sheet=sheet_name, label_column=column, header_row=header, first_row=run[0],
                               last_row=run[-1]))
    return blocks


def _shape_block(block, by_row):
    """Columns and rows of one block, or Stop (step 4.1) where the layout leaves a cell unlabelled."""
    sheet, c, h = block["sheet"], block["label_column"], block["header_row"]
    header = {col: cell for col, cell in by_row.get(h, {}).items() if col > c}
    first, last = min(header), max(header)
    rows = range(block["first_row"], block["last_row"] + 1)
    content = defaultdict(set)
    for r in rows:
        for col in by_row.get(r, {}):
            if col > c:
                content[col].add(r)
    where = f"sheet {sheet!r}"
    stray = sorted(col for col in content if col < first or col > last)
    if stray:
        raise Stop("4.1", f"{where}: cells in the table's rows lie outside the columns of the vintage labels "
                   f"(columns {', '.join(column_letter(col) for col in stray[:10])})", dict(sheet=sheet))
    columns, separators = [], []
    for col in range(first, last + 1):
        if col in header:
            columns.append(col)
        elif content.get(col):
            raise Stop("4.1", f"{where}: column {column_letter(col)} has cells in the table's rows but no vintage "
                       "label", dict(sheet=sheet, column=column_letter(col)))
        else:
            separators.append(col)
    kept, separator_rows = [], []
    for r in rows:
        if by_row.get(r, {}).get(c) is not None:
            kept.append(r)
        elif any(col in columns for col in by_row.get(r, {})):
            raise Stop("4.1", f"{where}: row {r} has cells in the table but no reference-quarter label",
                       dict(sheet=sheet, row=r))
        else:
            separator_rows.append(r)
    gap = [r for r in range(h + 1, block["first_row"])]
    numbers_in_gap = [r for r in gap for col, cell in by_row.get(r, {}).items()
                      if col in columns and cell.kind not in ("text",)]
    if numbers_in_gap:
        raise Stop("4.1", f"{where}: rows between the vintage labels and the first reference quarter hold cells "
                   "that are not text", dict(sheet=sheet, rows=sorted(set(numbers_in_gap))))
    return dict(block, columns=columns, rows=kept, separator_columns=separators, separator_rows=separator_rows,
                gap_rows=gap)


def _document_texts(workbook) -> list[dict]:
    return [dict(where=f"document property {key}", text=value)
            for key, value in sorted(workbook.document_properties().items())]


def read_structure(workbook: Workbook) -> dict:
    """Everything the mapping prints, from text cells and cell types: sheets, titles and notes (numbers
    blanked), comments, the table geometry and its raw parts, or the step 4.1 stop found."""
    date1904 = workbook.date1904
    sheets, texts, parts, shaped, stop = [], _document_texts(workbook), [], [], None
    for sheet in workbook.sheets:
        by_row = defaultdict(dict)
        for cell in workbook.cells(sheet, dates=True):
            by_row[cell.row][cell.column] = cell
        blocks = find_blocks(by_row, sheet.name)
        headed = [b for b in blocks if b["header_row"] is not None]
        inside = set()
        sheet_shaped = []
        for block in headed:
            try:
                shape = _shape_block(block, by_row)
            except Stop as error:
                stop = stop or error
                continue
            sheet_shaped.append(shape)
            c = shape["label_column"]
            inside |= {(shape["header_row"], col) for col in shape["columns"]}
            inside |= {(r, col) for r in shape["rows"] for col in shape["columns"] + [c]}
        merged = [f"{column_letter(l)}{t}:{column_letter(r)}{b}" for t, l, b, r in workbook.merged_ranges(sheet)]
        sheet_texts = [dict(where=f"{sheet.name}!{column_letter(col)}{row}", text=cell.text)
                       for row in sorted(by_row) for col, cell in sorted(by_row[row].items())
                       if cell.kind == "text" and (row, col) not in inside]
        comments = [dict(where=f"{sheet.name}!{note.ref} ({note.kind})", text=note.text) for note in workbook.notes(sheet)]
        texts += [dict(where=f"sheet name {sheet.index + 1}", text=sheet.name)] + sheet_texts + comments
        sheets.append(dict(index=sheet.index, name=sheet.name, state=sheet.state, merged=merged,
                           blocks=len(headed), unheaded_label_runs=len(blocks) - len(headed),
                           texts=[dict(t, text=blank_numbers(t["text"])) for t in sheet_texts + comments]))
        if len(headed) > 1 and stop is None:
            stop = Stop("4.1", f"sheet {sheet.name!r} holds {len(headed)} vintage-by-quarter tables; one is required",
                        dict(sheet=sheet.name))
        shaped += sheet_shaped
        if stop is None:
            for shape in sheet_shaped:
                serials = {}
                if any(by_row[shape["header_row"]].get(col) is not None and by_row[shape["header_row"]][col].kind == "date"
                       for col in shape["columns"]):
                    serials = {(cell.row, cell.column): cell.text
                               for cell in workbook.cells(sheet, numbers=True, dates=True, rows={shape["header_row"]},
                                                          columns={col for col in shape["columns"]
                                                                   if by_row[shape["header_row"]].get(col) is not None
                                                                   and by_row[shape["header_row"]][col].kind == "date"})
                               if cell.kind == "date"}      # only date-typed header cells: a bare number is not read
                labels = tuple(_label_value(by_row[shape["header_row"]].get(col), date1904, serials)
                               for col in shape["columns"])
                quarter_labels = tuple(_quarter_label(by_row[r].get(shape["label_column"])) for r in shape["rows"])
                cells = tuple(tuple(_body_value(by_row[r].get(col)) for col in shape["columns"]) for r in shape["rows"])
                parts.append(RawPart(sheet.name, labels, quarter_labels, cells))
    if stop is None and not parts:
        stop = Stop("4.1", "there is no vintage-by-quarter table (no column of reference-quarter labels with a row "
                    "of vintage labels above it)")
    return dict(sheets=sheets, texts=texts, parts=parts, shaped=shaped, stop=stop,
                document_properties={k: blank_numbers(v) for k, v in workbook.document_properties().items()})


# --------------------------------------------------------------- title, cover and notes (release rule)

_EDITION_IN_TEXT = re.compile(r"quarter\s*([1-4])\s*\(\s*([a-z]+)\.?\s+to\s+([a-z]+)\.?\s*\)\s*(\d{4})\s*,?\s*"
                              r"(first estimate|second estimate|third estimate|quarterly national accounts|"
                              r"month\s*[1-3])", re.IGNORECASE)
_RELEASE_WORDS = re.compile(r"\b(releas(?:e|ed)|publish(?:ed)?|publication|issued)\b", re.IGNORECASE)
_NEXT_RELEASE = re.compile(r"\bnext\s+release\b", re.IGNORECASE)
_NUMERIC_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b|\b(\d{1,2})/(\d{1,2})/(\d{4})\b")


def _edition_key(match):
    quarter, first, last, year, kind = match.groups()
    months = tuple(_MONTH_NAMES.get(m.lower()[:4].rstrip("t") if m.lower().startswith("sept") else m.lower()[:3],
                                    _MONTH_NAMES.get(m.lower())) for m in (first, last))
    return int(quarter), months, int(year), " ".join(kind.lower().split())


def _dates_in(text):
    found = []
    for match in _DATE_TEXT.finditer(text):
        day = parse_day(match.group(0))
        if day:
            found.append((match.start(), day))
    for match in _NUMERIC_DATE.finditer(text):
        try:
            day = (_dt.date(int(match.group(1)), int(match.group(2)), int(match.group(3))) if match.group(1)
                   else _dt.date(int(match.group(6)), int(match.group(5)), int(match.group(4))))
        except ValueError:
            continue
        found.append((match.start(), day))
    return found


def check_title_and_notes(texts, edition: dict) -> list[dict]:
    """R-X2.10: the texts that name another edition or release date than the selected edition's (empty when
    none). An edition is named by the pattern of the dataset's edition labels ('Quarter 2 (Apr to June) 2026,
    first estimate'); a release date by a full date in a text that speaks of a release or publication. A date
    introduced by 'next release' is another release's date and conflicts only if it is not later."""
    selected_key = None
    match = _EDITION_IN_TEXT.search(edition["label"])
    if match:
        selected_key = _edition_key(match)
    release = _dt.date.fromisoformat(edition["release_date"])
    conflicts = []
    for item in texts:
        text = " ".join(str(item["text"]).split())
        for found in _EDITION_IN_TEXT.finditer(text):
            if _edition_key(found) != selected_key:
                conflicts.append(dict(where=item["where"], kind="another edition", text=blank_numbers(text)))
        if _RELEASE_WORDS.search(text):
            nexts = [m.end() for m in _NEXT_RELEASE.finditer(text)]
            for position, day in _dates_in(text):
                is_next = any(0 <= position - end <= 20 for end in nexts)
                if (is_next and day <= release) or (not is_next and day != release):
                    conflicts.append(dict(where=item["where"], kind="another release date", date=day.isoformat(),
                                          text=blank_numbers(text)))
    return conflicts


# ------------------------------------------------------------------------------ mapping stage

def _attempt_number(root) -> int:
    path = Path(root) / ATTEMPTS_LOG
    return 1 + (sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
                if path.is_file() else 0)


def _last_attempt(root):
    path = Path(root) / ATTEMPTS_LOG
    if not path.is_file():
        return None
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return json.loads(lines[-1]) if lines else None


def format_mapping(result: dict) -> str:
    """The printed mapping: sheet names, titles and notes with numbers blanked, labels, availability counts,
    marker and other contents with digits as '#'. No level is printed (no level is read)."""
    lines = ["E4 structure mapping at X.2 (prereg/E4.md section 4, steps 1 to 5): headers and availability only; "
             "no level is read or printed.",
             f"Workbook: {result['file']} (SHA-256 {result['raw_sha256']})",
             f"Edition: {result['edition']['label']}, released {result['edition']['release_date']}"
             + (f" {result['edition']['release_time_uk']} UK time" if result['edition'].get('release_time_uk') else ""),
             f"Attempt: {result['attempt']}", "", f"Sheets ({len(result['sheets'])}):"]
    for sheet in result["sheets"]:
        lines.append(f"  {sheet['index'] + 1}. {sheet['name']!r} [{sheet['state']}]"
                     + (f" merged: {', '.join(sheet['merged'])}" if sheet["merged"] else ""))
    lines += ["", "Document properties (numbers blanked):"]
    lines += [f"  {k}: {v}" for k, v in sorted(result["document_properties"].items())] or ["  none"]
    lines += ["", "Titles, cover and notes: text cells outside the table and cell comments (numbers blanked):"]
    for sheet in result["sheets"]:
        lines += [f"  {t['where']}: {t['text']}" for t in sheet["texts"]]
    table = result.get("table")
    if table:
        for part in table["parts"]:
            lines += ["", f"Table part on sheet {part['sheet']!r}: label column {part['label_column']}, header row "
                          f"{part['header_row']}, rows {part['rows'][0]}-{part['rows'][-1]} "
                          f"({len(part['rows'])} labelled), vintage columns {part['columns'][0]}-{part['columns'][-1]} "
                          f"({len(part['columns'])})"
                          + (f", separator columns {', '.join(part['separator_columns'])}" if part["separator_columns"] else "")
                          + (f", separator rows {', '.join(map(str, part['separator_rows']))}" if part["separator_rows"] else ""),
                      "Vintage labels: " + " | ".join(part["vintage_labels"]),
                      "Reference-quarter labels: " + " | ".join(part["quarter_labels"])]
    report = result.get("availability")
    if report:
        lines += ["", "Availability per vintage (cells of each kind; no level):",
                  "  vintage | release month | " + " | ".join(KINDS)]
        lines += [f"  {row['vintage']} | {row['release_month']} | " + " | ".join(str(row[k]) for k in KINDS)
                  for row in report["per_vintage"]]
        lines.append("  total: " + ", ".join(f"{k} {v}" for k, v in report["kinds_total"].items()))
        lines += ["Marker cells (content, digits as #):"]
        lines += [f"  {m['vintage']} / {m['quarter']}: {m['content']!r}" for m in report["marker_cells"]] or ["  none"]
        manifest = result["manifest"]
        lines += ["", f"Earliest vintage: {manifest['earliest_vintage']}; latest vintage: {manifest['latest_vintage']}; "
                      f"earliest reference quarter: {manifest['earliest_reference_quarter']}"]
    if result.get("conflicts"):
        lines += ["", "Title, cover or notes naming another edition or release date:"]
        lines += [f"  {c['where']}: {c['kind']}: {c['text']}" for c in result["conflicts"]]
    lines += ["", f"Outcome: {result['status']}"]
    if result["status"] == "stopped":
        lines.append(f"STOP ({result['stop']['kind']}), step {result['stop']['step']}: {result['stop']['reason']}")
        lines.append("Stop and amend (prereg/E4.md section 13): the amendment is registered before any level is read, "
                     "then the mapping is run again. " + result["stop"]["consequence"])
    return "\n".join(lines) + "\n"


def _mask(value):
    """A label as printed: a date as ISO text, a placeholder as its description, a text with numbers blanked as
    in Annex C (labels such as 'Jan 2016' or '1955 Q1' are unchanged); None when there is no label."""
    if value is None:
        return None
    if isinstance(value, _dt.date):
        return value.isoformat()
    return blank_numbers(value)


def map_structure(root, *, amendment=None) -> dict:
    """Section 4, structure mapping steps 1 to 5 on the acquired workbook; every attempt recorded."""
    root = Path(root)
    gate = _registration_gate(root)
    acquisition = load_acquisition(root)
    gates.check_committed(root, ACQUISITION_RECORD)
    if (root / MAPPING_JSON).exists():
        raise records.RecordExists(f"{MAPPING_JSON} already exists; the mapping has been completed")
    last = _last_attempt(root)
    cited = None
    if last is not None and last.get("status") == "stopped":
        if amendment is None:
            raise gates.GateClosed("The previous mapping attempt stopped: name the committed amendment record that "
                                   "settles it (section 13) before the mapping is run again")
    if amendment is not None:
        gates.check_committed(root, amendment)
        cited = dict(record=amendment, sha256=gates.sha256_file(root / amendment))
    content = _raw(root, acquisition)
    if gates.sha256_file(root / EDITION_RECORD) != acquisition["edition_record_sha256"]:
        raise gates.GateClosed(f"{EDITION_RECORD} differs from the edition record the acquisition cites")
    edition = load_edition(root)["selected"]
    attempt = _attempt_number(root)
    result = dict(record_type="E4 structure mapping at X.2 (prereg/E4.md section 4, steps 1 to 5)", attempt=attempt,
                  file=acquisition["file"], raw_sha256=acquisition["sha256"], edition=edition, amendment=cited,
                  registration_id=gate.get("registration_id"), mapped_utc=gates.now_utc(), sheets=[],
                  document_properties={}, readings="docs/E4_X2_READINGS.md")
    try:
        structure = read_structure(Workbook(content))
        result.update(sheets=structure["sheets"], document_properties=structure["document_properties"])
        conflicts = check_title_and_notes(structure["texts"], edition)
        result["conflicts"] = conflicts
        if conflicts:
            raise SourceStop("release rule", f"{len(conflicts)} text(s) of the title, cover or notes name another "
                             "edition or release date than the selected edition's")
        if structure["stop"] is not None:
            raise structure["stop"]
        parts = []
        for shape, part in zip(structure["shaped"], structure["parts"]):
            parts.append(dict(sheet=shape["sheet"], label_column=column_letter(shape["label_column"]),
                              header_row=shape["header_row"], rows=shape["rows"],
                              columns=[column_letter(c) for c in shape["columns"]],
                              separator_columns=[column_letter(c) for c in shape["separator_columns"]],
                              separator_rows=shape["separator_rows"],
                              vintage_labels=[_mask(l)
                                              for l in part.vintage_labels],
                              quarter_labels=[_mask(q) for q in part.quarter_labels]))
        result["table"] = dict(parts=parts)
        tables = build_tables(structure["parts"])
        report = availability_report(tables.availability)
        result.update(availability=report, manifest={k: (list(v) if isinstance(v, tuple) else v)
                                                   for k, v in tables.manifest.items()},
                      kinds_sha256=gates.sha256_bytes(np.ascontiguousarray(tables.availability.kinds).tobytes()),
                      status="mapped", stop=None)
    except Stop as stop:
        kind = "release rule" if isinstance(stop, SourceStop) else "structure mapping"
        result.update(status="stopped", stop=dict(
            kind=kind, step=stop.step, reason=stop.reason,
            detail=None if isinstance(stop.detail, dict) and "editions" in stop.detail else stop.detail,
            consequence=("After a stop under section 4 the amendment states which file is used." if kind == "release rule"
                         else "The workbook already acquired is kept and used.")))
    except (WorkbookError, ValueError) as error:
        result.update(status="stopped", stop=dict(kind="structure mapping", step="4.1",
                                                  reason=f"the workbook could not be read: {error}", detail=None,
                                                  consequence="The workbook already acquired is kept and used."))
    text = format_mapping(result)
    records.write_once(root / f"{SOURCE_DIR}/structure-attempt-{attempt}.json", _pretty(result))
    records.write_once(root / f"{SOURCE_DIR}/structure-attempt-{attempt}.txt", text.encode("utf-8"))
    with (root / ATTEMPTS_LOG).open("a", encoding="utf-8", newline="\n") as output:
        output.write(json.dumps(dict(attempt=attempt, time_utc=result["mapped_utc"], status=result["status"],
                                     step=(result["stop"] or {}).get("step"), reason=(result["stop"] or {}).get("reason"),
                                     raw_sha256=acquisition["sha256"], amendment=cited), sort_keys=True) + "\n")
    if result["status"] == "mapped":
        records.write_once(root / MAPPING_JSON, _pretty(result))
        records.write_once(root / MAPPING_TEXT, text.encode("utf-8"))
        m = result["manifest"]
        row = records.manifest_row(root, acquisition["file"])
        records.replace_manifest_row(root, acquisition["file"], acquisition["sha256"], notes=(
            row["notes"].replace("E4 X.2 structure mapping pending", "E4 X.2 structure mapping done")
            + f"; coverage: earliest vintage {m['earliest_vintage']}, latest vintage {m['latest_vintage']}, earliest "
              f"reference quarter {m['earliest_reference_quarter']} ({MAPPING_JSON})"))
    return dict(result=result, text=text)


# ------------------------------------------------------------------------- level tables (X.4)

def read_level_tables(root) -> dict:
    """The level table for the registered run (X.4), built from the committed mapping; gated.

    Needs G4, the X.3 record (committed, passed), the frozen code, and the committed edition, acquisition
    and mapping records. The re-read availability must equal the recorded one. Returns the uc_e4 Tables
    and a summary of counts and hashes; nothing here prints a level.
    """
    root = Path(root)
    _registration_gate(root)
    x3 = gates.check_x3(root, "e4")
    gates.check_code_frozen(root, x3, "e4")
    for relative in (EDITION_RECORD, ACQUISITION_RECORD, MAPPING_JSON):
        if not (root / relative).is_file():
            raise gates.GateClosed(f"{relative} is missing: E4 X.2 is not complete")
        gates.check_committed(root, relative)
    acquisition = load_acquisition(root)
    mapping = records.read_json(root / MAPPING_JSON)
    if mapping.get("status") != "mapped" or mapping.get("raw_sha256") != acquisition["sha256"]:
        raise gates.GateClosed(f"{MAPPING_JSON} does not record a completed mapping of the acquired workbook")
    workbook = Workbook(_raw(root, acquisition))
    date1904 = workbook.date1904
    parts = []
    from .workbook import column_index
    for part in mapping["table"]["parts"]:
        sheet = workbook.sheet(part["sheet"])
        label_column, header_row = column_index(part["label_column"]), part["header_row"]
        columns = [column_index(c) for c in part["columns"]]
        rows = list(part["rows"])
        grid = {(cell.row, cell.column): cell for cell in workbook.cells(
            sheet, numbers=True, dates=True, rows=set(rows) | {header_row}, columns=set(columns) | {label_column})}
        serials = {key: cell.text for key, cell in grid.items() if key[0] == header_row and cell.kind == "date"}
        labels = tuple(_label_value(grid.get((header_row, c)), date1904, serials) for c in columns)
        quarter_labels = tuple(_quarter_label(grid.get((r, label_column))) for r in rows)
        cells = []
        for r in rows:
            row = []
            for c in columns:
                cell = grid.get((r, c))
                row.append(float(cell.text) if cell is not None and cell.kind == "number" else _body_value(cell))
            cells.append(tuple(row))
        parts.append(RawPart(part["sheet"], labels, quarter_labels, tuple(cells)))
    tables = build_tables(parts)
    kinds = gates.sha256_bytes(np.ascontiguousarray(tables.availability.kinds).tobytes())
    if kinds != mapping["kinds_sha256"]:
        raise gates.GateClosed("The availability of the re-read table differs from the recorded mapping")
    levels = tables.levels.levels
    summary = dict(n_vintages=int(levels.shape[1]), n_reference_quarters=int(levels.shape[0]),
                   numeric_cells=int(np.isfinite(levels).sum()), kinds_sha256=kinds,
                   levels_sha256=gates.sha256_bytes(np.ascontiguousarray(levels, dtype="<f8").tobytes()),
                   mapping_sha256=gates.sha256_file(root / MAPPING_JSON), x3_record_sha256=x3["record_sha256"])
    return dict(tables=tables, summary=summary)
