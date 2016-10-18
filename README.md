# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

© 2002–2016 Reuben Thomas <rrt@sc3d.org>  
<https://github.com/rrthomas/nancy>

Nancy is a simple macro processor that fills in a template from other files
and the output of programs. It has just one non-trivial construct:
context-dependent file inclusion. A file can either be included literally,
or run as a command and its output included.

Nancy was originally designed to build simple static web sites, but can be
used for all sorts of other tasks, similar to more complicated systems like
[AutoGen] and [TXR].

[AutoGen]: http://autogen.sourceforge.net
[TXR]: http://www.nongnu.org/txr

Nancy is free software, licensed under the GNU GPL version 3 (or, at your
option, any later version), and written in Perl.

See the [Cookbook](Cookbook.md) for instructions and examples.

Please send questions, comments, and bug reports to the maintainer, or
report them on the project’s web page (see above for addresses).

## Installation

Download the latest release from
​<https://github.com/rrthomas/nancy/releases>.

Nancy is written in Perl, and requires version 5.10 or later, and the
`File::Slurp` and `File::Which` modules, which can be installed with the
following commands, assuming you have Perl:

    cpan File::Slurp File::Which

(Many GNU/Linux systems package these modules natively.)

To install Nancy, unpack the distribution archive and copy the `nancy`
script to a directory on your path.

## Invocation

Nancy takes two arguments:

    nancy [OPTION...] TEMPLATE PATH

where `TEMPLATE` is name of the template file, and `PATH` is the path of the
file or directory to build. There is nothing special about the template
file, it is just the source file with which Nancy starts.

The following command-line `OPTION`s may be given:

* *`--output FILE`* Set the name of the output file (the default is standard
  output).
* *`--root DIRECTORY`* Set the root source directory (the default is the
  current directory). This is the directory that Nancy will search for
  source files.
* *`--verbose`* Print to standard error the name of the file being
  generated, and the files used to make it.
* *`--version`* Show the version number of Nancy.
* *`--help`* Show help on how to run Nancy.

The options may be abbreviated to any unambiguous prefix.

## Operation <a name="operation"></a>

Nancy builds a path given a template as follows:

1. Set the initial text to `$include{TEMPLATE}`, unless `TEMPLATE` is `-`,
   in which case set the initial text to the contents of standard input.
2. Scan the text for commands. Expand any arguments to the command, run each
   command, and replace the command by the result.
3. Output the resultant text, eliding any final newline. (This last part may
   look tricky, but it almost always does what you want, and makes
   `$include` behave better in various contexts.)

A command takes the form `$COMMAND` or `$COMMAND{ARGUMENT, ...}`. To prevent
a comma from being interpreted as an argument separator, put a backslash in
front of it:

    $include{cat,I\,Robot.txt,3 Rules of Robotics.txt}

Similarly, a command can be treated as literal text by putting a backslash in front of it:

    Now I can talk about \$paste.

Nancy recognises these commands:

* *`$include{FILE}`* Look up the given source file; read its contents, then
  expand them (that is, execute any commands found therein) and return the
  result.
* *`$paste{FILE}`* Like `$include`, but does not expand its result before
  returning it.
* *`$path`* Return the `PATH` argument.
* *`$root`* Return the root directory.
* *`$template`* Return the `TEMPLATE` argument.

The last three commands are mostly useful as arguments to `$include` and
`$paste`.

To find the source file `FILE` specified by a `$include{FILE}` command,
Nancy proceeds thus:

1. See whether `ROOT/PATH/FILE` is a file (or a symbolic link to a file). If
   so, return the file path.
2. If not, remove the last directory from `PATH` and try again, until `PATH`
   is empty.
3. Try looking for `ROOT/FILE`.

If no file is found, Nancy stops with an error message.

For example, if the root directory is `/dir`, `PATH` is `foo/bar/baz`, and
Nancy is trying to find `file.html`, it will try the following files, in
order:

1. `/dir/foo/bar/baz/file.html`
2. `/dir/foo/bar/file.html`
3. `/dir/foo/file.html`
4. `/dir/file.html`

There is one exception to this rule: if the file being searched for has the same name as the file currently being expanded, then the search starts at the next directory up. This avoids an endless loop, and can also be useful.

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
   list of directories specified by the `PATH` environment variable), as if
   with the `which` command. If one is found, it is run. (This possibility
   was not mentioned in the example above, but it is not very likely that
   Nancy will find a file called `file.html` somewhere on the user’s `PATH`,
   since executables don’t normally end in `.html`.)

In either case, arguments may be passed to the program: use `$include{FILE,
ARGUMENT_1, ARGUMENT_2, …}`, or the equivalent for `$paste`.

For example, to insert the current date:

    $paste{date,+%Y-%m-%d}

[FIXME]: # (Insert cross-ref to date example here)

When commands that run programs are nested inside each other, the order in
which they are run may matter. Nancy only guarantees that if one command is
nested inside another, the inner command will be processed first. There is
no guarantee of the order in which commands at the same nesting level are
run.

[FIXME]: # (Add example where this is significant)

## Development

Check out the git repository with:

    git clone --recursive https://github.com/rrthomas/nancy

After checkout, run `./setup-git-config` to wire up writing version numbers
into scripts.

To build Nancy and run its tests:

    make check

To make releases, zip and [woger] are needed.

[woger]: https://github.com/rrthomas/woger
