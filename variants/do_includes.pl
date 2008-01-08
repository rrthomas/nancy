#! /usr/bin/perl -w
# Simple file inclusion processor
# (c) 2002-2006 Reuben Thomas (rrt@sc3d.org, http://rrt.sc3d.org)
# Distributed under the GNU General Public License

use utf8;
use encoding 'utf8';
use strict;
use warnings;

use File::Basename;
use Cwd;


# Macros (supplied by caller)
use vars qw(%Macros);

%Macros =
  (
   include => sub {
     my ($file) = @_;
     our ($path, $indent);
     my $text;
     my $curdir = $path;
     do {
       $text = readFile("$curdir/$file");
       $curdir = dirname($curdir);
     } while (!defined($text) && $curdir ne "" && $curdir ne ".");
     # Don't use || below because empty string counts as false
     $text = readFile("$file") if !defined($text);
     die "Can't find file $file" if !defined($text);
     $text =~ s/^/$indent/gme;
     return $text;
   }
  );

# Read the given file and return its contents
# An undefined value is returned if the file can't be opened or read
sub readFile {
  my ($file) = @_;
  open FILE, "<:utf8", $file or return;
  my $text = do {local $/, <FILE>};
  close FILE;
  return $text;
}

# Process a single macro call; if the macro is undefined, replace it, uppercased
sub doMacro {
  my ($macro, $arg) = @_;
  our $indent = $_[2];
  my @arg = split /(?<!\\),/, ($arg || "");
  return $Macros{$macro}(@arg) if $Macros{$macro};
  $macro =~ s/^(.)/\u$1/;
  return "\$$macro\{$arg}";
}

# Process macros in some text
sub expand {
  my ($text) = shift;
  %Macros = %{shift()};
  1 while $text =~ s/([ \t]*)\$([[:lower:]]+)(?:{((?:(?!(?<!\\)[{}]).)*)(?<!\\)})/doMacro($2, $3, $1)/ge;
  return $text;
}


# Get parameters name to process
if ($#ARGV == -1) {
  my $prog = basename($0);
  die
    "Usage: $prog ROOT PATH FILE\n",
"  ROOT is the root directory for the file tree\n",
"  PATH is the inheritance path to use\n",
"  FILE is the file to process\n"
}
my $root = shift || die "No root given";
our $path = shift || die "No path given";
my $file = shift || die "No file given";

# Process file
our $indent = "";
chdir($root);
my $tmpl = $Macros{include}($file);
print expand($tmpl, \%Macros);
