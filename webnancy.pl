#!/usr/bin/perl -T
# Web wrapper for Nancy
# (c) 2002-2009 Reuben Thomas (rrt@sc3d.org, http://rrt.sc3d.org)
# Distributed under the GNU General Public License

use strict;
use warnings;

use Perl6::Slurp;
use File::Spec::Functions qw(catfile);
use CGI qw(:standard);
use CGI::Util qw(unescape);

# Root of site relative to root of server
my $BaseUrl = "/";
# Root of source files
my $DocumentRoot = "/var/www";

my $template = "template.html";

# Extract file name from URL
my $page = unescape(url(-absolute => 1));
$page =~ s|^$BaseUrl/?||;
$page =~ s|\.html$||;
$page = "index" if $page eq "";
$template = "404.html" if !-d catfile($DocumentRoot, $page);

# Perform the request
open(IN, "-|", "weavefile.pl", $DocumentRoot, $page, $template);
print header() . (slurp \*IN);
