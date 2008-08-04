#! /usr/bin/perl
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2008 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use strict;
use warnings;

use File::Basename;
use File::Spec::Unix; # See FIXME below
use File::Spec;
use File::Find;
use Getopt::Long;

my $suffix = ".html"; # suffix to make source directory into destination file

# FIXME: To make $page{} work we assume that the OS can handle
# UNIX-style paths; we should use File::Spec and convert paths into
# URLs. Do this by splitting using the platform's splitdir, then
# rejoining using the File::Spec::Unix joiner.

# Get arguments
my ($version_flag, $help_flag, $list_files_flag);
my $prog = basename($0);
my $opts = GetOptions(
  "list-files" => \$list_files_flag,
  "version" => \$version_flag,
  "help" => \$help_flag,
 );
die $version if $version_flag;
dieWithUsage() if !$opts || $#ARGV < 2 || $#ARGV > 3;

sub dieWithUsage {
  die <<END;
Usage: $prog SOURCE DESTINATION TEMPLATE [BRANCH]
The lazy web site maker

  --list-files, -l  list files read (on stderr)
  --version, -v     show program version
  --help, -h, -?    show this help

  SOURCE is the source directory tree
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
my $sourceRoot = $ARGV[0];
Die("`$sourceRoot' not found or is not a directory") unless -d $sourceRoot;
my $destRoot = $ARGV[1];
Die("`$destRoot' is not a directory") if -e $destRoot && !-d $destRoot;
my $template = $ARGV[2];
$sourceRoot = File::Spec::Unix->catfile($sourceRoot, $ARGV[3]) if $ARGV[3];

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
    my $name = File::Spec::Unix->catfile($tree, $search_path, $file);
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
      return $page;
    },
    root => sub {
      my $reps = scalar(File::Spec::Unix->splitdir($page)) - 2;
      return File::Spec::Unix->catfile(("..") x $reps) if $reps > 0;
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

# Get source directories
my %sources = ();
my $non_leaves = 0;
File::Find::find(
  sub {
    return if !-d;
    my $obj = $File::Find::name;
    $obj = substr($obj, length($sourceRoot));
    $sources{$obj} = 1 if $obj ne "" && !defined($sources{$obj});
    if (dirname($obj) ne ".") {
      $sources{dirname($obj)} = 2;
      $non_leaves++;
    }
  },
  $sourceRoot);
Die("No pages found in source tree") unless $non_leaves > 0;

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
      my $out = expand("\$include{$template}", $sourceRoot, $dir);
      open OUT, ">$dest$suffix" or Warn("Could not write to `$dest'");
      print OUT $out;
      close OUT;
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
