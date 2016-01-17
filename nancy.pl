#!/usr/bin/perl
# Lazy person's web site generator
# (c) 2002-2013 Reuben Thomas (rrt@sc3d.org, http://rrt.sc3d.org)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

use strict;
use warnings;

use File::Spec::Functions qw(splitdir catfile);
use File::Glob qw(:bsd_glob);
use CGI qw(:standard);
use CGI::Util qw(unescape);

use File::Slurp qw(slurp);
use File::MimeInfo;

# Configuration variables
my $BaseUrl = $ENV{NANCY_WEB_ROOT};
$BaseUrl = "/$BaseUrl" unless $BaseUrl =~ m|^/|;
my $BaseDir = bsd_glob($ENV{NANCY_FILE_ROOT});
my $Template = $ENV{NANCY_TEMPLATE} || "template";
my $Index = $ENV{NANCY_INDEX} || "index.html";
my $ListFiles = $ENV{NANCY_LIST_FILES};

# Extract file name from URL
my $page = unescape(url(-absolute => 1));
$page =~ s|^$BaseUrl||;

# Extract site name and page name to calculate source roots
$page =~ s|/$||;
my @path = splitdir($page);
my $site = shift @path || "";

# Read source roots, and sort lexically
my $root = catfile($BaseDir, $site);
opendir(my $dh, $root) || die "cannot read `$root': $!";
my @source_roots = map { catfile($root, $_) } sort {$b cmp $a} (grep {/^[^.]/} readdir($dh));
closedir $dh;

# File object in multiple source trees
sub find_in_trees {
  my ($path, $roots, $test) = @_;
  $test ||= sub { return -f shift; };
  foreach my $root (@{$roots}) {
    my $obj = catfile($root, @{$path});
    return $obj if &{$test}($obj);
  }
  return undef;
}

# Search for file starting at the given path; if found return its file
# name and contents; if not, print a warning and return undef.
sub find_on_path {
  my ($path, $file, @roots) = @_;
  my @file = (split "/", $file);
  my @search = @{$path};
  while ($file[0] eq "..") {
    shift @file;
    pop @search;
  }
  for (;; pop @search) {
    my $thissearch = [@search, @file];
    my $node = find_in_trees($thissearch, \@roots);
    if (defined($node)) {
      print STDERR "  $node\n" if $ListFiles;
      return $thissearch, scalar(slurp($node, {binmode => ':raw'}));
    }
    last if $#search == -1;
  }
  warn "Cannot find `$file' while building `" . catfile(@{$path}) ."'\n";
}

# Process a command; if the command is undefined, replace it, uppercased
sub do_macro {
  my ($macro, $arg, %macros) = @_;
  return $macros{$macro}(split /(?<!\\),/, ($arg || ""))
    if defined($macros{$macro});
  $macro =~ s/^(.)/\u$1/;
  return "\$$macro\{$arg}";
}

# Process commands in some text
sub do_macros {
  my ($text, %macros) = @_;
  1 while $text =~ s/\$([[:lower:]]+){(((?:(?!(?<!\\)[{}])).)*?)(?<!\\)}/do_macro($1, $2, %macros)/ge;
  return $text;
}

# Expand commands in some text
#   $text - text to expand
#   $path - directory to make into a page
#   @roots - list of roots of trees to scan
# returns expanded text
sub expand {
  my ($text, $path, @roots) = @_;
  my %macros = (
    root => sub {
      return join "/", (("..") x $#{$path}) if $#{$path} > 0;
      return ".";
    },
    include => sub {
      my ($leaf) = @_;
      my ($file, $contents) = find_on_path($path, $leaf, @roots);
      return $file ? $contents : "";
    },
    run => sub {
      my ($prog) = shift;
      my ($file, $contents) = find_on_path($path, $prog, @roots);
      return $file ? &{eval($contents)}(@_, $path, @roots) : "";
    },
  );
  $text = do_macros($text, %macros);
  # Convert `$Macro' back to `$macro'
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;

  return $text;
}

# Process request
my $headers = {-type => "application/xhtml+xml", -charset => "utf-8"};
$path[$#path] =~ m/(\.\w+)$/;
my $ext = $1 || "";
my $node = find_in_trees(\@path, \@source_roots, sub { return -e shift; });
if ($node) {
  if (-f $node) { # If a file, serve it
    print header(-type => mimetype($page)) . slurp($node);
    exit;
  } elsif (-d $node && $ext eq "") {
    push @path, $Index;
    print redirect("$BaseUrl$site/" . (join "/", @path));
    exit;
  }
} else { # If not found, give a 404
  ($Template, $ext) = ("404", ".xhtml");
  $headers->{"-status"} = 404;
}

# Output page
print STDERR catfile(@path) . "\n" if $ListFiles;
binmode(STDOUT, ":raw");
print STDOUT header($headers) . expand("\$include{$Template$ext}", \@path, @source_roots);
