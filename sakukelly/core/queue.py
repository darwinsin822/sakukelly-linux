"""Navegación de reproducción: qué índice sigue o antecede al actual según
los modos aleatorio y repetir.

Es lógica pura (sin Qt, sin QMediaPlayer, sin base de datos): funciones de
(índice actual, total de filas, aleatorio, repetir) -> índice siguiente.
En el monolito original esta misma fórmula estaba escrita dos veces por
separado (en `_peek_next_local` y en `next()`); aquí queda en un solo sitio.

Deliberadamente NO incluye la cola "a continuación" (`self.queue` en la
ventana principal) ni el crossfade: esas partes siguen tocando directamente
QMediaPlayer, la base de datos y varios widgets a la vez (arte, indicador
"reproduciendo", reproductor de video), y separarlas de verdad requeriría
poder probar interactivamente el crossfade y el arrastrar-soltar de la cola
en una máquina real — algo que no es posible verificar en este entorno.
"""
import random


def next_index(current_index, total, shuffle, repeat, respect_repeat=True):
    """Índice que debería sonar después del actual.

    - Sin filas (`total<=0`): -1 (no hay nada que reproducir).
    - Si `respect_repeat` y repetir está activo (sin aleatorio): se repite
      la misma pista. Esto solo aplica cuando una canción termina de forma
      natural — el botón manual "Siguiente" SIEMPRE avanza, incluso con
      repetir activo (respect_repeat=False en ese caso), igual que en el
      reproductor original.
    - Aleatorio: un índice al azar entre todas las filas.
    - Caso normal: la siguiente fila, dando la vuelta al llegar al final.
    """
    if total <= 0:
        return -1
    if respect_repeat and repeat and not shuffle:
        return current_index
    if shuffle:
        return random.randrange(total)
    return (current_index + 1) % total


def prev_index(current_index, total):
    """Índice anterior al actual, dando la vuelta al llegar al principio.
    (El modo aleatorio no tiene "anterior" real — como en el reproductor
    original, retrocede secuencialmente igual que sin aleatorio)."""
    if total <= 0:
        return -1
    return (current_index - 1) % total
