"""
Roblox AutoDraw — ponto de entrada.

Uso:
    python main.py
"""

from __future__ import annotations

import sys


def main() -> int:
    from autodraw.screen import enable_dpi_awareness

    # Precisa vir antes de qualquer janela Tk, senão as coordenadas do mouse
    # ficam deslocadas em telas com escala diferente de 100%.
    enable_dpi_awareness()

    try:
        from autodraw.app import run
    except ImportError as exc:
        print("Dependência faltando:", exc)
        print("Instale tudo com:  pip install -r requirements.txt")
        return 1

    run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
