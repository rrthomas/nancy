#!/usr/bin/perl
my $version = <<'END';
nancy $Revision$ ($Date$)
(c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
Distributed under the GNU General Public License version 3, or (at
your option) any later version. There is no warranty.
END

use strict;
use warnings;

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);
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
# FIXME: Separate directory tree traversal from tree building
sub find {
  my ($obj) = @_;
  if (-f $obj) {
    return slurp($obj);
  } elsif (-d $obj) {
    my %dir = ();
    opendir(DIR, $obj);
    my @files = readdir(DIR);
    for my $file (@files) {
      next if $file eq "." or $file eq "..";
      $dir{$file} = find(catfile($obj, $file));
    }
    return \%dir;
  }
}

# Process source directories
my $sourceTree = find($sourceRoot);

# FIXME: The code below up to but not including write_pages should be
# in Nancy.pm.

# Fragment to page tree
my $fragment_to_page = WWW::Nancy::tree_copy($sourceTree);
foreach my $path (@{WWW::Nancy::tree_iterate_preorder($sourceTree, [], undef)}) {
  WWW::Nancy::tree_set($fragment_to_page, $path, undef)
      if WWW::Nancy::tree_isleaf(WWW::Nancy::tree_get($sourceTree, $path));
}

# Return true if a tree node has non-leaf children
sub has_node_children {
  my ($tree) = @_;
  foreach my $node (keys %{$tree}) {
    return 1 if ref($tree->{$node});
  }
}

# Walk tree, generating pages
my $pages = {};
foreach my $path (@{WWW::Nancy::tree_iterate_preorder($sourceTree, [], undef)}) {
  next if $#$path == -1 or WWW::Nancy::tree_isleaf(WWW::Nancy::tree_get($sourceTree, $path));
  if (has_node_children(WWW::Nancy::tree_get($sourceTree, $path))) {
    WWW::Nancy::tree_set($pages, $path, {});
  } else {
    my $name = catfile(@{$path});
    print STDERR "$name:\n" if $list_files_flag;
    my $out = WWW::Nancy::expand("\$include{$template}", $sourceRoot, $name, $sourceTree, $fragment_to_page, $warn_flag, $list_files_flag);
    print STDERR "\n" if $list_files_flag;
    WWW::Nancy::tree_set($pages, $path, $out);
  }
}


# Analyze generated pages to print warnings if desired
if ($warn_flag) {
  # Return the path made up of the first n components of p
  sub subPath {
    my ($p, $n) = @_;
    my @path = splitdir($p);
    return "" if $n > $#path + 1;
    return catfile(@path[0 .. $n - 1]);
  }

  # Check for unused fragments and fragments all of whose uses have a
  # common prefix that the fragment does not share.
  foreach my $path (@{WWW::Nancy::tree_iterate_preorder($fragment_to_page, [], undef)}) {
    my $node = WWW::Nancy::tree_get($fragment_to_page, $path);
    if (WWW::Nancy::tree_isleaf($node)) {
      my $name = catfile(@{$path});
      if (!$node) {
        Warn "`$name' is unused";
      } elsif (UNIVERSAL::isa($node, "ARRAY")) {
        my $prefix_len = scalar(splitdir(@{$node}[0]));
        foreach my $page (@{$node}) {
          for (;
               $prefix_len > 0 &&
                 subPath($page, $prefix_len) ne
                   subPath(@{$node}[0], $prefix_len);
               $prefix_len--)
            {}
        }
        my $dir = subPath(@{$node}[0], $prefix_len);
        Warn "`$name' could be moved into `$dir'"
          if scalar(splitdir(dirname($name))) < $prefix_len &&
            $dir ne subPath(dirname($name), $prefix_len);
      }
    }
  }
}


# Write pages to disk
foreach my $path (@{WWW::Nancy::tree_iterate_preorder($pages, [], undef)}) {
  my $name = "";
  $name = catfile(@{$path}) if $#$path != -1;
  my $node = WWW::Nancy::tree_get($pages, $path);
  if (WWW::Nancy::tree_isnotleaf($node)) {
    mkdir catfile($destRoot, $name);
  } else {
    open OUT, ">" . catfile($destRoot, $name) or Warn "Could not write to `$name'";
    print OUT $node;
    close OUT;
  }
}
