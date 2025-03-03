run:
    uv run sanic ci_relay.web:create_app -d

test:
    uv run pytest

image_url := "ghcr.io/acts-project/ci-bridge"
sha := "sha-" + `git rev-parse --short HEAD`
image:
    docker build -t  {{image_url}}:{{sha}} .
    docker tag {{image_url}}:{{sha}} {{image_url}}:latest
    docker push {{image_url}}:{{sha}}
    docker push {{image_url}}:latest


deploy: image
    sleep 1
    oc import-image ci-bridge --all
