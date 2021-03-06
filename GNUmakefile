# Makefile for Nancy

VERSION=`git describe --tags`

all: nancy Cookbook.md

nancy: perl/Macro.pm nancy.in GNUmakefile
	rm -f $@
	echo '#!/usr/bin/perl' > $@
	cat perl/Macro.pm >> $@
	cat nancy.in >> $@
	sed -e "s/use RRT::Macro 3...;/RRT::Macro->import('expand');/" -i $@
	chmod +x $@

# Try to be helpful if user did not git clone correctly
perl/Macro.pm:
	@test -d .git && ( test -d perl || ( echo "Cannot find perl modules: did you git clone --recursive?"; exit 1 ) )

Cookbook.md: Cookbook.md.in nancy
	./nancy --output $@ $< $@

check: nancy
	cd test && ./dotest

dist: all check
	rm -f nancy.in && git checkout nancy.in && $(MAKE) nancy # Get correct version number in nancy.in
	rm -f nancy-*.zip nancy-$(VERSION)
	ln -s . nancy-$(VERSION)
	zip -r nancy-$(VERSION).zip nancy-$(VERSION)/* --symlinks --exclude=nancy-$(VERSION)/nancy-$(VERSION) --exclude=\*/.\* --exclude=\*/setup-git-config
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

website-example:
	cd test && \
	mkdir website-example && \
	cp -a cookbook-example-website-assets/* cookbook-example-website-expected/* website-example/ && \
	xdg-open file://`pwd`/website-example/index.html
