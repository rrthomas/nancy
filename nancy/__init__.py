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
NO_COPY_REGEX = re.compile(r"\.in(?=\.(nancy.)?[^.]+$|$)")
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


def expand(
    inputs: list[Path], output_path: Path, build_path: Optional[Path] = Path()
) -> None:
    if len(inputs) == 0:
        raise ValueError("at least one input must be given")
    if build_path is None:
        build_path = Path()
    if build_path.is_absolute():
        raise ValueError("build path must be relative")
    for root in inputs:
        if not root.exists():
            raise ValueError(f"input '{root}' does not exist")
        if not root.is_dir():
            raise ValueError(f"input '{root}' is not a directory")

    # Find the first file or directory with relative path `object` in the
    # input tree, scanning the roots from left to right.
    # If the result is a file, return its path.
    # If the result is a directory, return its contents as a list of
    # os.DirEntry, obtained by similarly scanning the tree from left to
    # right.
    # If something neither a file nor directory is found, raise an error.
    # If no result is found, return `None`.
    def find_object(obj: Path) -> Optional[Union[Path, list[os.DirEntry[str]]]]:
        debug(f"find_object {obj} {inputs}")
        objects = [root / obj for root in inputs]
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
        dirents: dict[Path, os.DirEntry[str]] = {}
        for d in reversed(dirs):
            for dirent in os.scandir(d):
                dirents[obj / dirent.name] = dirent
        if len(dirs) == 0:
            return None
        return sorted(list(dirents.values()), key=lambda x: sorting_name(x.name))

    def parse_arguments(
        text: bytes, arg_start: int, initial_closing: int
    ) -> tuple[list[bytes], int]:
        args = []
        closing = [initial_closing]
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

    def expand_bytes(
        text: bytes,
        base_file: Path,
        file_path: Path,
        output_path: Optional[Path] = None,
    ) -> bytes:
        def inner_expand(text: bytes, expand_stack: list[Path]) -> bytes:
            debug(f"inner_expand {text} {expand_stack}")

            def do_expand(text: bytes) -> bytes:
                # Search for file starting at the given path; if found return its file
                # name and contents; if not, raise an error.
                def find_on_path(start_path: Path, file: Path) -> Optional[Path]:
                    debug(f"Searching for '{file}' on {start_path}")
                    norm_file = Path(os.path.normpath(file))
                    for parent in (start_path / "_").parents:
                        this_search = parent / norm_file
                        obj = find_object(this_search)
                        if (
                            obj is not None
                            and not isinstance(obj, list)
                            and obj.is_file()
                            and obj not in expand_stack
                        ):
                            debug(f"Found '{obj}'")
                            return obj
                        next_path = start_path.parent
                        if next_path == start_path:
                            break
                        start_path = next_path
                    return None

                # Set up macros
                macros: dict[bytes, Callable[..., bytes]] = {}
                macros[b"path"] = lambda _args, _external_args: bytes(base_file)
                macros[b"realpath"] = lambda _args, _external_args: bytes(file_path)
                macros[b"outputpath"] = (
                    lambda _args, _external_args: bytes(output_path)
                    if output_path is not None
                    else b""
                )

                # Try to find the given file. If it is found, return its
                # contents, with the file name actually read, so as to
                # exclude it from recursive expansion; otherwise, return
                # `None` and an empty bytes.
                def read_file(
                    basename: Path,
                ) -> tuple[Optional[Path], bytes]:
                    file = find_on_path(base_file.parent, basename)
                    if file is None:
                        raise ValueError(
                            f"cannot find '{basename}' while expanding '{base_file.parent}'"
                        )
                    with open(file, "rb") as fh:
                        output = fh.read()
                    return (file, output)

                def filter_bytes(
                    input: bytes,
                    external_args: list[bytes],
                ):
                    exe_name = Path(os.fsdecode(external_args[0]))
                    exe_path = find_on_path(base_file.parent, exe_name)
                    if exe_path is None:
                        exe_path_str = shutil.which(exe_name)
                        if exe_path_str is None:
                            raise ValueError(f"cannot find program '{exe_name}'")
                        exe_path = Path(exe_path_str)
                    exe_args = external_args[1:]
                    debug(f"Running {exe_path} {b' '.join(exe_args)}")
                    res = subprocess.run(
                        [exe_path.resolve(strict=True)] + exe_args,
                        capture_output=True,
                        check=True,
                        input=input,
                    )
                    return res.stdout

                def command_to_str(
                    name: bytes,
                    external_args: Optional[list[bytes]],
                    args: Optional[list[bytes]],
                ):
                    external_args_string = (
                        b"(" + b",".join(external_args) + b")"
                        if external_args is not None
                        else b""
                    )
                    args_string = (
                        b"{" + b",".join(args) + b"}" if args is not None else b""
                    )
                    return b"$" + name + external_args_string + args_string

                def check_file_command_args(
                    command_name: bytes,
                    args: Optional[list[bytes]],
                    external_args: Optional[list[bytes]],
                ):
                    command_name_str = command_name.decode("iso-8859-1")
                    if args is None and external_args is None:
                        raise ValueError(
                            f"${command_name_str} needs arguments or external arguments"
                        )
                    if args is not None and len(args) != 1:
                        raise ValueError(
                            f"${command_name_str} needs exactly one argument"
                        )
                    debug(command_to_str(command_name, external_args, args))

                def maybe_file_arg(
                    args: Optional[list[bytes]],
                ) -> tuple[Optional[Path], bytes]:
                    file = None
                    contents = b""
                    if args is not None:
                        basename = Path(os.fsdecode(args[0]))
                        file, contents = read_file(basename)
                    return (file, contents)

                def maybe_filter_bytes(
                    input: bytes, external_args: Optional[list[bytes]]
                ) -> bytes:
                    return (
                        filter_bytes(input, external_args)
                        if external_args is not None
                        else input
                    )

                def include(
                    args: Optional[list[bytes]], external_args: Optional[list[bytes]]
                ) -> bytes:
                    check_file_command_args(b"include", args, external_args)
                    file, contents = maybe_file_arg(args)
                    expanded_contents = inner_expand(
                        contents, expand_stack + [file] if file is not None else []
                    )
                    filtered_contents = maybe_filter_bytes(
                        expanded_contents, external_args
                    )
                    return strip_final_newline(
                        inner_expand(filtered_contents, expand_stack)
                    )

                macros[b"include"] = include

                def paste(
                    args: Optional[list[bytes]], external_args: Optional[list[bytes]]
                ) -> bytes:
                    check_file_command_args(b"paste", args, external_args)
                    _file, contents = maybe_file_arg(args)
                    filtered_contents = maybe_filter_bytes(contents, external_args)
                    return strip_final_newline(filtered_contents)

                macros[b"paste"] = paste

                def expand_args(args: list[bytes]) -> list[bytes]:
                    expanded_args: list[bytes] = []
                    for a in args:
                        # Unescape escaped commas
                        debug(f"escaped arg {a}")
                        unescaped_arg = re.sub(rb"\\,", b",", a)
                        debug(f"unescaped arg {unescaped_arg}")
                        expanded_args.append(do_expand(unescaped_arg))
                    return expanded_args

                def do_macro(
                    macro: bytes,
                    args: Optional[list[bytes]],
                    external_args: Optional[list[bytes]],
                ) -> bytes:
                    debug(f"do_macro {command_to_str(macro, external_args, args)}")
                    expanded_args = expand_args(args) if args is not None else None
                    expanded_external_args = (
                        expand_args(external_args)
                        if external_args is not None
                        else None
                    )
                    if macro not in macros:
                        decoded_macro = macro.decode("iso-8859-1")
                        raise ValueError(f"no such macro '${decoded_macro}'")
                    return macros[macro](expanded_args, expanded_external_args)

                debug("do_match")
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
                    external_args = None
                    # Parse external program arguments
                    if startpos < len(expanded) and expanded[startpos] == ord(b"("):
                        external_args, startpos = parse_arguments(
                            expanded, startpos, ord(")")
                        )
                    if startpos < len(expanded) and expanded[startpos] == ord(b"{"):
                        args, startpos = parse_arguments(expanded, startpos, ord("}"))
                    if escaped != b"":
                        # Just remove the leading '\'
                        output = command_to_str(name, external_args, args)
                    else:
                        output = do_macro(name, args, external_args)
                    expanded = expanded[: res.start()] + output + expanded[startpos:]
                    # Update search position to restart matching after output of macro
                    startpos = res.start() + len(output)
                    debug(f"expanded is now: {expanded}")

                return expanded

            return do_expand(text)

        return inner_expand(text, [file_path])

    def expand_file(base_file: Path, file_path: Path, output_file: Path) -> bytes:
        debug(f"expand_file {base_file} on path {file_path} to {output_file}")
        return expand_bytes(file_path.read_bytes(), base_file, file_path, output_file)

    def get_output_path(base_file: Path, file_path: Path) -> Path:
        relpath = base_file.relative_to(build_path)
        output_file = relpath
        if output_file.name != "":
            output_file = output_file.with_name(
                os.fsdecode(re.sub(TEMPLATE_REGEX, "", relpath.name))
            )
            output_file = os.fsdecode(
                expand_bytes(bytes(output_file), output_file, file_path)
            )
        return output_path / output_file

    def process_file(base_file: Path, file_path: Path) -> None:
        output_file = get_output_path(base_file, file_path)
        debug(f"Processing file '{file_path}'")
        if re.search(TEMPLATE_REGEX, file_path.name):
            debug(f"Expanding '{base_file}' to '{output_file}'")
            output = expand_file(base_file, file_path, output_file)
            if not re.search(NO_COPY_REGEX, str(output_file)):
                if output_file == Path("-"):
                    sys.stdout.buffer.write(output)
                else:
                    with open(output_file, "wb") as fh:
                        fh.write(output)
        elif not re.search(NO_COPY_REGEX, file_path.name):
            if output_file == Path("-"):
                file_contents = file_path.read_bytes()
                sys.stdout.buffer.write(file_contents)
            else:
                shutil.copy2(file_path, output_file)

    def process_path(obj: Path) -> None:
        dirent = find_object(obj)
        if dirent is None:
            raise ValueError(f"'{obj}' matches no path in the inputs")
        if isinstance(dirent, list):
            output_dir = get_output_path(obj, obj)
            if output_dir == Path("-"):
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            os.makedirs(output_dir, exist_ok=True)
            for child_dirent in dirent:
                if child_dirent.name[0] != ".":
                    child_object = obj / child_dirent.name
                    if child_dirent.is_file():
                        process_file(child_object, Path(child_dirent.path))
                    else:
                        process_path(child_object)
        else:
            process_file(obj, dirent)

    process_path(build_path)


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

        expand(inputs, Path(args.output), Path(args.path) if args.path else None)
    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            die(f"{err}")
        sys.exit(1)
