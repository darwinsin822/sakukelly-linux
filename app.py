#!/usr/bin/env python3
"""Punto de entrada heredado.

El lanzador del paquete Debian (usr/bin/sakukelly) invoca este archivo
por compatibilidad con instalaciones existentes. Toda la lógica real vive
en el paquete sakukelly/ (sakukelly/main.py, sakukelly/ui/main_window.py).
"""
from sakukelly.main import main

if __name__ == "__main__":
    main()
