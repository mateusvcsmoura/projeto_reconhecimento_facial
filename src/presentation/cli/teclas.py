"""Codigos de tecla e cores da interface.

Modulo separado, sem cv2: assim o menu (testavel) e o viewer (que precisa
do OpenCV) compartilham as mesmas constantes sem que testar o menu exija
ter o OpenCV instalado.
"""

from __future__ import annotations

ESC = 27
ESPACO = 32
ENTER = 13

# BGR, a ordem usada pelo OpenCV.
VERDE = (0, 255, 0)
VERMELHO = (0, 0, 255)
BRANCO = (255, 255, 255)
