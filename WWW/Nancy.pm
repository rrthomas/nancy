# Nancy.pm $Revision: 982 $ ($Date: 2009-10-04 22:01:25 +0100 (Sun, 04 Oct 2009) $)
# (c) 2002-2009 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org/)
# Distributed under the GNU General Public License version 3, or (at
# your option) any later version. There is no warranty.

# FIXME: Write proper API documentation in POD

package WWW::Nancy;

use strict;
use warnings;

use File::Basename;
use File::Spec::Functions qw(catfile splitdir);


my ($list_files_flag, $fragments);


# Search for fragment starting at the given path; if found return
# its name, if not, print a warning and return undef.
sub findFragment {
  my ($path, $fragment) = @_;
  my $search_path = $path;
  while (1) {
    my $name = catfile($search_path, $fragment);
    $name =~ s|^\./||;
    if (defined($fragments->{$name})) {
      print STDERR "  $name\n" if $list_files_flag;
      return $name;
    }
    last if $search_path eq "." || $search_path eq "/"; # Keep going until we go above $path
    $search_path = dirname($search_path);
  }
  warn("Cannot find `$fragment' while building `$path'\n");
  return undef;
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
#   $tree - source tree
#   $page - leaf directory to make into a page
#   $fragments - map from fragment names to contents
#   $list_files_flag - whether to output fragment diagnostics
#   [$fragment_to_page] - optional hash to which to add fragment->page entries
# returns expanded text
sub expand {
  my ($text, $tree, $page, $fragment_to_page);
  ($text, $tree, $page, $fragments, $list_files_flag, $fragment_to_page) = @_;
  my %macros = (
    page => sub {
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
      my $name = findFragment($page, $fragment);
      my $text = "";
      if ($name) {
        push @{$fragment_to_page->{$name}}, $page
          if defined($fragment_to_page);
        $text .= "***INCLUDE: $name***" if $list_files_flag;
        $text .= $fragments->{$name};
      }
      return $text;
    },
    run => sub {
      my ($prog) = @_;
      shift;
      my $name = findFragment($page, $prog);
      if ($name) {
        push @{$fragment_to_page->{$prog}}, $page
          if defined($fragment_to_page);
        my $sub = eval($fragments->{$name});
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

return 1;
