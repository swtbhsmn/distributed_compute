from distributed_compute.computations import execute, is_prime, prime_count, sum_squares


def test_sum_squares_uses_half_open_range() -> None:
    assert sum_squares(1, 5) == 1 + 4 + 9 + 16
    assert execute("sum_squares", 1, 5) == 30


def test_prime_count() -> None:
    assert is_prime(2)
    assert is_prime(97)
    assert not is_prime(1)
    assert not is_prime(100)
    assert prime_count(0, 20) == 8
    assert execute("prime_count", 0, 20) == 8


