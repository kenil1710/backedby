#!/bin/sh
# The whole offline suite, against build/ (the deployed bytes): the Python
# contract, rule, attack and meaning tests, then the payout fee guard and
# delivery check and the keeper suite (node).
cd "$(dirname "$0")" && python3 ../tools/build.py --check && python3 -m unittest discover -p 'test_*.py' "$@" && node --test payout.test.mjs keeper.test.mjs
