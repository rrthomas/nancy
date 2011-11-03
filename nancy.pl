#!/usr/bin/perl
# Web wrapper for Nancy
# (c) 2002-2011 Reuben Thomas (rrt@sc3d.org, http://rrt.sc3d.org)
# Distributed under the GNU General Public License

use strict;
use warnings;

use File::Spec::Functions qw(splitdir catfile);
use File::Glob qw(:glob);
use CGI qw(:standard);
use CGI::Util qw(unescape);

use File::Slurp qw(slurp);
use File::MimeInfo;

# Configuration variables
my $BaseUrl = "/" . $ENV{NANCY_WEB_ROOT};
my $BaseDir = bsd_glob($ENV{NANCY_WEB_ROOT}, GLOB_TILDE);
my $Template = $ENV{NANCY_TEMPLATE} || "template";
my $Home = $ENV{NANCY_HOME} || "index.html";
my $list_files = $ENV{NANCY_LIST_FILES};

# Extract file name from URL
my $page = unescape(url(-absolute => 1));
$page =~ s|^$BaseUrl||;

# Extract site name and page name to calculate source roots
$page =~ s|/$||;
my @path = splitdir($page);
my $site = shift @path || "";

# Read source roots
my $site_root = catfile($BaseDir, $site);
opendir(my $dh, $site_root) || die "cannot read `$site_root': $!";
my @source_roots = map { catfile($site_root, $_) } sort {$b cmp $a} (grep {/^[^.]/} readdir($dh));
closedir $dh;

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
      print STDERR "  $node\n" if $list_files;
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
      return $file ? &{eval($contents)}(@_, $path, @roots) : "";
    },
  );
  $text = do_macros($text, %macros);
  # Convert `$Macro' back to `$macro'
  $text =~ s/(?!<\\)(?<=\$)([[:upper:]])(?=[[:lower:]]*{)/lc($1)/ge;

  return $text;
}

# Process request
$path[$#path] =~ m/(\.[^.]*)$/;
my $ext = $1 || "";
my $node = find_in_trees(\@path, @source_roots);
if ($node) {
  if (-f $node) { # If a file, serve it
    print header(-type => mimetype($page)) . slurp($node);
    exit;
  } elsif (-d $node && $ext eq "") {
    push @path, $Home;
    print redirect("$BaseUrl$site/" . (join "/", @path));
    exit;
  }
} else { # If not found, give a 404
  ($Template, $ext) = ("404", ".html");
}

# Output page
print STDERR catfile(@path) . "\n" if $list_files; # implement via environment variable
print header(-type => "application/xhtml+xml") . expand("\$include{$Template$ext}", \@path, @source_roots);
