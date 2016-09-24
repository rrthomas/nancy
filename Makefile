# Makefile for Nancy

VERSION=`git describe --tags`

nancy: perl/Macro.pm nancy.in Makefile
	rm -f $@
	rm -f nancy.in && git checkout nancy.in # Get correct version number in nancy.in
	echo '#!/usr/bin/perl' > $@
	cat perl/Macro.pm >> $@
	cat nancy.in >> $@
	sed -e "s/use RRT::Macro 3.13;/RRT::Macro->import('expand');/" -i $@
	chmod +x $@

check: nancy
	cd test && ./dotest

DIST_FILES = nancy README.md logo/nancy-small.png Cookbook.md

dist: check
	rm -f nancy-$(VERSION)
	ln -s . nancy-$(VERSION)
	for i in $(DIST_FILES); do \
		zip nancy-$(VERSION).zip "nancy-$(VERSION)/$$i"; \
	done
	rm -f nancy-$(VERSION)

release: dist
	echo $(VERSION) | grep -v -e - || ( echo "Current version $(VERSION) is not a release version"; exit 1 )
	git diff --exit-code && \
	woger github \
		github_user="rrthomas" \
		github_dist_type="universal-runnable" \
		package="nancy" \
		version=$(VERSION) \
		dist_type="zip"
