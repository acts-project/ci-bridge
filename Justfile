run:
    dotenvx run -- uv run sanic ci_relay.web:create_app -d -p 5001

test:
    uv run pytest

test-all:
    uv run --frozen --python 3.11 pytest
    uv run --frozen --python 3.12 pytest
    uv run --frozen --python 3.13 pytest

lint:
    uv run --frozen pre-commit run --all-files

image_url := "ghcr.io/acts-project/ci-bridge"
sha := "sha-" + `git rev-parse --short HEAD`
image:
    docker build --platform linux/amd64 -t {{image_url}}:{{sha}} .
    docker tag {{image_url}}:{{sha}} {{image_url}}:latest
    docker push {{image_url}}:{{sha}}
    docker push {{image_url}}:latest


deploy: image
    oc import-image ci-bridge --all
