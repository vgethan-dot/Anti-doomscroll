#!/usr/bin/env bash
# Lance AntiScroll sur Ubuntu (installe ce qu'il faut la première fois)
cd "$(dirname "$0")"
if ! python3 -c "import tkinter" 2>/dev/null; then
  echo "Installation de tkinter (mot de passe sudo demandé)..."
  sudo apt install -y python3-tk
fi
if [ ! -d .venv ]; then
  python3 -m venv .venv --system-site-packages
  .venv/bin/pip install -r requirements.txt
fi
exec .venv/bin/python antiscroll.py "$@"
