{ pkgs
, lib
, config
, inputs
, ...
}: {
  dotenv.enable = true;

  languages.python = {
    enable = true;
    version = "3.11";
    uv.enable = true;
  };

  git-hooks.hooks.nixpkgs-fmt.enable = true;
  git-hooks.hooks.mypy.enable = true;
  git-hooks.hooks.ruff.enable = true;
  git-hooks.hooks.ruff-format.enable = true;

  scripts.friskis.exec = "python -m friskis";
  scripts.friskisd.exec = "python -m friskis.daemon";

  scripts.deploy.exec = ''
    ssh root@$FRISKIS_HOST "\
      git -C /opt/friskis pull --rebase && \
      systemctl restart friskisd.service
    "
  '';
}
