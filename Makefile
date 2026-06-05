.PHONY: help hooks dist

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
	@cp -R ccpkg manifest.json home mailbox install.sh LICENSE dist/ccpkg-$(VERSION)/
	@find dist/ccpkg-$(VERSION) -name '__pycache__' -type d -prune -exec rm -rf {} +
	@tar -C dist -czf $(DIST) ccpkg-$(VERSION)
	@rm -rf dist/ccpkg-$(VERSION)
	@shasum -a 256 $(DIST)
	@echo "dist: wrote $(DIST)"
