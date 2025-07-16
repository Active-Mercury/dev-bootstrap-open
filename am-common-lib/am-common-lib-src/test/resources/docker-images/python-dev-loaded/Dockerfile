FROM python-dev

# Install shell tools, node & npm as root
USER root
RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    zsh \
    nodejs \
    npm \
    shfmt \
    jq \
  && rm -rf /var/lib/apt/lists/*

# Switch to basicuser and set up a local formatter project
USER basicuser
WORKDIR /home/basicuser/prettier-formatter
RUN npm init -y \
  && npm install --save-dev prettier prettier-plugin-sh

WORKDIR /home/basicuser

# Keep bash as the default shell
CMD ["bash"]
