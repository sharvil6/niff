# Niff

A private, self-hosted finance agent for a two-person household. See the design doc for the full picture.

## Development

Requires [uv](https://docs.astral.sh/uv/). uv installs Python 3.13 and the project's virtual environment on first use.

```bash
uv sync                          # create .venv from uv.lock
uv run uvicorn niff.main:app --reload   # dev server on http://127.0.0.1:8000
uv run pytest                    # tests
uv run ruff check . && uv run ruff format --check .   # lint + format
uv run pyright                   # type check
```
