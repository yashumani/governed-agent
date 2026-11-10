# demo-repo

A tiny calculator fixture for the governed reviewer, so the whole
reviewer runs end-to-end offline with no model key and no GPU.

## The fixture

- `calculator.py` — five small functions.
- `test_calculator.py` — five tests.

## Injected bugs (intentional — this is an eval fixture)

1. `divide` (`calculator.py:24`) uses integer division (`a // b`)
   while its docstring promises a float result. `test_divide_returns_float` fails.
2. `average` (`calculator.py:31`) divides by `len(values) + 1`
   instead of `len(values)`. `test_average` fails.

A correct reviewer should report exactly these two findings, each with
a file/line citation and high confidence, and nothing else. A finding
about any other line is a false positive.
