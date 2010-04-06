# Nancy.pm $Revision: 982 $ ($Date: 2009-10-04 22:01:25 +0100 (Sun, 04 Oct 2009) $)
# (c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

# FIXME: Write proper API documentation in POD

package WWW::Nancy;

use strict;
use warnings;

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);
use File::Slurp qw(slurp); # Also used in $run scripts

use RRT::Misc;


my ($warn_flag, $list_files_flag, $fragments, $fragment_to_page);


# Tree operations
# FIXME: Put them in their own module

# Return subtree at given path
sub tree_get {
  my ($tree, $path) = @_;
  foreach my $elem (@{$path}) {
    last if !ref($tree);
    $tree = $tree->{$elem};
  }
  return $tree;
}

# Set subtree at given path to given value, creating any intermediate
# nodes required
# FIXME: Return whether we needed to create intermediate nodes
sub tree_set {
  my ($tree, $path, $val) = @_;
  my $leaf = pop @{$path};
  foreach my $node (@{$path}) {
    $tree->{$node} = {} if !defined($tree->{$node});
    $tree = $tree->{$node};
  }
  $tree->{$leaf} = $val;
}

# Return whether tree is a leaf
sub tree_isleaf {
  my ($tree) = @_;
  return !UNIVERSAL::isa($tree, "HASH");
}

# Return whether tree is not a leaf
sub tree_isnotleaf {
  return !tree_isleaf(@_);
}

# Return list of paths in tree, in pre-order
sub tree_iterate_preorder {
  my ($tree, $path, $paths) = @_;
  push @{$paths}, $path if $path;
  if (tree_isnotleaf($tree)) {
    foreach my $node (keys %{$tree}) {
      my @sub_path = @{$path};
      push @sub_path, $node;
      $paths = tree_iterate_preorder($tree->{$node}, \@sub_path, $paths);
    }
  }
  return $paths;
}

# Return a copy of a tree
# FIXME: Rewrite in terms of tree_merge
sub tree_copy {
  my ($in_tree) = @_;
  if (ref($in_tree)) {
    my $out_tree = {};
    foreach my $node (keys %{$in_tree}) {
      $out_tree->{$node} = tree_copy($in_tree->{$node});
    }
    return $out_tree;
  } else {
    return $in_tree;
  }
}

# Merge two trees; right-hand operand takes precedence
sub tree_merge {
  my ($left, $right) = @_;
  foreach my $path (@{tree_iterate_preorder($right, [], undef)}) {
    my $node = tree_get($right, $path);
    tree_set($left, $path, $node) if tree_isleaf($node);
  }
}


# Search for fragment starting at the given path; if found return its
# name, contents and file name; if not, print a warning and return
# undef.
sub findFragment {
  my ($path, $fragment) = @_;
  my ($name, $contents, $node);
  for (my @search = splitdir($path); 1; pop @search) {
    my @thissearch = @search;
    my @fragpath = splitdir($fragment);
    # Cope with `..' and `.' (need to do this each time round the
    # loop). There is no obvious standard function to do this, because
    # File::Spec::canonpath does not do `..' removal, as that does not
    # work with symlinks; in other words, Nancy's relative paths don't
    # behave in the presence of symlinks.
    foreach my $elem (@fragpath) {
      if ($elem eq "..") {
        pop @thissearch;
      } elsif ($elem ne ".") {
        push @thissearch, $elem;
      }
    }
    $node = tree_get($fragments, \@thissearch);
    if (defined($node) && !ref($node)) { # We have a fragment, not a directory
      my $new_name = catfile(@search);
      print STDERR "  $new_name\n" if $list_files_flag;
      warn("`$new_name' is identical to `$name'") if $warn_flag && defined($contents) && $contents eq $node;
      $name = $new_name;
      $contents = $node;
      if ($fragment_to_page) {
        my $used_list = tree_get($fragment_to_page, \@search);
        $used_list = [] if !UNIVERSAL::isa($used_list, "ARRAY");
        push @{$used_list}, $path;
        tree_set($fragment_to_page, \@search, $used_list);
        last;
      }
    }
    pop @search;
    last if $#search == -1;
  }
  warn("Cannot find `$fragment' while building `$path'\n") unless $contents;
  return $name, $contents, $node;
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
#   $text - text to expand
#   $tree - source tree path
#   $page - leaf directory to make into a page
#   $fragments - tree of fragments
#   [$fragment_to_page] - tree of fragment to page maps
#   [$warn_flag] - whether to output warnings
#   [$list_files_flag] - whether to output fragment lists
# returns expanded text, fragment to page tree
sub expand {
  my ($text, $tree, $page);
  ($text, $tree, $page, $fragments, $fragment_to_page, $warn_flag, $list_files_flag) = @_;
  my %macros = (
    page => sub {
      # Split and join needed for platforms whose path separator is not "/"
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
      my ($name, $contents) = findFragment($page, $fragment);
      my $text = "";
      if ($name) {
        $text .= "***INCLUDE: $name***" if $list_files_flag;
        $text .= $contents;
      }
      return $text;
    },
    run => sub {
      my ($prog) = shift;
      my ($name, $contents) = findFragment($page, $prog);
      if ($name) {
        my $sub = eval(untaint($contents));
        return &{$sub}(@_);
      }
      return "";
    },
  );
  $text = doMacros($text, %macros);
  # Convert $Macro back to $macro
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;
  return $text;
}

# Read a directory tree into a tree
# FIXME: Separate directory tree traversal from tree building
# FIXME: Make exclusion easily extensible, and add patterns for
# common VCSs (use tar's --exclude-vcs patterns) and editor backup
# files &c.
sub read_tree {
  my ($obj) = @_;
  # FIXME: Should really do this in a separate step (need to do it
  # before pruning empty directories)
  return if basename($obj) eq ".svn"; # Ignore irrelevant objects
  if (-f $obj) {
    return slurp($obj); # if -s $obj; # Ignore empty files
  } elsif (-d $obj) {
    my %dir = ();
    opendir(DIR, $obj);
    my @files = readdir(DIR);
    foreach my $file (@files) {
      next if $file eq "." or $file eq "..";
      my $val = read_tree(catfile($obj, $file));
      $dir{$file} = $val if defined($val);
    }
    return \%dir; # if $#file != -1; # Ignore empty directories
  }
  # We get here if we are ignoring the file, and return nothing.
}

# Slurp the leaves of a tree, assuming they are filenames
sub tree_slurp {
  my ($tree) = @_;
  foreach my $path (@{tree_iterate_preorder($tree, [], undef)}) {
    my $node = tree_get($tree, $path);
    if (tree_isleaf($node)) {
      tree_set($tree, $path, scalar(slurp($node)));
    }
  }
  return $tree;
}

# Construct file tree from multiple source trees, masking out empty
# files and directories
sub find {
  my @roots = reverse @_;
  my $out = {};
  foreach my $root (@roots) {
    $out = tree_merge($out, read_tree($root));
  }
  # Get rid of empty files and directories
  foreach my $path (@{tree_iterate_preorder($out, [], undef)}) {
    my $node = tree_get($out, $path);
    if ((tree_isleaf($node) && -z $node) ||
          (!tree_isleaf($node) && scalar keys %{$node} == 0)) {
      tree_delete($out, $path);
    }
  }
  # FIXME: Remove empty directories and files
  return $out;
}

# Write $tree to a file hierarchy based at $root
sub write_tree {
  my ($tree, $root) = @_;
  foreach my $path (@{tree_iterate_preorder($tree, [], undef)}) {
    my $name = "";
    $name = catfile(@{$path}) if $#$path != -1;
    my $node = tree_get($tree, $path);
    if (!tree_isleaf($node)) {
      mkdir catfile($root, $name);
    } else {
      open OUT, ">" . catfile($root, $name) or print STDERR "Could not write to `$name'";
      print OUT $node;
      close OUT;
    }
  }
}

# Macro expand a tree
sub expand_tree {
  my ($sourceTree, $template, $warn_flag, $list_files_flag) = @_;

  # Fragment to page tree
  my $fragment_to_page = tree_copy($sourceTree);
  foreach my $path (@{tree_iterate_preorder($sourceTree, [], undef)}) {
    tree_set($fragment_to_page, $path, undef)
        if tree_isleaf(tree_get($sourceTree, $path));
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
  foreach my $path (@{tree_iterate_preorder($sourceTree, [], undef)}) {
    next if $#$path == -1 or tree_isleaf(tree_get($sourceTree, $path));
    if (has_node_children(tree_get($sourceTree, $path))) {
      tree_set($pages, $path, {});
    } else {
      my $name = catfile(@{$path});
      print STDERR "$name:\n" if $list_files_flag;
      my $out = expand("\$include{$template}", $name, $sourceTree, $fragment_to_page, $warn_flag, $list_files_flag);
      print STDERR "\n" if $list_files_flag;
      tree_set($pages, $path, $out);
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
    foreach my $path (@{tree_iterate_preorder($fragment_to_page, [], undef)}) {
      my $node = tree_get($fragment_to_page, $path);
      if (tree_isleaf($node)) {
        my $name = catfile(@{$path});
        if (!$node) {
          print STDERR "`$name' is unused";
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
          print STDERR "`$name' could be moved into `$dir'"
            if scalar(splitdir(dirname($name))) < $prefix_len &&
              $dir ne subPath(dirname($name), $prefix_len);
        }
      }
    }
  }

  return $pages;
}


return 1;
