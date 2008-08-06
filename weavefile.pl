#! /usr/bin/perl
my $version = <<'END';
weavefile $Revision$ ($Date$)
(c) 2002-2008 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use strict;
use warnings;

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);
use Getopt::Long;


# Get arguments
my ($version_flag, $help_flag, $list_files_flag);
my $prog = basename($0);
my $opts = GetOptions(
  "list-files" => \$list_files_flag,
  "version" => \$version_flag,
  "help" => \$help_flag,
 );
die $version if $version_flag;
dieWithUsage() if !$opts || $#ARGV != 2;

sub dieWithUsage {
  die <<END;
Usage: $prog SOURCE DIRECTORY TEMPLATE
The lazy web site maker

  --list-files, -l  list files read (on stderr)
  --version, -v     show program version
  --help, -h, -?    show this help

  SOURCE is the source directory tree
  DIRECTORY is the sub-directory to build into a file
  TEMPLATE is the name of the template fragment
END
}

# FIXME: Use a module to add the boilerplate to the messages
sub Die {
  my ($message) = @_;
  die "$prog: $message\n";
}

sub Warn {
  my ($message) = @_;
  warn "$prog: $message\n";
}

Die("No source tree given") unless $ARGV[0];
my $source = $ARGV[0];
Die("`$source' not found or is not a directory") unless -d $source;
my $directory = $ARGV[1];
my $template = $ARGV[2];

# Read the given file and return its contents
# An undefined value is returned if the file can't be opened or read
sub readFile {
  my ($file) = @_;
  local *FILE;
  open FILE, "<", $file or return;
  my $text = do {local $/, <FILE>};
  close FILE;
  return $text;
}

# Search tree for a file starting at the given path; if found return
# its name, if not, print a warning and return undef.
sub findFile {
  my ($tree, $path, $file) = @_;
  my $search_path = $path;
  while (1) {
    my $name = catfile($tree, $search_path, $file);
    if (-e $name) {
      print STDERR "  $name\n" if $list_files_flag;
      return $name;
    }
    last if $search_path eq "." || $search_path eq "/"; # Keep going until we go above $path
    $search_path = dirname($search_path);
  }
  Warn "Cannot find `$file' while building `$path'";
  return undef;
}

# Process a command; if the command is undefined, replace it, uppercased
sub doMacro {
  my ($macro, $arg, %macros) = @_;
  if (defined($macros{$macro})) {
    my @arg = split /(?<!\\),/, ($arg || "");
    return $macros{$macro}(@arg);
  } else {
    $macro =~ s/^(.)/\u$1/;
    return "\$$macro\{$arg}";
  }
}

# Process commands in some text
sub doMacros {
  my ($text, %macros) = @_;
  1 while $text =~ s/\$([[:lower:]]+){(((?:(?!(?<!\\)[{}])).)*?)(?<!\\)}/doMacro($1, $2, %macros)/ge;
  return $text;
}

# Expand commands in some text
sub expand {
  my ($text, $tree, $page) = @_;
  my %macros = (
    page => sub {
      my @url = splitdir($page);
      return join "/", @url;
    },
    root => sub {
      my $reps = scalar(splitdir($page)) - 1;
      return join "/", (("..") x $reps) if $reps > 0;
      return ".";
    },
    include => sub {
      my ($fragment) = @_;
      my $name = findFile($tree, $page, $fragment);
      return readFile($name) if $name;
      return "";
    },
    run => sub {
      my $cmd = '"' . (join '" "', @_) . '"';
      local *PIPE;
      open(PIPE, "-|", $cmd);
      my $text = do {local $/, <PIPE>};
      close PIPE;
      return $text;
    },
  );
  $text = doMacros($text, %macros);
  # Convert $Macro back to $macro
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;
  return $text;
}

# Process one page
print STDERR "$directory:\n" if $list_files_flag;
print STDOUT expand("\$include{$template}", $source, $directory);
print STDERR "\n" if $list_files_flag;
