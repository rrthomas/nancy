# Makefile for Nancy

nancy: nancy.in perl/Macro.pm
	rm -f nancy
	cat $^ >> nancy
	chmod +x nancy

check: nancy
	cd test && ./dotest
