#! /usr/bin/perl
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2008 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use strict;
use warnings;

use Config;
use File::Basename;
use File::Spec::Functions;
use File::Find;
use Getopt::Long;

my $suffix = ".html"; # suffix to make source directory into destination file

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
Die("`$destRoot' is not a directory") if -e $destRoot && !-d $destRoot;
my $template = $ARGV[2];
$sourceRoot = catfile($sourceRoot, $ARGV[3]) if $ARGV[3];

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
  my $dest = catfile($destRoot, $dir);
  # Only leaf directories correspond to pages
  if (defined($sources{$dir}) && $sources{$dir} > 0 &&
        ((defined($sources{dirname($dir)} && $sources{dirname($dir)} > 0) || $dir eq ""))) {
    if ($sources{$dir} == 1) {
      # Process one page
      my $list = $list_files_flag ? "--list-files" : "";
      my $page = substr($dir, length($Config{path_sep}));
      open(IN, "-|", "weavefile.pl $list $sourceRoot $page $template");
      my $out = do { local $/, <IN> };
      close IN;
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
        unless $sources{catfile($dir, "index")};
    }
  }
}
