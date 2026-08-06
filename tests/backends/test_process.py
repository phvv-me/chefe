import os
import sys
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO, StringIO
from threading import Event

import pytest
from plumbum import local
from pytest_subprocess import FakeProcess

from chefe.backends import Process, Tool
from chefe.core import ChefeError, current_platform


class NotifyingDestination(StringIO):
    """A text destination that signals as soon as something writes its first chunk."""

    def __init__(self) -> None:
        super().__init__()
        self.written = Event()

    def write(self, text: str) -> int:
        """Retain ``text`` and wake the waiting assertion."""
        count = super().write(text)
        self.written.set()
        return count


def test_current_platform_shape() -> None:
    """The host platform reads as `<os>-<arch>` from the known os/arch maps."""
    osname, arch = current_platform().split("-", 1)
    assert osname in ("osx", "linux", "win")
    assert arch in ("64", "arm64", "aarch64")


def test_tool_default_scope_is_empty_and_available() -> None:
    """The base backend pins nothing and runs by default; pixi overrides scope."""
    assert Tool().scope() == () and Tool().available() is True


def test_tool_without_a_name_refuses_to_resolve_a_command() -> None:
    """A backend that names no binary says so, instead of failing deep inside plumbum."""
    with pytest.raises(ChefeError, match="names no command"):
        _ = Tool().command


def test_flags_translate_kwargs_to_cli_args() -> None:
    """Booleans become bare `--flag`, values become `--flag value`, falsy ones drop, `_`→`-`."""
    assert Tool.flags(pypi=True, cargo=False, npm=None) == ["--pypi"]
    assert Tool.flags(feature="serving", env="") == ["--feature", "serving"]
    assert Tool.flags(no_default=True) == ["--no-default"]


def test_tool_skips_when_unavailable() -> None:
    """A backend whose `available()` is False is a silent no-op, running nothing."""

    class Blocked(Tool):
        name = "nonexistent-binary"

        def available(self) -> bool:
            return False

    assert Blocked()("install") is None
    assert Blocked().exit_code("install") == 0


@pytest.mark.parametrize("code", [0, 1, 2, 42, 255])
def test_passthrough_preserves_exit_code(
    code: int, fp: FakeProcess, tool_paths: Mapping[str, str]
) -> None:
    """A command's exact exit code rides back out of `passthrough`, zero for a clean success."""
    fp.register([tool_paths["pixi"], fp.any()], returncode=code)
    assert Process.passthrough(local[tool_paths["pixi"]]["run"]) == code


def test_handover_gives_the_child_the_callers_own_streams() -> None:
    """An interactive command inherits the caller's stdout, where `stream` would hand it a pipe.

    The child compares the inode behind its own stdout with the caller's: equal means the very
    same open file, which is what lets a shell redraw the terminal it took over.
    """
    probe = "import os, sys; sys.exit(0 if os.fstat(1).st_ino == int(sys.argv[1]) else 3)"
    inode = str(os.fstat(1).st_ino)

    assert Process.handover(local[sys.executable]["-c", probe, inode]) == 0
    assert Process.stream(local[sys.executable]["-c", probe, inode]).returncode == 3


def test_output_relay_flushes_an_incomplete_multibyte_tail() -> None:
    """The live relay retains a replacement marker when a process ends mid-codepoint."""
    destination = StringIO()

    assert Process.relay(BytesIO(b"\xe2"), destination, "utf-8") == "�"
    assert destination.getvalue() == "�"


def test_output_relay_emits_a_short_protocol_message_without_filling_the_buffer() -> None:
    """A small response is relayed after one pipe read while the producing process stays open."""
    read_fd, write_fd = os.pipe()
    destination = NotifyingDestination()
    with os.fdopen(read_fd, "rb") as reader, ThreadPoolExecutor(max_workers=1) as executor:
        relayed = executor.submit(Process.relay, reader, destination, "utf-8")
        with os.fdopen(write_fd, "wb", buffering=0) as writer:
            writer.write(b'{"jsonrpc":"2.0"}\n')
            immediate = destination.written.wait(timeout=0.5)
        result = relayed.result(timeout=1)

    assert immediate is True
    assert result == destination.getvalue() == '{"jsonrpc":"2.0"}\n'
