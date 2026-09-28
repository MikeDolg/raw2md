# Benchmarks

## MPDocBench-Parse

- Paper: [MPDocBench-Parse: Benchmarking Practical Multi-page Document Parsing](https://arxiv.org/abs/2605.22100)
- Code and scorer: [Tongyi-Zhiwen/Qwen-Doc](https://github.com/Tongyi-Zhiwen/Qwen-Doc), folder `MPDocBench`
- Data: [zhoubb/MPDocBench](https://www.modelscope.cn/datasets/zhoubb/MPDocBench), [SlideVQA](https://huggingface.co/datasets/NTT-hil-insight/SlideVQA)

| Element, metric | Whole set, engine | Whole set, raw2md | English, engine | English, raw2md |
|---|---|---|---|---|
| `text_block`, Edit_dist ↓ | 0.122 | 0.130 | 0.112 | 0.126 |
| `merged_text_block`, Edit_dist ↓ | 0.303 | 0.300 | 0.286 | 0.281 |
| `table`, TEDS ↑ | 0.652 | 0.698 | 0.664 | 0.706 |
| `merged_table`, TEDS ↑ | 0.488 | 0.553 | 0.500 | 0.572 |
| `text_relation`, Relation_F1 ↑ | 0.122 | 0.131 | 0.133 | 0.148 |
| `reading_order`, Edit_dist ↓ | 0.204 | 0.205 | 0.209 | 0.211 |
| `head`, HeadTEDS ↑ | 0.371 | 0.408 | 0.392 | 0.430 |
| `display_formula`, CDM ↑ | 0.818 | 0.821 | 0.858 | 0.867 |

**engine** is the output of `marker` before raw2md, and **raw2md** is the
final Markdown file. The difference between the two is what raw2md adds.
`raw2md <pdf> -e marker -d`, no LLM stages. The details of each run are in
[mpdocbench/results/](mpdocbench/results/).

`FigureF1` and `table_relation` are not computable for raw2md: they read
figure boxes from image file names and merged tables from HTML.

The English set is a part of the whole set and is not for comparison with
other results. It shows what raw2md adds to the engine.

How to run: [mpdocbench/README.md](mpdocbench/README.md).

License: the code of the benchmark is Apache-2.0. The data is CC BY-NC-SA 4.0,
for academic and research use only. SlideVQA is under an NTT license for
evaluation only. This repository does not redistribute the data.
