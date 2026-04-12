# Illustrative examples

Three hand-picked triples from the format-tax sweep. Each file
contains the verbatim question, the verbatim prompt sent to the
model, and the verbatim raw model output for three decoding
conditions on the same example: **Freeform**, **Format** (structured
prompting), and **Format (+GCD)** (structured prompting plus
grammar-constrained decoding). No trimming, no editorializing.

These files are the source material. The top-level README shows
concise snippets and explains what's happening; this directory is
where a reader fact-checks those snippets against the raw triples.

All three use the same model (OLMo-3-7B-Instruct) and the same
schema (JSON). In every case, freeform gets the right answer and
both structured variants get the wrong answer.

## Files

| # | Task | Topic | File |
|---|---|---|---|
| 1 | MATH500 | Ball-swap probability | [`01-math500-ball-swap.md`](01-math500-ball-swap.md) |
| 2 | GPQA | Quantum wavefunction normalization | [`02-gpqa-wavefunction.md`](02-gpqa-wavefunction.md) |
| 3 | ZebraLogic | 4-house constraint puzzle | [`03-zebralogic-houses.md`](03-zebralogic-houses.md) |

## Pulling your own

`dev/show_triple.py` at the repo root can print triples for any
`(split, task, format, example_id)` in the HF dataset
[`ivnle/the-format-tax`](https://huggingface.co/datasets/ivnle/the-format-tax):

```bash
python dev/show_triple.py \
    --split olmo_3_7b_instruct \
    --task math500 \
    --format json \
    --example-id 138 \
    --full-output
```

Use `--random --where "ff_correct and not prompt_correct and not gcd_correct"`
to sample format-tax failures from any split.
