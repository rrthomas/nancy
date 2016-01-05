# Nancy

![logo](logo/nancy-small.png) _picture by Silvia Polverini_

© 2002–2013 Reuben Thomas <rrt@sc3d.org>  
https://github.com/rrthomas/nancy

Nancy is a simple web site builder. It has just one non-trivial
construct: context-dependent file inclusion. With this single feature
you can build pretty much any web site whose logical structure mirrors
its URL layout, and which does not rely on dynamically computed content,
out of fragments (of HTML, CSS, text, and whatever else you like) plus
other files (images, audio &c.). Instead of including a file, you can
run a Perl subroutine; this allows you to do anything else you might
want.

Nancy builds pages on the fly as a CGI script, but of course static
copies for high-traffic or offline use can easily be produced by
mirroring.

Nancy is free software, licensed under the GNU GPL version 3 (or, at
your option, any later version), and written in Perl.

See [the user guide](Nancy user's guide.pdf) for instructions.

Please send questions, comments, and bug reports to the maintainer, or
report them on the project’s web page (see above for addresses).

To install Nancy, copy `nancy.pl` to a CGI script directory, and
configure the web server to pass all URLs for the site to the script.
Copy 404.html to the top of the site. Configuration for Apache (in an
`.htaccess` file) looks something like this:

    # Direct URLs to Nancy
    RewriteEngine on
    RewriteRule ^$ /ROOT/cgi-bin/webnancy.pl
    RewriteRule ^(.*)\.html$ /ROOT/cgi-bin/webnancy.pl

## History

I gave a talk about an early version of Nancy at the
[Lua Workshop 2006](https://www.lua.org/wshop06.html). (Back then it was
written in Lua!)

* [PDF slides](Lua Workshop 2006.pdf)
* [OpenOffice Impress presentation](Lua Workshop 2006.odp)
* [Video](https://youtube.com/watch?v=-QDRQXK9VFE)
