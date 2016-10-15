# Makefile for Nancy

VERSION=`git describe --tags`

nancy: perl/Macro.pm nancy.in GNUmakefile
	rm -f $@
	echo '#!/usr/bin/perl' > $@
	cat perl/Macro.pm >> $@
	cat nancy.in >> $@
	sed -e "s/use RRT::Macro 3...;/RRT::Macro->import('expand');/" -i $@
	chmod +x $@

%.md-html: %.md
	markdown $< > $@

%.html: %.md-html nancy
	./nancy build-aux/markdown-html-template.html $< > $@

# Try to be helpful if user did not git clone correctly
perl/Macro.pm:
	@test -d .git && ( test -d perl || ( echo "Cannot find perl modules: did you git clone --recursive?"; exit 1 ) )

Cookbook.md: Cookbook.md.in nancy
	./nancy --output $@ $< $@

check: nancy
	cd test && ./dotest

DIST_FILES = nancy README.md logo/nancy-small.png Cookbook.md Cookbook.md.in

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
	rm -f nancy.in && git checkout nancy.in && $(MAKE) nancy # Get correct version number in nancy.in
	woger github \
		github_user="rrthomas" \
		github_dist_type="universal-runnable" \
		package="nancy" \
		version=$(VERSION) \
		dist_type="zip"

website-example: check
	cd test && \
	rm -rf dest && \
	mkdir dest && \
	cp -a cookbook-example-website-assets/* cookbook-example-website-expected/* dest/ && \
	cd dest && \
	python3 -m http.server
