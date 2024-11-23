# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

© 2002–2024 Reuben Thomas <rrt@sc3d.org>  
https://github.com/rrthomas/nancy  

Nancy is a simple macro processor that copies a file or directory, filling
in templates as it goes. It has just one non-trivial construct:
context-dependent file inclusion. A file can either be included literally,
or run as a command and its output included.

Nancy was originally designed to build simple static web sites, but can be
used for all sorts of other tasks, similar to more complicated systems like
[AutoGen] and [TXR].

[AutoGen]: https://autogen.sourceforge.net
[TXR]: https://www.nongnu.org/txr

Nancy is free software, licensed under the GNU GPL version 3 (or, at your
option, any later version), and written in TypeScript.

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

OUTPUT cannot be in any input directory.
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

For each file, Nancy looks at its name, and:

+ If the name contains the suffix `.nancy`, the file’s contents is expanded
  (see below), and the result is then written to a file of the same name,
  but with `.nancy` removed, in the corresponding place in the output
  directory.
+ Else, if the name contains the suffix `.in`, the file is skipped. (It may
  be used by macros in other files.)
+ Otherwise, the file is copied verbatim to the corresponding place in the
  output.

Files and directories in the output have the same name as in the input tree,
except for the root directory (or file), which is called `OUTPUT`.

The special suffixes need not end the file name; they can be used as infixes
before the file type suffix.

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

1. Scan the text for commands. Expand any arguments to the command, run each
   command, and replace the command by the result, eliding any final
   newline. (This elision may look tricky, but it almost always does what
   you want, and makes `$include` behave better in various contexts.)
2. Output the resultant text.

A command takes the form `$COMMAND` or `$COMMAND{ARGUMENT, ...}`.

### Built-in commands

Nancy recognises these commands:

* *`$include{FILE}`* Look up the given source file in the input tree (see
  below); read its contents, then expand them (that is, execute any commands
  it contains) and return the result.
* *`$paste{FILE}`* Like `$include`, but does not expand its result before
  returning it.
* *`$path`* Expands to the file currently being expanded, relative to the
  input tree.
* *`$realpath`* Expands to the real path of the file currently being
    expanded.

The last two commands are mostly useful as arguments to external programs
(see below).

To find the file specified by a `$include{FILE}` command, Nancy proceeds
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

### Running other programs

In addition to the rules given above, Nancy also allows `$include` and
`$paste` to take their input from programs. This can be useful in a variety
of ways: to insert the current date or time, to make a calculation, or to
convert a file to a different format.

Nancy can run a program in two ways:

1. If a file found by an `$include` or `$paste` command has the “execute”
   permission, it is run.

2. If no file of the given name can be found using the rules in the previous
   section, Nancy looks for an executable file on the user’s `PATH` (the
   list of directories specified by the `PATH` environment variable). If one
   is found, it is run.

In either case, arguments may be passed to the program: use
`$include{FILE,ARGUMENT_1,ARGUMENT_2,…}`, or the equivalent for `$paste`.

For example, to insert the current date:

```
$paste{date,+%Y-%m-%d}
```

See the [date example](Cookbook.md#date-example) in the Cookbook for more
detail.

When commands that run programs are nested inside each other, the order in
which they are run may matter. Nancy only guarantees that if one command is
nested inside another, the inner command will be processed first.

[FIXME]: # (Add example where this is significant)

### Escaping

To prevent a comma from being interpreted as an argument separator, put a
backslash in front of it:

```
$include{cat,I\, Robot.txt,3 Rules of Robotics.txt}
```

This will run the `$include` command with the following arguments:

1. `cat`
2. `I, Robot.txt`
3. `3 Rules of Robotics.txt`

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
