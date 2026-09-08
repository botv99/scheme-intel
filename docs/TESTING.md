# Scheme-Intel Testing Guide

## Running Tests

### Run all tests
```bash
python -m pytest tests/ -v
```

### Run with coverage report
```bash
python -m pytest tests/ -v --cov=src/scheme_intel --cov-report=html
```

### Run specific test file
```bash
python -m pytest tests/test_sources.py -v
```

### Run specific test class
```bash
python -m pytest tests/test_sources.py::TestFetchRss -v
```

### Run specific test
```bash
python -m pytest tests/test_sources.py::TestFetchRss::test_fetch_rss_success -v
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── test_sources.py          # Source fetching tests
├── test_catalyst.py         # Catalyst classification tests
└── test_notifier.py         # Telegram notification tests
```

## Test Coverage

Current coverage targets:
- **sources.py**: Feed fetching, page scanning, error handling
- **catalyst.py**: Event classification, scoring
- **notifier.py**: Telegram sending, multi-chat support
- **models.py**: Data model integrity

Run coverage report:
```bash
python run_tests.py
```

This generates an HTML report in `htmlcov/index.html`

## CI/CD Integration

Tests run automatically in GitHub Actions on:
- Every pull request
- Every commit to main branch

See `.github/workflows/test.yml` for workflow configuration.
