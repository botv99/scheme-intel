"""
Test runner script with coverage report.
"""
import subprocess
import sys

def run_tests_with_coverage():
    """Run all tests with coverage report."""
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--cov=src/scheme_intel",
        "--cov-report=html",
        "--cov-report=term-missing"
    ]
    
    result = subprocess.run(cmd)
    print("\n" + "="*60)
    print("Coverage report generated in htmlcov/index.html")
    print("="*60)
    return result.returncode


if __name__ == "__main__":
    sys.exit(run_tests_with_coverage())
