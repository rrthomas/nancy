module namespace nc = "https://github.com/rrthomas/nancy/raw/master/nancy.dtd";
declare %public function nc:path-to-root($path as xs:string) as xs:string {
  string-join((for $_ in 1 to count(tokenize($path, '/')) return '..'), '/')
};
