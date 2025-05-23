"""Nancy tests utility routines.

© Reuben Thomas <rrt@sc3d.org> 2023-2025.

Released under the GPL version 3, or (at your option) any later version.
"""

import contextlib
import difflib
import filecmp
import io
import os
import re
import subprocess
import sys
import tempfile
from contextlib import AbstractContextManager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional, Union

import pytest
from pytest import CaptureFixture, LogCaptureFixture

from nancy import Trees, main


def file_objects_equal(
    a: Union[os.PathLike[str], str], b: Union[os.PathLike[str], str]
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
    input_dirs: list[str],
    expected: str,
    build_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    process_hidden: bool = False,
    delete_ungenerated: bool = False,
    update_newer: bool = False,
) -> None:
    input_dir_paths = list(map(Path, input_dirs))
    ctx_mgr: Union[AbstractContextManager[None], TemporaryDirectory[str]]
    if output_dir is None:
        # TODO: when we can assume Python ≥ 3.12, use
        # `TemporaryDirectory(delete="DEBUG" not in os.environ)`
        ctx_mgr = tempfile.TemporaryDirectory()
        output_obj = os.path.join(ctx_mgr.name, "output")
    else:
        ctx_mgr = contextlib.nullcontext()
        output_obj = output_dir
    with ctx_mgr:
        trees = Trees(
            input_dir_paths,
            Path(output_obj),
            process_hidden,
            None if build_path is None else Path(build_path),
            delete_ungenerated,
            update_newer,
        )
        trees.process_path(trees.build)
        trees.__del__()
        assert file_objects_equal(output_obj, expected)


def failing_test(
    input_dirs: list[str],
    expected: str,
    build_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    process_hidden: bool = False,
    delete_ungenerated: bool = False,
    update_newer: bool = False,
) -> None:
    with TemporaryDirectory() as expected_dir:
        try:
            passing_test(
                input_dirs,
                expected_dir,
                build_path,
                output_dir,
                process_hidden,
                delete_ungenerated,
                update_newer,
            )
        except Exception as err:
            assert str(err).find(expected) != -1
            return
        raise ValueError("test passed unexpectedly")  # pragma: no cover


def passing_cli_test(
    capsys: CaptureFixture[str],
    args: list[str],
    expected: str,
    output_dir: Optional[str] = None,
) -> None:
    tmp_dir = None
    if output_dir is None:
        tmp_dir = TemporaryDirectory()
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
    args: list[str],
    expected: str,
    output_dir: Optional[str] = None,
) -> None:
    with pytest.raises(SystemExit) as e:
        passing_cli_test(capsys, args, "", output_dir)
    assert e.type is SystemExit
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


def tree_mtimes(dir: Path) -> dict[Path, int]:
    mtimes = {}
    for dirpath, _, filenames in os.walk(dir):
        for f in filenames:
            obj = Path(dirpath) / f
            if obj.is_file():
                mtimes[obj] = obj.stat().st_mtime
    return mtimes
