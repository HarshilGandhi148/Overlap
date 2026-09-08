#!/bin/zsh
cd -- "${0:A:h}" || exit 1
if [[ ! -x .venv/bin/python ]]; then
  print "Run the Python setup steps in README.md first."
  read -r "reply?Press Return to close."
  exit 1
fi
.venv/bin/python run.py
if [[ $? -ne 0 ]]; then
  read -r "reply?Press Return to close."
fi
