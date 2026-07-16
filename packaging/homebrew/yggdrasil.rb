# Homebrew formula for Yggdrasil.
#
# This lives in a tap (e.g. github.com/VonderVuflya/homebrew-tap) as
# Formula/yggdrasil.rb, so users can:  brew install VonderVuflya/tap/yggdrasil
#
# Yggdrasil is a pure-stdlib Python package with ZERO runtime dependencies, so
# the formula just installs `yggdrasil-memory` from PyPI into an isolated
# virtualenv and links the `ygg` command. After publishing to PyPI, fill in the
# real `url` + `sha256` (see RELEASING.md for the one-liner that prints both).
class Yggdrasil < Formula
  include Language::Python::Virtualenv

  desc "One shared, durable memory for your AI coding agents (MCP, local-first)"
  homepage "https://github.com/VonderVuflya/yggdrasil"
  url "https://files.pythonhosted.org/packages/c1/08/2e030455b09f88404c992266ce4331676b36d553a04ea2b44ccff16199bc/yggdrasil_memory-0.12.0.tar.gz"
  sha256 "9ee973abebe44172cfc5215d717935999c384de56d36fb7c3c34b486df55b4d0"
  license "AGPL-3.0-or-later"
  head "https://github.com/VonderVuflya/yggdrasil.git", branch: "main"

  depends_on "python@3.12"

  def install
    # No PyPI dependencies (stdlib only) -> nothing extra to vendor as resources.
    virtualenv_install_with_resources
  end

  test do
    assert_match "yggdrasil", shell_output("#{bin}/ygg version")
  end
end
