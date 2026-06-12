class Ccpkg < Formula
  desc "Claude Code environment-as-code installer"
  homepage "https://github.com/aahilshaikh-twlbs/ccpkg"
  url "https://github.com/aahilshaikh-twlbs/ccpkg/archive/refs/tags/v0.2.2.tar.gz"
  sha256 "043a0338944c303cfbd188c07a39e297671e48702c817d7c746b0f6188f12571"
  license "MIT"

  depends_on "jq"
  depends_on "python@3.12"

  def install
    libexec.install "ccpkg", "manifest.json", "home", "mailbox", "install.sh", "LICENSE"
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
        ccpkg install   # interactive picker, or
        ccpkg pull      # apply the saved/default selection headlessly
      `ccpkg push` is disabled in this packaged install (it needs a git checkout).
    EOS
  end

  test do
    assert_match "ccpkg #{version}", shell_output("#{bin}/ccpkg --version")
    system bin/"ccpkg", "scan"
  end
end
