# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

© 2002–2021 Reuben Thomas <rrt@sc3d.org>  
<https://github.com/rrthomas/nancy>

Nancy is a simple macro processor that copies a file or directory, filling
in templates as it goes. It has just one non-trivial construct:
context-dependent file inclusion. A file can either be included literally,
or run as a command and its output included.

Nancy was originally designed to build simple static web sites, but can be
used for all sorts of other tasks, similar to more complicated systems like
[AutoGen] and [TXR].

[AutoGen]: http://autogen.sourceforge.net
[TXR]: http://www.nongnu.org/txr

Nancy is free software, licensed under the GNU GPL version 3 (or, at your
option, any later version), and written in TypeScript.

See the [Cookbook](Cookbook.md) for examples.

Please send questions, comments, and bug reports to the maintainer, or
report them on the project’s web page (see above for addresses).

## Installation

Install Nancy with npm (part of [Node](https://nodejs.org/en/)):

```
$ npm install -g @sc3d/nancy
```

## Invocation

```
$paste{/bin/sh,-c,./bin/run --help | sed -e 's/usage: run/nancy/'}
```

## Operation <a name="operation"></a>

Nancy starts by combining the list of directories given as its _input path_.
If the same file or directory exists in more than one of the directories on
the input path, the left-most takes precedence.

Nancy then creates the output directory, deleting its contents if it already
existed.

Next, Nancy traverses the resulting directory tree, or the subdirectory
given by the `--path` argument, if any.

For each file, Nancy looks at its name, and:

+ If the name contains the suffix `.nancy`, the file’s contents is expanded
  (see below), and the result is then written to a file of the same name,
  but with the `.nancy` suffix removed, in the corresponding place in the
  output directory.
+ Else, if the name contains the suffix `.in`, the file is skipped. (It may
  be used by macros in other files.)
+ Otherwise, the file is copied verbatim to the corresponding place in the
  output directory.

The special suffixes need not end the file name; they can be used as infixes
before the file type suffix.

### Template expansion

Nancy expands a template file as follows:

1. Scan the text for commands. Expand any arguments to the command, run each
   command, and replace the command by the result.
2. Output the resultant text, eliding any final newline. (This last part may
   look tricky, but it almost always does what you want, and makes
   `\$include` behave better in various contexts.)

A command takes the form `\$COMMAND` or `\$COMMAND{ARGUMENT, ...}`. To
prevent a comma from being interpreted as an argument separator, put a
backslash in front of it:

```
\$include{cat,I\,Robot.txt,3 Rules of Robotics.txt}
```

This will run the command as if it had been typed:

```
cat "I, Robot.txt" "3 Rules of Robotics.txt"
```

Similarly, a command can be treated as literal text by putting a backslash
in front of it:

```
Now I can talk about \\$paste.
```

This will output:

```
Now I can talk about \$paste.
```

Nancy recognises these commands:

* *`\$include{FILE}`* Look up the given source file; read its contents, then
  expand them (that is, execute any commands it contains) and return the
  result.
* *`\$paste{FILE}`* Like `\$include`, but does not expand its result before
  returning it.
* *`\$path`* Expands to the directory containing the file currently being
  expanded.
* *`\$root`* Expands to the `INPUT-PATH` argument.

The last two commands are mostly useful as arguments to `\$include` and
`\$paste`.

To find the file specified by a `\$include{FILE}` command, Nancy proceeds
thus:

1. Set `path` to the directory containing the input file currently being
   expanded.
2. See whether `path/FILE` is a file (or a symbolic link to a file). If so,
   return the file path, unless we are already in the middle of expanding
   this file.
3. If not, remove the last directory from `path` and try again. Keep going
   until `path` is `INPUT-PATH/PATH`.

If no file is found, Nancy stops with an error message.

For example, if `INPUT-PATH` is `/dir`, `PATH` is `foo`, and Nancy is trying
to find `file.html`, starting in the subdirectory `foo/bar/baz`, it will try
the following files, in order:

1. `/dir/foo/bar/baz/file.html`
2. `/dir/foo/bar/file.html`
3. `/dir/foo/file.html`
4. `/dir/file.html`

See the [website example](Cookbook.md#website-example) in the Cookbook for a
worked example.

### Running other programs

In addition to the rules given above, Nancy also allows `\$include` and
`\$paste` to take their input from programs. This can be useful in a variety
of ways: to insert the current date or time, to make a calculation, or to
convert a file to a different format.

Nancy can run a program in two ways:

1. If a file found by an `\$include` or `\$paste` command has the “execute”
   permission, it is run.

2. If no file of the given name can be found using the rules in the previous
   section, Nancy looks for an executable file on the user’s `PATH` (the
   list of directories specified by the `PATH` environment variable), as if
   with the `command -v` command. If one is found, it is run.

In either case, arguments may be passed to the program: use
`\$include{FILE, ARGUMENT_1, ARGUMENT_2, …}`, or the equivalent for `\$paste`.

For example, to insert the current date:

```
\$paste{date,+%Y-%m-%d}
```

See the [date example](Cookbook.md#date-example) in the Cookbook for more
detail.

When commands that run programs are nested inside each other, the order in
which they are run may matter. Nancy only guarantees that if one command is
nested inside another, the inner command will be processed first. There is
no guarantee of the order in which commands at the same nesting level are
run.

[FIXME]: # (Add example where this is significant)

## Development

Check out the git repository and download dependencies with:

```
git clone https://github.com/rrthomas/nancy
npm install
```

In addition, [agrep](https://www.tgries.de/agrep/) is required to build the
documentation.

To run the tests:

```
npm test
```