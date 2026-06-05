# Releasing ccpkg

ccpkg is distributed via an in-repo Homebrew formula (`Formula/ccpkg.rb`), tapped by URL.

## Cut a release

1. Bump the version in `ccpkg/__init__.py` (`__version__`) and commit.
2. Tag and push:
   ```sh
   git tag vX.Y.Z
   git push origin vX.Y.Z
   ```
3. Compute the tag-archive checksum:
   ```sh
   make formula-sha VERSION=X.Y.Z
   ```
4. In `Formula/ccpkg.rb`, set `url` to the `vX.Y.Z` archive and paste the `sha256`. Commit.
5. (Maintainer) validate the formula:
   ```sh
   brew install --build-from-source Formula/ccpkg.rb
   brew test ccpkg
   brew audit --formula Formula/ccpkg.rb
   ```

## Install (consumers)

```sh
brew tap aahilshaikh-twlbs/ccpkg https://github.com/aahilshaikh-twlbs/ccpkg
brew install ccpkg
# upgrade later:
brew update && brew upgrade ccpkg
```

The formula installs the runtime payload into Homebrew's `libexec` and provides a
`ccpkg` wrapper that sets `CCPKG_ROOT` (see the "Running from a package" section of the
README). `ccpkg push` is intentionally disabled in a packaged install — clone the repo
for the development workflow.
