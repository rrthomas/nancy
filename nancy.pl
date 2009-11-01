#!/usr/bin/perl
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2009 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use strict;
use warnings;

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);
use File::Find;
use Getopt::Long;

use File::Slurp qw(slurp);

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
Usage: $prog SOURCE DESTINATION TEMPLATE [BRANCH]
The lazy web site maker

  --list-files, -l  list files read (on standard error)
  --warn, -w        warn about possible problems
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
# non-leaf directories marked as such, and read all the files.
# Report duplicate fragments one of which masks the other.
sub scanDir {
  my ($root) = @_;
  my %list = ();
  my %fragments = ();
  File::Find::find(
    sub {
      my $obj = $File::Find::name;
      my $pattern = "$root(?:" . catfile("", "") . ")?";
      my $name = $obj;
      $name =~ s/$pattern//;
      if (-f) {
        my $text = slurp($obj);
        $fragments{$name} = $text;

        if ($warn_flag) {
          # Warn about fragments that mask identical fragments
          my $search_path = dirname(dirname($name));
          my $fragment = basename($name);
          while ($search_path ne "." && $search_path ne "/") {
            my $parent_name = catfile($search_path, $fragment);
            $parent_name =~ s|^\./||;
            if (defined($fragments{$parent_name})) {
              Warn "$name is identical to $parent_name" if $fragments{$parent_name} eq $text;
              last; # Stop as soon as we find a fragment of the same name
            }
            $search_path = dirname($search_path);
          }
        }
      } elsif (-d) {
        $list{$name} = "leaf" if !defined($list{$name});
        my $parent = dirname($name);
        $parent = "" if $parent eq ".";
        $list{$parent} = "node";
      }
    },
    $root);
  return \%list, \%fragments;
}

# Fragment to page map
my %fragment_to_page = ();

# Process source directories; work in sorted order so we process
# create directories in the destination tree before writing their
# contents
my ($sources, $fragments) = scanDir($sourceRoot);
foreach my $dir (sort keys %{$sources}) {
  my $dest = catfile($destRoot, $dir);
  if ($sources->{$dir} eq "leaf") { # Process a leaf directory into a page
    print STDERR "$dir:\n" if $list_files_flag;
    my $out = WWW::Nancy::expand("\$include{$template}", $sourceRoot, $dir, $fragments, $list_files_flag, \%fragment_to_page);
    open OUT, ">$dest" or Warn("Could not write to `$dest'");
    print OUT $out;
    close OUT;
    print STDERR "\n" if $list_files_flag;
  } else { # Make a non-leaf directory
    mkdir $dest;
  }
}

if ($warn_flag) {
  # Return the path made up of the first n components of p
  sub subPath {
    my ($p, $n) = @_;
    my @path = splitdir($p);
    return catfile(@path[0 .. $n - 1]);
  }

  # Check for "overpromoted" fragments, that is, fragments that are only
  # used further towards the leaves than they are.
  foreach my $fragment (keys %fragment_to_page) {
    my @page_list = @{$fragment_to_page{$fragment}};
    my $prefix_len = scalar(splitdir($page_list[0]));
    for (my $i = 1; $i <= $#page_list; $i++) {
      for (;
           $prefix_len > 0 &&
             subPath($page_list[$i], $prefix_len) ne
               subPath($page_list[0], $prefix_len);
           $prefix_len--)
        {}
    }
    # If common prefix of pages is longer than the directory of the
    # fragment, then fragment should be demoted towards leaves
    Warn "$fragment could be moved into " . subPath($page_list[0], $prefix_len)
      if $prefix_len > scalar(splitdir(dirname($fragment)));
  }

  # Check for unused fragments
  foreach my $fragment (keys %{$fragments}) {
    Warn "$fragment is unused" if !defined($fragment_to_page{$fragment});
  }
}
