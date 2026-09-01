from __future__ import annotations

import math


SUPPORTED_JOB_TYPES = ("sum_squares", "prime_count")


def sum_squares(start: int, end: int) -> int:
    """Return the sum of n^2 for the half-open range [start, end)."""
    return sum(number * number for number in range(start, end))


def is_prime(number: int) -> bool:
    if number < 2:
        return False
    if number == 2:
        return True
    if number % 2 == 0:
        return False
    limit = math.isqrt(number)
    return all(number % divisor for divisor in range(3, limit + 1, 2))


def prime_count(start: int, end: int) -> int:
    """Count primes in the half-open range [start, end)."""
    return sum(1 for number in range(start, end) if is_prime(number))


def execute(job_type: str, start: int, end: int) -> int:
    if job_type == "sum_squares":
        return sum_squares(start, end)
    if job_type == "prime_count":
        return prime_count(start, end)
    raise ValueError(f"Unsupported job type: {job_type}")

