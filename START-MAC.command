#!/bin/bash
cd "$(dirname "$0")"
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://www.python.org/downloads/ and run this again."
  read -r -p "Press Enter to close"; exit 1
fi
if [ ! -x ".venv/bin/python" ]; then
  echo "First run: installing what the program needs. This takes a few minutes, only once."
  python3 -m venv .venv
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/python -m pip install playwright pillow
  .venv/bin/python -m playwright install chromium
fi
echo
echo "Links are read from urls.txt, options from settings.txt"
echo "Press Enter to keep the value in [brackets]."
echo
.venv/bin/python mockup_maker.py --ask "$@"
read -r -p "Press Enter to close"
