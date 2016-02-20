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

use RRT::Macro;

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
  die "$prog: $_[0]\n";
}

# Get file and template, and compute root and object
my $path = $ARGV[0];
my $template = $ARGV[1];
my @path = splitdir($path);
$root ||= cwd();

# Search for file starting at the given path; if found return its file
# name and contents; if not, die.
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
    my $obj = catfile($root, @{$thissearch});
    if (-f $obj) {
      print STDERR "  $obj\n" if $list_files_flag;
      return $obj;
    }
    last if $#search == -1;
  }
  Die("Cannot find `$file' while building `" . catfile(@{$path}) ."'");
}

my %macros = (
  path => sub { $path; },
  root => sub { $root; },
  template => sub { $template; },
  include => sub {
    my ($leaf) = @_;
    my $file = find_on_path(\@path, $leaf, $root);
    if (defined($file)) {
      if (-x $file) {
        open(READER, "-|", $file, @_);
      } else {
        open(READER, $file);
      }
      binmode(READER, ':raw');
      return scalar(slurp(\*READER));
    }
  }
);

# Weave path
print STDOUT expand("\$include{$template}", \%macros);
