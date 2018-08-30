from micropython import const

from trezor import ui
from trezor.messages import ButtonRequestType
from trezor.ui.text import Text

from apps.common import HARDENED
from apps.common.confirm import require_confirm


async def validate_path(ctx, validate_func, path: list, network: str = None):
    if not validate_func(path, network):
        await show_path_warning(ctx, path)


async def show_path_warning(ctx, path: list):
    text = Text("Confirm path", ui.ICON_WRONG, icon_color=ui.RED)
    text.normal("The path")
    text.mono(*_break_address_n_to_lines(path))
    text.normal("seems unusual.")
    text.normal("Are you sure?")
    return await require_confirm(
        ctx, text, code=ButtonRequestType.Other
    )  # todo what type?


def _break_address_n_to_lines(address_n: list) -> list:
    def path_item(i: int):
        if i & HARDENED:
            return str(i ^ HARDENED) + "'"
        else:
            return str(i)

    lines = []
    path_str = "m/" + "/".join([path_item(i) for i in address_n])

    per_line = const(17)
    while len(path_str) > per_line:
        i = path_str[:per_line].rfind("/")
        lines.append(path_str[:i])
        path_str = path_str[i:]
    lines.append(path_str)

    return lines
