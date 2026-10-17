#!/bin/sh
# The whole offline suite, against build/ (the deployed bytes): the Python
# contract tests, then the payout fee guard and delivery check (node).
cd "$(dirname "$0")" && python3 ../tools/build.py --check && python3 -m unittest discover -p 'test_*.py' "$@" && node --test payout.test.mjs
