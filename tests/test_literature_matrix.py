from pathlib import Path
import unittest
import tempfile

from research.literature.check_literature import load_and_validate
from research.literature.check_literature import parse_bibtex
from research.literature.check_literature import normalize_doi, validate_url, identity_fingerprint, safe_fetch
from research.literature.check_literature import _PinnedHTTPSConnection
from unittest import mock
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "research/literature/literature_matrix.csv"
BIB = ROOT / "paper/refs.bib"


class LiteratureMatrixTest(unittest.TestCase):
    def test_doi_prefix_is_normalized_and_evil_doi_rejected(self):
        self.assertEqual(normalize_doi("https://doi.org/10.2514/1.27553"), "10.2514/1.27553")
        with self.assertRaises(ValueError):
            normalize_doi("10.2514/evil doi")

    def test_url_security_policy(self):
        for url in ("http://doi.org/x", "https://user@doi.org/x",
                    "https://doi.org:444/x", "https://evil-doi.org/x",
                    "https://127.0.0.1/x", "https://169.254.1.1/x"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_url(url)

    def test_identity_fingerprint_normalizes_latex_unicode_and_punctuation(self):
        a = identity_fingerprint(r"{Açıkmeşe}: Guidance!", r"Beh{\c{c}}et Açıkmeşe", "2013")
        b = identity_fingerprint("Acikmese Guidance", "Behcet Acikmese", "2013")
        self.assertEqual(a, b)

    def test_redirect_to_private_address_is_rejected(self):
        headers = {"Location": "https://127.0.0.1/secret"}
        redirect = urllib.error.HTTPError("https://doi.org/x", 302, "Found", headers, None)
        opener = mock.Mock()
        opener.open.side_effect = redirect
        with mock.patch("urllib.request.build_opener", return_value=opener):
            with self.assertRaisesRegex(ValueError, "approved|non-global"):
                safe_fetch("https://doi.org/x", ("text/html",))

    def test_pinned_https_connection_never_resolves_hostname_again(self):
        raw_socket = mock.Mock()
        tls_socket = mock.Mock()
        context = mock.Mock()
        context.wrap_socket.return_value = tls_socket
        connection = _PinnedHTTPSConnection(
            "doi.org", pinned_ip="93.184.216.34", context=context, timeout=3)
        with mock.patch("socket.create_connection", return_value=raw_socket) as create:
            with mock.patch("socket.getaddrinfo", side_effect=AssertionError("second DNS lookup")):
                connection.connect()
        create.assert_called_once_with(("93.184.216.34", 443), 3, None)
        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="doi.org")
        self.assertIs(connection.sock, tls_socket)

    def test_duplicate_bibliography_key_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bib = Path(directory) / "refs.bib"
            bib.write_text(BIB.read_text(encoding="utf-8") +
                           "\n@misc{acikmese2007lossless, author={X}, title={Y}, year={2020}}")
            _, errors = load_and_validate(MATRIX, bib)
            self.assertTrue(any("duplicate bibliography key" in error for error in errors))

    def test_malformed_csv_extra_column_is_rejected(self):
        import csv
        with tempfile.TemporaryDirectory() as directory:
            matrix = Path(directory) / "matrix.csv"
            text = MATRIX.read_text(encoding="utf-8")
            lines = text.splitlines()
            lines[1] += ",unexpected"
            matrix.write_text("\n".join(lines), encoding="utf-8")
            _, errors = load_and_validate(matrix, BIB)
            self.assertTrue(any("malformed CSV" in error for error in errors))
    def test_bibtex_parser_extracts_structured_metadata(self):
        parsed = parse_bibtex("@article{x, author={Doe, Jane}, title={Real Title}, year={2020}, doi={10.1/x}}")
        self.assertEqual(parsed["x"]["title"], "Real Title")
        self.assertEqual(parsed["x"]["author"], "Doe, Jane")

    def test_csv_bib_doi_mismatch_is_rejected(self):
        import csv
        with tempfile.TemporaryDirectory() as directory:
            matrix = Path(directory) / "matrix.csv"
            with MATRIX.open(encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            rows[0]["doi"] = "10.9999/wrong"
            with matrix.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader(); writer.writerows(rows)
            _, errors = load_and_validate(matrix, BIB)
            self.assertTrue(any("DOI mismatch" in error for error in errors))

    def test_duplicate_work_under_different_keys_is_rejected(self):
        import csv
        with tempfile.TemporaryDirectory() as directory:
            matrix = Path(directory) / "matrix.csv"
            with MATRIX.open(encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            rows[1]["doi"] = rows[0]["doi"]
            with matrix.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader(); writer.writerows(rows)
            _, errors = load_and_validate(matrix, BIB)
            self.assertTrue(any("duplicate DOI" in error for error in errors))

    def test_duplicate_doi_only_in_bibliography_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bib = Path(directory) / "refs.bib"
            bib.write_text(BIB.read_text(encoding="utf-8") +
                           "\n@article{duplicate_only, author={X, Y}, title={Other}, year={2020}, doi={10.2514/1.27553}}\n")
            _, errors = load_and_validate(MATRIX, bib)
            self.assertTrue(any("duplicate bibliography DOI" in error for error in errors))

    def test_conference_sources_are_inproceedings(self):
        entries = parse_bibtex(BIB.read_text(encoding="utf-8"))
        for key in ("mao2018successive", "mao2018continuous", "chen2021mars2020"):
            with self.subTest(key=key):
                self.assertEqual(entries[key]["entry_type"], "inproceedings")
                self.assertIn("booktitle", entries[key])
    def test_placeholder_bibliography_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            bib = Path(directory) / "refs.bib"
            bib.write_text("@misc{lit01, title={Verified literature matrix source 01}, year={2020}}")
            _, errors = load_and_validate(MATRIX, bib)
            self.assertTrue(any("placeholder" in error for error in errors))

    def test_metadata_only_source_cannot_make_strong_evidence_claim(self):
        import csv
        with tempfile.TemporaryDirectory() as directory:
            matrix = Path(directory) / "matrix.csv"
            with MATRIX.open(encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            rows[0]["verification"] = "metadata_verified: Crossref"
            rows[0]["evidence"] = "Proves global superiority over all methods."
            with matrix.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
                writer.writeheader(); writer.writerows(rows)
            _, errors = load_and_validate(matrix, BIB)
            self.assertTrue(any("metadata-only strong claim" in error for error in errors))

    def test_literature_matrix_is_complete_and_traceable(self):
        rows, errors = load_and_validate(MATRIX, BIB)
        self.assertFalse(errors, "\n".join(errors))
        self.assertGreaterEqual(len(rows), 40)

    def test_required_themes_have_multiple_sources(self):
        themes = [
        "lossless convexification",
        "sequential convex programming",
        "conic warm start and factorization reuse",
        "embedded real-time optimization",
        "robust and chance-constrained powered descent",
        "closed-loop and hardware-in-the-loop",
        ]
        rows, errors = load_and_validate(MATRIX, BIB)
        self.assertFalse(errors, "\n".join(errors))
        for theme in themes:
            with self.subTest(theme=theme):
                self.assertGreaterEqual(sum(row["theme"] == theme for row in rows), 3)


if __name__ == "__main__":
    unittest.main()
