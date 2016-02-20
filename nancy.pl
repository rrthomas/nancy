#!/usr/bin/perl
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2016 Reuben Thomas <rrt@sc3d.org>
https://github.com/rrthomas/nancy/
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use 5.10.0;
use strict;
use warnings;

use File::Spec::Functions qw(splitdir catfile);
use File::Basename;
use Getopt::Long;
use Cwd;

use File::Slurp qw(slurp);

# Get arguments
my ($list_files_flag, $root, $version_flag, $help_flag);
my $prog = basename($0);
my $opts = GetOptions(
  "list-files" => \$list_files_flag,
  "root=s" => \$root,
  "version" => \$version_flag,
  "help" => \$help_flag,
 );
die $version if $version_flag;
die <<END if !$opts || $#ARGV != 1;
Usage: $prog [OPTION...] PATH TEMPLATE
The lazy web site maker

  --list-files      list files read (on standard error)
  --root DIRECTORY  source root directory [default is current directory]
  --version         show program version
  --help            show this help

  PATH is the desired path to weave
  TEMPLATE is the template file
END

# FIXME: Use a module to add the boilerplate to the messages
sub Die {
  my ($message, $code) = @_;
  print STDERR "$prog: $message\n";
  exit $code || 1;
}

# Get file and template, and compute root and object
my $path = $ARGV[0];
my $template = $ARGV[1];
my @path = splitdir($path);
$root ||= cwd();

# Find object in a source tree
sub find_in_tree {
  my ($path, $root, $test) = @_;
  $test ||= sub { return -f shift; };
  my $obj = catfile($root, @{$path});
  return $obj if &{$test}($obj);
  return undef;
}

# Search for file starting at the given path; if found return its file
# name and contents; if not, print a warning and return undef.
sub find_on_path {
  my ($path, $file, $root) = @_;
  my @file = (split "/", $file);
  my @search = @{$path};
  while ($file[0] eq "..") {
    shift @file;
    pop @search;
  }
  for (;; pop @search) {
    my $thissearch = [@search, @file];
    my $obj = find_in_tree($thissearch, $root);
    if (defined($obj)) {
      print STDERR "  $obj\n" if $list_files_flag;
      return scalar(slurp($obj, {binmode => ':raw'}));
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
#   $root - root of tree to scan
# returns expanded text
sub expand {
  my ($text, $path, $root) = @_;
  my %macros = (
    root => sub {
      return join "/", (("..") x $#{$path}) if $#{$path} > 0;
      return ".";
    },
    include => sub {
      my ($leaf) = @_;
      return find_on_path($path, $leaf, $root) || "";
    },
    run => sub {
      my ($prog) = shift;
      my ($contents) = find_on_path($path, $prog, $root);
      return $contents ? &{eval($contents)}(@_, $path, $root) : "";
    },
  );
  $text = do_macros($text, %macros);
  # Convert `$Macro' back to `$macro'
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;

  return $text;
}

# Process file
my $obj = find_in_tree(\@path, $root, sub { return -e shift; })
  or Die("`$path' not found");
print STDOUT expand("\$include{$template}", \@path, $root);
