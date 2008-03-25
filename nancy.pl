#! /usr/bin/perl -w
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2008 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License
END

use strict;
use warnings;

use Config;
use Scalar::Util;
use File::Basename;
use File::Spec::Unix;
use File::Find;
use Getopt::Long;

my $suffix = ".html"; # suffix to make source directory into destination file

# FIXME: To make $page{} work we assume that the OS can handle
# UNIX-style paths; we should use File::Spec and convert paths into
# URLs. Do this by splitting using the platform's splitdir, then
# rejoining using the File::Spec::Unix joiner.

# Get arguments
my ($version_flag, $help_flag, $list_files_flag);
my $opts = GetOptions(
  "list-files" => \$list_files_flag,
  "version" => \$version_flag,
  "help" => \$help_flag,
 );
die $version if $version_flag;
dieWithUsage() if !$opts || $#ARGV < 2 || $#ARGV > 3;

my $prog = basename($0);
sub dieWithUsage {
  die <<'END';
Usage: $prog SOURCES DESTINATION TEMPLATE [BRANCH]
The lazy web site maker

  --list-files, -l  list files read (on stderr)
  --version, -v     show program version
  --help, -h, -?    show this help

  SOURCES is a colon-separated list of source directory trees
  DESTINATION is the directory to which the output is written
  TEMPLATE is the name of the template fragment
  BRANCH is the sub-directory of each SOURCE tree to process
    (defaults to the entire tree)
END
}

sub Die {
  my ($message) = @_;
  die "$prog: $message\n";
}

sub Warn {
  my ($message) = @_;
  warn "$prog: $message\n";
}

Die("No source tree given") unless $ARGV[0];
my @sourceRoot = split /$Config{path_sep}/, $ARGV[0];
foreach my $dir (@sourceRoot) {
  Die("`$dir' not found or is not a directory")
    unless -d $dir;
}
my $destRoot = $ARGV[1];
Die("`$destRoot' is not a directory")
  if -e $destRoot && !-d $destRoot;
my $template = $ARGV[2];
if ($ARGV[3]) {
  for (my $i = 0; $i <= $#sourceRoot; $i++) {
    $sourceRoot[$i] = File::Spec::Unix->catfile($sourceRoot[$i], $ARGV[3]);
  }
}

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

# Search trees for a file starting at the given path; if found return
# its name, if not, print a warning and return undef.
sub findFile {
  my ($trees, $path, $file) = @_;
  foreach my $tree (@{$trees}) {
    my $search_path = File::Spec::Unix->catfile($tree, $path);
    while ($search_path =~ /^$tree/) { # Keep going until we go above $tree
      my $name = File::Spec::Unix->catfile($search_path, $file);
      if (-e $name) {
        print STDERR "  $name\n" if $list_files_flag;
        return $name;
      }
      $search_path = dirname($search_path);
    }
  }
  Warn "Cannot find `$file' while building `$path'\n";
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
  my ($text, $trees, $page) = @_;
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
      my $name = findFile($trees, $page, $fragment);
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

sub emptyDir {
  my ($dir) = @_;
  opendir DIR, $dir;
  my @contents = readdir DIR;
  closedir DIR;
  return $#contents <= 1;
}

# Get source directories
# FIXME: Make exclusion easily extensible, and add patterns for
# common VCSs (use find's --exclude-vcs patterns) and editor backup
# files &c.
my %sources = ();
my $non_leaves = 0;
foreach my $dir (reverse @sourceRoot) {
  File::Find::find(
    sub {
      return if !-d;
      if (/^\.svn$/) {
        $File::Find::prune = 1;
      } else {
        my $object = $File::Find::name;
        $object = substr($object, length($dir));
        # Flag directories as leaf/non-leaf, filtering out redundant names
        if (emptyDir($_)) { # Empty directories are removed
          $sources{$object} = undef if $object ne "";
          $sources{dirname($object)}-- if dirname($object) ne ".";
        } else { # non-empty directories are added
          $sources{$object} = 1 if $object ne "";
          if (dirname($object) ne ".") {
            $sources{dirname($object)}++;
            $non_leaves++;
          }
        }
      }
    },
    $dir);
}
Die("No pages found in source trees") unless $non_leaves > 0;

# Process source directories; work in sorted order so we process
# create directories in the destination tree before writing their
# contents
foreach my $dir (sort keys %sources) {
  my $dest = File::Spec::Unix->catfile($destRoot, $dir);
  # Only leaf directories correspond to pages
  if (defined($sources{$dir}) && $sources{$dir} > 0 &&
        ((defined($sources{dirname($dir)} && $sources{dirname($dir)} > 0) || $dir eq ""))) {
    if ($sources{$dir} == 1) {
      # Process one page
      print STDERR "$dir:\n" if $list_files_flag;
      my $out = expand("\$include{$template}", \@sourceRoot, $dir);
      if ($out ne "") {
        open OUT, ">$dest$suffix" or Die("Could not write to `$dest'");
        print OUT $out;
        close OUT;
      } else {
        print STDERR "  (no page written)\n" if $list_files_flag;
      }
      print STDERR "\n" if $list_files_flag;
    } else { # non-leaf directory
      # Make directory
      mkdir $dest;
      # Warn if directory is called index, as this is confusing
      Warn("`$dir' looks like an index page, but has sub-directories")
        if basename($dir) eq "index";
      # Check we have an index subdirectory
      Warn("`$dir' has no `index' subdirectory")
        unless $sources{File::Spec::Unix->catfile($dir, "index")};
    }
  }
}
