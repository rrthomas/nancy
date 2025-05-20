# © Reuben Thomas <rrt@sc3d.org> 2024-2025
# Released under the GPL version 3, or (at your option) any later version.

import argparse
import importlib.metadata
import logging
import os
import re
import shutil
import subprocess
import sys
import warnings
from logging import debug
from pathlib import Path
from typing import Callable, Optional

from .warnings_util import die, simple_warning


VERSION = importlib.metadata.version("nancy")

COPY_REGEX = re.compile(r"\.copy(?=\.|$)")
TEMPLATE_REGEX = re.compile(r"\.nancy(?=\.[^.]+$|$)")
INPUT_REGEX = re.compile(r"\.in(?=\.[^.]+$|$)")

MACRO_REGEX = re.compile(rb"(\\?)\$([^\W\d_]\w*)")


def strip_final_newline(s: bytes) -> bytes:
    return re.sub(b"\n$", b"", s)


def parse_arguments(
    text: bytes, arg_start: int, initial_closing: int
) -> tuple[list[bytes], int]:
    """Parse macro arguments.

    Parse macro arguments from `text[arg_start + 1:]` until the first
    unpaired occurrence of `initial_closing`.

    Args:
        text (bytes): the string to parse
        arg_start (int): the start position
        initial_closing (int): the ASCII code of the closing bracket

    Returns:
        tuple[list[bytes], int]:
        - list of arguments
        - position within `text` of the character after closing delimiter
    """
    args = []
    closing = [initial_closing]  # Stack of expected close brackets
    next_index = arg_start + 1
    while next_index < len(text):
        if text[next_index] == closing[-1]:
            closing.pop()
            if len(closing) == 0:
                args.append(text[arg_start + 1 : next_index])
                break
        elif text[next_index] in {ord(b"("), ord(b"{")}:
            closing.append(ord(b")") if text[next_index] == ord(b"(") else ord(b"}"))
        elif (
            len(closing) == 1
            and text[next_index] == ord(b",")
            and text[next_index - 1] != ord(b"\\")
        ):
            args.append(text[arg_start + 1 : next_index])
            arg_start = next_index
        next_index += 1
    if next_index == len(text):
        raise ValueError(f"missing {chr(closing[-1])}")
    return args, next_index + 1


def command_to_str(
    name: bytes,
    args: Optional[list[bytes]],
    input: Optional[bytes],
) -> bytes:
    """Reconstitute a macro call from its parsed form."""
    args_string = b"" if args is None else b"(" + b",".join(args) + b")"
    input_string = b"" if input is None else b"{" + input + b"}"
    return b"$" + name + args_string + input_string


def filter_bytes(
    input: Optional[bytes], exe_path: Path, exe_args: list[bytes]
) -> bytes:
    """Run an external command passing `input` on stdin.

    Args:
        input (Optional[bytes]): passed to `stdin`
        exe_path (Path): `Path` of the command to run
        exe_args (list[bytes]): arguments to the command

    Returns:
        bytes: stdout of the command
    """
    debug(f"Running {exe_path} {b' '.join(exe_args)}")
    try:
        res = subprocess.run(
            [exe_path.resolve(strict=True)] + exe_args,
            capture_output=True,
            check=True,
            input=input,
        )
        return res.stdout
    except subprocess.CalledProcessError as err:
        if err.stderr is not None:
            print(err.stderr.decode("iso-8859-1"), file=sys.stderr)
        die(f"Error code {err.returncode} running: {' '.join(map(str, err.cmd))}")


class Tree:
    """The state that is constant for a whole invocation of Nancy.

    Fields:
        input (Path): the `Path` of the input directory
        output (Path): the `Path` of the output directory
        build (Path): the subtree of `input` to process. Defaults to the whole
            tree.
        process_hidden (bool): `True` to process hidden files (those whose
            names begin with ".")
        delete_ungenerated (bool): `True` to delete files we do not generate
        update_newer (bool): Used when updating an existing output tree;
            files will only be updated if their macro arguments are newer than
            any current output file. Note this does not take into account macro
            invocations output by scripts.
        extant_files (dict[Path, os.stat_result]): the files in the output tree
            when we start (only set when `delete_ungenerated` is true)
        output_files (set[Path]): the files we write
    """

    input: Path
    output: Path
    build: Path
    process_hidden: bool
    delete_ungenerated: bool
    update_newer: bool
    extant_files: dict[Path, os.stat_result]
    output_files: set[Path]

    def __init__(
        self,
        input: Path,
        output: Path,
        process_hidden: bool,
        build: Optional[Path] = None,
        delete_ungenerated: bool = False,
        update_newer: bool = False,
    ):
        self.delete_ungenerated = delete_ungenerated
        self.process_hidden = process_hidden
        self.update_newer = update_newer
        if not input.exists():
            raise ValueError(f"input '{input}' does not exist")
        if not input.is_dir():
            raise ValueError(f"input '{input}' is not a directory")
        self.input = input
        self.output = output
        if build is None:
            build = Path()
        if build.is_absolute():
            raise ValueError("build path must be relative")
        self.build = build
        self.extant_files = {}
        self.output_files = set()
        if delete_ungenerated or update_newer:
            self.find_existing_files()

    def __del__(self):
        if self.delete_ungenerated:
            self.delete_ungenerated_files()
            # Prevent the destructor running again
            self.delete_ungenerated = False

    def find_object(self, obj: Path) -> Optional[Path]:
        """Returns `self.input / obj` or `None`."""
        debug(f"find_object {obj} {self.input}")
        if (self.input / obj).exists():
            return self.input / obj
        return None

    def _check_output_newer(self, inputs: list[Path], output: Path) -> bool:
        if not output.exists():
            return False
        output_mtime = output.stat().st_mtime
        return all(i.stat().st_mtime <= output_mtime for i in inputs)

    def process_file(self, obj: Path, only_newer: bool) -> None:
        """Expand, copy or ignore a file.

        Args:
            obj (Path): the `tree.input`-relative `Path`
            only_newer (bool): `True` means only update the file if a
                dependency is newer than any current output file.
        """
        expand = Expand(RunMacros, self, obj)
        debug(f"Processing file '{expand.input_file()}'")
        if only_newer:
            inputs: list[Path] = []
            if re.search(COPY_REGEX, expand.input_file().name):
                inputs.append(expand.input_file())
            elif re.search(TEMPLATE_REGEX, expand.input_file().name):
                _, include_inputs = Expand(Macros, self, obj).include(
                    expand.input_file()
                )
                inputs += include_inputs
            elif not re.search(INPUT_REGEX, expand.input_file().name):
                inputs.append(expand.input_file())
            debug(f"Checking inputs {inputs} against output {expand.output_file()}")
            if self._check_output_newer(inputs, expand.output_file()):
                debug("Not updating")
                return
            debug("Updating")
        os.makedirs(expand.output_file().parent, exist_ok=True)
        if re.search(COPY_REGEX, expand.input_file().name):
            expand.copy_file()
        elif re.search(TEMPLATE_REGEX, expand.input_file().name):
            debug(f"Expanding '{expand.path}' to '{expand.output_file()}'")
            output, _ = expand.include(expand.input_file())
            if expand.tree.output == Path("-"):
                sys.stdout.buffer.write(output)
            else:
                with open(expand.output_file(), "wb") as fh:
                    fh.write(output)
                expand.tree.output_files.add(expand.output_file())
        elif not re.search(INPUT_REGEX, expand.input_file().name):
            expand.copy_file()

    def process_path(self, obj: Path) -> None:
        """Recursively scan `obj` and pass every file to `process_file`.

        Args:
            obj (Path): the `input`-relative `Path` to scan.
        """
        if self.find_object(obj) is None:
            raise ValueError(f"'{obj}' matches no path in the input")
        if (self.input / obj).is_dir():
            if self.output == Path("-"):
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            output_dir = Expand(RunMacros, self, obj).output_file()
            os.makedirs(output_dir, exist_ok=True)
            for child in os.listdir(self.input / obj):
                if child[0] != "." or self.process_hidden:
                    self.process_path(obj / child)
        elif (self.input / obj).is_file():
            self.process_file(obj, self.update_newer)
        else:
            raise ValueError(f"'{obj}' is not a file or directory")

    def find_existing_files(self) -> None:
        for dirpath, _, filenames in os.walk(self.output):
            parent = Path(dirpath)
            for f in filenames:
                child = parent / f
                self.extant_files[child] = child.stat()

    def delete_ungenerated_files(self) -> None:
        for path in set(self.extant_files) - self.output_files:
            os.remove(path)

        # Now remove empty directories
        for dirpath, _, filenames in os.walk(self.output, topdown=False):
            if len(filenames) == 0:
                try:
                    os.rmdir(dirpath)
                except OSError:
                    pass  # The directory contained other (non-empty) directories.


# TODO: Use type statement with Python 3.12
Expansion = tuple[bytes, set[Path]]


class Expand:
    """`Path`s related to the file being expanded.

    Fields:
        tree (Tree):
        path (Path): the `tree.input`-relative `Path`
    """

    tree: Tree
    path: Path

    # The output file relative to `tree.output`.
    # `None` while the filename is being expanded.
    _output_path: Optional[Path]

    # _stack is a list of `Path`s which are currently being `$include`d.
    # This is used to avoid infinite loops.
    _stack: list[Path]

    def __init__(
        self,
        macrosClass: "type[Macros]",
        tree: Tree,
        path: Path,
    ):
        self.tree = tree
        self.path = path
        self._output_path = None
        self._stack = []
        self._macros = macrosClass(self)

        # Recompute `_output_path` by expanding `path`.
        output_path = self.path.relative_to(self.tree.build)
        if output_path.name != "":
            if re.search(COPY_REGEX, output_path.name):
                output_path = output_path.with_name(
                    output_path.name.replace(".copy", "", 1)
                )
            else:
                output_path = output_path.with_name(
                    re.sub(TEMPLATE_REGEX, "", output_path.name)
                )
            # Discard computed inputs when expanding filenames.
            output, _ = self.expand(bytes(output_path))
            output_path = os.fsdecode(output)
        self._output_path = Path(output_path)

    def input_file(self):
        """Returns the input `Path`."""
        return self.tree.input / self.path

    def output_path(self):
        """Returns the relative output `Path` for the current file.

        Raises an error if called while the filename is being expanded.
        """
        if self._output_path is None:
            raise ValueError(
                "$outputpath is not available while expanding the filename"
            )
        return self._output_path

    def output_file(self):
        """Returns the (computed) output `Path`.

        Raises an error if called while the filename is being expanded.
        """
        return self.tree.output / self.output_path()

    def find_on_path(self, start_path: Path, file: Path) -> Optional[Path]:
        """Search for file starting at the given path.

        Args:
            start_path (Path): `input`-relative `Path` to search up from
            file (Path): the `Path` to look for.

        Returns:
            Optional[Path]: `ancestor/file` where `ancestor` is the longest
                possible prefix of `start_path` satisfying:
                - `ancestor/file` exists and is a file
                - not in `self._stack`
                otherwise `None`.
        """
        debug(f"Searching for '{file}' on {start_path}")
        norm_file = Path(os.path.normpath(file))
        for parent in (start_path / "_").parents:
            obj = self.tree.find_object(parent / norm_file)
            if obj is not None and obj.is_file() and obj not in self._stack:
                debug(f"Found '{obj}'")
                return obj
        return None

    def file_arg(self, arg: bytes, exe=False) -> Path:
        """Find a file with the given name, or raise an error.

        The input tree is searched first. If no file is found there, and `exe`,
        the system `PATH` is searched for an executable file.

        Args:
            arg (bytes): the name to search for.
            exe (bool): `True` to search the system `PATH`. Default `False`

        Returns:
            Path: The filename found
        """
        filename = Path(os.fsdecode(arg))
        file_path = self.find_on_path(self.path.parent, filename)
        if file_path is not None:
            return file_path
        if not exe:
            raise ValueError(
                f"cannot find '{filename}' while expanding '{self.path.parent}'"
            )
        exe_path_str = shutil.which(filename)
        if exe_path_str is not None:
            return Path(exe_path_str)
        raise ValueError(f"cannot find program '{filename}'")

    def expand_arg(self, arg: bytes) -> Expansion:
        # Unescape escaped commas
        debug(f"escaped arg {arg}")
        unescaped_arg = re.sub(rb"\\,", b",", arg)
        debug(f"unescaped arg {unescaped_arg}")
        return self.expand(unescaped_arg)

    def do_macro(
        self,
        name: bytes,
        args: Optional[list[bytes]],
        input: Optional[bytes],
    ) -> Expansion:
        debug(f"do_macro {command_to_str(name, args, input)}")
        name_str = name.decode("iso-8859-1")
        inputs = set()
        if args is None:
            args = None
        else:
            args_expansion = [self.expand_arg(arg) for arg in args]
            args = [a[0] for a in args_expansion]
            for a in args_expansion:
                inputs.update(a[1])
        if input is not None:
            input, input_inputs = self.expand_arg(input)
            inputs.update(input_inputs)
        macro: Optional[
            Callable[[Optional[list[bytes]], Optional[bytes]], Expansion]
        ] = getattr(self._macros, name_str, None)
        if macro is None:
            raise ValueError(f"no such macro '${name_str}'")
        expanded, macro_inputs = macro(args, input)
        inputs.update(macro_inputs)
        return expanded, inputs

    def expand(self, text: bytes) -> Expansion:
        """Expand `text`.

        Args:
            text (bytes): the text to expand

        Returns:
            Expansion
        """
        debug(f"expand {text} {self._stack}")

        startpos = 0
        expanded = text
        inputs = set()
        while True:
            res = MACRO_REGEX.search(expanded, startpos)
            if res is None:
                break
            debug(f"match: {res} {res.end()}")
            escaped = res[1]
            name = res[2]
            startpos = res.end()
            args = None
            input = None
            # Parse arguments
            if startpos < len(expanded) and expanded[startpos] == ord(b"("):
                args, startpos = parse_arguments(expanded, startpos, ord(")"))
            # Parse input
            if startpos < len(expanded) and expanded[startpos] == ord(b"{"):
                input_args, startpos = parse_arguments(expanded, startpos, ord("}"))
                input = b",".join(input_args)
            if escaped != b"":
                # Just remove the leading '\'
                output = command_to_str(name, args, input)
            else:
                output, macro_inputs = self.do_macro(name, args, input)
                inputs.update(macro_inputs)
            expanded = expanded[: res.start()] + output + expanded[startpos:]
            # Update search position to restart matching after output of macro
            startpos = res.start() + len(output)
            debug(f"expanded is now: {expanded}")

        debug(f"expand found inputs {inputs}")
        return expanded, inputs

    def include(self, file_path) -> Expansion:
        """Expand the contents of `file_path`.

        Args:
            file_path (Path): the path to include

        Returns:
            Expansion
        """
        self._stack.append(file_path)
        output, inputs = self.expand(file_path.read_bytes())
        self._stack.pop()
        inputs.add(file_path)
        return output, inputs

    def copy_file(self) -> None:
        """Copy the input file to the output file."""
        if self.tree.output == Path("-"):
            file_contents = self.input_file().read_bytes()
            sys.stdout.buffer.write(file_contents)
        else:
            shutil.copyfile(self.input_file(), self.output_file())
            self.tree.output_files.add(self.output_file())


class Macros:
    """Defines the macros available to template files.

    Each method `foo` defines the behaviour of `$foo`.
    """

    _expand: Expand

    def __init__(self, expand: Expand):
        self._expand = expand

    def path(self, args: Optional[list[bytes]], input: Optional[bytes]) -> Expansion:
        if args is not None:
            raise ValueError("$path does not take arguments")
        if input is not None:
            raise ValueError("$path does not take an input")
        return bytes(self._expand.path), set()

    def outputpath(
        self, args: Optional[list[bytes]], input: Optional[bytes]
    ) -> Expansion:
        if args is not None:
            raise ValueError("$outputpath does not take arguments")
        if input is not None:
            raise ValueError("$outputpath does not take an input")
        return bytes(self._expand.output_path()), set()

    def expand(self, args: Optional[list[bytes]], input: Optional[bytes]) -> Expansion:
        if args is not None:
            raise ValueError("$expand does not take arguments")
        if input is None:
            raise ValueError("$expand takes an input")
        debug(command_to_str(b"expand", args, input))

        output, inputs = self._expand.expand(input)
        return strip_final_newline(output), inputs

    def paste(self, args: Optional[list[bytes]], input: Optional[bytes]) -> Expansion:
        if args is None or len(args) != 1:
            raise ValueError("$paste needs exactly one argument")
        if input is not None:
            raise ValueError("$paste does not take an input")
        debug(command_to_str(b"paste", args, input))

        file_path = self._expand.file_arg(args[0])
        return file_path.read_bytes(), set((file_path,))

    def include(self, args: Optional[list[bytes]], input: Optional[bytes]) -> Expansion:
        if args is None or len(args) != 1:
            raise ValueError("$include needs exactly one argument")
        if input is not None:
            raise ValueError("$include does not take an input")
        debug(command_to_str(b"include", args, input))

        file_path = self._expand.file_arg(args[0])
        output, inputs = self._expand.include(file_path)
        return strip_final_newline(output), inputs

    def run(self, args: Optional[list[bytes]], input: Optional[bytes]) -> Expansion:
        if args is None:
            raise ValueError("$run needs at least one argument")
        debug(command_to_str(b"run", args, input))

        exe_path = self._expand.file_arg(args[0], exe=True)
        return b"", set((exe_path,))


class RunMacros(Macros):
    def run(self, args: Optional[list[bytes]], input: Optional[bytes]) -> Expansion:
        if args is None:
            raise ValueError("$run needs at least one argument")
        debug(command_to_str(b"run", args, input))

        exe_path = self._expand.file_arg(args[0], exe=True)
        expanded_input, inputs = (
            (None, set()) if input is None else self._expand.expand(input)
        )
        os.environ["NANCY_INPUT"] = str(self._expand.tree.input)
        inputs.add(exe_path)
        return filter_bytes(expanded_input, exe_path, args[1:]), inputs


def main(argv: list[str] = sys.argv[1:]) -> None:
    if "DEBUG" in os.environ:
        logging.basicConfig(level=logging.DEBUG)

    # Read and process arguments
    parser = argparse.ArgumentParser(
        description="A simple templating system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input",
        metavar="INPUT",
        help="input directory, or file",
    )
    parser.add_argument(
        "output", metavar="OUTPUT", help="output directory, or file ('-' for stdout)"
    )
    parser.add_argument(
        "--path", help="path to build relative to input tree [default: '']"
    )
    parser.add_argument(
        "--process-hidden",
        help="do not ignore hidden files and directories",
        action="store_true",
    )
    parser.add_argument(
        "--update",
        help="only overwrite files in the output tree if their dependencies are newer than the current file",
        action="store_true",
    )
    parser.add_argument(
        "--delete",
        help="delete files and directories in the output tree that are not written",
        action="store_true",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"""%(prog)s {VERSION}
© 2002–2025 Reuben Thomas <rrt@sc3d.org>
https://github.com/rrthomas/nancy
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.""",
    )
    warnings.showwarning = simple_warning(parser.prog)
    args = parser.parse_args(argv)

    # Expand input
    try:
        if args.input == "":
            die("input path must not be empty")
        input = Path(args.input)

        # Deal with special case where INPUT is a single file and --path is not
        # given.
        if args.path is None and input.is_file():
            args.path = input
            input = Path.cwd()

        tree = Tree(
            input,
            Path(args.output),
            args.process_hidden,
            Path(args.path) if args.path else None,
            args.delete,
            args.update,
        )
        tree.process_path(tree.build)
    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            die(f"{err}")
        sys.exit(1)
