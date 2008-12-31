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
use File::Spec::Functions qw(catfile splitdir);
use File::Find;
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
dieWithUsage() if !$opts || $#ARGV < 2 || $#ARGV > 3;

sub dieWithUsage {
  die <<END;
Usage: $prog SOURCE DESTINATION TEMPLATE [BRANCH]
The lazy web site maker

  --list-files, -l  list files read (on standard error)
  --version, -v     show program version
  --help, -h, -?    show this help

  SOURCE is the source directory tree
  DESTINATION is the directory to which the output is written
  TEMPLATE is the name of the template fragment
  BRANCH is the sub-directory of each SOURCE tree to process
    (defaults to the entire tree)
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
my $sourceRoot = $ARGV[0];
Die("`$sourceRoot' not found or is not a directory") unless -d $sourceRoot;
my $destRoot = $ARGV[1];
$destRoot =~ s|/+$||;
Die("`$destRoot' is not a directory") if -e $destRoot && !-d $destRoot;
my $template = $ARGV[2];
$sourceRoot = catfile($sourceRoot, $ARGV[3]) if $ARGV[3];
$sourceRoot =~ s|/+$||;

# Turn a directory into a list of subdirectories, with leaf and
# non-leaf directories marked as such
# FIXME: Put this function in a module
sub dirToTreeList {
  my ($root) = @_;
  my %list = ();
  File::Find::find(
    sub {
      return if !-d;
      my $obj = $File::Find::name;
      my $pattern = "$root(?:" . catfile("", "") . ")?";
      $obj =~ s/$pattern//;
      $list{$obj} = "leaf" if !defined($list{$obj});
      my $parent = dirname($obj);
      $parent = "" if $parent eq ".";
      $list{$parent} = "node";
    },
    $sourceRoot);
  return \%list;
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

# Search tree for a file starting at the given path; if found return
# its name, if not, print a warning and return undef.
sub findFile {
  my ($tree, $path, $file) = @_;
  my $search_path = $path;
  while (1) {
    my $name = catfile($tree, $search_path, $file);
    if (-f $name) {
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
      my $text = "";
      if ($name) {
        $text .= "***INCLUDE: $name***" if $list_files_flag;
        $text .= readFile($name);
        return $text;
      }
      return "";
    },
    run => sub {
      my ($prog) = @_;
      my $name = findFile($tree, $page, $prog);
      my $sub = eval expand(readFile($name), $tree, $page);
      return &{$sub}();
    },
  );
  $text = doMacros($text, %macros);
  # Convert $Macro back to $macro
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;
  return $text;
}

# Process source directories; work in sorted order so we process
# create directories in the destination tree before writing their
# contents
my %sources = %{dirToTreeList($sourceRoot)};
foreach my $dir (sort keys %sources) {
  my $dest = catfile($destRoot, $dir);
  if ($sources{$dir} eq "leaf") { # Process a leaf directory into a page
    print STDERR "$dir:\n" if $list_files_flag;
    my $out = expand("\$include{$template}", $sourceRoot, $dir);
    open OUT, ">$dest" or Warn("Could not write to `$dest'");
    print OUT $out;
    close OUT;
    print STDERR "\n" if $list_files_flag;
  } else { # Make a non-leaf directory
    mkdir $dest;
  }
}
