# Nancy.pm $Revision$ ($Date$)
# (c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

# FIXME: Write proper API documentation in POD

package WWW::Nancy;

use strict;
use warnings;
use feature ":5.10";

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);
use File::Slurp qw(slurp); # Also used in $run scripts

use RRT::Misc;

my ($warn_flag, $list_files_flag, $fragments, $fragment_to_page, $output, $template);


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

# Append relative fragment path to search path
# FIXME: Modifies first arg (is used as return value)
sub make_fragment_path {
  my ($search, $fragment) = @_;
  my @fragpath = splitdir($fragment);
  # Append fragment path, coping with `..' and `.'. There is no
  # obvious standard function to do this: File::Spec::canonpath does
  # not do `..' removal, as that does not work with symlinks; in
  # other words, our relative paths don't behave in the presence of
  # symlinks.
  foreach my $elem (@fragpath) {
    if ($elem eq "..") {
      pop @{$search};
    } elsif ($elem ne ".") {
      push @{$search}, $elem;
    }
  }
}

# Search for fragment starting at the given path; if found return its
# path, contents and file name; if not, print a warning and return
# undef.
sub findFragment {
  my ($path, $fragment) = @_;
  my (@foundpath, $contents, $node);
  for (my @search = @{$path}; 1; pop @search) {
    my @thissearch = @search;
    make_fragment_path(\@thissearch, $fragment);
    $node = tree_get($fragments, \@thissearch);
    if (defined($node) && tree_isleaf($node)) { # We have a fragment, not a directory
      my $new_contents = slurp($node);
      print STDERR "  " . catfile(@thissearch) . "\n" if $list_files_flag;
      warn("`" . catfile(@thissearch) . "' is identical to `" . catfile(@foundpath) . "'")
        if $warn_flag && defined($contents) && $new_contents eq $contents;
      @foundpath = @thissearch;
      $contents = $new_contents;
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
      # join, not catfile as we're making a URL, not a path
      return join "/", @{$path};
    },
    root => sub {
      return join "/", (("..") x $#{$path}) if $#{$path} > 0;
      return ".";
    },
    include => sub {
      my ($fragment) = @_;
      my ($fragpath, $contents) = findFragment($path, $fragment);
      return $contents if $fragpath;
      return "";
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
      my $val = read_tree(catfile($obj, $file));
      $dir{$file} = $val if defined($val);
    }
    return \%dir;
  }
  # If not a file or directory, return nothing
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

# Add a page to the output
sub add_output {
  my ($path, $contents) = @_;
  tree_set($output, $path, $contents);
}

# Expand a file system object, recursively expanding links
sub expand_page {
  my ($tree, $path) = @_;
  # Don't expand the same node twice
  if (!defined(tree_get($output, $path))) {
    # If we are looking at a non-leaf or undefined node, expand it
    if ($#$path != -1 && (!defined(tree_get($tree, $path)) ||
                            !tree_isleaf(tree_get($tree, $path)))) {
      print STDERR catfile(@{$path}) . ":\n" if $list_files_flag;
      my $out = expand("\$include{$template}", $path, $tree);
      print STDERR "\n" if $list_files_flag;
      tree_set($output, $path, $out);

      # Find all local links and add them to output (a local link is
      # one that doesn't start with a scheme)
      my @links = $out =~ /\Whref=\"(?![a-z]+:)([^\"\#]+)/g;
      foreach my $link (@links) {
        if ($link !~ /\.html$/) {
          my ($fragpath, $contents) = findFragment($path, $link);
          add_output($fragpath, $contents) if $fragpath;
        } else {
          my @pagepath = @{$path};
          pop @pagepath; # Remove current directory, which represents a page
          make_fragment_path(\@pagepath, $link);
          no warnings qw(recursion); # We may recurse deeply.
          expand_page($fragments, \@pagepath);
        }
      }
    }
  }
}

# Macro expand a tree
sub expand_tree {
  my ($sourceTree, $start);
  ($sourceTree, $template, $start, $warn_flag, $list_files_flag) = @_;

  # Fragment to page tree
  $fragment_to_page = tree_copy($sourceTree);
  foreach my $path (@{tree_iterate_preorder($sourceTree, [], undef)}) {
    tree_set($fragment_to_page, $path, undef)
      if tree_isleaf(tree_get($sourceTree, $path));
  }

  # Expand tree, starting from $start
  $output = {};
  expand_page($sourceTree, [$start]);

  # Analyse generated pages to print warnings if desired
  if ($warn_flag) {
    # Check for unused fragments and fragments all of whose uses have a
    # common prefix that the fragment does not share.
    foreach my $path (@{tree_iterate_preorder($fragment_to_page, [], undef)}) {
      my $node = tree_get($fragment_to_page, $path);
      if (tree_isleaf($node)) {
        if (!$node) {
          print STDERR "`" . catfile(@{$path}) . "' is unused\n";
        } elsif (UNIVERSAL::isa($node, "ARRAY")) {
          my $prefix = $#{@{$node}[0]};
          foreach my $page (@{$node}) {
            for (; $prefix >= 0 && !(@{$page}[0..$prefix] ~~ @{@{$node}[0]}[0..$prefix]);
                 $prefix--) {}
          }
          my @dir = @{@{$node}[0]}[0..$prefix];
          print STDERR "`" . catfile(@{$path}) . "' could be moved into `" . catfile(@dir) . "'\n"
            if $#{$path} <= $prefix && !(@dir ~~ @{$path});
        }
      }
    }
  }

  return $output;
}


return 1;
