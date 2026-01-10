# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

https://github.com/rrthomas/nancy Distributed under the GNU General Public  
License version 3, or (at your option) any later version. There is no  

Nancy is a simple templating system that copies a file or directory, filling
in templates as it goes. Two simple mechanisms, context-dependent file
inclusion and the invocation of external commands, allow for a wide range of
uses, from simple template filling to generating a web site or software
project.

Nancy was originally designed to build simple static web sites, but can be
used for all sorts of other tasks, similar to more complicated systems like
[AutoGen] and [TXR].

[AutoGen]: https://autogen.sourceforge.net
[TXR]: https://www.nongnu.org/txr

Nancy is free software, licensed under the GNU GPL version 3 (or, at your
option, any later version), and written in Python. See the file COPYING.

See the [Cookbook](Cookbook.md) for examples.

Please send questions, comments, and bug reports to the maintainer, or
report them on the project’s web page (see above for addresses).

## Installation

Install Nancy with pip (part of [Python](https://python.org)):

```
$ pip install nancy
```

## Invocation

```
usage: python -m nancy [-h] [--path PATH] [--process-hidden] [--update]
                       [--delete] [--jobs JOBS] [--version]
                       INPUT-PATH OUTPUT

A simple templating system.

positional arguments:
  INPUT-PATH        list of input directories, or a single file
  OUTPUT            output directory, or file ('-' for stdout)

options:
  -h, --help        show this help message and exit
  --path PATH       path to build relative to input tree [default: '']
  --process-hidden  do not ignore hidden files and directories
  --update          only overwrite files in the output tree if their
                    dependencies are newer than the current file
  --delete          delete files and directories in the output tree that are
                    not written
  --jobs JOBS       number of parallel tasks to run at the same time [default
                    is number of CPU cores, currently 16]
  --version         show program's version number and exit

The INPUT-PATH is a ':'-separated list; the inputs are merged in left-to-right
order.
```

## Operation <a name="operation"></a>

Nancy starts by combining the list of inputs given as its _input path_. If
the same file or directory exists in more than one of the directories on the
input path, the left-most takes precedence. The result is called the “input
tree”, and all paths are relative to it.

Next, Nancy traverses the input tree, or the tree given by the `--path`
argument, if any, which is a relative path denoting a subtree of the
input tree.

For each directory in the input tree, Nancy creates a corresponding
directory, if it does not already exist.

Each file is one of four types:

+ *Copied files* are those whose name contains the suffix `.copy`; this
  takes precedence over the suffixes mentioned below. A file may have more
  than one `.copy` suffix.
+ *Input files* are those whose name contains the suffix `.in`.
+ *Template files* are those whose name contains the suffix `.nancy`.
+ *Plain files* are the rest.

Hidden files and directories (files whose names starts with `.`) are ignored
unless the option `--process-hidden` is given, except for those mentioned in
command line arguments.

The special suffixes need not end the file name; they can be used as infixes
before the file type suffix.

Nancy then processes each file:

+ Each plain file is copied to the corresponding place in the output.
* Each copied file is copied to the corresponding place in the output, with
  a `.copy` suffix removed.
* Each input file is ignored.
+ Each template file is expanded (see below), and the result is written to
  the corresponding place in the output directory. To get the name of a file
  or directory in the output, the name in the input tree is expanded, and
  any `.nancy` suffix is removed. There is one exception: the root directory
  (or file) is called `OUTPUT` (that is, the `OUTPUT` argument to Nancy).

Input files, which are not copied to the output in any form, can be used by
commands in other files. They can also be used for documentation or other
files which you’d like to keep with the inputs, but not form part of the
output.

Output files are created with default permissions, except that when a file
is copied, if any of its execute permission bits is set, then those bits are
first ANDed with the complement of the umask, and if any bits remain set,
they are set on the destination file. This means that a file that is
executable in the input will be executable in the output.

When the option `--update` is used, when a given output file exists, Nancy
only overwrites it with a new version if one of the files used to make it
has a newer timestamp than the current output file. The files considered are
the arguments of `$include`, `$paste` and `$run`. `$include`d files are
processed in order to discover further files, but `$run` commands are not
executed. Therefore, any filename in a command generated by a `$run`
command will not be found, and the use of `--update` may cause some output
files not to be updated when they should be. The `--update` flag is intended
as an optimisation to avoid unnecessarily repeating long-running `$run`
commands.

If the `--delete` option is given, Nancy deletes any files in the output
directory that it did not write, and any directories that thereby become
empty.

Nancy runs background tasks in parallel. By default, it uses up to one task per available CPU core. You can set the number of tasks with the `--jobs` flag. In particular, if you rely on tasks not being run in parallel (usually a bad idea!) you can use `--jobs=1`.


### Special cases

+ If the input path is a single file, and no `--path` argument is given,
  then Nancy acts as if the input path were the current directory and the
  `--path` argument were the file name. This makes it convenient to expand a
  single file using the command: `nancy INPUT-FILE OUTPUT-FILE`
+ When the output is a single file, the special filename `-` may be used to
  cause Nancy to print the result to standard output instead of writing it to
  a file.

### Expansion

Nancy expands a template file as follows:

1. Scan the file for commands. For each command, unescape and expand any
  arguments and input, execute the command, and replace the command by the
  result.
2. Output the result.

A command is written as its name prefixed with a dollar sign: `$COMMAND`.
Some commands take an input, given in braces: `$COMMAND{INPUT}`, and
some take arguments, given in parentheses:
`$COMMAND(ARGUMENT,…)`.

Nancy treats its input as 8-bit ASCII, but command names and other
punctuation only use the 7-bit subset. This means that any text encoding
that is a superset of 7-bit ASCII can be used, such as UTF-8.

The same method is used to expand the arguments of and inputs to commands.

### Built-in commands

Nancy recognises these commands:

+ *`$include(FILE)`* Look up the given source file in the input tree (see
  below); read its contents, then expand them (that is, execute any commands
  it contains) and return the result. Note that the value of `$path` does
  not change during the expansion of an included file’s content. If the
  result ends in a newline, it is removed. (This almost always does what you
  want, and makes `$include` behave better in various contexts.)
+ *`$paste(FILE)`* Look up the given source file like `$include`, and
  return its contents.
+ *`$run(PROGRAM,ARGUMENT…){INPUT}`* Run the given program with the given
  arguments and return its result. If an input is given, it is expanded,
  then supplied to the program’s standard input. This can be useful in a
  variety of ways: to insert the current date or time, to make a
  calculation, or to convert a file to a different format.
+ *`$expand{INPUT}`* Re-expand the input, returning the result, with any
  trailing newline removed. This can be used to expand the output of a
  program run with `$run`.
+ *`$path`* Expands to the file currently being expanded, relative to the
  input tree. This is always a template file, unless the current input path
  is a single file.
+ *`$outputpath`* Returns the output-tree relative path for the file
  currently being expanded.

The last two commands are mostly useful in arguments to `$run`.

To find the file specified by a `$include(FILE)` command, Nancy proceeds
thus:

1. Set `path` to the value of `$path`.
2. See whether `path/FILE` is a file (or a symbolic link to a file). If so,
   return the file path, unless we are already in the middle of expanding
   this file.
3. If `path` is empty, stop. Otherwise, remove the last directory from
   `path` and go to step 2.

If no file is found, Nancy stops with an error message.

For example, if Nancy is trying to find `file.html`, starting in the
subdirectory `foo/bar/baz`, it will try the following files, in order:

1. `foo/bar/baz/file.html`
2. `foo/bar/file.html`
3. `foo/file.html`
4. `file.html`

See the [website example](Cookbook.md#website-example) in the Cookbook for a
worked example.

### How `$run` finds and runs programs

Nancy looks for programs in two ways:

1. Using the same rules as for finding an `$include` or `$paste` input,
   Nancy looks for a file which has the “execute” permission.

2. If no file of the given name can be found using the rules in the previous
   section, Nancy looks for an executable file on the user’s `PATH` (the
   list of directories specified by the `PATH` environment variable).

For example, to insert the current date:

```
$run(date,+%Y-%m-%d)
```

See the [date example](Cookbook.md#date-example) in the Cookbook for more
detail.

If one command is nested inside another, the inner command will be processed
first. This means that if, for example, `$path` is passed as an argument to
a program, the program will be given the actual path, rather than the string
`$path`. Arguments and command inputs are processed from left to right.

### Environment variables provided by `$run`

When Nancy `$run`s a program, it sets the following environment variables:

- NANCY_INPUT - the input file name.

### Escaping

To prevent a comma from being interpreted as an argument separator, put a
backslash in front of it:

```
$run(cat,I\, Robot.txt,3 Rules of Robotics.txt)
```

This will run the `cat` command with the following arguments:

1. `I, Robot.txt`
2. `3 Rules of Robotics.txt`

Note that the filenames supplied to `cat` refer not to the input tree, but
to the file system.

Similarly, a command can be treated as literal text by putting a backslash
in front of it:

```
Now I can talk about \$paste.
```

This will output:

```
Now I can talk about $paste.
```

## Development

Check out the git repository with:

```
git clone https://github.com/rrthomas/nancy
```

Install the pre-commit hooks (needs `pre-commit`, which is installed
automatically if you use a venv) with:

```
pre-commit install
```

To run the tests:

```
make test
```

You will need the `tree` utility to build the documentation.
