{
  pkgs,
  lib,
  config,
  inputs,
  ...
}: {
  languages.python = {
    enable = true;
    version = "3.12";
    venv.enable = true;
  };

  pre-commit.hooks.alejandra.enable = true;
  pre-commit.hooks.ruff.enable = true;
  pre-commit.hooks.ruff-format.enable = true;
}
