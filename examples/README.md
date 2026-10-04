# Examples

Sources:

- `book.md`: Arthur T. Woods, Albert W. Stahl. *Elementary Mechanism: A Textbook for Students of Mechanical Engineering*. D. Van Nostrand, New York, 1885. [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Elementary_mechanism-_a_textbook_for_students_of_mechanical_engineering_(IA_cu31924031203742).pdf)
- `thesis.md`: Tina Schwamb. *Performance Monitoring and Numerical Modelling of a Deep Circular Excavation*. PhD thesis, University of Cambridge, 2014. [University of Cambridge repository](https://www.repository.cam.ac.uk/items/04ec45a9-4b8b-4ece-b848-7806d4636412)
- `report.md`: Jill Hanson, Lewis Clark. *An Evaluation of the Derbyshire and Nottinghamshire Collaborative Outreach Programme*. Final report, 2019. [University of Derby repository](https://derby-repository.worktribe.com/output/804857/an-evaluation-of-the-derbyshire-and-nottinghamshire-collaborative-outreach-programme)

Each file is the complete result for the whole source document. The sources are not in this repository.

## Results

| Result | Source | Pages | Engine | Source license | Result license |
|---|---|---|---|---|---|
| `book.md` | scanned PDF | 344 | `marker` | Public Domain Mark | AI Pubs OpenRAIL-M (modified), Datalab |
| `thesis.md` | born-digital PDF | 230 | `marker` | CC0 1.0 | AI Pubs OpenRAIL-M (modified), Datalab |
| `report.md` | DOCX | – | `pandoc` | CC0 1.0 | CC0 1.0 |

The source license is the license that the repository record of the source states.

## Source checksums

The SHA-256 checksum of each source file:

| Result | Source SHA-256 |
|---|---|
| `book.md` | `3a6bd046567056eac8328815f5429e8a78960c2c525e26dcd5e77c6703dd7c5d` |
| `thesis.md` | `0129ee608282a5690992f28052b8853e6d5a1a7af954214cc61303565888af3b` |
| `report.md` | `d1f8115f2f6495eda3d891f69ab40e92c16ea7c2f1c3baa5f8f62683c3991668` |

The `source_hash` field in the header of each result holds the same checksum in URL-safe Base64.

## Conversion

raw2md 0.1.0 made all three results with this command:

```bash
raw2md SOURCE -i gemini_api -p gemini_api --disable-image-extraction
```

| Result | Time | Machine |
|---|---|---|
| `book.md` | 16 min 25 s | Ubuntu 22.04, NVIDIA RTX A5000, CUDA 13.0 |
| `thesis.md` | 6 min 22 s | Ubuntu 22.04, NVIDIA RTX A5000, CUDA 13.0 |
| `report.md` | 7 s | Windows 10, NVIDIA T1200 Laptop GPU |

Key:

- `gemini_api` is the `gemini-3.5-flash-lite` model. It runs the LLM inspection (`-i`) and the LLM post-processing (`-p`).
- A DOCX source has no scan, so `report.md` has no inspection step.
- `--disable-image-extraction` removes the images. The captions stay in the text.
- The time covers the full conversion, including the LLM steps.

## License of the results

`book.md` and `thesis.md` are output of the `marker` models by Datalab. The models are licensed under a modified AI Pubs OpenRAIL-M license, and the license applies to their output too. The license text is in [`MODEL_LICENSE`](MODEL_LICENSE). The models are available at <https://github.com/datalab-to/marker/tree/v1.10.2>. raw2md cleaned the output of the models and changed the text.

The `pandoc` converter made `report.md` from the DOCX source. The result is dedicated to the public domain under CC0 1.0, as the source is.
