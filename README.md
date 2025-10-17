# dev-bootstrap-open

Scripts and docs to start developing on a new machine.

## Docker-in-Docker (dind-dev) Image

The `dind-dev` image provides an isolated environment for running tasks that
need to create and manage their own Docker containers. This is particularly
useful for CI/CD pipelines, testing, and development workflows that require
container isolation.

### Sample Usage

```bash
CONTAINER_NAME="my-dind"
VOLUME_NAME="dind-cache"
HOST_PATH="$HOME"
CONTAINER_PATH="src"
WORK_DIR="/home/dockeruser"
COMMAND=("echo" "Hello")

# Clean up any existing container
docker rm -f ${CONTAINER_NAME} 2> /dev/null

# Start the dind container
docker run --privileged -d \
  --name ${CONTAINER_NAME} \
  -v ${VOLUME_NAME}:/var/lib/docker \
  -v "${HOST_PATH}:/home/dockeruser/${CONTAINER_PATH}:ro" \
  dind-dev

# Execute commands in the container
docker exec -i -u dockeruser \
  -w ${WORK_DIR} \
  ${CONTAINER_NAME} \
  "${COMMAND[@]}"

# Optionally, delete the container
docker rm -f ${CONTAINER_NAME} 2> /dev/null
```

### Managing Docker Volumes

Docker volumes persist data between container runs and provide better
performance than bind mounts for Docker's internal data.

```bash
# List all volumes
docker volume ls

# Inspect a specific volume
docker volume inspect ${VOLUME_NAME}

# Remove a volume (WARNING: This will delete all data)
docker volume rm ${VOLUME_NAME}

# Create a named volume
docker volume create ${VOLUME_NAME}

# Remove unused volumes
docker volume prune
```

### Key Benefits

- **Isolation**: Tasks run in a completely isolated environment
- **Persistence**: Docker volumes maintain state between runs
- **Performance**: Named volumes offer better I/O performance than bind mounts
- **Security**: Read-only bind mounts prevent accidental modifications to host
  files
