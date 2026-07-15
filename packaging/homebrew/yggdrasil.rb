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
  url "https://files.pythonhosted.org/packages/ac/b6/7707ea918db8ab46660c41051cc0f60df9a98f780903418aed964b5f47d0/yggdrasil_memory-0.11.0.tar.gz"
  sha256 "aedf7495c0c8897d998f7defb2dc23ee3a297c643d1f4c23b6ae2997552e267b"
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
