# Nancy.pm $Revision$ ($Date$)
# (c) 2002-2010 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

# FIXME: Write proper API documentation in POD

package WWW::Nancy;

use strict;
use warnings;

use File::Spec::Functions qw(catfile);

use File::Slurp qw(slurp); # Also used in $run scripts
use RRT::Misc qw(untaint);

our ($list_files_flag);


# Remove `..' and `.' components from a path
sub normalize_path {
  my @in_path = @_;
  my @out_path = ();
  foreach my $elem (@in_path) {
    if ($elem eq "..") {
      pop @out_path;
    } elsif ($elem ne ".") {
      push @out_path, $elem;
    }
  }
  return @out_path;
}

# File file in multiple source trees
sub find_in_trees {
  my ($path, @roots) = @_;
  my @norm_path = normalize_path(@{$path});
  foreach my $root (@roots) {
    my $obj = catfile($root, @norm_path);
    return $obj if -e $obj;
  }
  return undef;
}

# Search for file starting at the given path; if found return its
# path, contents and file name; if not, print a warning and return
# undef.
sub find_on_path {
  my ($path, $link, @roots) = @_;
  for (my @search = @{$path}; 1; pop @search) {
    my $thissearch = [@search, split "/", $link];
    my $node = find_in_trees($thissearch, @roots);
    if (defined($node)) {
      my $contents = slurp($node);
      print STDERR "  $node\n" if $list_files_flag;
      return $thissearch, $contents if $contents;
    }
    last if $#search == -1;
  }
  warn "Cannot find `$link' while building `" . catfile(@{$path}) ."'\n";
}

# Process a command; if the command is undefined, replace it, uppercased
sub do_macro {
  my ($macro, $arg, %macros) = @_;
  return $macros{$macro}(split /(?<!\\),/, ($arg || ""))
    if defined($macros{$macro});
  $macro =~ s/^(.)/\u$1/;
  return "\$$macro\{$arg}";
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
#   @roots - list of roots of trees to scan
# returns expanded text
sub expand {
  my ($text, $path, @roots) = @_;
  my %macros = (
    root => sub {
      return join "/", (("..") x $#{$path}) if $#{$path} > 0;
      return ".";
    },
    include => sub {
      my ($link) = @_;
      my ($file, $contents) = find_on_path($path, $link, @roots);
      return $file ? $contents : "";
    },
    run => sub {
      my ($prog) = shift;
      my ($file, $contents) = find_on_path($path, $prog, @roots);
      return $file ? &{eval(untaint($contents))}(@_, $path, @roots) : "";
    },
  );
  $text = do_macros($text, %macros);
  # Convert `$Macro' back to `$macro'
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;

  return $text;
}


return 1;
