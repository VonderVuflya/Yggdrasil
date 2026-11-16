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
  url "https://files.pythonhosted.org/packages/fe/c6/7533a231633124932f6d0fe40e639e788cf59bd583a63fdf4408d77726c4/yggdrasil_memory-0.18.0.tar.gz"
  sha256 "f2c2b44acecdc477a4ac15b13989de6f2c476694b33f3dbcd8df171269effa44"
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
