"""Nancy tests.

© Reuben Thomas <rrt@sc3d.org> 2024-2025.

Released under the GPL version 3, or (at your option) any later version.
"""

import os
import shutil
import socket
import stat
from contextlib import chdir  # pyright: ignore
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import pytest
from pytest import CaptureFixture, LogCaptureFixture
from testutils import (
    check_links,
    failing_cli_test,
    failing_test,
    passing_cli_test,
    passing_test,
    tree_mtimes,
)

from nancy import main


tests_dir = Path(__file__).parent.resolve() / "test-files"


# Module tests
async def test_whole_tree() -> None:
    with chdir(tests_dir):
        await passing_test(["webpage-src"], "webpage-expected")
        check_links("webpage-expected", "index.html")


async def test_part_tree() -> None:
    with chdir(tests_dir):
        await passing_test(["webpage-src"], "webpage-expected/people", "people")
        check_links("webpage-expected/people", "index.html")


async def test_two_trees() -> None:
    with chdir(tests_dir):
        await passing_test(["mergetrees-src", "webpage-src"], "mergetrees-expected")
        check_links("mergetrees-expected", "index.html")


async def test_override_symink() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["overriding-symlink", "override-symlink"], "override-symlink-expected"
        )


async def test_update_with_no_existing_output() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["cookbook-example-website-src"],
            "cookbook-example-website-expected",
            None,
            None,
            False,
            False,
            True,
        )
        check_links("cookbook-example-website-expected", "index/index.html")


async def test_update_with_existing_input() -> None:
    # Create temporary directory to copy initial files into
    with TemporaryDirectory() as tmp_dir:
        with chdir(tests_dir):
            shutil.copytree(
                "webpage-expected",
                tmp_dir,
                dirs_exist_ok=True,
                copy_function=shutil.copy,
            )
            orig_mtimes = tree_mtimes(Path(tmp_dir))
            await passing_test(
                ["webpage-src"],
                "webpage-expected",
                None,
                tmp_dir,
                False,
                False,
                True,
            )
            new_mtimes = tree_mtimes(Path(tmp_dir))
            for file, mtime in orig_mtimes.items():
                assert mtime == new_mtimes[file]


async def test_update_overwriting_some_input() -> None:
    # Create temporary directory to copy initial files into
    with TemporaryDirectory() as tmp_dir:
        with chdir(tests_dir):
            # Copy files without preserving time stamps
            shutil.copytree(
                "webpage-expected",
                tmp_dir,
                dirs_exist_ok=True,
                copy_function=shutil.copy,
            )
            updating_path = Path(tmp_dir) / "people" / "index.html"
            # Set one file's mtime to zero, to make it out of date
            os.utime(updating_path, times=(0, 0))
            orig_mtimes = tree_mtimes(Path(tmp_dir))
            await passing_test(
                ["webpage-src"],
                "webpage-expected",
                None,
                tmp_dir,
                False,
                False,
                True,
            )
            new_mtimes = tree_mtimes(Path(tmp_dir))
            # Check file that should have been updated was in fact updated
            assert orig_mtimes[updating_path] < new_mtimes[updating_path]
            # Remove time stamps for regenerated file before checking the rest
            del orig_mtimes[updating_path]
            del new_mtimes[updating_path]
            for file, mtime in orig_mtimes.items():
                assert mtime == new_mtimes[file]


async def test_env_vars() -> None:
    with chdir(tests_dir):
        await passing_test(["env-vars-src", "webpage-src"], "env-vars-expected")


async def test_nested_macro_invocations() -> None:
    with chdir(tests_dir):
        await passing_test(["nested-macro-src"], "nested-macro-expected")


async def test_expand_of_run_output() -> None:
    with chdir(tests_dir):
        await passing_test(["expand-run-src"], "expand-run-expected")


async def test_nonexistent_executable_test() -> None:
    with chdir(tests_dir):
        await failing_test([os.getcwd()], "cannot find program 'foo'", "foo.nancy.txt")


async def test_passing_executable_test() -> None:
    with chdir(tests_dir):
        await passing_test([os.getcwd()], "true-expected.txt", "true.nancy.txt")


async def test_executable_test() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["page-template-with-date-src"], "page-template-with-date-expected"
        )


async def test_executable_in_cwd_test() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["."], "executable-in-cwd-expected.txt", "executable-in-cwd.nancy.txt"
        )


async def test_hidden_files_are_ignored() -> None:
    # Create empty directory to use as expected test result, as we cannot
    # store an empty directory in git.
    with TemporaryDirectory() as empty_dir:
        with chdir(tests_dir):
            await passing_test(["hidden-files"], empty_dir)


async def test_hidden_files_can_be_processed() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["hidden-files"],
            "hidden-files",
            None,
            None,
            True,
        )


async def test_macros_not_expanded_in_command_line_arguments() -> None:
    with chdir(tests_dir):
        await passing_test(["$path-src"], "$path-expected")


async def test_path_in_filename() -> None:
    with chdir(tests_dir):
        await passing_test(["path-in-filename-src"], "path-in-filename-expected")


async def test_outputpath_in_filename() -> None:
    with chdir(tests_dir):
        await failing_test(
            ["outputpath-in-filename-src"],
            "$outputpath is not available while expanding the filename",
        )


async def test_copy_suffix() -> None:
    # Create temporary directory for output dir
    with TemporaryDirectory() as tmp_dir:
        with chdir(tests_dir):
            await passing_test(["copy-src"], "copy-expected", None, tmp_dir)
            # Check permissions on executable file in result.
            stats = os.stat(os.path.join(tmp_dir, "test.in"))
            assert stats.st_mode & stat.S_IXUSR != 0


async def test_update_copy_suffix() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["copy-src"], "copy-expected", None, None, False, False, True
        )


async def test_delete_ungenerated() -> None:
    # Create temporary directory to copy initial files into
    with TemporaryDirectory() as tmp_dir:
        with chdir(tests_dir):
            shutil.copytree("webpage-src", tmp_dir, dirs_exist_ok=True)
            await passing_test(
                ["delete-ungenerated-src"],
                "delete-ungenerated-expected",
                None,
                tmp_dir,
                False,
                True,
            )


# Test that when we don't set `delete_ungenerated` files in input are retained.
async def test_not_delete_ungenerated() -> None:
    # Create temporary directory to copy initial files into
    with TemporaryDirectory() as tmp_dir:
        with chdir(tests_dir):
            shutil.copytree("webpage-src", tmp_dir, dirs_exist_ok=True)
            await passing_test(["copy-src"], "copy-no-delete-expected", None, tmp_dir)


async def test_paste_does_not_expand_macros() -> None:
    with chdir(tests_dir):
        await passing_test(["paste-src"], "paste-expected")


async def test_path_with_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$path does not take arguments",
            "path-arg.nancy.txt",
        )


async def test_path_with_input_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$path does not take an input",
            "path-input.nancy.txt",
        )


async def test_outputpath_with_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$outputpath does not take arguments",
            "outputpath-arg.nancy.txt",
        )


async def test_outputpath_with_input_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$outputpath does not take an input",
            "outputpath-input.nancy.txt",
        )


async def test_include_with_no_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$include needs exactly one argument",
            "include-no-arg.nancy.txt",
        )


async def test_include_with_input_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$include does not take an input",
            "include-input.nancy.txt",
        )


async def test_paste_with_no_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$paste needs exactly one argument",
            "paste-no-arg.nancy.txt",
        )


async def test_paste_with_input_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$paste does not take an input",
            "paste-input.nancy.txt",
        )


async def test_paste_with_too_many_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$paste needs exactly one argument",
            "paste-too-many-args.nancy.txt",
        )


async def test_expand_with_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$expand does not take arguments",
            "expand-arguments.nancy.txt",
        )


async def test_expand_without_input_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$expand takes an input",
            "expand-no-input.nancy.txt",
        )


async def test_run_with_no_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$run needs at least one argument",
            "run-no-arg.nancy.txt",
        )


async def test_update_run_with_no_arguments_gives_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()],
            "$run needs at least one argument",
            "run-no-arg.nancy.txt",
            None,
            False,
            False,
            True,
        )


async def test_escaping_a_macro_without_arguments() -> None:
    with chdir(tests_dir):
        await passing_test(["escaped-path-src"], "escaped-path-expected")


async def test_escaping_a_macro_with_arguments() -> None:
    with chdir(tests_dir):
        await passing_test(["escaped-include-src"], "escaped-include-expected")


async def test_cookbook_web_site_example() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["cookbook-example-website-src"], "cookbook-example-website-expected"
        )
        check_links("cookbook-example-website-expected", "index/index.html")


async def test_expanding_a_file_with_relative_includes() -> None:
    with chdir(tests_dir):
        await passing_test(
            [os.getcwd()],
            "file-root-relative-include-expected.txt",
            "file-root-relative-include.nancy.txt",
        )


async def test_nested_argument_in_comma_list_works() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["nested-argument-in-comma-list-src"],
            "nested-argument-in-comma-list-expected",
        )


async def test_expanding_macros_in_file_names() -> None:
    with chdir(tests_dir):
        await passing_test(
            ["expanding-macros-in-file-names-src"],
            "expanding-macros-in-file-names-expected",
        )


async def test_run_with_input() -> None:
    with chdir(tests_dir):
        await passing_test(
            [os.getcwd()],
            "lines-expected.txt",
            "filter.nancy.txt",
        )


async def test_run_with_input_containing_commas() -> None:
    with chdir(tests_dir):
        await passing_test(
            [os.getcwd()],
            "run-input-with-commas-expected.txt",
            "run-input-with-commas.nancy.txt",
        )


async def test_empty_input_path_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test([], "at least one input must be given")


async def test_a_nonexistent_input_path_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(["a"], "input 'a' does not exist")


async def test_an_input_that_is_not_a_directory_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            ["random-text.txt"], "input 'random-text.txt' is not a directory"
        )


async def test_including_a_nonexistent_file_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()], "cannot find 'foo'", "missing-include.nancy.txt"
        )


async def test_calling_an_undefined_macro_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()], "no such macro '$foo'", "undefined-macro.nancy.txt"
        )


async def test_calling_an_undefined_single_letter_macro_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            [os.getcwd()], "no such macro '$f'", "undefined-short-macro.nancy.txt"
        )


async def test_a_macro_call_with_a_missing_close_brace_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test([os.getcwd()], "missing }", "missing-close-brace.nancy.txt")


async def test_a_macro_call_with_mismatched_heterogeneous_brackets_causes_correct_error() -> (
    None
):
    with chdir(tests_dir):
        await failing_test([os.getcwd()], "missing )", "missing-close-paren.nancy.txt")


async def test_trying_to_output_multiple_files_to_stdout_causes_an_error() -> None:
    with chdir(tests_dir):
        await failing_test(
            ["webpage-src"], "cannot output multiple files to stdout", None, "-"
        )


# CLI tests
def test_help_option_should_produce_output(capsys: CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.type is SystemExit
    assert e.value.code == 0
    assert capsys.readouterr().out.find("A simple templating system.") != -1


async def test_running_with_a_single_file_as_INPUT_PATH_should_work(
    capsys: CaptureFixture[str],
) -> None:
    with chdir(tests_dir):
        await passing_cli_test(
            capsys,
            ["file-root-relative-include.nancy.txt"],
            "file-root-relative-include-expected.txt",
        )


async def test_output_to_stdout_of_a_single_file_works(
    capsys: CaptureFixture[str],
) -> None:
    with chdir(tests_dir):
        await passing_cli_test(
            capsys,
            ["file-root-relative-include.nancy.txt"],
            "file-root-relative-include-expected.txt",
            "-",
        )


async def test_copy_to_stdout_of_a_single_file_works(
    capsys: CaptureFixture[str],
) -> None:
    with chdir(tests_dir):
        await passing_cli_test(
            capsys,
            ["random-text.txt"],
            "random-text.txt",
            "-",
        )


async def test_missing_command_line_argument_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    await failing_cli_test(capsys, caplog, [], "the following arguments are required")


async def test_invalid_command_line_argument_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    await failing_cli_test(
        capsys, caplog, ["--foo", "a"], "unrecognized arguments: --foo"
    )


async def test_failing_executable_test(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        await failing_cli_test(capsys, caplog, ["false.nancy.txt"], "Error code 1")


async def test_failing_executable_error_message_test(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        await failing_cli_test(
            capsys,
            caplog,
            ["fail-with-error.nancy.txt"],
            "oh no!",
        )


async def test_running_on_a_nonexistent_path_causes_an_error_DEBUG_coverage(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with mock.patch.dict(os.environ, {"DEBUG": "yes"}):
        await failing_cli_test(capsys, caplog, ["a"], "input 'a' does not exist")


async def test_running_on_something_not_a_file_or_directory_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        with TemporaryDirectory() as temp_dir:
            temp_file = os.path.join(temp_dir, "foo")
            server.bind(temp_file)
            await failing_cli_test(
                capsys,
                caplog,
                [f"--path={os.path.basename(temp_file)}", temp_dir],
                "is not a file or directory",
            )


async def test_nonexistent_build_path_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        await failing_cli_test(
            capsys,
            caplog,
            ["--path", "nonexistent", "webpage-src"],
            "matches no path in the inputs",
        )


async def test_absolute_build_path_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    with chdir(tests_dir):
        await failing_cli_test(
            capsys,
            caplog,
            ["--path", "/nonexistent", "webpage-src"],
            "build path must be relative",
        )


async def test_empty_INPUT_PATH_causes_an_error(
    capsys: CaptureFixture[str],
    caplog: LogCaptureFixture,
) -> None:
    await failing_cli_test(capsys, caplog, [""], "input path must not be empty")
