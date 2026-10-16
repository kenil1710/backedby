#!/bin/sh
# The whole offline suite, against build/ (the deployed bytes).
cd "$(dirname "$0")" && python3 ../tools/build.py --check && python3 -m unittest discover -p 'test_*.py' "$@"
