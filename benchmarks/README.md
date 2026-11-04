# Benchmarks

## MPDocBench-Parse

- Paper: [MPDocBench-Parse: Benchmarking Practical Multi-page Document Parsing](https://arxiv.org/abs/2605.22100)
- Code and scorer: [Tongyi-Zhiwen/Qwen-Doc](https://github.com/Tongyi-Zhiwen/Qwen-Doc), folder `MPDocBench`
- Data: [zhoubb/MPDocBench](https://www.modelscope.cn/datasets/zhoubb/MPDocBench), [SlideVQA](https://huggingface.co/datasets/NTT-hil-insight/SlideVQA)

| Element, metric | Whole set | English |
|---|---|---|
| `text_block`, Edit_dist ↓ | 0.130 | 0.125 |
| `merged_text_block`, Edit_dist ↓ | 0.299 | 0.280 |
| `table`, TEDS ↑ | 0.696 | 0.706 |
| `merged_table`, TEDS ↑ | 0.553 | 0.572 |
| `text_relation`, Relation_F1 ↑ | 0.132 | 0.149 |
| `reading_order`, Edit_dist ↓ | 0.206 | 0.212 |
| `head`, HeadTEDS ↑ | 0.453 | 0.493 |
| `display_formula`, CDM ↑ | 0.826 | 0.869 |
| `figure`, FigureF1 ↑ | 0.652 | 0.646 |
| `table_relation`, Relation_F1 ↑ | n/a | n/a |
| Overall ↑ | 69.30 | 70.87 |

**Overall** is the summary score of the benchmark leaderboard: the mean of the
eight rows other than `text_relation` and `table_relation`, on a 0–100 scale.
An Edit_dist value `x` counts as `(1 − x) · 100`, and the value of any other
metric as `x · 100`.

Both columns come from one run of raw2md 0.3.0 without the LLM stages:
`raw2md <pdf> -d -s -e raw2md-engine`. `raw2md-engine` is based on `marker`
1.10.2. The English column scores the English documents of that run.

The result files are in [mpdocbench/results/](mpdocbench/results/).

`table_relation` is not computable for raw2md: the metric reads merged tables
from HTML, and raw2md writes tables in Markdown.

The English set is a part of the whole set and is not for comparison with
other results.

How to run: [mpdocbench/README.md](mpdocbench/README.md).

License: the code of the benchmark is Apache-2.0. The data is CC BY-NC-SA 4.0,
for academic and research use only. SlideVQA is under an NTT license for
evaluation only. This repository does not redistribute the data.
