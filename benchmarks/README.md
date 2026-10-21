# Benchmarks

## MPDocBench-Parse

- Paper: [MPDocBench-Parse: Benchmarking Practical Multi-page Document Parsing](https://arxiv.org/abs/2605.22100)
- Code and scorer: [Tongyi-Zhiwen/Qwen-Doc](https://github.com/Tongyi-Zhiwen/Qwen-Doc), folder `MPDocBench`
- Data: [zhoubb/MPDocBench](https://www.modelscope.cn/datasets/zhoubb/MPDocBench), [SlideVQA](https://huggingface.co/datasets/NTT-hil-insight/SlideVQA)

| Element, metric | Whole set, engine | Whole set, raw2md | English, engine | English, raw2md |
|---|---|---|---|---|
| `text_block`, Edit_dist ↓ | 0.122 | 0.130 | 0.112 | 0.126 |
| `merged_text_block`, Edit_dist ↓ | 0.303 | 0.300 | 0.285 | 0.280 |
| `table`, TEDS ↑ | 0.652 | 0.698 | 0.665 | 0.706 |
| `merged_table`, TEDS ↑ | 0.488 | 0.553 | 0.500 | 0.573 |
| `text_relation`, Relation_F1 ↑ | 0.122 | 0.131 | 0.134 | 0.149 |
| `reading_order`, Edit_dist ↓ | 0.204 | 0.205 | 0.209 | 0.211 |
| `head`, HeadTEDS ↑ | 0.371 | 0.408 | 0.392 | 0.429 |
| `display_formula`, CDM ↑ | 0.818 | 0.821 | 0.858 | 0.868 |

**engine** is the output of the engine before raw2md, and **raw2md** is the
final Markdown file. The difference between the two is what raw2md adds. No
run used the LLM stages.

- Whole set: raw2md 0.1.0, `raw2md <pdf> -d -s -e marker`, with `marker`
  1.10.2.
- English: `raw2md <pdf> -d -s -e raw2md-engine`, on the code of 0.2.0 before
  the version number changed, so its result file names 0.1.1.
  `raw2md-engine` is based on `marker` 1.10.2.

The details of each run are in [mpdocbench/results/](mpdocbench/results/).

`FigureF1` and `table_relation` are not computable for raw2md: they read
figure boxes from image file names and merged tables from HTML.

The English set is a part of the whole set and is not for comparison with
other results. It shows what raw2md adds to the engine.

How to run: [mpdocbench/README.md](mpdocbench/README.md).

License: the code of the benchmark is Apache-2.0. The data is CC BY-NC-SA 4.0,
for academic and research use only. SlideVQA is under an NTT license for
evaluation only. This repository does not redistribute the data.
