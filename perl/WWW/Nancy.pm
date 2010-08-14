# Nancy.pm $Revision$ ($Date$)
# (c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

# FIXME: Write proper API documentation in POD

package WWW::Nancy;

use strict;
use warnings;
use feature ":5.10";

use File::Spec::Functions qw(catfile);
use File::Slurp qw(slurp); # Also used in $run scripts

use RRT::Misc;

my ($warn_flag, $list_files_flag, $files, $file_to_page, $output, $roots);


# Tree operations
# FIXME: Put them in their own module

# For debugging
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
    if (tree_isleaf($tree)) {
      $tree = undef;
      last;
    }
    $tree = $tree->{$elem};
  }
  return $tree;
}

# Set subtree at given path to given value, creating any intermediate
# nodes required
sub tree_set {
  my ($tree, $path, $val) = @_;
  my @path = @{$path};
  my $leaf = pop @path;
  return unless defined($leaf); # FIXME: Ignore attempts to set entire tree
  foreach my $node (@path) {
    $tree->{$node} = {} if tree_isleaf($tree->{$node});
    $tree = $tree->{$node};
  }
  if (defined($val)) {
    $tree->{$leaf} = $val;
  } else {
    delete $tree->{$leaf};
  }
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


# Append relative path to search path
sub make_relative_path {
  my ($file, @search) = @_;
  my @filepath = split m|/|, $file;
  # Append file path, coping with `..' and `.'. There is no
  # obvious standard function to do this: File::Spec::canonpath does
  # not do `..' removal, as that does not work with symlinks; in
  # other words, our relative paths don't behave in the presence of
  # symlinks.
  foreach my $elem (@filepath) {
    if ($elem eq "..") {
      pop @search;
    } elsif ($elem ne ".") {
      push @search, $elem;
    }
  }
  return @search;
}

# Search for file starting at the given path; if found return its
# path, contents and file name; if not, print a warning and return
# undef.
sub inherit_file {
  my ($path, $file) = @_;
  my (@foundpath, $contents);
  for (my @search = @{$path}; 1; pop @search) {
    my ($thissearch, $new_contents, $node) = slurp_file($file, @search);
    if (defined($new_contents)) {
      print STDERR "  " . catfile(@{$thissearch}) . "\n" if $list_files_flag;
      warn("`" . catfile(@{$thissearch}) . "' is identical to `" . catfile(@foundpath) . "'")
        if $warn_flag && defined($contents) && $new_contents eq $contents;
      @foundpath = @{$thissearch};
      $contents = $new_contents;
      if ($file_to_page) {
        my $used_list = tree_get($file_to_page, $thissearch);
        if (UNIVERSAL::isa($used_list, "ARRAY")) {
          push @{$used_list}, $path;
        } else {
          tree_set($file_to_page, $thissearch, [$path]);
        }
      }
      last;
    }
    last if $#search == -1;
  }
  warn("Cannot find `$file' while building `" . catfile(@{$path}) ."'\n") unless $contents;
  return \@foundpath, $contents;
}

# Process a command; if the command is undefined, replace it, uppercased
sub do_macro {
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
sub do_macros {
  my ($text, %macros) = @_;
  1 while $text =~ s/\$([[:lower:]]+){(((?:(?!(?<!\\)[{}])).)*?)(?<!\\)}/do_macro($1, $2, %macros)/ge;
  return $text;
}

# Expand commands in some text
#   $text - text to expand
#   $path - leaf directory to make into a page
# returns expanded text
sub expand {
  my ($text, $path) = @_;
  my %macros = (
    root => sub {
      return join "/", (("..") x $#{$path}) if $#{$path} > 0;
      return ".";
    },
    include => sub {
      my ($file) = @_;
      my ($fragpath, $contents) = inherit_file($path, $file);
      return $contents if $fragpath;
      return "";
    },
    run => sub {
      my ($prog) = shift;
      my ($fragpath, $contents) = inherit_file($path, $prog);
      return &{eval(untaint($contents))}(@_, $path) if $fragpath;
      return "";
    },
  );
  $text = do_macros($text, %macros);
  # Convert $Macro back to $macro
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;

  return $text;
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

# File file object in multiple source trees, masking out empty files
# and directories
sub find {
  my ($path) = @_;
  my $obj;
  foreach my $root (reverse @{$roots}) {
    my $filename = catfile($root, @{$path});
    if (-f $filename) {
      $obj = $filename;
      undef $obj if -z $filename;
    } elsif (-d $filename) {
      my @path = @{$path};
      while ($#path >= 0) {
        pop @path;
        $obj = catfile($root, @path);
        if (-d $obj) {
          opendir(my $dh, $obj) || die "cannot opendir $obj: $!";
          my @dots = grep {/^\./} readdir($dh);
          closedir $dh;
          if ($#dots == -1) {
            undef $obj;
            last;
          }
        }
      }
    }
  }
  return $obj;
}

# Find a file name in the tree given a search position and relative path
# Return tree path and file name
sub get_file {
  my ($path, @search) = @_;
  my @filepath = make_relative_path($path, @search);
  # FIXME: Implement stat caching for persistent use
  my $node = tree_get($files, \@filepath);
  if (!$node) {
    $node = find(\@filepath);
    tree_set($files, \@filepath, $node);
  }
  return \@filepath, $node;
}

# Find a file name with get_file and slurp it if it exists
# Return tree path, contents and file name
sub slurp_file {
  my ($path, @search) = @_;
  my ($filepath, $node) = get_file($path, @search);
  my $contents;
  $contents = slurp($node)
    if defined($node) && tree_isleaf($node); # We have a file, not a directory
  return $filepath, $contents, $node;
}

# Add a file to the output
sub add_output {
  my ($path) = @_;
  my ($filepath, $contents) = slurp_file($path);
  tree_set($output, $filepath, $contents) if $contents;
}

# Expand a file system object, recursively expanding links
sub expand_page {
  my ($path, $template) = @_;
  # Don't expand the same node twice
  if (!defined(tree_get($output, $path))) {
    my $node = get_file(catfile(@{$path}));
    # If we are looking at a non-leaf node, expand it
    if ($#$path != -1 && defined($node) && -d $node) {
      print STDERR catfile(@{$path}) . ":\n" if $list_files_flag;
      my $out = expand("\$include{$template}", $path);
      print STDERR "\n" if $list_files_flag;
      tree_set($output, $path, $out);

      # Find all local links and add them to output (a local link is
      # one that doesn't start with a URI scheme)
      my @links = $out =~ /\Whref\s*=\s*\"(?![a-z]+:)([^\"\#]+)/g;
      push @links, $out =~ /\Wsrc\s*=\s*\"(?![a-z]+:)([^\"\#]+)/g;
      foreach my $link (@links) {
        # Remove current directory, which represents a page
        my @pagepath = make_relative_path($link, @{$path}[0..$#{$path} - 1]);
        no warnings qw(recursion); # We may recurse deeply.
        my $node = get_file(catfile(@pagepath));
        if (!defined($node)) {
          print STDERR "Broken link from `" . catfile(@{$path}) . "' to `" . catfile(@pagepath) . "'\n";
        } else {
          expand_page(\@pagepath, $template);
        }
      }
    } else {
      add_output(catfile(@{$path}));
    }
  }
}

# Macro expand a tree
sub expand_tree {
  my ($template, $start);
  ($roots, $template, $start, $warn_flag, $list_files_flag) = @_;

  $files = {};
  $file_to_page = {};
  $output = {};
  expand_page([$start], $template);

  # Analyse generated pages to print warnings if desired
  if ($warn_flag) {
    # Check for files all of whose uses are in a sub-directory of the
    # file's parent directory.
    foreach my $path (@{tree_iterate_preorder($files, [], undef)}) {
      my $node = tree_get($file_to_page, $path);
      if (tree_isleaf($node) && UNIVERSAL::isa($node, "ARRAY")) {
        my $prefix = $#{@{$node}[0]};
        foreach my $page (@{$node}) {
          for (; $prefix >= 0 && !(@{$page}[0..$prefix] ~~ @{@{$node}[0]}[0..$prefix]);
               $prefix--) {}
        }
        my @dir = @{@{$node}[0]}[0..$prefix];
        print STDERR "`" . catfile(@{$path}) . "' could be moved into `" . catfile(@dir) . "'\n"
          if defined(tree_get($files, \@dir)) && $#{$path} <= $prefix && !(@dir ~~ @{$path});
      }
    }
  }

  return $output;
}


return 1;
