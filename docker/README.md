# Docker Support

The root `Dockerfile` builds the v7 runtime image. This directory is reserved
for Docker-specific support files when the image needs them; it currently has
no additional build context.

The image is validated by `.github/workflows/docker.yaml`. Build it locally
from the repository root:

```bash
docker build -t liteyukibot:v7-local .
docker run --rm liteyukibot:v7-local version
```

Do not add secrets, workspace data, profiles, or plugin bundles to image
layers. The image runs as a non-root user and exposes `/app/data` and
`/app/cache` as persistent volumes.
