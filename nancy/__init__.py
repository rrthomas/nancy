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
        output (Path): the filesystem `Path` of the output directory
        build (Path): the subtree of `inputs` to process.
            Defaults to the whole tree.
        process_hidden (bool): `True` to process hidden files (those whose
            names begin with ".")
    """

    inputs: list[Path]
    output: Path
    build: Path
    process_hidden: bool

    def __init__(
        self,
        inputs: list[Path],
        output: Path,
        process_hidden: bool,
        build: Optional[Path] = None,
    ):
        if len(inputs) == 0:
            raise ValueError("at least one input must be given")
        for root in inputs:
            if not root.exists():
                raise ValueError(f"input '{root}' does not exist")
            if not root.is_dir():
                raise ValueError(f"input '{root}' is not a directory")
        self.inputs = inputs
        self.output = output
        self.process_hidden = process_hidden
        if build is None:
            build = Path()
        if build.is_absolute():
            raise ValueError("build path must be relative")
        self.build = build

    def find_root(self, obj: Path) -> Optional[Path]:
        """Find the leftmost of `inputs` that contains `obj`."""
        for root in self.inputs:
            if (root / obj).exists():
                return root
        return None

    def find_object(self, obj: Path) -> Optional[Path]:
        """Returns `find_root(obj) / obj` or `None`."""
        debug(f"find_object {obj} {self.inputs}")
        root = self.find_root(obj)
        return None if root is None else root / obj

    def scandir(self, obj: Path) -> list[str]:
        """Returns the child names of overlaid input directory `obj`."""
        debug(f"scandir {obj} {self.inputs}")
        names = set(
            dirent.name
            for root in self.inputs
            if (root / obj).is_dir()
            for dirent in os.scandir(root / obj)
        )
        return list(names)

    def process_path(self, obj: Path) -> None:
        """Recursively scan `obj` and pass every file to `process_file`.

        Args:
            obj (Path): the `inputs`-relative `Path` to scan.
        """
        root = self.find_root(obj)
        if root is None:
            raise ValueError(f"'{obj}' matches no path in the inputs")
        if (root / obj).is_dir():
            if self.output == Path("-"):
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            output_dir = Expand(self, None, obj).output_file()
            os.makedirs(output_dir, exist_ok=True)
            for child in self.scandir(obj):
                if child[0] != "." or self.process_hidden:
                    self.process_path(obj / child)
        elif (root / obj).is_file():
            Expand(self, root, obj).process_file()
        else:
            raise ValueError(f"'{obj}' is not a file or directory")


# TODO: Inline into callers, and remove.
def expand(
    inputs: list[Path],
    output: Path,
    process_hidden: bool,
    build: Optional[Path] = None,
) -> None:
    trees = Trees(inputs, output, process_hidden, build)
    trees.process_path(trees.build)


class Expand:
    """`Path`s related to the file being expanded.

    Fields:
        trees (Trees):
        root (Optional[Path]): one of `trees.inputs`
        path (Path): the `root`-relative `Path`
    """

    trees: Trees
    root: Optional[Path]
    path: Path

    # The output file relative to `trees.output`.
    # `None` while the filename is being expanded.
    _output_path: Optional[Path]

    # _stack is a list of filesystem `Path`s which are currently being
    # `$include`d. This is used to avoid infinite loops.
    _stack: list[Path]

    def __init__(
        self,
        trees: Trees,
        root: Optional[Path],
        path: Path,
    ):
        if root is not None:
            assert root in trees.inputs, (root, trees)
        self.trees = trees
        self.root = root
        self.path = path
        self._output_path = None
        self._stack = []
        self._macros = Macros(self)

        # Recompute `_output_path` by expanding `path`.
        output_path = self.path.relative_to(self.trees.build)
        if output_path.name != "":
            if re.search(COPY_REGEX, output_path.name):
                output_path = output_path.with_name(
                    output_path.name.replace(".copy", "", 1)
                )
            else:
                output_path = output_path.with_name(
                    re.sub(TEMPLATE_REGEX, "", output_path.name)
                )
            output_path = os.fsdecode(self.expand(bytes(output_path)))
        self._output_path = Path(output_path)

    def input_file(self):
        """Returns the filesystem input `Path`."""
        assert self.root is not None
        return self.root / self.path

    def output_path(self):
        """Returns the relative output `Path` for the current file.

        Raises an error if called while the filename is being expanded.
        """
        if self._output_path is None:
            raise ValueError(
                "$outputfile is not available while expanding the filename"
            )
        return self._output_path

    def output_file(self):
        """Returns the (computed) filesystem output `Path`.

        Raises an error if called while the filename is being expanded.
        """
        return self.trees.output / self.output_path()

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

    def _copy_file(self) -> None:
        if self.trees.output == Path("-"):
            file_contents = self.input_file().read_bytes()
            sys.stdout.buffer.write(file_contents)
        else:
            shutil.copyfile(self.input_file(), self.output_file())

    def process_file(self) -> None:
        """Expand, copy or ignore the file."""
        debug(f"Processing file '{self.input_file()}'")
        os.makedirs(self.output_file().parent, exist_ok=True)
        if re.search(COPY_REGEX, self.input_file().name):
            self._copy_file()
        elif re.search(TEMPLATE_REGEX, self.input_file().name):
            debug(f"Expanding '{self.path}' to '{self.output_file()}'")
            output = self.include(self.input_file())
            if self.trees.output == Path("-"):
                sys.stdout.buffer.write(output)
            else:
                with open(self.output_file(), "wb") as fh:
                    fh.write(output)
        elif not re.search(INPUT_REGEX, self.input_file().name):
            self._copy_file()


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

    def outputpath(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is not None:
            raise ValueError("$outputpath does not take arguments")
        if input is not None:
            raise ValueError("$outputpath does not take an input")
        return bytes(self._expand.output_path())

    def expand(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is not None:
            raise ValueError("$expand does not take arguments")
        if input is None:
            raise ValueError("$expand takes an input")
        debug(command_to_str(b"expand", args, input))

        return strip_final_newline(self._expand.expand(input))

    def filename(self, args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
        if args is None or len(args) != 1:
            raise ValueError("$filename needs exactly one argument")
        if input is not None:
            raise ValueError("$filename does not take an input")
        debug(command_to_str(b"filename", args, input))

        return bytes(self._expand.file_arg(args[0]))

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
        os.environ['NANCY_INPUT'] = str(self._expand.root)
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
        trees.process_path(trees.build)
    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            die(f"{err}")
        sys.exit(1)
