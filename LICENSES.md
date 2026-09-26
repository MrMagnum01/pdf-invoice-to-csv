# Third-party licences

Every library this project installs, and the licence it ships under, as
read from each package's installed distribution metadata. All are open
source; no closed-source or paid dependency is used.

## Direct dependencies (pinned in `requirements.txt`)

Only these four are pinned. Everything else below is pulled in by them, and
the version shown is the one a clean install resolved, not a pin.

| Library | Pinned version | Licence | Used for |
|---|---|---|---|
| [reportlab](https://pypi.org/project/reportlab/) | 5.0.1 | BSD-3-Clause (see the package's own `license.txt`) | Generating the synthetic invoice PDFs |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | 0.11.10 | MIT | Extracting text/tables from PDFs |
| [Pillow](https://pypi.org/project/Pillow/) | 12.3.0 | MIT-CMU | Rendering the one "scanned-looking" page as a raster image |
| [pytest](https://pypi.org/project/pytest/) | 9.1.1 | MIT | Test suite |

## Transitive dependencies (not pinned; versions from a clean install)

| Library | Resolved version | Licence | Pulled in by |
|---|---|---|---|
| [pdfminer.six](https://pypi.org/project/pdfminer.six/) | 20260107 | MIT | pdfplumber (its PDF-parsing engine) |
| [pypdfium2](https://pypi.org/project/pypdfium2/) | 5.13.0 | BSD-3-Clause, Apache-2.0, plus the licences of its bundled dependencies | pdfplumber (not called directly; image-only pages are detected from pdfplumber's text layer) |
| [cryptography](https://pypi.org/project/cryptography/) | 50.0.1 | Apache-2.0 OR BSD-3-Clause | pdfminer.six |
| [cffi](https://pypi.org/project/cffi/) | 2.1.1 | MIT-0 | cryptography |
| [pycparser](https://pypi.org/project/pycparser/) | 3.0 | BSD-3-Clause | cffi |
| [charset-normalizer](https://pypi.org/project/charset-normalizer/) | 3.5.1 | MIT | pdfminer.six, reportlab |
| [packaging](https://pypi.org/project/packaging/) | 26.3 | Apache-2.0 OR BSD-2-Clause | pytest |
| [pluggy](https://pypi.org/project/pluggy/) | 1.6.0 | MIT | pytest |
| [iniconfig](https://pypi.org/project/iniconfig/) | 2.3.0 | MIT | pytest |
| [Pygments](https://pypi.org/project/Pygments/) | 2.21.0 | BSD-2-Clause | pytest |

## Notices

These licences require their copyright and licence notices to be kept with
any copy or redistribution. This repository does not vendor or redistribute
any of these packages; they are installed from PyPI. Each installed package
carries its own licence and notice files (including pypdfium2's bundled
dependency licences), and those must be preserved in any distribution that
includes them.

No paid or closed-source service is used anywhere in this project.
