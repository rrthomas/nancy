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
MACRO_REGEX = re.compile(r"(\\?)\$([^\W\d_]\w*)")


def is_executable(file: Path) -> bool:
    return os.access(file, os.X_OK)


def strip_final_newline(s: str) -> str:
    return re.sub("\n$", "", s)


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

    def expand_text(
        text: str, base_file: Path, file_path: Path, output_path: Optional[Path] = None
    ) -> str:
        def inner_expand(text: str, expand_stack: list[Path]) -> str:
            debug(f"inner_expand {text} {expand_stack}")

            def do_expand(text: str) -> str:
                # Search for file starting at the given path; if found return its file
                # name and contents; if not, die.
                def find_on_path(start_path: Path, file: Path) -> Optional[Path]:
                    debug(f"find_on_path {start_path} {file}")
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
                            return obj
                        next_path = start_path.parent
                        if next_path == start_path:
                            return None
                        start_path = next_path

                def get_file(leaf: Path) -> Path:
                    debug(f"Searching for '{leaf}'")
                    file_or_exec = find_on_path(base_file.parent, leaf)
                    if file_or_exec is None:
                        executable = shutil.which(leaf)
                        if executable is None:
                            raise ValueError(
                                f"cannot find '{leaf}' while expanding '{base_file}'"
                            )
                        file_or_exec = Path(executable)
                    debug(f"Found '{file_or_exec}'")
                    return file_or_exec

                def read_file(file: Path, args: list[str]) -> str:
                    if is_executable(file):
                        debug(f"Running {file} {' '.join(args)}")
                        output = subprocess.check_output([file] + args, text=True)
                    else:
                        with open(file, encoding="utf-8") as fh:
                            output = fh.read()
                    return output

                # Set up macros
                macros: dict[str, Callable[..., str]] = {}
                macros["path"] = lambda _args: str(base_file)
                macros["realpath"] = lambda _args: str(file_path)
                macros["outputpath"] = (
                    lambda _args: str(output_path) if output_path is not None else ""
                )

                def get_included_file(
                    command_name: str, args: list[str]
                ) -> tuple[Path, str]:
                    debug(f"${command_name}{{{','.join(args)}}}")
                    if len(args) < 1:
                        raise ValueError(
                            f"${command_name} expects at least one argument"
                        )
                    file = get_file(Path(args[0]))
                    return file, read_file(file, args[1:])

                def include(args: list[str]) -> str:
                    file, contents = get_included_file("include", args)
                    return strip_final_newline(
                        inner_expand(contents, expand_stack + [file])
                    )

                macros["include"] = include

                def paste(args: list[str]) -> str:
                    _file, contents = get_included_file("paste", args)
                    return strip_final_newline(contents)

                macros["paste"] = paste

                def do_macro(macro: str, args: list[str]) -> str:
                    debug(f"do_macro {macro} {args}")
                    expanded_args: list[str] = []
                    for a in args:
                        # Unescape escaped commas
                        debug(f"escaped arg {a}")
                        unescaped_arg = re.sub(r"\\,", ",", a)
                        debug(f"unescaped arg {unescaped_arg}")
                        expanded_args.append(do_expand(unescaped_arg))
                    if macro not in macros:
                        raise ValueError(f"no such macro '${macro}'")
                    return macros[macro](expanded_args)

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
                    arg_start = res.end()
                    startpos = arg_start
                    args = []
                    # Parse arguments, respecting nested commands
                    if arg_start < len(expanded) and expanded[arg_start] == "{":
                        depth = 1
                        next_index = arg_start + 1
                        while next_index < len(expanded):
                            if expanded[next_index] == "}":
                                depth -= 1
                                if depth == 0:
                                    args.append(expanded[arg_start + 1 : next_index])
                                    break
                            elif expanded[next_index] == "{":
                                depth += 1
                            elif (
                                depth == 1
                                and expanded[next_index] == ","
                                and expanded[next_index - 1] != "\\"
                            ):
                                args.append(expanded[arg_start + 1 : next_index])
                                arg_start = next_index
                            next_index += 1
                        if next_index == len(expanded):
                            raise ValueError("missing close brace")
                        startpos = next_index + 1
                    if escaped != "":
                        # Just remove the leading '\'
                        args_string = f"{{{','.join(args)}}}"
                        output = f"${name}{args_string if len(args) > 0 else ''}"
                    else:
                        output = do_macro(name, args)
                    expanded = expanded[: res.start()] + output + expanded[startpos:]
                    # Update search position to restart matching after output of macro
                    startpos = res.start() + len(output)
                    debug(f"expanded is now: {expanded}")

                return expanded

            return do_expand(text)

        return inner_expand(text, [file_path])

    def expand_file(base_file: Path, file_path: Path, output_file: Path) -> str:
        debug(f"expand_file {base_file} on path {file_path} to {output_file}")
        with open(file_path, encoding="utf-8") as fh:
            return expand_text(fh.read(), base_file, file_path, output_file)

    def get_output_path(base_file: Path, file_path: Path) -> Path:
        relpath = base_file.relative_to(build_path)
        output_file = relpath
        if output_file.name != "":
            output_file = output_file.with_name(
                re.sub(TEMPLATE_REGEX, "", relpath.name)
            )
            output_file = expand_text(str(output_file), output_file, file_path)
        return output_path / output_file

    def process_file(base_file: Path, file_path: Path) -> None:
        output_file = get_output_path(base_file, file_path)
        debug(f"Processing file '{file_path}'")
        if re.search(TEMPLATE_REGEX, file_path.name):
            debug(f"Expanding '{base_file}' to '{output_file}'")
            output = expand_file(base_file, file_path, output_file)
            if not re.search(NO_COPY_REGEX, str(output_file)):
                if output_file == Path("-"):
                    sys.stdout.write(output)
                else:
                    with open(output_file, "w", encoding="utf-8") as fh:
                        fh.write(output)
        elif not re.search(NO_COPY_REGEX, file_path.name):
            if output_file == Path("-"):
                with open(file_path, encoding="utf-8") as fh:
                    file_contents = fh.read()
                sys.stdout.write(file_contents)
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
