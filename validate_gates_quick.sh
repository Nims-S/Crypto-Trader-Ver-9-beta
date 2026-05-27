#!/bin/bash
# Quick validation - Fast version of validate_gates.sh (excludes style/type checks)
# Usage: ./validate_gates_quick.sh
# Useful for rapid iteration during development

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════════${NC}"
echo -e "${BLUE}QUICK VALIDATION - Phase 5 Core Checks${NC}"
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════════${NC}"
echo ""

cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1

FAILED=0

echo -e "${BLUE}[1/6]${NC} Code Compilation..."
if python -m py_compile ver9; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ((FAILED++))
fi

echo -e "${BLUE}[2/6]${NC} Unit Tests..."
if pytest tests/phase1 tests/phase4 tests/phase5 -q; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ((FAILED++))
fi

echo -e "${BLUE}[3/6]${NC} Replay Correctness..."
if pytest tests/integration/test_replay_correctness.py -q; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ((FAILED++))
fi

echo -e "${BLUE}[4/6]${NC} Idempotency..."
if pytest tests/integration/test_duplicate_suppression.py -q; then
    echo -e "${GREEN}✓${NC}"
else
    echo -e "${RED}✗${NC}"
    ((FAILED++))
fi

echo -e "${BLUE}[5/6]${NC} Import Linter..."
if command -v import-linter &> /dev/null; then
    if import-linter --config .importlinter > /dev/null 2>&1; then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        ((FAILED++))
    fi
else
    echo -e "${BLUE}⊘ (skipped)${NC}"
fi

echo -e "${BLUE}[6/6]${NC} Configuration..."
if python << 'EOF'
import sys
sys.path.insert(0, '.')
from ver9.domain.events.execution import OrderSubmittedDomain
from ver9.persistence.event_journal import EventJournal
from ver9.execution.idempotency import IdempotencyLayer
EOF
    then
        echo -e "${GREEN}✓${NC}"
    else
        echo -e "${RED}✗${NC}"
        ((FAILED++))
fi

echo ""
echo -e "${BLUE}════════════════════════════════════════════════════════════════════════════════════${NC}"
if [ "${FAILED}" -eq 0 ]; then
    echo -e "${GREEN}✅ All core checks passed${NC}"
    echo -e "${GREEN}════════════════════════════════════════════════════════════════════════════════════${NC}"
    exit 0
else
    echo -e "${RED}❌ ${FAILED} check(s) failed${NC}"
    echo -e "${RED}════════════════════════════════════════════════════════════════════════════════════${NC}"
    exit 1
fi
