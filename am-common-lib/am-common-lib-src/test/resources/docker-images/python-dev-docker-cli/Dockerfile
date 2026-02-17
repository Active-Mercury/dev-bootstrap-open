FROM python-dev-loaded

USER root

RUN useradd -m dockeruser

RUN apt-get update \
  && apt-get install -y --no-install-recommends \
    docker-cli \
  && rm -rf /var/lib/apt/lists/* \
  && docker --version

COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh
ENTRYPOINT ["entrypoint.sh"]

WORKDIR /home/dockeruser
CMD ["bash"]
