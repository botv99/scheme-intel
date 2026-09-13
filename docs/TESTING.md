# Testing Guide for Scheme-Intel

## Quick Start

### Install test dependencies
```bash
pip install -r requirements.txt
```

### Run all tests (default: coverage + parallel)
```bash
python run_tests.py
```
Generates `htmlcov/index.html`, `coverage.xml`, and `coverage.json`.

### Run without coverage
```bash
python run_tests.py --no-coverage
```

### Run only unit tests
```bash
python run_tests.py -m unit
```

### Fallback: direct pytest
```bash
python -m pytest tests/ -v
```

## Running Specific Tests

### Run single test file
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

### Run only unit tests
```bash
python -m pytest tests/ -v -m unit
```

## Test Structure

```
tests/
├── conftest.py              # Shared fixtures and configuration
├── test_catalyst.py         # Catalyst classification tests (5 tests)
├── test_ingestion.py        # Screener/NSE/BSE/media ingestion tests (20 tests)
├── test_main.py             # Pipeline entry-point tests (5 tests)
├── test_models.py           # Data model tests (3 tests)
├── test_notifier.py         # Telegram notification tests (11 tests)
├── test_pipeline.py         # Pipeline ingestion wiring tests (9 tests)
├── test_signals.py          # Technical analysis tests (18 tests)
└── test_sources.py          # Source fetching tests (11 tests)
```

## Test Coverage

Current coverage across modules:
- **sources.py**: Feed fetching, page scanning, error handling, deduplication, date parsing
- **catalyst.py**: Event classification, scoring, multi-company matching
- **notifier.py**: Telegram sending, multi-chat support, config validation
- **signals.py**: RSI, MACD, 200-DMA, volume breakout, weekly multi-timeframe trend, setup generation
- **models.py**: Article, Catalyst, SwingSetup, SourceQuality, AnalysisReport integrity
- **pipeline.py**: Ingested-articles, history mapping, catalyst detection, setup generation
- **ingestion.py**: Screener price snapshots, exchange bulk/block deals, media news
- **main.py**: Pipeline entry point and config loading

Target: 85%+ line coverage on `src/scheme_intel`

## Coverage Report

After running tests with coverage:
1. Open `htmlcov/index.html` in a browser
2. Click on individual modules to see line-by-line coverage
3. Look for red lines (uncovered code)

Target: 85%+ code coverage

## CI/CD Integration

Tests run automatically on:
- Every push to `main` branch
- Every pull request
- Multiple Python versions (3.11, 3.12)

See `.github/workflows/test.yml` for workflow configuration.

## Common Issues

### ModuleNotFoundError: No module named 'scheme_intel'
**Solution**: `run_tests.py` sets the path automatically. Otherwise ensure `PYTHONPATH` includes the `src` directory:
```bash
export PYTHONPATH=src
python -m pytest tests/
```

### Tests fail with "connection error"
All HTTP calls are mocked with `unittest.mock`. `pytest-mock` is already listed in `requirements.txt` if you prefer the `mocker` fixture.

## Adding New Tests

### Test file naming
- Use `test_<module>.py` format
- Example: `test_analysis.py` for `analysis.py` module

### Test class naming
- Use `Test<Feature>` format
- Example: `TestCatalystClassification` for catalyst tests

### Test method naming
- Use `test_<scenario>` format
- Example: `test_classify_cabinet_approval`

### Using fixtures
Available fixtures from `conftest.py`:
- `sample_article`: Example Article instance
- `sample_catalyst`: Example Catalyst instance
- `sample_setup`: Example SwingSetup instance
- `config_dict`: Sample configuration dictionary

```python
def test_example(sample_article):
    assert sample_article.title is not None
```

## Performance Testing

### Slow tests
Mark slow tests for easy exclusion:
```python
@pytest.mark.slow
def test_fetch_large_feed():
    pass
```

Run excluding slow tests:
```bash
python -m pytest tests/ -v -m "not slow"
```
