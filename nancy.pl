#! /usr/bin/perl -w
# nancy
# The lazy web site maker
# (c) 2002-2008 Reuben Thomas (rrt@sc3d.org, http://rrt.sc3d.org)
# Distributed under the GNU General Public License

use strict;
use warnings;

use Scalar::Util;
use File::Basename;
use File::Spec::Functions qw(:ALL);
use Getopt::Long;

use vars qw(%Macros);

my $suffix = ".html"; # suffix to make source directory into destination file

# Get arguments
my ($version_flag, $help_flag, $list_files_flag);
dieWithUsage() unless GetOptions(
  "version" => \$version_flag,
  "help" => \$help_flag,
  "list-files" => \$list_files_flag # FIXME: usage message "list files read (on stderr)"
 ) && $#ARGV >= 2 && $#ARGV <= 3;

sub dieWithUsage {
  my $prog = basename($0);
  die <<END;
Usage: $prog SOURCE DESTINATION TEMPLATE [BRANCH]
The lazy web site maker

  -list-files, -l  list files read (on stderr)
  -version, -v     show program version
  -help, -h, -?    show this help

  SOURCE is the source directory tree
  DESTINATION is the directory to which the output is written
  TEMPLATE is the name of the template fragment
  BRANCH is the sub-directory of SOURCE to process (the default
    is to process the entire source tree)
END
}

my $sourceRoot = $ARGV[0];
die "`$sourceRoot' not found or not a directory"
  unless -d $sourceRoot;
my $destRoot = $ARGV[1];
die "`$destRoot' is not a directory"
  if -e $destRoot && !-d $destRoot;
my $fragment = $ARGV[2];
my $sourceTree = $sourceRoot;
$sourceTree = catfile($sourceRoot, $ARGV[3]) if $ARGV[3];

# Read the given file and return its contents
# An undefined value is returned if the file can't be opened or read
sub readFile {
  my ($file) = @_;
  open FILE, "<", $file or return;
  my $text = do {local $/, <FILE>};
  close FILE;
  return $text;
}

# Search the current path for a file; if found return its name,
# if not, return nil and print a warning.
sub findFile {
  my ($path, $fragment) = @_;
  my $page = $path;
  do {
    my $name = catfile($path, $fragment);
    if (-e $name) {
      print STDERR " $name" if $list_files_flag;
      return $name;
    }
    if ($path eq ".") {
      warn "Cannot find fragment `$fragment' while building `$page'";
      return;
    }
    $path = dirname($path);
  } while (1);
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
  my ($text, $root, $page) = @_;
  my %macros = (
    page => sub {
      return $page;
    },
    root => sub {
      my $reps = scalar(splitdir($page)) - 2;
      return catfile(("..") x $reps) if $reps > 0;
      return ".";
    },
    include => sub {
      my ($fragment) = @_;
      my $name = findFile(catfile($root, $page), $fragment);
      return readFile($name) if $name;
    },
    run => sub {
      open(PIPE, "-|") || exec @_;
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

# find: Scan a file system object and process its elements
#   root: root path to scan
#   pred: function to apply to each element
#     root: as above
#     object: relative path from root to object
#   returns
#     flag: true to descend if object is a directory
sub subfind {
  my ($root, $path, $pred) = @_;
  opendir DIR, catfile($root, $path) or die "Could not read directory `" . catfile($root, $path) . "'";
  for my $object (readdir DIR) {
    subfind($root, catfile($path, $object), $pred)
      if $object ne "." && $object ne ".." && &{$pred}($root, catfile($path, $object)) &&
        -d catfile($root, $path, $object);
  }
  closedir DIR;
}
sub find {
  my ($root, $pred) = @_;
  &{$pred}($root, "");
  subfind($root, "", $pred);
}

# Get source directories and destination files
# FIXME: Make exclusion easily extensible, and add patterns for
# common VCSs (use find's --exclude-vcs patterns) and editor backup
# files &c.
my @sources = ();
find($sourceTree,
     sub {
       my ($path, $object) = @_;
       if (-d catfile($path, $object) && basename($object) ne ".svn") {
         push @sources, $object;
         return 1;
       }
       return undef;
     });
my %sourceSet = map { $_ => 1 } @sources;

# Sort the sources for the "is leaf" check
@sources = sort @sources;

# Process source directories
my $i = 0;
foreach my $dir (@sources) {
  my $dest = catfile($destRoot, $dir);
  # Only leaf directories correspond to pages; the sources are sorted
  # alphabetically, so a directory is not a leaf if and only if it is
  # either the last directory, or it is not a prefix of the next one
  if ($dir ne "" && ($i == $#sources || substr($sources[$i + 1], 0, length($dir) + 1) ne "$dir/")) {
    # Process one file
    print STDERR "$dir:\n" if $list_files_flag;
    open OUT, ">$dest$suffix" or die "Could not write to `$dest'";
    print OUT expand("\$include{$fragment}", $sourceTree, $dir);
    print STDERR "\n" if $list_files_flag;
  } else { # non-leaf directory
    # FIXME: If directory is called `index', complain
    # Make directory
    mkdir $dest;

    # Check we have an index subdirectory
    warn ("`" . catfile($sourceTree, $dir) . "' has no `index' subdirectory")
      unless $sourceSet{catfile($dir, "index")};
  }
  $i++;
}
