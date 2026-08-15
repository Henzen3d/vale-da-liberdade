#!/usr/bin/env python3
"""
MinHash leve — dedup semântica em Python puro.

Estratégia: shingles de caractere (3-grams) + função hash estável (MD5 truncado).
Mais robusto para títulos curtos e textos com pequenas variações.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata


def _normalize(text: str) -> str:
    text = (text or "").lower()
    # Normalização Unicode + remoção de acentos
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    # Permitir letras, números e espaços
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _char_shingles(text: str, n: int = 3) -> list[str]:
    text = _normalize(text)
    if len(text) < n:
        return [text]
    return [text[i:i + n] for i in range(len(text) - n + 1)]


class MinHasher:
    def __init__(self, n_grams: int = 3, n_hashes: int = 64, seed: int = 42):
        self.n_grams = n_grams
        self.n_hashes = n_hashes
        # bases distintas para cada função hash
        self._bases = [seed + i * 7919 for i in range(n_hashes)]

    def signature(self, text: str) -> tuple[int, ...]:
        shingles = _char_shingles(text, self.n_grams)
        if not shingles:
            return tuple([0] * self.n_hashes)

        sig = []
        for base in self._bases:
            best = None
            for s in shingles:
                h = int(hashlib.md5(f"{base}:{s}".encode("utf-8")).hexdigest()[:8], 16)
                if best is None or h < best:
                    best = h
            sig.append(best)
        return tuple(sig)


def jaccard_from_signatures(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    matches = sum(1 for x, y in zip(a, b) if x == y)
    return matches / len(a)


class DedupStore:
    """
    Mantém a janela de assinaturas aceitas e devolve se um novo texto
    é duplicata semântica.
    """

    def __init__(self, window: int = 50, threshold: float = 0.80):
        self.hasher = MinHasher(n_grams=3, n_hashes=64)
        self.window = window
        self.threshold = threshold
        self._accepted: list[tuple[int, ...]] = []

    def is_duplicate(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        sig = self.hasher.signature(text)
        if not any(sig):
            return False
        for prev in self._accepted[-self.window:]:
            if prev and jaccard_from_signatures(sig, prev) >= self.threshold:
                return True
        return False

    def add(self, text: str) -> None:
        """Registra um texto aceito na janela de dedup (não consulta)."""
        if not text or not text.strip():
            return
        sig = self.hasher.signature(text)
        if not any(sig):
            return
        self._accepted.append(sig)
        if len(self._accepted) > self.window * 2:
            self._accepted = self._accepted[-self.window:]
