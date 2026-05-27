# Validation & Testing Documentation

## Quick Start

### Install Development Dependencies

```bash
pip install -e ".[dev]"
```

### Run Full Validation Suite

```bash
bash scripts/validate.sh
```

### Quick Tests

```bash
# Run unit tests
pytest tests/ -v

# Run specific test file
pytest tests/test_structure.py -v

# Run with coverage
pytest tests/ --cov=ver9 --cov-report=html
```

## Validation Checks

The `scripts/validate.sh` script runs 8 comprehensive checks:

1. **Python Version** - Verifies Python 3.10+ is available
2. **Dependencies** - Confirms dev dependencies are installed
3. **Code Syntax** - Validates all Python files compile
4. **Import Structure** - Tests core module imports work
5. **Code Formatting** - Checks Black compliance
6. **Linting** - Runs Ruff linter
7. **Unit Tests** - Executes all pytest tests
8. **Type Checking** - Runs Mypy type validation

### Example Output

```
════════════════════════════════════════════════════════════════
Crypto-Trader-Ver-9 VALIDATION SUITE
════════════════════════════════════════════════════════════════
Time: 2026-05-27 17:15:00
Root: /path/to/project
Log:  .validation_logs/validation_20260527_171500.log

ℹ [1/8] Python Version
✓ Python version: Python 3.11.8

ℹ [2/8] Dependencies
✓ Development dependencies installed

ℹ [3/8] Code Syntax Validation
✓ All Python files compile

ℹ [4/8] Import Structure
✓ Import structure valid

ℹ [5/8] Code Formatting (Black)
✓ Code formatting compliant

ℹ [6/8] Linting (Ruff)
✓ No linting errors

ℹ [7/8] Unit Tests
✓ All tests passed

ℹ [8/8] Type Checking (Mypy)
✓ Type checking passed

════════════════════════════════════════════════════════════════
SUMMARY
════════════════════════════════════════════════════════════════
✓ Passed:  8
⚠ Skipped: 0
✓ Failed:  0

═══════════════════════════════════════════════════════════════
✓ VALIDATION COMPLETE - ALL CHECKS PASSED
═══════════════════════════════════════════════════════════════

Repository is ready for development!
```

## CI/CD Integration

### GitHub Actions Workflow

The `.github/workflows/validate.yml` file provides automated validation:

- **Trigger**: On push to `main` or `develop`, on PRs
- **Python Versions**: Tests against 3.10, 3.11, 3.12
- **Jobs**:
  - **Validate**: Full test suite with coverage
  - **Lint**: Code formatting and linting
  - **Security**: Bandit and Safety checks

### Running Workflows Locally

```bash
# Using act (GitHub Actions emulator)
act -j validate
```

## Development Workflow

### Pre-commit Hooks

Set up pre-commit hooks to validate before commits:

```bash
pre-commit install
pre-commit run --all-files
```

### Code Quality Tools

**Format code:**
```bash
black ver9 tests
```

**Check linting:**
```bash
ruff check ver9 tests
ruff check ver9 tests --show-fixes
```

**Type checking:**
```bash
mypy ver9 --ignore-missing-imports
```

**Run tests with coverage:**
```bash
pytest tests/ --cov=ver9 --cov-report=html
open htmlcov/index.html
```

## Test Structure

Tests are organized by concern:

```
tests/
├── test_structure.py      # Project structure tests
├── unit/                  # Unit tests
├── integration/           # Integration tests
└── conftest.py           # Pytest fixtures and config
```

### Writing Tests

```python
import pytest

class TestMyFeature:
    """Tests for my feature."""
    
    def test_something_works(self):
        """Test that something works."""
        assert True
    
    @pytest.mark.asyncio
    async def test_async_operation(self):
        """Test async operations."""
        result = await some_async_function()
        assert result is not None
```

## Coverage Requirements

The project requires minimum 70% code coverage:

```bash
pytest tests/ --cov=ver9 --cov-fail-under=70
```

## Troubleshooting

### Tests fail with import errors

```bash
# Reinstall in editable mode
pip install -e ".[dev]"
```

### Code formatting fails

```bash
# Auto-format code
black ver9 tests
```

### Type checking errors

```bash
# Check specific module
mypy ver9/runtime --show-error-codes

# Ignore missing stubs temporarily
mypy ver9 --ignore-missing-imports
```

### Validation script doesn't run

```bash
# Make script executable
chmod +x scripts/validate.sh

# Run with bash explicitly
bash scripts/validate.sh
```

## Continuous Integration Status

Check the status of CI/CD workflows:

- **GitHub Actions**: https://github.com/Nims-S/Crypto-Trader-Ver-9-beta/actions
- **Coverage**: Check codecov integration after PR

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Black Code Formatter](https://black.readthedocs.io/)
- [Ruff Linter](https://docs.astral.sh/ruff/)
- [Mypy Type Checker](https://mypy.readthedocs.io/)
- [Pre-commit Framework](https://pre-commit.com/)
