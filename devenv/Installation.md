# Installation

## Shell Imports

To install the shell imports, run the following and add the resulting output to the end of `~/.bashrc` or `~/.zshrc`:

```bash
SHELL_IMPORTS_DIR="$(pwd)/shell_imports"
echo "source $SHELL_IMPORTS_DIR/git_basic_shortcuts.sh"
```

## Other Shell Scripts

```bash
HOME_BIN=~/bin
DEV_ENV_DIR=$(pwd)
mkdir -p $HOME_BIN

ln -sf "$DEV_ENV_DIR/scripts/cli_echo.py" $HOME_BIN/cli-echo
ln -sf "$DEV_ENV_DIR/scripts/cli_echo_all.py" $HOME_BIN/cli-echo-all
ln -sf "$DEV_ENV_DIR/scripts/git_toplevel.py" $HOME_BIN/gtl
```