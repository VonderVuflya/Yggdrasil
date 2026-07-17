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
  url "https://files.pythonhosted.org/packages/2a/89/9bd8cb95e1aa7e62d1322414f88d43f62a3d893c1103b779b6e63bdfa67d/yggdrasil_memory-0.13.1.tar.gz"
  sha256 "621e0c23b823b794b190c9d9e7cfeb21a98e46d8a8ec4ab391a4519421e82378"
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
