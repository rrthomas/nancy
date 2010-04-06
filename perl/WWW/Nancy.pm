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

my ($warn_flag, $list_files_flag, $fragments, $fragment_to_page, $extra_output);


# Tree operations
# FIXME: Put them in their own module

# Return subtree at given path
sub tree_get {
  my ($tree, $path) = @_;
  foreach my $elem (@{$path}) {
    last if tree_isleaf($tree);
    $tree = $tree->{$elem};
  }
  return $tree;
}

# Set subtree at given path to given value, creating any intermediate
# nodes required
# FIXME: Allow the entire tree to be set; need to return result!
# FIXME: Return whether we needed to create intermediate nodes
sub tree_set {
  my ($tree, $path, $val) = @_;
  my @path = @{$path};
  my $leaf = pop @path;
  return unless defined($leaf); # Ignore attempts to set entire tree
  foreach my $node (@path) {
    $tree->{$node} = {} if !defined($tree->{$node});
    $tree = $tree->{$node};
  }
  $tree->{$leaf} = $val;
}

# Remove subtree at given path
sub tree_delete {
  my ($tree, $path, $val) = @_;
  my @path = @{$path};
  my $leaf = pop @path;
  foreach my $node (@path) {
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
# path, contents and file name; if not, print a warning and return
# undef.
sub findFragment {
  my ($path, $fragment) = @_;
  my @fragpath = splitdir($fragment);
  my (@foundpath, $contents, $node);
  for (my @search = @{$path}; 1; pop @search) {
    my @thissearch = @search;
    # Append fragment path, coping with `..' and `.'. There is no
    # obvious standard function to do this: File::Spec::canonpath does
    # not do `..' removal, as that does not work with symlinks; in
    # other words, our relative paths don't behave in the presence of
    # symlinks.
    foreach my $elem (@fragpath) {
      if ($elem eq "..") {
        pop @thissearch;
      } elsif ($elem ne ".") {
        push @thissearch, $elem;
      }
    }
    $node = tree_get($fragments, \@thissearch);
    if (defined($node) && tree_isleaf($node)) { # We have a fragment, not a directory
      my $new_contents = slurp($node);
      print STDERR "  " . catfile(@thissearch) . "\n" if $list_files_flag;
      warn("`" . catfile(@thissearch) . "' is identical to `" . catfile(@foundpath) . "'")
        if $warn_flag && defined($contents) && $new_contents eq $contents;
      @foundpath = @thissearch;
      $contents = $new_contents;
      if ($fragment_to_page) {
        my $used_list = tree_get($fragment_to_page, \@search);
        $used_list = [] if !UNIVERSAL::isa($used_list, "ARRAY");
        push @{$used_list}, catfile(@{$path});
        tree_set($fragment_to_page, \@thissearch, $used_list);
      }
    }
    pop @search;
    last if $#search == -1;
  }
  warn("Cannot find `$fragment' while building `" . catfile(@{$path}) ."'\n") unless $contents;
  return \@foundpath, $contents, $node;
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
#   $path - leaf directory to make into a page
#   $fragments - tree of fragments
# returns expanded text
sub expand {
  my ($text, $path);
  ($text, $path, $fragments) = @_;
  my %macros = (
    page => sub {
      # join, not catdir as we're making a URL, not a path
      return join "/", @{$path};
    },
    root => sub {
      return join "/", (("..") x $#{$path}) if $#{$path} > 0;
      return ".";
    },
    include => sub {
      my ($fragment) = @_;
      my ($fragpath, $contents) = findFragment($path, $fragment);
      my $text = "";
      if ($fragpath) {
        $text .= "***INCLUDE: $fragpath***" if $list_files_flag;
        $text .= $contents;
      }
      return $text;
    },
    run => sub {
      my ($prog) = shift;
      my ($fragpath, $contents) = findFragment($path, $prog);
      return &{eval(untaint($contents))}(@_) if $fragpath;
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
      open OUT, ">" . catfile($root, $name) or print STDERR "Could not write to `$name'\n";
      print OUT $node;
      close OUT;
    }
  }
}

# Return true if a tree node has non-leaf children
sub has_node_children {
  my ($tree) = @_;
  foreach my $node (keys %{$tree}) {
    return 1 if !tree_isleaf($tree->{$node});
  }
}

# Return the path made up of the first n components of p
sub subPath {
  my ($p, $n) = @_;
  my @path = splitdir($p);
  return "" if $n > $#path + 1;
  return catfile(@path[0 .. $n - 1]);
}

# Add a page to the output (for calling from $run scripts)
sub add_output {
  my ($path, $contents) = @_;
  tree_set($extra_output, $path, $contents);
}

# Macro expand a tree
sub expand_tree {
  my ($sourceTree, $template);
  ($sourceTree, $template, $warn_flag, $list_files_flag) = @_;

  # Fragment to page tree
  $fragment_to_page = tree_copy($sourceTree);
  foreach my $path (@{tree_iterate_preorder($sourceTree, [], undef)}) {
    tree_set($fragment_to_page, $path, undef)
      if tree_isleaf(tree_get($sourceTree, $path));
  }

  # Walk tree, generating pages
  # FIXME: Non-leaf directories with dot in name should generate warning
  my $pages = {};
  $extra_output = {};
  foreach my $path (@{tree_iterate_preorder($sourceTree, [], undef)}) {
    next if $#$path == -1 or tree_isleaf(tree_get($sourceTree, $path));
    # If a non-leaf directory or no dot in its name
    if (has_node_children(tree_get($sourceTree, $path)) || ($path->[$#{$path}] !~ /\./)) {
      tree_set($pages, $path, {});
    } else {
      print STDERR catfile(@{$path}) . ":\n" if $list_files_flag;
      my $out = expand("\$include{$template}", $path, $sourceTree);
      print STDERR "\n" if $list_files_flag;
      tree_set($pages, $path, $out);
    }
  }

  # Analyze generated pages to print warnings if desired
  if ($warn_flag) {
    # Check for unused fragments and fragments all of whose uses have a
    # common prefix that the fragment does not share.
    foreach my $path (@{tree_iterate_preorder($fragment_to_page, [], undef)}) {
      my $node = tree_get($fragment_to_page, $path);
      if (tree_isleaf($node)) {
        my $name = catfile(@{$path});
        if (!$node) {
          print STDERR "`$name' is unused\n";
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
          print STDERR "`$name' could be moved into `$dir'\n"
            if scalar(splitdir(dirname($name))) < $prefix_len &&
              $dir ne subPath(dirname($name), $prefix_len);
        }
      }
    }
  }

  return tree_merge($pages, $extra_output);
}


return 1;
