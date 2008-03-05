#! /usr/bin/perl -w
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2008 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License
END

use strict;
use warnings;

use Scalar::Util;
use File::Basename;
use File::Spec::Unix;
use Getopt::Long;

my $suffix = ".html"; # suffix to make source directory into destination file

# FIXME: We assume that the OS can handle UNIX-style paths to make the
# $page command work; we should use File::Spec and convert paths into
# URLs. Do this by splitting using the platform's splitdir, then
# rejoining using the File::Spec::Unix joiner.

# Get arguments
my ($version_flag, $help_flag, $list_files_flag);
my $opts = GetOptions(
  "version" => \$version_flag,
  "help" => \$help_flag,
  "list-files" => \$list_files_flag # FIXME: usage message "list files read (on stderr)"
 );
die $version if $version_flag;
dieWithUsage() if !$opts || $#ARGV < 2 || $#ARGV > 3;

sub dieWithUsage {
  my $prog = basename($0);
  die <<'END';
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
$sourceTree = File::Spec::Unix->catfile($sourceRoot, $ARGV[3]) if $ARGV[3];

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

# Search the current path for a file; if found return its name,
# if not, return nil and print a warning.
sub findFile {
  my ($path, $fragment) = @_;
  my $page = $path;
  do {
    my $name = File::Spec::Unix->catfile($path, $fragment);
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
      my $reps = scalar(File::Spec::Unix->splitdir($page)) - 2;
      return File::Spec::Unix->catfile(("..") x $reps) if $reps > 0;
      return ".";
    },
    include => sub {
      my ($fragment) = @_;
      my $name = findFile(File::Spec::Unix->catfile($root, $page), $fragment);
      return readFile($name) if $name;
    },
    run => sub {
      my $cmd = join " ", @_;
      local *PIPE;
      open(PIPE, "$cmd|");
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
  local *DIR;
  opendir DIR, File::Spec::Unix->catfile($root, $path) or die "Could not read directory `" . File::Spec::Unix->catfile($root, $path) . "'";
  for my $object (readdir DIR) {
    subfind($root, File::Spec::Unix->catfile($path, $object), $pred)
      if $object ne File::Spec::Unix->curdir() && $object ne File::Spec::Unix->updir() && &{$pred}($root, File::Spec::Unix->catfile($path, $object)) &&
        -d File::Spec::Unix->catfile($root, $path, $object);
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
       if (-d File::Spec::Unix->catfile($path, $object) && basename($object) ne ".svn") {
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
  my $dest = File::Spec::Unix->catfile($destRoot, $dir);
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
    warn ("`" . File::Spec::Unix->catfile($sourceTree, $dir) . "' has no `index' subdirectory")
      unless $sourceSet{File::Spec::Unix->catfile($dir, "index")};
  }
  $i++;
}
