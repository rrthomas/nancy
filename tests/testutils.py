"""
Nancy tests utility routines.
Copyright (c) Reuben Thomas 2023-2024.
Released under the GPL version 3, or (at your option) any later version.
"""

import contextlib
import io
import os
import sys
import subprocess
import re
import filecmp
import difflib
import tempfile
from tempfile import TemporaryDirectory
from dataclasses import dataclass
from typing import AnyStr, Callable, List, Optional, Union, ContextManager

import pytest
from pytest import CaptureFixture, LogCaptureFixture

from nancy import expand, main


@dataclass
class Case:
    name: str
    args: List[str]
    expected: str
    path: Optional[str] = None
    error: Optional[int] = None
    extra_checks: Optional[Callable[[], None]] = None


def file_objects_equal(
    a: Union[AnyStr, os.PathLike[AnyStr]], b: Union[os.PathLike[AnyStr], AnyStr]
) -> bool:
    if os.path.isfile(a):
        with contextlib.ExitStack() as stack:
            out_fh = stack.enter_context(open(a, encoding="utf-8"))
            exp_fh = stack.enter_context(open(b, encoding="utf-8"))
            diff = list(
                difflib.unified_diff(
                    out_fh.readlines(), exp_fh.readlines(), str(a), str(b)
                )
            )
            if len(diff) > 0:  # pragma: no cover
                sys.stdout.writelines(diff)
                return False
            return True
    # See https://stackoverflow.com/questions/4187564
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        filecmp.dircmp(a, b).report_full_closure()
        match = re.search("Differing files|Only in", stdout.getvalue())
        if match is None:
            return True
    print(stdout.getvalue())  # pragma: no cover
    return False  # pragma: no cover


def passing_test(
    input_dirs: List[str],
    expected: str,
    build_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> None:
    ctx_mgr: Union[ContextManager[None], TemporaryDirectory[str]]
    if output_dir is None:
        ctx_mgr = tempfile.TemporaryDirectory()  # pylint ignore=consider-using-with
        output_obj = os.path.join(ctx_mgr.name, "output")
    else:
        ctx_mgr = contextlib.nullcontext()
        output_obj = output_dir
    with ctx_mgr:
        if build_path is not None:
            expand(input_dirs, output_obj, build_path)
        else:
            expand(input_dirs, output_obj)
        assert file_objects_equal(output_obj, expected)


def failing_test(
    input_dirs: List[str],
    expected: str,
    build_path: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> None:
    with TemporaryDirectory() as expected_dir:
        try:
            passing_test(input_dirs, expected_dir, build_path, output_dir)
        except Exception as err:  # pylint: disable=broad-exception-caught
            assert str(err).find(expected) != -1
            return
        raise ValueError("test passed unexpectedly")  # pragma: no cover


def passing_cli_test(
    capsys: CaptureFixture[str],
    args: List[str],
    expected: str,
    output_dir: Optional[str] = None,
) -> None:
    tmp_dir = None
    if output_dir is None:
        tmp_dir = TemporaryDirectory()  # pylint: disable=consider-using-with
        output_obj = os.path.join(tmp_dir.name, "output")
    else:
        output_obj = output_dir
    try:
        main(args + [output_obj])
        if tmp_dir is not None:
            assert filecmp.cmp(output_obj, expected)
        else:
            with open(expected, encoding="utf-8") as fh:
                expected_text = fh.read()
                assert capsys.readouterr().out == expected_text
    finally:
        if tmp_dir is not None:
            tmp_dir.cleanup()


def failing_cli_test(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
    args: List[str],
    expected: str,
    output_dir: Optional[str] = None,
) -> None:
    with pytest.raises(SystemExit) as e:
        passing_cli_test(capsys, args, "", output_dir)
    assert e.type == SystemExit
    assert e.value.code != 0
    err = capsys.readouterr().err
    log = caplog.messages
    match = err.find(expected) != -1 or any(msg.find(expected) != -1 for msg in log)
    if not match:  # pragma: no cover
        print(err)
        print(log)
    assert match


def check_links(root: str, start: str) -> None:
    subprocess.check_call(["linkchecker", os.path.join(root, start)])
