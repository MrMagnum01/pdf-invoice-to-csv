# Third-party licences

Every library this project imports at runtime or in its test suite, and the
licence it ships under. All are open source; no closed-source or paid
dependency is used.

| Library | Version (pinned in `requirements.txt`) | Licence | Used for |
|---|---|---|---|
| [reportlab](https://pypi.org/project/reportlab/) | 5.0.1 | BSD-3-Clause (see the package's own `license.txt`) | Generating the synthetic invoice PDFs |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 0.11.10 | MIT | Extracting text/tables from PDFs |
| [pdfminer.six](https://pypi.org/project/pdfminer.six/) | 20260107 | MIT (pdfplumber's PDF-parsing engine) | Transitive dependency of pdfplumber |
| [pypdfium2](https://pypi.org/project/pypdfium2/) | 5.13.0 | BSD-3-Clause / Apache-2.0 (dual-licensed, dependency licences bundled) | Transitive dependency of pdfplumber; used here to detect image-only (no text layer) pages |
| [Pillow](https://pypi.org/project/Pillow/) | 12.3.0 | MIT-CMU | Transitive dependency of pdfplumber/reportlab; also used directly to render the one "scanned-looking" page as a raster image |
| [pytest](https://pypi.org/project/pytest/) | 9.1.1 | MIT | Test suite |

Transitive build/runtime dependencies pulled in by the above (`cffi`,
`cryptography`, `pycparser`, `charset-normalizer`, `packaging`, `pluggy`,
`iniconfig`, `Pygments`) are themselves MIT, BSD-3-Clause, or Apache-2.0
licensed per their own PyPI metadata; none add a licence obligation beyond
what's already listed above.

No paid or closed-source service is used anywhere in this project.
