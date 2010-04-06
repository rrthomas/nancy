# RRT::Misc (c) 2003-2009 Reuben Thomas (rrt@sc3d.org; http://rrt.sc3d.org)
# Distributed under the GNU General Public License

# This module contains various misc code that I reuse, but don't
# consider worth packaging for others (i.e. it reflects my taste,
# laziness and ignorance more than general utility!)

# FIXME: Need slurpText and spew[Text] to avoid needing to remember
# incantations.

require 5.8.4;
package RRT::Misc;

use strict;
use warnings;

use Perl6::Slurp;
use POSIX 'floor';
use File::Basename;
use Cwd 'abs_path';
use Encode;

BEGIN {
  use Exporter ();
  our ($VERSION, @ISA, @EXPORT, @EXPORT_OK);
  $VERSION = 0.05;
  @ISA = qw(Exporter);
  @EXPORT = qw(&untaint &touch &which &cleanPath &normalizePath &readDir
               &getMime &getMimeType &getMimeEncoding &numberToSI);
}
our @EXPORT_OK;


# Untaint the given value
# FIXME: Use CGI::Untaint
sub untaint {
  my ($var) = @_;
  return if !defined($var);
  $var =~ /^(.*)$/ms;           # get untainted value in $1
  return $1;
}

# Touch the given objects, which must exist
sub touch {
  my $now = time;
  utime $now, $now, @_;
}

# Find an executable on the PATH
sub which {
  my ($prog) = @_;
  my @progs = grep { -x $_ } map { "$_/$prog" } split(/:/, $ENV{PATH});
  return shift @progs;
}

# Check the given path is clean (no ".." components)
sub cleanPath {
  my ($path) = @_;
  $path = "" if !$path;
  return $path !~ m|^\.\./| && $path !~ m|/\.\.$| && $path !~ m|/\.\./|;
}

# Normalize a path possibly relative to another
sub normalizePath {
  my ($file, $currentDir) = @_;
  return "" if !cleanPath($file);
  my $path = "";
  $path = (fileparse($currentDir))[1] if $currentDir && $currentDir ne "";
  if ($file !~ m|^/|) {
    $file = "$path$file";
  } else {
    $file =~ s|^/||;
  }
  $file =~ s|^\./||;
  return $file;
}

# Return the readable non-dot files in a directory as a list
sub readDir {
  my ($dir, $test) = @_;
  $test ||= sub {
    my $file = abs_path(shift);
    if (defined($file)) {
      return (-f $file || -d _) && -r _;
    } else {
      return 0;
    }
  };
  opendir(DIR, $dir) || return ();
  my @entries = grep {/^[^.]/ && &{$test}(decode_utf8($dir) . "/" . decode_utf8($_))} readdir(DIR);
  closedir DIR;
  return @entries;
}

# FIXME: Use File::LibMagic instead of next 3 subs

# Return the MIME type, and possibly encoding, of the given file
sub getMime {
  my ($file) = @_;
  local *READER;
  open(READER, "-|", "mimetype", $file);
  my $mimetype = slurp \*READER;
  chomp $mimetype;
  return $mimetype;
}

# Return the MIME type of the given file
sub getMimeType {
  my ($file) = @_;
  my $mime = getMime($file);
  $mime =~ s/;.*$//;
  return $mime;
}

# Return the MIME encoding of the given file, or "binary" if none
sub getMimeEncoding {
  my ($file) = @_;
  my $mime = getMime($file);
  $mime =~ s/.*; charset=//;
  $mime = "binary" if $mime eq "";
  return $mime;
}

# Convert a number to SI (3sf plus suffix)
# If outside SI suffix range, use "e" plus exponent
sub numberToSI {
  my ($n) = shift;
  my %SIprefix = (
    -8 => "y", -7 => "z", -6 => "a", -5 => "f", -4 => "p", -3 => "n", -2 => "mu", -1 => "m",
    1 => "k", 2 => "M", 3 => "G", 4 => "T", 5 => "P", 6 => "E", 7 => "Z", 8 => "Y"
  );
  my $t = sprintf "% #.2e", $n;
  $t =~ /.(.\...)e(.+)/;
  my ($man, $exp) = ($1, $2);
  my $siexp = floor($exp / 3);
  my $shift = $exp - $siexp * 3;
  my $s = $SIprefix{$siexp} || "e" . $siexp;
  $s = "" if $siexp == 0;
  $man = $man * (10 ** $shift);
  return $man . $s;
}


1;                              # return a true value
