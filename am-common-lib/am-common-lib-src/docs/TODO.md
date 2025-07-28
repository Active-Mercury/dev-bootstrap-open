# Project TODOs

## High Priority

- [x] Introduce a script for running tests inside a docker-in-docker container.
- [x] Introduce a dind-dev image based on docker:dind for properly running the
      suites in a Linux environment.
- [x] Correct DockerRunnerUserView.copy_to logic, so that the owning user will
      now be correctly set.
- [x] Add tests for devenv so that there is adequate coverage for the
      executables from it that are installed. Also, this paves the way to a
      future refactor.
- [ ] Finish out the tests for `docker_runner.py`, especially
      `DockerRunnerUserView`.

## Unprioritized Items

Edit these and move them to one of the other lists.

- `cli_echo` should report the basename
- Rough draft item 2

## Low Priority

- [ ] Low priority item 1
- [ ] Low priority item 2
