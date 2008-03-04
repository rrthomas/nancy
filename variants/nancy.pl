#! /usr/bin/perl -w
# nancy
# The lazy person's web site maker
# (c) 2002-2006 Reuben Thomas (rrt@sc3d.org, http://rrt.sc3d.org)
# Distributed under the GNU General Public License

use strict;
use warnings;

use Scalar::Util;
use File::Basename;

use vars qw(%Macros);

%Macros =
  (
   include => sub {
     my ($file) = @_;
     our ($path, $indent);
     my ($text, $note);
     my $curdir = $path;
     do {
       $text = readFile("$curdir/$file");
       $note = $curdir = dirname($curdir);
     } while (!defined($text) && $curdir ne "" && $curdir ne ".");
     # Don't use || below because empty string counts as false
     if (!defined($text)) {
       $text = readFile($file);
       die "Can't find file $file" if !defined($text);
       $note = "";
     }
     $text =~ s/^/$indent/gme;
     return $text, " $note";
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

# Process a macro call; if the macro is undefined, replace it, uppercased
sub doMacro {
  my ($macro, $arg, $caller) = @_;
  if (defined($Macros{$macro})) {
    our $indent = $_[3];
    my @arg = split /(?<!\\),/, ($arg || "");
    my @callees = ();
    my ($text, $note) = $Macros{$macro}(@arg);
    $note ||= "";
    1 while $text =~ s/([ \t]*)\$([[:lower:]]+)(?:{((?:(?!(?<!\\)[{}]).)*)(?<!\\)})/doMacro($2, $3, \@callees, $1)/ge;
    push @{$caller}, ["$macro\{$arg}$note", \@callees];
    return $text;
  } else {
    $macro =~ s/^(.)/\u$1/;
    return "\$$macro\{$arg}";
  }
}

# Turn a call forest into a string
sub forestToStr {
  my ($forest, $indent) = @_;
  my $text = "";
  foreach my $call (@{$forest}) {
    my ($caller, $callees) = @{$call};
    $text .= "$indent$caller";
    $text .= "\n" . forestToStr($callees, "$indent  ")
      if Scalar::Util::reftype($callees);
  }
  return $text;
}

# Get parameters name to process
if ($#ARGV == -1) {
  my $prog = basename($0);
  die
    "Usage: $prog ROOT PATH FILE\n",
"Prints the web page on stdout and inclusion graph on stderr\n",
"  ROOT is the root directory for the file tree\n",
"  PATH is the inheritance path to use\n",
"  FILE is the file to process\n"
}
my $root = shift || die "No root given";
our $path = shift || die "No path given";
my $file = shift || die "No file given";

# Process file
chdir $root || die "Root `$root' not found";
my @forest = ();
print STDOUT doMacro("include", $file, \@forest, "");
print STDERR "$root/$path\n";
print STDERR forestToStr(\@forest, "  ");
