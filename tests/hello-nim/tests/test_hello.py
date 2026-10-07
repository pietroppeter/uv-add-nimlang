import hello_nim


def test_greet():
    assert hello_nim.greet("Python") == "Hello, Python from Nim!"


def test_fib():
    assert [hello_nim.fib(n) for n in range(8)] == [0, 1, 1, 2, 3, 5, 8, 13]


def test_roll():
    assert all(1 <= hello_nim.roll(6) <= 6 for _ in range(20))
