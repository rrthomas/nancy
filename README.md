# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

© 2002–2025 Reuben Thomas <rrt@sc3d.org>  
https://github.com/rrthomas/nancy  

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
nancy [-h] [--path PATH] [--version] INPUT-PATH OUTPUT

A simple templating system.

positional arguments:
  INPUT-PATH   list of input directories, or a single file
  OUTPUT       output directory, or file ('-' for stdout)

options:
  -h, --help   show this help message and exit
  --path PATH  path to build relative to input tree [default: '']
  --version    show program's version number and exit

The INPUT-PATH is a ':'-separated list; the inputs are merged
in left-to-right order.
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

The files are sorted into three groups:

+ *Input files* are those whose name contains the suffix `.in`.
+ *Template files* are those whose name contains the suffix `.nancy`.
+ *Plain files* are the rest.

The special suffixes need not end the file name; they can be used as infixes
before the file type suffix. If both are used, they must be in the order
`.in.nancy`; such files go in the first group.

Nancy then considers the files in each group, taking the files in each group
in lexical order:

+ First, each plain file is copied to the corresponding place in the
  output.
+ Secondly, each template file is expanded (see below), and the result is
  written to the corresponding place in the output directory. To get
  the name of a file or directory in the output, the name in the input tree
  is expanded, and any `.nancy` suffix is removed. There is one exception:
  the root directory (or file) is called `OUTPUT` (that is, the `OUTPUT`
  argument to Nancy).
+ Thirdly, any template files among the input files are also expanded, but
  the result is discarded.

Input files, which are not copied to the output in any form, can be used by
commands in other files, or in the case of `.in.nancy` files, have other
side-effects, as commands they contain are executed. They can also be used
for documentation or other files which you’d like to keep with the inputs,
but not form part of the output.


### Special cases

+ If the input path is a single file, and no `--path` argument is given,
  then Nancy acts as if the input path were the current directory and the
  `--path` argument were the file name. This makes it convenient to expand a
  single file using the command: `nancy INPUT-FILE OUTPUT-FILE`
+ When the output is a single file, the special filename `-` may be used to
  cause Nancy to print the result to standard output instead of writing it to
  a file.

### Template expansion

Nancy expands a template file as follows:

1. Scan the file for commands. Expand any arguments to the command, run each
   command, and replace the command by the result. If the result ends in a
  newline, it is removed. (This is almost always does what you want, and
  makes `$include` behave better in various contexts.)
2. Output the result.

A command is written as its name prefixed with a dollar sign: `$COMMAND`.
Some commands take an input, given in braces: `$COMMAND{INPUT}`, and
some take arguments, given in parentheses:
`$COMMAND(ARGUMENT,…)`.

Nancy treats its input as 8-bit ASCII, but command names and other
punctuation only use the 7-bit subset. This means that any text encoding
that is a superset of 7-bit ASCII can be used, such as UTF-8.

### Built-in commands

Nancy recognises these commands:

+ *`$include(FILE)`* Look up the given source file in the input tree (see
  below); read its contents, then expand them (that is, execute any commands
  it contains) and return the result.
+ *`$paste(FILE)`* Look up the given source file like `$include`, and
  return its contents.
+ *`$run(PROGRAM,ARGUMENT…){INPUT}`* Run the given program with the given
  arguments and return its result. If an input is given, it is expanded,
  then supplied to the program’s standard input. This can be useful in a
  variety of ways: to insert the current date or time, to make a
  calculation, or to convert a file to a different format.
+ *`$expand{INPUT}`* Expand the input, returning the result. This can be
  used to expand the output of a program run with `$run`.
+ *`$path`* Expands to the file currently being expanded, relative to the
  input tree.
+ *`$realpath`* Returns the real path of the file currently being expanded.
+ *`$outputpath`* Returns the path of the output for the file currently
  being expanded.

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
first. This means that if, for example, `$realpath` is passed as an
argument to a program, the program will be given the actual path, rather
than the string `$realpath`. Arguments and command inputs are processed
from left to right.

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

To run the tests:

```
make test
```

You will need the `tree` utility to build the documentation.
