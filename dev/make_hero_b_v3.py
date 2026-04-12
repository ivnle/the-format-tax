"""Hero figure variant B (v3): v2 + no gridlines + distinctive chance line.

Visual changes from v2:
  - gridlines removed (they were competing with the freeform and chance
    reference lines, both of which are intentional horizontal markers)
  - chance line is now a muted purple dotted line so it pops clearly
    against the data and can't be mistaken for gridwork
  - y-axis spine is kept visible as the left-edge anchor for each panel
"""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from datasets import get_dataset_split_names, load_dataset

DATASET = "ivnle/the-format-tax"
TASKS = ["math500", "gpqa", "zebralogic"]
STRUCT_FORMATS = ["json", "xml", "latex", "markdown"]
FREEFORM = "freeform"

CHANCE = {"math500": 0.0, "gpqa": 0.25, "zebralogic": 1.0 / 6.0}

TASK_LABELS = {"math500": "MATH500", "gpqa": "GPQA", "zebralogic": "ZebraLogic"}
FORMAT_LABELS = {"json": "JSON", "xml": "XML", "latex": "LaTeX", "markdown": "Markdown"}
MODEL_LABELS = {
    "qwen3_8b": "Qwen3-8B",
    "llama_3_1_8b_instruct": "Llama-3.1-8B-Instruct",
    "olmo_3_7b_instruct": "OLMo-3-7B-Instruct",
    "qwen3_32b": "Qwen3-32B",
    "granite_4_0_h_tiny": "Granite-4.0-H-Tiny",
    "granite_4_0_h_small": "Granite-4.0-H-Small",
}

OUT_PNG = Path(__file__).parent.parent / "assets" / "hero.png"


def compute_accuracies(ds) -> dict[tuple[str, str, str], tuple[float, int]]:
    sums: dict[tuple[str, str, str], int] = {}
    counts: dict[tuple[str, str, str], int] = {}

    task_col = ds["task"]
    fmt_col = ds["format"]
    dec_col = ds["decoding"]
    parsed_col = ds["judge_parsed"]
    correct_col = ds["judge_correct"]

    for task, fmt, dec, parsed, correct in zip(
        task_col, fmt_col, dec_col, parsed_col, correct_col
    ):
        if not parsed:
            continue
        key = (task, fmt, dec)
        counts[key] = counts.get(key, 0) + 1
        sums[key] = sums.get(key, 0) + (1 if correct else 0)

    out: dict[tuple[str, str, str], tuple[float, int]] = {}
    for key, n in counts.items():
        out[key] = (sums[key] / n, n)
    return out


def make_figure(per_split_accs: dict[str, dict]) -> plt.Figure:
    splits = sorted(per_split_accs.keys())
    n_cols = len(splits)
    n_rows = len(TASKS)

    plt.style.use("default")

    fig, axes = plt.subplots(
        n_rows,
        n_cols,
        figsize=(max(4.2 * n_cols, 6.5), 2.7 * n_rows + 1.6),
        sharey=True,
        squeeze=False,
    )

    x = np.arange(len(STRUCT_FORMATS))
    bar_w = 0.38

    color_prompt = "#2f6fb5"
    color_gcd = "#9dc3e8"
    color_freeform = "#c0392b"
    color_chance = "#6b5b95"  # muted purple, distinct from red freeform
    color_loss = "#c0392b"  # red for lost competence

    for r, task in enumerate(TASKS):
        for c, split in enumerate(splits):
            ax = axes[r][c]
            accs = per_split_accs[split]

            prompt_vals = []
            gcd_vals = []
            for fmt in STRUCT_FORMATS:
                p = accs.get((task, fmt, "prompt"), (np.nan, 0))[0]
                g = accs.get((task, fmt, "gcd"), (np.nan, 0))[0]
                prompt_vals.append(p * 100 if not np.isnan(p) else np.nan)
                gcd_vals.append(g * 100 if not np.isnan(g) else np.nan)

            ax.bar(
                x - bar_w / 2,
                prompt_vals,
                bar_w,
                color=color_prompt,
                edgecolor="white",
                linewidth=0.6,
                label="Format",
                zorder=3,
            )
            ax.bar(
                x + bar_w / 2,
                gcd_vals,
                bar_w,
                color=color_gcd,
                edgecolor=color_prompt,
                linewidth=0.8,
                hatch="///",
                label="Format (+GCD)",
                zorder=3,
            )

            # freeform baseline
            ff = accs.get((task, FREEFORM, "prompt"))
            ff_y = ff[0] * 100 if ff is not None else None

            # shade the tax region per bar (between bar top and freeform)
            # Only shade losses — gains are visually confusing because the
            # shading sits inside the bar and reads as "below freeform."
            if ff_y is not None:
                for i, fmt in enumerate(STRUCT_FORMATS):
                    for offset, val in (
                        (-bar_w / 2, prompt_vals[i]),
                        (+bar_w / 2, gcd_vals[i]),
                    ):
                        if np.isnan(val) or val >= ff_y:
                            continue
                        x0 = x[i] + offset - bar_w / 2
                        x1 = x[i] + offset + bar_w / 2
                        ax.fill_between(
                            [x0, x1],
                            val,
                            ff_y,
                            color=color_loss,
                            alpha=0.28,
                            linewidth=0,
                            zorder=4,
                        )

                ax.axhline(
                    ff_y,
                    color=color_freeform,
                    linestyle="--",
                    linewidth=1.6,
                    label="Freeform",
                    zorder=5,
                )

            ch = CHANCE[task] * 100
            if ch > 0:
                ax.axhline(
                    ch,
                    color=color_chance,
                    linestyle=":",
                    linewidth=1.2,
                    label="chance",
                    zorder=4,
                )

            ax.set_ylim(0, 100)
            ax.set_yticks([0, 25, 50, 75, 100])
            ax.set_xticks(x)
            ax.set_xticklabels([FORMAT_LABELS[f] for f in STRUCT_FORMATS], fontsize=13)
            ax.tick_params(axis="y", labelsize=13)
            # No gridlines; let the bars + reference lines carry all the ink
            ax.grid(False)
            # Keep left + bottom spines, drop the top and right
            for side in ("top", "right"):
                ax.spines[side].set_visible(False)
            for side in ("left", "bottom"):
                ax.spines[side].set_color("#666666")
                ax.spines[side].set_linewidth(0.8)

            if r == 0:
                ax.set_title(
                    MODEL_LABELS.get(split, split), fontsize=16, fontweight="bold", pad=10
                )
            if c == 0:
                ax.set_ylabel(
                    TASK_LABELS.get(task, task) + "\naccuracy (%)",
                    fontsize=15,
                    fontweight="bold",
                )

    handles = [
        plt.Rectangle((0, 0), 1, 1, color=color_prompt, label="Format"),
        plt.Rectangle(
            (0, 0),
            1,
            1,
            facecolor=color_gcd,
            edgecolor=color_prompt,
            hatch="///",
            label="Format (+GCD)",
        ),
        plt.Line2D([0], [0], color=color_freeform, linestyle="--", linewidth=2.2, label="Freeform"),
        plt.Rectangle((0, 0), 1, 1, facecolor=color_loss, alpha=0.3, label="format tax"),
        plt.Line2D([0], [0], color=color_chance, linestyle=":", linewidth=1.8, label="chance"),
    ]
    fig.legend(
        handles=handles,
        loc="lower center",
        bbox_to_anchor=(0.5, 0.0),
        frameon=True,
        fontsize=13,
        ncol=5,
    )

    fig.tight_layout(rect=(0, 0.06, 1, 0.97))
    return fig


def main() -> None:
    print(f"HF_HOME={os.environ.get('HF_HOME')}")
    splits = get_dataset_split_names(DATASET)
    print(f"splits: {splits}")

    per_split_accs: dict[str, dict] = {}
    for s in splits:
        print(f"loading split {s} ...")
        ds = load_dataset(DATASET, split=s)
        per_split_accs[s] = compute_accuracies(ds)

    fig = make_figure(per_split_accs)
    fig.savefig(OUT_PNG, dpi=200, bbox_inches="tight")
    print(f"\nsaved: {OUT_PNG}")


if __name__ == "__main__":
    main()
