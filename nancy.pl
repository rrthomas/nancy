#!/usr/bin/perl
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use strict;
use warnings;

use Config;
use File::Basename;
use File::Spec::Functions qw(catfile);
use Getopt::Long;

use WWW::Nancy;

# Get arguments
my ($version_flag, $help_flag, $list_files_flag, $warn_flag);
my $prog = basename($0);
my $opts = GetOptions(
  "list-files" => \$list_files_flag,
  "warn" => \$warn_flag,
  "version" => \$version_flag,
  "help" => \$help_flag,
 );
die $version if $version_flag;
dieWithUsage() if !$opts || $#ARGV < 2 || $#ARGV > 3;

sub dieWithUsage {
  die <<END;
Usage: $prog SOURCES DESTINATION TEMPLATE [BRANCH]
The lazy web site maker

  --list-files, -l  list files read (on standard error)
  --warn, -w        warn about possible problems
  --version, -v     show program version
  --help, -h, -?    show this help

  SOURCES is the source directory trees
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

# FIXME: Move source and destination validation into Nancy.pm
Die("No source tree given") unless $ARGV[0];
my @sourceRoot = split /$Config{path_sep}/, $ARGV[0];
foreach my $dir (@sourceRoot) {
  Die("`$dir' not found or is not a directory")
    unless -d $dir;
}
my $destRoot = $ARGV[1];
$destRoot =~ s|/+$||;
Die("`$destRoot' is not a directory")
  if -e $destRoot && !-d $destRoot;
my $template = $ARGV[2];
if ($ARGV[3]) {
  for (my $i = 0; $i <= $#sourceRoot; $i++) {
    $sourceRoot[$i] = File::Spec::Unix->catfile($sourceRoot[$i], $ARGV[3]);
  }
}
for (my $i = 0; $i <= $#sourceRoot; $i++) {
  $sourceRoot[$i] =~ s|/+$||;
}

# Process source directories
WWW::Nancy::write_tree(WWW::Nancy::expand_tree(WWW::Nancy::find(@sourceRoot), $template, $warn_flag, $list_files_flag), $destRoot);
