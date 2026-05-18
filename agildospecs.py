#!/usr/bin/env python3
"""Launcher do Agildo Specs (evita conflito com o pacote agildo_specs/)."""
from agildo_specs.app import main

if __name__ == "__main__":
    raise SystemExit(main())
