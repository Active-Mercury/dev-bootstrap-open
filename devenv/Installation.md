# Installation

Automated installation is available via a script that is in beta:

```bash
# Get help
python3 devenv/install.py -h

# Run for real
python3 devenv/install.py --rc-file ~/.zshrc
```

## Shell Imports

To install the shell imports, run the following and add the resulting output to
the end of `~/.bashrc` or `~/.zshrc`:

```bash
SHELL_IMPORTS_DIR="$(pwd)/devenv/shell_imports"
echo "source $SHELL_IMPORTS_DIR/git_basic_shortcuts.sh"
```

## Other Shell Scripts

```bash
HOME_BIN=~/bin
DEV_ENV_DIR=$(pwd)
mkdir -p $HOME_BIN

ln -sf "$DEV_ENV_DIR/devenv/scripts/cli_echo.py" $HOME_BIN/cli-echo
ln -sf "$DEV_ENV_DIR/devenv/scripts/cli_echo_all.py" $HOME_BIN/cli-echo-all
ln -sf "$DEV_ENV_DIR/devenv/scripts/git_toplevel.sh" $HOME_BIN/gtl
```
