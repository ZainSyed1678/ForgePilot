# ForgePilot research report

## Status

The benchmark and reporting pipeline are implemented. **No live model comparison has been run.** The local workspace has no configured model or API key, and the existing local smoke database contains an unverified attempt from when Docker was unavailable. Scripted model tests validate the runner; they are not evidence that any architecture performs better. Consequently, there are no empirical architecture rankings, success rates, or statistical conclusions to report yet.

## Research question

How do basic tool use, planner–executor–critic, and reflection after tool failures perform on the same software engineering tasks under the same model and tool budgets? The planned comparisons cover task success, test regressions, elapsed agent time, reported token use, and recovery after tool failures. Subgroup descriptions cover task complexity, observed agent steps, information availability, and fixture failure type.

## Method

The nine versioned task fixtures contain starter files, an agent prompt, and hidden acceptance tests. Five tasks provide the needed information directly; four require inspecting repository clues. Every attempt starts in a fresh Git repository. The runner executes baseline tests in a network-disabled Docker container before calling a model. After the attempt, it restores the original tests, adds the predefined acceptance test, and grades with pytest. A successful run must pass all cases without losing any baseline case. Unverified grading is excluded from success denominators.

Each architecture receives at most 12 model turns and 24 tool calls. The runner records fixture SHA-256, model name, image tag, repeat index, resource limits, test counts, steps, time, tool failures, clue-file reads, and API-reported token usage in SQLite. Missing token usage is left missing. The `forgepilot analyze` command writes raw-count-backed tables and a descriptive chart. It flags whether architectures have matching task hash, model, image, and repeat coverage. Complexity is a prespecified structural proxy: single-file versus multi-file, counted from non-test, non-document source files in a fixture. Step counts are outcomes of attempts, so their association with success cannot show that more steps cause success.

## Reproduction

```sh
python -m pip install -e ".[dev]"
docker build -t forgepilot-runner:phase1 .
python -m pytest -q
# Set FORGEPILOT_MODEL and FORGEPILOT_API_KEY locally first.
forgepilot compare --repeats 3 --output results/experiments.sqlite3
forgepilot analyze --database results/experiments.sqlite3 --output-dir results/analysis
```

The complete matrix above is 9 tasks × 3 architectures × 3 repeats, or 81 model attempts. Live runs can incur API charges. Use one model and one pinned runner image for the matrix, retain the SQLite database, and record the image digest and provider model snapshot externally because the current runner stores only an image tag and model name. Do not mix scripted or unverified runs into this matrix. `results/` is excluded from Git because raw attempts can contain code, model messages, and other sensitive context.

## Results and interpretation

No verified live-model results are available. The study cannot currently answer whether planning or reflection improves task success, recovery, speed, or token efficiency. The repository test suite and Docker checks establish only that fixtures, isolation, grading, architecture wiring, and reporting work on controlled examples. They do not measure autonomous software engineering capability.

Once live runs exist, report each rate with its numerator and denominator, examine the `dimensions.csv` groups, and inspect failures in the raw records. Treat small subgroup counts and unequal coverage as exploratory. A matched matrix permits descriptive comparison, but three repeats per cell are too few to support strong claims about model reliability or statistical significance.

## Limitations and trade-offs

- Nine synthetic tasks are a narrow sample. The structural complexity proxy may not reflect human difficulty.
- The acceptance suite can miss defects outside its specified behavior, and pytest is not a security boundary against an adversarial agent.
- Reflection triggers after tool failures; successful but misleading tool outputs may remain undetected.
- Clue coverage counts explicit file reads, so other ways of finding a clue are not represented.
- Agent steps, latency, and token usage depend on provider behavior and run conditions. Provider-reported usage may be absent.
- An image tag and model name alone do not freeze the exact runtime or model snapshot.

The next evidence-gathering step is a cost-approved, credentialed model matrix. Until then, this report remains a methods and validation report rather than a claim of architecture effectiveness.
