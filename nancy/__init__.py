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
from typing import Callable, Optional, Union

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
    closing = [initial_closing] # Stack of expected close brackets
    next_index = arg_start + 1
    while next_index < len(text):
        if text[next_index] == closing[-1]:
            closing.pop()
            if len(closing) == 0:
                args.append(text[arg_start + 1 : next_index])
                break
        elif text[next_index] in {ord(b"("), ord(b"{")}:
            closing.append(
                ord(b")") if text[next_index] == ord(b"(") else ord(b"}")
            )
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
    args_string = b"(" + b",".join(args) + b")" if args is not None else b""
    input_string = b"{" + input + b"}" if input is not None else b""
    return b"$" + name + args_string + input_string


class Trees:
    """The state that is constant for a whole invocation of Nancy.

    Fields:
        inputs (list[Path]): a list of filesystem `Path`s to overlay to
            make an abstract input tree
        output_path (Path): the filesystem `Path` of the output directory
        build_path (Path): the subtree of `inputs` to process.
            Defaults to the whole tree.
    """
    inputs: list[Path]
    output_path: Path
    build_path: Path

    def __init__(
        self,
        inputs: list[Path],
        output_path: Path,
        build_path: Optional[Path]=None,
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
        if build_path is None:
            build_path = Path()
        if build_path.is_absolute():
            raise ValueError("build path must be relative")
        self.build_path = build_path

    def find_object(
        self, obj: Path,
    ) -> Optional[Union[Path, list[os.DirEntry[str]]]]:
        """Find an object in the input tree.

        Find the first file or directory with relative path `obj` in the
        input tree, scanning the roots from left to right.
        If the result is a file, return its path.
        If the result is a directory, return its contents as a list of
        os.DirEntry, obtained by similarly scanning the tree from left to
        right.
        If something neither a file nor directory is found, raise an error.
        If no result is found, return `None`.
        """
        debug(f"find_object {obj} {self.inputs}")
        objects = [root / obj for root in self.inputs]
        dirs = []
        debug(f"objects to consider: {objects}")
        for o in objects:
            debug(f"considering {o}")
            if o.exists():
                if o.is_file():
                    return o
                if o.is_dir():
                    dirs.append(o)
                else:
                    raise ValueError(f"'{o}' is not a file or directory")
        if len(dirs) == 0:
            return None
        dirents: dict[Path, os.DirEntry[str]] = {}
        for d in reversed(dirs):
            for dirent in os.scandir(d):
                dirents[obj / dirent.name] = dirent
        return sorted(list(dirents.values()), key=lambda x: sorting_name(x.name))

    def get_output_path(self, base_file: Path, file_path: Path) -> Path:
        """Compute the output path of an input file.

        Args:
            base_file (Path): the `inputs`-relative `Path`
            file_path (Path): the filesystem input `Path`

        Returns:
            Path
        """
        output_file = base_file.relative_to(self.build_path)
        if output_file.name != "":
            output_file = output_file.with_name(re.sub(TEMPLATE_REGEX, "", output_file.name))
            output_file = os.fsdecode(
                Expand(self, output_file, file_path).expand_bytes(bytes(output_file))
            )
        return self.output_path / output_file

    def process_file(self, base_file: Path, file_path: Path) -> None:
        """Expand, copy or ignore a single file.

        Args:
            base_file (Path): the `inputs`-relative `Path`
            file_path (Path): the filesystem input `Path`
        """
        debug(f"Processing file '{file_path}'")
        output_file = self.get_output_path(base_file, file_path)
        os.makedirs(output_file.parent, exist_ok=True)
        if re.search(TEMPLATE_REGEX, file_path.name):
            debug(f"Expanding '{base_file}' to '{output_file}'")
            text = file_path.read_bytes()
            output = Expand(self, base_file, file_path, output_file).expand_bytes(text)
            if not re.search(NO_COPY_REGEX, str(output_file)):
                if self.output_path == Path("-"):
                    sys.stdout.buffer.write(output)
                else:
                    with open(output_file, "wb") as fh:
                        fh.write(output)
        elif not re.search(NO_COPY_REGEX, file_path.name):
            if output_file == Path("-"):
                file_contents = file_path.read_bytes()
                sys.stdout.buffer.write(file_contents)
            else:
                shutil.copyfile(file_path, output_file)

    def process_path(self, obj: Path) -> None:
        """Recursively scan `obj` and pass every file to `process_file`.

        Args:
            obj (Path): the `inputs`-relative `Path` to scan.
        """
        dirent = self.find_object(obj)
        if dirent is None:
            raise ValueError(f"'{obj}' matches no path in the inputs")
        if isinstance(dirent, list):
            if self.output_path == Path("-"):
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            for child_dirent in dirent:
                if child_dirent.name[0] != ".":
                    child_object = obj / child_dirent.name
                    if child_dirent.is_file():
                        self.process_file(child_object, Path(child_dirent.path))
                    else:
                        self.process_path(child_object)
        else:
            self.process_file(obj, dirent)


# TODO: Inline into callers, and remove.
def expand(
    inputs: list[Path], output_path: Path, build_path: Optional[Path] = None
) -> None:
    trees = Trees(inputs, output_path, build_path)
    trees.process_path(trees.build_path)


class Expand:
    """`Path`s related to the file being expanded.

    Fields:
        trees (Trees):
        base_file (Path): the `inputs`-relative `Path`
        file_path (Path): the filesystem input `Path`
        output_file (Optional[Path]): the filesystem output `Path`
    """
    trees: Trees
    base_file: Path
    file_path: Path
    output_file: Optional[Path]

    def __init__(
        self,
        trees: Trees,
        base_file: Path,
        file_path: Path,
        output_file: Optional[Path] = None,
    ):
        self.trees = trees
        self.base_file = base_file
        self.file_path = file_path
        self.output_file = output_file

    def inner_expand(self, text: bytes, expand_stack: list[Path]) -> bytes:
        """Expand `text`.

        Args:
            text (bytes): the text to expand
            expand_stack (list[Path]): a list of `inputs`-relative `Path`s
                which are currently being expanded. This is used to avoid
                infinite loops.

        Returns:
            bytes
        """
        debug(f"inner_expand {text} {expand_stack}")

        def find_on_path(start_path: Path, file: Path) -> Optional[Path]:
            """Search for file starting at the given path.

            If none found, raise an error.

            Args:
                start_path (Path): `inputs`-relative `Path` to search
                    up from
                file (Path): the `Path` to look for.

            Returns:
                Optional[Path]: `ancestor/file` where `ancestor` is the
                    longest possible prefix of `start_path` satisfying:
                    - `ancestor/file` exists and is a file
                    - not in `expand_stack`
                    otherwise `None`.
            """
            debug(f"Searching for '{file}' on {start_path}")
            norm_file = Path(os.path.normpath(file))
            for parent in (start_path / "_").parents:
                this_search = parent / norm_file
                obj = self.trees.find_object(this_search)
                if (
                    obj is not None
                    and not isinstance(obj, list)
                    and obj.is_file()
                    and obj not in expand_stack
                ):
                    debug(f"Found '{obj}'")
                    return obj
            return None

        def read_file(file: Path) -> tuple[Optional[Path], bytes]:
            """Try to find and read `file`.

            Args:
                file (Path): the `Path` to look for

            Returns:
                tuple[Optional[Path], bytes]:
                    - The filename found; otherwise `None`
                    - The contents of the file; otherwise empty
            """
            found_file = find_on_path(self.base_file.parent, file)
            if found_file is None:
                raise ValueError(
                    f"cannot find '{file}' while expanding '{self.base_file.parent}'"
                )
            with open(found_file, "rb") as fh:
                output = fh.read()
            return (found_file, output)

        def do_expand(text: bytes) -> bytes:
            debug("do_expand")

            # Set up macros
            macros: dict[bytes, Callable[..., bytes]] = {}
            macros[b"path"] = lambda _args, _external_args: bytes(self.base_file)
            macros[b"realpath"] = lambda _args, _external_args: bytes(self.file_path)
            macros[b"outputpath"] = (
                lambda _args, _external_args: bytes(self.output_file)
                if self.output_file is not None
                else b""
            )

            def exe_arg(exe_arg: bytes):
                """Find an executable file with the given name.

                The input tree is searched first. If no file is found there,
                the system path is searched. If the file is still not found,
                raise an error.

                Args:
                    exe_arg (bytes): the name to search for.

                Returns:
                    Path
                """
                exe_name = Path(os.fsdecode(exe_arg))
                exe_path = find_on_path(self.base_file.parent, exe_name)
                if exe_path is not None:
                    return exe_path
                exe_path_str = shutil.which(exe_name)
                if exe_path_str is not None:
                    return Path(exe_path_str)
                raise ValueError(f"cannot find program '{exe_name}'")

            def filter_bytes(
                input: Optional[bytes],
                exe_path: Path,
                exe_args: list[bytes]
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

            def file_arg(filename: bytes) -> tuple[Optional[Path], bytes]:
                file = None
                contents = b""
                if args is not None:
                    basename = Path(os.fsdecode(filename))
                    file, contents = read_file(basename)
                return (file, contents)

            def expand(
                args: Optional[list[bytes]], input: Optional[bytes]
            ) -> bytes:
                if args is not None:
                    raise ValueError("$expand does not take arguments")
                if input is None:
                    raise ValueError("$expand takes an input")
                debug(command_to_str(b"expand", args, input))

                return strip_final_newline(self.inner_expand(input, expand_stack))

            macros[b"expand"] = expand

            def paste(args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
                if args is None or len(args) != 1:
                    raise ValueError("$paste needs exactly one argument")
                if input is not None:
                    raise ValueError("$paste does not take an input")
                debug(command_to_str(b"paste", args, input))

                _file, contents = file_arg(args[0])
                return contents

            macros[b"paste"] = paste

            def include(
                args: Optional[list[bytes]], input: Optional[bytes]
            ) -> bytes:
                if args is None or len(args) != 1:
                    raise ValueError("$include needs exactly one argument")
                if input is not None:
                    raise ValueError("$include does not take an input")
                debug(command_to_str(b"include", args, input))

                file, contents = file_arg(args[0])
                return strip_final_newline(
                    self.inner_expand(
                        contents, expand_stack + [file] if file is not None else []
                    )
                )

            macros[b"include"] = include

            def run(args: Optional[list[bytes]], input: Optional[bytes]) -> bytes:
                if args is None:
                    raise ValueError("$run needs at least one argument")
                debug(command_to_str(b"run", args, input))
                exe_path = exe_arg(args[0])
                exe_args = args[1:]

                expanded_input = None
                if input is not None:
                    expanded_input = self.inner_expand(input, expand_stack)
                return filter_bytes(expanded_input, exe_path, exe_args)

            macros[b"run"] = run

            def expand_arg(arg: bytes) -> bytes:
                # Unescape escaped commas
                debug(f"escaped arg {arg}")
                unescaped_arg = re.sub(rb"\\,", b",", arg)
                debug(f"unescaped arg {unescaped_arg}")
                return do_expand(unescaped_arg)

            def do_macro(
                macro: bytes,
                args: Optional[list[bytes]],
                input: Optional[bytes],
            ) -> bytes:
                debug(f"do_macro {command_to_str(macro, args, input)}")
                expanded_args = (
                    list(map(expand_arg, args)) if args is not None else None
                )
                expanded_input = expand_arg(input) if input is not None else None
                if macro not in macros:
                    decoded_macro = macro.decode("iso-8859-1")
                    raise ValueError(f"no such macro '${decoded_macro}'")
                return macros[macro](expanded_args, expanded_input)

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
                    input_args, startpos = parse_arguments(
                        expanded, startpos, ord("}")
                    )
                    input = b','.join(input_args)
                if escaped != b"":
                    # Just remove the leading '\'
                    output = command_to_str(name, args, input)
                else:
                    output = do_macro(name, args, input)
                expanded = expanded[: res.start()] + output + expanded[startpos:]
                # Update search position to restart matching after output of macro
                startpos = res.start() + len(output)
                debug(f"expanded is now: {expanded}")

            return expanded

        return do_expand(text)

    def expand_bytes(
        self,
        text: bytes,
    ) -> bytes:
        """Expand `text`.

        Args:
            text (bytes): the text to expand

        Returns:
            bytes
        """
        return self.inner_expand(text, [self.file_path])


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
            Path(args.path) if args.path else None,
        )
        trees.process_path(trees.build_path)
    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            die(f"{err}")
        sys.exit(1)
