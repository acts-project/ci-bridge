run:
    uv run sanic ci_relay.web:create_app -d

test:
    uv run pytest

image_url := "ghcr.io/acts-project/ci-bridge/acts-ci-bridge:latest"
image:
    docker build -t {{image_url}} .
    docker push {{image_url}}


deploy: image
    oc import-image ci-bridge --all
