# Systematic literature review protocol

## Registration and responsibility

Executed 2026-07-13 (Asia/Shanghai), covering database inception through that date. The repository research maintainer owns quarterly updates (January, April, July, October) and a refresh before every paper release.

## Eligibility

Core questions are lossless convexification; SCP; conic warm starts/factorization reuse; embedded real-time optimization; robust/chance-constrained powered descent; and closed-loop/HIL landing evidence. A core source must directly name the method and application in its title, abstract, or full text. Generic NLP, CasADi, direct transcription, robust optimization, and sparse algebra are adjacent prior art and do not count toward the three-direct-source minimum.

Include archival articles, proceedings, theses, and publisher/agency reports with identifiable title, authors, year, venue, and DOI or institutional URL. Exclude snippets, blogs, unarchived slides, duplicate versions, wrong DOI identities, and inferred relevance. Screening exclusions: wrong work/DOI 13; duplicate 2; no stable identity 3; adjacent-only 12 (retained but non-core).

## Exact searches and counts

Crossref endpoint: https://api.crossref.org/works?query.bibliographic=QUERY&rows=20. NASA NTRS and publisher searches used the literal queries below. Counts are inspected / retained after deduplication.

| Database | Exact query | Count |
|---|---|---:|
| Crossref | "lossless convexification" powered descent guidance | 20 / 7 |
| Crossref | "successive convexification" powered descent guidance | 20 / 3 |
| Crossref | conic solver embedded warm start factorization reuse | 20 / 6 |
| Crossref | embedded real-time convex optimization MPC | 20 / 7 |
| Crossref | robust powered descent guidance convex optimization | 5 / 1 |
| Crossref | stochastic powered descent guidance | 5 / 1 |
| Crossref | powered descent guidance uncertainty | 5 / 1 |
| Crossref | Morpheus lander project flight test | 5 / 1 |
| NASA NTRS | powered descent guidance Morpheus | 25 / 3 |
| NASA NTRS | terrain relative navigation landing | 25 / 2 |
| IEEE Xplore | ("powered descent" AND (stochastic OR chance)) | 8 / 1 |
| AIAA ARC | "powered descent" AND "covariance steering" | 3 / 1 |

## Deduplication and citation chasing

Normalize DOI to lowercase without resolver prefixes. Without a DOI, normalize title punctuation/spacing and compare title plus first author and year. Prefer the version of record. Backward chasing began with Acikmese and Ploen (2007), Acikmese et al. (2013), Domahidi et al. (2013), and Malyuta et al. (2021). Forward chasing used Crossref cited-by and publisher cited-by lists. Fourteen candidates were screened: six retained and eight duplicate or adjacent-only.

## Evidence and audit

metadata_verified supports only identity and conservative title-level relevance. full_text_verified requires readable full text and section/page-specific extraction. Unknown claims say "not established from metadata; full-text review required". DOI identity is checked with GET https://api.crossref.org/works/{urlencoded-doi}; NASA records use their exact NTRS citation page.

Run `python3 -m unittest -v tests/test_literature_matrix.py`, then `python3 research/literature/check_literature.py`. Online verification is `python3 research/literature/check_literature.py --verify-online`.
