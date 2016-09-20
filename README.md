# Nancy

![logo](logo/nancy-small.png) _logo by Silvia Polverini_

© 2002–2016 Reuben Thomas <rrt@sc3d.org>  
https://github.com/rrthomas/nancy

Nancy is a simple file weaver. It has just one non-trivial construct:
context-dependent file inclusion. A file can either be included literally,
or run as a command and its output included.

Nancy was originally designed to build simple static web sites, but can be used for all sorts of other tasks, similar to more complicated systems like [AutoGen](http://autogen.sourceforge.net) and [TXR](http://www.nongnu.org/txr).

Nancy is free software, licensed under the GNU GPL version 3 (or, at
your option, any later version), and written in Perl.

See [the user guide](Nancy user's guide.pdf) for instructions and examples.

Please send questions, comments, and bug reports to the maintainer, or
report them on the project’s web page (see above for addresses).

## Development

Check out the git repository with:

    git clone --recursive https://github.com/rrthomas/nancy

After checkout, run `./setup-git-config` to wire up writing version numbers into scripts.

To build Nancy and run its tests:

    make check

To make releases, zip and [woger] are needed.

[woger]: https://github.com/rrthomas/woger