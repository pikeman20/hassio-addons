# Unit Tests

This directory contains **unit tests** for individual functions in the duplex scanning system.

## Structure

- `test_orientation.py` - Tests for orientation detection algorithms
- `test_deskew.py` - Tests for skew angle detection and correction
- `run_unit_tests.py` - Runner script that executes all unit tests

## Running Unit Tests

```bash
# Run all unit tests
python tests/run_unit_tests.py

# Or run individual test modules
python -m tests.test_orientation
python -m tests.test_deskew
```

## Integration Tests

For **end-to-end workflow tests** (scan_duplex, copy_duplex), see `integration_tests.py` in the project root.

```bash
# Run integration tests
python integration_tests.py
```

## Test Data

Unit tests use sample images from:
- `scan_inbox/scan_duplex/` - For orientation and deskew tests
- `scan_inbox/copy_duplex/` - For additional test scenarios
