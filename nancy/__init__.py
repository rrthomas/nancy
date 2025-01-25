# © Reuben Thomas <rrt@sc3d.org> 2024
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
from typing import Callable, Optional, Union
from warnings import warn

from .warnings_util import die, simple_warning


VERSION = importlib.metadata.version("nancy")

TEMPLATE_REGEX = re.compile(r"\.nancy(?=\.[^.]+$|$)")
NO_COPY_REGEX = re.compile(r"\.in(?=\.[^.]+$|$)")
MACRO_REGEX = re.compile(r"(\\?)\$([^\W\d_]\w*)")


def is_executable(file: str) -> bool:
    return os.access(file, os.X_OK)


def strip_final_newline(s: str) -> str:
    return re.sub("\n$", "", s)


def expand(inputs: list[str], output_path: str, build_path: Optional[str] = "") -> None:
    if len(inputs) == 0:
        raise ValueError("at least one input must be given")
    if build_path is None:
        build_path = ""
    if os.path.isabs(build_path):
        raise ValueError("build path must be relative")
    for root in inputs:
        if not os.path.exists(root):
            raise ValueError(f"input '{root}' does not exist")
        if not os.path.isdir(root):
            raise ValueError(f"input '{root}' is not a directory")

    # Find the first file or directory with relative path `object` in the
    # input tree, scanning the roots from left to right.
    # If the result is a file, return its os.DirEntry.
    # If the result is a directory, return its contents as a list of
    # os.DirEntry, obtained by similarly scanning the tree from left to
    # right.
    # If something neither a file nor directory is found, raise an error.
    # If no result is found, return `None`.
    def find_object(obj: str) -> Optional[Union[str, list[os.DirEntry[str]]]]:
        debug(f"find_object {obj} {inputs}")
        objects = [os.path.join(root, obj) for root in inputs]
        dirs = []
        debug(f"objects to consider: {objects}")
        for o in objects:
            debug(f"considering {o}")
            if os.path.exists(o):
                if os.path.isfile(o):
                    return o
                if os.path.isdir(o):
                    dirs.append(o)
                else:
                    raise ValueError(f"'{o}' is not a file or directory")
        dirents: dict[str, os.DirEntry[str]] = {}
        for d in reversed(dirs):
            for dirent in os.scandir(d):
                dirents[os.path.join(obj, dirent.name)] = dirent
        return list(dirents.values()) if len(dirs) > 0 else None

    def expand_file(base_file: str, file_path: str) -> str:
        debug(f"expand_file {base_file} {file_path}")

        def inner_expand(text: str, expand_stack: list[str]) -> str:
            debug(f"inner_expand {text} {expand_stack}")

            def do_expand(text: str) -> str:
                # Search for file starting at the given path; if found return its file
                # name and contents; if not, die.
                def find_on_path(start_path: list[str], file: str) -> Optional[str]:
                    debug(f"find_on_path {start_path} {file}")
                    search = start_path[:]
                    file_array = os.path.normpath(file).split(os.pathsep)
                    while True:
                        this_search = search + file_array
                        obj = find_object(os.path.join(*this_search))
                        if (
                            obj is not None
                            and not isinstance(obj, list)
                            and os.path.isfile(obj)
                            and obj not in expand_stack
                        ):
                            return obj
                        if len(search) == 0:
                            return None
                        search.pop()

                def get_file(leaf: str) -> str:
                    debug(f"Searching for '{leaf}'")
                    start_path = os.path.dirname(base_file) or "."
                    file_or_exec = find_on_path(
                        start_path.split(os.path.sep), leaf
                    ) or shutil.which(leaf)
                    if file_or_exec is None:
                        raise ValueError(
                            f"cannot find '{leaf}' while expanding '{base_file}'"
                        )
                    debug(f"Found '{file_or_exec}'")
                    return file_or_exec

                def read_file(file: str, args: list[str]) -> str:
                    if is_executable(file):
                        debug(f"Running {file} {' '.join(args)}")
                        output = subprocess.check_output([file] + args, text=True)
                    else:
                        with open(file, encoding="utf-8") as fh:
                            output = fh.read()
                    return output

                # Set up macros
                macros: dict[str, Callable[..., str]] = {}
                macros["path"] = lambda _args: base_file
                macros["realpath"] = lambda _args: file_path

                def get_included_file(
                    command_name: str, args: list[str]
                ) -> tuple[str, str]:
                    debug(f"${command_name}{{{','.join(args)}}}")
                    if len(args) < 1:
                        raise ValueError(
                            f"${command_name} expects at least one argument"
                        )
                    file = get_file(args[0])
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
                        args_string = f"{{{'.'.join(args)}}}"
                        output = f"${name}{args_string if len(args) > 0 else ''}"
                    else:
                        output = do_macro(name, args)
                    expanded = expanded[: res.start()] + output + expanded[startpos:]
                    # Update search position to restart matching after output of macro
                    startpos = res.start() + len(output)
                    debug(f"expanded is now: {expanded}")

                return expanded

            return do_expand(text)

        with open(file_path, encoding="utf-8") as fh:
            return inner_expand(fh.read(), [file_path])

    def get_output_path(base_file: str) -> str:
        relpath = base_file[len(build_path) + 1 :] if build_path != "" else base_file
        output_file = re.sub(TEMPLATE_REGEX, "", relpath)
        return (
            os.path.join(output_path, output_file) if output_file != "" else output_path
        )

    def process_file(base_file: str, file_path: str) -> None:
        output_file = get_output_path(base_file)
        debug(f"Processing file '{file_path}'")
        if re.search(TEMPLATE_REGEX, file_path):
            debug(f"Expanding '{base_file}' to '{output_file}'")
            output = expand_file(base_file, file_path)
            if output_file == "-":
                sys.stdout.write(output)
            else:
                with open(output_file, "w", encoding="utf-8") as fh:
                    fh.write(output)
        elif not re.search(NO_COPY_REGEX, file_path):
            if output_file == "-":
                with open(file_path, encoding="utf-8") as fh:
                    file_contents = fh.read()
                sys.stdout.write(file_contents)
            else:
                shutil.copy2(file_path, output_file)

    def process_path(obj: str) -> None:
        dirent = find_object(obj)
        if dirent is None:
            raise ValueError(f"'{obj}' matches no path in the inputs")
        if isinstance(dirent, list):
            output_dir = get_output_path(obj)
            if output_dir == "-":
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            os.makedirs(output_dir, exist_ok=True)
            for child_dirent in dirent:
                if child_dirent.name[0] != ".":
                    child_object = os.path.join(obj, child_dirent.name)
                    if child_dirent.is_file():
                        process_file(child_object, child_dirent.path)
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
        inputs = args.input.split(os.path.pathsep)

        # Deal with special case where INPUT is a single file and --path is not
        # given.
        if args.path is None and len(inputs) == 1 and os.path.isfile(inputs[0]):
            args.path = inputs[0]
            inputs[0] = os.getcwd()

        expand(inputs, args.output, args.path)
    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            warn(f"{os.path.basename(argv[1])}: {err}")
        sys.exit(1)
