# © Reuben Thomas <rrt@sc3d.org> 2024-2025
# Released under the GPL version 3, or (at your option) any later version.

import argparse
import asyncio
import importlib.metadata
import logging
import os
import re
import shutil
import stat
import sys
import warnings
from asyncio.subprocess import Process
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from logging import debug
from pathlib import Path

from .warnings_util import die, simple_warning


VERSION = importlib.metadata.version("nancy")

COPY_REGEX = re.compile(r"\.copy(?=\.|$)")
TEMPLATE_REGEX = re.compile(r"\.nancy(?=\.[^.]+$|$)")
INPUT_REGEX = re.compile(r"\.in(?=\.[^.]+$|$)")

MACRO_REGEX = re.compile(rb"(\\?)\$([^\W\d_]\w*)")

umask = os.umask(0)
os.umask(umask)


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
    args: list[bytes] | None,
    input: bytes | None,
) -> bytes:
    """Reconstitute a macro call from its parsed form."""
    args_string = b"" if args is None else b"(" + b",".join(args) + b")"
    input_string = b"" if input is None else b"{" + input + b"}"
    return b"$" + name + args_string + input_string


@dataclass
class Command:
    command: str
    process: Process


async def filter_bytes(
    input: bytes | None, exe_path: Path, exe_args: list[bytes]
) -> Command:
    """Start an external command passing `input` on stdin.

    Args:
        input (Optional[bytes]): passed to `stdin`
        exe_path (Path): filesystem `Path` of the command to run
        exe_args (list[bytes]): arguments to the command

    Returns:
        bytes: stdout of the command
    """
    debug(f"Running {exe_path} {b' '.join(exe_args)}")
    proc = await asyncio.create_subprocess_exec(
        exe_path.resolve(strict=True),
        *exe_args,
        stdout=asyncio.subprocess.PIPE,
        stdin=asyncio.subprocess.PIPE if input is not None else None,
        stderr=asyncio.subprocess.PIPE,
    )
    if input is not None:
        assert proc.stdin is not None
        proc.stdin.write(input)
    command = str(exe_path)
    if len(exe_args) > 0:
        command += f" {str(b' '.join(exe_args))}"
    return Command(command, proc)


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
        delete_ungenerated (bool): `True` to delete files we do not generate
        update_newer (bool): Used when updating an existing output tree;
            files will only be updated if their macro arguments are newer than
            any current output file. Note this does not take into account macro
            invocations output by scripts.
        extant_files (dict[Path, os.stat_result]): the files in the output tree
            when we start (only set when `delete_ungenerated` is true)
        output_files (set[Path]): the files we write
    """

    inputs: list[Path]
    output: Path
    build: Path
    process_hidden: bool
    delete_ungenerated: bool
    update_newer: bool
    extant_files: dict[Path, os.stat_result]
    output_files: set[Path]
    work_queue: asyncio.Queue[Awaitable]

    def __init__(
        self,
        inputs: list[Path],
        output: Path,
        process_hidden: bool,
        build: Path | None = None,
        delete_ungenerated: bool = False,
        update_newer: bool = False,
    ):
        self.delete_ungenerated = delete_ungenerated
        self.process_hidden = process_hidden
        self.update_newer = update_newer
        if len(inputs) == 0:
            raise ValueError("at least one input must be given")
        for root in inputs:
            if not root.exists():
                raise ValueError(f"input '{root}' does not exist")
            if not root.is_dir():
                raise ValueError(f"input '{root}' is not a directory")
        self.inputs = inputs
        self.output = output
        if build is None:
            build = Path()
        if build.is_absolute():
            raise ValueError("build path must be relative")
        self.build = build
        self.extant_files = {}
        self.output_files = set()
        self.work_queue = asyncio.Queue()
        if delete_ungenerated or update_newer:
            self.find_existing_files()

    def __del__(self):
        if self.delete_ungenerated:
            self.delete_ungenerated_files()
            # Prevent the destructor running again
            self.delete_ungenerated = False

    def find_object(self, obj: Path) -> Path | None:
        """Find the leftmost of `self.inputs` that contains `obj` and return its real `Path`.

        Follow symlinks.
        """
        debug(f"find_object {obj} {self.inputs}")
        for root in self.inputs:
            path = root / obj
            if path.exists():
                # If path is a symlink, and it resolves to a path that is also
                # in the input tree, try to find its target. If it points
                # outside the input tree, return it directly.
                if path.is_symlink():
                    target = path.resolve()
                    if target.is_relative_to(root.resolve()):
                        return self.find_object(target.relative_to(root.resolve()))
                return path
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
        return list(names)

    def _check_output_newer(self, inputs: list[Path], output: Path) -> bool:
        if not output.exists():
            return False
        output_mtime = output.stat().st_mtime
        return all(i.stat().st_mtime <= output_mtime for i in inputs)

    async def process_file(self, real_path: Path, obj: Path, only_newer: bool) -> None:
        """Expand, copy or ignore a file.

        Args:
            real_path (Path): the real `Path` of the file to process
            obj (Path): the inputs-relative `Path`
            only_newer (bool): `True` means only update the file if a
                dependency is newer than any current output file.
        """
        expand = Expand(RunMacros, self, real_path, obj)
        await expand.set_output_path()
        if not re.search(COPY_REGEX, obj.name) and re.search(INPUT_REGEX, obj.name):
            return
        debug(f"Processing path '{obj}' file '{real_path}'")
        self.output_files.add(expand.output_file())
        if only_newer:
            inputs: list[Path] = []
            if re.search(COPY_REGEX, real_path.name):
                inputs.append(real_path)
            elif re.search(TEMPLATE_REGEX, real_path.name):
                check_expand = Expand(Macros, self, real_path, obj)
                await check_expand.set_output_path()
                _, include_inputs = await check_expand.include(real_path)
                inputs += include_inputs
            else:
                inputs.append(real_path)
            debug(f"Checking inputs {inputs} against output {expand.output_file()}")
            if self._check_output_newer(inputs, expand.output_file()):
                debug("Not updating")
                return
            debug("Updating")
        os.makedirs(expand.output_file().parent, exist_ok=True)
        if re.search(COPY_REGEX, obj.name):
            expand.copy_file()
        elif re.search(TEMPLATE_REGEX, obj.name):
            debug(f"Expanding '{obj}' to '{expand.output_file()}'")
            output, _ = await expand.include(expand.real_path)
            if expand.trees.output == Path("-"):
                sys.stdout.buffer.write(output)
            else:
                exe_perms = expand.get_new_execution_perms()
                with open(expand.output_file(), "wb") as fh:
                    fh.write(output)
                expand.set_output_execution_perms(exe_perms)
        else:
            expand.copy_file()

    async def process_path(self, obj: Path) -> None:
        """Recursively scan `obj` and pass every file to `process_file`.

        Args:
            obj (Path): the `inputs`-relative `Path` to scan.
        """
        real_obj = self.find_object(obj)
        if real_obj is None:
            raise ValueError(f"'{obj}' matches no path in the inputs")
        if real_obj.is_dir():
            if self.output == Path("-"):
                raise ValueError("cannot output multiple files to stdout ('-')")
            debug(f"Entering directory '{obj}'")
            expand = Expand(RunMacros, self, None, obj)
            await expand.set_output_path()
            output_dir = expand.output_file()
            os.makedirs(output_dir, exist_ok=True)
            for child in self.scandir(obj):
                if child[0] != "." or self.process_hidden:
                    self.work_queue.put_nowait(self.process_path(obj / child))
        elif real_obj.is_file():
            self.work_queue.put_nowait(
                self.process_file(real_obj, obj, self.update_newer)
            )
        else:
            raise ValueError(f"'{obj}' is not a file or directory")

    async def process(self, workers: int) -> None:
        """Process `self.build` with parallel worker tasks.

        Args:
            workers (int): the number of tasks to use.
        """
        await self.process_path(self.build)

        # Process the work queue
        tasks = []
        for i in range(workers):
            task = asyncio.create_task(worker(i, self.work_queue))
            tasks.append(task)
        await self.work_queue.join()
        self.work_queue.shutdown()
        await asyncio.gather(*tasks)

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


type Expansion = tuple[bytes, list[Path]]
type CommandExpansion = tuple[Command | bytes, list[Path]]


class Expand:
    """`Path`s related to the file being expanded.

    Fields:
        trees (Trees): the inputs
        real_path (Optional[Path]): the real path corresponding to `path`, if any
        path (Path): the inputs-relative `Path`
    """

    trees: Trees
    real_obj: Path | None
    path: Path

    # The output file relative to `trees.output`.
    # `None` while the filename is being expanded.
    _output_path: Path | None

    # _stack is a list of filesystem `Path`s which are currently being
    # `$include`d. This is used to avoid infinite loops.
    _stack: list[Path]

    def __init__(
        self,
        macrosClass: "type[Macros]",  # TODO: remove quotes with 3.14.
        trees: Trees,
        real_path: Path | None,
        path: Path,
    ):
        if real_path is not None:
            assert any(real_path.is_relative_to(root) for root in trees.inputs), (
                real_path,
                trees,
            )
        self.trees = trees
        self.real_path = real_path
        self.path = path
        self._output_path = None
        self._stack = []
        self._macros = macrosClass(self)

    async def set_output_path(self):
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
            # Discard computed inputs when expanding filenames.
            output, _ = await self.expand(bytes(output_path))
            output_path = os.fsdecode(output)
        self._output_path = Path(output_path)

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
        """Returns the (computed) filesystem output `Path`.

        Raises an error if called while the filename is being expanded.
        """
        return self.trees.output / self.output_path()

    def find_on_path(self, start_path: Path, file: Path) -> Path | None:
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

    async def expand_arg(self, arg: bytes) -> Expansion:
        # Unescape escaped commas
        debug(f"escaped arg {arg}")
        unescaped_arg = re.sub(rb"\\,", b",", arg)
        debug(f"unescaped arg {unescaped_arg}")
        return await self.expand(unescaped_arg)

    async def do_macro(
        self,
        name: bytes,
        args: list[bytes] | None,
        input: bytes | None,
    ) -> CommandExpansion:
        debug(f"do_macro {command_to_str(name, args, input)}")
        name_str = name.decode("iso-8859-1")
        inputs = []
        if args is None:
            args = None
        else:
            args_expansion = [await self.expand_arg(arg) for arg in args]
            args = [a[0] for a in args_expansion]
            for a in args_expansion:
                inputs += a[1]
        if input is not None:
            input, input_inputs = await self.expand_arg(input)
            inputs += input_inputs
        macro: (
            Callable[[list[bytes] | None, bytes | None], Awaitable[CommandExpansion]]
            | None
        ) = getattr(self._macros, name_str, None)
        if macro is None:
            raise ValueError(f"no such macro '${name_str}'")
        e = macro(args, input)
        expanded, macro_inputs = await e
        return expanded, inputs + macro_inputs

    async def expand(self, text: bytes) -> Expansion:
        """Expand `text`.

        Args:
            text (bytes): the text to expand

        Returns:
            Expansion
        """
        debug(f"expand {text} {self._stack}")

        startpos = 0
        inputs = []
        expansions: list[tuple[int, int, bytes | Command]] = []
        while True:
            res = MACRO_REGEX.search(text, startpos)
            if res is None:
                break
            debug(f"match: {res} {res.end()}")
            escaped = res[1]
            name = res[2]
            startpos = res.end()
            args = None
            input = None
            # Parse arguments
            if startpos < len(text) and text[startpos] == ord(b"("):
                args, startpos = parse_arguments(text, startpos, ord(")"))
            # Parse input
            if startpos < len(text) and text[startpos] == ord(b"{"):
                input_args, startpos = parse_arguments(text, startpos, ord("}"))
                input = b",".join(input_args)
            if escaped != b"":
                # Just remove the leading '\'
                output = command_to_str(name, args, input)
            else:
                output, macro_inputs = await self.do_macro(name, args, input)
                inputs += macro_inputs
            expansions.append((res.start(), startpos, output))

        expanded: list[bytes] = []
        last_nextpos = 0
        for startpos, nextpos, e in expansions:
            expanded.append(text[last_nextpos:startpos])
            if isinstance(e, bytes):
                expanded.append(e)
            else:
                stdout_data, stderr_data = await e.process.communicate()
                assert e.process.returncode is not None
                expanded.append(stdout_data)
                if e.process.returncode != 0:
                    print(stderr_data.decode("iso-8859-1"), file=sys.stderr)
                    raise ValueError(
                        f"Error code {e.process.returncode} running: {e.command}"
                    )
            last_nextpos = nextpos
        expanded.append(text[last_nextpos:])

        debug(f"expanded is now: {expanded}")
        debug(f"expand found inputs {inputs}")
        return b"".join(expanded), inputs

    async def include(self, file_path) -> Expansion:
        """Expand the contents of `file_path`.

        Args:
            file_path (Path): the filesystem path to include

        Returns:
            Expansion
        """
        self._stack.append(file_path)
        output = await self.expand(file_path.read_bytes())
        self._stack.pop()
        return output[0], output[1] + [file_path]

    def get_new_execution_perms(self):
        """Get the execution permissions for a new file."""
        assert self.real_path is not None
        stats = os.stat(self.real_path)
        return (
            stat.S_IMODE(stats.st_mode)
            & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            & ~umask
        )

    def set_output_execution_perms(self, exe_perms: int):
        """Update the execution permissions on the output file if needed."""
        if exe_perms != 0:
            output_stats = os.stat(self.output_file())
            os.chmod(self.output_file(), output_stats.st_mode | exe_perms)

    def copy_file(self) -> None:
        """Copy the input file to the output file."""
        if self.trees.output == Path("-"):
            assert self.real_path is not None
            file_contents = self.real_path.read_bytes()
            sys.stdout.buffer.write(file_contents)
        else:
            exe_perms = self.get_new_execution_perms()
            assert self.real_path is not None
            shutil.copyfile(self.real_path, self.output_file())
            self.set_output_execution_perms(exe_perms)


class Macros:
    """Defines the macros available to template files.

    Each method `foo` defines the behaviour of `$foo`.
    """

    _expand: Expand

    def __init__(self, expand: Expand):
        self._expand = expand

    async def path(self, args: list[bytes] | None, input: bytes | None) -> Expansion:
        if args is not None:
            raise ValueError("$path does not take arguments")
        if input is not None:
            raise ValueError("$path does not take an input")
        return bytes(self._expand.path), []

    async def outputpath(
        self, args: list[bytes] | None, input: bytes | None
    ) -> Expansion:
        if args is not None:
            raise ValueError("$outputpath does not take arguments")
        if input is not None:
            raise ValueError("$outputpath does not take an input")
        return bytes(self._expand.output_path()), []

    async def expand(self, args: list[bytes] | None, input: bytes | None) -> Expansion:
        if args is not None:
            raise ValueError("$expand does not take arguments")
        if input is None:
            raise ValueError("$expand takes an input")
        debug(command_to_str(b"expand", args, input))

        output, inputs = await self._expand.expand(input)
        return strip_final_newline(output), inputs

    async def paste(self, args: list[bytes] | None, input: bytes | None) -> Expansion:
        if args is None or len(args) != 1:
            raise ValueError("$paste needs exactly one argument")
        if input is not None:
            raise ValueError("$paste does not take an input")
        debug(command_to_str(b"paste", args, input))

        file_path = self._expand.file_arg(args[0])
        return file_path.read_bytes(), [file_path]

    async def include(self, args: list[bytes] | None, input: bytes | None) -> Expansion:
        if args is None or len(args) != 1:
            raise ValueError("$include needs exactly one argument")
        if input is not None:
            raise ValueError("$include does not take an input")
        debug(command_to_str(b"include", args, input))

        file_path = self._expand.file_arg(args[0])
        output, inputs = await self._expand.include(file_path)
        return strip_final_newline(output), inputs

    async def run(
        self, args: list[bytes] | None, input: bytes | None
    ) -> CommandExpansion:
        if args is None:
            raise ValueError("$run needs at least one argument")
        debug(command_to_str(b"run", args, input))

        exe_path = self._expand.file_arg(args[0], exe=True)
        return b"", [exe_path]


class RunMacros(Macros):
    async def run(
        self, args: list[bytes] | None, input: bytes | None
    ) -> CommandExpansion:
        if args is None:
            raise ValueError("$run needs at least one argument")
        debug(command_to_str(b"run", args, input))

        exe_path = self._expand.file_arg(args[0], exe=True)
        expanded_input, inputs = (
            (None, []) if input is None else await self._expand.expand(input)
        )
        os.environ["NANCY_INPUT"] = str(self._expand.real_path)
        return await filter_bytes(expanded_input, exe_path, args[1:]), inputs + [
            exe_path
        ]


async def worker(i: int, queue: asyncio.Queue[Awaitable]):
    while True:
        try:
            process = await queue.get()
        except asyncio.queues.QueueShutDown:
            return
        debug(f"worker {i} got task {process}")
        try:
            await process
        finally:
            queue.task_done()


async def real_main(argv: list[str] = sys.argv[1:]) -> None:
    if "DEBUG" in os.environ:
        logging.basicConfig(level=logging.DEBUG)

    # Read and process arguments
    parser = argparse.ArgumentParser(
        description="A simple templating system.",
        epilog=f"The INPUT-PATH is a '{os.path.pathsep}'-separated list; the inputs are merged "
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
        "--jobs",
        help="number of parallel tasks to run at the same time [default is number of CPU cores, currently %(default)s]",
        type=int,
        default=os.cpu_count() or 1,
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

        await Trees(
            inputs,
            Path(args.output),
            args.process_hidden,
            Path(args.path) if args.path else None,
            args.delete,
            args.update,
        ).process(args.jobs)

    except Exception as err:
        if "DEBUG" in os.environ:
            logging.error(err, exc_info=True)
        else:
            die(f"{err}")
        sys.exit(1)


def main(argv: list[str] = sys.argv[1:]) -> None:
    asyncio.run(real_main(argv))
