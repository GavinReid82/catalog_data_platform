# Search tuning experiments — 2026-11-12

All numbers below are copied from the JSON files in `search/eval/results/`. Setup: 40 queries (15 keyword, 15 descriptive, 10 messy) and 719 judgements, pre-graded by an LLM, with every query checked by Gavin Reid. The index holds 5,861 products, and k = 10.

**These are in-sample numbers.** The variants were tuned on the same 40 queries they are scored on. With 40 queries, I treat a difference in nDCG@10 under about 0.02 as noise.

## Baseline (`2026-11-12-baseline.json`)

| method | nDCG@10 | MRR@10 | Recall@10 | judged@10 | descriptive | keyword | messy |
|---|---|---|---|---|---|---|---|
| bm25 | 0.685 | 0.841 | 0.496 | 0.950 | 0.557 | 0.882 | 0.580 |
| vector | **0.841** | 0.956 | **0.598** | 1.000 | **0.811** | 0.915 | **0.772** |
| hybrid (0.5/0.5) | 0.815 | 0.942 | 0.572 | 1.000 | 0.732 | **0.946** | 0.744 |

The last three columns are nDCG@10 by query type. BM25's judged@10 is below 1 only because it returned **no results at all** for q31 "watter botle" and q32 "powerbnk".

## Experiment 1: hybrid weights (BM25 weight / vector weight)

The weights only change the hybrid row. BM25 and vector stay the same as the baseline.

| label | weights | hybrid nDCG@10 | MRR@10 | Recall@10 | descriptive | keyword | messy | kept? |
|---|---|---|---|---|---|---|---|---|
| hybrid-0.2-0.8 | 0.2 / 0.8 | 0.824 | 0.956 | 0.578 | 0.774 | 0.920 | 0.756 | no |
| hybrid-0.3-0.7 | 0.3 / 0.7 | 0.819 | 0.956 | 0.569 | 0.754 | 0.930 | 0.749 | no |
| hybrid-0.4-0.6 | 0.4 / 0.6 | 0.821 | 0.956 | 0.568 | 0.752 | 0.936 | 0.754 | no |
| baseline | 0.5 / 0.5 | 0.815 | 0.942 | 0.572 | 0.732 | 0.946 | 0.744 | (default) |
| hybrid-0.6-0.4 | 0.6 / 0.4 | 0.792 | 0.897 | 0.572 | 0.698 | 0.925 | 0.732 | no |
| hybrid-0.7-0.3 | 0.7 / 0.3 | 0.782 | 0.885 | 0.569 | 0.680 | 0.922 | 0.726 | no |
| hybrid-0.8-0.2 | 0.8 / 0.2 | 0.778 | 0.884 | 0.567 | 0.669 | 0.916 | 0.734 | no |

More weight on vector helps hybrid, but the best weighting (0.2 / 0.8, nDCG 0.824) only beats the 0.5 / 0.5 default by 0.009. That is inside the noise. It is also still below vector alone (0.841). I kept the default.

## Experiment 2: BM25 field boosts

| label | change | bm25 nDCG@10 | bm25 judged@10 | hybrid nDCG@10 | hybrid judged@10 | kept? |
|---|---|---|---|---|---|---|
| baseline | `product_name^3`, type/category/subcategory/keywords `^2` | 0.685 | 0.950 | 0.815 | 1.000 | (default) |
| boost-name5 | `product_name^5`, the rest unchanged | 0.569 | 0.748 | 0.749 | 0.930 | no |
| boost-flat | no boosts | 0.384 | 0.440 | 0.665 | 0.753 | no |

**Warning:** both variants have a much lower judged@10 than the baseline (0.75 and 0.44 against 0.95). Most of their new top-10 products were never graded, and ungraded products count as wrong. So the drop in their scores is exaggerated, and these rows cannot be read as true scores. The direction is still informative: once the boosts change, BM25 brings up many products the graded pool never saw. I kept the default.

## What I learned

1. **Keyword search breaks when people describe a need or make a typo.** BM25 scored 0.557 on descriptive queries and 0.580 on messy ones, against 0.811 and 0.772 for vector. For two typo queries it returned nothing.
2. **Hybrid is not automatically better.** At 0.5 / 0.5 it won only on keyword queries (0.946). Overall it trailed vector (0.815 against 0.841), because the weak BM25 scores pull it down. No weighting I tried beat vector alone.
3. **Tuning needs a judged pool that covers the variants.** Changing the BM25 boosts surfaced products nobody had graded (judged@10 fell to 0.44). A fair boost comparison needs those products graded first.

## Defaults after tuning

Unchanged: `DEFAULT_HYBRID_WEIGHTS = (0.5, 0.5)` and `DEFAULT_BM25_FIELDS` as in the baseline. No variant beat its default by more than the noise threshold.
