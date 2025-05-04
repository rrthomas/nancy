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
from typing import Optional

from .warnings_util import die, simple_warning


VERSION = importlib.metadata.version("nancy")

TEMPLATE_REGEX = re.compile(r"\.nancy(?=\.[^.]+$|$)")
NO_COPY_REGEX = re.compile(r"\.in(?=\.(nancy\.)?[^.]+$|$)")
MACRO_REGEX = re.compile(rb"(\\?)\$([^\W\d_]\w*)")


def strip_final_newline(s: bytes) -> bytes:
    return re.sub(b"\n$", b"", s)


# Turn a filename into a sort key.
def sorting_name(n: str) -> str:
    if re.search(NO_COPY_REGEX, n):
        return f"2 {n}"
    elif re.search(TEMPLATE_REGEX, n):
        return f"1 {n}"
    return f"0 {n}"


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
        exe_path (Path): filesystem `Path` of the command to run
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


class Trees:
    """The state that is constant for a whole invocation of Nancy.

    Fields:
        inputs (list[Path]): a list of filesystem `Path`s to overlay to
            make an abstract input tree
        output_path (Path): the filesystem `Path` of the output directory
        build_path (Path): the subtree of `inputs` to process.
            Defaults to the whole tree.
        process_hidden (bool): `True` to process hidden files (those whose
            names begin with ".")
    """

    inputs: list[Path]
    output_path: Path
    build_path: Path
    process_hidden: bool

    def __init__(
        self,
        inputs: list[Path],
        output_path: Path,
        process_hidden: bool,
        build_path: Optional[Path] = None,
    ):
        if len(inputs) == 0:
            raise ValueError("at least one input must be given")
        for root in inputs:
            if not root.exists():
                raise ValueError(f"input '{root}' does not exist")
            if not root.is_dir():
                raise ValueError(f"input '{root}' is not a directory")
        self.inputs = inputs
        self.output_path = output_path
        self.process_hidden = process_hidden
        if build_path is None:
            build_path = Path()
        if build_path.is_absolute():
            raise ValueError("build path must be relative")
        self.build_path = build_path

    def find_object(self, obj: Path) -> Optional[Path]:
        """Find the leftmost input tree containing `obj`.

        Returns:
            Optional[Path]: the filesystem path of `obj`
        """
        debug(f"find_object {obj} {self.inputs}")
        for o in (root / obj for root in self.inputs):
            debug(f"considering {o}")
            if o.exists():
                return o
        return None

    def scandir(self, obj: Path) -> list[str]:
        """Returns the child names of overlaid input directory `obj`."""
        debug(f"scandir {obj} {self.inputs}")
        names = set(
            dirent.name
            for root in self.inputs
            if (root / obj).is_dir()
            for dirent in os.scandir(root / obj)
        )
        return sorted(names, key=sorting_name)

    def process_path(self, obj: Path) -> None:
        """Recursively scan `obj` and pass every file to `process_file`.

        Args:
            obj (Path): the `inputs`-relative `Path` to scan.
        """
        found = self.find_object(obj)
        if found is None:
            raise ValueError(f"'{obj}' matches no path in the inputs")
        if found.is_dir():
            if self.output_path == Path("-"):
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            os.makedirs(
                self.output_path, exist_ok=True
            )  # FIXME: `Trees.output_path` vs `Expand.output_file`
            for child in self.scandir(obj):
                if child[0] != "." or self.process_hidden:
                    self.process_path(obj / child)
        elif found.is_file():
            Expand(self, obj, found).process_file()
        else:
            raise ValueError(f"'{obj}' is not a file or directory")


# TODO: Inline into callers, and remove.
def expand(
    inputs: list[Path],
    output_path: Path,
    process_hidden: bool,
    build_path: Optional[Path] = None,
) -> None:
    trees = Trees(inputs, output_path, process_hidden, build_path)
    trees.process_path(trees.build_path)


class Expand:
    """`Path`s related to the file being expanded.

    Fields:
        trees (Trees):
        path (Path): the `inputs`-relative `Path`
        file_path (Path): the filesystem input `Path`
    """

    trees: Trees
    path: Path
    file_path: Path
    _output_file: Optional[Path]

    # _stack is a list of filesystem `Path`s which are currently being
    # `$include`d. This is used to avoid infinite loops.
    _stack: list[Path]

    def __init__(
        self,
        trees: Trees,
        path: Path,
        file_path: Path,
    ):
        self.trees = trees
        self.path = path
        self.file_path = file_path
        self._output_file = None
        self._stack = []
        self._macros = Macros(self)

        # Recompute `output_file` by expanding `path`.
        output_file = self.path.relative_to(self.trees.build_path)
        if output_file.name != "":
            output_file = output_file.with_name(
                re.sub(TEMPLATE_REGEX, "", output_file.name)
            )
            output_file = os.fsdecode(self.expand(bytes(output_file)))
        self._output_file = self.trees.output_path / output_file

    def output_file(self):
        """Returns the (computed) filesystem output `Path`.

        Raises an error if called while the filename is being expanded.
        """
        if self._output_file is None:
            raise ValueError(
                "$outputfile is not available while expanding the filename"
            )
        return self._output_file

    def find_on_path(self, start_path: Path, file: Path) -> Optional[Path]:
        """Search for file starting at the given path.

        Args:
            start_path (Path): `inputs`-relative `Path` to search up from
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
            obj = self.trees.find_object(parent / norm_file)
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

    def expand_arg(self, arg: bytes) -> bytes:
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
    ) -> bytes:
        debug(f"do_macro {command_to_str(name, args, input)}")
        name_str = name.decode("iso-8859-1")
        args = None if args is None else [self.expand_arg(arg) for arg in args]
        input = None if input is None else self.expand_arg(input)
        macro = getattr(self._macros, name_str, None)
        if macro is None:
            raise ValueError(f"no such macro '${name_str}'")
        return macro(args, input)

    def expand(self, text: bytes) -> bytes:
        """Expand `text`.

        Args:
            text (bytes): the text to expand

        Returns:
            bytes
        """
        debug(f"expand {text} {self._stack}")

        startpos = 0
        expanded = text
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
                output = self.do_macro(name, args, input)
            expanded = expanded[: res.start()] + output + expanded[startpos:]
            # Update search position to restart matching after output of macro
            startpos = res.start() + len(output)
            debug(f"expanded is now: {expanded}")

        return expanded

    def include(self, file_path):
        """Expand the contents of `file_path`.

        Args:
            file_path (Path): the filesystem path to include

        Returns:
            bytes
        """
        self._stack.append(file_path)
        output = self.expand(file_path.read_bytes())
        self._stack.pop()
        return output

    def process_file(self) -> None:
        """Expand, copy or ignore the file."""
        debug(f"Processing file '{self.file_path}'")
        os.makedirs(self.output_file().parent, exist_ok=True)
        if re.search(TEMPLATE_REGEX, self.file_path.name):
            debug(f"Expanding '{self.path}' to '{self.output_file()}'")
            output = self.include(self.file_path)
            if not re.search(NO_COPY_REGEX, str(self.output_file())):
                if self.trees.output_path == Path("-"):
                    sys.stdout.buffer.write(output)
                else:
                    with open(self.output_file(), "wb") as fh:
                        fh.write(output)
        elif not re.search(NO_COPY_REGEX, self.file_path.name):
            if self.trees.output_path == Path("-"):
                file_contents = self.file_path.read_bytes()
                sys.stdout.buffer.write(file_contents)
            else:
                shutil.copyfile(self.file_path, self.output_file())


class Macros:
    """Defines all the macros available to .nancy files.

    Each method `foo` defines the behaviour of `$foo`.
    """

    _expand: Expand

    def __init__(self, expand: Expand):
        self._expand = expand

    def path(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is not None:
            raise ValueError("$path does not take arguments")
        if input is not None:
            raise ValueError("$path does not take an input")
        return bytes(self._expand.path)

    def realpath(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is not None:
            raise ValueError("$realpath does not take arguments")
        if input is not None:
            raise ValueError("$realpath does not take an input")
        return bytes(self._expand.file_path)

    def outputpath(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is not None:
            raise ValueError("$outputpath does not take arguments")
        if input is not None:
            raise ValueError("$outputpath does not take an input")
        try:
            return bytes(self._expand.output_file())
        except ValueError:
            return b""

    def expand(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is not None:
            raise ValueError("$expand does not take arguments")
        if input is None:
            raise ValueError("$expand takes an input")
        debug(command_to_str(b"expand", args, input))

        return strip_final_newline(self._expand.expand(input))

    def paste(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is None or len(args) != 1:
            raise ValueError("$paste needs exactly one argument")
        if input is not None:
            raise ValueError("$paste does not take an input")
        debug(command_to_str(b"paste", args, input))

        file_path = self._expand.file_arg(args[0])
        return file_path.read_bytes()

    def include(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is None or len(args) != 1:
            raise ValueError("$include needs exactly one argument")
        if input is not None:
            raise ValueError("$include does not take an input")
        debug(command_to_str(b"include", args, input))

        file_path = self._expand.file_arg(args[0])
        return strip_final_newline(self._expand.include(file_path))

    def run(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is None:
            raise ValueError("$run needs at least one argument")
        debug(command_to_str(b"run", args, input))

        exe_path = self._expand.file_arg(args[0], exe=True)
        expanded_input = None if input is None else self._expand.expand(input)
        return filter_bytes(expanded_input, exe_path, args[1:])


def main(argv: list[str] = sys.argv[1:]) -> None:
    if "DEBUG" in os.environ:
        logging.basicConfig(level=logging.DEBUG)

    # Read and process arguments
    parser = argparse.ArgumentParser(
        description="A simple templating system.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"The INPUT-PATH is a '{os.path.pathsep}'-separated list; the inputs are merged\n"
        + "in left-to-right order.",
    )
    parser.add_argument(
        "input",
        metavar="INPUT-PATH",
        help="list of input directories, or a single file",
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
        inputs = list(map(Path, args.input.split(os.path.pathsep)))

        # Deal with special case where INPUT is a single file and --path is not
        # given.
        if args.path is None and len(inputs) == 1 and inputs[0].is_file():
            args.path = inputs[0]
            inputs[0] = Path.cwd()

        trees = Trees(
            inputs,
            Path(args.output),
            args.process_hidden,
            Path(args.path) if args.path else None,
        )
        trees.process_path(trees.build_path)
    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            die(f"{err}")
        sys.exit(1)
