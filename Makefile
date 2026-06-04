.PHONY: help hooks

help:
	@echo "claude-setup make targets:"
	@echo "  make hooks   install the pre-commit hook (git config core.hooksPath .githooks)"

hooks:
	git config core.hooksPath .githooks
	chmod +x .githooks/pre-commit
	@echo "pre-commit hook installed: core.hooksPath -> .githooks"
