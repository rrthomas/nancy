"""
Nancy tests.
Copyright (c) Reuben Thomas 2024.
Released under the GPL version 3, or (at your option) any later version.
"""

import os
import sys
import socket
from pathlib import Path
from collections.abc import Iterator
from tempfile import TemporaryDirectory
from unittest import mock

import pytest
from pytest import CaptureFixture, LogCaptureFixture

from testutils import (
    passing_test,
    failing_test,
    passing_cli_test,
    failing_cli_test,
    check_links,
)
from nancy import main

if sys.version_info[:2] >= (3, 11): # pragma: no cover
    from contextlib import chdir
else: # pragma: no cover
    from contextlib import contextmanager

    @contextmanager
    def chdir(path: os.PathLike[str]) -> Iterator[None]:
        old_dir = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(old_dir)


tests_dir = Path(__file__).parent.resolve() / "test-files"


# Module tests
def test_whole_tree() -> None:
    with chdir(tests_dir):
        passing_test(["webpage-src"], "webpage-expected")
        check_links("webpage-expected", "index.html")


def test_part_tree() -> None:
    with chdir(tests_dir):
        passing_test(["webpage-src"], "webpage-expected/people", "people")
        check_links("webpage-expected/people", "index.html")


def test_two_trees() -> None:
    with chdir(tests_dir):
        passing_test(["mergetrees-src", "webpage-src"], "mergetrees-expected")
        check_links("mergetrees-expected", "index.html")


def test_nested_macro_invocations() -> None:
    with chdir(tests_dir):
        passing_test(["nested-macro-src"], "nested-macro-expected")


def test_failing_executable_test() -> None:
    with chdir(tests_dir):
        failing_test(
            [os.getcwd()], "returned non-zero exit status 1", "false.nancy.txt"
        )


def test_passing_executable_test() -> None:
    with chdir(tests_dir):
        passing_test([os.getcwd()], "true-expected.txt", "true.nancy.txt")


def test_executable_test() -> None:
    with chdir(tests_dir):
        passing_test(
            ["page-template-with-date-src"], "page-template-with-date-expected"
        )


def test_macros_not_expanded_in_command_line_arguments() -> None:
    with chdir(tests_dir):
        passing_test(["$path-src"], "$path-expected")


def test_paste_does_not_expand_macros() -> None:
    with chdir(tests_dir):
        passing_test(["paste-src"], "paste-expected")


def test_include_with_no_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        failing_test(
            [os.getcwd()],
            "$include expects at least one argument",
            "include-no-arg.nancy.txt",
        )


def test_paste_with_no_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        failing_test(
            [os.getcwd()],
            "$paste expects at least one argument",
            "paste-no-arg.nancy.txt",
        )


def test_escaping_a_macro_without_arguments() -> None:
    with chdir(tests_dir):
        passing_test(["escaped-path-src"], "escaped-path-expected")


def test_escaping_a_macro_with_arguments() -> None:
    with chdir(tests_dir):
        passing_test(["escaped-include-src"], "escaped-include-expected")


def test_cookbook_web_site_example() -> None:
    with chdir(tests_dir):
        passing_test(
            ["cookbook-example-website-src"], "cookbook-example-website-expected"
        )
        check_links("cookbook-example-website-expected", "index/index.html")


def test_expanding_a_file_with_relative_includes() -> None:
    with chdir(tests_dir):
        passing_test(
            [os.getcwd()],
            "file-root-relative-include-expected.txt",
            "file-root-relative-include.nancy.txt",
        )


def test_empty_input_path_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test([], "at least one input must be given")


def test_a_nonexistent_input_path_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test(["a"], "input 'a' does not exist")


def test_an_input_that_is_not_a_directory_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test(["random-text.txt"], "input 'random-text.txt' is not a directory")


def test_including_a_nonexistent_file_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test([os.getcwd()], "cannot find 'foo'", "missing-include.nancy.txt")


def test_calling_an_undefined_macro_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test([os.getcwd()], "no such macro '$foo'", "undefined-macro.nancy.txt")


def test_calling_an_undefined_single_letter_macro_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test(
            [os.getcwd()], "no such macro '$f'", "undefined-short-macro.nancy.txt"
        )


def test_a_macro_call_with_a_missing_close_brace_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test(
            [os.getcwd()], "missing close brace", "missing-close-brace.nancy.txt"
        )


def test_trying_to_output_multiple_files_to_stdout_causes_an_error() -> None:
    with chdir(tests_dir):
        failing_test(
            ["webpage-src"], "cannot output multiple files to stdout", None, "-"
        )


# CLI tests
def test_help_option_should_produce_output(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.type == SystemExit
    assert e.value.code == 0
    assert capsys.readouterr().out.find("A simple templating system.") != -1


# pylint: disable-next=invalid-name
def test_running_with_a_single_file_as_INPUT_PATH_should_work(
    capsys: CaptureFixture[str],
) -> None:
    with chdir(tests_dir):
        passing_cli_test(
            capsys,
            ["file-root-relative-include.nancy.txt"],
            "file-root-relative-include-expected.txt",
        )


def test_output_to_stdout_of_a_single_file_works(capsys: CaptureFixture[str]) -> None:
    with chdir(tests_dir):
        passing_cli_test(
            capsys,
            ["file-root-relative-include.nancy.txt"],
            "file-root-relative-include-expected.txt",
            "-",
        )


def test_copy_to_stdout_of_a_single_file_works(capsys: CaptureFixture[str]) -> None:
    with chdir(tests_dir):
        passing_cli_test(
            capsys,
            ["random-text.txt"],
            "random-text.txt",
            "-",
        )


def test_missing_command_line_argument_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    failing_cli_test(capsys, caplog, [], "the following arguments are required")


def test_invalid_command_line_argument_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    failing_cli_test(capsys, caplog, ["--foo", "a"], "unrecognized arguments: --foo")


# pylint: disable-next=invalid-name
def test_running_on_a_nonexistent_path_causes_an_error_DEBUG_coverage(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with mock.patch.dict(os.environ, {"DEBUG": "yes"}):
        failing_cli_test(capsys, caplog, ["a"], "input 'a' does not exist")


def test_running_on_something_not_a_file_or_directory_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        with TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, "foo")
            server.bind(temp_file)
            failing_cli_test(
                capsys,
                caplog,
                [f"--path={os.path.basename(temp_file)}", temp_dir],
                "is not a file or directory",
            )


def test_nonexistent_build_path_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        failing_cli_test(
            capsys,
            caplog,
            ["--path", "nonexistent", "webpage-src"],
            "matches no path in the inputs",
        )


def test_absolute_build_path_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        failing_cli_test(
            capsys,
            caplog,
            ["--path", "/nonexistent", "webpage-src"],
            "build path must be relative",
        )


def test_output_to_subdirectory_of_input_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        failing_cli_test(
            capsys,
            caplog,
            ["webpage-src"],
            "output cannot be in any input directory",
            "webpage-src/foo",
        )


# pylint: disable-next=invalid-name
def test_empty_INPUT_PATH_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    failing_cli_test(capsys, caplog, [""], "input path must not be empty")
