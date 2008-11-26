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
use File::Spec::Functions;
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

# Process source directories; work in sorted order so we process
# create directories in the destination tree before writing their
# contents
my %sources = %{dirToTreeList($sourceRoot)};
foreach my $dir (sort keys %sources) {
  my $dest = catfile($destRoot, $dir);
  if ($sources{$dir} eq "leaf") { # Process a leaf directory into a page
    my @args = ($sourceRoot, $dir, $template);
    unshift @args, "--list-files" if $list_files_flag;
    open(IN, "-|", "weavefile.pl", @args);
    # FIXME: Use slurp once this can be done portably
    my $out = do {local $/, <IN>};
    close IN;
    open OUT, ">$dest" or Warn("Could not write to `$dest'");
    print OUT $out;
    close OUT;
    print STDERR "\n" if $list_files_flag;
  } else { # Make a non-leaf directory
    mkdir $dest;
  }
}
