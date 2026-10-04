import std/os

let name = if paramCount() > 0: paramStr(1) else: "world"
echo "Hello, ", name, " from a Nim binary!"
