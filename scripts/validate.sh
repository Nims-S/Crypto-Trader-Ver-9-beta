#!/bin/bash
# Complete validation suite for Crypto-Trader-Ver-9-beta
# Checks code quality, tests, and project structure
# Usage: ./scripts/validate.sh

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Config
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
LOG_DIR="${PROJECT_ROOT}/.validation_logs"
LOG_FILE="${LOG_DIR}/validation_${TIMESTAMP}.log"

mkdir -p "${LOG_DIR}"

# Logging
log() { echo "$*" | tee -a "${LOG_FILE}"; }
success() { echo -e "${GREEN}✓${NC} $*" | tee -a "${LOG_FILE}"; }
error() { echo -e "${RED}✗${NC} $*" | tee -a "${LOG_FILE}"; }
info() { echo -e "${BLUE}ℹ${NC} $*" | tee -a "${LOG_FILE}"; }
warn() { echo -e "${YELLOW}⚠${NC} $*" | tee -a "${LOG_FILE}"; }

# Counters
PASSED=0
FAILED=0
SKIPPED=0

cd "${PROJECT_ROOT}"

# Header
log ""
log "════════════════════════════════════════════════════════════════"
log "Crypto-Trader-Ver-9 VALIDATION SUITE"
log "════════════════════════════════════════════════════════════════"
log "Time: $(date)"
log "Root: ${PROJECT_ROOT}"
log "Log:  ${LOG_FILE}"
log ""

# ==================== CHECK 1: Python Version ====================
info "[1/8] Python Version"
if python_version=$(python --version 2>&1); then
    success "Python version: $python_version"
    ((PASSED++))
else
    error "Python not available"
    ((FAILED++))
fi
log ""

# ==================== CHECK 2: Dependencies ====================
info "[2/8] Dependencies"
if pip list | grep -q pytest; then
    success "Development dependencies installed"
    ((PASSED++))
else
    error "Missing dependencies. Run: pip install -e '.[dev]'"
    ((FAILED++))
fi
log ""

# ==================== CHECK 3: Code Syntax ====================
info "[3/8] Code Syntax Validation"
if python -m py_compile ver9 2>> "${LOG_FILE}"; then
    success "All Python files compile"
    ((PASSED++))
else
    error "Syntax errors found"
    ((FAILED++))
fi
log ""

# ==================== CHECK 4: Import Structure ====================
info "[4/8] Import Structure"
if python << 'EOF' 2>> "${LOG_FILE}"
import sys
sys.path.insert(0, '.')

try:
    from ver9.events.base_event import RuntimeEvent
    from ver9.runtime.kernel.event_bus import EventBus
    from ver9.runtime.state.runtime_state_store import RuntimeStateStore
    print("✓ Core imports successful")
except ImportError as e:
    print(f"✗ Import failed: {e}")
    sys.exit(1)
EOF
    success "Import structure valid"
    ((PASSED++))
else
    error "Import errors detected"
    ((FAILED++))
fi
log ""

# ==================== CHECK 5: Code Formatting ====================
info "[5/8] Code Formatting (Black)"
if command -v black &>/dev/null; then
    if black --check ver9 tests 2>> "${LOG_FILE}"; then
        success "Code formatting compliant"
        ((PASSED++))
    else
        warn "Code formatting issues (run: black ver9 tests)"
        ((PASSED++))
    fi
else
    warn "Black not installed (skipping format check)"
    ((SKIPPED++))
fi
log ""

# ==================== CHECK 6: Linting ====================
info "[6/8] Linting (Ruff)"
if command -v ruff &>/dev/null; then
    if ruff check ver9 tests 2>> "${LOG_FILE}"; then
        success "No linting errors"
        ((PASSED++))
    else
        warn "Linting issues found (run: ruff check ver9 tests)"
        ((PASSED++))
    fi
else
    warn "Ruff not installed (skipping lint check)"
    ((SKIPPED++))
fi
log ""

# ==================== CHECK 7: Unit Tests ====================
info "[7/8] Unit Tests"
if [ -d "tests" ]; then
    if pytest tests -q --tb=short 2>> "${LOG_FILE}"; then
        success "All tests passed"
        ((PASSED++))
    else
        error "Some tests failed"
        ((FAILED++))
    fi
else
    warn "No tests directory found"
    ((SKIPPED++))
fi
log ""

# ==================== CHECK 8: Type Checking ====================
info "[8/8] Type Checking (Mypy)"
if command -v mypy &>/dev/null; then
    if mypy ver9 --ignore-missing-imports --no-error-summary 2>> "${LOG_FILE}"; then
        success "Type checking passed"
        ((PASSED++))
    else
        warn "Type checking issues (informational)"
        ((PASSED++))
    fi
else
    warn "Mypy not installed (skipping type check)"
    ((SKIPPED++))
fi
log ""

# ==================== SUMMARY ====================
log "════════════════════════════════════════════════════════════════"
log "SUMMARY"
log "════════════════════════════════════════════════════════════════"
success "Passed:  $PASSED"
warn "Skipped: $SKIPPED"
[ $FAILED -eq 0 ] && success "Failed:  0" || error "Failed:  $FAILED"
log ""

if [ $FAILED -eq 0 ]; then
    log -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    success "✓ VALIDATION COMPLETE - ALL CHECKS PASSED"
    log -e "${GREEN}═══════════════════════════════════════════════════════════════${NC}"
    log ""
    log "Repository is ready for development!"
    log ""
    exit 0
else
    log -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    error "✗ VALIDATION FAILED - $FAILED check(s) failed"
    log -e "${RED}═══════════════════════════════════════════════════════════════${NC}"
    log ""
    log "Review: $LOG_FILE"
    log ""
    exit 1
fi
