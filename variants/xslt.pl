# XSLT action
use XML::LibXSLT;
use XML::LibXML;

xslt => sub {
  my ($sheetfile, $xmlfile, %params) = @_;
  my $parser = XML::LibXML->new();
  my $xslt = XML::LibXSLT->new();
  my $source = $parser->parse_file($xmlfile);
  my $stylesheet = $xslt->parse_stylesheet_file($sheetfile);
  return $stylesheet->output_string($stylesheet->transform($source, XML::LibXSLT::xpath_to_string(%params)));
},

# Corresponding xml2html.html
$xslt{../wordml2html.xsl,../XML source/$page{}.xml,destroot,../site,thispage,$page{}.html}
