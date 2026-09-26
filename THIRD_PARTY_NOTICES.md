# Third-party notices

The MIT license in `LICENSE` covers the raw2md source code only. This file
lists the third-party material that raw2md bundles or keeps in its test
assets, and the licenses of the software and the models that an installation
of raw2md runs.

## Bundled material

The raw2md package contains one third-party file: `raw2md/katex.min.js`,
KaTeX 0.18.4, unmodified. raw2md uses it to check that formulas are valid.

```text
The MIT License (MIT)

Copyright (c) 2013-2020 Khan Academy and other contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Test assets

The repository keeps one third-party file outside the package:
`tests/corpus/assets/fonts/Caveat-Regular.ttf`, the Caveat font, unmodified.
The round-trip tests use it to render a handwritten page. The font is
Copyright 2014 The Caveat Project Authors
(<https://github.com/googlefonts/caveat>) and is licensed under the SIL Open
Font License 1.1. The license text is in
`tests/corpus/assets/fonts/OFL.txt`, next to the font.

## Dependencies that raw2md does not bundle

The package manager installs the dependencies. raw2md does not distribute
them, and its MIT license does not change their licenses. The installed
program runs under all of them together. Two are strong copyleft licenses:

- `PyMuPDF` is available under AGPL-3.0, or under a commercial license from
  Artifex.
- `marker-pdf` and `surya-ocr` are available under GPL-3.0-or-later.

If you distribute a program that contains raw2md and these dependencies, or
you let users interact over a network with a modified `PyMuPDF`, the terms of
these licenses apply to you. The other runtime dependencies use permissive or
weak copyleft licenses: MIT, BSD, Apache-2.0, HPND, MPL-2.0, and LGPL-3.0.

The CUDA libraries come inside the `torch` wheel. raw2md does not distribute
them.

## Model weights

`marker` downloads its model weights on the first run. The weights are not
part of raw2md. They are licensed by Datalab under a modified AI Pubs
OpenRAIL-M license:
<https://github.com/datalab-to/marker/blob/master/MODEL_LICENSE>

In short, and the license text governs:

- Use is free for research, for personal use, and for an organization with
  less than $2M in gross revenue in the prior year and less than $2M in total
  funding.
- An organization whose product or service competes with Datalab may not use
  the weights, whatever its size.
- The license applies to the output of the models too: a Markdown file that
  raw2md makes from a PDF or a DjVu file with `marker`. If you share such a
  file, give credit to Datalab, link to the model, and include a copy of the
  license.

Commercial licenses are available from Datalab: <https://www.datalab.to/>
