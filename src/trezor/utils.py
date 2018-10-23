import gc
import sys
from trezorutils import (  # noqa: F401
    EMULATOR,
    GITREV,
    MODEL,
    VERSION_MAJOR,
    VERSION_MINOR,
    VERSION_PATCH,
    halt,
    memcpy,
    set_mode_unprivileged,
)

if False:
    from typing import Iterable, Iterator, TypeVar, List


def unimport_begin() -> Iterable[str]:
    return set(sys.modules)


def unimport_end(mods: Iterable[str]) -> None:
    for mod in sys.modules:
        if mod not in mods:
            # remove reference from sys.modules
            del sys.modules[mod]
            # remove reference from the parent module
            i = mod.rfind(".")
            if i < 0:
                continue
            path = mod[:i]
            name = mod[i + 1 :]
            if path in sys.modules:
                delattr(sys.modules[path], name)
    # collect removed modules
    gc.collect()


def ensure(cond: bool, msg: str = None) -> None:
    if not cond:
        if msg is None:
            raise AssertionError()
        else:
            raise AssertionError(msg)


if False:
    Chunked = TypeVar("Chunked")


def chunks(items: List[Chunked], size: int) -> Iterator[List[Chunked]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def format_amount(amount: int, decimals: int) -> str:
    d = pow(10, decimals)
    s = ("%d.%0*d" % (amount // d, decimals, amount % d)).rstrip("0")
    if s.endswith("."):
        s = s[:-1]
    return s


def format_ordinal(number: int) -> str:
    return str(number) + {1: "st", 2: "nd", 3: "rd"}.get(
        4 if 10 <= number % 100 < 20 else number % 10, "th"
    )


class HashWriter:
    def __init__(self, hashfunc, *hashargs, **hashkwargs):
        self.ctx = hashfunc(*hashargs, **hashkwargs)
        self.buf = bytearray(1)  # used in append()

    def extend(self, buf: bytearray):
        self.ctx.update(buf)

    def append(self, b: int):
        self.buf[0] = b
        self.ctx.update(self.buf)

    def get_digest(self) -> bytes:
        return self.ctx.digest()
