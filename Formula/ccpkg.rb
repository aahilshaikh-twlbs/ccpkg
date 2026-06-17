class Ccpkg < Formula
  desc "Claude Code environment-as-code installer"
  homepage "https://github.com/aahilshaikh-twlbs/ccpkg"
  url "https://github.com/aahilshaikh-twlbs/ccpkg/archive/refs/tags/v0.7.0.tar.gz"
  sha256 "f4ba1949c8a8f880ce78e4ccb2d605129ec6df4d6b71f53485880280849eb1f0"
  license "MIT"

  depends_on "jq"
  depends_on "python@3.12"

  def install
    libexec.install "ccpkg", "manifest.json", "home", "mboard", "install.sh", "LICENSE"
    (bin/"ccpkg").write <<~SH
      #!/bin/bash
      export CCPKG_ROOT="#{opt_libexec}"
      export PYTHONPATH="#{opt_libexec}${PYTHONPATH:+:$PYTHONPATH}"
      exec "#{Formula["python@3.12"].opt_bin}/python3.12" -m ccpkg "$@"
    SH
  end

  def caveats
    <<~EOS
      ccpkg installed its bundled Claude Code environment into:
        #{libexec}
      Apply it to your ~/.claude (and re-apply after each `brew upgrade ccpkg`):
        ccpkg apply   # interactive picker, or replays your saved selection headlessly
      `ccpkg push` is disabled in this packaged install (it needs a git checkout).
    EOS
  end

  test do
    assert_match "ccpkg #{version}", shell_output("#{bin}/ccpkg --version")
    system bin/"ccpkg", "status", "scan"
  end
end
