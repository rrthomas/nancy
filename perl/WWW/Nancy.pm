# Nancy.pm $Revision$ ($Date$)
# (c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

# FIXME: Write proper API documentation in POD

package WWW::Nancy;

use strict;
use warnings;

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);

use File::Slurp qw(slurp); # For $run scripts to use


my ($warn_flag, $list_files_flag, $fragments, $fragment_to_page);


# Tree operations
# FIXME: Put them in their own module

sub tree_dump {
  my ($tree) = @_;
  foreach my $path (@{tree_iterate_preorder($tree, [], undef)}) {
    my $node = tree_get($tree, $path);
    print STDERR (join "/", @{$path});
    print STDERR ":" if !tree_isleaf($node);
    print STDERR "\n";
  }
}

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
# FIXME: Allow the entire tree to be overridden; need to return result!
# FIXME: Return whether we needed to create intermediate nodes
sub tree_set {
  my ($tree, $path, $val) = @_;
  my $leaf = pop @{$path};
  return unless defined($leaf); # Ignore attempts to set entire tree
  foreach my $node (@{$path}) {
    $tree->{$node} = {} if !defined($tree->{$node});
    $tree = $tree->{$node};
  }
  $tree->{$leaf} = $val;
}

# Remove subtree at given path
sub tree_delete {
  my ($tree, $path, $val) = @_;
  my $leaf = pop @{$path};
  foreach my $node (@{$path}) {
    return if !exists($tree->{$node});
    $tree = $tree->{$node};
  }
  delete $tree->{$leaf};
}

# Return whether tree is a leaf
sub tree_isleaf {
  my ($tree) = @_;
  return !UNIVERSAL::isa($tree, "HASH");
}

# Return list of paths in tree, in pre-order
sub tree_iterate_preorder {
  my ($tree, $path, $paths) = @_;
  push @{$paths}, $path if $path;
  if (!tree_isleaf($tree)) {
    foreach my $node (keys %{$tree}) {
      my @sub_path = @{$path};
      push @sub_path, $node;
      $paths = tree_iterate_preorder($tree->{$node}, \@sub_path, $paths);
    }
  }
  return $paths;
}

# Return a copy of a tree
sub tree_copy {
  my ($tree) = @_;
  return $tree if scalar keys %{$tree} == 0;
  return tree_merge({}, $tree);
}

# Merge two trees, returning the result; right-hand operand takes
# precedence, and its empty subtrees replace left-hand subtrees.
sub tree_merge {
  my ($left, $right) = @_;
  my $out = tree_copy($left);
  foreach my $path (@{tree_iterate_preorder($right, [], undef)}) {
    my $node = tree_get($right, $path);
    if (tree_isleaf($node)) {
      tree_set($out, $path, $node);
    } elsif (scalar keys %{$node} == 0) {
      tree_set($out, $path, {});
    }
  }
  return $out;
}


# Search for fragment starting at the given path; if found return
# its name and contents; if not, print a warning and return undef.
sub findFragment {
  my ($path, $fragment) = @_;
  my ($name, $contents);
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
    my $node = tree_get($fragments, \@thissearch);
    if (defined($node) && !ref($node)) { # We have a fragment, not a directory
      my $new_name = catfile(@thissearch);
      print STDERR "  $new_name\n" if $list_files_flag;
      warn("`$new_name' is identical to `$name'") if $warn_flag && defined($contents) && $contents eq $node;
      $name = $new_name;
      $contents = slurp($node);
      if ($fragment_to_page) {
        my $used_list = tree_get($fragment_to_page, \@thissearch);
        $used_list = [] if !UNIVERSAL::isa($used_list, "ARRAY");
        push @{$used_list}, $path;
        tree_set($fragment_to_page, \@thissearch, $used_list);
      }
      last;
    }
    last if $#search == -1;
  }
  warn("Cannot find `$fragment' while building `$path'\n") unless $contents;
  return $name, $contents;
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
#   $page - leaf directory to make into a page
#   $fragments - tree of fragments
#   [$fragment_to_page] - tree of fragment to page maps
#   [$warn_flag] - whether to output warnings
#   [$list_files_flag] - whether to output fragment lists
# returns expanded text, fragment to page tree
sub expand {
  my ($text, $page);
  ($text, $page, $fragments, $fragment_to_page, $warn_flag, $list_files_flag) = @_;
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
        my $sub = eval($contents);
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

# Turn a directory into a list of subdirectories, with leaf and
# non-leaf directories marked as such, and read all the files.
# Report duplicate fragments one of which masks the other.
# FIXME: Separate directory tree traversal from tree building
# FIXME: Make exclusion easily extensible, and add patterns for
# common VCSs (use tar's --exclude-vcs patterns) and editor backup
# files &c.
sub slurp_tree {
  my ($obj) = @_;
  # FIXME: Do this in a separate step (need to do it before pruning
  # empty directories)
  return if basename($obj) eq ".svn"; # Ignore irrelevant objects
  if (-f $obj) {
    return $obj;
  } elsif (-d $obj) {
    my %dir = ();
    opendir(DIR, $obj);
    my @files = readdir(DIR);
    foreach my $file (@files) {
      next if $file eq "." or $file eq "..";
      my $val = slurp_tree(catfile($obj, $file));
      $dir{$file} = $val if defined($val);
    }
    return \%dir;
  }
  # If not a file or directory, return nothing
}

# Construct file tree from multiple source trees, masking out empty
# files and directories
sub find {
  my @roots = reverse @_;
  my $out = {};
  foreach my $root (@roots) {
    $out = tree_merge($out, slurp_tree($root));
  }
  # Get rid of empty files and directories
  foreach my $path (@{tree_iterate_preorder($out, [], undef)}) {
    my $node = tree_get($out, $path);
    if ((tree_isleaf($node) && -z $node) ||
          (!tree_isleaf($node) && scalar keys %{$node} == 0)) {
      tree_delete($out, $path);
    }
  }
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
      print OUT slurp($node);
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
    next if $#$path == -1 or tree_isleaf(WWW::Nancy::tree_get($sourceTree, $path));
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
