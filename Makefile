.PHONY: help hooks dist formula-sha

help:
	@echo "claude-setup make targets:"
	@echo "  make hooks   install the pre-commit hook (git config core.hooksPath .githooks)"

hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit
	@echo "pre-commit hook installed: core.hooksPath -> .githooks"

VERSION := $(shell python3 -c "import ccpkg; print(ccpkg.__version__)")
DIST := dist/ccpkg-$(VERSION).tar.gz

dist:
	@rm -rf dist && mkdir -p dist/ccpkg-$(VERSION)
	@cp -R ccpkg manifest.json home mboard install.sh LICENSE dist/ccpkg-$(VERSION)/
	@find dist/ccpkg-$(VERSION) -name '__pycache__' -type d -prune -exec rm -rf {} +
	@tar -C dist -czf $(DIST) ccpkg-$(VERSION)
	@rm -rf dist/ccpkg-$(VERSION)
	@shasum -a 256 $(DIST)
	@echo "dist: wrote $(DIST)"

# Compute the sha256 of the GitHub tag archive for Formula/ccpkg.rb.
# Usage: make formula-sha VERSION=0.1.0   (defaults to ccpkg.__version__)
formula-sha:
	@curl -fsSL "https://github.com/aahilshaikh-twlbs/ccpkg/archive/refs/tags/v$(VERSION).tar.gz" \
		| shasum -a 256 | awk '{print $$1}'
