# Development Scratch Pad

## Testing during development

TODO: Notes on testing during development.

For `devenv-test`, accomplish this:

```python
"""
docker run -it --rm `
  -v "$env:USERPROFILE\Development\dev-base:/home/basicuser/repo-source:ro" `
  --name git_loaded `
  python-dev-loaded
"""

"""
git config --global --add safe.directory '*'

git clone \
  file:///home/basicuser/repo-source/dev-bootstrap-closed \
  ~/dev-bootstrap-closed
a
python3 ~/dev-bootstrap-closed/devenv/install.py

source ~/.bashrc
"""


```
