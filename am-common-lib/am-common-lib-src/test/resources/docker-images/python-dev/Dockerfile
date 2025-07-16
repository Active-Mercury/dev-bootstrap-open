FROM python:3.13

# Install sudo and pipenv, then clean up apt caches
RUN apt-get update \
  && apt-get install -y --no-install-recommends sudo \
  && pip install --no-cache-dir pipenv \
  && rm -rf /var/lib/apt/lists/*

# Create basicuser (no sudo), and superuser (in sudo group, no-password sudo)
RUN useradd -m basicuser \
  && useradd -m superuser -G sudo \
  && echo "superuser ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/superuser \
  && chmod 0440 /etc/sudoers.d/superuser

# Make basicuser the default user
USER basicuser
WORKDIR /home/basicuser

# Start bash by default rather than python
CMD ["bash"]
