# Testing Guide for Scheme-Intel

## Quick Start

### Install test dependencies
```bash
pip install -r requirements.txt
```

### Run all tests
```bash
python -m pytest tests/ -v
```

### Run with coverage report
```bash
python run_tests.py
```

This generates an HTML report in `htmlcov/index.html`

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
├── test_sources.py          # Source fetching tests (15+ tests)
├── test_catalyst.py         # Catalyst classification tests (10+ tests)
├── test_signals.py          # Technical analysis tests (8+ tests)
└── test_notifier.py         # Telegram notification tests (10+ tests)
```

## Test Coverage

Current targets:
- **sources.py**: Feed fetching, page scanning, error handling, deduplication
- **catalyst.py**: Event classification, scoring, multi-company matching
- **notifier.py**: Telegram sending, multi-chat support, config validation
- **signals.py**: RSI calculation, setup generation, status determination
- **models.py**: Data model integrity and serialization

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
**Solution**: Ensure `PYTHONPATH` includes the `src` directory:
```bash
export PYTHONPATH=src
python -m pytest tests/
```

### Tests fail with "connection error"
**Solution**: Some tests mock HTTP requests. If they fail, check that `unittest.mock` is available:
```bash
pip install pytest-mock
```

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
