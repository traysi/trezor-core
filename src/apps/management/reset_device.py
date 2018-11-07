from micropython import const
from ubinascii import hexlify

from trezor import config, ui, wire, workflow
from trezor.crypto import bip39, hashlib, random
from trezor.messages import ButtonRequestType, MessageType
from trezor.messages.ButtonRequest import ButtonRequest
from trezor.messages.EntropyRequest import EntropyRequest
from trezor.messages.Success import Success
from trezor.pin import pin_to_int
from trezor.ui.confirm import HoldToConfirmDialog
from trezor.ui.mnemonic import MnemonicKeyboard
from trezor.ui.scroll import Scrollpage, animate_swipe, paginate
from trezor.ui.text import Text
from trezor.utils import chunks, format_ordinal

from apps.common import storage
from apps.common.confirm import require_confirm
from apps.management.change_pin import request_pin_confirm

if __debug__:
    from apps import debug


async def reset_device(ctx, msg):
    # validate parameters and device state
    if msg.strength not in (128, 192, 256):
        raise wire.ProcessError("Invalid strength (has to be 128, 192 or 256 bits)")
    if msg.display_random and (msg.skip_backup or msg.no_backup):
        raise wire.ProcessError("Can't show internal entropy when backup is skipped")
    if storage.is_initialized():
        raise wire.UnexpectedMessage("Already initialized")

    text = Text("Create a new wallet", ui.ICON_RESET)
    text.normal("Do you really want to", "create a new wallet?", "")

    await require_confirm(ctx, text, code=ButtonRequestType.ResetDevice)

    # request new PIN
    if msg.pin_protection:
        newpin = await request_pin_confirm(ctx)
    else:
        newpin = ""

    # generate and display internal entropy
    internal_ent = random.bytes(32)
    if __debug__:
        debug.reset_internal_entropy = internal_ent
    if msg.display_random:
        await show_entropy(ctx, internal_ent)

    # request external entropy and compute mnemonic
    ent_ack = await ctx.call(EntropyRequest(), MessageType.EntropyAck)
    mnemonic = generate_mnemonic(msg.strength, internal_ent, ent_ack.entropy)

    if not msg.skip_backup and not msg.no_backup:
        # require confirmation of the mnemonic safety
        await show_warning(ctx)

        # show mnemonic and require confirmation of a random word
        while True:
            await show_mnemonic(ctx, mnemonic)
            if await check_mnemonic(ctx, mnemonic):
                break
            await show_wrong_entry(ctx)

    # write PIN into storage
    if not config.change_pin(pin_to_int(""), pin_to_int(newpin)):
        raise wire.ProcessError("Could not change PIN")

    # write settings and mnemonic into storage
    storage.load_settings(label=msg.label, use_passphrase=msg.passphrase_protection)
    storage.load_mnemonic(
        mnemonic=mnemonic, needs_backup=msg.skip_backup, no_backup=msg.no_backup
    )

    # show success message.  if we skipped backup, it's possible that homescreen
    # is still running, uninterrupted.  restart it to pick up new label.
    if not msg.skip_backup and not msg.no_backup:
        await show_success(ctx)
    else:
        workflow.restartdefault()

    return Success(message="Initialized")


def generate_mnemonic(strength: int, int_entropy: bytes, ext_entropy: bytes) -> bytes:
    ehash = hashlib.sha256()
    ehash.update(int_entropy)
    ehash.update(ext_entropy)
    entropy = ehash.digest()
    mnemonic = bip39.from_data(entropy[: strength // 8])
    return mnemonic


async def show_warning(ctx):
    text = Text("Backup your seed", ui.ICON_NOCOPY)
    text.normal(
        "Never make a digital",
        "copy of your recovery",
        "seed and never upload",
        "it online!",
    )
    await require_confirm(
        ctx, text, ButtonRequestType.ResetDevice, confirm="I understand", cancel=None
    )


async def show_wrong_entry(ctx):
    text = Text("Wrong entry!", ui.ICON_WRONG, icon_color=ui.RED)
    text.normal("You have entered", "wrong seed word.", "Please check again.")
    await require_confirm(
        ctx, text, ButtonRequestType.ResetDevice, confirm="Check again", cancel=None
    )


async def show_success(ctx):
    text = Text("Backup is done!", ui.ICON_CONFIRM, icon_color=ui.GREEN)
    text.normal(
        "Never make a digital",
        "copy of your recovery",
        "seed and never upload",
        "it online!",
    )
    await require_confirm(
        ctx, text, ButtonRequestType.ResetDevice, confirm="Finish setup", cancel=None
    )


async def show_entropy(ctx, entropy: bytes):
    entropy_str = hexlify(entropy).decode()
    lines = chunks(entropy_str, 16)
    text = Text("Internal entropy", ui.ICON_RESET)
    text.mono(*lines)
    await require_confirm(ctx, text, ButtonRequestType.ResetDevice)


async def show_mnemonic(ctx, mnemonic: str):
    await ctx.call(
        ButtonRequest(code=ButtonRequestType.ResetDevice), MessageType.ButtonAck
    )
    first_page = const(0)
    words_per_page = const(4)
    words = list(enumerate(mnemonic.split()))
    pages = list(chunks(words, words_per_page))
    paginator = paginate(show_mnemonic_page, len(pages), first_page, pages)
    await ctx.wait(paginator)


@ui.layout
async def show_mnemonic_page(page: int, page_count: int, pages: list):
    if __debug__:
        debug.reset_current_words = [word for _, word in pages[page]]

    lines = ["%2d. %s" % (wi + 1, word) for wi, word in pages[page]]
    text = Text("Recovery seed", ui.ICON_RESET)
    text.mono(*lines)
    content = Scrollpage(text, page, page_count)

    if page + 1 == page_count:
        await HoldToConfirmDialog(content)
    else:
        content.render()
        await animate_swipe()


async def check_mnemonic(ctx, mnemonic: str) -> bool:
    words = mnemonic.split()

    # check a word from the first half
    index = random.uniform(len(words) // 2)
    if not await check_word(ctx, words, index):
        return False

    # check a word from the second half
    index = random.uniform(len(words) // 2) + len(words) // 2
    if not await check_word(ctx, words, index):
        return False

    return True


@ui.layout
async def check_word(ctx, words: list, index: int):
    if __debug__:
        debug.reset_word_index = index

    keyboard = MnemonicKeyboard("Type the %s word:" % format_ordinal(index + 1))
    result = await ctx.wait(keyboard)
    return result == words[index]
