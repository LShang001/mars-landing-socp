#!/usr/bin/env python3
"""Validate the traceability and coverage of the literature matrix."""
from __future__ import annotations

import csv
import re
import sys
import json
import urllib.parse
import urllib.request
import urllib.error
import unicodedata
import ipaddress
import socket
import ssl
import http.client
from difflib import SequenceMatcher
from pathlib import Path

FIELDS = ("source_id", "year", "venue", "doi", "url", "theme", "method",
          "problem", "hardware", "evidence", "relevance", "gap", "verification")
THEMES = {
    "lossless convexification", "sequential convex programming",
    "conic warm start and factorization reuse", "embedded real-time optimization",
    "robust and chance-constrained powered descent",
    "closed-loop and hardware-in-the-loop",
}
DIRECT_CORE = {
 "lossless convexification": {"acikmese2007lossless", "acikmese2013", "blackmore2012lossless", "blackmore2010minimum", "carson2013gfold"},
 "sequential convex programming": {"mao2018successive", "mao2018continuous", "szmuk2020successive"},
 "conic warm start and factorization reuse": {"domahidi2013ecos", "stellato2020osqp", "ferreau2014qpoases", "ouyang2015scs"},
 "embedded real-time optimization": {"domahidi2013ecos", "domahidi2013theory", "mattingley2012cvxgen", "verschueren2022acados", "frison2020hpipm"},
 "robust and chance-constrained powered descent": {"su2026distributionally", "su2023stochastic", "ridderhof2018covariance"},
 "closed-loop and hardware-in-the-loop": {"acikmese2013morpheus", "dwyer2014morpheus", "olansen2014morpheus", "scharf2014adapt"},
}
DOI_RE = re.compile(r"^10\.\d{4,9}/\S+$", re.I)
STABLE_HOSTS = ("doi.org", "api.crossref.org", "ntrs.nasa.gov", "jmlr.org",
                "web.stanford.edu", "people.engr.tamu.edu")

def normalize_doi(value):
    value = value.strip()
    value = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", value, flags=re.I)
    if value and not DOI_RE.fullmatch(value):
        raise ValueError("invalid DOI")
    return value.lower()

def _plain(value):
    value = value.replace("ı", "i").replace("İ", "I")
    value = re.sub(r"\{\\[a-zA-Z]+\{([^{}]+)\}\}", r"\1", value)
    value = re.sub(r"[{}\\]", "", value)
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", value)

def identity_fingerprint(title, first_author, year):
    return f"{_plain(title)}|{_plain(first_author)}|{year.strip()}"

def validate_url(value, resolve=True):
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
        raise ValueError("URL must be HTTPS without credentials or nonstandard port")
    host = (parsed.hostname or "").rstrip(".").lower()
    if host not in STABLE_HOSTS:
        raise ValueError("URL host is not approved")
    try:
        literal = ipaddress.ip_address(host)
        addresses = [literal]
    except ValueError:
        addresses = []
        if resolve:
            for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
                addresses.append(ipaddress.ip_address(item[4][0]))
    if any(not address.is_global for address in addresses):
        raise ValueError("URL resolves to non-global address")
    return value

class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, pinned_ip, proxy=None, **kwargs):
        self._pinned_ip = pinned_ip
        self._proxy = proxy
        super().__init__(host, **kwargs)

    def connect(self):
        if self._proxy:
            self.set_tunnel(self._pinned_ip, self.port)
        target = self._proxy or (self._pinned_ip, self.port)
        self.sock = socket.create_connection(target, self.timeout, self.source_address)
        if self._proxy:
            self._tunnel()
        self.sock = self._context.wrap_socket(self.sock, server_hostname=self.host)

class _PinnedHTTPSHandler(urllib.request.HTTPSHandler):
    def __init__(self, pinned_ip):
        super().__init__(context=ssl.create_default_context())
        self._pinned_ip = pinned_ip

    def https_open(self, request):
        proxy = urllib.parse.urlsplit(
            __import__("os").environ.get("HTTPS_PROXY", ""))
        proxy_target = (proxy.hostname, proxy.port) if proxy.hostname and proxy.port else None
        def factory(host, **kwargs):
            return _PinnedHTTPSConnection(
                host, pinned_ip=self._pinned_ip, proxy=proxy_target, **kwargs)
        return self.do_open(factory, request, context=self._context)

def _resolve_global(host):
    addresses = []
    for item in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM):
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise ValueError("URL resolves to non-global address")
        if str(address) not in addresses:
            addresses.append(str(address))
    if not addresses:
        raise ValueError("URL has no global address")
    return sorted(addresses, key=lambda value: ipaddress.ip_address(value).version)

_PIN_CACHE = {}
_PIN_PREFERRED = {}

def parse_bibtex(text: str):
    """Parse the braced fields used by this repository's BibTeX file."""
    entries = {}
    for match in re.finditer(r"@([A-Za-z]+)\s*\{\s*([^,]+),", text):
        key = match.group(2).strip()
        pos, depth = match.end(), 1
        while pos < len(text) and depth:
            if text[pos] == "{": depth += 1
            elif text[pos] == "}": depth -= 1
            pos += 1
        body = text[match.end():pos - 1]
        fields = {"entry_type": match.group(1).lower()}
        for field in re.finditer(r"(?i)(?:^|,)\s*([A-Za-z]+)\s*=\s*\{", body):
            start, i, level = field.end(), field.end(), 1
            while i < len(body) and level:
                if body[i] == "{": level += 1
                elif body[i] == "}": level -= 1
                i += 1
            fields[field.group(1).lower()] = re.sub(r"\s+", " ", body[start:i - 1]).strip()
        entries[key] = fields
    return entries


def load_and_validate(matrix: Path, bibliography: Path):
    errors = []
    if not matrix.exists():
        return [], [f"missing matrix: {matrix}"]
    with matrix.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if tuple(reader.fieldnames or ()) != FIELDS:
            errors.append(f"columns must be exactly: {','.join(FIELDS)}")
        rows = list(reader)
        if any(None in row for row in rows):
            errors.append("malformed CSV: unexpected extra columns")
    bib = bibliography.read_text(encoding="utf-8") if bibliography.exists() else ""
    bib_entries = parse_bibtex(bib)
    bib_keys = re.findall(r"@[A-Za-z]+\s*\{\s*([^,]+),", bib)
    for key in set(bib_keys):
        if bib_keys.count(key) > 1:
            errors.append(f"duplicate bibliography key: {key}")
    bib_dois = {}
    bib_fingerprints = {}
    for key, fields in bib_entries.items():
        try:
            normalized = normalize_doi(fields.get("doi", ""))
        except ValueError:
            errors.append(f"invalid bibliography DOI: {key}")
            normalized = ""
        if normalized:
            if normalized in bib_dois:
                errors.append(f"duplicate bibliography DOI {normalized}: {bib_dois[normalized]}, {key}")
            bib_dois[normalized] = key
        elif fields.get("title") and fields.get("author") and fields.get("year"):
            first = re.split(r"\s+and\s+", fields["author"])[0]
            fingerprint = identity_fingerprint(fields["title"], first, fields["year"])
            if fingerprint in bib_fingerprints:
                errors.append(f"duplicate bibliography work: {bib_fingerprints[fingerprint]}, {key}")
            bib_fingerprints[fingerprint] = key
    if re.search(r"Verified literature matrix source|placeholder|TBD", bib, re.I):
        errors.append("bibliography contains placeholder metadata")
    seen = set()
    seen_dois = set()
    seen_fingerprints = {}
    for line, row in enumerate(rows, 2):
        sid = (row.get("source_id") or "").strip()
        if not sid or sid in seen:
            errors.append(f"line {line}: missing or duplicate source_id {sid!r}")
        seen.add(sid)
        for field in FIELDS:
            if field not in ("doi", "url", "hardware") and not (row.get(field) or "").strip():
                errors.append(f"line {line}: empty {field}")
        try:
            year = int(row.get("year") or "")
            if not 1950 <= year <= 2100:
                raise ValueError
        except (ValueError, TypeError):
            errors.append(f"line {line}: invalid year")
        doi, url = (row.get("doi") or "").strip(), (row.get("url") or "").strip()
        try:
            doi = normalize_doi(doi)
        except ValueError:
            errors.append(f"line {line}: invalid DOI")
            doi = ""
        if not ((doi and DOI_RE.match(doi)) or url.startswith("https://")):
            errors.append(f"line {line}: DOI or stable HTTPS URL required")
        if url:
            try: validate_url(url, resolve=False)
            except ValueError as exc: errors.append(f"line {line}: invalid URL: {exc}")
        normalized_doi = doi.lower()
        if normalized_doi and normalized_doi in seen_dois:
            errors.append(f"line {line}: duplicate DOI {doi}")
        seen_dois.add(normalized_doi)
        if row.get("theme") not in THEMES:
            errors.append(f"line {line}: uncontrolled theme {row.get('theme')!r}")
        verification = row.get("verification", "")
        if not verification.startswith(("metadata_verified:", "full_text_verified:")):
            errors.append(f"line {line}: verification level required")
        if verification.startswith("metadata_verified:") and re.search(
            r"\b(proves?|demonstrates?|outperforms?|superior|experiment(?:ally)? verifies?)\b",
            row.get("evidence", ""), re.I
        ):
            errors.append(f"line {line}: metadata-only strong claim")
        if sid and not re.search(r"@[A-Za-z]+\s*\{\s*" + re.escape(sid) + r"\s*,", bib):
            errors.append(f"line {line}: {sid} missing from bibliography")
        elif sid:
            entry = re.search(r"@[A-Za-z]+\s*\{\s*" + re.escape(sid) + r"\s*,(.*?)(?=\n@|\Z)", bib, re.S)
            if entry and not re.search(r"\bauthor\s*=", entry.group(1), re.I):
                errors.append(f"line {line}: {sid} bibliography entry missing author")
            fields = bib_entries.get(sid, {})
            try: bib_doi = normalize_doi(fields.get("doi", ""))
            except ValueError: bib_doi = ""
            if doi and bib_doi != doi.lower():
                errors.append(f"line {line}: DOI mismatch for {sid}: CSV={doi}, BibTeX={bib_doi}")
            if fields.get("year") and fields["year"] != row.get("year"):
                errors.append(f"line {line}: year mismatch for {sid}")
            if not doi and all(fields.get(name) for name in ("title", "author", "year")):
                first = re.split(r"\s+and\s+", fields["author"])[0]
                fingerprint = identity_fingerprint(fields["title"], first, fields["year"])
                if fingerprint in seen_fingerprints:
                    errors.append(f"line {line}: duplicate identity fingerprint: {seen_fingerprints[fingerprint]}, {sid}")
                seen_fingerprints[fingerprint] = sid
    for theme in THEMES:
        if sum(r.get("theme") == theme for r in rows) < 3:
            errors.append(f"theme has fewer than 3 sources: {theme}")
        present = {r["source_id"] for r in rows if r.get("theme") == theme}
        if len(present & DIRECT_CORE[theme]) < 3:
            errors.append(f"theme has fewer than 3 direct core sources: {theme}")
    if len(rows) < 40:
        errors.append(f"matrix has {len(rows)} rows; need at least 40")
    return rows, errors

def verify_online(rows, bibliography: Path):
    errors = []
    entries = parse_bibtex(bibliography.read_text(encoding="utf-8"))
    for row in rows:
        if not row["doi"]:
            try:
                safe_fetch(row["url"], ("text/html", "application/pdf"))
            except Exception as exc:
                errors.append(f"{row['source_id']}: institutional URL unavailable: {exc}")
            continue
        endpoint = "https://api.crossref.org/works/" + urllib.parse.quote(row["doi"], safe="")
        try:
            payload = json.loads(safe_fetch(endpoint, ("application/json",)))
            if payload.get("status") != "ok" or not isinstance(payload.get("message"), dict):
                raise ValueError("invalid Crossref schema")
            work = payload["message"]
            if not (isinstance(work.get("DOI"), str)
                    and isinstance(work.get("title"), list) and work["title"]
                    and isinstance(work.get("author"), list)
                    and isinstance(work.get("container-title"), list)
                    and isinstance(work.get("issued"), dict)):
                raise ValueError("invalid Crossref work schema")
            if normalize_doi(work["DOI"]) != normalize_doi(row["doi"]):
                raise ValueError("Crossref DOI identity mismatch")
        except Exception as exc:
            errors.append(f"{row['source_id']}: Crossref request failed: {exc}")
            continue
        fields = entries[row["source_id"]]
        normalize = lambda value: re.sub(
            r"[^a-z0-9]+", "",
            unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().lower())
        if normalize(work.get("title", [""])[0]) != normalize(fields.get("title", "")):
            errors.append(f"{row['source_id']}: Crossref title mismatch")
        authors = work.get("author") or []
        if authors:
            def signature(name):
                name = re.sub(r"\{\\[a-zA-Z]+\{([^{}]+)\}\}", r"\1", name)
                name = re.sub(r"\{\\[a-zA-Z]+\}", "", name)
                name = name.replace("{", "").replace("}", "").replace("\\", "")
                tokens = re.findall(r"[a-z0-9]+", unicodedata.normalize(
                    "NFKD", name).encode("ascii", "ignore").decode().lower())
                return "".join(tokens)
            crossref_authors = [signature(a.get("family", "")) for a in authors]
            bib_authors = []
            for author in re.split(r"\s+and\s+", fields.get("author", "")):
                family = author.split(",", 1)[0] if "," in author else author.rsplit(None, 1)[-1]
                bib_authors.append(signature(family))
            if len(crossref_authors) != len(bib_authors) or any(
                SequenceMatcher(None, expected, actual).ratio() < .7
                for expected, actual in zip(crossref_authors, bib_authors)
            ):
                errors.append(f"{row['source_id']}: Crossref author mismatch")
        container = (work.get("container-title") or [""])[0]
        bib_venue = fields.get("journal") or fields.get("booktitle") or fields.get("publisher", "")
        if container and bib_venue and SequenceMatcher(
            None, normalize(container), normalize(bib_venue)).ratio() < .65:
            errors.append(f"{row['source_id']}: Crossref venue mismatch")
        crossref_years = {str(value["date-parts"][0][0]) for key in
                          ("published", "published-print", "published-online", "issued")
                          if (value := work.get(key)) and value.get("date-parts")}
        if row["year"] not in crossref_years:
            errors.append(f"{row['source_id']}: Crossref year mismatch")
    return errors

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None

def safe_fetch(url, content_types, retries=2, max_bytes=1024 * 1024):
    current = url
    for redirect in range(6):
        validate_url(current, resolve=False)
        host = urllib.parse.urlsplit(current).hostname
        if host not in _PIN_CACHE:
            _PIN_CACHE[host] = _resolve_global(host)
        pinned_ips = _PIN_CACHE[host]
        preferred = _PIN_PREFERRED.get(host)
        if preferred in pinned_ips:
            pinned_ips = [preferred] + [ip for ip in pinned_ips if ip != preferred]
        request = urllib.request.Request(current, headers={"User-Agent": "mars-literature-audit/1.0"})
        last = None
        attempts = max(retries + 1, len(pinned_ips))
        for attempt in range(attempts):
            opener = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), _NoRedirect,
                _PinnedHTTPSHandler(pinned_ips[attempt % len(pinned_ips)]))
            try:
                response = opener.open(request, timeout=2)
                break
            except urllib.error.HTTPError as exc:
                if exc.code in (301, 302, 303, 307, 308):
                    location = exc.headers.get("Location")
                    if not location: raise ValueError("redirect without Location")
                    current = urllib.parse.urljoin(current, location)
                    response = None
                    break
                last = exc
                if exc.code < 500 and exc.code != 429: raise
            except (urllib.error.URLError, TimeoutError) as exc:
                last = exc
        else:
            raise RuntimeError(f"network unavailable after retries: {last}")
        if response is None:
            continue
        content_type = response.headers.get_content_type()
        if content_type not in content_types:
            response.close(); raise ValueError(f"unexpected content type {content_type}")
        data = response.read(max_bytes + 1); response.close()
        if len(data) > max_bytes: raise ValueError("response too large")
        _PIN_PREFERRED[host] = pinned_ips[attempt % len(pinned_ips)]
        return data.decode("utf-8", "replace")
    raise ValueError("too many redirects")


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    rows, errors = load_and_validate(Path(__file__).with_name("literature_matrix.csv"), root / "paper/refs.bib")
    if "--verify-online" in sys.argv and not errors:
        errors.extend(verify_online(rows, root / "paper/refs.bib"))
    if errors:
        print("FAIL")
        print("\n".join(errors))
        return 1
    print(f"PASS: {len(rows)} verified sources; {len(THEMES)} themes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
