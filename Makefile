# Makefile for Nancy

nancy: perl/Macro.pm nancy.in Makefile
	rm -f $@
	echo '#!/usr/bin/perl' > $@
	cat perl/Macro.pm >> $@
	cat nancy.in >> $@
	sed -e "s/use RRT::Macro 3.13;/RRT::Macro->import('expand');/" -i $@
	chmod +x $@

check: nancy
	cd test && ./dotest
