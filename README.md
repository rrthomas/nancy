# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

© 2002–2016 Reuben Thomas <rrt@sc3d.org>  
https://github.com/rrthomas/nancy

Nancy is a simple macro processor that fills in a template from other files and the output of programs. It has just one non-trivial construct:
context-dependent file inclusion. A file can either be included literally,
or run as a command and its output included.

Nancy was originally designed to build simple static web sites, but can be used for all sorts of other tasks, similar to more complicated systems like [AutoGen] and [TXR].

[AutoGen]: http://autogen.sourceforge.net
[TXR]: http://www.nongnu.org/txr

Nancy is free software, licensed under the GNU GPL version 3 (or, at
your option, any later version), and written in Perl.

See the [Cookbook](Nancy cookbook.pdf) for instructions and examples.

Please send questions, comments, and bug reports to the maintainer, or
report them on the project’s web page (see above for addresses).

# Installation

Nancy is written in Perl, and requires version 5.10 or later, and the `File::Slurp` and `File::Which` modules, which can be installed with the following commands, assuming you have Perl:

    cpan File::Slurp
    cpan File::Which

(Many GNU/Linux systems package these modules natively.)

To install Nancy, unpack the distribution archive and copy the `nancy` script to a directory on your path.

# Invocation

Nancy takes two arguments:

    nancy [OPTION...] TEMPLATE PATH

where `TEMPLATE` is name of the template file, and `PATH` is the path of the file or directory to build. There is nothing special about the template file, it is just the source file with which Nancy starts.

The following command-line `OPTION`s may be given:

* *`--output FILE`* Set the name of the output file (the default is standard output).
* *`--root DIRECTORY`* Set the root source directory (the default is the current directory). This is the directory that Nancy will search for source files.
* *`--verbose`* Print to standard error the name of the file being generated, and the files used to make it.
* *`--version`* Show the version number of Nancy.
* *`--help`* Show help on how to run Nancy.

The options may be abbreviated to any unambiguous prefix.

# Operation

Nancy builds a path given a template as follows:

1. Set the initial text to `$include{TEMPLATE}`, unless `TEMPLATE` is `-`, in which case set the initial text to the contents of standard input.
2. Scan the text for commands. Expand any arguments to the command, run each command, and replace the command by the result.
3. Output the resultant text, eliding any final newline. (This last part may look tricky, but it almost always does what you want, and makes `$include` behave better in various contexts.)

A command takes the form `$COMMAND` or `$COMMAND{ARGUMENT, ...}`.

Nancy recognises these commands:

* *`$include{FILE, ARGUMENT, ...}`* Look up the given source file. If it is executable, run it as a command with the given arguments and collect the output. Otherwise, read the contents of the given file. Expand and return the result.
* *`$paste{FILE, ARGUMENT, ...}`* Like `$include`, but does not expand its result before returning it.
* *`$path`* Return the `PATH` argument.
* *`$root`* Return the root directory.
* *`$template`* Return the `TEMPLATE` argument.

The last three commands are mostly useful as arguments to `$include`.

Only one guarantee is made about the order in which commands are processed: if one command is nested inside another, the inner command will be processed first. (The order only matters for `$include` commands that run executables; if you nest them, you have to deal with this potential pitfall.)

To find the source file `FILE` specified by a `$include{FILE, ...}` command, Nancy proceeds thus:

1. See whether `ROOT/PATH/FILE` is a file (or a symbolic link to a file). If so, return the file path.
2. If not, remove the last directory from `PATH` and try again, until `PATH` is empty.
3. Try looking for `ROOT/FILE`.
4. Try looking for the file on the user’s `PATH` (the list of directories specified by the `PATH` environment variable).
5. If no file is found, Nancy stops with an error message.

For example, if the root directory is `/dir`, `PATH` is `foo/bar/baz`, and Nancy is trying to find `file.html`, it will try the following files, in order:

1. `/dir/foo/bar/baz/file.html`
2. `/dir/foo/bar/file.html`
3. `/dir/foo/file.html`
4. `/dir/file.html`
5. An executable called `file.html` somewhere on the user’s `PATH`. (This is not very likely, since executables don’t normally end in `.html`.)

## Development

Check out the git repository with:

    git clone --recursive https://github.com/rrthomas/nancy

After checkout, run `./setup-git-config` to wire up writing version numbers into scripts.

To build Nancy and run its tests:

    make check

To make releases, zip and [woger] are needed.

[woger]: https://github.com/rrthomas/woger