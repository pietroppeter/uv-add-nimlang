import nimpy

proc greet(name: string): string {.exportpy.} =
  "Hello, " & name & " from Nim!"

proc fib(n: int): int {.exportpy.} =
  var (a, b) = (0, 1)
  for _ in 0 ..< n:
    (a, b) = (b, a + b)
  a
